#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查引号雷 —— 中文里夹 ASCII 双引号 = 语法雷（我今晚栽了三次 ✓ 做成闸门 ✓）

规矩（写死）：
  · 字符串里要引号，**一律用「」** ✓（项目惯例 ✓）
  · 只有**代码层**的双引号才用 ASCII " ✓
用法：python3 tools/查引号雷.py [目录…]    （默认扫 bridge.py + 外挂/*/补丁.py + tools/*.py）
只读 ✓ 不改文件 ✗ —— 但会**真编译**每个文件 ✓（那才是最终判据 ✓）
"""
import glob
import io
import os
import re
import sys

根 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
雷 = re.compile(r'[\u4e00-\u9fff]"')          # 中文字后面紧跟 ASCII 双引号 ⇒ 十有八九是雷


def 扫(路):
    坏 = []
    try:
        文 = io.open(路, encoding="utf-8").read()
    except Exception as e:
        return [("读不到", str(e)[:60])]
    # ① 真编译（最终判据 ✓）
    try:
        compile(文, 路, "exec")
    except SyntaxError as e:
        坏.append(("语法错", "第 %s 行：%s" % (e.lineno, e.msg)))
    # ② 引号雷：★ 2026-10-16 实测**误报 58 个**（`名字="库"` 这种是合法的 ✓）⇒ **删掉 ✗**
    #    教训：**正则判不了这个** ✗ —— 真正的判据只有 `compile()` ✓（上面那条 ✓ 保留 ✓）
    #    我自己改用**规矩**防它：字符串里要引号一律「」✓ 写完先跑本工具 ✓
    return 坏


def main():
    目标 = sys.argv[1:] or (["bridge.py"] + sorted(glob.glob("外挂/*/补丁.py")) + sorted(glob.glob("tools/*.py")))
    n = 0
    for 相对 in 目标:
        路 = 相对 if os.path.isabs(相对) else os.path.join(根, 相对)
        if not os.path.isfile(路):
            continue
        坏 = 扫(路)
        if 坏:
            n += 1
            print("✗ %s" % 相对)
            for 类, 说 in 坏[:6]:
                print("     [%s] %s" % (类, 说))
    print("── 扫了 %d 个文件 ✓ 有问题的 %d 个 %s" % (len(目标), n, "✓ 干净" if n == 0 else "✗ 上面这些"))
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
