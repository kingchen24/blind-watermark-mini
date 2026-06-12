# -*- coding: utf-8 -*-
"""
blind-watermark-mini — 完整功能演示

运行: python demo.py
依赖: numpy, opencv-python, PyWavelets
"""

import os
import sys
import io
import numpy as np
import cv2

# 解决 Windows 终端中文编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from core import (
    BlindWatermark,
    embed_text, extract_text,
    embed_image_wm, extract_image_wm,
)

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def create_sample_images():
    """生成示例图片"""
    # 原图：彩色渐变
    img = np.zeros((512, 512, 3), dtype=np.uint8)
    for i in range(512):
        for j in range(512):
            img[i, j] = [
                int(128 + 127 * np.sin(i / 50) * np.cos(j / 50)),
                int(128 + 127 * np.sin((i + j) / 70)),
                int(128 + 127 * np.cos(j / 50)),
            ]
    cv2.imwrite(f"{OUTPUT_DIR}/sample_original.png", img)

    # 水印图：简单图案
    wm = np.zeros((64, 64), dtype=np.uint8)
    cv2.putText(wm, "WM", (5, 40), cv2.FONT_HERSHEY_SIMPLEX,
                1.0, 255, 2)
    cv2.imwrite(f"{OUTPUT_DIR}/sample_watermark.png", wm)

    return f"{OUTPUT_DIR}/sample_original.png", f"{OUTPUT_DIR}/sample_watermark.png"


# ══════════════════════════════════════════
# 场景 1：文本盲水印嵌入与提取
# ══════════════════════════════════════════
def demo_text_watermark():
    """演示文本盲水印"""
    print("\n" + "=" * 60)
    print("  场景 1：文本盲水印 — 在图片中隐形嵌入文字")
    print("=" * 60)

    # 输入图片（如果没有示例图则自动生成）
    input_img = f"{OUTPUT_DIR}/sample_original.png"
    if not os.path.exists(input_img):
        create_sample_images()

    # 嵌入文本水印
    secret_text = "Copyright (c) 2026 开源学习"
    embed_path = f"{OUTPUT_DIR}/scene1_embedded.png"

    embed_text(
        image_path=input_img,
        text=secret_text,
        output_path=embed_path,
        password_img=1234,   # 图片加密密码
        password_wm=5678     # 水印加密密码
    )

    # 验证：肉眼几乎不可见
    original = cv2.imread(input_img)
    embedded = cv2.imread(embed_path)
    diff = cv2.absdiff(original, embedded)
    diff_amplified = np.clip(diff * 20, 0, 255).astype(np.uint8)
    cv2.imwrite(f"{OUTPUT_DIR}/scene1_diff.png", diff_amplified)
    psnr = cv2.PSNR(original, embedded)
    print(f"  PSNR = {psnr:.1f} dB (值越大越接近原图，>40dB 肉眼不可见)")

    # 提取水印
    extracted = extract_text(
        image_path=embed_path,
        wm_length=len(secret_text.encode('utf-8')) * 8,
        password_img=1234,
        password_wm=5678
    )
    print(f"  原文本: '{secret_text}'")
    print(f"  提取文本: '{extracted}'")
    print(f"  匹配: {'✓ 成功' if secret_text in extracted else '✗ 失败'}")


# ══════════════════════════════════════════
# 场景 2：图片水印（品牌 Logo 防伪）
# ══════════════════════════════════════════
def demo_image_watermark():
    """演示图片盲水印 — 嵌入品牌Logo"""
    print("\n" + "=" * 60)
    print("  场景 2：图片盲水印 — 嵌入品牌 Logo / 二维码")
    print("=" * 60)

    ori_path, wm_path = create_sample_images()

    embed_path = f"{OUTPUT_DIR}/scene2_embedded.png"
    embed_image_wm(
        image_path=ori_path,
        wm_image_path=wm_path,
        output_path=embed_path,
        password_img=9999,
        password_wm=8888
    )

    original = cv2.imread(ori_path)
    embedded = cv2.imread(embed_path)
    psnr = cv2.PSNR(original, embedded)
    print(f"  PSNR = {psnr:.1f} dB")

    wm_img = cv2.imread(wm_path, cv2.IMREAD_GRAYSCALE)
    wm_truth = (wm_img > 128).astype(np.uint8)
    extracted_wm = extract_image_wm(
        image_path=embed_path,
        wm_shape=wm_img.shape,
        password_img=9999,
        password_wm=8888
    )
    match = (extracted_wm.astype(bool) == wm_truth.astype(bool)).mean()
    print(f"  水印还原率: {match * 100:.1f}%")


