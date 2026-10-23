#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原子考题 —— 测「单个动作」的真实成功率（MCU-turbo 的两层基准里的 atomic 层 ✓）
用法：python3 tools/原子考题.py [每题跑几次，默认 3] [只跑某题]

纪律（施工规矩 ✓）：
  · 命令走**手侧 socket**（cyberdyne.sock ✓ 和文件口令同一条 ✓ 不依赖聊天 ✓）
  · 判定只认 **RCON（服务端）** ✓（STRIPS：完成=effect 成立 ✓）
  · 每道题：**干净前置**（清背包 ✓ 传到固定点 ✓）⇒ 一条命令 ⇒ 等效果 ⇒ 判定 ✓
  · 结果落 `进度/测量-<时间>.txt` ✓（含成功/总数 + 用时 ✓ 供方差 ✓）
"""
import json, os, re, socket, subprocess, sys, time

根 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
玩家 = 'DeepSeek'
env = {**os.environ, 'MC_RCON_PASSWORD': os.environ.get('MC_RCON_PASSWORD', 'cyberdyne'), 'LC_ALL': 'C.UTF-8'}


def rcon(c, 秒=12):
    try:
        r = subprocess.run(['python3', os.path.join(根, 'tools', 'rcon.py'), c],
                           capture_output=True, text=True, env=env, timeout=秒)
        return (r.stdout or '') + (r.stderr or '')
    except Exception as e:
        return '（rcon 超时/失败：%s）' % str(e)[:40]


def 数物(名):
    m = re.search(r'Found (\d+)', rcon('clear %s minecraft:%s 0' % (玩家, 名)))
    return int(m.group(1)) if m else -1


def 位置():
    o = rcon('data get entity %s Pos' % 玩家)
    m = re.search(r'\[([-0-9.]+)d, ([-0-9.]+)d, ([-0-9.]+)d', o)
    return [float(x) for x in m.groups()] if m else None


def 给物(名, 数=4):
    rcon('give %s minecraft:%s %d' % (玩家, 名, 数))
    time.sleep(0.6)


def 传(x, y, z):
    rcon('tp %s %d %d %d' % (玩家, x, y, z))
    rcon('effect give %s minecraft:slow_falling 8 1' % 玩家)
    time.sleep(1.2)


def 清包():
    rcon('clear %s' % 玩家)
    time.sleep(0.4)


def 发命令(令, 等=1.0):
    """走手侧 socket ✓ —— **保持连接 + 读回执** ✓✓
    ★ 2026-10-15 血证：原来"发完就 close"✗ ⇒ 手的回执（`回执(sock,…)` 回给发件人 ✓）**全丢** ✗
      而且手可能要求连接保持（脑就是长连 ✓）⇒ 结果：命令看着发出去了 ✓ 实际没人执行 ✗
    ⇒ 现在：连上 ⇒ 发 ⇒ **读 2 秒回执** ✓ ⇒ 有回执就打印出来（这是最硬的证据 ✓）
    """
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2.5)
        s.connect(os.path.join(根, 'cyberdyne.sock'))
        s.sendall((json.dumps(令, ensure_ascii=False) + '\n').encode())
        time.sleep(等)
        回 = []
        t0 = time.time()
        while time.time() - t0 < 2.5:
            try:
                b = s.recv(4096)
                if not b:
                    break
                回.append(b.decode('utf-8', 'replace'))
            except socket.timeout:
                break
            except Exception:
                break
        s.close()
        if 回:
            文 = ''.join(回)
            print('       ↳ 手回执:', 文.strip().replace('\n', ' ')[:150])
        return True
    except Exception as e:
        print('     ✗ 发命令失败:', str(e)[:60])
        return False


def 等条件(条, 秒=15.0, 每=0.6):
    t0 = time.time()
    while time.time() - t0 < 秒:
        try:
            if 条():
                return True, time.time() - t0
        except Exception:
            pass
        time.sleep(每)
    return False, time.time() - t0


# ─────────── 考题（每题：前置 / 做 / 判 ✓）───────────
基地 = (200, 100, 200)      # ★ 2026-10-15：改用**铺好的测试台** ✓（原来那点是个坑 ✗ 三次都掉进去 ✓）


def 题_走到():
    传(*基地)
    time.sleep(1.5)
    a = 位置()
    if not a:
        return False, 0.0, '拿不到位置'
    # ★ 2026-10-15 血证：目标 y 用**旧值** ⇒ 目标悬在头顶 ⇒ 寻路到不了 ⇒ 假失败 ✗
    #   （它 tp 后掉了几格 ✓ 而我还在用 tp 前的 y ✗）⇒ **发命令前重读一次位置** ✓
    a = 位置() or a
    目 = [a[0] + 4, a[1], a[2]]
    发命令({'cmd': 'goto', 'p': 目, 'near': 2})
    ok, dt = 等条件(lambda: (位置() or [9e9]*3)[0] > 基地[0] + 1.5, 20)
    return ok, dt, ('末位置 %s' % (位置(),))


def 题_挖到():        # 挖 + 自动捡
    传(*基地)
    清包()
    y = 基地[1]
    # 先在自己脚下放一块土（能挖、会掉、走上去就捡 ✓）
    给物('dirt', 2)
    发命令({'cmd': 'place', 'p': [基地[0], y - 1, 基地[2]], 'item': 'dirt'}, 1.2)
    time.sleep(1.0)
    发命令({'cmd': 'dig', 'p': [基地[0], y - 1, 基地[2]]})
    ok, dt = 等条件(lambda: 数物('dirt') >= 1, 18)
    return ok, dt, ('背包土 = %d' % 数物('dirt'))


def 题_捡():
    传(*基地)
    清包()
    给物('dirt', 2)
    发命令({'cmd': 'place', 'p': [基地[0] + 1, 基地[1] - 1, 基地[2]], 'item': 'dirt'}, 1.2)
    time.sleep(1.0)
    发命令({'cmd': 'dig', 'p': [基地[0] + 1, 基地[1] - 1, 基地[2]]})
    time.sleep(1.5)
    清包()          # 把刚捡的也清掉 ⇒ 逼它用 collect 自己去收 ✓（土已掉在地上 ✓）
    发命令({'cmd': 'collect', '物品': 'dirt', '数量': 1})
    ok, dt = 等条件(lambda: 数物('dirt') >= 1, 20)
    return ok, dt, ('collect 后背包土 = %d' % 数物('dirt'))


def 题_合成():
    传(*基地)
    清包()
    给物('oak_log', 2)
    time.sleep(0.8)
    发命令({'cmd': 'craft', 'item': 'oak_planks', 'count': 4})
    ok, dt = 等条件(lambda: 数物('oak_planks') >= 4, 15)
    return ok, dt, ('木板 = %d' % 数物('oak_planks'))


def 题_放方块():
    传(*基地)
    清包()
    给物('crafting_table', 1)
    time.sleep(0.8)
    n0 = 数物('crafting_table')
    # ★ 2026-10-15：原来往 y-1 放 ✗ ⇒ **没有支撑面** ⇒ 插件自己就报过
    #   「place 没做成：六面全是空的，没有可以靠着放的地方」✗ ⇒ 假失败 ✓
    #   改成：站在台面上，往**脚下那格**（台面顶 ✓ 有支撑 ✓）的旁边放 ✓
    发命令({'cmd': 'place', 'p': [基地[0] + 1, 基地[1], 基地[2]], 'item': 'crafting_table'})
    ok, dt = 等条件(lambda: 数物('crafting_table') == 0 and n0 >= 1, 15)
    return ok, dt, ('放前 %d / 放后 %d（手里没了=放下了 ✓）' % (n0, 数物('crafting_table')))


考题 = [('走到', 题_走到), ('挖到(含自动捡)', 题_挖到), ('捡(collect 能力)', 题_捡),
        ('合成(原木→木板)', 题_合成), ('放方块(工作台)', 题_放方块)]


def 跑(次=3, 只跑=None):
    出 = ['═══ 原子考题测量（每道 %d 次 ✓）═══' % 次, '时间：%s' % time.strftime('%Y-%m-%d %H:%M:%S'), '']
    print(出[0])
    总 = []
    for 名, 做 in 考题:
        if 只跑 and 只跑 not in 名:
            continue
        好 = 0; 时 = []
        for i in range(次):
            try:
                ok, dt, 详 = 做()
            except Exception as e:
                ok, dt, 详 = False, 0.0, '炸了：%s' % str(e)[:50]
            好 += 1 if ok else 0
            时.append(dt)
            行 = '  %-18s 第%d次 %s ｜ %.1f 秒 ｜ %s' % (名, i + 1, '✓成' if ok else '✗败', dt, 详[:70])
            print(行); 出.append(行)
            传(*基地)
        均 = sum(时) / len(时) if 时 else 0
        汇 = '  ★ %-18s 成功 %d/%d（%.0f%%）｜ 平均 %.1f 秒' % (名, 好, 次, 100.0 * 好 / max(次, 1), 均)
        print(汇); 出.append(汇); 出.append('')
        总.append((名, 好, 次))
    总汇 = ['═══ 总成绩 ═══']
    for 名, 好, 次 in 总:
        总汇.append('  %-18s %d/%d = %.0f%%' % (名, 好, 次, 100.0 * 好 / max(次, 1)))
    print('\n'.join(总汇)); 出 += 总汇
    p = os.path.join(根, '进度', '测量-%s.txt' % time.strftime('%Y%m%d-%H%M%S'))
    open(p, 'w', encoding='utf-8').write('\n'.join(出) + '\n')
    print('  ✓ 报告：%s' % p)
    return 出


if __name__ == '__main__':
    次 = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
    只 = sys.argv[2] if len(sys.argv) > 2 else None
    跑(次, 只)
