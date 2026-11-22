// 增强版抖音评论抓取：滚动容器探测 + 展开按钮 + 虚拟列表累积
// 用法: node _probe/scrape_cdp2.js <video_url> [out_dir]
const fs = require('fs');
const path = require('path');
const CDP = 'http://127.0.0.1:9222';

const TARGET = process.argv[2];
const OUT = process.argv[3] || 'skilltest/comments';

const SCRAPE = `(async () => {
  const S = ms => new Promise(r => setTimeout(r, ms));
  const seen = new Set();
  const comments = [];
  let noGrowth = 0;

  function collect() {
    const nodes = [...document.querySelectorAll('[data-e2e="comment-item"]')];
    let added = 0;
    for (const n of nodes) {
      const t = (n.innerText || '').replace(/\\s+/g, ' ').trim();
      if (t && !seen.has(t)) { seen.add(t); comments.push(t); added++; }
    }
    return added;
  }

  function findScroller() {
    const items = document.querySelectorAll('[data-e2e="comment-item"]');
    if (!items.length) return null;
    let el = items[0].parentElement;
    while (el && el !== document.body) {
      if (el.scrollHeight > el.clientHeight + 50) return el;
      el = el.parentElement;
    }
    return null;
  }

  for (let round = 0; round < 160; round++) {
    // 点“展开/查看更多”
    for (const el of document.querySelectorAll('span,div,button')) {
      const t = (el.innerText || '').trim();
      if (t === '展开' || t === '查看更多' || t === '展开更多' || t === '加载更多' || t === '展开更多回复') {
        try { el.click(); } catch (e) {}
      }
    }
    const added = collect();
    noGrowth = added ? 0 : noGrowth + 1;
    const sc = findScroller();
    if (sc) {
      sc.scrollTop = sc.scrollHeight;
      sc.dispatchEvent(new Event('scroll', { bubbles: true }));
    } else {
      window.scrollTo(0, document.body.scrollHeight);
    }
    if (noGrowth >= 20) break;
    await S(700);
  }
  return JSON.stringify({ url: location.href, title: document.title, count: comments.length, comments });
})()`;

async function main() {
  const list = await (await fetch(CDP + '/json/list')).json();
  const page = list.find(t => t.type === 'page' && t.url.includes('douyin'));
  if (!page) throw new Error('no douyin tab');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise(r => (ws.onopen = r));
  let id = 0; const pending = new Map();
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { const { res } = pending.get(m.id); pending.delete(m.id); res(m.result); }
  };
  const send = (method, params = {}, timeoutMs = 300000) => new Promise((res, rej) => {
    const i = ++id; pending.set(i, { res });
    ws.send(JSON.stringify({ id: i, method, params }));
    setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('timeout ' + method)); } }, timeoutMs);
  });
  if (TARGET) {
    await send('Page.enable');
    await send('Page.navigate', { url: TARGET });
    await new Promise(r => setTimeout(r, 8000));
  }
  const r = await send('Runtime.evaluate', { expression: SCRAPE, awaitPromise: true, returnByValue: true });
  const payload = JSON.parse(r.result.value);
  payload.scraped_at = new Date().toISOString();
  fs.mkdirSync(OUT, { recursive: true });
  const m = (payload.url || TARGET || '').match(/\/video\/(\d+)/);
  const id_ = m ? m[1] : String(Date.now());
  const out = path.join(OUT, `raw_v3_${id_}.json`);
  fs.writeFileSync(out, JSON.stringify(payload, null, 2), 'utf8');
  console.log(`saved ${payload.count} comments -> ${out}`);
  ws.close();
}
main().catch(e => { console.error('FAILED', e.message); process.exit(1); });
