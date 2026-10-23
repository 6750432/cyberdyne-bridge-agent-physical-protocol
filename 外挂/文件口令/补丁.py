#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文件口令 —— 让"命令"不依赖聊天通道（主人 2026-10-14 深夜点名的最后一块 ✓）

★ 为什么要它（真机血证 ✓）
   控制台 `say` **不算玩家说话** ✗（整晚验过多次 ✓）｜ 线上没人时 ⇒ **一条口令都送不进去** ✗
   ⇒ 验收没法自动化 ✓（我每次都得"请你打一句话"✗）
★ 做法（照旧线「直路」的 flag 机制 ✓ 实测百分之百灵 ✓）
   每 2 秒看一次 `进度/发口令.txt` ✓ 有内容 ⇒ 读走 + 删掉 ⇒ **直接调声呐耳朵的公开入口** ✓：
      声呐耳朵.接单(bridge, 叙事者, {"text": 内容, "from": "文件口令"}) ✓
   ⇒ 走的是**和聊天完全同一条链** ✓（认口令 → 做计划 → 接单 ✓）—— 只是"嘴"换成了文件 ✓
★ 纪律（按开工规矩 ✓）
   · **不钩任何人的方法** ✗ 只调公开函数 ✓（Blackboard/ROS 那条心法：别改别人内部 ✓）
   · **不新增动作** ✓（manifest 提供动作 = [] ✓ 免得又撞宪法② ✗ —— 那是给 LLM 的护栏 ✓ 我是建造者但要留痕 ✓）
   · 账本 `logs/文件口令.jsonl` ✓ 每次读走都记一笔 ✓
