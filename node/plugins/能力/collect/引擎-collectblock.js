/* 收东西 —— 引擎：mineflayer-collectblock（MIT ✓）
 *
 * ★ 主人 2026-10-09：「编译成我们现在这种架构，**可以多路也可以替换**
 *   （**开关其中一个就行**的那种）」✓
 *   所以这一节是「**能力** collect」✓ 它下面可以挂好几个**引擎** ✓
 *   用哪个写在 config 的 `引擎` 字段里 ✓ —— 换引擎、关掉，都不用改一行代码 ✓
 *
 * 它干的活：`{cmd:"collect", 物品:"oak_log", 数量:3}`
 *   自己找最近的 → 走过去 → 挖掉 → 把掉落物捡进包 → 直到够数或找不到了
 *   （不是"挖一步、拾一步、走一步"拼的 ✗ —— 那是我们今天反复坏掉的那条链 ✗）
 */
'use strict';

let 日志 = () => {};
const 名字 = 'collectblock';
let 可用 = false;
let 装的原因 = '还没试';

// ★ 2026-10-17 插桩（只加痕迹，不改逻辑 ✓）
//   病：命令每秒到 ✓ 引擎挂上了 ✓ 背包空 ✗ 而手侧日志**一行执行痕迹都没有** ✗
//   要看见：① 进来几次（并发？）② 找到几块、距离多远 ③ collect 返回/抛错 ④ 花了多久 ⑤ 背包前后
let 单号 = 0;
let 在做 = 0;
let 在飞 = null;       // 当前那一单：{物品, 要, 单, 承诺, 果} —— 后来的排队等它，不取消 ✓

function 装(bot, log) {
  日志 = log || (() => {});
  try {
    const 包 = require('mineflayer-collectblock');
    bot.loadPlugin(包.plugin);
    可用 = true;
    装的原因 = '装上了 ✓';
    日志(`  [collect] 引擎 collectblock 挂上了 ✓（MIT ✓ 自己会走位+挖+捡 ✓）`);
    return true;
  } catch (e) {
    可用 = false;
    // ★ 开着的引擎装不上 → **必须出声** ✗（静默退化是头号敌人 ✗）
    装的原因 = `装不上：${e && (e.code || e.message)}`;
    日志(`  ★ [collect] 引擎 collectblock **装不上** ✗ —— ${装的原因}`);
    return false;
  }
}

function 能用() { return 可用; }

/* 找最近的同名**方块**（找不到就给个能看懂的理由 ✓ 不许"就是没找到"✗）
 * ★ 2026-10-17 P0-2：参数是**方块名**（前置条件），不是掉落物名（效果）✓
 *   实机：stone 挖掉掉 cobblestone；拿 cobblestone 去 blocksByName 找方块 ⇒ 找不到 ✗
 */
function 找一块(bot, 方块名) {
  let 数据 = null;
  try { 数据 = require('minecraft-data')(bot.version); } catch (e) { 数据 = null; }
  const 定 = 数据 && 数据.blocksByName && 数据.blocksByName[方块名];
  if (!定) return { 块: null, 为什么: `我不认识「${方块名}」这种方块` };
  let 块 = null;
  try { 块 = bot.findBlock({ matching: 定.id, maxDistance: 48 }); } catch (e) { 块 = null; }
  if (!块) return { 块: null, 为什么: `48 格内我没看到「${方块名}」这种方块` };
  return { 块, 为什么: null };
}

/* 插桩用：背包里这个东西现在有几个（读不到报 -1 ✓ 不假装 0 ✗） */
function 背包数(bot, 物品) {
  try {
    let n = 0;
    for (const it of bot.inventory.items()) if (it.name === 物品) n += it.count;
    return n;
  } catch (e) { return -1; }
}

