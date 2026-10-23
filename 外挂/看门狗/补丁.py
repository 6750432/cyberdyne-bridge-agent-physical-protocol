#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看门狗 —— 治"某一步卡死不动、又永远不超时"（2026-10-14 真机血证 ✓）

★ 血证（服务端 + 账本 ✓）
   账本：20:39:22 接单 ⇒ 第0步「调」**开始** ⇒ 然后三分钟一动不动 ✗
   手侧状态帧：`acting: idle` ✗ 背包空 ✗ drops 空 ✗ 位置三秒不变 ✗
   ⇒ 那条命令**根本没发到手** ✗（卡在脑里等参数/等状态 ✓）
   ⇒ 而主人要求"先不要时间限制"✓ ⇒ 卡住就**永远卡住** ✗（我自己造的坑 ✓ 认 ✓）

★ 修法（车厢层 ✓ 不动主链 ✓）
   盯住每一次「任务栈._下发」：
     · 同一个 (任务, 第几步) 第一次下发时**记时间** ✓
     · 同一步**反复下发**超过「卡死秒」（默认 240 秒 ✓）还没过 ⇒ 判定卡死 ✗
       ⇒ 把这一步**就地改写成 `{"动作":"等","ms":1}`** ✓（当拍就过 ✓）
       ⇒ 让主链自己的流程继续往前走 ✓（它会按自己的规矩重试/换活 ✓）
   为什么用"改写"而不是直接喊失败：改写只碰**这一步**✓ 不越权 ✓ 风险最小 ✓
   （教训：今晚我已经两次改错地方 ✗ 这次选最窄的那条路 ✓）
