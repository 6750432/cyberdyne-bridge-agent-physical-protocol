#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""服务器仲裁 —— 让小家伙**自己能问服务器**（主人 2026-10-15 亲口提的架构 ✓）

★ 主人两连问（同一件事）：
   ①「既然小家伙没有人类的视网膜，但耳朵总听得见吧？为啥他不跟服务器对答案？」
   ②「看不见背包怎么不问服务器？」
★ 病（今晚实证 ✓）：脑的世界视图**只有手那一条**（mineflayer 帧 ✓）——
   手不说（watch 没设上 ✓ 或者干脆没答 ✓）⇒ 常识就"看不见背包"✗ ⇒ **拒单** ✓
   而真相**服务器一直知道**（RCON 一问就有 ✓）—— 权威源就在旁边没人问 ✗
★ 老祖依据：
   · **STRIPS/PDDL**：判据看**世界事实** ✓ —— 而服务器的答案是最终事实 ✓
   · **SayCan（grounding）**：建议要能落到"我真能做到"✓ —— 那得先知道真有什么 ✓
   · **主人的铁律②**：任何结论都要拿**服务器数据**对照 ✓✓
★ 做法（守规矩 ✓）：
   · **一条长连接**复用（★ 那封信的硬教训：别在循环里 spawn rcon.py ✗ 每次一个新 Java 线程 ✓）
   · 挂在 `叙事者.看状态` 上 —— **第一件事：回调原函数** ✓（今晚血证：包装≠替换 ✗）
   · 只在 `s["items"]` 缺/空时问服务器 ✓（**不抢手的活** ✗ 手有数据就用手 ✓）
   · 只问**短名单**（省往返 ✓）＋ 结果写 `logs/服务器仲裁.jsonl` ✓（出声 ✓ 不静默 ✗）