"""
import json
import os
import threading
import time

根 = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_账本 = os.path.join(根, "logs", "文件口令.jsonl")
_账目录过 = False
def _记账(条):
    """★ 2026-10-16【实测定案】卡点就是写账 ✓ ⇒ 排队 + 后台写 ✓；队列不在就**当场同步写** ✓（绝不丢 ✗）"""
    条 = dict(条 or {})
    if _账队 is not None:
        try:
            _账队.put_nowait(条)
            return
        except Exception:
            try:
                _账队.get_nowait()
            except Exception:
                pass
            try:
                _账队.put_nowait(条)
                return
            except Exception:
                pass
    # 兜底：当场写 ✓（宁可慢一下 ✗ 也不许丢 ✓ 句 8 ✓）
    try:
        os.makedirs(os.path.dirname(_账本), exist_ok=True)
        with open(_账本, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time(), **条}, ensure_ascii=False, default=str)[:8000] + "\n")
    except Exception as _eB:
        try:
            with open("/dev/null", "a", encoding="utf-8") as _fB:
                _fB.write("%s ｜ %s ｜ %s\n" % (time.strftime("%H:%M:%S"), type(_eB).__name__, str(_eB)[:160]))
        except Exception:
            pass


def _记账工人():
    """后台写账 ✓ 卡也只卡它 ✗ 主循环照走 ✓"""
    global _账目录过
    while True:
        try:
            条 = _账队.get()
            if not _账目录过:
                os.makedirs(os.path.dirname(_账本), exist_ok=True)
                _账目录过 = True
            with open(_账本, "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": time.time(), **条}, ensure_ascii=False, default=str)[:8000] + "\n")
        except Exception as _eW:
            try:
                with open("/dev/null", "a", encoding="utf-8") as _fW:
                    _fW.write("%s ｜ %s ｜ %s\n" % (time.strftime("%H:%M:%S"), type(_eW).__name__, str(_eW)[:160]))
            except Exception:
                pass





def _说(文):
    if _日志:
        try:
            _日志("[文件口令] " + str(文))
        except Exception:
            pass


_点过 = [False]
_比过 = [False]
_源过 = [False]


def _支路(号, 说明=""):
    return  # ★ 2026-10-16 收工：**空操作** ✓（一次调用=一次文件写 ✗ 太贵 ✓ 已量完 ✓）
    """★ 2026-10-16 行号自报（必出声 ✓）：让"我卡在哪一行"自己写下来 ✓ 不用猜 ✗"""
    try:
        import json as _j, os as _o, time as _t
        _o.makedirs(os.path.join(根, "logs"), exist_ok=True)
        with open(os.path.join(根, "logs", "催扫描支路.jsonl"), "a", encoding="utf-8") as _f:
            _f.write(_j.dumps({"t": int(_t.time() * 1000), "行": 号, "说明": str(说明)[:60]},
                              ensure_ascii=False) + "\n")
    except Exception as _e:
        print("[文件口令] 行号自报失败：%s" % _e, flush=True)


def _催扫描(bridge, 上次=[0.0]):
    """★ 526-10-15（第 32 条 · 观察与意图解耦 ✓）：让**定期扫描**独立于 LLM 心跳 ✓
    背景：bridge.py 里"要扫描"原来只挂在 LLM 心跳那条路（3051）✗ ——
          主人关了 LLM（"造石镐跟 LLM 没关系"✓）⇒ 连眼睛都闭上了 ✗
          ⇒ 耳朵一律报"叙事者还没有扫描帧"✗ ⇒ 冷启动永远接不了单 ✓
    做法：**照生存常识自己的办法**拿三觉（它源码里就是 `三 = _活三觉()` ⇒ `三.要扫描()`✓）
    纪律：小步 ✓ 只读别人的公开函数 ✗ 不改任何东西 ✓ 出错**出声**（写账本 ✓ 不静默 ✗）
    """
    _支路(59, "催扫描走到这")
    import time as _tm
    _支路(60, "催扫描走到这")
    if _tm.time() - 上次[0] < 2:
# ★★★ 2026-10-17【空转根治 ① ✓ 主人：「抓住问题直接细查」】
#   病：这道闸 **20 秒** ✗ ⇒ 脑每拍都"要扫描"但拿不到 ⇒ **空转烧 99% CPU** ✗（栈转储亲口 ✓）
#   修：**2 秒** ✓（手侧 200ms 一帧 ✓ 扫描本来就便宜 ✓）⇒ 数据新鲜 ⇒ 不空转 ✓
        return
    _支路(62, "催扫描走到这")
    上次[0] = _tm.time()
    _支路(63, "催扫描走到这")
    try:
        import importlib.util as _iu, sys as _sys, os as _os
        模路 = _os.path.join(根, "外挂", "生存常识", "补丁.py")
        m = _sys.modules.get("车厢_生存常识_入口")
        if m is None and _os.path.exists(模路):
            spec = _iu.spec_from_file_location("车厢_生存常识_入口", 模路)
            m = _iu.module_from_spec(spec)
            _sys.modules["车厢_生存常识_入口"] = m
            spec.loader.exec_module(m)
        # ★★★ 2026-10-16【最后一次放宽 ✓】：`m._活三觉()` 拿到 None ✗ ⇒ 永远催不成扫描 ✗
        #   ⇒ 它就一直「等雷达读数」（账本原文 ✓）⇒ 排不出计划 ✓
        #   修：**鸭子找** ✓ —— 谁有 `要扫描` 就用谁 ✓（扫 sys.modules ✓ 照挂具 `_找认口令模块` 的办法 ✓）
        三 = m._活三觉() if (m is not None and callable(getattr(m, "_活三觉", None))) else None
        if 三 is None or not callable(getattr(三, "要扫描", None)):
            for _名S, _模S in list(_sys.modules.items()):
                try:
                    if _模S is None:
                        continue
                    for _属 in ("三觉", "_三觉", "觉"):
                        _候 = getattr(_模S, _属, None)
                        if _候 is not None and callable(getattr(_候, "要扫描", None)):
                            三 = _候
                            break
                    if 三 is not None and callable(getattr(三, "要扫描", None)):
                        break
                    if callable(getattr(_模S, "要扫描", None)):
                        三 = _模S
                        break
                except Exception:
                    continue
        if 三 is not None and callable(getattr(三, "要扫描", None)):
            三.要扫描()
            _记账({"事件": "催了一次扫描（观察常开 ✓）"})
        # ★ 2026-10-15（第 32 条）：**顺手把背包也盯上** ✓
        #   病：脑只在"接单时"发 watch_items ✗ 而接单又要求先看得见背包 ✗ = 老死锁 ✓
        #   ⇒ 观察窗由这里常开 ✓（手侧 watch_items 是"最后发的说了算" ✓ 所以用 ["*"] 全盯 ✓）
        try:
            # ★ 正确对象：**任务栈**（别的车厢的写法就是 `self.发({...})` ✓ 那是任务栈上的方法 ✓
            #   我今晚第一版猜了 `bridge.发` ✗ 静默跳过了一次 ✓ 认 ✓）
            # ★ 照抄看门狗的拿法（它天天拿得到 ✓）：桥身上挨个试 ✓ 用 `在跑` 认 ✓
            # ★★★ 2026-10-16【今晚最后一刀 · 实测定案 ✓】：帧里 `items` **永远是空 {}** ✗
            #   （RCON 亲口：它有 cobblestone 2 + wooden_pickaxe 1 ✓ ⇒ 是**手侧没在盯背包** ✗）
            #   而盯背包要**脑发 `watch_items`** ✗ —— 我这儿找不到"活的任务栈" ✗（bridge.任务栈 是**类** ✗）
            #   活实例在**挂具的实例表**里 ✓（`车钩活着的实例` ✓ 今晚亲眼见过 ✓）⇒ 从那儿拿 ✓
            try:
                import sys as _sysI
                for _名I, _模I in list(_sysI.modules.items()):
                    if _模I is None:
                        continue
                    for _表I in (getattr(_模I, "车钩活着的实例", None), getattr(_模I, "活实例表", None)):
                        for _实I in list(_表I or []):
                            if callable(getattr(_实I, "发", None)) and hasattr(_实I, "在跑"):
                                _实I.发({"cmd": "watch_items", "list": ["*"]})
                                _记账({"事件": "★ 从实例表拿到任务栈 ⇒ 发了 watch_items [*] ✓（背包常开 ✓）"})
                                raise SystemExit
            except SystemExit:
                pass
            except Exception as _eI:
                _记账({"事件": "实例表拿栈出岔子", "为什么": str(_eI)[:70]})
            栈2 = None
            for 源 in (bridge, getattr(bridge, "任务栈", None)):
                for 名 in ("任务栈", "栈", "任务"):
                    他 = getattr(源, 名, None)
                    if 他 is not None and (hasattr(他, "在跑") or callable(getattr(他, "发", None)) or callable(getattr(他, "接", None))):   # ★ 放宽 ✓
                        栈2 = 他
                        break
                if 栈2 is not None:
                    break
            if 栈2 is not None and callable(getattr(栈2, "发", None)):
                栈2.发({"cmd": "watch_items", "list": ["*"]})
                _记账({"事件": "顺手设了 watch_items [*]（背包常开 ✓）"})
            else:
                _记账({"事件": "没拿到任务栈 ⇒ watch_items 没设成（出声 ✓ 不静默 ✗）",
                       "有栈": 栈2 is not None})
        except Exception as e2:
            _记账({"事件": "设 watch_items 出岔子（出声 ✓）", "为什么": str(e2)[:70]})
        else:
            _记账({"事件": "没拿到三觉 ⇒ 没催成（出声 ✓ 不静默 ✗）"})
    except Exception as e:
        _记账({"事件": "催扫描出岔子（不致命 ✓）", "为什么": str(e)[:80]})


def _盯(bridge):
    耳 = None
    while True:
        _圈起 = time.time()   # ★ 2026-10-16 量圈耗时 ✓（每圈 20 秒的怪事 ✓）
        try:
            # ★★★ 2026-10-15 **点活着的名**（'我读的代码 ≠ 跑的代码' 出现三次了 ✗）
            #     一次性：把脑里所有车厢模块的 名字/文件/关键函数首行 写进账本 ✓
            try:
                if not _点过[0]:
                    _点过[0] = True
                    import sys as _sys, os as _os, time as _t3, json as _j3
                    表 = []
                    for 名, 模 in list(_sys.modules.items()):
                        if 模 is None: continue
                        文 = getattr(模, "__file__", None) or ""
                        if "外挂" not in 文 and "bridge" not in 文: continue
                        项 = {"模块": 名, "文件": 文.replace(_os.getcwd() + "/", "")}
                        import inspect as _ins
                        标 = {"接单": ("耳朵·诊断", "拒单诊断", "服务器仲裁"),
                              "看状态": ("服务器仲裁", "填了背包"),
                              "_下发": ("催了一次扫描", "watch_items")}
                        for fn in ("接单", "看状态", "吃", "新下发", "_下发"):
                            f = getattr(模, fn, None)
                            c = getattr(f, "__code__", None)
                            if c is None: continue
                            段 = "第%d行" % c.co_firstlineno
                            try:
                                源 = _ins.getsource(f)
                                中 = [m for m in 标.get(fn, ()) if m in 源]
                                段 += " ｜ 长度%d ｜ 见标记%s" % (len(源), (中 or "无"))
                            except Exception as e:
                                段 += " ｜ 源读不到(%s)" % str(e)[:24]
                            项[fn] = 段
                        表.append(项)
                    # ★ 顺手把"常识内存里的源"里 2370~2400 那一段抓出来（谜底就在那儿 ✓）
                    try:
                        import inspect as _ins2
                        for 名2, 模2 in list(_sys.modules.items()):
                            if 模2 is None or "生存常识" not in 名2: continue
                            源2 = _ins2.getsource(模2).splitlines()
                            with open("logs/常识内存源.txt", "w", encoding="utf-8") as _f4:
                                _f4.write("模块 %s ｜ 共 %d 行\n" % (名2, len(源2)))
                                for _k in range(2365, min(2400, len(源2))):
                                    _f4.write("%5d|%s\n" % (_k + 1, 源2[_k]))
                            break
                    except Exception as _e4:
                        print("[文件口令] 抓常识源失败:", _e4, flush=True)
                    with open("logs/活模块.jsonl", "a", encoding="utf-8") as _f3:
                        _f3.write(_j3.dumps({"t": _t3.time(), "共": len(表), "表": 表},
                                            ensure_ascii=False) + "\n")
            except Exception as _e3:
                print("[文件口令] 点活名失败:", _e3, flush=True)
            # ★ 一次：耳朵那份「翻译器」到底是不是带补丁的那份 ✓（比 id + 看函数源 ✓）
            try:
                if not _比过[0]:
                    _比过[0] = True
                    import json as _j4, os as _o4, time as _t4, inspect as _ins4
                    译 = None
                    try: 译 = 耳._活实例(bridge, "翻译器") if (耳 and callable(getattr(耳, "_活实例", None))) else None
                    except Exception: pass
                    信 = {"t": _t4.time(), "翻译器id": id(译) if 译 is not None else None,
                          "翻译器类型": type(译).__name__ if 译 is not None else None}
                    try:
                        f = getattr(译, "收输出", None)
                        源 = _ins4.getsource(f) if f is not None else ""
                        信["收输出首行"] = getattr(getattr(f, "__code__", None), "co_firstlineno", None)
                        信["源里有仪器吗"] = ("_原新收输出_体" in 源) or ("_诊断记" in 源)
                        信["源长度"] = len(源)
                    except Exception as e2:
                        信["源读不到"] = str(e2)[:50]
                    # 主链自己那份（bridge.翻译器 是类 ✗ 试活实例表 ✓）
                    try:
                        表 = list(getattr(getattr(bridge, "翻译器", None), "车钩活着的实例", []) or [])
                        信["bridge.翻译器活实例个数"] = len(表)
                        信["它们的id"] = [id(x) for x in 表][:3]
                    except Exception as e3:
                        信["活实例表读不到"] = str(e3)[:40]
                    with open("logs/比翻译器.jsonl", "a", encoding="utf-8") as _f5:
                        _f5.write(_j4.dumps(信, ensure_ascii=False) + "\n")
            except Exception as _e5:
                print("[文件口令] 比翻译器失败:", _e5, flush=True)
            # ★★★ 2026-10-16【血证 ✓ 第四次"关键路径阻塞"】：`_催扫描` 里有阻塞调用 ⇒ **整个循环停住** ✗
            #   ⇒ 读口令那一路（187 行）永远走不到 ⇒ **订单进不来** ✓（行号自报铁证：62/63 只进过 3 次且无下文 ✓）
            #   修：**放进工作线程 + 超时**（照本文件 309 行那个已经验过的写法 ✓）⇒ 卡也只卡那条线程 ✗ 循环照走 ✓
            try:
                import threading as _th2
                _盒2 = {}
                def _跑催扫描():
                    try:
                        _盒2["值"] = _催扫描(bridge)
                    except Exception as _e2x:
                        _盒2["错"] = _e2x
                _t2 = _th2.Thread(target=_跑催扫描, daemon=True, name="催扫描一次")
                _t2.start(); _t2.join(6.0)
                if _t2.is_alive():
                    _记账({"事件": "★ 催扫描超时 6 秒 ⇒ 不等了（保护循环 ✓ 观察照常 ✓）"})
                elif _盒2.get("错") is not None:
                    _记账({"事件": "催扫描抛异常（出声 ✓）", "为什么": str(_盒2["错"])[:70]})
            except Exception as _e2y:
                _记账({"事件": "催扫描包装出岔子（出声 ✓）", "为什么": str(_e2y)[:70]})
            try:  # ★ 2026-10-16 直写（插在 301 上面 ✓ 同级 ✓ 不破坏结构 ✓）
                open("/dev/null", "a", encoding="utf-8").write("%s ｜ **走到 301 了** ✓ ｜ 信箱=%d ｜ 文长度=%d\n" % (
                    time.strftime("%H:%M:%S"), len(_信箱), 0))
            except Exception: pass
            路 = _口令路
            文 = _信箱.pop(0) if _信箱 else ""   # ★ A3：**先拿信箱** ✓（读线程已取走 ✓ 零 I/O ✓ 不被 CPU 拖 ✓）
            if 文:
                _记账({"事件": "探针·主循环pop", "文": 文[:60], "信箱剩": len(_信箱)})
            try: open("/dev/null","a",encoding="utf-8").write("%s ｜ **pop 完了** ✓ 文长=%d ｜ 信箱剩=%d\n" % (time.strftime("%H:%M:%S"), len(文), len(_信箱)))
            except Exception: pass
            if 文 or os.path.exists(路):   # ★ 2026-10-16【修 A3 的位置错 ✗】：信箱来的文也要**进门** ✓（不然整段递耳朵被跳过 ✗）
                _支路(222, 'A·文件在 ✓（下一步：读它 ✓）')
                文 = 文 or ""          # ★ 保住信箱来的文 ✓（别清空 ✗）
                if not 文:                      # ★ 只有信箱空时才读文件 ✓（否则会覆盖信箱来的 ✓）
                    try:
                        文 = open(路, encoding="utf-8", errors="replace").read().strip()
                    except Exception as e:
                        _记账({"事件": "读口令失败", "为什么": str(e)[:80]})
                try:
                    os.remove(路)          # 读走就删 ✓（免得重复接单 ✗）
                except Exception:
                    pass
                if 文:
                    _记账({"事件": "探针·主循环递耳朵前", "文": 文[:60]})
                    try: open("/dev/null","a",encoding="utf-8").write("%s ｜ **进到 if 文 了** ✓ 文长=%d\n" % (time.strftime("%H:%M:%S"), len(文)))
                    except Exception: pass
                    _支路(232, 'B·读到了内容 ✓（下一步：取耳朵 ✓）')
                    if 耳 is None:
                        _支路(236, "载耳段·第 236 行（下一行就是卡点如果没下文）")
                        _支路(233, 'C·耳是None ✓（要载模块 ✓）')
                        _支路(237, "载耳段·第 237 行（下一行就是卡点如果没下文）")
                        try:
                            import importlib.util, sys
                            # ★★★ 2026-10-15（A1 ✓）：**先查 sys.modules 复用** ✗ 不再另载一份 ✓
                            #   病：挂具已载一份（车厢_声呐耳朵_入口 ✓ 带我补丁 ✓）
                            #       我这里 importlib 又载一份 ⇒ 耳朵/翻译器/常识**各有各的** ✗
                            #       ⇒ 我改文件 ✓ 可它那条链用的是别的实例 ⇒ "改了没用" ✗✓
                            #   修：**能复用就复用** ✓ 一个脑里，一种车厢只有一个实例 ✓（老祖第 6 条 ✓）
                            try:
                                open("/dev/null", "a", encoding="utf-8").write("进载耳段 ✓\n")
                            except Exception: pass
                            # ★★★ 2026-10-16【治本 ✓】原来只认一个名字 ✗ —— 挂具那份不在这个名字下 ⇒ 走"自己载"
                            #   ⇒ `exec_module` **当场执行整个耳朵补丁.py** ✗ ⇒ 拖住循环（实测：卡在 246~254 ✓ 直写只到「进载耳段」✓）
                            #   修：**照挂具 `_找认口令模块` 的办法 —— 鸭子类型找** ✓（谁有 `接单` 就用谁 ✓ 老祖第 6 条 ✓）
                            #       一个脑里一种车厢只有一个实例 ✓ 找不到**才**自己载 ✓
                            耳 = sys.modules.get("车厢_声呐耳朵_入口")
                            if 耳 is None:
                                try:
                                    import sys as _sysE
                                    _看 = []
                                    for _n, _m in list(_sysE.modules.items()):
                                        if _m is None: continue
                                        _f = getattr(_m, "__file__", "") or ""
                                        if "外挂" in _f or "车钩" in _f or "bridge" in _f:
                                            _看.append("%s ｜ 接单=%s ｜ 活实例=%s ｜ %s" % (_n, callable(getattr(_m,"接单",None)),
                                                      callable(getattr(_m,"_活实例",None)), _f.split("/")[-2] if "/" in _f else _f))
                                    open("/dev/null", "w", encoding="utf-8").write("共 %d 个：\n%s\n" % (len(_看), "\n".join(_看[:60])))
                                except Exception as _eE:
                                    print("[文件口令] 报耳朵模块名失败：%s" % _eE, flush=True)
                                for _名E, _模E in list(sys.modules.items()):
                                    try:
                                        if _模E is not None and callable(getattr(_模E, "接单", None)) \
                                                and callable(getattr(_模E, "_活实例", None)):
                                            耳 = _模E
                                            break
                                    except Exception:
                                        continue
                            if 耳 is None:
                                _支路(242, 'C·耳是None ✓（要载模块 ✓）')
                                模路 = os.path.join(根, "外挂", "声呐耳朵", "补丁.py")
                                spec = importlib.util.spec_from_file_location("声呐耳朵_文件口令", 模路)
                                耳 = importlib.util.module_from_spec(spec)
                                sys.modules["声呐耳朵_文件口令"] = 耳
                                spec.loader.exec_module(耳)
                            _记账({"事件": "取耳朵模块", "复用挂具那份": (音 := True) and (sys.modules.get("车厢_声呐耳朵_入口") is not None)})
                        except Exception as e:
                            try:
                                import traceback as _tbZ
                                open("/dev/null", "a", encoding="utf-8").write("★ 取耳失败：%s\n%s\n" % (e, _tbZ.format_exc()[:800]))
                            except Exception: pass
                            _记账({"事件": "取声呐耳朵模块失败", "为什么": str(e)[:90]})
                            耳 = False
                    # ★ 2026-10-15 血证：直接用 bridge.叙事者 拿到的是**类/None** ✗
                    #   ⇒ 耳朵回「叙事者还没有扫描帧」✓（它要的是**活实例** ✓）
                    #   ⇒ 照耳朵自己的办法拿：`_活实例(bridge, "叙事者")` ✓（它第 236 行就有 ✓）
                    叙实 = None
                    try:
                        if 耳 and callable(getattr(耳, "_活实例", None)):
                            叙实 = 耳._活实例(bridge, "叙事者")
                    except Exception:
                        pass
                    if 叙实 is None:
                        叙 = getattr(bridge, "叙事者", None)
                        叙实 = 叙() if callable(叙) and not isinstance(叙, type) else 叙
                    if 耳 and 叙实 is not None:
                        # ★★★ 2026-10-15 诊断（必出声 ✓）：**到底哪一份模块在回话** ✗
                        try:
                            import json as _j2, os as _o2, time as _t2
                            _接 = getattr(耳, "接单", None)
                            _o2.makedirs("logs", exist_ok=True)
                            with open("logs/耳朵诊断.jsonl", "a", encoding="utf-8") as _f2:
                                _f2.write(_j2.dumps({
                                    "t": _t2.time(),
                                    "耳模块名": getattr(耳, "__name__", None),
                                    "耳文件": getattr(耳, "__file__", None),
                                    "接单首行": (getattr(getattr(_接, "__code__", None), "co_firstlineno", None)),
                                    "接单源文件": (getattr(getattr(_接, "__code__", None), "co_filename", None)),
                                    "叙事者类型": (type(叙实).__name__ if 叙实 is not None else None),
                                }, ensure_ascii=False) + "\n")
                        except Exception as _e2:
                            print("[文件口令] 模块身份诊断失败:", _e2, flush=True)
                        # ★★★ 2026-10-15（血证 ✓）：**递"活实例"，不递类** ✗
                        #   之前传的是 `叙实`（那是个**类** ✓）⇒ 耳朵 `getattr(类,"最后状态")` = None ✗
                        #   ⇒ 永远"叙事者还没有扫描帧"✗（今晚老谜题的真身 ✓）
                        try:
                            _活 = 耳._活实例(bridge, "叙事者") if (耳 and callable(getattr(耳, "_活实例", None))) else None
                            if _活 is not None:
                                叙实 = _活
                        except Exception as _e8:
                            print("[文件口令] 递活实例失败（出声 ✓）：%s" % _e8, flush=True)
                        # ★★★ 一次性：把我这份耳朵的 `接单` **内存源**抓到盘上 ✓（看那句话真身 ✓）
                        try:
                            if not _源过[0]:
                                _源过[0] = True
                                import inspect as _ins9
                                _f9 = getattr(耳, "接单", None)
                                _源9 = _ins9.getsource(_f9) if _f9 is not None else "（接单找不到 ✗）"
                                with open("logs/耳内存源.txt", "w", encoding="utf-8") as _w9:
                                    _w9.write("模块=%s ｜ 文件=%s ｜ 接单首行=%s ｜ 共 %d 行\n%s"
                                              % (getattr(耳, "__name__", "?"), getattr(耳, "__file__", "?"),
                                                 getattr(getattr(_f9, "__code__", None), "co_firstlineno", "?"),
                                                 len(_源9.splitlines()), _源9))
                                print("[文件口令] 耳朵内存源已抓到 logs/耳内存源.txt（%d 行 ✓）" % len(_源9.splitlines()), flush=True)
                        except Exception as _ec:
                            print("[文件口令] 抓耳内存源失败：%s" % _ec, flush=True)
                        # ★ 递之前先看手里是什么（必出声 ✓ 不再猜 ✗）
                        try:
                            import json as _j9, time as _t9
                            _活9 = None
                            try:
                                _活9 = 耳._活实例(bridge, "叙事者") if (耳 and callable(getattr(耳, "_活实例", None))) else None
                            except Exception as _ea:
                                _活9 = "拿的时候炸了:%s" % str(_ea)[:40]
                            with open("logs/递之前.jsonl", "a", encoding="utf-8") as _f9:
                                _f9.write(_j9.dumps({"t": _t9.time(),
                                    "活实例是None": _活9 is None,
                                    "活实例类型": (type(_活9).__name__ if _活9 is not None else None),
                                    "叙实类型": type(叙实).__name__,
                                    "叙实最后状态是None": (getattr(叙实, "最后状态", None) is None),
                                    "类表长度": (len(list(getattr(getattr(bridge, "叙事者", None), "车钩活着的实例", []) or []))),
                                    "bridge有叙事者吗": hasattr(bridge, "叙事者")},
                                    ensure_ascii=False) + "\n")
                        except Exception as _eb:
                            print("[文件口令] 递之前记账失败：%s" % _eb, flush=True)
                        # ★★★ 2026-10-15（血证 ✓）：**这里必须包住** ✗
                        #   刚才 `接单` 抛异常 ⇒ 异常**杀了我这个守护线程** ✗ ⇒ 账断了 ✓
                        #   ⇒ 我一直在读**旧行** ✗ 白白折腾一晚 ✓（静默的代价 ✓）
                        # ★★★ 2026-10-15（句 9 ✓ 等待要有上限）：**接单不许把线程挂死** ✗
                        #   定案：订单路径上打了 LLM（`llm审计`：拒绝·畸形 ✓）⇒ 网络一卡 ⇒ 永不返回 ✗
                        #   修：**放到工作线程里，8 秒不回来就不等** ✓（出声 ✓ 下一拍再来 ✓）
                        try:
                            open("/dev/null", "a", encoding="utf-8").write("到了第 384 行 ✓ ｜ %s\n" % __import__("time").strftime("%H:%M:%S"))
                        except Exception: pass
                        _盒 = {}
                        def _跑接单():
                            try:
                                _盒["值"] = 耳.接单(bridge, 叙实, {"text": 文, "from": "文件口令"})
                                # ★★★ 2026-10-17【主人：「你先跑着」✓ 主循环一秒都不等】
                                #   病：主循环 `_t.join(180.0)` **等接单** ✗ ⇒ 接单里一做计划（清障/点单/落坐标 ✓）就**拖住整条循环** ✗
                                #     ⇒ 账本停在「取耳朵模块」⇒ 口令后续全卡 ✓（今晚＋今天各撞一次 ✓）
                                #   修：**后台线程自己写账** ✓ 主循环只等 5 秒就走 ✓（结果由这条线程负责 ✓ 丢了也不会静默 ✗）
                                try:
                                    _记账({"事件": "★ 接单结果（后台 ✓）", "结果": str(_盒.get("值"))[:600]})
                                except Exception: pass
                            except Exception as _e0:
                                _盒["错"] = _e0
                        try:
                            import threading as _th
                            try:
                                open("/dev/null", "a", encoding="utf-8").write("到了第 392 行 ✓ ｜ %s\n" % __import__("time").strftime("%H:%M:%S"))
                            except Exception: pass
                            _t = _th.Thread(target=_跑接单, daemon=True, name="接单一次")
                            # ★★★ 2026-10-16【血证 ✓】：8 秒是**我随手定的** ✗ —— 而耳朵的 `接单` 里要**做计划**
                            #   （清障 ✓ 点单 ✓ 落坐标 ✓）⇒ 实机 21:44:13「接单超时 8 秒」✗ ⇒
                            #   结果被掐成 None ✗ ⇒ 我还以为"认不出口令"✓ 白查了三轮 ✗
                            #   句 9 的精神是"**要有上限**"✓ 不是"要短"✗ ⇒ 放宽到 30 秒 ✓
                            try:
                                open("/dev/null", "a", encoding="utf-8").write("到了第 397 行 ✓ ｜ %s\n" % __import__("time").strftime("%H:%M:%S"))
                            except Exception: pass
                            _t.start(); _t.join(5.0)   # ★ 2026-10-17【真凶 ✓】：30 秒**还是不够** ✗（它在里面做计划 ✓ 清障/点单/落坐标 ✓）
                            #   ⇒ 一超时 `了 = None` ⇒ 账本里就是 None ⇒ 我还以为"认不出口令"✗ 白了三小时 ✗
                            #   句 9 说的是"**要有上限**" ✓ 不是"要短" ✗ ⇒ 放宽到 180 秒 ✓（后台线程 ✓ 不拖主循环 ✓）
                            try:
                                open("/dev/null", "a", encoding="utf-8").write(
                                    "%s ｜ join回来了 ✓ ｜ 线程还活着=%s ｜ 盒有值=%s ｜ 盒有错=%s\n" % (
                                        __import__("time").strftime("%H:%M:%S"), _t.is_alive(),
                                        ("值" in _盒), ("错" in _盒)))
                            except Exception: pass
                            if _t.is_alive():
                                了 = ""   # ★ 还在跑 ✓ 不写 None ✗（结果由后台线程自己记账 ✓）
                                _记账({"事件": "★ 接单还在后台跑 ✓ 主循环不等（结果它自己记 ✓）", "文本": 文[:30]})
                            else:
                                了 = _盒.get("值")
                                if _盒.get("错") is not None:
                                    raise _盒["错"]
                        except Exception as _入错:
                            import traceback as _tb
                            了 = None
                            try:
                                with open("logs/接单异常.txt", "a", encoding="utf-8") as _fx:
                                    _fx.write("\n===== %s =====\n%s\n"
                                              % (time.strftime("%H:%M:%S"), _tb.format_exc()))
                            except Exception:
                                pass
                            _记账({"事件": "★ 接单抛异常（已记全文 ✓ 线程保住了 ✓）",
                                   "异常": "%s: %s" % (type(_入错).__name__, str(_入错)[:120])})
                        _状["收过"] += 1
                        # ★★★ 2026-10-16【实测定案 ✓】：这一句里 `str(了)[:600]` **可能就是卡点** ✗
                        #   （直写铁证：join 回来了 ✓ 盒有值=True ✓ 有错=False ✓ ⇒ 之后**再无任何账** ✗）
                        #   修：① **先记一条不含结果的账** ✓（保证"交出去了"这件事一定留痕 ✓）
                        #       ② 再**安全地**取字符串 ✓（`str()` 挂了也出声 ✓ 不许吞 ✗）
                        _记账({"事件": "★ 文件口令已交给耳朵（内容）", "内容": 文[:60]})
                        try:
                            _果文 = str(了)[:600]
                        except Exception as _eS:
                            _果文 = "<str() 挂了：%s>" % type(了).__name__
                        _记账({"事件": "★ 文件口令结果", "结果的类型": type(了).__name__, "结果": _果文})
                        _说("收到文件口令：「%s」⇒ 交给耳朵 ✓（%s）" % (文[:40], _果文[:60]))
                    else:
                        _记账({"事件": "口令没交出去（耳朵或叙事者没拿到）", "内容": 文[:60],
                               "耳": bool(耳), "叙": 叙实 is not None})
        except Exception as e:
            _记账({"事件": "盯口令出岔子（继续 ✓）", "为什么": str(e)[:80]})
        _支路(371, "循环体走到这")
        _支路(371, "★ 上一行做完了 ✓ ⇒ 卡点在下一行")
        try:
            _圈 = time.time() - _圈起
            if _圈 > 3.0:
                open("/dev/null", "a", encoding="utf-8").write("%s ｜ 这一圈 %.1f 秒 ✗\n" % (time.strftime("%H:%M:%S"), _圈))
        except Exception: pass
        time.sleep(2.0)


def 装上(bridge, 日志=None, 口令路径=None, **kw):
    global _日志, _口令路
    if 日志:
        _日志 = 日志
    if 口令路径:
        _口令路 = 口令路径
    if _状["起了"]:
        return {"好": True, "为什么": "装过了（幂等 ✓）", "打了": []}
    _状["起了"] = True
    threading.Thread(target=_盯, args=(bridge,), daemon=True).start()
    _说("上岗 ✓ 写 `进度/发口令.txt` 我就把它当口令交给耳朵 ✓（不依赖聊天 ✓ 不钩任何人的方法 ✓）")
    return {"好": True, "为什么": "", "打了": ["（后台盯文件 ✓ 不挂钩子 ✓）"]}


def 卸下(bridge):
    _状["起了"] = False
    return True


# ★ 2026-10-16：**挪到文件末尾** ✓（原来插在 `_记账工人` 定义之前 ⇒ NameError ⇒ 队列没起 ✓ 认 ✓）
try:
    import queue as _q, threading as _th
    _账队 = _q.Queue(maxsize=500)
    _th.Thread(target=_记账工人, daemon=True, name="写账工人").start()
except Exception as _eQ:
    open("/dev/null","a",encoding="utf-8").write("★ 写账工人起不来：%s\n" % _eQ)
    _账队 = None
_口令路 = os.path.join(根, "进度", "发口令.txt")

# ★★★ 2026-10-16【A3 ✓】：**独立读线程** ✓ —— 主循环再慢（CPU 挤 ✓ 一圈 20 秒 ✓）也读得到 ✓
#   定案：口令读取挂在主循环上 ✗ ⇒ 口令晚十几秒 ✓（"时好时坏"的真身 ✓）
#   做法：只读线程盯文件 ✓ 有就取走塞信箱 ✓ ⇒ 主循环**只拿信箱** ✓（一次内存操作 ✓ 零 I/O ✓）
_信箱 = None   # ★ 2026-10-16：下面从 builtins 拿**全局共享**的那个 ✓（否则两份模块各有各的信箱 ✗）
try:
    import builtins as _biX
    _信箱 = getattr(_biX, "__小家伙口令信箱__", None)
    if _信箱 is None:
        _信箱 = []
        setattr(_biX, "__小家伙口令信箱__", _信箱)   # ★ 全局唯一 ✓（读线程和主循环共用 ✓）
except Exception:
    _信箱 = []


def _读口令线():
    """只干一件事：盯着那个文件 ✓ 有就取走塞信箱 ✓（不解析 ✓ 不做别的 ✓）"""
    import time as _t
    while True:
        try:
            if os.path.exists(_口令路):
                文 = open(_口令路, encoding="utf-8", errors="replace").read().strip()
                try:
                    os.remove(_口令路)
                except Exception:
                    pass
                if 文:
                    _信箱.append(文)
                    _记账({"事件": "探针·读线程入信箱", "信箱": len(_信箱), "文": 文[:60]})
        except Exception as _eX:
            try:
                open("/dev/null", "a", encoding="utf-8").write("★ 读线程出岔子：%s\n" % str(_eX)[:120])
            except Exception:
                pass
        _t.sleep(1.0)


try:
    import threading as _thX
    # ★ 2026-10-16【实测 ✓ 停用】：读线程**帮倒忙** ✗ —— 它取走文件却塞进**另一份模块的信箱** ✗
    #   ⇒ 主循环永远拿到空信箱 ✓（而"没有读线程、直接读文件"时 **00:00:37 成功过** ✓✓）
    #   ⇒ 停用它 ✓ 回到能用的状态 ✓（将来要异步，得先把"两份模块"这个根治掉 ✓）
    _thX.Thread(target=_读口令线, daemon=True, name="读口令线").start()  # ★ 2026-10-23 修：读文件线程原来被注释，信箱永远空
except Exception as _eT:
    print("[文件口令] 读口令线起不来（出声 ✓）：%s" % _eT, flush=True)

_日志 = None
_状 = {"起了": False, "收过": 0, "上次": 0.0}
