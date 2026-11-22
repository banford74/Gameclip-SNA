/**
 * 通过 Chrome DevTools Protocol 批量抓抖音评论。
 *
 * 前置：浏览器带调试端口启动（见 _probe/start-browser-debug.cmd）。
 * 用法：node _probe/scrape_via_cdp.js <video_url> [输出目录]
 *
 * 流程：连接 -> 新建/复用标签页 -> 打开视频页 -> 注入抓取脚本（自动滚动加载）-> 收结果落盘。
 */
const fs = require('node:fs');
const path = require('node:path');

const CDP = process.env.CDP_URL || 'http://127.0.0.1:9222';
const TARGET_URL = process.argv[2];
const OUT_DIR = process.argv[3] || 'skilltest/comments';
if (!TARGET_URL) { console.error('usage: node scrape_via_cdp.js <video_url> [out_dir]'); process.exit(1); }

const SCRAPE = `(async () => {
  const S = (ms) => new Promise(r => setTimeout(r, ms));
  const SEL = '[data-e2e="comment-item"]';
  let last = 0; const all = [];
  for (let round = 0; round < 200; round++) {
    const nodes = [...document.querySelectorAll(SEL)];
    if (nodes.length > last) {
      for (let i = last; i < nodes.length; i++) {
        const t = (nodes[i].innerText || '').replace(/\\s+/g, ' ').trim();
        if (t) all.push(t);
      }
      last = nodes.length;
    } else if (round > 6) break;
    const a = nodes[nodes.length - 1];
    if (a) {
      let p = a.parentElement;
      while (p && p.scrollHeight <= p.clientHeight + 8) p = p.parentElement;
      if (p) p.scrollTop = p.scrollHeight; else a.scrollIntoView({ block: 'end' });
    }
    await S(650);
  }
  return JSON.stringify({ url: location.href, title: document.title, count: all.length, comments: all });
})()`;

async function cdpTargets() {
  const r = await fetch(CDP + '/json/list');
  return r.json();
}

function connect(wsUrl) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl);
    let id = 0;
    const pending = new Map();
    ws.onopen = () => resolve({
      send(method, params = {}, timeoutMs = 180000) {
        const msgId = ++id;
        ws.send(JSON.stringify({ id: msgId, method, params }));
        return new Promise((res, rej) => {
          pending.set(msgId, { res, rej });
          setTimeout(() => { if (pending.has(msgId)) { pending.delete(msgId); rej(new Error('cdp timeout: ' + method)); } }, timeoutMs);
        });
      },
      close() { ws.close(); },
    });
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.id && pending.has(msg.id)) {
        const { res, rej } = pending.get(msg.id);
        pending.delete(msg.id);
        msg.error ? rej(new Error(JSON.stringify(msg.error))) : res(msg.result);
      }
    };
    ws.onerror = (e) => reject(new Error('ws error'));
  });
}

(async () => {
  const targets = await cdpTargets();
  const page = targets.find(t => t.type === 'page');
  if (!page) throw new Error('没有可用的页面标签，请先在浏览器里打开一个窗口');
  const client = await connect(page.webSocketDebuggerUrl);

  await client.send('Page.enable');
  await client.send('Page.navigate', { url: TARGET_URL });
  await new Promise(r => setTimeout(r, 6000)); // 等首屏与评论区渲染

  const res = await client.send('Runtime.evaluate', {
    expression: SCRAPE,
    awaitPromise: true,
    returnByValue: true,
  }, 300000);

  const payload = JSON.parse(res.result.value);
  payload.scraped_at = new Date().toISOString();
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const idMatch = (payload.url || TARGET_URL).match(/\/video\/(\d+)/) || (payload.url || '').match(/modal_id=(\d+)/);
  const id = idMatch ? idMatch[1] : String(Date.now());
  const out = path.join(OUT_DIR, `raw_${id}.json`);
  fs.writeFileSync(out, JSON.stringify(payload, null, 2), 'utf8');
  console.log(`saved ${payload.count} comment blobs -> ${out}`);
  client.close();
})().catch(e => { console.error('FAILED:', e.message); process.exit(1); });