# ══════════════════════════════════════════
# 场景 3：鲁棒性测试 — 对抗图像攻击
# ══════════════════════════════════════════
def demo_robustness():
    """测试水印对各种攻击的抵抗能力"""
    print("\n" + "=" * 60)
    print("  场景 3：鲁棒性测试 — 水印抗攻击能力")
    print("=" * 60)

    ori_path, wm_path = create_sample_images()
    embed_path = f"{OUTPUT_DIR}/scene3_embedded.png"

    # 嵌入
    embed_image_wm(ori_path, wm_path, embed_path,
                   password_img=42, password_wm=42)

    wm_original = cv2.imread(wm_path, cv2.IMREAD_GRAYSCALE)

    # 攻击类型列表
    attacks = {
        "无攻击(原始)": lambda img: img,
        "JPEG压缩(Q=30)": lambda img: jpeg_compress_attack(img, 30),
        "亮度降低50%": lambda img: np.clip(img * 0.5, 0, 255).astype(np.uint8),
        "椒盐噪声(1%)": lambda img: salt_pepper_attack(img, 0.01),
        "高斯模糊(3×3)": lambda img: cv2.GaussianBlur(img, (3, 3), 0),
        "缩放50%→还原": lambda img: scale_attack(img, 0.5),
        "旋转5°": lambda img: rotate_attack(img, 5),
    }

    embedded = cv2.imread(embed_path)
    for name, attack_fn in attacks.items():
        attacked = attack_fn(embedded)
        atk_path = f"{OUTPUT_DIR}/scene3_{name.replace(' ', '_')}.png"
        cv2.imwrite(atk_path, attacked)

        try:
            extracted = extract_image_wm(
                image_path=atk_path,
                wm_shape=wm_original.shape,
                password_img=42,
                password_wm=42
            )
            accuracy = (extracted == wm_original).mean()
            bar = "█" * int(accuracy * 20) + "░" * (20 - int(accuracy * 20))
            print(f"  {name:<18s}  [{bar}]  {accuracy * 100:5.1f}%")
        except Exception as e:
            print(f"  {name:<18s}  [提取失败] {e}")


# ══════════════════════════════════════════
# 场景 4：密码保护验证
# ══════════════════════════════════════════
def demo_password_protection():
    """验证密码保护：水印密码提供强加密保护"""
    print("\n" + "=" * 60)
    print("  场景 4：密码安全验证 — 双重密码机制")
    print("=" * 60)

    ori_path, _ = create_sample_images()
    embed_path = f"{OUTPUT_DIR}/scene4_embedded.png"
    secret = "TopSecret2026"

    embed_text(ori_path, secret, embed_path,
               password_img=1234, password_wm=5678)

    # 正确密码
    r1 = extract_text(embed_path, len(secret.encode('utf-8')) * 8,
                      password_img=1234, password_wm=5678)
    print(f"  正确密码(1234,5678): '{r1}'")

    # 错误水印密码（强加密，必须匹配）
    r2 = extract_text(embed_path, len(secret.encode('utf-8')) * 8,
                      password_img=1234, password_wm=1111)
    ok2 = secret not in r2 and len(r2) > 0
    print(f"  错水印密码(1234,1111): '{r2}' → {'✓ 防篡改' if ok2 else '✗ 未防护'}")

    # 两个都错
    r3 = extract_text(embed_path, len(secret.encode('utf-8')) * 8,
                      password_img=7777, password_wm=2222)
    ok3 = secret not in r3 and len(r3) > 0
    print(f"  双错密码(7777,2222): '{r3}' → {'✓ 防篡改' if ok3 else '✗ 未防护'}")

    print("\n  📝 说明：password_img 提供 DCT 系数混淆（弱保护）")
    print("       password_wm 提供水印比特排列加密（强保护）")
    print("       原库设计：水印信号经 SVD 传播到多系数，即使")
    print("       系数顺序被混淆，仍能通过投票机制部分恢复。")


# ══════════════════════════════════════════
# 攻击辅助函数
# ══════════════════════════════════════════
def jpeg_compress_attack(img, quality):
    """JPEG 压缩攻击"""
    _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def salt_pepper_attack(img, ratio):
    """椒盐噪声攻击"""
    noisy = img.copy()
    mask = np.random.rand(*img.shape[:2]) < ratio
    noisy[mask] = 255
    mask = np.random.rand(*img.shape[:2]) < ratio
    noisy[mask] = 0
    return noisy