async function 执行(bot, a) {
  const 物品 = String(a.物品 || a.item || '');
  // ★ 2026-10-17 P0-2：`方块` = 要挖的方块（前置条件）；`物品` = 掉落物（效果/判据）✓
  //   老命令没带 `方块` ⇒ 默认跟 `物品` 同名（oak_log→oak_log 不受影响 ✓）
  const 方块 = String(a.方块 || a.block || a.物品 || a.item || '');
  const 要 = Math.max(1, parseInt(a.数量 || a.count || 1, 10) || 1);
  const 单 = ++单号;
  const 起点 = Date.now();
  日志(`  [collect#${单}] 进来：物品=${物品 || '(空)'} 方块=${方块 || '(空)'} 数量=${要} ｜ 同时在跑=${在做}`);
  if (!物品) {
    日志(`  [collect#${单}] 拒：没给物品名 ✗`);
    return { ok: false, why: '要给我一个物品名（物品:"oak_log"）' };
  }
  if (!可用) {
    日志(`  [collect#${单}] 拒：引擎没装上（${装的原因}）✗`);
    return { ok: false, why: `collect 引擎没装上（${装的原因}）` };
  }
  const 引擎 = bot.collectBlock;
  if (!引擎 || typeof 引擎.collect !== 'function') {
    日志(`  [collect#${单}] 拒：collectBlock 不在 bot 上 ✗`);
    return { ok: false, why: 'collectBlock 不在 bot 上（插件没挂成功 ✗）' };
  }

  /* ★★★ 2026-10-17【实机铁证 ✓ 这一刀的主刀】
   *   病：脑每 ~800ms 重发一条 collect ✓ 而 collectblock 的 collect() 默认 append:false
   *     ⇒ **每条新命令第一件事就是 cancelTask()** ⇒ 上一单的 pathfinder 被停
   *     ⇒ 实机插桩：同时在跑 **4** ✓ 8 发里 7 发被打断（GoalChanged / Digging aborted）
   *       ✓ 只有最后一发（没人打断）3.7 秒真收到 1 个 ✗ 前面的全白跑 ✓
   *     更坏：被 PathStopped 取消的那一单 collect() **正常返回** ⇒ 旧代码 `收 += 1`
   *       ⇒ **回执 ok:true 而背包 0→0** ✗（假成功 ✓ 脑以为成了 ✓）
   *   修（老祖句 1/4/7）：
   *     ① **后来的等前面那一单**（不取消 ✓ 不重开 ✓）
   *     ② 一模一样的（物品+数量）**直接复用结果** ✓（重发 = 幂等 ✓）
   *     ③ 收数**只认背包真增长** ✓（引擎说完成不算 ✓ 回执不许骗人 ✓）
   */
  while (在飞) {
    const 前 = 在飞;
    // ★ 等待要有上限（老祖句 9 ✓）：一单卡死不许把后面所有 collect 永久堵住 ✗
    //   超过 120 秒就不等它了 ⇒ 让新单接手（collectblock 的 append:false 会取消旧单 ✓）
    if (前.起点 && Date.now() - 前.起点 > 120000) {
      日志(`  [collect#${单}] #${前.单} 已经跑了 ${Math.round((Date.now() - 前.起点) / 1000)} 秒还没完 ⇒ 不再等它（新单接手 ✓）`);
      if (在飞 === 前) 在飞 = null;
      break;
    }
    日志(`  [collect#${单}] 前面有 #${前.单}「${前.物品}」×${前.要} 在跑 ⇒ 排队等它（不打断 ✓）`);
    try { await 前.承诺; } catch (e) { /* 它的错它自己报 ✓ */ }
    if (前.果 && 前.物品 === 物品 && 前.要 === 要) {
      日志(`  [collect#${单}] 跟 #${前.单} 是同一件事 ⇒ 复用结果 ✓（收 ${前.果.收}）`);
      return Object.assign({}, 前.果, { 合并: true });
    }
  }

  const 本 = { 物品, 方块, 要, 单, 果: null, 承诺: null, 起点 };
  本.承诺 = (async () => {
    const 果 = await 真做(bot, 物品, 方块, 要, 单, 起点);
    本.果 = 果;
    return 果;
  })();
  在飞 = 本;
  try {
    return await 本.承诺;
  } finally {
    if (在飞 === 本) 在飞 = null;
  }
}

