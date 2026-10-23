#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""走到平面 —— ① 走到的目标**压到我自己这一层**（别给树冠里的高度 ✗）② 砍树回树根（配方 1 ✓）

★ 为什么要 ①（2026-10-14 真机 + 源码双证据 ✓）
   手侧寻路是官方 mineflayer-pathfinder 的薄壳 ✓ 用的是 `GoalNear(x, y, z, 容差2)` ✓
   ⇒ 它是**三维球体** ✗ ⇒ 目标在**树冠里**（y=103 ✗ 而 bot 在 y=93）时，
     地面上**永远进不了那个球** ✗ ⇒ 30 秒超时 ✓（今晚实测：第12步连超 3 次 ⇒ 任务失败 ✓）
   ⇒ 解药：**脑侧就把 y 压到 bot 自己那一层** ✓（走到那根柱子的地面位置 ✓ 正是主人配方 1 的精神 ✓）
★ ② 顺带（同一份血证 ✓）：挖原木时若这一列底下还有更低的原木 ⇒ 先砍最底下那格 ✓

★ 血证（记性车厢自己的原话 ✓）
   [记性]     要上去 [-2998, 100, -4999]（比我高 7 格 ✗ 一步只上 0.…
   [记性·调]  ✗「安排一趟挖上去」没排出路（**手里没有镐**…）
   ⇒ 它想爬上去砍树 ✓ 可记性的爬升路线**要求有镐** ✗ —— 从零开局手里什么都没有 ✗
   ⇒ 于是「调」这一步永远排不出路 ⇒ 卡住 ✗ ⇒（今晚）加上我的看门狗就变成 20 秒一次空转 ✓
   ⇒ 石镐测试因此一步都走不动 ✓

★ 人怎么办（主人三站实测 ✓）
   用**脚**爬 ✓：一格台阶直接跳上去 ✓ 高一点就绕 ✓ —— 不需要镐 ✓
   mineflayer-pathfinder 本来就会跳 1 格台阶 ✓（PATHFINDER.md 里也记着这条 ✓）

★ 做法（确定性 ✓ 最小改动 ✓）
   钩 `任务栈._下发`（类上 ✓）：
     步是「调」且 要 里带「上去」⇒ 改写成 `{"动作":"走到","p": <同一坐标>, "到点":1.5}` ✓
     · 只碰「上去」✗ 不碰「挖到（往下）」✓（往下要真挖 ✓ 留给记性自己的闭环 ✓）
     · 一步只改一次 ✓（同一步反复改写会把走路打断 ✗ 今晚已经吃过这个亏 ✓）