def scale_attack(img, scale):
    """缩放攻击（缩小再放大）"""
    h, w = img.shape[:2]
    small = cv2.resize(img, (int(w * scale), int(h * scale)))
    return cv2.resize(small, (w, h))


def rotate_attack(img, angle):
    """旋转攻击"""
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1)
    return cv2.warpAffine(img, M, (w, h))


# ══════════════════════════════════════════
# 场景 5：深度理解 — 用底层 API 手动走通全流程
# ══════════════════════════════════════════
def demo_low_level():
    """演示底层 API，理解每一步的数据流转"""
    print("\n" + "=" * 60)
    print("  场景 5：底层 API 逐步骤演示")
    print("=" * 60)

    # 创建 256x256 渐变测试图（更大=更多冗余=更好准确率）
    img = np.zeros((256, 256, 3), dtype=np.uint8)
    for i in range(256):
        for j in range(256):
            img[i, j] = [
                int(128 + 64 * np.sin(i / 10) * np.cos(j / 10)),
                int(128 + 64 * np.cos((i + j) / 15)),
                int(128 + 64 * np.sin(j / 10)),
            ]

    bwm = BlindWatermark(password_img=7, password_wm=7)
    bwm.read_img(img)
    print(f"  图片尺寸: {bwm.img_shape}")
    print(f"  DWT后LL尺寸: {bwm.ca_shape}")
    print(f"  分块网格: {bwm.ca_block_shape[0]}×{bwm.ca_block_shape[1]}")
    print(f"  水印容量: {bwm.block_count} bit ({bwm.block_count//8} 字节)")

    # 嵌入 32 bit 水印（每个 bit 约重复 32 次 × 3 通道 = 96 票）
    np.random.seed(42)
    wm_bits = np.random.randint(0, 2, 32, dtype=np.uint8)
    wm_bits_copy = wm_bits.copy()  # 保存副本，因为 embed() 会原地修改
    bwm.read_wm(wm_bits)
    result = bwm.embed()
    print(f"  嵌入 32 bit → 输出 {result.shape}")

    # 提取验证
    bwm2 = BlindWatermark(password_img=7, password_wm=7)
    extracted = bwm2.extract(result, (32, 1)).flatten()
    match_count = (wm_bits_copy == extracted).sum()
    print(f"  原始: {wm_bits_copy}")
    print(f"  提取: {extracted}")
    print(f"  匹配率: {match_count}/{len(wm_bits_copy)} = {match_count/len(wm_bits_copy)*100:.1f}%")

    # 逐步展示数据流转
    print(f"\n  📐 数据流转详解:")
    print(f"    原图 {bwm.img_shape} → DWT(Haar) → LL子带 {bwm.ca_shape}")
    print(f"    LL子带划分: {bwm.ca_block_shape[0]}×{bwm.ca_block_shape[1]} 个 {bwm.block_shape[0]}×{bwm.block_shape[1]} 块")
    print(f"    每块: DCT(4×4) → 密码置乱 → SVD → QIM修改奇异值 → 逆变换")
    print(f"    提取: 多通道投票 + 循环冗余平均 → K-means二值化 → 解密")


# ══════════════════════════════════════════
# 主函数
# ══════════════════════════════════════════
def main():
    print("=" * 60)
    print("  blind-watermark-mini — 数字盲水印完整演示")
    print("  基于 DCT+SVD 频域盲水印技术")
    print("=" * 60)

    demos = [
        ("1", "文本盲水印", demo_text_watermark),
        ("2", "图片水印(Logo)", demo_image_watermark),
        ("3", "鲁棒性测试", demo_robustness),
        ("4", "密码保护验证", demo_password_protection),
        ("5", "底层API演示", demo_low_level),
    ]

    # 命令行参数选择场景
    if len(sys.argv) > 1:
        selector = sys.argv[1]
        for sid, name, fn in demos:
            if sid == selector or name == selector:
                fn()
                return
        print(f"未知场景: {selector}")
        print(f"可选: {[d[0] + '=' + d[1] for d in demos]}")
    else:
        for _, name, fn in demos:
            fn()

    print("\n" + "=" * 60)
    print("  全部演示完成！")
    print(f"  输出文件保存在: {os.path.abspath(OUTPUT_DIR)}/")
    print("=" * 60)


if __name__ == '__main__':
    main()
