#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""认知轨迹（第 1 步 · **纯只读** ✓ 主人 2026-10-16 的方案 ✓）

★★ 主人定的三步走，这是**第 1 步**：先能"看见它怎么想的" ✗ 不改任何行为 ✓

★ 为什么先做这一步（我自己的评估 ✓）：
   · **零风险** ✓：只观察 ✗ 不判断 ✗ 不加动作 ✗ 不开新状态源 ✗（主人方案④的原话 ✓）
   · 它顺带就是验收⑤要的两本账：`logs/轨迹.jsonl` ✓ ＋ `logs/思维链.jsonl` ✓
   · 跑一晚就能**验证设计**（拆解/分叉/校验 ✓）而不是先写一堆会坏的逻辑 ✗

★ 老祖依据：
   · **LLM-Modulo**：批评者在**外面**看（观察者独立于被观察者 ✓）
   · **tf2**：一切都带**时间戳**（本项目全链路一律 **epoch 毫秒** ✓）
   · **老祖第 6 条**：**包装 ≠ 替换** ✗ ⇒ 每个钩子**第一件事都是回调原函数** ✓ 并**原样返回** ✓
   · **老祖第 8 条**：**失败必须出声** ✗（本车厢自己的错也写账 ✓ 不静默 ✓）
   · **老祖第 10 条**：观察**常开** ✓（所以默认启用 ✓ 但**只读** ✓ 出事拔掉不影响主链 ✓）

★ 它**不做什么**（主人方案里点名的红线 ✓）：
   · 不产生任何新的状态源 ✗ ｜ 不修改任何参数/返回值 ✗ ｜ 不自己判断"完成" ✗
   · 不发任何命令 ✗ ｜ 不读云端 ✗ ｜ 不写"事实"（只记录**别人给的事实** ✓ 带来源 ✓）