"""
import json
import os
import socket
import struct
import threading
import time

根 = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_日志 = None
_状 = {"好": False, "问过": 0, "填过": 0}
_锁 = threading.Lock()
_sock = None
_i = 0

# 问什么（短名单 ✓ 只问最容易用得上的 ✓ 以后要什么再加 ✓）
# ★★★ 2026-10-16【定案 ✓】：原来只问木头 ✗ ⇒ 问回来永远 {} ⇒ **背包填不上** ⇒ 脑还是瞎 ✓
#   修：**问"当前任务要什么" ＋ 一条常备链** ✓（合成链上的东西都问 ✓ 不猜 ✗）
常备 = ["oak_log", "spruce_log", "birch_log", "oak_planks", "stick", "crafting_table",
        "cobblestone", "stone", "coal", "iron_ore", "raw_iron", "iron_ingot",
        "wooden_pickaxe", "stone_pickaxe", "iron_pickaxe", "torch", "furnace",
        "dirt", "sand", "gravel", "wheat", "bread", "apple"]
问的 = list(常备)


def 记要问(名字们):
    """把"这一步要什么"加进问的 ✓（任务一变就问得到 ✓ 不猜 ✗）"""
    try:
        for 名 in (名字们 or []):
            名 = str(名 or "").strip()
            if 名 and 名 not in 问的:
                问的.append(名)
        del 问的[80:]          # 上限 ✓（免得越问越多 ✗）
    except Exception:
        pass
玩家 = "DeepSeek"
原看 = {}
# ★★★ 2026-10-16【缓存 ✓ 治爆内存的病】：
#   病（今晚定案 ✓）：手侧背包**永远是空** ✗ ⇒ 下面"空就填"的条件**每帧成立** ✗
#     ⇒ **每秒问 RCON 5 次** ✗（问的[] 个物品 × 5/秒 ✓）⇒ 脑涨到 10GB ✓✓
#   修：**报价缓存** ✓ —— 同一份背包 **TTL 秒内只问一次** ✓ 中间用缓存填 ✓（句 9：等待要有上限 ✓）
_价 = {"t": 0.0, "背包": {}, "TTL": 3.0}
原看 = {}


def _说(文):
    if _日志:
        try: _日志("[服务器仲裁] " + str(文))
        except Exception: pass
    try:
        os.makedirs(os.path.join(根, "logs"), exist_ok=True)
        with open(os.path.join(根, "logs", "服务器仲裁.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time(), "说": str(文)[:200]}, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _配置():
    try:
        c = json.load(open(os.path.join(根, "config.json"), encoding="utf-8"))
        p = ((c.get("m2") or {}).get("probe") or {})
        return (p.get("host") or "127.0.0.1", int(p.get("port") or 25575),
                os.environ.get("MC_RCON_PASSWORD") or "cyberdyne")
    except Exception:
        return ("127.0.0.1", 25575, "cyberdyne")


def _连():
    global _sock, _i
    h, p, pw = _配置()
    s = socket.create_connection((h, p), timeout=6)
    _i += 1
    b = struct.pack("<ii", _i, 3) + pw.encode() + b"\x00\x00"
    s.sendall(struct.pack("<i", len(b)) + b)
    n = struct.unpack("<i", s.recv(4))[0]
    d = b""
    while len(d) < n: d += s.recv(n - len(d))
    _sock = s
    _状["好"] = True
    _说("连上服务器 ✓（一条长连接 ✓ 不再每次 spawn 一个解释器 ✗）")
    return True


def _令(c):
    """一条连接复用 ✓（★ 那封信第一条硬教训）"""
    global _sock, _i
    with _锁:
        for _ in range(2):
            try:
                if _sock is None: _连()
                _i += 1
                b = struct.pack("<ii", _i, 2) + c.encode() + b"\x00\x00"
                _sock.sendall(struct.pack("<i", len(b)) + b)
                n = struct.unpack("<i", _sock.recv(4))[0]
                d = b""
                while len(d) < n: d += _sock.recv(n - len(d))
                return d[8:-2].decode("utf-8", "replace")
            except Exception as e:
                _sock = None
                _说("这一问断了（重连一次 ✓）：%s" % str(e)[:60])
        return ""


def 问背包():
    """★ 2026-10-16【主人：刷屏挡视野 ✗】：换成**只回 RCON、不打扰玩家**的问法 ✓

    老问法 `clear <玩家> <物品> 0`：能数 ✓ 但**会给玩家发提示** ✗（今晚跑了几十次 ⇒ 主人在游戏里被刷屏 ✗ 我认 ✓）
    新问法 `data get entity <玩家> Inventory`：一次拿**整包 NBT** ✓ 只回 RCON ✓ 玩家看不到 ✓ 而且信息更全 ✓
    """
    o = _令("data get entity %s Inventory" % 玩家)
    出 = {}
    try:
        import re as _re
        # NBT 形如：{count: 1, Slot: 0b, id: "minecraft:andesite"}
        for _m in _re.finditer(r'count:\s*(\d+).*?id:\s*"minecraft:([a-z_]+)"', o):
            _n = int(_m.group(1))
            _名 = _m.group(2)
            出[_名] = 出.get(_名, 0) + _n
    except Exception as _e:
        _说("解背包 NBT 出岔子（出声 ✓）：%s" % str(_e)[:70])
    if not 出:
        # 兜底：老问法（只在没有 Inventory 时用 ✓ 尽量少见 ✓）
        for it in 问的[:6]:
            o2 = _令("clear %s minecraft:%s 0" % (玩家, it))
            if "Found " in o2:
                try:
                    n = int(o2.split("Found ")[1].split(" ")[0])
                    if n > 0: 出[it] = n
                except Exception:
                    pass
    _状["问过"] += 1
    return 出


def _装看状态(叙类):
    if not callable(getattr(叙类, "看状态", None)):
        return False
    真 = 叙类.看状态
    原看[id(叙类)] = 真

    def 看状态(self, s=None, *a, **kw):
        # ① **先回调原函数** ✓（今晚血证：包装≠替换 ✗ —— 看门狗那个错我不能再犯 ✓）
        try:
            真(self, s, *a, **kw)
        except Exception as e:
            _说("回调原看状态出岔子（出声 ✓）：%s" % str(e)[:70])
        # ② 只在"手没给背包"时问服务器 ✓（手有就用手 ✓ 不抢 ✗）
        try:
            if isinstance(s, dict):
                现 = s.get("items")
                # ★ 必出声诊断（一行业 ✓）：为什么没填 / 该不该填
                try:
                    _说("诊断：键有=%s 是dict=%s 空=%s 类型=%s"
                        % ("items" in s, isinstance(现, dict),
                           (not 现) if isinstance(现, dict) else "n/a",
                           type(现).__name__))
                except Exception:
                    pass
                if not isinstance(现, dict) or not 现:
                    新 = dict(_价["背包"]) if (time.time() - _价["t"]) < _价["TTL"] else None
                    # ★★★ 2026-10-16【血证 ✓ 主人看到刷屏那一刻起】：**热路径上不许有阻塞调用** ✗
                    #   病：我在这儿每 3 秒真问一次 RCON（阻塞 socket ✗）⇒ 主循环被拖住 ⇒ 口令读不动 ✓
                    #   修：**真问搬进后台线程** ✓ —— 这里**只读缓存** ✓（拿不到就先用手的 ✓ 绝不阻塞 ✗）
                    新 = dict(_价["背包"]) if _价["背包"] else None
                    if 新:
                        s["items"] = 新
                        s["_items来源"] = "服务器仲裁（RCON ✓）"
                        _状["填过"] += 1
                        if _状["填过"] <= 3 or _状["填过"] % 20 == 0:
                            _说("填了背包（服务器 ✓）：%s" % json.dumps(新, ensure_ascii=False)[:120])
        except Exception as e:
            _说("填背包出岔子（出声 ✓）：%s" % str(e)[:70])
        return None

    叙类.看状态 = 看状态
    return True


def 装上(bridge, 日志=None, **kw):
    global _日志
    if 日志: _日志 = 日志
    叙 = getattr(bridge, "叙事者", None)
    叙类 = 叙 if isinstance(叙, type) else type(叙) if 叙 is not None else None
    if 叙类 is None:
        return {"好": False, "为什么": "找不到叙事者类", "打了": []}
    if getattr(叙类, "_服务器仲裁装了", False):
        return {"好": True, "为什么": "装过了（幂等 ✓）", "打了": []}
    好 = _装看状态(叙类)
    setattr(叙类, "_服务器仲裁装了", True)
    _说("上岗 ✓ 手不说背包时，我自己问服务器 ✓（一条长连接 ✓ 不抢手的活 ✗）")
    return {"好": bool(好), "为什么": "" if 好 else "叙事者.看状态 不是函数",
            "打了": ["叙事者.看状态() ← ① 回调原函数 ✓ ② 背包空/缺 ⇒ 问服务器填上 ✓（铁律②：拿服务器数据对照 ✓）"]}


def 卸下(bridge):
    叙 = getattr(bridge, "叙事者", None)
    叙类 = 叙 if isinstance(叙, type) else type(叙) if 叙 is not None else None
    if 叙类 is not None and id(叙类) in 原看:
        叙类.看状态 = 原看.pop(id(叙类))
        try: delattr(叙类, "_服务器仲裁装了")
        except Exception: pass
    return True


# ★ 2026-10-16：**缓存刷新线程** ✓（真问只在这里 ✗ 热路径永远不碰 socket ✓）
def _刷价():
    import time as _t
    while True:
        try:
            新 = 问背包()
            if 新:
                _价["背包"] = dict(新)
                _价["t"] = _t.time()
        except Exception as _e:
            _说("刷价出岔子（出声 ✓ 不致命 ✓）：%s" % str(_e)[:70])
        _t.sleep(5.0)


try:
    import threading as _thJ
    _thJ.Thread(target=_刷价, daemon=True, name="服务器仲裁刷价").start()
except Exception as _eJ:
    _说("刷价线程起不来（出声 ✓）：%s" % _eJ)
