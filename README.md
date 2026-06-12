# blind-watermark-mini

> 基于 DCT + SVD 的频域数字盲水印 — 精简复现版

复现自 [guofei9987/blind_watermark](https://github.com/guofei9987/blind_watermark) (MIT License, ⭐12.8k)

---

## 什么是盲水印？

盲水印是一种将信息**隐形嵌入**图片的技术，嵌入后肉眼无法察觉，但可通过特定算法提取。**提取时无需原图**，因此称为「盲」水印。

适用于：
- 图片版权保护（嵌入作者署名、版权声明）
- 防伪溯源（嵌入唯一ID追踪泄漏源头）
- 隐蔽通信（在图片中隐藏消息）

---

## 核心原理

```
嵌入流程：
原图 → YUV色彩空间 → DWT(Haar小波取低频LL) → 4×4分块
    → DCT变换 → 密码置乱加密 → SVD奇异值分解
    → QIM量化修改奇异值 → 逆SVD → 逆置乱
    → 逆DCT → 逆DWT → 含水印图

提取流程（逆向，无需原图）：
含水印图 → 相同变换 → SVD → 模运算解码
    → 多通道+循环投票 → K-means二值化 → 解密还原
```

### 5 个核心设计技巧

| # | 技巧 | 作用 |
|---|------|------|
| 1 | **DWT 取低频子带 (LL)** | 图像主要能量集中在低频，水印嵌在此处抗 JPEG 压缩 |
| 2 | **DCT + SVD 混合变换** | 频域嵌入 + 奇异值稳定性，双重保证鲁棒性 |
| 3 | **QIM 量化索引调制** | `s = (s//d + 1/4 + wm/2) * d` — 修改后无需原图即可盲提取 |
| 4 | **密码双重置乱** | 图片密码控制 DCT 系数顺序，水印密码控制水印比特顺序，双重安全 |
| 5 | **多通道循环冗余** | YUV 三通道独立嵌入 + 水印循环重复，提取时投票平均，大幅提升准确率 |

---

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行演示

```bash
# 运行全部 5 个场景演示
python run.py

# 只运行某个场景
python run.py 1    # 文本盲水印
python run.py 2    # 图片水印(Logo)
python run.py 3    # 鲁棒性测试
python run.py 4    # 密码保护验证
python run.py 5    # 底层API演示

# 命令行模式
python run.py embed --image 原图.png --text "Copyright" --out 水印图.png
python run.py extract --image 水印图.png --length 72
```

### Python API

```python
from core import BlindWatermark, embed_text, extract_text
import cv2
import numpy as np

# === 高层 API ===

# 嵌入文本水印
embed_text(
    image_path="photo.png",
    text="Copyright © 2026",
    output_path="watermarked.png",
    password_img=1234,
    password_wm=5678
)

# 提取文本水印
text = extract_text(
    image_path="watermarked.png",
    wm_length=144,          # 文本字节数 × 8
    password_img=1234,
    password_wm=5678
)

# === 底层 API ===

bwm = BlindWatermark(password_img=1234, password_wm=5678)
img = cv2.imread("photo.png")

# 嵌入
bwm.read_img(img)
wm_bits = np.array([1, 0, 1, 1, 0, 0, 1, 0], dtype=np.uint8)
bwm.read_wm(wm_bits)
result = bwm.embed()   # 含水印图片 (numpy array)

# 提取（需新建实例，因为 read_img 会覆盖状态）
bwm2 = BlindWatermark(password_img=1234, password_wm=5678)
extracted = bwm2.extract(result, wm_shape=(8, 1))
```

---

## 关键参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `d1` | 36 | 最大奇异值量化步长，越大鲁棒性越强，但失真越大 |
| `d2` | 20 | 次大奇异值量化步长，作为辅助通道增加冗余 |
| `block_shape` | (4, 4) | DCT 分块大小 |
| `password_img` | — | 控制 DCT 系数加密的种子 |
| `password_wm` | — | 控制水印比特加密的种子 |

**容量估算**: 对于 H×W 图片，最大嵌入容量 ≈ H/8 × W/8 bit（约 (H×W)/64 bit）

---

## 鲁棒性

该算法能抵抗以下攻击：

| 攻击类型 | 抵抗能力 |
|----------|----------|
| JPEG 压缩 | ✓ 较好（低频嵌入） |
| 亮度调整 | ✓ 较好 |
| 椒盐噪声 | △ 一般 |
| 高斯模糊 | △ 一般 |
| 缩放 | ✗ 较差（建议加入缩放恢复） |
| 旋转 | ✗ 较差（同步问题） |

---

## 项目结构

```
blind-watermark-mini/
├── core.py           # 核心算法实现（~300行）
├── demo.py           # 5个场景完整演示
├── run.py            # 快速运行入口
├── requirements.txt  # 依赖清单
├── README.md         # 本文档
├── .gitignore
└── output/           # 输出目录
```

---

## 协议

MIT License — 继承自原项目 [blind_watermark](https://github.com/guofei9987/blind_watermark)