"""
import json
import os
import time

_日志 = None
_账本 = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "logs", "走到平面.jsonl")
_原件 = {}
_改过 = {}
启用 = True


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


def 该改吗(步):
    if not isinstance(步, dict):
        return None
    if str(步.get("动作")) != "调":
        return None
    要 = str(步.get("要") or "")
    if "上去" not in 要:
        return None
    p = 步.get("p")
    if not (isinstance(p, (list, tuple)) and len(p) >= 3):
        return None
    return [float(p[0]), float(p[1]), float(p[2])]



原木类 = ("oak_log", "birch_log", "spruce_log", "jungle_log", "acacia_log",
        "dark_oak_log", "mangrove_log", "cherry_log", "pale_oak_log", "log", "wood")


def _是原木(名):
    名 = str(名 or "").replace("minecraft:", "")
    return any(k in 名 for k in 原木类)


def 同列最低原木(s, 目标):
    """从状态帧里找**同一 (x,z) 列上最低的那格原木** ✓（帧形状不唯一 ⇒ 几种都认 ✓）

    ★ 依据：主人配方 1「砍树先挖下面两个，站到树干最底下，向上抬头挖」✓
      主人看到的原木坐标（日志原话）：oak_log(-2992, 98, -5000) ✓ —— 帧里带坐标 ✓
    """
    try:
        tx, ty, tz = float(目标[0]), float(目标[1]), float(目标[2])
    except Exception:
        return None
    最低 = None
    for 键 in ("blocks", "scan", "看得见的方块", "方块"):
        表 = (s or {}).get(键)
        if not isinstance(表, list):
            continue
        for 条 in 表:
            if not isinstance(条, dict):
                continue
            名 = 条.get("name") or 条.get("id") or 条.get("方块")
            p = 条.get("p") or 条.get("pos") or 条.get("坐标")
            if not (isinstance(p, (list, tuple)) and len(p) >= 3 and _是原木(名)):
                continue
            try:
                x, y, z = float(p[0]), float(p[1]), float(p[2])
            except Exception:
                continue
            if abs(x - tx) > 0.6 or abs(z - tz) > 0.6:      # 同一列 ✓（同一棵树 ✓）
                continue
            if y > ty + 0.6:                                # 只关心比目标低（或相等）的 ✓
                continue
            if 最低 is None or y < 最低[1]:
                最低 = (x, y, z)
    return list(最低) if 最低 else None


def 该回树根吗(步, s):
    """这一步是「挖某格原木」而这一列底下还有更低的原木 ⇒ 回树根 ✓"""
    if not (isinstance(步, dict) and 步.get("动作") == "挖"):
        return None
    p = 步.get("p")
    if not (isinstance(p, (list, tuple)) and len(p) >= 3):
        return None
    名 = str(步.get("物品") or 步.get("方块") or "")
    if not _是原木(名) and not _是原木(步.get("挖的是") or ""):
        return None                                          # 只碰原木 ✓ 石头泥土一律不插手 ✗
    低 = 同列最低原木(s, p)
    if 低 and (float(p[1]) - 低[1]) > 0.6:                   # 底下确实更低 ✓
        return 低
    return None



# ══════ ★ ① 走到目标压高度（2026-10-14 真机 + 源码双证据 ✓）══════
def 该压平吗(步, s):
    """步是「走到」而目标比我高 >2 格 ⇒ 返回压平后的坐标 ✓（别去够树冠 ✗）"""
    if not (isinstance(步, dict) and 步.get("动作") == "走到"):
        return None
    p = 步.get("p")
    if not (isinstance(p, (list, tuple)) and len(p) >= 3):
        return None
    我 = (s or {}).get("pos")
    if not (isinstance(我, (list, tuple)) and len(我) >= 3):
        return None
    try:
        高 = float(p[1]) - float(我[1])
    except Exception:
        return None
    if 高 <= 2.0:                      # 平路/小台阶 ⇒ 不动它 ✓
        return None
    return [float(p[0]), float(我[1]), float(p[2])]


def _包下发(原):
    def 新下发(self, 步=None, 任=None, 现在=None, s=None, *a, **kw):
        try:
            if 启用:
                s_ = s
                try:
                    平 = 该压平吗(步, s)
                    if 平:
                        键0 = "%s|%s|平%s" % ((任 or {}).get("任务") or "?", (任 or {}).get("第几步"), 平)
                        if not _改过.get(键0):
                            _改过[键0] = True
                            _记账({"事件": "★ 走到目标压到我自己这一层", "原目标": list(步.get("p"))[:3],
                                   "改成": 平, "为什么": "GoalNear 是三维球体 ✗ 树冠里的点地面永远到不了 ✓"})
                            _说("[走到平面] 目标高 %.1f 格 ✗ ⇒ 压到我这一层 y=%.0f ✓（走到那根柱子的地面位置 ✓）"
                                % (float(步["p"][1]) - float(((s or {}).get("pos") or [0, 0, 0])[1]), 平[1]))
                            新 = dict(步); 新["p"] = 平; 新["_走到平面"] = "压到我这一层 ✓"
                            return 原(self, 新, 任, 现在, s, *a, **kw) if callable(原) else None
                except Exception as e:
                    _记账({"事件": "压平出岔子（原样放行 ✓）", "为什么": str(e)[:80]})
                # ★ 新规矩（主人配方 1 ✓）：砍树**从下往上** ⇒ 先把目标挪到这一列最底下那格 ✓
                try:
                    低 = 该回树根吗(步, s)
                    if 低:
                        键2 = "%s|%s|根%s" % ((任 or {}).get("任务") or "?", (任 or {}).get("第几步"), 低)
                        if not _改过.get(键2):
                            _改过[键2] = True
                            _记账({"事件": "★ 回树根：从下往上砍", "原目标": [round(float(x), 1) for x in 步.get("p")],
                                   "改成": 低, "为什么": "主人配方 1：站在树干最底下往上砍 ✓ 掉落物落脚边 ⇒ 自动进包 ✓"})
                            _说("[回树根] 目标 %.0f 太高 ✗ ⇒ 先砍这一列最底下那格 y=%.0f ✓（从下往上 ✓ 掉落物落脚边 ✓）"
                                % (float(步["p"][1]), 低[1]))
                            新 = dict(步); 新["p"] = 低; 新["_回树根"] = "从下往上砍 ✓"
                            return 原(self, 新, 任, 现在, s, *a, **kw) if callable(原) else None
                except Exception as e:
                    _记账({"事件": "回树根出岔子（原样放行 ✓）", "为什么": str(e)[:90]})
                落 = 该改吗(步)
                if 落:
                    键 = "%s|%s|%s" % ((任 or {}).get("任务") or "?", (任 or {}).get("第几步"), 落)
                    if not _改过.get(键):
                        _改过[键] = True
                        _记账({"事件": "★ 排不出路 ⇒ 改用脚爬", "去哪": 落,
                               "原来": str(步.get("要"))[:40],
                               "为什么": "记性的爬升要镐 ✗ 从零没镐 ✓ 走过去寻路自己会跳台阶 ✓"})
                        _说("[走到平面] 没镐爬不了 ✗ ⇒ 改成**走过去** [-%.0f, %.0f, %.0f] ✓（脚爬 ✓）"
                            % (abs(落[0]), 落[1], abs(落[2])))
                        return 原(self, {"动作": "走到", "p": 落, "到点": 1.5,
                                         "_爬上去": "用脚爬 ✓ 不用镐 ✓"}, 任, 现在, s, *a, **kw) \
                            if callable(原) else None
        except Exception as e:
            _记账({"事件": "自己出岔子（原样放行 ✓）", "为什么": str(e)[:90]})
        if callable(原):
            return 原(self, 步, 任, 现在, s, *a, **kw)
        return None
    return 新下发


def 装上(bridge, 日志=None, 账本路径=None, **kw):
    global _日志, _账本, 启用
    if 日志:
        _日志 = 日志
    if 账本路径:
        _账本 = 账本路径
    if "启用" in (kw or {}):
        启用 = bool(kw["启用"])
    栈 = getattr(bridge, "任务栈", None)
    if 栈 is None or not hasattr(栈, "_下发"):
        return {"好": False, "为什么": "找不到 任务栈._下发", "打了": []}
    类 = _类或自己(栈)
    if getattr(类, "_走到平面装了", False):
        return {"好": True, "为什么": "装过了（幂等 ✓）", "打了": []}
    _原件[类] = getattr(类, "_下发")
    setattr(类, "_下发", _包下发(getattr(类, "_下发")))
    setattr(类, "_走到平面装了", True)
    _说("[走到平面] 上岗 ✓ 「调·挖上去」⇒ 改成走过去（脚爬 ✓ 不用镐 ✓）")
    return {"好": True, "为什么": "", "打了": ["任务栈._下发"]}


def 卸下(bridge):
    栈 = getattr(bridge, "任务栈", None)
    if 栈 is None:
        return False
    类 = _类或自己(栈)
    原 = _原件.get(类)
    if callable(原):
        setattr(类, "_下发", 原)
    try:
        delattr(类, "_走到平面装了")
    except Exception:
        pass
    return True
