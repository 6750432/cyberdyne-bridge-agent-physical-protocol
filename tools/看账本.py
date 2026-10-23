#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看账本 —— 带**新鲜度**地读账本（治"读残留当结论"✗ 主人 2026-10-14 验收标准第 1 条 ✓）
用法：python3 tools/看账本.py 任务 收集 回执      # 看这几个账本最后几条 + 文件多旧
"""
import json, os, sys, time
根 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for 名 in (sys.argv[1:] or ['任务']):
    for 路 in (os.path.join(根,'logs',名+'.jsonl'), os.path.join(根,'logs',名)):
        if os.path.exists(路):
            age = time.time() - os.path.getmtime(路)
            旗 = '★新鲜' if age < 60 else ('⚠旧' if age < 600 else '✗很旧(别当结论)')
            print('── %s ｜ %d 字节 ｜ %s前 ｜ %s' % (名, os.path.getsize(路), ('%.0f秒'%age) if age<3600 else ('%.1f小时'%(age/3600)), 旗))
            try:
                for l in open(路, encoding='utf-8', errors='replace').readlines()[-5:]:
                    print('   ', l.strip()[:150])
            except Exception as e:
                print('    （读不出：%s）' % e)
            break
    else:
        print('── %s ｜ ✗ **文件不存在**（先确认它真会被写 ✓ 别拿它当证据 ✗）' % 名)
