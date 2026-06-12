# -*- coding: utf-8 -*-
"""
blind-watermark-mini — 可视化实例脚本
生成所有展示图片，用于 README 和文档

运行: python visualize.py
输出: output/fig_*.png
"""

import os, sys, io
import numpy as np
import cv2
import matplotlib
matplotlib.use('Agg')  # 无 GUI 后端
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.font_manager as fm

# ── 中文支持 ──────────────────────────
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial']
plt.rcParams['axes.unicode_minus'] = False

from core import (
    BlindWatermark, embed_text, extract_text,
    embed_image_wm, extract_image_wm,
    _random_shuffle_idx, _kmeans_threshold
)

OUTPUT_DIR = "output"
FIG_DIR = "figures"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(FIG_DIR, exist_ok=True)


# ════════════════════════════════════════════════════════════
# 工具函数
# ════════════════════════════════════════════════════════════

def create_realistic_image():
    """生成一张更像真实照片的测试图（山脉 + 天空渐变）"""
    h, w = 512, 512
    img = np.zeros((h, w, 3), dtype=np.uint8)

    for i in range(h):
        for j in range(w):
            # 天空渐变
            if i < h * 0.45:
                r = int(100 + 100 * (1 - i / (h * 0.45)))
                g = int(140 + 80 * (1 - i / (h * 0.45)))
                b = int(200 + 55 * (1 - i / (h * 0.45)))
            # 山脉区域
            else:
                mountain_h = 0.45 + 0.25 * np.sin(j / 80) * np.cos(j / 120) \
                           + 0.15 * np.sin(j / 40) * np.sin(j / 60)
                rel = (i / h - 0.45) / 0.55
                if i / h < mountain_h:
                    # 山体
                    r = int(40 + 60 * rel + 30 * np.sin(j / 30))
                    g = int(100 + 40 * rel + 20 * np.cos(j / 25))
                    b = int(50 + 30 * rel + 10 * np.sin(j / 20))
                else:
                    # 草地/前景
                    r = int(34 + 50 * (rel - (mountain_h - 0.45) / 0.55))
                    g = int(139 + 30 * (rel - (mountain_h - 0.45) / 0.55))
                    b = int(34 + 10 * (rel - (mountain_h - 0.45) / 0.55))

            # 添加微小纹理
            texture = np.random.randint(-5, 6)
            img[i, j] = np.clip([r + texture, g + texture, b + texture], 0, 255)

    return img