"""
import json
import os
import time

_日志 = None
_账本 = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "logs", "看门狗.jsonl")
_原件 = {}
_步表 = {}          # (任务, 第几步) → 第一次下发时刻 ✓
_救过 = {}          # 已救过的步 ✓（一步只救一次 ✗ 免得反复）

启用 = True
卡死秒 = 240.0       # 4 分钟没动静就判卡死 ✓（正经的挖矿/走路绝不会这么久 ✓）
认识的步 = {"走到", "挖", "拾", "放", "合成", "等", "说", "看", "打", "吃", "调头"}   # 手侧真认的 ✓
未知步秒 = 20.0      # ★ 不认识的步名（如主链来的「调」✗）⇒ 20 秒就判死 ✓（别等 240 ✗ 真机血证 ✓）


def _说(文):
    if _日志:
        try:
            _日志(文)
        except Exception:
            pass


def _记账(条):
    try:
        os.makedirs(os.path.dirname(_账本), exist_ok=True)
        with open(_账本, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time(), **条}, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _类或自己(对象):
    return 对象 if isinstance(对象, type) else type(对象)



# ══════ ★ 幽灵任务检测（2026-10-14 真机血证 ✓）══════
#   现场：任务账本停在第 1 步「拾」开始 ✗ 而 `任务栈.在跑()` 一直为真 ✓
#   ⇒ 「过日子」引擎以为"我在忙"⇒ **再也不派新活** ✗（实测闲了 5 分钟、五个车厢账本一个都没生成 ✓）
#   本车厢的旧逻辑只管"发下去的步"✗ ⇒ 这种**连发都没发出去**的幽灵，它看不见 ✗
#   修法：心跳时看一眼 —— 说在跑 ✓ 可已经「幽灵秒」没有过任何一次 _下发 ⇒ 判幽灵 ⇒ 中止它 ✓
幽灵秒 = 180.0
_活迹 = {"上次下发": 0.0, "上次看": 0.0, "中止过": 0}
_喂过 = [0]
_原看 = {}          # ★ 2026-10-15：按 id(类) 存**原看状态** ✓（包装必须能回调原函数 ✓）


def 心跳(self, s=None, *a, **kw):
    """挂在 叙事者.看状态 上（主链每帧都叫它 ✓ 天生的心跳 ✓）

    ★★★ 2026-10-15 修（血证 ✓）：**包装 ≠ 替换** ✗✗
      原来这里把 `叙事者.看状态` **整个换掉了** ✗ 而且**从不回调原函数** ✗
      ⇒ 而 `self.最后状态 = s` 正在**原函数**里（bridge.py:174）⇒ **永远不执行** ✓
      ⇒ 耳朵一律读到 `最后状态 = None` ⇒ 报"叙事者还没有扫描帧"✗
      ⇒ 从冷启动**永远接不了单** ✓（今晚第四道同款门：观察被挡 ✓ 老祖第 32 条 ✓）
      规矩：任何包装者**第一句就是回调原函数** ✓（黑板/Subsumption：包装是叠加 ✓ 不是替换 ✗）
    """
    # ★★★ 2026-10-15 诊断（**必出声** ✓ 不许条件 ✗）：这个包装到底有没有被调？喂的是什么？
    try:
        _记账({"事件": "★ 看门狗被喂了", "s是None": s is None,
               "s是dict": isinstance(s, dict),
               "s键数": (len(s) if isinstance(s, dict) else -1),
               "有self": self is not None})
    except Exception as _ed:
        print("[看门狗] 诊断记账失败：%s" % _ed, flush=True)

    # ① **先喂原函数**（它里面会记 `最后状态` ✓ 还会做叙事 ✓）—— 一个字都不许省 ✗
    try:
        # ★ 原函数在**挂具**的 `_原件` 里（本节是按 manifest 补丁点装的 ✓ 不是自己 setattr ✓）
        _原 = None
        try:
            import sys as _sys
            for _名 in ("车厢_看门狗_入口",):
                _m = _sys.modules.get(_名)
                if _m is not None and hasattr(_m, "_原件"):
                    _原 = _m._原件.get(type(self))
                    if callable(_原): break
        except Exception:
            pass
        if not callable(_原):
            _原 = _原看.get(id(type(self)))
        if callable(_原):
            _原(self, s, *a, **kw)
            _喂过[0] += 1
    except Exception as _e:
        _记账({"事件": "回调原看状态出岔子（出声 ✓）", "为什么": str(_e)[:80]})
    except Exception as _e:
        _记账({"事件": "回调原看状态出岔子（出声 ✓）", "为什么": str(_e)[:80]})
    # ★★★ 2026-10-15 补（血证 ✓）：**本车厢把原函数替换掉了** ✗
    #   而原函数里那句 `self.最后状态 = s`（bridge.py:174 ✓）就被吃掉了 ✓
    #   ⇒ 耳朵一律读到 None ⇒ 报"叙事者还没有扫描帧"✗ ⇒ 冷启动永远接不了单 ✓
    #   规矩（老祖第 6/32 条）：**包装 ≠ 替换** ✗ —— 先把它该记的记上 ✓
    try:
        if s is not None:
            self.最后状态 = s
    except Exception as _e0:
        _记账({"事件": "记最后状态出岔子（出声 ✓ 不静默 ✗）", "为什么": str(_e0)[:80]})

    # ② 再做本车厢自己的事（判幽灵 ✓）
    try:
        现在 = time.time()
        if 现在 - float(_活迹["上次看"] or 0) < 5.0:
            return
        _活迹["上次看"] = 现在
        栈 = _找任务栈(self)
        if 栈 is None:
            return
        在跑 = False
        try:
            在跑 = bool(栈.在跑())
        except Exception:
            return
        if not 在跑:
            return
        上次 = float(_活迹["上次下发"] or 0)
        if 上次 and (现在 - 上次) < 幽灵秒:
            return
        # 说在跑、却这么久一次下发都没有 ⇒ 幽灵 ✗
        _活迹["中止过"] = int(_活迹["中止过"] or 0) + 1
        _记账({"事件": "★ 判幽灵任务 ⇒ 中止它", "多久没下发": round(现在 - 上次, 1) if 上次 else "从没下发过",
               "总共中止": _活迹["中止过"]})
        _说("[看门狗] 任务栈说在跑 ✓ 可 %.0f 秒一次都没下发过 ✗ ⇒ **判幽灵、中止它** ✓（让引擎能派新活 ✓）"
            % ((现在 - 上次) if 上次 else 幽灵秒))
        try:
            栈.中止("幽灵任务：从没下发过动作（看门狗 ✓）")
            _活迹["上次下发"] = 现在          # 给它一个喘息窗口再判 ✓
        except Exception as e:
            _记账({"事件": "中止失败（主链不认这个调法 ✗）", "为什么": str(e)[:90]})
    except Exception as e:
        _记账({"事件": "心跳出岔子（静默 ✓）", "为什么": str(e)[:80]})


def _找任务栈(对):
    """从叙事者/桥身上摸任务栈 ✓（几种藏法都试 ✓）"""
    global _栈实例2
    if _栈实例2 is not None:
        return _栈实例2
    for 源 in (对, getattr(对, "任务栈", None)):
        for 名 in ("任务栈", "栈", "任务"):
            他 = getattr(源, 名, None)
            if 他 is not None and hasattr(他, "在跑"):
                _栈实例2 = 他
                return 他
    return None


_栈实例2 = None


def _包下发(原):
    def 新下发(self, 步=None, 任=None, 现在=None, s=None, *a, **kw):
        try:
            if 启用 and isinstance(步, dict):
                现在 = float(现在 or time.time())
                _活迹["上次下发"] = 现在
                # ★★ 2026-10-14 真机血证：按"任务号+第几步"记时 ⇒ **每换一个新任务就清零** ✗
                #    于是同一个卡死的步（例如「拾 oak_log」）被一次次重来、**永远攒不到 240 秒** ✗
                #    ⇒ 任务栈被它占住 ⇒ 过日子的引擎以为"我在忙"⇒ 不再派新活 ✗（实测：闲了 5 分钟 ✓）
                #    修法：按**这一步长什么样**记时（动作 + 目标坐标取整 ✓）⇒ 跨任务累加 ✓
                签 = "%s|%s" % (str(步.get("动作") or "?"),
                               [round(float(x), 1) for x in (步.get("p") or [])[:3]]
                               if isinstance(步.get("p"), (list, tuple)) else "")
                键 = "%s|%s" % (签, (任 or {}).get("第几步"))
                if 键 not in _步表:
                    _步表[键] = 现在                    # 这一步第一次露面 ✓
                elif (现在 - _步表[键]) > (未知步秒 if str(步.get("动作") or "") not in 认识的步 else 卡死秒) \
                        and (现在 - float(_救过.get(键) or 0)) > 90.0:
                    _救过[键] = 现在
                    动 = str(步.get("动作") or "?")
                    _记账({"事件": "★ 判卡死 ⇒ 就地过掉这一步", "任务": (任 or {}).get("任务"),
                           "第几步": (任 or {}).get("第几步"), "动作": 动,
                           "卡了秒": round(现在 - _步表[键], 1),
                           "怎么救": "改写成「等 1 毫秒」⇒ 当拍过 ⇒ 让计划继续 ✓"})
                    限 = 未知步秒 if 动 not in 认识的步 else 卡死秒
                    _说("[看门狗] 第%s步「%s」卡了 %.0f 秒（超过 %.0f%s）⇒ 就地过掉 ✓ 让计划继续 ✓"
                        % ((任 or {}).get("第几步"), 动, 现在 - _步表[键], 限,
                           " ✗ 而且**手侧根本不认识这个动作**" if 动 not in 认识的步 else ""))
                    return 原(self, {"动作": "等", "ms": 1, "_看门狗": "卡死过掉 ✓"}, 任, 现在, s, *a, **kw) \
                        if callable(原) else None
        except Exception as e:
            _记账({"事件": "自己出岔子（原样放行 ✓）", "为什么": str(e)[:100]})
        if callable(原):
            return 原(self, 步, 任, 现在, s, *a, **kw)
        return None
    return 新下发


def 装上(bridge, 日志=None, 账本路径=None, **kw):
    global _日志, _账本, 启用, 卡死秒
    if 日志:
        _日志 = 日志
    if 账本路径:
        _账本 = 账本路径
    for k, v in (kw or {}).items():
        if k == "启用":
            启用 = bool(v)
        elif k in ("卡死秒",):
            卡死秒 = float(v)
    栈 = getattr(bridge, "任务栈", None)
    if 栈 is None or not hasattr(栈, "_下发"):
        return {"好": False, "为什么": "找不到 任务栈._下发", "打了": []}
    类 = _类或自己(栈)
    if getattr(类, "_看门狗装了", False):
        return {"好": True, "为什么": "装过了（幂等 ✓）", "打了": []}
    _原件[类] = getattr(类, "_下发")
    setattr(类, "_下发", _包下发(getattr(类, "_下发")))
    # ★★ 2026-10-14 摘掉心跳钩子（我造成的故障 ✓ 认 ✓）★★
    #   我原来在这里包了 `叙事者.看状态` ✗ ⇒ 它挡在「过日子」的心跳外面 ✓
    #   结果：引擎账本 **17 分钟一条没写** ✗（本该每 20 秒一条 ✓）⇒ 引擎整个不跳了 ✗
    #   教训（今晚第四次）：**跨车厢包别人的钩子，很容易把别人的心跳弄断** ✗
    #   ⇒ 幽灵任务的检测改挂到「过日子」自己身上 ✗（下一轮做 ✓ 不在这儿跨着包 ✓）
    #   本车厢**只管「下发」那一套** ✓（自检 10/0 ✓ 那套是好的 ✓）
    setattr(类, "_看门狗装了", True)
    _说("[看门狗] 上岗 ✓ 同一步卡超过 %.0f 秒 ⇒ 就地过掉 ✓（主链自己的流程照走 ✓）" % 卡死秒)
    return {"好": True, "为什么": "", "打了": ["任务栈._下发"]}


def 卸下(bridge):
    try:
        叙 = getattr(bridge, "叙事者", None)
        叙类 = _类或自己(叙) if 叙 is not None else None
        if 叙类 is not None and getattr(叙类, "_看门狗心跳过", False):
            原看 = _原件.get(叙类)
            if callable(原看):
                _原看.pop(id(叙类), None)
                setattr(叙类, "看状态", 原看)
            delattr(叙类, "_看门狗心跳过")
    except Exception:
        pass
    栈 = getattr(bridge, "任务栈", None)
    if 栈 is None:
        return False
    类 = _类或自己(栈)
    原 = _原件.get(类)
    if callable(原):
        setattr(类, "_下发", 原)
    try:
        delattr(类, "_看门狗装了")
    except Exception:
        pass
    return True
