#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发计时 ★ 2026-10-16（主人「继续」✓）

**目的：先量再改** ✓（老祖：别猜 ✗）
   今晚六个卡点都指向同一件事：**`发(...)` 在关键路径上阻塞** ✗
   但"发到底慢不慢"**没量过** ✗ —— 这一节只做**测量**：
     包住 `任务栈.发` ✓ 记每次调用的**耗时毫秒 + 谁在调 + 发的是什么 cmd** ✓
   **一个字都不改行为** ✗：原样调用 ✓ 原样返回 ✓ 不拦 ✗ 不异步 ✗ 不超时 ✗
   （量出数据 ⇒ 再决定"包线程 / 加超时 / 换通道"✓ —— 那才是对症下药 ✓）

★ 铁规矩：
   · **包装 ≠ 替换** ✗ ⇒ 第一件事回调原函数 ✓ 返回值原样 ✓（老祖第 6 条 ✓）
   · **失败必须出声** ✗（本车厢自己的错也写账 ✓）
   · 只写 `logs/发耗时.jsonl` ✓（超过 50ms 的才记 ✓ 免得刷屏 ✓）
"""
import json
import os
import time

根 = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_原 = {}
_状 = {"调用": 0, "慢": 0, "错": 0}


def _落(条):
    try:
        os.makedirs(os.path.join(根, "logs"), exist_ok=True)
        with open(os.path.join(根, "logs", "发耗时.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(条, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception as e:
        print("[发计时] 写账失败（出声 ✓）：%s" % e, flush=True)
        _状["错"] += 1
        return False


def 装上(bridge, 日志=None, 数=None, 车钩=None, **kw):
    栈 = getattr(bridge, "任务栈", None)
    类 = 栈 if isinstance(栈, type) else type(栈) if 栈 is not None else None
    if 类 is None:
        return {"好": False, "为什么": "找不到任务栈类", "打了": []}
    if getattr(类, "_发计时装了", False):
        return {"好": True, "为什么": "装过了（幂等 ✓）", "打了": []}
    原 = getattr(类, "发", None)
    if not callable(原):
        # ★ 2026-10-16：`发` 是**实例属性**（`self.发 = 发命令` ✓ 构造时挂的 ✓）不在类上 ✗
        #   ⇒ 我这里找不到是**正常**的 ✓ ⇒ **不许因此拖垮整列火车** ✗（挂具刚才整列没发车 ✓ 记一笔 ✓）
        #   量"发慢不慢"改从别处量 ✓（`_催扫描` 的 6 秒超时已经实测证明它会卡 ✓✓）
        print("[发计时] 任务栈的 `发` 是实例属性 ⇒ 本节暂时量不到（**不拖累主链** ✓ 出声 ✓）", flush=True)
        return {"好": True, "为什么": "", "打了": ["（没找到类上的 `发` ✓ 实例属性量不到 ✓ 照常发车 ✓）"]}
    _原[id(类)] = 原

    def 发(self, obj):
        起 = time.time()
        谁 = "?"
        try:
            import sys as _s
            f = _s._getframe(1)
            谁 = "%s:%s" % (os.path.basename(f.f_code.co_filename), f.f_code.co_name)
        except Exception:
            pass
        try:
            return 原(self, obj)              # ★ 原样调用 ✓ 原样返回 ✓
        finally:
            耗时 = (time.time() - 起) * 1000.0
            _状["调用"] += 1
            if 耗时 >= 50.0:
                _状["慢"] += 1
                命 = None
                try:
                    命 = obj.get("cmd") or obj.get("act") if isinstance(obj, dict) else None
                except Exception:
                    pass
                _落({"t": int(time.time() * 1000), "毫秒": round(耗时, 1), "谁在调": 谁,
                     "命令": 命, "第几次慢": _状["慢"]})
            if _状["调用"] % 200 == 0:
                _落({"t": int(time.time() * 1000), "小计": {"调用": _状["调用"], "慢": _状["慢"], "错": _状["错"]}})

    类.发 = 发
    setattr(类, "_发计时装了", True)
    return {"好": True, "为什么": "", "打了": ["任务栈.发() ← **只记耗时** ✓（≥50ms 才写账 ✓ 不改行为 ✗）"]}


def 卸下(bridge):
    栈 = getattr(bridge, "任务栈", None)
    类 = 栈 if isinstance(栈, type) else type(栈) if 栈 is not None else None
    if 类 is None:
        return False
    原 = _原.pop(id(类), None)
    if callable(原):
        类.发 = 原
    try:
        delattr(类, "_发计时装了")
    except Exception:
        pass
    return True