def create_binary_watermark():
    """创建品牌水印图（文字 + 边框）— 尺寸适配512×512图片容量"""
    wm = np.zeros((56, 56), dtype=np.uint8)

    # 文字
    cv2.putText(wm, "W", (6, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, 255, 2)
    cv2.putText(wm, "M", (32, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, 255, 2)

    # 边框
    cv2.rectangle(wm, (2, 2), (53, 53), 255, 2)
    # 装饰点
    cv2.circle(wm, (28, 44), 6, 255, 2)

    return wm


def jpeg_compress(img, quality):
    _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def bgr2rgb(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


# ════════════════════════════════════════════════════════════
# 图1: 总览 — 盲水印效果对比大图
# ════════════════════════════════════════════════════════════
def fig_overview():
    """生成总览图：原图 | 嵌入后 | 差异(×20) | 提取水印"""
    print("[1/6] 生成总览对比图...")

    # 准备数据
    original = create_realistic_image()
    wm = create_binary_watermark()
    cv2.imwrite(f"{OUTPUT_DIR}/tmp_original.png", original)
    cv2.imwrite(f"{OUTPUT_DIR}/tmp_wm.png", wm)

    embed_image_wm(f"{OUTPUT_DIR}/tmp_original.png",
                   f"{OUTPUT_DIR}/tmp_wm.png",
                   f"{OUTPUT_DIR}/tmp_embedded.png",
                   password_img=888, password_wm=666)

    embedded = cv2.imread(f"{OUTPUT_DIR}/tmp_embedded.png")
    diff = cv2.absdiff(original, embedded)
    diff_amp = np.clip(diff * 20, 0, 255).astype(np.uint8)

    extracted = extract_image_wm(f"{OUTPUT_DIR}/tmp_embedded.png",
                                 wm_shape=wm.shape,
                                 password_img=888, password_wm=666)

    psnr = cv2.PSNR(original, embedded)

    # 绘图
    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    fig.suptitle('数字盲水印 — 效果总览', fontsize=18, fontweight='bold', y=0.98)

    titles = [
        '① 原始图片 (512×512)',
        '② 嵌入水印后 (PSNR > 40dB)',
        '③ 差异放大 ×20 (揭示隐藏信息)',
        '④ 原始水印图案',
        '⑤ 提取出的水印',
        '⑥ 像素差异分布',
    ]
    images = [
        bgr2rgb(original),
        bgr2rgb(embedded),
        bgr2rgb(diff_amp),
        wm,
        extracted,
        None,  # 特殊处理：直方图
    ]

    for idx, ax in enumerate(axes.flat):
        if idx == 5:
            # 差异直方图
            flat_diff = diff.flatten()
            ax.hist(flat_diff, bins=50, color='#2196F3', alpha=0.8, edgecolor='white')
            ax.axvline(flat_diff.mean(), color='red', linestyle='--',
                      label=f'均值={flat_diff.mean():.1f}')
            ax.set_xlabel('像素差值')
            ax.set_ylabel('频数')
            ax.legend(fontsize=8)
        else:
            if len(images[idx].shape) == 2:
                ax.imshow(images[idx], cmap='gray')
            else:
                ax.imshow(images[idx])
        ax.set_title(titles[idx], fontsize=11)
        ax.axis('off' if idx != 5 else 'on')

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(f"{FIG_DIR}/fig_overview.png", dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print(f"  ✓ 保存: {FIG_DIR}/fig_overview.png (PSNR = {psnr:.1f} dB)")


# ════════════════════════════════════════════════════════════
# 图2: 算法原理流程图
# ════════════════════════════════════════════════════════════
def fig_algorithm_flow():
    """算法流程图：DWT → DCT → SVD → QIM"""
    print("[2/6] 生成算法原理图...")

    fig, axes = plt.subplots(1, 4, figsize=(18, 4.5))
    fig.suptitle('DWT+DCT+SVD+QIM 频域盲水印核心流程', fontsize=16,
                 fontweight='bold', y=0.98)

    # 准备演示数据
    img = np.zeros((256, 256, 3), dtype=np.uint8)
    for i in range(256):
        for j in range(256):
            img[i, j] = [
                int(128 + 96 * np.sin(i / 20) * np.cos(j / 20)),
                int(128 + 96 * np.cos((i + j) / 25)),
                int(128 + 96 * np.sin(j / 20)),
            ]

    bwm = BlindWatermark(password_img=7, password_wm=7)
    bwm.read_img(img)

    # -- 第1列: DWT低频子带 --
    ca_y = bwm.ca[0]  # Y 通道 LL
    ca_y_norm = (ca_y - ca_y.min()) / (ca_y.max() - ca_y.min() + 1e-8)

    ax = axes[0]
    ax.imshow(ca_y_norm, cmap='viridis')
    ax.set_title('① DWT 低频子带 (LL)\nHaar 小波, 128×128', fontsize=11)
    ax.axis('off')
    # 标注网格
    for r in range(0, 128, 32):
        ax.axhline(r, color='white', alpha=0.3, linewidth=0.5)
        ax.axvline(r, color='white', alpha=0.3, linewidth=0.5)

    # -- 第2列: DCT 频域系数 --
    block = bwm.ca_block[0][0, 0]  # 第一个 4×4 块
    block_dct = cv2.dct(block.astype(np.float32))
    block_dct_norm = (block_dct - block_dct.min()) / (block_dct.max() - block_dct.min() + 1e-8)

    ax = axes[1]
    im = ax.imshow(block_dct_norm, cmap='coolwarm', vmin=0, vmax=1)
    ax.set_title('② DCT 频域系数\n4×4 块频域变换', fontsize=11)
    for r in range(4):
        for c in range(4):
            val = block_dct[r, c]
            color = 'white' if abs(val) < abs(block_dct).max() * 0.5 else 'black'
            ax.text(c, r, f'{val:.0f}', ha='center', va='center',
                   fontsize=7, color=color)
    ax.set_xticks([])
    ax.set_yticks([])
    plt.colorbar(im, ax=ax, shrink=0.8, label='归一化强度')

    # -- 第3列: SVD 奇异值 --
    shuffle_idx = _random_shuffle_idx(7, 1, 16)[0]
    shuffled = block_dct.flatten()[shuffle_idx].reshape((4, 4))
    u, s, v = np.linalg.svd(shuffled)

    ax = axes[2]
    x = np.arange(len(s))
    colors = ['#FF5722' if i < 2 else '#9E9E9E' for i in range(len(s))]
    bars = ax.bar(x, s, color=colors, edgecolor='white', width=0.6)
    ax.set_title('③ SVD 奇异值分解\n修改 s[0], s[1] 嵌入水印', fontsize=11)
    ax.set_xlabel('奇异值索引')
    ax.set_ylabel('值')
    # QIM 标注
    ax.annotate('QIM嵌入\ns = (s//d+¼+wm/2)·d',
                xy=(0, s[0]), xytext=(1.5, s[0] * 1.3),
                arrowprops=dict(arrowstyle='->', color='#FF5722', lw=1.5),
                fontsize=9, color='#FF5722', fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='#FFF3E0', alpha=0.9))

    # -- 第4列: QIM 量化示意 --
    ax = axes[3]
    d1 = 36
    x_vals = np.linspace(0, d1 * 4, 500)
    wm0_vals = np.abs(x_vals % d1 - d1 / 2)  # bit=0 到中心的距离
    wm1_vals = np.abs((x_vals - d1 / 2) % d1 - d1 / 2)  # bit=1 到中心的距离

    ax.fill_between(x_vals, 0, wm0_vals,
                     where=(np.abs(x_vals % d1 - d1 * 0.75) < d1 * 0.25),
                     color='#4CAF50', alpha=0.4, label='嵌入 bit=1 (s mod d > d/2)')
    ax.fill_between(x_vals, 0, wm0_vals,
                     where=(np.abs(x_vals % d1 - d1 * 0.25) < d1 * 0.25),
                     color='#2196F3', alpha=0.4, label='嵌入 bit=0 (s mod d < d/2)')
    ax.plot(x_vals, wm0_vals, color='#333', linewidth=1)
    ax.axhline(d1 / 2, color='red', linestyle='--', linewidth=1, label=f'阈值 d/2 = {d1/2}')
    ax.set_title('④ QIM 量化索引调制\ns%d 判断水印比特', fontsize=11)
    ax.set_xlabel('奇异值 s')
    ax.set_ylabel('s mod d')
    ax.legend(loc='upper right', fontsize=7)
    ax.set_ylim(0, d1 * 1.2)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(f"{FIG_DIR}/fig_algorithm.png", dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print(f"  ✓ 保存: {FIG_DIR}/fig_algorithm.png")


# ════════════════════════════════════════════════════════════
# 图3: 不可见性证明 — PSNR + 并排对比
# ════════════════════════════════════════════════════════════
def fig_invisibility():
    """不可见性：并排对比 + 像素差异热力图"""
    print("[3/6] 生成不可见性证明图...")

    original = create_realistic_image()
    cv2.imwrite(f"{OUTPUT_DIR}/tmp_ori2.png", original)

    embed_text(f"{OUTPUT_DIR}/tmp_ori2.png",
               "Copyright (c) 2026 版权所有",
               f"{OUTPUT_DIR}/tmp_emb2.png",
               password_img=555, password_wm=777)

    embedded = cv2.imread(f"{OUTPUT_DIR}/tmp_emb2.png")
    psnr = cv2.PSNR(original, embedded)
    diff = cv2.absdiff(original, embedded)

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.suptitle('水印不可见性验证 — 肉眼无法分辨', fontsize=16,
                 fontweight='bold', y=0.98)

    # 左上：原图
    axes[0, 0].imshow(bgr2rgb(original))
    axes[0, 0].set_title(f'原始图片', fontsize=12, fontweight='bold')
    axes[0, 0].axis('off')

    # 右上：嵌入后
    axes[0, 1].imshow(bgr2rgb(embedded))
    axes[0, 1].set_title(f'嵌入水印后  (PSNR = {psnr:.1f} dB)', fontsize=12,
                         fontweight='bold')
    axes[0, 1].axis('off')

    # 左下：差异图（热力图）
    diff_gray = cv2.cvtColor(diff.astype(np.float32) * 20, cv2.COLOR_BGR2GRAY)
    im = axes[1, 0].imshow(diff_gray, cmap='hot')
    axes[1, 0].set_title(f'差异热力图 (×20放大)', fontsize=12, fontweight='bold')
    axes[1, 0].axis('off')
    plt.colorbar(im, ax=axes[1, 0], shrink=0.78, label='差异强度',
                 ticks=[], orientation='horizontal')

    # 右下：PSNR 标准参考
    ax = axes[1, 1]
    ax.axis('off')
    info_text = [
        "========  PSNR Reference  ========",
        "",
        f"  This image PSNR:  {psnr:.1f} dB",
        "",
        "  >= 40 dB  -> Invisible to eye  *",
        "  35-40 dB  -> Very slight diff",
        "  30-35 dB  -> Noticeable diff",
        "  < 30 dB   -> Obvious distortion",
        "",
        "  |diff| = |original - embedded|",
        f"  max diff  = {diff.max()}",
        f"  mean diff = {diff.mean():.2f}",
        "",
        "  * pixel range 0-255",
    ]
    ax.text(0.1, 0.95, '\n'.join(info_text), transform=ax.transAxes,
            fontsize=11, va='top', family='monospace',
            bbox=dict(boxstyle='round', facecolor='#E8F5E9', alpha=0.9))

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(f"{FIG_DIR}/fig_invisibility.png", dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print(f"  ✓ 保存: {FIG_DIR}/fig_invisibility.png")


# ════════════════════════════════════════════════════════════
# 图4: 鲁棒性攻击网格
# ════════════════════════════════════════════════════════════
def fig_robustness():
    """鲁棒性测试：各类攻击下提取效果网格"""
    print("[4/6] 生成鲁棒性测试图...")

    # 准备
    original = create_realistic_image()
    wm = create_binary_watermark()
    cv2.imwrite(f"{OUTPUT_DIR}/tmp_ori3.png", original)
    cv2.imwrite(f"{OUTPUT_DIR}/tmp_wm3.png", wm)

    embed_image_wm(f"{OUTPUT_DIR}/tmp_ori3.png",
                   f"{OUTPUT_DIR}/tmp_wm3.png",
                   f"{OUTPUT_DIR}/tmp_emb3.png",
                   password_img=42, password_wm=42)

    embedded = cv2.imread(f"{OUTPUT_DIR}/tmp_emb3.png")

    # 攻击列表
    attacks = {
        "无攻击": embedded,
        "JPEG Q=70": jpeg_compress(embedded, 70),
        "JPEG Q=30": jpeg_compress(embedded, 30),
        "JPEG Q=10": jpeg_compress(embedded, 10),
        "亮度+30%": np.clip(embedded * 1.3, 0, 255).astype(np.uint8),
        "亮度-30%": np.clip(embedded * 0.7, 0, 255).astype(np.uint8),
        "椒盐噪声 1%": None,  # 动态生成
        "高斯模糊 3×3": cv2.GaussianBlur(embedded, (3, 3), 0),
        "中值滤波 3×3": cv2.medianBlur(embedded, 3),
        "缩放50%还原": None,  # 动态生成
    }

    # 动态攻击
    noisy = embedded.copy()
    mask = np.random.rand(*embedded.shape[:2]) < 0.01
    noisy[mask] = 255
    mask = np.random.rand(*embedded.shape[:2]) < 0.01
    noisy[mask] = 0
    attacks["椒盐噪声 1%"] = noisy

    h, w = embedded.shape[:2]
    small = cv2.resize(embedded, (w // 2, h // 2))
    attacks["缩放50%还原"] = cv2.resize(small, (w, h))

    # 对每种攻击提取水印
    n = len(attacks)
    cols = 5
    rows = (n + cols - 1) // cols

    fig, axes = plt.subplots(rows * 2, cols, figsize=(16, rows * 4.5))
    fig.suptitle('鲁棒性测试 — 各种攻击下的水印提取效果', fontsize=16,
                 fontweight='bold', y=0.99)

    # 隐藏多余子图
    if rows * 2 * cols > 2 * n:
        for i in range(2 * n, rows * 2 * cols):
            r, c = divmod(i, cols)
            axes[r, c].axis('off')

    wm_truth = (wm > 128).astype(np.uint8)

    for idx, (name, attacked_img) in enumerate(attacks.items()):
        atk_path = f"{OUTPUT_DIR}/tmp_robust_{idx}.png"
        cv2.imwrite(atk_path, attacked_img)

        row_img = (idx // cols) * 2
        col = idx % cols

        # 上方：攻击后图片
        ax_img = axes[row_img, col]
        ax_img.imshow(bgr2rgb(attacked_img))
        ax_img.set_title(name, fontsize=10)
        ax_img.axis('off')

        # 下方：提取的水印
        try:
            extracted = extract_image_wm(atk_path, wm_shape=wm.shape,
                                         password_img=42, password_wm=42)
            acc = (extracted.astype(bool) == wm_truth.astype(bool)).mean()
            color = '#4CAF50' if acc > 0.85 else ('#FF9800' if acc > 0.6 else '#F44336')
        except Exception:
            extracted = np.zeros_like(wm)
            acc = 0
            color = '#F44336'

        ax_wm = axes[row_img + 1, col]
        ax_wm.imshow(extracted, cmap='gray')
        ax_wm.set_title(f'还原率 {acc*100:.1f}%', fontsize=10, color=color,
                        fontweight='bold')
        ax_wm.axis('off')

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(f"{FIG_DIR}/fig_robustness.png", dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print(f"  ✓ 保存: {FIG_DIR}/fig_robustness.png")


# ════════════════════════════════════════════════════════════
# 图5: 密码安全性演示
# ════════════════════════════════════════════════════════════
def fig_password_security():
    """密码保护机制可视化"""
    print("[5/6] 生成密码安全演示图...")

    original = create_realistic_image()
    cv2.imwrite(f"{OUTPUT_DIR}/tmp_ori4.png", original)
    secret = "SECRETKEY2026"

    embed_text(f"{OUTPUT_DIR}/tmp_ori4.png", secret,
               f"{OUTPUT_DIR}/tmp_emb4.png",
               password_img=1111, password_wm=9999)

    # 四种密码组合提取
    tests = [
        ("正确密码 (1111, 9999)", 1111, 9999, '#4CAF50'),
        ("错误水印密码 (1111, 1234)", 1111, 1234, '#FF9800'),
        ("错误图片密码 (5678, 9999)", 5678, 9999, '#FF9800'),
        ("双密码错误 (5678, 1234)", 5678, 1234, '#F44336'),
    ]

    fig, axes = plt.subplots(1, 4, figsize=(16, 4))
    fig.suptitle('双重密码安全机制', fontsize=16, fontweight='bold', y=0.98)

    for idx, (label, pw_img, pw_wm, color) in enumerate(tests):
        ax = axes[idx]
        try:
            result = extract_text(f"{OUTPUT_DIR}/tmp_emb4.png",
                                  len(secret.encode('utf-8')) * 8,
                                  password_img=pw_img, password_wm=pw_wm)
        except Exception:
            result = "[提取失败]"

        match = "[OK] 正确" if secret in result else "[XX] 乱码"

        # 画一个漂亮的卡片
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')

        bg_color = '#E8F5E9' if 'OK' in match else '#FFEBEE'
        rect = FancyBboxPatch((0.05, 0.05), 0.9, 0.9,
                              boxstyle="round,pad=0.1",
                              facecolor=bg_color, edgecolor=color,
                              linewidth=2)
        ax.add_patch(rect)

        ax.text(0.5, 0.88, label, transform=ax.transAxes, ha='center',
                fontsize=11, fontweight='bold', color=color)
        ax.text(0.5, 0.65, f"提取结果:", transform=ax.transAxes, ha='center',
                fontsize=9, color='#666')
        ax.text(0.5, 0.48, f"'{result}'", transform=ax.transAxes, ha='center',
                fontsize=12, fontweight='bold', fontfamily='monospace',
                color='#333', bbox=dict(facecolor='white', alpha=0.7,
                                        boxstyle='round'))
        ax.text(0.5, 0.22, match, transform=ax.transAxes, ha='center',
                fontsize=14, fontweight='bold', color=color,
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

        ax.text(0.5, 0.08, f"img_pwd={pw_img} wm_pwd={pw_wm}",
                transform=ax.transAxes, ha='center', fontsize=8,
                color='#999', fontfamily='monospace')

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(f"{FIG_DIR}/fig_password.png", dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print(f"  ✓ 保存: {FIG_DIR}/fig_password.png")


# ════════════════════════════════════════════════════════════
# 图6: 数据流转可视化（技术深度展示）
# ════════════════════════════════════════════════════════════
def fig_data_flow():
    """展示从像素到水印比特的完整数据流转"""
    print("[6/6] 生成数据流转深度展示图...")

    img = np.zeros((256, 256, 3), dtype=np.uint8)
    for i in range(256):
        for j in range(256):
            img[i, j] = [
                int(128 + 64 * np.sin(i / 10) * np.cos(j / 10)),
                int(128 + 64 * np.cos((i + j) / 15)),
                int(128 + 64 * np.sin(j / 10)),
            ]

    np.random.seed(42)
    wm_bits = np.random.randint(0, 2, 32, dtype=np.uint8)

    bwm = BlindWatermark(password_img=7, password_wm=7)
    bwm.read_img(img)
    bwm.read_wm(wm_bits.copy())

    # 获取中间数据
    y_ch = bwm.img_YUV[:, :, 0]
    ca_y = bwm.ca[0]
    block_00 = bwm.ca_block[0][0, 0]
    block_dct_00 = cv2.dct(block_00.astype(np.float32))

    fig, axes = plt.subplots(2, 4, figsize=(18, 8))
    fig.suptitle('盲水印数据流转 — 从像素到水印比特', fontsize=16,
                 fontweight='bold', y=0.99)

    # [0,0] 原图
    axes[0, 0].imshow(bgr2rgb(img))
    axes[0, 0].set_title('① 原始图片 (BGR)', fontsize=10, fontweight='bold')
    axes[0, 0].axis('off')

    # [0,1] Y通道
    axes[0, 1].imshow(y_ch, cmap='gray')
    axes[0, 1].set_title('② Y亮度通道', fontsize=10, fontweight='bold')
    axes[0, 1].axis('off')

    # [0,2] DWT LL子带
    ca_norm = (ca_y - ca_y.min()) / (ca_y.max() - ca_y.min() + 1e-8)
    axes[0, 2].imshow(ca_norm, cmap='plasma')
    axes[0, 2].set_title('③ DWT(LL) 128×128', fontsize=10, fontweight='bold')
    axes[0, 2].axis('off')
    for r in range(0, 128, 8):
        axes[0, 2].axhline(r, color='white', alpha=0.15, lw=0.3)
        axes[0, 2].axvline(r, color='white', alpha=0.15, lw=0.3)

    # [0,3] 4×4 分块示意
    sample_block = ca_y[:16, :16]
    axes[0, 3].imshow(sample_block, cmap='plasma')
    axes[0, 3].set_title('④ 4×4分块 局部放大', fontsize=10, fontweight='bold')
    axes[0, 3].axis('off')
    for r in range(0, 17, 4):
        axes[0, 3].axhline(r - 0.5, color='white', alpha=0.5, lw=1)
        axes[0, 3].axvline(r - 0.5, color='white', alpha=0.5, lw=1)

    # [1,0] DCT 系数
    bdc_norm = (block_dct_00 - block_dct_00.min()) / \
               (block_dct_00.max() - block_dct_00.min() + 1e-8)
    im00 = axes[1, 0].imshow(bdc_norm, cmap='coolwarm')
    axes[1, 0].set_title('⑤ DCT频域系数', fontsize=10, fontweight='bold')
    axes[1, 0].set_xticks([])
    axes[1, 0].set_yticks([])
    plt.colorbar(im00, ax=axes[1, 0], shrink=0.8)

    # [1,1] SVD 奇异值
    shuffle_idx = _random_shuffle_idx(7, 1, 16)[0]
    shuffled = block_dct_00.flatten()[shuffle_idx].reshape((4, 4))
    _, s, _ = np.linalg.svd(shuffled)

    axes[1, 1].bar(range(len(s)), s, color=['#FF5722', '#FF9800', '#9E9E9E', '#9E9E9E'])
    axes[1, 1].set_title('⑥ SVD奇异值', fontsize=10, fontweight='bold')
    axes[1, 1].set_ylabel('值')
    axes[1, 1].set_xlabel('索引')

    # [1,2] 嵌入后的平均响应
    result = bwm.embed()
    bwm2 = BlindWatermark(password_img=7, password_wm=7)
    bwm2.read_img(result)
    shuffle_idx2 = _random_shuffle_idx(7, bwm2.block_count, 16)
    wm_3ch = np.zeros((3, bwm2.block_count))
    for ch in range(3):
        blocks = bwm2.ca_block[ch]
        for i in range(bwm2.block_count):
            r, c = divmod(i, bwm2.ca_block_shape[1])
            wm_3ch[ch, i] = bwm2._extract_block(blocks[r, c], shuffle_idx2[i])

    wm_avg = np.zeros(32)
    for i in range(32):
        wm_avg[i] = wm_3ch[:, i::32].mean()

    x = np.arange(32)
    bars = axes[1, 2].bar(x, wm_avg,
                          color=['#4CAF50' if v > 0.5 else '#2196F3' for v in wm_avg])
    axes[1, 2].axhline(0.5, color='red', linestyle='--', linewidth=1.5, label='K-means阈值')
    axes[1, 2].set_title('⑦ 多通道投票平均', fontsize=10, fontweight='bold')
    axes[1, 2].set_xlabel('水印bit索引')
    axes[1, 2].set_ylabel('平均响应')
    axes[1, 2].legend(fontsize=7)

    # [1,3] 最终提取的水印
    extracted = bwm2.extract(result, (32, 1)).flatten()
    match = (wm_bits == extracted).sum()

    axes[1, 3].axis('off')
    info = [
        "8) Decrypt & Verify",
        "",
        f"Embed:  {''.join(str(b) for b in wm_bits)}",
        f"Extract:{''.join(str(b) for b in extracted)}",
        f"Match:  {match}/32 = {match/32*100:.0f}%",
        "",
        "Key params:",
        f"  img_size: {bwm.img_shape}",
        f"  blocks:   {bwm.block_count}",
        f"  QIM step: d1={bwm.d1}, d2={bwm.d2}",
        f"  redundancy: ~{bwm.block_count//32}x/bit",
    ]
    axes[1, 3].text(0.05, 0.95, '\n'.join(info), transform=axes[1, 3].transAxes,
                    fontsize=9, va='top', family='monospace',
                    bbox=dict(boxstyle='round', facecolor='#F3E5F5', alpha=0.9))

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(f"{FIG_DIR}/fig_data_flow.png", dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print(f"  ✓ 保存: {FIG_DIR}/fig_data_flow.png")


# ════════════════════════════════════════════════════════════
# 主函数
# ════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("  blind-watermark-mini 可视化实例生成")
    print("=" * 60)

    generators = [
        fig_overview,           # 1
        fig_algorithm_flow,     # 2
        fig_invisibility,       # 3
        fig_robustness,         # 4
        fig_password_security,  # 5
        fig_data_flow,          # 6
    ]

    if len(sys.argv) > 1:
        try:
            idx = int(sys.argv[1]) - 1
            if 0 <= idx < len(generators):
                generators[idx]()
            else:
                print(f"序号 1-{len(generators)}")
        except ValueError:
            print(f"未知参数: {sys.argv[1]}")
    else:
        for gen in generators:
            try:
                gen()
            except Exception as e:
                print(f"  ✗ 生成失败: {e}")
                import traceback
                traceback.print_exc()

    # 清理临时文件
    for f in os.listdir(OUTPUT_DIR):
        if f.startswith('tmp_'):
            os.remove(os.path.join(OUTPUT_DIR, f))

    print(f"\n✓ 全部完成! 图片保存在 {FIG_DIR}/ 目录")


if __name__ == '__main__':
    main()
