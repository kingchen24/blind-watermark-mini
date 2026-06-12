# -*- coding: utf-8 -*-
"""
blind-watermark-mini — 基于 DCT+SVD 的频域数字盲水印精简实现

复现自 guofei9987/blind_watermark (MIT License, 12.8k stars)

核心算法流程：
┌─────────────────────────────────────────────────────┐
│  嵌入：原图 → YUV → DWT(LL) → 4×4分块 → DCT →    │
│        加密打乱 → SVD → QIM修改奇异值 → 逆变换      │
│  提取：含水印图 → 同样变换 → SVD → 模运算解码 →    │
│        多通道投票平均 → 解密还原                     │
└─────────────────────────────────────────────────────┘

技术要点：
  1. DWT 取低频子带 (LL) — 集中图像主要能量，抗压缩
  2. DCT 频域变换 — 将空间域分块转到频域
  3. SVD 奇异值修改 — 在最大奇异值嵌水印，抗几何攻击
  4. QIM 量化索引调制 — s=(s//d+1/4+wm/2)*d 实现盲提取
  5. 密码置乱 — 双重种子控制系数顺序和水印顺序
"""

import numpy as np
from numpy.linalg import svd
import cv2
from cv2 import dct, idct
from pywt import dwt2, idwt2


class BlindWatermark:
    """频域盲水印核心类

    Attributes:
        block_shape: 分块大小 (默认 4×4)
        d1, d2: 量化步长，越大鲁棒性越强但图像失真越大
    """

    def __init__(self, password_img=1, password_wm=1, block_shape=(4, 4)):
        self.block_shape = np.array(block_shape)
        self.password_img = password_img
        self.password_wm = password_wm

        # 量化步长：控制嵌入强度
        # d1/d2 越大 → 水印越鲁棒，但图片失真也越大
        # d1/d2 是原作者经过大量实验选取的默认值
        self.d1, self.d2 = 36, 20

        # 内部状态
        self.img = None           # 原始图片 (BGR)
        self.img_YUV = None       # YUV 色彩空间图片
        self.ca = None            # DWT 低频分量 (3通道)
        self.hvd = None           # DWT 高频分量 (3通道)
        self.ca_block = None      # 4维分块后的低频分量
        self.wm_bit = None        # 水印比特数组
        self.wm_size = 0          # 水印长度(bit)

    # ──────────────────────────
    # 1. 图片预处理
    # ──────────────────────────
    def read_img(self, img):
        """
        读取并预处理图片
        1. 处理透明通道 (RGBA → RGB)
        2. BGR → YUV (分离亮度/色度，在Y通道嵌入对人眼影响最小)
        3. 补白边使尺寸为偶数 (DWT 要求)
        """
        self.alpha = None
        if img.shape[2] == 4 and img[:, :, 3].min() < 255:
            self.alpha = img[:, :, 3].copy()
            img = img[:, :, :3]

        self.img = img.astype(np.float32)
        self.img_shape = self.img.shape[:2]
        h, w = self.img_shape

        # 确保偶数尺寸 → 否则补白边
        self.img_YUV = cv2.copyMakeBorder(
            cv2.cvtColor(self.img, cv2.COLOR_BGR2YUV),
            0, h % 2, 0, w % 2,
            cv2.BORDER_CONSTANT, value=(0, 0, 0)
        )

        # DWT 后 LL 子带尺寸减半
        self.ca_shape = [(s + 1) // 2 for s in self.img_shape]

        # 计算分块网格
        bh, bw = self.block_shape
        self.ca_block_shape = (
            self.ca_shape[0] // bh,
            self.ca_shape[1] // bw,
            bh, bw
        )
        self.block_count = self.ca_block_shape[0] * self.ca_block_shape[1]

        # 对每个通道做 DWT + as_strided 分块
        self.ca = [None] * 3
        self.hvd = [None] * 3
        self.ca_block = [None] * 3

        for ch in range(3):
            # Haar 小波分解：取低频 LL
            self.ca[ch], (cH, cV, cD) = dwt2(self.img_YUV[:, :, ch], 'haar')
            self.hvd[ch] = (cH, cV, cD)

            # ★ 核心技巧：as_strided 零拷贝4维分块
            # 将 (H, W) 的2D数组 → (H/bh, W/bw, bh, bw) 的4D数组
            # 内存视图共享，无拷贝开销
            strides = 4 * np.array([
                self.ca_shape[1] * bh,  # 跨行步长
                bw,                      # 跨列步长
                self.ca_shape[1],        # 块内行步长
                1                        # 块内列步长
            ])
            self.ca_block[ch] = np.lib.stride_tricks.as_strided(
                self.ca[ch].astype(np.float32),
                self.ca_block_shape, strides
            )

    def read_wm(self, wm_bit):
        """读取水印比特（内部会复制一份，不污染用户输入）"""
        self.wm_bit = wm_bit.copy() if hasattr(wm_bit, 'copy') else wm_bit
        self.wm_size = self.wm_bit.size
        if self.wm_size > self.block_count:
            raise ValueError(
                f'水印过长: {self.wm_size}bit > 容量{self.block_count}bit')

    # ──────────────────────────
    # 2. 嵌入水印
    # ──────────────────────────
    def _embed_block(self, block, shuffle_idx, wm_idx):
        """
        在单个 4×4 分块中嵌入 1 bit 水印

        算法步骤:
          1. DCT 变换 → 频域系数
          2. 按密码打乱系数顺序（加密）
          3. SVD 分解 → 奇异值
          4. QIM 修改 s[0]（最大奇异值）: s = (s//d + 1/4 + wm/2) * d
          5. 逆 SVD → 逆打乱 → 逆 DCT
        """
        wm_bit = self.wm_bit[wm_idx % self.wm_size]
        block_dct = dct(block)

        # 加密：打乱 DCT 系数顺序
        shuffled = block_dct.flatten()[shuffle_idx].reshape(self.block_shape)
        u, s, v = svd(shuffled)

        # QIM 嵌入：在两个奇异值上嵌入同一 bit 增加冗余
        s[0] = (s[0] // self.d1 + 0.25 + 0.5 * wm_bit) * self.d1
        s[1] = (s[1] // self.d2 + 0.25 + 0.5 * wm_bit) * self.d2

        # 逆变换
        restored = np.dot(u, np.dot(np.diag(s), v)).flatten()
        restored[shuffle_idx] = restored.copy()
        return idct(restored.reshape(self.block_shape))

    def embed(self):
        """执行水印嵌入，返回含水印图片 (BGR, uint8)"""
        # 生成置乱索引（密码做种子，保证可复现）
        shuffle_idx = _random_shuffle_idx(
            self.password_img, self.block_count,
            self.block_shape[0] * self.block_shape[1]
        )

        # 先加密水印比特本身
        np.random.RandomState(self.password_wm).shuffle(self.wm_bit)

        # 确保每个分块都能访问
        assert self.wm_size <= self.block_count, \
            f"水印{self.wm_size}bit超过容量{self.block_count}bit"

        # 对3个YUV通道分别嵌入
        embed_ca = [c.copy() for c in self.ca]
        bh, bw = self.block_shape

        for ch in range(3):
            blocks = self.ca_block[ch]
            for i in range(self.block_count):
                r, c = divmod(i, self.ca_block_shape[1])
                blocks[r, c] = self._embed_block(
                    blocks[r, c], shuffle_idx[i], i)

            # 4维分块 → 2维
            ca_part = np.concatenate(
                np.concatenate(blocks, axis=1), axis=1)
            part_h = self.ca_block_shape[0] * bh
            part_w = self.ca_block_shape[1] * bw
            embed_ca[ch][:part_h, :part_w] = ca_part

        # 逆 DWT 重构
        embed_YUV = np.zeros_like(self.img_YUV)
        for ch in range(3):
            embed_YUV[:, :, ch] = idwt2(
                (embed_ca[ch], self.hvd[ch]), 'haar')

        # 裁剪回原始尺寸 → YUV→BGR → 截断
        embed_YUV = embed_YUV[:self.img_shape[0], :self.img_shape[1]]
        embed_img = cv2.cvtColor(embed_YUV, cv2.COLOR_YUV2BGR)
        embed_img = np.clip(embed_img, 0, 255).astype(np.uint8)

        # 恢复透明通道
        if self.alpha is not None:
            embed_img = cv2.merge([embed_img, self.alpha])

        return embed_img

    # ──────────────────────────
    # 3. 提取水印
    # ──────────────────────────
    def _extract_block(self, block, shuffle_idx):
        """
        从单个分块提取 1 bit
        逆过程: DCT → 加密打乱 → SVD → s[0] % d1 判断
        """
        block_dct = dct(block)
        shuffled = block_dct.flatten()[shuffle_idx].reshape(self.block_shape)
        u, s, v = svd(shuffled)

        # 从两个奇异值解码，加权投票
        wm0 = 1 if s[0] % self.d1 > self.d1 / 2 else 0
        wm1 = 1 if s[1] % self.d2 > self.d2 / 2 else 0
        # s[0] 权重 3，s[1] 权重 1
        return (wm0 * 3 + wm1) / 4

    def extract(self, img, wm_shape):
        """
        从含水印图中提取水印

        Args:
            img: 含水印图片 (numpy array, BGR)
            wm_shape: 水印形状 (h, w) 或 (length,)

        Returns:
            水印比特数组 (0~1 浮点值)
        """
        self.read_img(img)
        wm_h, wm_w = wm_shape[0], wm_shape[1]
        self.wm_size = wm_h * wm_w

        shuffle_idx = _random_shuffle_idx(
            self.password_img, self.block_count,
            self.block_shape[0] * self.block_shape[1]
        )

        # 3通道分别提取
        wm_3ch = np.zeros((3, self.block_count))
        for ch in range(3):
            blocks = self.ca_block[ch]
            for i in range(self.block_count):
                r, c = divmod(i, self.ca_block_shape[1])
                wm_3ch[ch, i] = self._extract_block(
                    blocks[r, c], shuffle_idx[i])

        # 循环嵌入 + 多通道求平均
        wm_avg = np.zeros(self.wm_size)
        for i in range(self.wm_size):
            wm_avg[i] = wm_3ch[:, i::self.wm_size].mean()

        # K-means 二值化
        threshold = _kmeans_threshold(wm_avg)
        wm_bits = (wm_avg > threshold).astype(np.uint8)

        # 解密水印顺序
        wm_index = np.arange(self.wm_size)
        np.random.RandomState(self.password_wm).shuffle(wm_index)
        wm_bits[wm_index] = wm_bits.copy()

        return wm_bits.reshape(wm_h, wm_w)


# ══════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════

def _random_shuffle_idx(seed, n_blocks, block_size):
    """生成基于密码种子的置乱索引矩阵"""
    rng = np.random.RandomState(seed)
    return rng.random(size=(n_blocks, block_size)).argsort(axis=1)


def _kmeans_threshold(values, max_iter=300):
    """一维 K-means 二值化（自动寻找最佳阈值）"""
    c0, c1 = values.min(), values.max()
    eps = 1e-6
    for _ in range(max_iter):
        threshold = (c0 + c1) / 2
        mask = values > threshold
        new_c0, new_c1 = values[~mask].mean(), values[mask].mean()
        if abs((new_c0 + new_c1) / 2 - threshold) < eps:
            return (new_c0 + new_c1) / 2
        c0, c1 = new_c0, new_c1
    return (c0 + c1) / 2


# ══════════════════════════════════════════
# 便捷高层 API
# ══════════════════════════════════════════

def text_to_bits(text):
    """文本 → 比特数组（保留每个字节的8位，不丢前导零）"""
    raw_bytes = text.encode('utf-8')
    bit_str = ''.join(format(b, '08b') for b in raw_bytes)
    return np.array([int(c) for c in bit_str], dtype=np.uint8)


def bits_to_text(bits):
    """比特数组 → 文本"""
    bit_str = ''.join(str(int(b)) for b in bits)
    # 按8位分组，保留前导零
    n_bytes = len(bit_str) // 8
    byte_vals = [int(bit_str[i * 8:(i + 1) * 8], 2) for i in range(n_bytes)]
    try:
        return bytes(byte_vals).decode('utf-8', errors='replace')
    except (ValueError, UnicodeDecodeError):
        return f"[解码失败] 原始比特: {bit_str[:80]}..."


def embed_text(image_path, text, output_path,
               password_img=1, password_wm=1):
    """在图片中嵌入文本水印"""
    img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(f"无法读取图片: {image_path}")

    bwm = BlindWatermark(password_img, password_wm)
    bwm.read_img(img)

    wm_bits = text_to_bits(text)
    bwm.read_wm(wm_bits)

    result = bwm.embed()
    cv2.imwrite(output_path, result)
    print(f"[嵌入成功] 水印文本: '{text}' ({len(wm_bits)} bit) → {output_path}")
    return result


def extract_text(image_path, wm_length,
                 password_img=1, password_wm=1):
    """从图片中提取文本水印"""
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"无法读取图片: {image_path}")

    bwm = BlindWatermark(password_img, password_wm)
    bits = bwm.extract(img, (wm_length, 1)).flatten()

    text = bits_to_text(bits)
    print(f"[提取成功] 水印内容: '{text}'")
    return text


def embed_image_wm(image_path, wm_image_path, output_path,
                   password_img=1, password_wm=1):
    """在图片中嵌入图片水印（如 logo 二维码）"""
    img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    wm_img = cv2.imread(wm_image_path, cv2.IMREAD_GRAYSCALE)
    if img is None or wm_img is None:
        raise FileNotFoundError("图片或水印图读取失败")

    bwm = BlindWatermark(password_img, password_wm)
    bwm.read_img(img)

    # 水印图二值化
    wm_bits = (wm_img.flatten() > 128)
    bwm.read_wm(wm_bits)

    result = bwm.embed()
    cv2.imwrite(output_path, result)
    wm_h, wm_w = wm_img.shape
    print(f"[嵌入成功] 水印图 {wm_w}×{wm_h} → {output_path}")
    return result


def extract_image_wm(image_path, wm_shape,
                     password_img=1, password_wm=1):
    """从图片中提取图片水印"""
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"无法读取图片: {image_path}")

    bwm = BlindWatermark(password_img, password_wm)
    wm = bwm.extract(img, wm_shape)

    wm_img = (wm * 255).astype(np.uint8)
    out_path = image_path.rsplit('.', 1)[0] + '_extracted_wm.png'
    cv2.imwrite(out_path, wm_img)
    print(f"[提取成功] 水印图 → {out_path}")
    return wm_img
