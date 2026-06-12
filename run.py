# -*- coding: utf-8 -*-
"""
blind-watermark-mini — 快速运行入口

用法:
    python run.py                          # 运行全部演示
    python run.py 1                        # 只运行场景1（文本盲水印）
    python run.py 2                        # 只运行场景2（图片水印）
    python run.py 3                        # 只运行场景3（鲁棒性测试）
    python run.py 4                        # 只运行场景4（密码验证）
    python run.py 5                        # 只运行场景5（底层API）

快速命令行:
    # 嵌入文本水印
    python run.py embed --image 原图.png --text "我的版权" --out 水印图.png

    # 提取文本水印
    python run.py extract --image 水印图.png --length 80
"""

import sys
import io
import argparse

# 解决 Windows 终端中文编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from demo import main as demo_main
from demo import demo_text_watermark, demo_image_watermark
from demo import demo_robustness, demo_password_protection, demo_low_level


SCENE_MAP = {
    "1": ("文本盲水印", demo_text_watermark),
    "2": ("图片水印(Logo)", demo_image_watermark),
    "3": ("鲁棒性测试", demo_robustness),
    "4": ("密码保护验证", demo_password_protection),
    "5": ("底层API演示", demo_low_level),
}


def main():
    if len(sys.argv) == 1:
        demo_main()
        return

    # 场景编号
    if sys.argv[1] in SCENE_MAP:
        name, fn = SCENE_MAP[sys.argv[1]]
        print(f"\n>>> 运行场景 {sys.argv[1]}: {name}")
        fn()
        return

    # 命令行模式
    parser = argparse.ArgumentParser(
        description="blind-watermark-mini 数字盲水印工具")
    sub = parser.add_subparsers(dest="cmd")

    p_embed = sub.add_parser("embed", help="嵌入文本水印")
    p_embed.add_argument("--image", required=True, help="原图路径")
    p_embed.add_argument("--text", required=True, help="水印文本")
    p_embed.add_argument("--out", default="output/embedded.png",
                         help="输出路径")
    p_embed.add_argument("--pwd-img", type=int, default=1,
                         help="图片密码")
    p_embed.add_argument("--pwd-wm", type=int, default=1,
                         help="水印密码")

    p_extract = sub.add_parser("extract", help="提取文本水印")
    p_extract.add_argument("--image", required=True, help="含水印图路径")
    p_extract.add_argument("--length", type=int, required=True,
                           help="水印长度(bit)")
    p_extract.add_argument("--pwd-img", type=int, default=1,
                           help="图片密码")
    p_extract.add_argument("--pwd-wm", type=int, default=1,
                           help="水印密码")

    args = parser.parse_args()

    if args.cmd == "embed":
        from core import embed_text
        embed_text(args.image, args.text, args.out,
                   args.pwd_img, args.pwd_wm)
    elif args.cmd == "extract":
        from core import extract_text
        extract_text(args.image, args.length,
                     args.pwd_img, args.pwd_wm)
    else:
        demo_main()


if __name__ == '__main__':
    main()
