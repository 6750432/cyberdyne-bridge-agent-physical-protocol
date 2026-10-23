#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看轨迹 —— 读「认知轨迹」两本账，出一份**只读**的统计（主人方案第 1 步的验证工具 ✓）

用法：python3 tools/看轨迹.py [条数]
它只读 ✓ 不连服务端 ✗ 不发命令 ✗ 不写任何东西 ✗（除了打印 ✓）
"""
import json
import os
import sys
import time
from collections import Counter

根 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def 读(名, n=None):
    路 = os.path.join(根, "logs", 名)
    出 = []
    if not os.path.exists(路):
        return 出
    for l in open(路, encoding="utf-8", errors="replace"):
        l = l.strip()
        if not l:
            continue
        try:
            出.append(json.loads(l))
        except Exception:
            pass
    return 出[-n:] if n else 出


def 时刻(毫秒):
    try:
        return time.strftime("%H:%M:%S", time.localtime(float(毫秒) / 1000.0))
    except Exception:
        return "?"


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    链 = 读("思维链.jsonl", n)
    轨 = 读("轨迹.jsonl", n)

    print("═" * 66)
    print("认知轨迹 · 只读统计（读的是 logs/思维链.jsonl 与 logs/轨迹.jsonl ✓）")
    print("═" * 66)

    print("\n【一】它答应过的计划（思维链 ✓ 共 %d 条）" % len(链))
    for d in 链[-6:]:
        步 = d.get("计划") or []
        print("  %s ｜ %-22s ｜ %2d 步 ｜ 来源=%s"
              % (时刻(d.get("t")), str(d.get("任务"))[:22], d.get("步数") or len(步),
                 json.dumps(d.get("来源"), ensure_ascii=False)))
        if 步:
            print("        首三步：%s" % " → ".join(
                "%s%s" % (x.get("动作"), ("「%s」" % x.get("目标")) if x.get("目标") else "")
                for x in 步[:3]))

    判 = [d for d in 轨 if d.get("类型") == "判定"]
    事 = [d for d in 轨 if d.get("类型") == "事件"]
    print("\n【二】判定（轨迹 ✓ 共 %d 条）" % len(判))
    动 = Counter(d.get("动作") for d in 判)
    结 = Counter(d.get("结论") for d in 判)
    print("  按动作：%s" % dict(动))
    print("  按结论：%s" % dict(结))
    年 = [d.get("来源", {}).get("scan年龄毫秒") for d in 判
          if isinstance(d.get("来源"), dict) and isinstance(d.get("来源", {}).get("scan年龄毫秒"), (int, float))]
    if 年:
        print("  **判定依据的扫描年龄**：最小 %d ms ｜ 中位 %d ms ｜ 最大 %d ms"
              % (min(年), sorted(年)[len(年) // 2], max(年)))
        print("    （老祖句 5 ✓：每条判断都标了「它的世界图有多旧」✓）")
    无源 = sum(1 for d in 判 if not (d.get("来源") or {}).get("帧有scan"))
    print("  没有扫描帧就下判断的：**%d 条** %s" % (无源, "✓ 好" if 无源 == 0 else "⚠ 要看"))

    print("\n【三】事件（轨迹 ✓ 共 %d 条）" % len(事))
    print("  %s" % dict(Counter(d.get("事件") for d in 事)))

    print("\n【四】时间线（最近 12 条 ✓ 决策→行动→对账 的顺序）")
    for d in (轨[-12:] if n == 0 else 轨[-12:]):
        t = 时刻(d.get("t"))
        if d.get("类型") == "判定":
            print("  %s ｜ 判 %-8s 第%-2s步 ⇒ **%s**（scan %sms）"
                  % (t, d.get("动作"), d.get("第几步"), d.get("结论"),
                     (d.get("来源") or {}).get("scan年龄毫秒")))
        else:
            print("  %s ｜ 事 %-8s ｜ %s" % (t, d.get("事件"),
                                          json.dumps(d.get("细节"), ensure_ascii=False)[:70]))
    print("\n（先看「有没有」、再看「依据新不新」、最后看「顺序对不对」✓ —— 这三样就够验证设计了 ✓）")


if __name__ == "__main__":
    main()
