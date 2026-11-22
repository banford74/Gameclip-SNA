#!/usr/bin/env node
/**
 * 抖音无登录下载（移动端 feed 接口法）——2026-11-20 实测可用
 *
 * 用法：
 *   node _probe/dl_mobile.js <video_id 或 页面URL 或 短链> [输出目录]
 *
 * 链路：aweme_id → feed 接口 → bit_rate 选最高档 → CDN 直链（带 Referer）→ 落盘
 * 要点：
 *   1) feed 会返回推荐位列表，必须按 aweme_id 精确匹配，禁止取 [0]
 *   2) 按 bit_rate 降序选档（play_addr.url_list[0] 常是低码率/水印档）
 *   3) 下载必须带 Referer: https://www.douyin.com/，否则 403
 *   4) url_list 有多个 CDN 域名，逐个重试
 */
const fs = require('node:fs');
const path = require('node:path');

const ANDROID_UA = 'com.ss.android.ugc.aweme/290100 (Linux; U; Android 13; zh_CN)';

async function resolveId(input) {
  if (/^\d{15,}$/.test(input)) return input;
  const m = input.match(/\/video\/(\d+)/) || input.match(/modal_id=(\d+)/) || input.match(/^(\d{15,})/);
  if (m) return m[1];
  // 短链：跟随跳转
  const r = await fetch(input, { headers: { 'User-Agent': ANDROID_UA }, redirect: 'follow' });
  const html = await r.text();
  const m2 = (r.url || '').match(/\/video\/(\d+)/) || html.match(/\/video\/(\d+)/);
  if (!m2) throw new Error('无法从短链解析 aweme_id: ' + r.url);
  return m2[1];
}

(async () => {
  const input = process.argv[2];
  const outDir = process.argv[3] || 'skilltest/downloads';
  if (!input) { console.error('usage: node _probe/dl_mobile.js <id|url> [out_dir]'); process.exit(1); }
  const id = await resolveId(input);
  console.log('[id]', id);

  const feed = `https://aweme.snssdk.com/aweme/v1/feed/?aweme_id=${id}&aid=1128&version_code=290100&device_platform=android&os_version=13`;
  const r = await fetch(feed, { headers: { 'User-Agent': ANDROID_UA } });
  const j = await r.json();
  const list = j.aweme_list || [];
  console.log(`[feed] http=${r.status} status_code=${j.status_code} list=${list.length}`);
  const a = list.find(x => String(x.aweme_id) === id);
  if (!a) throw new Error('feed 未命中目标 aweme_id（风控/删除/地区限制）');

  const v = a.video || {};
  const tiers = (v.bit_rate || [])
    .filter(t => (t.play_addr || {}).url_list)
    .sort((x, y) => (y.bit_rate || 0) - (x.bit_rate || 0));
  const pick = tiers[0] || { play_addr: v.play_addr || {}, bit_rate: 0 };
  const urls = (pick.play_addr || {}).url_list || [];
  console.log(`[pick] gear=${pick.gear_name || 'default'} ${pick.play_addr.width}x${pick.play_addr.height} ${Math.round((pick.bit_rate || 0) / 1000)}kbps urls=${urls.length}`);

  fs.mkdirSync(outDir, { recursive: true });
  const dest = path.join(outDir, `${id}.mp4`);
  for (const u of urls.slice(0, 4)) {
    try {
      const dr = await fetch(u, { headers: { 'User-Agent': ANDROID_UA, 'Referer': 'https://www.douyin.com/', 'Accept': '*/*' } });
      if (!dr.ok) { console.log(`  [skip] ${dr.status} ${u.slice(0, 60)}`); continue; }
      const buf = Buffer.from(await dr.arrayBuffer());
      if (buf.length < 100000) { console.log('  [skip] too small'); continue; }
      fs.writeFileSync(dest, buf);
      console.log(`[ok] ${dest} ${(buf.length / 1e6).toFixed(2)}MB`);
      const meta = {
        aweme_id: id, desc: a.desc || '', duration_s: ((v.duration || a.duration || 0) / 1000),
        author: (a.author || {}).nickname || '', music: (a.music || {}).title || '',
        width: pick.play_addr.width, height: pick.play_addr.height, gear: pick.gear_name || 'default',
        stats: {
          digg: (a.statistics || {}).digg_count, comment: (a.statistics || {}).comment_count,
          share: (a.statistics || {}).share_count, collect: (a.statistics || {}).collect_count,
        },
        downloaded_at: new Date().toISOString(),
      };
      fs.writeFileSync(path.join(outDir, `${id}.meta.json`), JSON.stringify(meta, null, 2));
      console.log('[meta]', JSON.stringify(meta));
      return;
    } catch (e) { console.log('  [err]', e.message, u.slice(0, 60)); }
  }
  throw new Error('所有 CDN 域名均失败');
})().catch(e => { console.error('FAILED:', e.message); process.exit(1); });
