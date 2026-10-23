#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""体检全码 —— 把"老祖定的规矩 + 今晚踩过的坑"变成可扫的规则，一次扫全仓 ✓
规则来源：进度/考古报告-*.md（31 条心法）+ 进度/验收标准.md + 今晚的实机血证
用法：python3 tools/体检全码.py            # 扫全部
      python3 tools/体检全码.py 主链        # 只扫主链
"""
import os, re, sys, collections

根 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
跳过目录 = {'.git', 'node_modules', 'logs', '记忆', '进度', 'runtime', '__pycache__', 'jre', '备份', '.venv'}
扫的扩展 = ('.py', '.js')

# 规则：名字 / 正则 / 说明 / 老祖依据 / 严重度
规则 = [
    ("A1_重发打断", re.compile(r'停动作\(\)'), "每次重发都取消上一次动作 ⇒ 正反馈死循环", "Baritone（持有式执行器）", 3),
    ("A2_假卡住信号", re.compile(r'stuck_ms'), "stuck_ms 语义是'距上次卡住多久' ✗ 被当成'卡了多久'用", "Baritone（内部重算）", 3),
    ("A3_重下兜底", re.compile(r'重下|重发|resend'), "重发/重下的兜底间隔（要参数化 + 有下限）", "OMPL（预算）", 1),
    ("B1_原点兜底", re.compile(r'or\s*\[\s*0\s*,\s*0\s*,\s*0\s*\]'), "拿不到位置就假装世界原点 ⇒ 幽灵坐标家族", "tf2/SLAM", 3),
    ("B2_零值兜底", re.compile(r'or\s+0\b(?!\.)'), "数值兜底 0（可能是假值 ⇒ 下游算错）", "STRIPS（显式状态）", 1),
    ("C1_静默吞异常", re.compile(r'except[^\n:]*:\s*\n\s*pass'), "异常被静默吞掉 ⇒ 静默退化（项目自己说是头号敌人）", "Watchdog/监控层", 3),
    ("C2_JS_空catch", re.compile(r'catch\s*\([^)]*\)\s*\{\s*\}'), "JS 空 catch ⇒ 静默失败", "Watchdog/监控层", 2),
    ("D1_直接改类", re.compile(r'setattr\(\s*\w*类'), "直接 setattr 改别人的类 ⇒ 抢钩子家族", "Subsumption/ROS（只走消息）", 2),
    ("F1_坐标无年龄", re.compile(r'最后见'), "记忆点带'最后见' ⇒ 检查是否**使用前查年龄**（本规则只数出现次数）", "tf2（点+时间戳）", 2),
    ("G1_魔法时间", re.compile(r'\b(1500|2500|3000|5000|8000|10000|30000|60000|240)\b'), "硬编码毫秒/秒数 ⇒ 该参数化（Baritone 全是 Setting）", "Baritone（参数表）", 1),
    ("H1_自认坑", re.compile(r'TODO|FIXME|XXX|临时|先这样|凑合|以后再|回头再'), "代码里自认的未完成/临时", "Reflexion（反思闭环）", 1),
]

def 找文件(只):
    for 底, 目录们, 文件们 in os.walk(根):
        目录们[:] = [d for d in 目录们 if d not in 跳过目录]
        for 名 in 文件们:
            if not 名.endswith(扫的扩展): continue
            路 = os.path.join(底, 名)
            相对 = os.path.relpath(路, 根)
            if 只 and 只 not in 相对: continue
            yield 相对, 路

def main():
    只 = sys.argv[1] if len(sys.argv) > 1 else None
    计 = collections.defaultdict(list)
    文件数 = 0
    for 相对, 路 in 找文件(只):
        文件数 += 1
        try:
            文 = open(路, encoding='utf-8', errors='replace').read()
        except Exception:
            continue
        行们 = 文.splitlines()
        for 名, 正, 说, 依据, 级 in 规则:
            次 = len(正.findall(文))
            if 次:
                计[名].append((次, 相对, 说, 依据, 级))
    print('═══ 全码体检（扫了 %d 个文件 ✓）═══' % 文件数)
    print('规则来源：31 条老祖心法 + 今晚实机血证 ✓（每条的"依据"就是它为什么算病 ✓）\n')
    总 = []
    for 名, 列 in sorted(计.items(), key=lambda kv: -sum(x[0] for x in kv[1])):
        正 = 规则[[r[0] for r in 规则].index(名)]
        总次 = sum(x[0] for x in 列)
        print('★ %-14s 共 %-4d 处 ｜ 严重度 %s ｜ 依据：%s' % (名, 总次, '★' * 正[4], 正[3]))
        print('   病：%s' % 正[2])
        for 次, 相对, *_ in sorted(列, reverse=True)[:6]:
            print('      %-46s %d 处' % (相对, 次))
        print()
        总.append((正[4], 总次, 名))
    print('═══ 按严重度排（先修 ★★★）═══')
    for 级, 次, 名 in sorted(总, reverse=True):
        print('  %s %-14s %d 处' % ('★' * 级, 名, 次))

if __name__ == '__main__':
    main()
