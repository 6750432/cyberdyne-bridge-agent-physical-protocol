#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自我模型 —— 只读观察 predicted vs actual（B 路 v0）。

边界（主人 2026-10-23 钦定）
============================
· **只读**：每个钩子第一件事都是回调原函数，返回值原样返回。
· **不写任务栈**、**不接管动作**、**不做 veto**、**不改老车厢**、**不改 bridge.py**。
· 只写一本新账：`logs/自我模型.jsonl`。
· 不开并行执行链；只观察，不产生第二个任务真相源。

它记什么
========
· 任务开始：计划、预测步数/耗时/成功/失败码、物理体检报告、起点。
· 步骤开始：动作、目标、预测单步耗时/成功、物理体检里与这一步相关的条目。
· 步骤下发：实际发出去的命令（只记，不改）。
· 步骤完成/失败：实际耗时、预测误差、失败原因、重试次数。
· 任务结束：实际步数/耗时/成功/失败码、preempted_by、回执噪声统计。
· 状态：任务在跑时 1 Hz；空闲时 5 秒一条。**不喂 200ms 原始帧。**

预测从哪来
==========
· 先读 A 路离线基线 `/tmp/selfmodel-batch/岸-对接/SELFMODEL_EXPERIENCES_V3.jsonl`：
  - 动作中位耗时（挖/走到/拾/给/合成）
  - 采集任务耗时 ≈ 0.443 + 1.591 × 计划步数
  - 采集成功先验 0.91；手工成功先验 1.0
· 读不到基线就用内置默认，并如实写一条“基线读不到”。

