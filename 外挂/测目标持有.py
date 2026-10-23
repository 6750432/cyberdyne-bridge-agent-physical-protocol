#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L3：任务栈 B 口径（背包+箱子 >= target）单测。"""
import sys, tempfile, time, json, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import bridge

def mk():
    d = tempfile.mkdtemp(prefix="owned-")
    st = bridge.任务栈({}, lambda *a, **k: None, lambda *a, **k: None, d)
    return st, d

def task(st, steps, target=5, step=0):
    st.任务 = {
        "id": "T-%d" % id(st), "名字": "测试", "步骤": list(steps),
        "第几步": step, "重试": 0, "状态": "跑",
        "起点": [0, 64, 0], "开始时刻": time.time(), "步骤开始": 0.0,
        "重试到": 0.0, "暂停时刻": None, "暂停原因": None,
        "下发过": False, "目标物品": "oak_log", "目标数量": target,
        "口径": "owned", "failure_code": None,
    }

# 1) 背包 4 / 目标 5 / 箱子 0 → 失败，failure_code=incomplete_collection
st, d = mk(); task(st, [{"动作": "说", "文本": "x"}], target=5)
r = st._下一步({"items": {"oak_log": 4}})
print("case1", r, st.任务["状态"], st.任务.get("failure_code"))
assert r is False and st.任务["状态"] == "败"
assert st.任务.get("failure_code") == "incomplete_collection"

# 2) 背包 4 + 箱子 1 → 成功
st, d = mk(); task(st, [{"动作": "说", "文本": "x"}], target=5)
st.箱子账["oak_log"] = 1
r = st._下一步({"items": {"oak_log": 4}})
print("case2", r, st.任务["状态"], st.任务.get("failure_code"))
assert r is False and st.任务["状态"] == "完"
assert st.任务.get("failure_code") is None

# 3) 往箱子里放 1（背包 5→4）→ 箱子账 +1；目标 5 → 成功
st, d = mk(); task(st, [{"动作": "往箱子里放", "物品": "oak_log", "数量": 1, "_放前": 5}], target=5)
r = st._下一步({"items": {"oak_log": 4}})
print("case3", r, st.任务["状态"], st.箱子账)
assert r is False and st.任务["状态"] == "完"
assert st.箱子账.get("oak_log") == 1

# 4) 箱子里取 1（背包 4→5）→ 箱子账 +1 → 0；目标 5 → 成功
st, d = mk(); task(st, [{"动作": "箱子里取", "物品": "oak_log", "数量": 1, "_进项前": 4}], target=5)
st.箱子账["oak_log"] = 1
r = st._下一步({"items": {"oak_log": 5}})
print("case4", r, st.任务["状态"], st.箱子账)
assert r is False and st.任务["状态"] == "完"
assert st.箱子账.get("oak_log", 0) == 0
# 5) live chest 1 + 背包 4 → 目标 5 成功（箱子真读数）
st, d = mk(); task(st, [{"动作": "说", "文本": "x"}], target=5)
r = st._下一步({"items": {"oak_log": 4}, "chest": {"items": {"oak_log": 1}, "t": 123}})
print("case5", r, st.任务["状态"], st.任务.get("实际持有"))
assert r is False and st.任务["状态"] == "完"
assert st.任务.get("实际持有", {}).get("箱子来源") == "live"

# 6) live chest 0，且账本里有 10 —— 必须只信 live，不能拿账本补成成功
st, d = mk(); task(st, [{"动作": "说", "文本": "x"}], target=5)
st.箱子账["oak_log"] = 10
r = st._下一步({"items": {"oak_log": 4}, "chest": {"items": {}, "t": 124}})
print("case6", r, st.任务["状态"], st.任务.get("failure_code"))
assert r is False and st.任务["状态"] == "败"
assert st.任务.get("failure_code") == "incomplete_collection"

# 7) live chest 3 + 背包 1 → 4 < 5 失败
st, d = mk(); task(st, [{"动作": "说", "文本": "x"}], target=5)
r = st._下一步({"items": {"oak_log": 1}, "chest": {"items": {"oak_log": 3}, "t": 125}})
print("case7", r, st.任务["状态"], st.任务.get("failure_code"))
assert r is False and st.任务["状态"] == "败"

print("OWNED CONTRACT PASS")
