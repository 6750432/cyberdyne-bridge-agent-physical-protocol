#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""计划资源审计 —— STRIPS 效果闭合 + PDDL 同族 + collect 字段体检（只读 ✓ 不改任务 ✗）

用法：python3 tools/审计计划.py [logs/任务快照.json]
"""
import json
import os
import sys

根 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 只列**确定**的掉落；拿不准的方块跳过（不制造假阳性 ✗）
掉落 = {
    "stone": "cobblestone",
    "deepslate": "cobbled_deepslate",
    "coal_ore": "coal",
    "iron_ore": "raw_iron",
    "copper_ore": "raw_copper",
    "gold_ore": "raw_gold",
    "diamond_ore": "diamond",
    "redstone_ore": "redstone",
    "lapis_ore": "lapis_lazuli",
    "emerald_ore": "emerald",
    "nether_quartz_ore": "quartz",
    "nether_gold_ore": "gold_nugget",
}
木族 = ("oak", "birch", "spruce", "jungle", "acacia", "dark_oak",
        "mangrove", "cherry", "bamboo", "crimson", "warped")


def 掉落物(块):
    if 块 in 掉落:
        return 掉落[块]
    if 块.endswith("_log"):
        return 块
    return None


def 审计(任务):
    步骤 = 任务.get("步骤") or []
    问题 = []

    # ① 每挖必拾（效果闭合）
    for i, 步 in enumerate(步骤):
        if not isinstance(步, dict) or 步.get("动作") != "挖":
            continue
        块 = str(步.get("方块") or "")
        物 = 掉落物(块)
        if not 物:
            continue
        后 = 步骤[i + 1] if i + 1 < len(步骤) else {}
        已 = (isinstance(后, dict) and 后.get("动作") in ("拾", "collect")
              and str(后.get("物品") or "") == 物)
        if not 已:
            问题.append(f"第 {i} 步 挖「{块}」后面没有拾「{物}」")

    # ② 木族统一（挖/拾/合成同族）
    族 = set()
    for 步 in 步骤:
        if not isinstance(步, dict):
            continue
        for 键 in ("方块", "物品"):
            s = str(步.get(键) or "")
            for f in 木族:
                if s == f + "_log" or s == f + "_planks":
                    族.add(f)
    if len(族) > 1:
        问题.append(f"木族不统一：{sorted(族)}")

    # ③ collect 字段齐全（方块=找什么，物品=数什么）
    for i, 步 in enumerate(步骤):
        if not isinstance(步, dict) or 步.get("动作") != "collect":
            continue
        if not 步.get("方块") or not 步.get("物品"):
            问题.append(f"第 {i} 步 collect 缺「方块」或「物品」")
        try:
            if float(步.get("数量") or 0) <= 0:
                问题.append(f"第 {i} 步 collect 数量不是正数")
        except Exception:
            问题.append(f"第 {i} 步 collect 数量读不出来")

    # ④ 放/给的必填字段
    for i, 步 in enumerate(步骤):
        if not isinstance(步, dict):
            continue
        if 步.get("动作") == "放" and not (isinstance(步.get("p"), list) and len(步["p"]) >= 3):
            问题.append(f"第 {i} 步 放 没坐标")
        if 步.get("动作") == "给" and not 步.get("谁"):
            问题.append(f"第 {i} 步 给 没写谁")

    return 问题


def main():
    路 = sys.argv[1] if len(sys.argv) > 1 else os.path.join(根, "logs", "任务快照.json")
    try:
        with open(路, encoding="utf-8") as f:
            任务 = json.load(f)
    except Exception as e:
        print(f"✗ 读不到任务快照：{路}（{type(e).__name__}: {e}）")
        return 1
    if not isinstance(任务, dict):
        print(f"✗ 任务快照不是一个对象：{路}")
        return 1
    问题 = 审计(任务)
    if not 问题:
        print(f"✓ 计划审计通过：{路}（{len(任务.get('步骤') or [])} 步）")
        return 0
    print(f"✗ 计划审计发现 {len(问题)} 个问题：{路}")
    for q in 问题:
        print("  -", q)
    return 1


if __name__ == "__main__":
    sys.exit(main())