"""
import json
import os
import time

根 = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_原 = {}
_状 = {"接单": 0, "判定": 0, "事件": 0, "错": 0}
_上次判定 = {}          # (任务id, 第几步) → 上次的判据结论（只在**变了**的时候记 ✓ 省账 ✓）
_事件白名单 = ("接单", "步骤完成", "步骤失败", "重试", "拒单", "替换", "判据出错",
              "步骤开始", "整任务失败", "任务完成", "中止", "★ 判幽灵任务 ⇒ 中止它")
_开关 = True
_日志 = None

_RATE = {"窗口起": 0.0, "条数": 0, "上限": 8}      # 每 5 秒最多 8 条（防日志雪球 ✓ 昨晚的教训 ✓）


def _可写():
    """频率闸：防"每拍一条"把账写爆 ✗（昨晚日志雪球/内存的教训 ✓）"""
    现在 = time.time()
    if 现在 - _RATE["窗口起"] > 5.0:
        _RATE["窗口起"] = 现在
        _RATE["条数"] = 0
    _RATE["条数"] += 1
    return _RATE["条数"] <= _RATE["上限"]


_说开 = False          # ★ 默认关 ✓（config `认知轨迹.说话` 打开才说 ✓）
_说账 = {"上次": 0.0, "本任务条数": 0, "任务": None, "上限": 40, "间隔秒": 3.0}


def _能说(任=None):
    """说话闸：默认关 ✓ ＋ 限频 ✓ ＋ 每任务上限 ✓（防刷屏 ✗ 主人骂过日志刷屏 ✓）"""
    if not _说开:
        return False
    名 = str((任 or {}).get("名字")) if isinstance(任, dict) else None
    if 名 != _说账["任务"]:
        _说账["任务"] = 名
        _说账["本任务条数"] = 0
    if _说账["本任务条数"] >= _说账["上限"]:
        return False
    现在 = time.time()
    if 现在 - _说账["上次"] < _说账["间隔秒"]:
        return False
    _说账["上次"] = 现在
    _说账["本任务条数"] += 1
    return True


def _说给世界(栈, 文本):
    """让小家伙**在游戏里说出来** ✓（走已有的 say 命令 ✓ 不新开通道 ✗）
    规矩：只翻事实 ✗ 不编 ✓ ｜ 短句 ✓ ｜ 失败**出声** ✓ 不静默 ✓"""
    try:
        句 = str(文本)
        if len(句) > 90:
            句 = 句[:88] + "…"
        if hasattr(栈, "发"):
            栈.发({"cmd": "say", "text": 句})
            _落("认知轨迹.jsonl", {"t": int(time.time() * 1000), "事件": "我对世界说", "文本": 句})
            return True
    except Exception as e:
        print("[认知轨迹] 说话失败（出声 ✓）：%s" % e, flush=True)
    return False


def _年纪话(毫秒):
    try:
        if not isinstance(毫秒, (int, float)):
            return ""
        return "（地图 %d 毫秒新）" % 毫秒 if 毫秒 < 1000 else "（地图 %.1f 秒新）" % (毫秒 / 1000.0)
    except Exception:
        return ""


def _落(文件, 条):
    """写一条 ✓ 失败**出声** ✗ 不静默 ✓（老祖第 8 条）"""
    try:
        os.makedirs(os.path.join(根, "logs"), exist_ok=True)
        with open(os.path.join(根, "logs", 文件), "a", encoding="utf-8") as f:
            f.write(json.dumps(条, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception as e:
        出 = {"t": int(time.time() * 1000), "车厢": "认知轨迹", "事件": "写账失败（出声 ✓）",
             "文件": 文件, "为什么": str(e)[:120]}
        try:
            with open(os.path.join(根, "logs", "认知轨迹-错.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(出, ensure_ascii=False) + "\n")
        except Exception:
            print("[认知轨迹] 写账失败，而且连错账都写不进去：%s" % e, flush=True)
        _状["错"] += 1
        return False


def _来源(s):
    """这条判断**依据什么**（帧 ✓ 还是不知道 ✗）—— 只记录，不解释 ✓"""
    try:
        if not isinstance(s, dict):
            return {"状态": None}
        出 = {"帧有pos": bool(s.get("pos")), "帧有scan": isinstance(s.get("scan"), dict)}
        扫描 = s.get("scan") or {}
        if isinstance(扫描, dict) and 扫描.get("t"):
            try:
                出["scan年龄毫秒"] = int(time.time() * 1000 - float(扫描["t"]))
            except Exception:
                pass
        return 出
    except Exception:
        return {}


def 装上(bridge, 日志=None, 数=None, 车钩=None, **kw):
    global _日志
    if 日志:
        _日志 = 日志
    栈 = getattr(bridge, "任务栈", None)
    类 = 栈 if isinstance(栈, type) else type(栈) if 栈 is not None else None
    if 类 is None:
        return {"好": False, "为什么": "找不到任务栈类", "打了": []}
    if getattr(类, "_认知轨迹装了", False):
        return {"好": True, "为什么": "装过了（幂等 ✓）", "打了": []}
    try:
        import json as _j
        try:
            c = _j.load(open(os.path.join(根, "config.json"), encoding="utf-8"))
            _开关 = bool(((c.get("认知轨迹") or {}).get("启用")))
            _c = (c.get("认知轨迹") or {})
            # ★ 说话默认关 ✓（开关关着 ⇒ 一个字都不发 ✓ 零风险 ✓）
            globals()["_说开"] = bool(_c.get("说话"))
        except Exception as e:
            print("[认知轨迹] 读 config 失败（默认开 ✓ 出声 ✓）：%s" % e, flush=True)
    except Exception:
        pass
    打了 = []

    # ══════ 钩子①：`接` —— 记下"它答应了哪件事、计划长什么样"（= 思维链的起点 ✓）
    原接 = getattr(类, "接", None)
    if callable(原接):
        _原[("接", id(类))] = 原接

        def 接(self, 名字, 步骤, s, **kw):
            结果 = 原接(self, 名字, 步骤, s, **kw)          # ★ 第一件事：回调原函数 ✓ 原样返回 ✓
            try:
                if _开关 and 结果:
                    步 = list(步骤 or [])
                    _落("思维链.jsonl", {
                        "t": int(time.time() * 1000), "类型": "接单·计划",
                        "任务": str(名字)[:60], "步数": len(步),
                        "计划": [{"动作": (x or {}).get("动作"),
                                 "目标": (x or {}).get("物品") or (x or {}).get("方块"),
                                 "p": (x or {}).get("p")} for x in 步[:40]],
                        "来源": _来源(s)})
                    _状["接单"] += 1
                    if _能说(getattr(self, "任务", None)):
                        步 = list(步骤 or [])
                        头 = (步[0].get("动作") if 步 and isinstance(步[0], dict) else "")
                        _说给世界(self, "我想好了：%s（%d 步）%s —— 先%s" % (
                            str(名字)[:24], len(步),
                            _年纪话(((s or {}).get("scan") or {}).get("t") and (time.time() * 1000 - float(((s or {}).get("scan") or {}).get("t")))),
                            头 or "动手"))
            except Exception as e:
                print("[认知轨迹] 接单记录失败（出声 ✓）：%s" % e, flush=True)
                _状["错"] += 1
            return 结果                                # ★ 原样返回 ✓ 一个字不改 ✓

        类.接 = 接
        打了.append("任务栈.接()  ← 只记录「答应了什么计划」（思维链.jsonl ✓）")

    # ══════ 钩子②：`_看完成了没` —— 记下"它凭什么判这一步成不成"（只在结论**变了**时记 ✓ 省账 ✓）
    原看 = getattr(类, "_看完成了没", None)
    if callable(原看):
        _原[("看完成", id(类))] = 原看

        def _看完成了没(self, 步, s, 任=None):
            完成, 因 = 原看(self, 步, s, 任)          # ★ 回调原函数 ✓
            try:
                if _开关:
                    键 = (id(任) if 任 is not None else 0, (任 or {}).get("第几步"),
                          (步 or {}).get("动作"))
                    新 = (bool(完成), str(因)[:60])
                    if _上次判定.get(键) != 新 and _可写():
                        _上次判定[键] = 新
                        _落("轨迹.jsonl", {
                            "t": int(time.time() * 1000), "类型": "判定",
                            "任务": str((任 or {}).get("名字"))[:40] if isinstance(任, dict) else None,
                            "第几步": (任 or {}).get("第几步") if isinstance(任, dict) else None,
                            "动作": (步 or {}).get("动作"),
                            "结论": "成" if 完成 else "还没成",
                            "依据": str(因)[:80] if 因 else None,
                            "来源": _来源(s)})
                        _状["判定"] += 1
                        if 完成 and _能说(任):
                            _说给世界(self, "%s 成了 ✓ %s" % ((步 or {}).get("动作"),
                                      _年纪话(((s or {}).get("scan") or {}).get("t") and (time.time() * 1000 - float(((s or {}).get("scan") or {}).get("t"))))))
            except Exception as e:
                print("[认知轨迹] 判定记录失败（出声 ✓）：%s" % e, flush=True)
                _状["错"] += 1
            return 完成, 因                            # ★ 原样返回 ✓（两个元素都不动 ✓）

        类._看完成了没 = _看完成了没
        打了.append("任务栈._看完成了没()  ← 只记录「每个判定的依据」（轨迹.jsonl ✓ 只在结论变化时 ✓）")

    # ══════ 钩子③：`_记` —— 把主链自己的事件镜像一份（失败/重试/拒单 ✓ = 反思的素材 ✓）
    原记 = getattr(类, "_记", None)
    if callable(原记):
        _原[("记", id(类))] = 原记

        def _记(self, 事件, **kw):
            结果 = 原记(self, 事件, **kw)             # ★ 回调原函数 ✓
            try:
                if _开关 and str(事件) in _事件白名单 and _可写():
                    _落("轨迹.jsonl", {"t": int(time.time() * 1000), "类型": "事件",
                                     "事件": str(事件), "细节": {k: str(v)[:80] for k, v in list(kw.items())[:8]}})
                    _状["事件"] += 1
                    if str(事件) in ("步骤失败", "重试", "整任务失败", "拒单") and _能说(getattr(self, "任务", None)):
                        _说给世界(self, "%s：%s" % (str(事件),
                                  str(kw.get("原因") or kw.get("动作") or "")[:40]))
            except Exception as e:
                print("[认知轨迹] 事件记录失败（出声 ✓）：%s" % e, flush=True)
                _状["错"] += 1
            return 结果

        类._记 = _记
        打了.append("任务栈._记()  ← 镜像主链事件（失败/重试/拒单 ✓ 反思素材 ✓ 白名单+限频 ✓）")

    setattr(类, "_认知轨迹装了", True)
    try:
        os.makedirs(os.path.join(根, "logs"), exist_ok=True)
        with open(os.path.join(根, "logs", "认知轨迹.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": int(time.time() * 1000), "事件": "上岗",
                                "说明": "纯只读 ✓ 不改行为 ✗ 不加动作 ✗ 不开新状态源 ✗",
                                "两个钩子": 打了}, ensure_ascii=False) + "\n")
    except Exception as e:
        print("[认知轨迹] 上岗账写不进去：%s" % e, flush=True)
    return {"好": True, "为什么": "", "打了": 打了}


def 卸下(bridge):
    栈 = getattr(bridge, "任务栈", None)
    类 = 栈 if isinstance(栈, type) else type(栈) if 栈 is not None else None
    if 类 is None:
        return False
    for 名, 键 in (("接", "接"), ("_看完成了没", "看完成"), ("_记", "记")):
        原 = _原.pop((键, id(类)), None)
        if callable(原):
            setattr(类, 名, 原)
    try:
        delattr(类, "_认知轨迹装了")
    except Exception:
        pass
    return True
