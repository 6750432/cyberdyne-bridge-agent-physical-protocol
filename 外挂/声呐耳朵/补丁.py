#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""声呐耳朵车厢 —— 听见主人说话，当场认口令、当场接单，不等心跳。

主人 2026-10-08 晚 的原话
======================
「反应过来就应该立刻动身啊，那怎么我找他帮忙还以为他在思考呢？」

他说得对。手侧其实很及时 —— 日志里 `[21:59] 听见 mintstar 说：…` 一收到就报过来 ✓
慢的是**脑**：它要等下一次**心跳**才轮到这个活 ✗
中间那几秒它就站着，看上去像在发呆（主人：「他明明是站在我对面没怎么动的」）。

这节车厢照 **声呐外挂** 那套结构（手侧探针 + 核心 + 连耦）做一只「耳朵」，
只不过它挂在**脑侧**的事件口上：

    叙事者.看事件(e)   ← 聊天从这儿进来
        ↓  kind == "chat"
    ① 把这句原话记进「上次原话」（生存常识的 认口令 靠它，拼音也认 ✓）
    ② 拿 self.最后状态（叙事者每拍都存着当前扫描帧 ✓）
    ③ 立刻走一遍翻译器的 收输出()（= 立刻做计划，**不等心跳**）
    ④ 当场 任务栈.接(名字, 步骤, s)（接单入口自带"没登记的动作就拒单"的锁 ✓）

从「听见」到「迈腿」就是同一秒 ✓

