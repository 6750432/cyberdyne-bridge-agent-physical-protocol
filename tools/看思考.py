#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看思考 —— 把小家伙的两本账**翻译成人话**（只读 ✓ 不改任何东西 ✓）

主人 2026-10-16：「以后可以看到小家伙的思考，就像我偶尔点开你的思维链偷窥你在想着什么一样」

★ 铁规矩（写死）：**叙述 = 把账本翻译成人话** ✓ —— **不许编** ✗
   每句话都必须能追回账本里的一行（事实 + 时刻 ✓）。账本里没有的，这里一个字都不许加 ✗。

用法：
   python3 tools/看思考.py            # 看最近一轮（人话时间线 ✓）
   python3 tools/看思考.py 40         # 看最近 40 条
   python3 tools/看思考.py --存        # 另存成 进度/小家伙的思考-<日期>.md
"""
import json
import os
import sys
import time

根 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def 读(名):
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
    return 出


def 时刻(毫秒):
    try:
        return time.strftime("%H:%M:%S", time.localtime(float(毫秒) / 1000.0))
    except Exception:
        return "?"


def 年纪(毫秒):
    """把"地图多旧"说成人话 ✓（句 5 ✓ 永远带上 ✓）"""
    if not isinstance(毫秒, (int, float)):
        return "地图年龄：没记 ✗"
    if 毫秒 < 1000:
        return "地图 %d 毫秒新 ✓" % 毫秒
    return "地图 %.1f 秒新 %s" % (毫秒 / 1000.0, "⚠ 有点旧" if 毫秒 > 3000 else "✓")


def 人话(条, 从="事件", 细节=None):
    """一条账 → 一句人话 ✓（只翻译 ✓ 不解释 ✓）"""
    动 = 条.get("动作")
    目 = 条.get("目标")
    要 = ("「%s」" % 目) if 目 else ""
    if 从 == "判定":
        if 条.get("结论") == "成":
            return "✓ 我看了一眼世界：%s%s **成了** ✓（%s）" % (动, 要, 年纪((条.get("来源") or {}).get("scan年龄毫秒")))
        return "… 我看了看：%s%s 还**没成** ✓ 接着等（%s）" % (动, 要, 年纪((条.get("来源") or {}).get("scan年龄毫秒")))
    事 = 条.get("事件")
    细 = 条.get("细节") or {}
    if 事 == "接单":
        return "★ 有人让我干活：「%s」%s 步（%s）✓" % (细.get("名字"), 细.get("步数"), str(细.get("步骤"))[:60])
    def 第几步():
        第 = 细.get("第几步")
        return ("第 %s 步 " % 第) if 第 not in (None, "None", "") else ""
    if 事 == "步骤开始":
        return "→ 我开始做%s：%s" % (第几步(), 细.get("动作"))
    if 事 == "步骤完成":
        return "✅ %s**做完了**（用了 %s 秒）" % (第几步() or (str(细.get("动作")) + " "), 细.get("用了"))
    if 事 == "步骤失败":
        return "✗ %s**没做成** —— 原因：%s" % (第几步() or (str(细.get("动作")) + " "), str(细.get("原因"))[:60])
    if 事 == "重试":
        return "↻ 我重试了一次 %s（第 %s 次，等 %s 秒）—— 原因：%s" % (
            细.get("动作"), 细.get("第几次"), 细.get("等"), str(细.get("原因"))[:50])
    if 事 in ("拒单", "替换", "判据出错", "整任务失败"):
        return "⚠ %s：%s" % (事, json.dumps(细, ensure_ascii=False)[:80])
    return "· %s %s" % (事, json.dumps(细, ensure_ascii=False)[:70])


def 计划人话(条):
    步 = 条.get("计划") or []
    出 = ["★ 我答应了这个活：**%s**（%d 步）｜%s"
          % (条.get("任务"), 条.get("步数") or len(步), 年纪((条.get("来源") or {}).get("scan年龄毫秒")))]
    for i, x in enumerate(步[:12]):
        目 = ("「%s」" % x.get("目标")) if x.get("目标") else (str(x.get("p")) if x.get("p") else "")
        出.append("    %2d. %s %s" % (i, x.get("动作"), 目))
    if len(步) > 12:
        出.append("    … 还有 %d 步" % (len(步) - 12))
    return 出


def main():
    n = 30
    存 = False
    for a in sys.argv[1:]:
        if a == "--存":
            存 = True
        elif a.isdigit():
            n = int(a)
    链 = 读("思维链.jsonl")
    轨 = 读("轨迹.jsonl")
    if not 链 and not 轨:
        print("★ 思维链/轨迹账本不存在或为空 —— **不是它没想，是这一节没开/没写** ✗")
        print("   查 config.json 的 认知轨迹.启用；车钩日志搜「挂「认知轨迹」」")
        print("   账本路径：logs/思维链.jsonl、logs/轨迹.jsonl")
        return
    合 = sorted([dict(x, _类="计划") for x in 链] + [dict(x, _类="账") for x in 轨],
                key=lambda d: d.get("t") or 0)[-n:]

    行 = ["# 小家伙的思考（只读翻译 ✓ 账本原文在 logs/思维链.jsonl 与 logs/轨迹.jsonl ✓）", ""]
    for d in 合:
        if d.get("_类") == "计划":
            行.append("**[%s]**" % 时刻(d.get("t")))
            行 += 计划人话(d)
        else:
            行.append("  `%s` %s" % (时刻(d.get("t")), 人话(d, d.get("类型"))))
    文 = "\n".join(行)
    print(文)
    if 存:
        路 = os.path.join(根, "进度", "小家伙的思考-%s.md" % time.strftime("%Y%m%d"))
        open(路, "w", encoding="utf-8").write(文 + "\n")
        print("\n（已存：%s ✓）" % 路)


if __name__ == "__main__":
    main()