纪律
====
· 自己出错只写账，**绝不让主链因为观察者出错**（每个钩子 try 包住，原结果照返）。
· 不静默：基线读不到、体检不可用、钩子出错，都写进账。
"""
import copy
import glob
import json
import os
import statistics
import sys
import threading
import time
from collections import Counter

根 = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
默认账本 = os.path.join(根, "logs", "自我模型.jsonl")
默认基线 = "/tmp/selfmodel-batch/岸-对接/SELFMODEL_EXPERIENCES_V3.jsonl"
回执路 = os.path.join(根, "logs", "回执.jsonl")

_账本 = 默认账本
_日志 = None
_桥 = None
_原 = {}
_已装 = False
_停 = threading.Event()
_线程 = None
_锁 = threading.Lock()
_记录锁 = threading.RLock()
_回执锁 = threading.Lock()
_任务 = {}
_步 = {}
_已结束 = set()
_已下发 = set()
_已失败 = set()
_回执累计 = {"goto_sent": 0, "dig_sent": 0, "goto_interrupted": 0,
             "goto_path_timeout": 0, "dig_failed": 0}
_回执偏移 = 0
_上次状态 = 0.0
_基线 = {}
_错次 = []


def _说(文):
    if _日志:
        try:
            _日志(文)
            return
        except Exception:
            pass


def _记账(条):
    """只写 logs/自我模型.jsonl。失败不抛（观察者不许拖垮主链）。"""
    try:
        os.makedirs(os.path.dirname(_账本), exist_ok=True)
        with _锁:
            with open(_账本, "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": round(time.time(), 3), "车厢": "自我模型", **条},
                                   ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _错(在哪, e):
    if len(_错次) < 50:
        _错次.append((在哪, repr(e)[:160]))
    _记账({"事件": "观察者出错", "在哪": 在哪, "错": repr(e)[:300]})


# ══════════════════════════ 一、基线 ══════════════════════════

def _读基线():
    """读 A 路基线；读不到就用默认 + 如实记账。"""
    global _基线
    if _基线:
        return _基线
    默认 = {
        "动作中位": {"挖": 0.9, "走到": 1.2, "拾": 0.2, "给": 0.4, "合成": 0.3, "调": 2.0},
        "采集截距": 0.443, "采集斜率": 1.591,
        "采集成功先验": 0.91, "手工成功先验": 1.0,
        "成功来源": "prior_v3_0.91",
        "成功校准": "未校准；A_HELDOUT test observed=0.800，Brier=0.184（n=10）",
        "来源": "内置默认", "样本": 0,
    }
    try:
        行 = []
        with open(默认基线, encoding="utf-8") as f:
            for ln in f:
                行.append(json.loads(ln))
        分 = {}
        for r in 行:
            if not r.get("actual_success"):
                continue
            for p in (r.get("per_step") or []):
                if p.get("status") == "done" and isinstance(p.get("elapsed_sec"), (int, float)):
                    分.setdefault(str(p.get("action") or "?"), []).append(float(p["elapsed_sec"]))
        中位 = {a: round(statistics.median(v), 3) for a, v in 分.items() if v}
        if 中位:
            默认["动作中位"] = 中位
        默认["来源"] = 默认基线
        默认["样本"] = len(行)
        # ★ 任务耗时系数优先用 A 路留出 train 的拟合，不用 in-sample 的 0.443/1.591
        try:
            with open("/tmp/selfmodel-batch/岸-对接/A_HELDOUT.json", encoding="utf-8") as f:
                h = json.load(f)
            fit = (h.get("duration") or {}).get("fit") or {}
            if "intercept" in fit and "slope" in fit:
                默认["采集截距"] = float(fit["intercept"])
                默认["采集斜率"] = float(fit["slope"])
                # step 中位数也用 train 的（不是全 V3），避免留出泄漏
                tm = ((h.get("per_step") or {}).get("train_medians") or {})
                for _k, _v in tm.items():
                    try:
                        默认["动作中位"][str(_k)] = float(_v)
                    except Exception:
                        pass
                默认["来源"] = "A_HELDOUT train23（duration + step medians）；success=prior_v3_0.91（未校准）"
                默认["duration_source"] = "A_HELDOUT_train23"
        except Exception as e:
            _记账({"事件": "A_HELDOUT 系数读不到（用 V3 默认）", "为什么": repr(e)[:160]})
        _记账({"事件": "基线已读", "来源": 默认["来源"], "条数": len(行),
               "动作中位": 默认["动作中位"], "采集截距": 默认["采集截距"],
               "采集斜率": 默认["采集斜率"], "成功先验": 默认["采集成功先验"],
               "成功来源": 默认["成功来源"], "成功校准": 默认["成功校准"]})
    except Exception as e:
        _记账({"事件": "基线读不到（用内置默认）", "为什么": repr(e)[:200]})
    _基线 = 默认
    return _基线


def _预测任务(步骤):
    直方 = Counter(str((x or {}).get("动作") or "?") for x in (步骤 or []))
    步数 = len(步骤 or [])
    if 步数 == 0:
        return {"predicted_steps": 0, "predicted_steps_source": "plan_echo",
                "predicted_steps_current": 0,
                "predicted_steps_current_source": "plan_echo_current",
                "predicted_duration_sec": 0.0, "predicted_duration_source": "empty_plan",
                "predicted_duration_sum_steps": 0.0,
                "predicted_success": 0.0, "predicted_success_source": "empty_plan",
                "predicted_success_note": "没有步骤，不给成功先验",
                "predicted_failure_code": "empty_plan",
                "confidence": 0.0, "kind": "empty"}
    if any(a in 直方 for a in ("挖", "走到", "拾", "调")):
        种 = "collect"
        秒 = (_基线["采集截距"] + _基线["采集斜率"] * 步数) if _基线 else (0.443 + 1.591 * 步数)
        成功 = _基线.get("采集成功先验", 0.91) if _基线 else 0.91
        成功来源 = "prior_v3_0.91"
        成功注 = "未校准；A_HELDOUT test observed=0.800，Brier=0.184（n=10）；0.957 是 train23 先验，过自信，live 不采用"
        信 = 0.5
    else:
        种 = "craft"
        秒 = 0.35 * 步数
        成功 = _基线.get("手工成功先验", 1.0) if _基线 else 1.0
        成功来源 = "prior_v3_1.0"
        成功注 = "手工单 30/30 完；样本小，未校准"
        信 = 0.8
    中位 = ((_基线 or {}).get("动作中位") or {})
    总步秒 = sum(float(中位.get(a, 1.0)) * n for a, n in 直方.items())
    return {"predicted_steps": 步数, "predicted_steps_source": "plan_echo",
            "predicted_steps_current": 步数,
            "predicted_steps_current_source": "plan_echo_current",
            "predicted_duration_sec": round(秒, 2),
            "predicted_duration_sum_steps": round(总步秒, 2),
            "predicted_duration_source": ("linear_steps_" + str((_基线 or {}).get("duration_source", "v3"))
                                            if 种 == "collect" else "craft_per_step_v3"),
            "predicted_success": 成功, "predicted_success_source": 成功来源,
            "predicted_success_note": 成功注,
            "predicted_failure_code": None,
            "predicted_failure_code_source": "step_start_no_evidence",
            "confidence": 信, "kind": 种, "action_histogram": dict(直方)}


def _预测步(步, 任):
    动 = str((步 or {}).get("动作") or "?")
    中位 = float(((_基线 or {}).get("动作中位") or {}).get(动, 1.0))
    成功 = {"挖": 0.90, "走到": 0.95, "拾": 0.99, "给": 0.99,
            "合成": 0.99, "调": 0.95}.get(动, 0.95)
    return {"predicted_step_sec": 中位, "predicted_step_success": 成功,
            "predicted_failure_code": None,
            "predicted_failure_code_source": "step_start_no_evidence",
            "confidence": 0.5}


# ══════════════════════════ 二、只读取数 ══════════════════════════

def _活栈(bridge=None):
    桥 = bridge or _桥
    try:
        类 = getattr(桥, "任务栈", None)
        活 = list(getattr(类, "车钩活着的实例", []) or [])
        return 活[-1] if 活 else None
    except Exception:
        return None


def _状态帧():
    try:
        类 = getattr(_桥, "叙事者", None)
        活 = list(getattr(类, "车钩活着的实例", []) or [])
        if 活:
            s = getattr(活[-1], "最后状态", None)
            if isinstance(s, dict):
                return s
    except Exception:
        pass
    try:
        文件 = glob.glob(os.path.join(根, "logs", "全程-*.jsonl"))
        if 文件:
            p = max(文件, key=os.path.getmtime)
            with open(p, "rb") as f:
                大小 = os.path.getsize(p)
                f.seek(max(0, 大小 - 200000))
                行们 = f.read().decode("utf-8", "replace").splitlines()
            for ln in reversed(行们):
                try:
                    return json.loads(ln)
                except Exception:
                    continue
    except Exception:
        pass
    return {}


def _物品数(s, 名):
    try:
        return float(((s or {}).get("items") or {}).get(str(名), 0) or 0)
    except Exception:
        return 0.0


def _读箱子账():
    """只读任务栈的箱子账（logs/箱子账.json）：箱子侧总持有量的已知部分。"""
    try:
        with open(os.path.join(根, "logs", "箱子账.json"), encoding="utf-8") as f:
            原 = json.load(f)
        if isinstance(原, dict):
            return {str(k): float(v) for k, v in 原.items()
                    if isinstance(v, (int, float))}
    except Exception:
        pass
    return {}


def _回执增量():
    """从上次偏移读新回执，累计 goto/dig 噪声。只读文件。"""
    with _回执锁:
        _回执增量_体()


def _回执增量_体():
    global _回执偏移
    try:
        if not os.path.exists(回执路):
            return
        大小 = os.path.getsize(回执路)
        if 大小 < _回执偏移:
            _回执偏移 = 0
        if 大小 == _回执偏移:
            return
        with open(回执路, "rb") as f:
            f.seek(_回执偏移)
            数据 = f.read()
            _回执偏移 = f.tell()
        for ln in 数据.decode("utf-8", "replace").splitlines():
            try:
                o = json.loads(ln)
            except Exception:
                continue
            事 = o.get("事件")
            命 = o.get("命令")
            if 事 == "下发":
                if 命 == "goto":
                    _回执累计["goto_sent"] += 1
                elif 命 == "dig":
                    _回执累计["dig_sent"] += 1
            elif 事 == "回执":
                为 = str(o.get("为什么") or "")
                if 命 == "goto":
                    if "打断" in 为 or "Path was stopped" in 为:
                        _回执累计["goto_interrupted"] += 1
                    if "Took to long" in 为:
                        _回执累计["goto_path_timeout"] += 1
                elif 命 == "dig" and o.get("成不成") is False:
                    _回执累计["dig_failed"] += 1
    except Exception as e:
        _错("回执增量", e)


def _回执窗口(起, 止):
    """任务窗口内的回执统计；读文件尾 2 MB，够一个任务用。"""
    出 = {"goto_sent": 0, "dig_sent": 0, "goto_interrupted": 0,
          "goto_path_timeout": 0, "dig_failed": 0}
    try:
        if not os.path.exists(回执路):
            return 出
        with open(回执路, "rb") as f:
            大小 = os.path.getsize(回执路)
            f.seek(max(0, 大小 - 2000000))
            行们 = f.read().decode("utf-8", "replace").splitlines()
        for ln in 行们:
            try:
                o = json.loads(ln)
            except Exception:
                continue
            t = float(o.get("时刻") or 0)
            if t < 起 - 0.5 or t > 止 + 0.5:
                continue
            事 = o.get("事件")
            命 = o.get("命令")
            if 事 == "下发":
                if 命 == "goto":
                    出["goto_sent"] += 1
                elif 命 == "dig":
                    出["dig_sent"] += 1
            elif 事 == "回执":
                为 = str(o.get("为什么") or "")
                if 命 == "goto":
                    if "打断" in 为 or "Path was stopped" in 为:
                        出["goto_interrupted"] += 1
                    if "Took to long" in 为:
                        出["goto_path_timeout"] += 1
                elif 命 == "dig" and o.get("成不成") is False:
                    出["dig_failed"] += 1
    except Exception:
        pass
    return 出


def _物理体检(步骤, 状态):
    """调用物理体检的纯函数，只读；返回报告，不改任何步骤。"""
    try:
        m = sys.modules.get("车厢_物理体检_入口")
        if m is None or not callable(getattr(m, "体检", None)):
            m = None
            for x in list(sys.modules.values()):
                try:
                    if x and callable(getattr(x, "体检", None)) and "物理体检" in (getattr(x, "__file__", "") or ""):
                        m = x
                        break
                except Exception:
                    continue
        if m is None:
            return {"available": False, "为什么": "物理体检模块不在 sys.modules"}
        改, 报告 = m.体检(copy.deepcopy(步骤 or []), 状态 or {})
        return {"available": True, "条数": len(报告 or []),
                "报告": [str(x)[:300] for x in (报告 or [])][:40]}
    except Exception as e:
        return {"available": False, "为什么": repr(e)[:200]}


# ══════════════════════════ 三、记录 ══════════════════════════

def _计划签名(步):
    try:
        return json.dumps(步, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return repr(步)


def _观察计划(任, 来源):
    """只读观察：计划在任务开始后是否被改写。不改 任["步骤"]，不碰任务栈。"""
    if not isinstance(任, dict):
        return
    tid = 任.get("id") or "?"
    事件 = None
    with _记录锁:
        数据 = _任务.get(tid)
        if not 数据:
            return
        计划 = list(任.get("步骤") or [])
        旧计划 = list(数据.get("plan_current") or [])
        旧签 = [_计划签名(x) for x in 旧计划]
        新签 = [_计划签名(x) for x in 计划]
        if 旧签 == 新签:
            return
        旧总 = int(数据.get("plan_current_steps") or len(旧计划))
        新总 = len(计划)
        # 多重集 diff：重复的“挖两步”也要算成新增一步
        旧计 = Counter(旧签)
        新计 = Counter(新签)
        剩旧 = 旧计.copy()
        增加 = []
        for x, sig in zip(计划, 新签):
            if 剩旧.get(sig, 0) > 0:
                剩旧[sig] -= 1
            else:
                增加.append(x)
        剩新 = 新计.copy()
        减少 = []
        for x, sig in zip(旧计划, 旧签):
            if 剩新.get(sig, 0) > 0:
                剩新[sig] -= 1
            else:
                减少.append(x)
        增加动作 = [str((x or {}).get("动作") or "?") for x in 增加][:20]
        _名字 = str(任.get("名字") or "")
        if 新总 > 旧总 and (any(a in ("挖", "拾", "走到") for a in 增加动作)
                            or "log" in _名字 or "原木" in _名字):
            原因 = "collect_expand"
        elif 新总 < 旧总:
            原因 = "replan_shrink"
        else:
            原因 = "plan_revision"
        旧预测 = 数据.get("pred_after_revision") or 数据.get("pred") or {}
        旧秒 = float(旧预测.get("predicted_duration_sec") or 0)
        新预测 = _预测任务(计划)
        新秒 = float(新预测.get("predicted_duration_sec") or 0)
        数据["plan_current"] = 计划
        数据["plan_current_steps"] = 新总
        数据["plan_revision_count"] = int(数据.get("plan_revision_count") or 0) + 1
        数据["pred_after_revision"] = 新预测
        数据["predicted_duration_after_revision"] = 新秒
        事件 = {
            "事件": "计划修订", "task_id": tid,
            "step_idx": 任.get("第几步"), "old_total": 旧总, "new_total": 新总,
            "delta": 新总 - 旧总, "cause": 原因,
            "added_actions": 增加动作,
            "removed_actions": [str((x or {}).get("动作") or "?") for x in 减少][:20],
            "predicted_duration_before": round(旧秒, 2),
            "predicted_duration_after": round(新秒, 2),
            "predicted_steps_current": 新总,
            "predicted_steps_current_source": "plan_echo_current",
            "source": 来源,
        }
        事件们 = 数据.setdefault("plan_revision_events", [])
        事件们.append(事件)
        if len(事件们) > 50:
            del 事件们[:-50]
    if 事件:
        _记账(事件)


def _记录任务开始(任, s, 来源):
    if not isinstance(任, dict):
        return
    tid = 任.get("id") or "?"
    计划 = list(任.get("步骤") or [])
    预测 = _预测任务(计划)
    体检 = _物理体检(计划, s)
    _目标物品 = 任.get("目标物品")
    try:
        _目标数量 = float(任.get("目标数量")) if 任.get("目标数量") is not None else None
    except Exception:
        _目标数量 = None
    _背 = _物品数(s, _目标物品) if _目标物品 else 0.0
    _箱 = float(_读箱子账().get(str(_目标物品), 0) or 0) if _目标物品 else 0.0
    _有 = _背 + _箱
    with _记录锁:
        if tid in _任务:
            return
        _任务[tid] = {"start": time.time(), "plan": 计划, "pred": 预测,
                      "check": 体检, "done": set(), "failed": 0,
                      "name": 任.get("名字"), "start_pos": (s or {}).get("pos"),
                      "plan_initial_steps": len(计划),
                      "plan_current_steps": len(计划),
                      "plan_current": 计划,
                      "plan_revision_count": 0,
                      "plan_revision_events": [],
                      "pred_after_revision": 预测,
                      "predicted_duration_after_revision": 预测.get("predicted_duration_sec"),
                      "target_item": _目标物品, "requested_target": _目标数量,
                      "delivered_qty": 0.0,
                      "inventory_start": _背, "chest_start": _箱, "owned_start": _有}
    _回执累计.update({"goto_sent": 0, "dig_sent": 0, "goto_interrupted": 0,
                      "goto_path_timeout": 0, "dig_failed": 0})
    _记账({"事件": "任务开始", "task_id": tid, "task_name": 任.get("名字"),
           "start_pos": (s or {}).get("pos"), "steps": len(计划),
           "plan_action_histogram": dict(Counter(str((x or {}).get("动作") or "?") for x in 计划)),
           "predicted": 预测, "physical_check": 体检,
           "target_item": _目标物品, "requested_target": _目标数量,
           "inventory_qty": round(_背, 3), "chest_qty": round(_箱, 3),
           "owned_qty": round(_有, 3), "delivered_qty": 0.0,
           "order_satisfied": (bool(_有 + 1e-9 >= _目标数量) if _目标数量 is not None else None),
           "source": 来源})
    _记录步骤开始(任, 0, 来源, s)


def _记录步骤开始(任, idx, 来源, s=None):
    if not isinstance(任, dict):
        return
    _观察计划(任, "步骤开始")
    tid = 任.get("id") or "?"
    try:
        idx = int(idx)
    except Exception:
        idx = 0
    key = (tid, idx)
    with _记录锁:
        if key in _步:
            return
        计划 = 任.get("步骤") or []
        步 = 计划[idx] if 0 <= idx < len(计划) and isinstance(计划[idx], dict) else {}
        预测 = _预测步(步, 任)
        # ★ v0.1：每一步开始都重新体检（不是复用任务开始时那份）
        体检 = _物理体检(计划, s or {})
        检查 = [x for x in (体检.get("报告") or [])
                if ("第 %d 步" % (idx + 1)) in x or ("第 %d 步" % idx) in x]
        _步[key] = {"start": time.time(), "pred": 预测,
                    "action": 步.get("动作"), "target": 步.get("方块") or 步.get("物品"),
                    "p": 步.get("p"), "qty": 步.get("数量"),
                    "receipt_base": dict(_回执累计),
                    "last_receipt": {k: 0 for k in _回执累计},
                    "last_receipt_write": 0.0, "warned": False}
    _记账({"事件": "步骤开始", "task_id": tid, "step_idx": idx,
           "step_total": len(计划), "action": 步.get("动作"),
           "target": 步.get("方块") or 步.get("物品"), "p": 步.get("p"),
           "retry": 任.get("重试", 0), "predicted": 预测,
           "predicted_steps_current": len(计划),
           "predicted_steps_current_source": "plan_echo_current",
           "physical_check": {"source": "step_start",
                              "available": 体检.get("available"),
                              "pass": not 检查, "report": 检查,
                              "full_report_count": 体检.get("条数")},
           "source": 来源})


def _记录步骤完成(任, idx, 来源):
    if not isinstance(任, dict):
        return
    tid = 任.get("id") or "?"
    try:
        idx = int(idx)
    except Exception:
        idx = 0
    key = (tid, idx)
    with _记录锁:
        if key in _任务.get(tid, {}).get("done", set()):
            return
        if tid in _任务:
            _任务[tid]["done"].add(idx)
    _回执增量()
    数据 = _步.get(key)
    实际 = round(time.time() - 数据["start"], 2) if 数据 else 0.0
    预测 = (数据 or {}).get("pred") or {}
    基 = (数据 or {}).get("receipt_base") or {}
    步回 = {k: int(_回执累计.get(k, 0)) - int(基.get(k, 0)) for k in _回执累计}
    if (数据 or {}).get("action") == "给":
        try:
            _任务[tid]["delivered_qty"] = float(_任务[tid].get("delivered_qty") or 0) + float((数据 or {}).get("qty") or 0)
        except Exception:
            pass
    _记账({"事件": "步骤完成", "task_id": tid, "step_idx": idx,
           "action": (数据 or {}).get("action"),
           "target": (数据 or {}).get("target"),
           "actual": {"elapsed_sec": 实际},
           "predicted": 预测,
           "error": {"elapsed_sec": round(实际 - float(预测.get("predicted_step_sec") or 0), 2)},
           "step_receipt_stats": 步回,
           "delivered_qty": round(float((_任务.get(tid) or {}).get("delivered_qty") or 0), 3),
           "warning_fired": bool((数据 or {}).get("warned")),
           "warning_false_positive": bool((数据 or {}).get("warned")),
           "prediction_error_type": "step_time",
           "source": 来源})


def _记录步骤失败(任, idx, 原因, 来源):
    if not isinstance(任, dict):
        return
    tid = 任.get("id") or "?"
    try:
        idx = int(idx)
    except Exception:
        idx = 0
    次 = int(任.get("重试") or 0)
    key = (tid, idx, 次)
    with _记录锁:
        if key in _已失败:
            return
        _已失败.add(key)
    _回执增量()
    数据 = _步.get((tid, idx))
    实际 = round(time.time() - 数据["start"], 2) if 数据 else 0.0
    预测 = (数据 or {}).get("pred") or {}
    基 = (数据 or {}).get("receipt_base") or {}
    步回 = {k: int(_回执累计.get(k, 0)) - int(基.get(k, 0)) for k in _回执累计}
    if tid in _任务:
        _任务[tid]["failed"] = int(_任务[tid].get("failed") or 0) + 1
    _记账({"事件": "步骤失败", "task_id": tid, "step_idx": idx,
           "action": (数据 or {}).get("action"), "reason": str(原因)[:300],
           "attempt": 次, "actual": {"elapsed_sec": 实际},
           "predicted": 预测,
           "error": {"elapsed_sec": round(实际 - float(预测.get("predicted_step_sec") or 0), 2)},
           "step_receipt_stats": 步回,
           "delivered_qty": round(float((_任务.get(tid) or {}).get("delivered_qty") or 0), 3),
           "warning_fired": bool((数据 or {}).get("warned")),
           "warning_hit": bool((数据 or {}).get("warned")) and str(预测.get("predicted_failure_code")) == "pathfinder_interrupt_loop",
           "prediction_error_type": "step_failure",
           "source": 来源})


def _记录任务结束(任, 状态, 来源, preempted_by=None):
    if not isinstance(任, dict):
        return
    _观察计划(任, "任务结束")
    tid = 任.get("id") or "?"
    with _记录锁:
        if tid in _已结束:
            return
        _已结束.add(tid)
    数据 = _任务.get(tid) or {}
    事件步 = len(数据.get("done") or set())
    try:
        栈步 = int(任.get("第几步") or 0)
    except Exception:
        栈步 = 0
    if 栈步 <= 0 and (任.get("步骤") or []):
        栈步 = len(任.get("步骤") or [])
    实际步 = 栈步
    捕获差 = 栈步 - 事件步
    实际秒 = round(time.time() - float(数据.get("start") or time.time()), 2)
    成功 = (状态 == "完")
    if 成功:
        失败码 = None
    elif preempted_by:
        失败码 = "batch_policy_timeout_preempted"
    elif 状态 == "败":
        失败码 = str(任.get("failure_code") or "task_failed")
    elif 状态 == "中止":
        失败码 = "aborted"
    else:
        失败码 = str(状态 or "unknown")
    回执 = _回执窗口(float(数据.get("start") or time.time()), time.time())
    预测 = 数据.get("pred") or {}
    预测后 = 数据.get("pred_after_revision") or 预测
    开始秒 = float(预测.get("predicted_duration_sec") or 0)
    当前秒 = float(预测后.get("predicted_duration_sec") or 0)
    开始步 = int(预测.get("predicted_steps") or 0)
    当前步 = int(数据.get("plan_current_steps") or 开始步)
    _状态 = _状态帧()
    _目标物品 = 任.get("目标物品") or 数据.get("target_item")
    try:
        _目标数量 = float(任.get("目标数量")) if 任.get("目标数量") is not None else 数据.get("requested_target")
    except Exception:
        _目标数量 = 数据.get("requested_target")
    _背 = _物品数(_状态, _目标物品) if _目标物品 else 0.0
    _箱 = float(_读箱子账().get(str(_目标物品), 0) or 0) if _目标物品 else 0.0
    _有 = _背 + _箱
    _交付 = float(数据.get("delivered_qty") or 0)
    _满足 = (bool(_有 + 1e-9 >= float(_目标数量)) if _目标数量 is not None else None)
    _记账({"事件": "任务结束", "task_id": tid, "task_name": 任.get("名字"),
           "status": 状态, "actual": {"success": 成功, "steps": 实际步,
                                      "steps_from_task_stack": 栈步,
                                      "steps_from_events": 事件步,
                                      "capture_gap": 捕获差,
                                      "task_stack_step_index": 任.get("第几步"),
                                      "duration_sec": 实际秒,
                                      "failed_steps": 数据.get("failed", 0),
                                      "target_item": _目标物品,
                                      "requested_target": _目标数量,
                                      "inventory_qty": round(_背, 3),
                                      "chest_qty": round(_箱, 3),
                                      "owned_qty": round(_有, 3),
                                      "delivered_qty": round(_交付, 3),
                                      "order_satisfied": _满足},
           "predicted": 预测,
           "error": {"steps": 实际步 - 当前步,
                     "steps_at_start": 实际步 - 开始步,
                     "duration_sec": round(实际秒 - 开始秒, 2),
                     "duration_after_revision": round(实际秒 - 当前秒, 2),
                     "success": int(成功) - int(float(预测.get("predicted_success") or 0) >= 0.5)},
           "plan": {"initial_steps": 数据.get("plan_initial_steps"),
                    "final_steps": 数据.get("plan_current_steps"),
                    "revision_count": 数据.get("plan_revision_count", 0),
                    "revision_events": 数据.get("plan_revision_events", [])},
           "predicted_steps_initial": 数据.get("plan_initial_steps"),
           "predicted_steps_current": 数据.get("plan_current_steps"),
           "predicted_steps_current_source": "plan_echo_current",
           "predicted_duration_at_start": round(开始秒, 2),
           "predicted_duration_after_revision": round(当前秒, 2),
           "duration_error_at_start": round(实际秒 - 开始秒, 2),
           "duration_error_after_revision": round(实际秒 - 当前秒, 2),
           "duration_error_reduced_by_replanning": round(当前秒 - 开始秒, 2),
           "duration_error_reduced_is_causal": False,
           "duration_error_reduced_note": "这是旧计划预测与新计划重预测之差，不是计划修订实际耗时。",
           "predicted_after_revision": 预测后,
           "target_item": _目标物品, "requested_target": _目标数量,
           "inventory_qty": round(_背, 3), "chest_qty": round(_箱, 3),
           "owned_qty": round(_有, 3), "delivered_qty": round(_交付, 3),
           "order_satisfied": _满足,
           "failure_code": 失败码, "preempted_by": preempted_by,
           "prediction_error_type": ("preempted" if preempted_by else
                                      ("step_failure" if not 成功 else "step_time")),
           "prediction_error_types": {"steps": "plan_echo", "duration_sec": "step_time",
                                      "success": "prior", "failure_code": "prior_or_rule"},
           "receipt_stats": 回执,
           "receipt_since_mount": dict(_回执累计), "source": 来源})


# ══════════════════════════ 四、钩子（全部回调原函数 + 原样返回） ══════════════════════════

def _做接(原):
    def 新接(self, 名字, 步骤, s, **kw):
        旧 = getattr(self, "任务", None)
        旧id = 旧.get("id") if isinstance(旧, dict) else None
        结果 = 原(self, 名字, 步骤, s, **kw)
        try:
            新 = getattr(self, "任务", None)
            if 结果 and isinstance(新, dict):
                新id = 新.get("id")
                if 旧id and 旧id != 新id:
                    _记录任务结束(旧, "替换", "接单替换", preempted_by=新id)
                _记录任务开始(新, s, "接单")
        except Exception as e:
            _错("接", e)
        return 结果
    return 新接


def _做下一步(原):
    def 新下一步(self, s):
        旧 = getattr(self, "任务", None)
        旧id = 旧.get("id") if isinstance(旧, dict) else None
        旧idx = 旧.get("第几步") if isinstance(旧, dict) else None
        结果 = 原(self, s)
        try:
            任 = getattr(self, "任务", None)
            if isinstance(任, dict) and 任.get("id") == 旧id:
                状态 = 任.get("状态")
                _观察计划(任, "下一步")
                if 状态 in ("完", "败", "中止"):
                    _记录任务结束(任, 状态, "下一步")
                elif 任.get("第几步") != 旧idx and int(任.get("第几步") or 0) < len(任.get("步骤") or []):
                    _记录步骤开始(任, 任.get("第几步"), "下一步", s)
        except Exception as e:
            _错("下一步", e)
        return 结果
    return 新下一步


def _做失败(原):
    def 新失败(self, 步, 原因, s=None):
        任0 = getattr(self, "任务", None)
        idx0 = 任0.get("第几步") if isinstance(任0, dict) else 0
        结果 = 原(self, 步, 原因, s)
        try:
            任 = getattr(self, "任务", None)
            if isinstance(任, dict):
                if 任.get("状态") == "败":
                    _记录任务结束(任, "败", "失败")
                else:
                    _记录步骤失败(任, idx0, 原因, "失败")
        except Exception as e:
            _错("失败", e)
        return 结果
    return 新失败


def _做看(原):
    def 新看(self, 步, s, 任=None):
        任0 = 任 if isinstance(任, dict) else getattr(self, "任务", None)
        idx0 = 任0.get("第几步") if isinstance(任0, dict) else 0
        结果 = 原(self, 步, s, 任)
        try:
            if isinstance(结果, (tuple, list)) and 结果 and 结果[0]:
                _记录步骤完成(任0, idx0, "判定")
        except Exception as e:
            _错("判定", e)
        return 结果
    return 新看


def _做下发(原):
    def 新下发(self, 步, 任, 现在, s):
        结果 = 原(self, 步, 任, 现在, s)
        try:
            if 结果 and isinstance(任, dict):
                key = (任.get("id"), 任.get("第几步"))
                with _记录锁:
                    if key in _已下发:
                        key = None
                    else:
                        _已下发.add(key)
                if key is not None:
                    数据 = _步.get(key) or {}
                    _记账({"事件": "步骤下发", "task_id": 任.get("id"),
                           "step_idx": 任.get("第几步"), "action": 步.get("动作"),
                           "target": 步.get("方块") or 步.get("物品"),
                           "p": 步.get("p"), "predicted": 数据.get("pred") or {},
                           "source": "下发"})
        except Exception as e:
            _错("下发", e)
        return 结果
    return 新下发


# ══════════════════════════ 五、1 Hz 状态 + 兜底 ══════════════════════════

def _在跑(栈):
    try:
        任 = getattr(栈, "任务", None)
        return isinstance(任, dict) and 任.get("状态") in ("跑", "暂停")
    except Exception:
        return False


def _盯():
    global _上次状态
    while not _停.is_set():
        try:
            _回执增量()
            栈 = _活栈()
            任 = getattr(栈, "任务", None) if 栈 is not None else None
            s = _状态帧()
            if isinstance(任, dict):
                _记录任务开始(任, s, "轮询")
                状态 = 任.get("状态")
                _观察计划(任, "轮询")
                if 状态 in ("完", "败", "中止"):
                    _记录任务结束(任, 状态, "轮询")
                现在 = time.time()
                # ★ v0.1：step 内回执聚合 + pathfinder 预警（不是任务累计）
                if _在跑(栈):
                    try:
                        步骤号 = int(任.get("第几步") or 0)
                        键 = (任.get("id"), 步骤号)
                        数据 = _步.get(键)
                        if 数据:
                            基 = 数据.get("receipt_base") or {}
                            步回 = {k: int(_回执累计.get(k, 0)) - int(基.get(k, 0))
                                    for k in _回执累计}
                            if (步回 != 数据.get("last_receipt")
                                    and 现在 - float(数据.get("last_receipt_write") or 0) >= 0.5):
                                数据["last_receipt"] = 步回
                                数据["last_receipt_write"] = 现在
                                用时 = round(现在 - float(数据.get("start") or 现在), 1)
                                _记账({"事件": "步骤回执", "task_id": 任.get("id"),
                                       "step_idx": 步骤号, "action": 数据.get("action"),
                                       "step_receipt_stats": 步回, "elapsed_sec": 用时,
                                       "source": "0.5s"})
                                if int(步回.get("goto_interrupted", 0)) >= 3 and not 数据.get("warned"):
                                    数据["warned"] = True
                                    预测 = 数据.get("pred") or {}
                                    预测["predicted_failure_code"] = "pathfinder_interrupt_loop"
                                    预测["predicted_failure_code_source"] = "step_receipt_rule"
                                    数据["pred"] = 预测
                                    _记账({"事件": "步骤预警", "task_id": 任.get("id"),
                                           "step_idx": 步骤号, "action": 数据.get("action"),
                                           "predicted_failure_code": "pathfinder_interrupt_loop",
                                           "step_receipt_stats": 步回, "elapsed_sec": 用时,
                                           "confidence": 0.6, "source": "0.5s"})
                    except Exception as e:
                        _错("步骤回执", e)
                if _在跑(栈) and 现在 - _上次状态 >= 1.0:
                    _上次状态 = 现在
                    _记账({"事件": "状态", "task_id": 任.get("id"),
                           "task_name": 任.get("名字"), "status": 状态,
                           "step_idx": 任.get("第几步"),
                           "step_total": len(任.get("步骤") or []),
                           "retry": 任.get("重试"),
                           "pos": (s or {}).get("pos"), "hp": (s or {}).get("hp"),
                           "food": (s or {}).get("food"),
                           "items": (s or {}).get("items"),
                           "acting": (s or {}).get("acting"),
                           "block_changes": (((s or {}).get("scan") or {}).get("变了") or [])[:40],
                           "server_tick": ((s or {}).get("scan") or {}).get("t") or (s or {}).get("t"),
                           "source": "1Hz"})
            else:
                现在 = time.time()
                if 现在 - _上次状态 >= 5.0:
                    _上次状态 = 现在
                    _记账({"事件": "空闲", "pos": (s or {}).get("pos"),
                           "hp": (s or {}).get("hp"), "food": (s or {}).get("food"),
                           "items": (s or {}).get("items"), "source": "5s"})
        except Exception as e:
            _错("轮询", e)
        _停.wait(0.2 if _在跑(_活栈()) else 1.0)


# ══════════════════════════ 六、装上 / 卸下 ══════════════════════════

def 装上(bridge, 开关=True, 车钩=None, 日志=None, 数=None, 账本路径=None, **kw):
    global _桥, _日志, _已装, _账本, _线程, _回执偏移
    if not 开关:
        return {"好": False, "为什么": "开关关着", "打了": []}
    if _已装:
        return {"好": True, "为什么": "装过了（幂等）", "打了": []}
    栈类 = getattr(bridge, "任务栈", None)
    if 栈类 is None:
        return {"好": False, "为什么": "找不到 任务栈 类", "打了": []}
    if 账本路径:
        _账本 = str(账本路径)
    _桥, _日志 = bridge, 日志
    _读基线()
    _任务.clear(); _步.clear(); _已结束.clear(); _已下发.clear(); _已失败.clear()
    已打 = []
    try:
        for 名, 工厂 in (("接", _做接), ("_下一步", _做下一步), ("_失败", _做失败),
                         ("_看完成了没", _做看), ("_下发", _做下发)):
            原 = getattr(栈类, 名, None)
            if not callable(原):
                continue
            _原[名] = 原
            setattr(栈类, 名, 工厂(原))
            已打.append("任务栈." + 名)
    except Exception as e:
        for 名, 原 in list(_原.items()):
            try:
                setattr(栈类, 名, 原)
            except Exception:
                pass
        _原.clear()
        return {"好": False, "为什么": f"挂钩失败：{e!r}", "打了": 已打}
    _已装 = True
    _停.clear()
    try:
        _回执偏移 = os.path.getsize(回执路) if os.path.exists(回执路) else 0
    except Exception:
        _回执偏移 = 0
    _线程 = threading.Thread(target=_盯, daemon=True, name="自我模型观察")
    _线程.start()
    _记账({"事件": "装上", "打了": 已打, "账本": _账本,
           "基线": (_基线 or {}).get("来源")})
    _说("[自我模型] 只读上岗 ✓ 写 %s" % _账本)
    return {"好": True, "为什么": "", "打了": 已打}


def 卸下(bridge):
    global _已装, _线程
    if not _已装:
        return False
    _停.set()
    try:
        if _线程 is not None:
            _线程.join(timeout=2.0)
    except Exception:
        pass
    栈类 = getattr(bridge, "任务栈", None)
    for 名, 原 in list(_原.items()):
        try:
            setattr(栈类, 名, 原)
        except Exception:
            pass
    _原.clear()
    _已装 = False
    _记账({"事件": "卸下"})
    _说("[自我模型] 已卸下 ✓ 任务栈已还原")
    return True


def 同步实例(bridge, 日志=None, 车钩=None):
    """没有实例缓存要同步；只看活实例，不往回灌任何东西。"""
    return True