规矩
====
· **原来那条路一个字不改** —— 包装函数先把原件跑完，再走耳朵 ✓
· **耳朵听不清不许把脑弄哑** —— 任何异常都吞在耳朵里（但会报出来 ✓ 不静默 ✗）
· 找不到元件（翻译器/任务栈/认口令）就**什么都不做**，并说清为什么 ✓
"""

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_日志 = None
_原件 = {}

# ── 「叮」那一路（2026-10-09 主人点名：盲挖中听见「叮」→ 立刻插队去挖）──
#   岩浆音：冒泡那声「叮」是 `block.lava.pop` ✓ 另外两条一起认着（同源信号 ✓）
岩浆音 = ("block.lava.pop", "block.lava.ambient", "block.lava.extinguish")
#   1.21 的钻石层：y=-64 ~ 16，最密在 y=-59 ~ -53 ✓（wiki + 官方改动日志）
#   岩浆湖一律生成在 y≤10 ✓ → y 比 16 高就没必要为一个提示往下钻 ✓
钻石层 = (-64, 16)
_追叮上次 = {}          # 声源坐标 -> 上次追的时刻（去重用）
_追叮几次 = 0
_桥 = None              # 装上的时候存一份（追「叮」要它去摸任务栈 ✓）


def _说(文):
    if _日志:
        try:
            _日志(文)
            return
        except Exception:
            pass
    print(文, flush=True)


def _找认口令模块():
    """鸭子类型地找「生存常识」那节车厢（它提供 认口令 / _上次原话）。

    ⚠ 不按模块名找 —— 车厢是被 importlib 用别的名字载进来的 ✗
      按**有没有那个函数**找，谁有就用谁（找不到就返回 None，什么都不做）✓
    """
    for m in list(sys.modules.values()):
        try:
            if callable(getattr(m, "认口令", None)) and hasattr(m, "_上次原话"):
                # ★ 2026-10-16 探针（必出声 ✓）：报出"我抓的是哪一份常识" ✓ —— 一眼看穿"两份模块" ✓
                try:
                    import json as _jM, os as _oM, time as _tM
                    _oM.makedirs(os.path.join(根, "logs"), exist_ok=True)
                    with open(os.path.join(根, "logs", "找认口令探针.jsonl"), "a", encoding="utf-8") as _fM:
                        _fM.write(_jM.dumps({"t": int(_tM.time() * 1000),
                            "抓到模块名": getattr(m, "__name__", None),
                            "抓到文件": getattr(m, "__file__", None),
                            "它的原话": str(getattr(m, "_上次原话", {}).get("原话") or "")[:30],
                            "它有探针吗": hasattr(m, "_认口令有探针")}, ensure_ascii=False) + "\n")
                except Exception as _eM:
                    print("[耳朵] 找认口令探针失败：%s" % _eM, flush=True)
                return m
        except Exception:
            continue
    # ★ 2026-10-16 探针（必出声 ✓）：报出"我抓的是哪一份常识" ✓ 一眼看穿"两份模块" ✓
    try:
        import json as _jM, os as _oM, time as _tM
        _oM.makedirs(os.path.join(根, "logs"), exist_ok=True)
        with open(os.path.join(根, "logs", "找认口令探针.jsonl"), "a", encoding="utf-8") as _fM:
            _fM.write(_jM.dumps({"t": int(_tM.time() * 1000),
                "结果名": getattr(None, "__name__", None) if "None" in dir() else None,
                "结果文件": getattr(None, "__file__", None) if "None" in dir() else None,
                "结果有认口令": callable(getattr(None, "认口令", None)) if "None" in dir() else None,
                "结果原话": str(getattr(None, "_上次原话", {}).get("原话") or "")[:30] if "None" in dir() else None},
                ensure_ascii=False) + "\n")
    except Exception as _eM:
        print("[耳朵] 找认口令探针失败：%s" % _eM, flush=True)
    return None


def 听动静(叙事者, e, 桥=None):
    """手侧声呐报上来的"动静"（音效）—— 落在 logs/声呐.jsonl，要命的当场喊出来。

    ★ 跟"耳朵"是两件事：耳朵听**字**（聊天口令），这里听**动静**（音效事件）✓
      主人 2026-10-08 晚：「他现在在自己没事的时候能听见附近的动静了？」
      —— 手侧声呐（outbox 里那份 K0-K3 验收过的）接上之后，这就成立了 ✓
    """
    try:
        级 = str((e or {}).get("级别") or "")
        名 = str((e or {}).get("名") or (e or {}).get("名字") or "动静")
        # ⚠ 键名认多一点：手侧那份声呐用的是它自己的字段名，
        #   我这边别再"猜一个键" ✗（E2 就是这么挂的：我用「距」，它读「距离/环」）
        方 = ""
        for k in ("方位", "方向", "方", "dir", "bearing"):
            方 = str((e or {}).get(k) or "")
            if 方:
                break
        距 = ""
        for k in ("距离", "距", "环", "ring", "dist"):
            距 = (e or {}).get(k) or ""
            if 距:
                break
        位 = (e or {}).get("位置") or (e or {}).get("坐标") or (e or {}).get("p")
        try:
            路 = os.path.join(ROOT, "logs", "声呐.jsonl")
            os.makedirs(os.path.dirname(路), exist_ok=True)
            with open(路, "a", encoding="utf-8") as f:
                f.write(json.dumps({"级别": 级, "名": 名, "方位": 方, "距": 距,
                                    "位": 位, "t": round(time.time(), 3)},
                                   ensure_ascii=False) + "\n")
        except Exception:
            pass
        if 级 == "urgent":          # 要命的即刻喊；frame 只落账，不刷屏 ✓
            尾巴 = f"（{方} {距}）".strip("（）") if (方 or 距) else ""
            叙事者.说(f"[{time.strftime('%H:%M')}] 我听见「{名}」"
                     + (f" —— {尾巴}" if 尾巴 else "") + "！", 紧急=True)
            return f"听见动静：{名} {尾巴}"
        # ★★★ 2026-10-09 主人点名：盲挖中听见「叮」→ **立刻插队去挖** ✓
        #   ⚠ 位置在这儿是**故意的**：主链原来那条路（上面那一整段）**一个字不改** ✓
        #     追「叮」是**加在它后面**的下一步 ✓（原件先把该喊的喊了、该记的记了 ✓）
        try:
            追 = 追叮(_桥, 叙事者, e)
        except Exception as ex2:
            print(f"[声呐耳朵] 追「叮」那一句出岔子：{ex2}", flush=True)
            追 = None
        if 追:
            try:
                叙事者.说(f"[{time.strftime('%H:%M')}] {追}", 紧急=True)
            except Exception:
                pass
            return 追
    except Exception as ex:
        print(f"[声呐耳朵] 听动静出岔子（不影响主链）：{ex}", flush=True)
    return None


def 追叮(bridge, 叙事者, e):
    """听见「叮」（`block.lava.pop`）→ **当场插队去挖**。返回一句说明或 None。

    主人 2026-10-09 点名
    ==================
    「盲挖中听见『叮』→ 立刻插队去挖」

    为什么「叮」值钱（老玩家的常识）
    ==============================
    `block.lava.pop` 是岩浆湖冒泡那一声「叮」✓ —— **附近有岩浆湖**的强信号 ✓
    而钻石就长在深层岩浆湖旁边 ✓（1.21 的钻石层：y=-64 ~ 16，
    最密在 **y=-59 ~ -53**；岩浆湖一律生成在 y≤10 ✓）
    所以听见「叮」= 很可能挖到宝了 ✓ **这条线索比一路盲挖值钱得多** ✓

    ⚠ 但只有一半管用，另一半得**自己判** ✗
    ==============================
    手侧的声呐表（`声音速查_1.21.1.json`）把岩浆那几条标成「警惕 / 威胁 2」✓
    而**只有标「反射」档的才会走 urgent 即刻上报** ✗
    → 光靠手侧，这一声只会随状态帧慢慢过来 ✓
    所以本车厢**在脑侧自己认**：不管它走的是 urgent 还是 frame，
    只要音名是岩浆那几条，就当场判、当场插队 ✓

    ⚠ 什么时候**不**去挖（都是拿血换的）
    ==================================
    1. **不在钻石层就不挖** ✗ —— y>16 的地表岩浆湖旁边没有钻石 ✓
       这一条是"别为了一个提示白挖半天" ✓ 只喊一声、记一笔 ✓
    2. **没有活的任务栈 / 没有扫描帧** → 不接单，照实说 ✓
    3. **排不出路**（太远/太陡）→ 不接单，把理由说出来 ✓
    4. **同一个位置 30 秒内只追一次** ✓（岩浆泡一直在响 ✗ 不去重会疯 ✗）
    """
    global _追叮上次, _追叮几次
    try:
        e = e or {}
        # ★ 认名字要**多认几个键** ✓ —— 手侧那种 payload 用的是 `音名` ✓
        #   可走状态帧窗口那一路的条目，`名` 里放的是**人话**（「附近有危险源」）✗
        #   别把"人话"当音名去对（对不上就会**静默漏掉** ✓ 这正是"链子看着通、其实没通"）
        #   规矩：**每个候选值都要含 `领域.名字` 那个点** ✓ 人话里没有点 ✓
        名 = ""
        for _k in ("音名", "sound", "soundName", "名", "名字"):
            _v = str((e or {}).get(_k) or "")
            if "." in _v:
                名 = _v
                break
        if 名 not in 岩浆音:
            return None                      # 不是岩浆那几条 → 不碰 ✓
        位 = e.get("坐标") or e.get("位置") or e.get("p")
        if not (isinstance(位, (list, tuple)) and len(位) >= 3):
            return None                      # 没有声源坐标 → 没法追 ✓
        状态 = getattr(叙事者, "最后状态", None)
        if not 状态:
            return "听见「叮」了，可这一拍没拿到扫描帧 —— 等下一拍"
        我 = (状态 or {}).get("pos")
        if not (isinstance(我, (list, tuple)) and len(我) >= 3):
            return "听见「叮」了，可不知道我自己在哪 —— 先不动"
        脚下 = int(float(我[1]) // 1)
        # ── 规矩 1：不在钻石层就不挖 ✓（只喊一声、记一笔）──
        if not (钻石层[0] <= 脚下 <= 钻石层[1]):
            return (f"听见「叮」（岩浆泡）@{[int(位[0]), int(位[1]), int(位[2])]} —— "
                    f"可我在 y={脚下}（钻石层是 y={钻石层[0]}~{钻石层[1]}），"
                    f"这儿的岩浆旁边没有钻石 ✗ 记一笔，不下去追")
        # ── 规矩 4：同一个位置 30 秒内只追一次 ✓ ──
        键 = (int(float(位[0])), int(float(位[1])), int(float(位[2])))
        现在 = time.time()
        if 现在 - _追叮上次.get(键, -9999.0) < 30.0:
            return None
        栈 = _活实例(bridge, "任务栈")
        if 栈 is None:
            return f"听见「叮」@{list(键)}，可找不到活着的任务栈 —— 追不了 ✗"
        # ── 规矩 3：排路（挖过去就复用生存常识那一份实现 ✓ 不抄第二遍 ✓）──
        生 = _找挖路模块()
        if 生 is None:
            return f"听见「叮」@{list(键)}，可找不到「安排一趟挖到」—— 排不出路 ✗"
        步, 因 = 生.安排一趟挖到(状态, list(键), 背包=None, 最远=16)
        if not 步:
            _追叮上次[键] = 现在
            return f"听见「叮」@{list(键)}，可排不出路：{因}"
        try:
            import json as _jH
            open("logs/计划原文.jsonl", "a", encoding="utf-8").write(_jH.dumps({
                "t": time.time(),
                "名字": str((任 or {}).get("名字") if isinstance(任, dict) else 任)[:40],
                "步骤": ((任 or {}).get("步骤") if isinstance(任, dict) else None)},
                ensure_ascii=False, default=str) + "\n")
        except Exception as _eH:
            print("[耳朵] 记计划原文失败：%s" % _eH, flush=True)
        好 = 栈.接(f"追「叮」：挖到岩浆泡那儿（{list(键)}）", 步, 状态)
        if not 好:
            return f"听见「叮」@{list(键)}，路排好了（{len(步)} 步），可任务栈不接 ✗"
        _追叮上次[键] = 现在
        _追叮几次 += 1
        return (f"★ 听见「叮」（岩浆泡）@{list(键)} —— 钻石就在这种地方！"
                f"我当场插队去挖（{len(步)} 步，第 {_追叮几次} 次）")
    except Exception as ex:
        print(f"[声呐耳朵] 追「叮」出岔子（不影响主链）：{ex}", flush=True)
        return None


def _找挖路模块():
    """鸭子类型地找「生存常识」那节车厢里的 `安排一趟挖到` ✓（不抄第二遍 ✓）"""
    for m in list(sys.modules.values()):
        try:
            if callable(getattr(m, "安排一趟挖到", None)):
                return m
        except Exception:
            continue
    return None





def _活实例(bridge, 类名):
    """车钩的探针登记过的活实例（取最后一个）。"""
    try:
        类 = getattr(bridge, 类名, None)
        活 = list(getattr(类, "车钩活着的实例", []) or [])
        return 活[-1] if 活 else None
    except Exception:
        return None


def _接单支路(号, 说明=""):
    return  # ★ 2026-10-16 收工：**空操作** ✓（一次调用=一次文件写 ✗ 太贵 ✓ 已量完 ✓）
    """★ 2026-10-16 支路自报（一行 ✓ 必出声 ✓）：让"我从哪一行出去"自己写下来 ✓ 不用猜 ✗"""
    try:
        import json as _j, os as _o, time as _t
        _o.makedirs(os.path.join(根, "logs"), exist_ok=True)
        with open(os.path.join(根, "logs", "接单支路.jsonl"), "a", encoding="utf-8") as _f:
            _f.write(_j.dumps({"t": int(_t.time() * 1000), "行": 号, "说明": str(说明)[:90]},
                              ensure_ascii=False) + "\n")
    except Exception as _e:
        print("[耳朵] 支路记账失败（出声 ✓）：%s" % _e, flush=True)


def 接单(bridge, 叙事者, e):
    print("[接单入口] bridge的id=" + str(id(bridge)) + " ｜ 本模块=" + __file__ + " ｜ 模块名=" + __name__, flush=True)
    """听见一句话 → 立刻认口令、立刻做计划、立刻接单。返回一句说明或 None。"""
    # ★★★ 2026-10-15 **探针（主人提议 ✓）**：在入口把"谁在调 + 递的是什么"一次记清 ✓
    #   为什么：我这边账上明明"递过去的状态不是 None"✓ 可它回"没有扫描帧"✗ ⇒
    #   要么**不是我在调它** ✗ 要么**递的不是我以为的那个** ✗ ⇒ 探针在**入口**一问就分 ✓
    try:
        import json as _jp, time as _tp, os as _op, sys as _sp
        _调 = "?"
        try:
            _f = _sp._getframe(1)
            _调 = "%s:%s" % (os.path.basename(_f.f_code.co_filename) if (_f and _f.f_code) else "?",
                             _f.f_code.co_name if (_f and _f.f_code) else "?")
        except Exception:
            pass
        _op.makedirs("logs", exist_ok=True)
        with open("logs/接单探针.jsonl", "a", encoding="utf-8") as _fp:
            _fp.write(_jp.dumps({
                "t": _tp.time(),
                "谁在调": _调,
                "叙事者是None": 叙事者 is None,
                "叙事者类型": (type(叙事者).__name__ if 叙事者 is not None else None),
                "叙事者id": id(叙事者) if 叙事者 is not None else None,
                "最后状态是None": (getattr(叙事者, "最后状态", None) is None) if 叙事者 is not None else None,
                "最后状态键数": (len(getattr(叙事者, "最后状态", {}) or {}) if isinstance(getattr(叙事者, "最后状态", None), dict) else -1),
                "文本": str((e or {}).get("text") or "")[:30],
                "接单代码id": id(接单.__code__),
                "接单首行": 接单.__code__.co_firstlineno,
            }, ensure_ascii=False) + "\n")
    except Exception as _ep:
        print("[耳朵] 接单探针失败：%s" % _ep, flush=True)
    原话 = str((e or {}).get("text") or "").strip()
    谁 = str((e or {}).get("from") or "?")
    if not 原话:
        try:
            open("logs/接单探针.jsonl", "a", encoding="utf-8").write(
                '{"t": ' + str(time.time()) + ', "点": "出口", "行号": 279}\n')
        except Exception: pass
        _接单支路(329, 'None')
        return None
    常 = _找认口令模块()
    if 常 is None:
        try:
            open("logs/接单探针.jsonl", "a", encoding="utf-8").write(
                '{"t": ' + str(time.time()) + ', "点": "出口", "行号": 282}\n')
        except Exception: pass
        _接单支路(336, '"耳朵没找到「认口令」（生存常识车厢不在？）"')
        return "耳朵没找到「认口令」（生存常识车厢不在？）"
    # ① 记进「上次原话」—— 认口令 就是靠它 + 90 秒时效判断的
    try:
        常._上次原话.update({"原话": 原话, "时刻": time.time(), "说话人": 谁})
    except Exception as ex:
        try:
            open("logs/接单探针.jsonl", "a", encoding="utf-8").write(
                '{"t": ' + str(time.time()) + ', "点": "出口", "行号": 287}\n')
        except Exception: pass
        _接单支路(345, 'f"耳朵记原话失败：{ex}"')
        return f"耳朵记原话失败：{ex}"
    目标 = None
    try:
        # ★ 2026-10-16 探针（写文件 ✓ 不许 print ✗）：认口令进去/出来都留痕 ✓
        try:
            import json as _jQ, os as _oQ, time as _tQ
            _oQ.makedirs("logs", exist_ok=True)
            with open("/dev/null", "a", encoding="utf-8") as _fQ:
                _fQ.write(_jQ.dumps({"t": _tQ.time(), "点": "进去", "常是None": 常 is None,
                    "常模块名": getattr(常, "__name__", None), "常有认口令": callable(getattr(常, "认口令", None)),
                    "常有原话表": hasattr(常, "_上次原话"),
                    "原话表内容": str(getattr(常, "_上次原话", {}))[:80]}, ensure_ascii=False) + "\n")
        except Exception as _eQ:
            pass
        目标 = 常.认口令()
        print("[耳朵] 认口令返回 = " + str(目标) + " ｜ 真值=" + str(bool(目标)), flush=True)
        try:
            import json as _jR, time as _tR
            with open("/dev/null", "a", encoding="utf-8") as _fR:
                _fR.write(_jR.dumps({"t": _tR.time(), "点": "出来", "目标": str(目标)[:40],
                    "真值": bool(目标)}, ensure_ascii=False) + "\n")
        except Exception:
            pass
    except Exception as ex:
        try:
            open("logs/接单探针.jsonl", "a", encoding="utf-8").write(
                '{"t": ' + str(time.time()) + ', "点": "出口", "行号": 292}\n')
        except Exception: pass
        _接单支路(354, 'f"耳朵认口令炸了：{ex}"')
        return f"耳朵认口令炸了：{ex}"
    if not 目标:
        try:
            open("logs/接单探针.jsonl", "a", encoding="utf-8").write(
                '{"t": ' + str(time.time()) + ', "点": "出口", "行号": 294}\n')
        except Exception: pass
        _接单支路(360, 'None                      # 不是口令，正常聊天，不管 ✓')
        return "[认口令没认出] 目标为空 ⇒ 这次不算口令（原话=%s）" % str(_上次原话.get("原话") or "")[:40]   # ★ 2026-10-17 不再回 None ✓ 让账本说实话 ✓
    # ② 当前扫描帧（叙事者每拍都存着）
    状态 = getattr(叙事者, "最后状态", None)
    try:
        import json as _j, os as _o, time as _t
        with open("logs/耳朵诊断.jsonl", "a", encoding="utf-8") as _f:
            _f.write(_j.dumps({"t": _t.time(),
                               "有叙事者": 叙事者 is not None,
                               "叙事者类型": (type(叙事者).__name__ if 叙事者 is not None else None),
                               "最后状态是None": (getattr(叙事者, "最后状态", None) is None),
                               "有状态": 状态 is not None,
                               "状态键数": (len(状态) if isinstance(状态, dict) else -1)},
                              ensure_ascii=False) + "\n")
    except Exception as _e:
        print("[耳朵·诊断] 写账本炸了", _e, flush=True)
    # ★ 探针A（门前 ✓ bisection 中点）
    try:
        import json as _jA, time as _tA
        with open("logs/接单探针.jsonl", "a", encoding="utf-8") as _fA:
            _fA.write(_jA.dumps({"t": _tA.time(), "点": "A门前",
                "状态isNone": 状态 is None, "状态类型": type(状态).__name__,
                "状态键数": (len(状态) if isinstance(状态, dict) else -1),
                "有scan": (isinstance((状态 or {}).get("scan"), dict) if isinstance(状态, dict) else None),
                "有pos": (bool((状态 or {}).get("pos")) if isinstance(状态, dict) else None)},
                ensure_ascii=False) + "\n")
    except Exception as _eA:
        print("[耳朵] 探针A失败：%s" % _eA, flush=True)
    if not 状态:
        try:
            open("logs/接单探针.jsonl", "a", encoding="utf-8").write(
                '{"t": ' + str(time.time()) + ', "点": "出口", "行号": 322}\n')
        except Exception: pass
        _接单支路(392, 'f"认出口令「{目标}」，可叙事者还没有扫描帧 —— 等下一拍"')
        return f"认出口令「{目标}」，可叙事者还没有扫描帧 —— 等下一拍"
    # ★★★ 2026-10-15（句 5 ✓ tf2）：**状态里没有扫描/位置 ⇒ 先补料** ✗ 别硬推 ✓
    try:
        _缺 = []
        if not isinstance((状态 or {}).get("scan"), dict): _缺.append("扫描")
        if not (状态 or {}).get("pos"): _缺.append("位置")
        if _缺:
            try:
                三 = _活实例(bridge, "三觉")
                if 三 is not None and callable(getattr(三, "要扫描", None)): 三.要扫描()
            except Exception: pass
            try:
                open("logs/接单探针.jsonl", "a", encoding="utf-8").write(
                    '{"t": ' + str(time.time()) + ', "点": "出口", "行号": 333}\n')
            except Exception: pass
            _接单支路(407, 'f"认出口令「{目标}」，可这一帧缺{\'和\'.join(_缺)} —— 已经去要了，等下一拍 ✓"')
            return f"认出口令「{目标}」，可这一帧缺{'和'.join(_缺)} —— 已经去要了，等下一拍 ✓"
    except Exception as _e7:
        print("[耳朵] 缺料检查出岔子：%s" % _e7, flush=True)
    # ③ 立刻做计划（不等心跳）
    译 = _活实例(bridge, "翻译器")
    if 译 is None:
        try:
            open("logs/接单探针.jsonl", "a", encoding="utf-8").write(
                '{"t": ' + str(time.time()) + ', "点": "出口", "行号": 339}\n')
        except Exception: pass
        _接单支路(417, 'f"认出口令「{目标}」，可是找不到活着的翻译器"')
        return f"认出口令「{目标}」，可是找不到活着的翻译器"
    # ★ 探针C（译已拿到 ✓ 下面就是本地翻译/常识那一段 ✓）
    try:
        open("logs/接单探针.jsonl", "a", encoding="utf-8").write(
            '{"t": ' + str(time.time()) + ', "点": "C译已拿到"}\n')
    except Exception: pass
    # ══════ ★★★ 主人 2026-10-09：「LLM 的翻译太不可控了，做本地确定性翻译！」══════
    #   顺序（主人定的）：① 本地精确句式 ✓ ② 本地正则（带数量 ✓）
    #     两层都 Miss ⇒ 才用老路（空串 ⇒ 交给生存常识的意图兜底 / LLM 那条慢路 ✓）
    print("[接单段] ★ ① 要进 收输出 了 ✓", flush=True)
    _文本 = ""
    _本地话 = ""
    try:
        # ★ 2026-10-23 修：`本地翻译器` 住在 tools/，车钩只把项目根塞进 sys.path
        #   ⇒ 原来 `import 本地翻译器` 每次都 ModuleNotFoundError，被 except 静默吞掉
        #   ⇒ 本地确定性翻译**从来没跑过**，数量也全丢。这里把 tools/ 显式加进来。
        import sys as _sysT, os as _osT
        _工具路 = _osT.path.join(ROOT, "tools")
        if _工具路 not in _sysT.path:
            _sysT.path.insert(0, _工具路)
        import 本地翻译器 as _本译
        # ★ 探针D导入本地翻译器之后
        try:
            open("logs/接单探针.jsonl", "a", encoding="utf-8").write(
                '{"t": ' + str(time.time()) + ', "点": "D导入本地翻译器之后"}\n')
        except Exception: pass
        _映射 = None
        # ★ 2026-10-23：`常._名字表()` 是**起车时**的快照；物品映射改到文件里之后，
        #   热插拔耳朵也应该立刻用上新表。直接从 `数据.载入()` 读文件（它每次读盘）。
        try:
            import 数据 as _数M
            _映射 = (_数M.载入() or {}).get("物品映射") or None
        except Exception:
            _映射 = None
        if not _映射:
            try:
                _映射 = 常._名字表()
            except Exception:
                _映射 = None
        _本地 = _本译.译一句(原话, 物品映射=_映射)
        if _本地 and _本地.get("目标"):
            import json as _json
            _文本 = _json.dumps({"意图": "要", "目标": _本地["目标"],
                                "数量": int(_本地.get("数量") or 1)},
                               ensure_ascii=False)
            # ⚠ 这里**只记文本** ✓ 不 return 别的东西 ✗ ——
            #   `接单` 的契约是「返回一句说明 或 None」✓
            #   （我第一版顺手塞了个四元组 ✗ 自己回头看出来的 ✓）
            _本地话 = (f"（本地翻译器·{_本地.get('层')}：要 {_本地['目标']}"
                      f" × {_本地.get('数量') or 1} ✓ 不花大模型 ✓）")
        elif 目标:
            # ★ 2026-10-23 修：本地翻译器没匹配上时，认口令只剩目标，数量会丢成 1。
            #   只要原话里有「N 个」，就把 N 补进收输出，别让求解器永远只算 1。
            #   ⚠ 这里原来抄了生存常识的变量名 `抢`（本模块根本没有）⇒ NameError
            #     被外层 except 静默吞掉 ⇒ 数量兜底一次都没跑过。改用 `目标`。
            import json as _jsonQ, re as _reQ
            _mQ = _reQ.search(r"(\d+|[一二两三四五六七八九十]+)\s*个", 原话)
            try:
                _nQ = _本译.认数(_mQ.group(1)) if _mQ else 1
            except Exception:
                _nQ = int(_mQ.group(1)) if (_mQ and _mQ.group(1).isdigit()) else 1
            _文本 = _jsonQ.dumps({"意图": "要", "目标": 目标, "数量": int(_nQ or 1)},
                                ensure_ascii=False)
            _本地话 = f"（本地兜底：要 {目标} × {int(_nQ or 1)}）"
    except Exception:
        pass
    # ★ 2026-10-23 修：本地翻译器没匹配上时，收输出只拿到空串，数量全丢。
    #   用接单入口已经认出的目标 + 原话里的 N，补一份最小 JSON。
    if not _文本 and 目标:
        try:
            import json as _jsonQ2, re as _reQ2
            _mQ2 = _reQ2.search(r"(\d+|[一二两三四五六七八九十]+)\s*个", 原话)
            _nQ2 = _本译.认数(_mQ2.group(1)) if _mQ2 else 1
            _文本 = _jsonQ2.dumps({"意图": "要", "目标": 目标, "数量": int(_nQ2 or 1)},
                                 ensure_ascii=False)
        except Exception:
            pass
    try:
        # ★ 探针E调收输出之前
        try:
            open("logs/接单探针.jsonl", "a", encoding="utf-8").write(
                '{"t": ' + str(time.time()) + ', "点": "E调收输出之前"}\n')
        except Exception: pass
        动作, 任, 因 = 译.收输出(_文本 or 原话, 状态, 用途="聊天·耳朵")
        print("[接单段] ★ ② 收输出 回来了 ✓", flush=True)
    except Exception as ex:
        try:
            open("logs/接单探针.jsonl", "a", encoding="utf-8").write(
                '{"t": ' + str(time.time()) + ', "点": "出口", "行号": 368}\n')
        except Exception: pass
        _接单支路(465, 'f"耳朵做计划炸了：{ex}"')
        return f"耳朵做计划炸了：{ex}"
    if not (isinstance(任, dict) and 任.get("步骤")):
        # ★ 探针B（推不出前 ✓）
        try:
            import json as _jB, time as _tB
            with open("logs/接单探针.jsonl", "a", encoding="utf-8") as _fB:
                _fB.write(_jB.dumps({"t": _tB.time(), "点": "B推不出",
                    "动作": str(动作)[:40], "任是dict": isinstance(任, dict),
                    "任步骤数": (len((任 or {}).get("步骤") or []) if isinstance(任, dict) else -1),
                    "因": str(因)[:80]}, ensure_ascii=False) + "\n")
        except Exception as _eB:
            print("[耳朵] 探针B失败：%s" % _eB, flush=True)
        try:
            open("logs/接单探针.jsonl", "a", encoding="utf-8").write(
                '{"t": ' + str(time.time()) + ', "点": "出口", "行号": 380}\n')
        except Exception: pass
        _接单支路(481, 'f"认出口令「{目标}」，可这一拍推不出步骤（{str(因)[:60]}）"')
        return f"认出口令「{目标}」，可这一拍推不出步骤（{str(因)[:60]}）"
    # ④ 当场接单
    栈 = _活实例(bridge, "任务栈")
    if 栈 is None:
        try:
            open("logs/接单探针.jsonl", "a", encoding="utf-8").write(
                '{"t": ' + str(time.time()) + ', "点": "出口", "行号": 384}\n')
        except Exception: pass
        _接单支路(489, 'f"排出 {len(任[\'步骤\'])} 步，可是找不到活着的任务栈"')
        return f"排出 {len(任['步骤'])} 步，可是找不到活着的任务栈"
    try:
        import tempfile
        try:
            import json as _jG, time as _tG
            _栈G = locals().get("栈")
            open("logs/接单探针.jsonl", "a", encoding="utf-8").write(_jG.dumps({"t": _tG.time(),
                "点": "G即将接单", "栈类型": (type(_栈G).__name__ if _栈G is not None else None),
                "栈id": (id(_栈G) if _栈G is not None else None), "行": 446}, ensure_ascii=False) + "\n")
        except Exception as _eG:
            print("[耳朵] 探针G失败：%s" % _eG, flush=True)
        try:
            import json as _jH
            open("logs/计划原文.jsonl", "a", encoding="utf-8").write(_jH.dumps({
                "t": time.time(),
                "名字": str((任 or {}).get("名字") if isinstance(任, dict) else 任)[:40],
                "步骤": ((任 or {}).get("步骤") if isinstance(任, dict) else None)},
                ensure_ascii=False, default=str) + "\n")
        except Exception as _eH:
            print("[耳朵] 记计划原文失败：%s" % _eH, flush=True)
        print("[接单段] ★ ③ 要进 栈.接 了 ✓", flush=True)
        print("[栈身份] 栈=" + str(栈)[:60] + " ｜ 类型=" + type(栈).__name__ + " ｜ 有接=" + str(callable(getattr(栈, "接", None))) + " ｜ 模块=" + str(getattr(栈, "__module__", "?")), flush=True)
        try:
            import bridge as _bZ
            print("[类id] 栈的类=" + str(id(type(栈))) + " ｜ bridge.任务栈=" + str(id(_bZ.任务栈)) + " ｜ **同一个吗** = " + str(id(type(栈)) == id(_bZ.任务栈)), flush=True)
        except Exception as _eZ2:
            print("[类id] 比不了：" + str(_eZ2)[:80], flush=True)
        try:
            好 = 栈.接(任.get("名字") or 目标, 任.get("步骤"), 状态)
            print("[栈身份] ★ 栈.接 回来了 ✓ 好=" + str(好)[:40], flush=True)
        except Exception as _eZ:
            print("[栈身份] ✗ 栈.接 炸了：" + type(_eZ).__name__ + " " + str(_eZ)[:120], flush=True)
            raise
    except Exception as ex:
        try:
            open("logs/接单探针.jsonl", "a", encoding="utf-8").write(
                '{"t": ' + str(time.time()) + ', "点": "出口", "行号": 389}\n')
        except Exception: pass
        _接单支路(515, 'f"耳朵接单炸了：{ex}"')
        return f"耳朵接单炸了：{ex}"
    print("[接单段] ★ ④ 栈.接 出来了 ✓", flush=True)
    if 好:
        try:
            open("logs/接单探针.jsonl", "a", encoding="utf-8").write(
                '{"t": ' + str(time.time()) + ', "点": "出口", "行号": 391}\n')
        except Exception: pass
        _接单支路(521, '(f"耳朵接单 ✓：「{目标}」{len(任[\'步骤\'])} 步 —— "')
        return (f"耳朵接单 ✓：「{目标}」{len(任['步骤'])} 步 —— "
                f"{动作 or ''}（听见就动身，没等心跳）")
    # ★★★ 2026-10-09 主人：「把"拒单点名"补上」✓
    #   从前这里是一句**自己编的笼统话** ✗（「任务栈说这个活里有没登记的动作」✓）
    #   结果：主人和我都只能猜到底是哪个动作 ✗ —— 而且**猜错过一次** ✓
    #   规矩（今晚第 N 次）：**拒单必须点到具体名字** ✗
    #     栈返回什么 ✓ 计划里都有哪些动作 ✓ 白名单现在长什么样 ✓ —— 三样一起打 ✓
    _动作们 = sorted({str((x or {}).get("动作")) for x in (任.get("步骤") or [])})
    _白 = sorted(getattr(栈, "允许动作", []) or [])
    try:
        open("logs/接单探针.jsonl", "a", encoding="utf-8").write(
            '{"t": ' + str(time.time()) + ', "点": "出口", "行号": 400}\n')
    except Exception: pass
    _接单支路(534, '(f"耳朵接单被拒：「{目标}」{len(任[\'步骤\'])} 步 —— "')
    return (f"耳朵接单被拒：「{目标}」{len(任['步骤'])} 步 —— "
            f"**栈.接 返回 {好!r}** ｜ 计划里的动作 {_动作们} ｜ 白名单 {_白} ｜ "
            f"不在白名单的 {sorted(set(_动作们) - set(_白))}")


# ─────────────────────── 车厢接口 ───────────────────────

def 装上(bridge, 日志=None, **kw):
    global _日志, _桥
    _日志 = 日志
    _桥 = bridge
    叙类 = getattr(bridge, "叙事者", None)
    if 叙类 is None:
        return {"好": False, "为什么": "找不到 叙事者 类", "打了": []}
    if getattr(叙类, "_声呐耳朵装了", False):
        return {"好": True, "为什么": "已经装过了（幂等）", "打了": []}
    原看事件 = getattr(叙类, "看事件", None)
    if not callable(原看事件):
        return {"好": False, "为什么": "叙事者.看事件 不是函数", "打了": []}
    _原件[id(叙类)] = 原看事件

    def 看事件(self, e):
        r = 原看事件(self, e)              # ★ 原件先跑完，行为一个字不改
        try:
            if isinstance(e, dict) and e.get("kind") == "声呐":
                听动静(self, e, bridge)
            if isinstance(e, dict) and e.get("kind") == "chat":
                说明 = 接单(bridge, self, e)
                if 说明:
                    _说(f"[声呐耳朵] {说明}")
                    try:
                        self.说(f"[{time.strftime('%H:%M')}] {说明}", 紧急=True)
                    except Exception:
                        pass
        except Exception as ex:
            print(f"[声呐耳朵] 耳朵出岔子（不影响主链）：{ex}", flush=True)
        return r

    叙类.看事件 = 看事件
    叙类._声呐耳朵装了 = True
    return {"好": True, "为什么": "", "打了": [
        "叙事者.看事件()  ← 听见 chat 就当场认口令 + 做计划 + 接单（原来那条路一个字不改）"]}


def 卸下(bridge):
    global _日志
    叙类 = getattr(bridge, "叙事者", None)
    原 = _原件.pop(id(叙类), None) if 叙类 is not None else None
    if not 原:
        return {"好": True, "为什么": "本来就没装", "打了": []}
    叙类.看事件 = 原
    try:
        del 叙类._声呐耳朵装了
    except AttributeError:
        pass
    _日志 = None
    return {"好": True, "为什么": "", "打了": ["还原 叙事者.看事件()"]}