async function 真做(bot, 物品, 方块, 要, 单, 起点) {
  const 引擎 = bot.collectBlock;
  在做 += 1;
  try {
    let 收 = 0;
    let 上次没多 = null;
    const 上限 = Math.min(24, 要 * 4);          // 防死循环：找一块失败也算一次 ✓
    for (let i = 0; i < 上限 && 收 < 要; i++) {
      const { 块, 为什么 } = 找一块(bot, 方块);
      if (!块) {
        日志(`  [collect#${单}] 找不到（第 ${i + 1} 次）：${为什么}`);
        return { ok: 收 >= 要, 收, why: 为什么, 数量: 收, 物品, 方块 };
      }
      let 距 = -1;
      try { 距 = bot.entity.position.distanceTo(块.position); } catch (e) { 距 = -1; }
      日志(`  [collect#${单}] 找到「${方块}」@${块.position} 距 ${距.toFixed(2)} 格（掉落物「${物品}」）`);
      const 前 = 背包数(bot, 物品);
      const 刻 = Date.now();
      try {
        日志(`  [collect#${单}] 开始 collect（第 ${i + 1}/${上限} 次）…`);
        await 引擎.collect(块, { ignoreNoPath: true });
        const 后 = 背包数(bot, 物品);
        const 增 = (前 >= 0 && 后 >= 0) ? (后 - 前) : 0;
        日志(`  [collect#${单}] collect 返回 ✓ 用了 ${Date.now() - 刻}ms ｜ 背包 ${前}→${后}（增 ${增}）`);
        if (增 > 0) {
          收 += 增;
        } else {
          上次没多 = (前 < 0 || 后 < 0)
            ? '读不到背包，不能算收 ✓'
            : '引擎说完成了，可背包没多 ✗（不能算收 ✓）';
          日志(`  [collect#${单}] ★ ${上次没多}`);
        }
      } catch (e) {
        // ★ 2026-10-17【实机抓到的假失败 ✓】：寻路超时可能发生在**已经挖到并捡起之后**
        //   实机：抛 `Took to long to decide path to goal!` 而背包已经 0→1 ✗
        //   规矩（老祖句 1）：**只看世界事实** ✓ —— 抛错也要先量背包，再看要不要报失败 ✓
        const 后 = 背包数(bot, 物品);
        const 增 = (前 >= 0 && 后 >= 0) ? (后 - 前) : 0;
        日志(`  [collect#${单}] collect 抛错（${Date.now() - 刻}ms）：${e && (e.name || '')} ${e && e.message} ｜ 背包 ${前}→${后}（增 ${增}）`);
        if (增 > 0) {
          收 += 增;
          if (收 >= 要) {
            日志(`  [collect#${单}] ★ 引擎抛错了，可背包真多了 ⇒ 按事实算成 ✓（不报假失败 ✗）`);
            return { ok: true, 收, 数量: 收, 物品, 备注: '引擎抛错但背包已增 ✓' };
          }
        }
        // ★ 收不到就**如实报** ✗ —— 不许当成收够了 ✓
        return { ok: false, 收, why: `收「${物品}」的时候断了：${e && e.message}`, 数量: 收, 物品 };
      }
    }
    if (收 < 要) {
      return { ok: false, 收, 数量: 收,
               why: 上次没多 || `只收到 ${收} 个「${物品}」，要 ${要} 个（找不到了）`, 物品 };
    }
    return { ok: true, 收, 数量: 收, 物品 };
  } finally {
    在做 -= 1;
    日志(`  [collect#${单}] 出去：共 ${Date.now() - 起点}ms ｜ 同时在跑=${在做}`);
  }
}

module.exports = { 名字, 装, 能用, 执行, 命令: ['collect'] };
