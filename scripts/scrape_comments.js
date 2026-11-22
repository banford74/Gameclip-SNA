// 抖音评论全量抓取（CDP 网络拦截 + 滚动翻页 + 高赞优先）
// 用法: node _probe/scrape_comments_all.js <video_url> [out_dir] [maxComments=3000] [maxMinutes=8]
const fs = require('fs');
const path = require('path');
const CDP = 'http://127.0.0.1:9222';

const TARGET = process.argv[2];
const OUT = process.argv[3] || 'skilltest/comments';
const MAXC = Number(process.argv[4] || 3000);
const MAXMIN = Number(process.argv[5] || 8);

async function main() {
  const list = await (await fetch(CDP + '/json/list')).json();
  let page = list.find(t => t.type === 'page' && t.url.includes('douyin'));
  if (!page) {
    page = await (await fetch(CDP + '/json/new?' + encodeURIComponent(TARGET || 'https://www.douyin.com/'), { method: 'PUT' })).json();
  }
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise(r => (ws.onopen = r));
  let id = 0; const pending = new Map();
  const pages = [];
  let lastHasMore = true, lastCursor = '';

  ws.onmessage = async e => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { const { res } = pending.get(m.id); pending.delete(m.id); res(m.result); return; }
    if (m.method === 'Network.responseReceived') {
      const url = m.params.response.url || '';
      if (/comment\/list/.test(url)) {
        try {
          const r = await send('Network.getResponseBody', { requestId: m.params.requestId });
          const j = JSON.parse(r.body);
          const arr = j.comments || [];
          pages.push({ url: url.slice(0, 160), n: arr.length, has_more: j.has_more, cursor: j.cursor, comments: arr });
          lastHasMore = !!j.has_more;
          lastCursor = j.cursor;
          process.stdout.write(`\rpaginated: pages=${pages.length} comments=${pages.reduce((a, p) => a + p.n, 0)} has_more=${lastHasMore}`);
        } catch (err) { }
      }
    }
  };
  const send = (method, params = {}, timeoutMs = 120000) => new Promise((res, rej) => {
    const i = ++id; pending.set(i, { res });
    ws.send(JSON.stringify({ id: i, method, params }));
    setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('timeout ' + method)); } }, timeoutMs);
  });
  const ev = async expr => {
    const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    return r && r.result ? r.result.value : null;
  };

  await send('Network.enable');
  await send('Page.enable');
  await send('Page.navigate', { url: TARGET });
  await new Promise(r => setTimeout(r, 9000));

  const t0 = Date.now();
  let stale = 0; let lastCount = 0;
  for (let round = 0; round < 900; round++) {
    // 展开按钮（回复/更多）
    await ev(`(() => {
      for (const el of document.querySelectorAll('span,div,button')) {
        const t = (el.innerText || '').trim();
        if (t === '展开' || t === '查看更多' || t === '展开更多' || t === '加载更多' || t === '展开更多回复') {
          try { el.click(); } catch (e) {}
        }
      }
      const items = document.querySelectorAll('[data-e2e="comment-item"]');
      let el = items.length ? items[0].parentElement : null;
      let scrolled = false;
      while (el && el !== document.body) {
        if (el.scrollHeight > el.clientHeight + 40) {
          el.scrollTop = el.scrollHeight;
          el.dispatchEvent(new Event('scroll', { bubbles: true }));
          scrolled = true;
          break;
        }
        el = el.parentElement;
      }
      if (!scrolled) window.scrollTo(0, document.body.scrollHeight);
      return true;
    })()`);
    await new Promise(r => setTimeout(r, 1100));

    const total = pages.reduce((a, p) => a + p.n, 0);
    if (total > lastCount) { stale = 0; lastCount = total; } else stale++;
    if (lastHasMore === false) { console.log('\nreached has_more=0'); break; }
    if (total >= MAXC) { console.log('\nreached maxComments'); break; }
    if (stale >= 40) { console.log('\nstale 40 rounds'); break; }
    if (Date.now() - t0 > MAXMIN * 60 * 1000) { console.log('\ntime cap'); break; }
  }

  // 汇总去重 + 高赞排序
  const map = new Map();
  for (const p of pages) for (const c of p.comments) {
    const text = (c.text || '').trim();
    if (!text) continue;
    const key = c.cid || text;
    if (!map.has(key)) map.set(key, {
      cid: c.cid, text, digg: c.digg_count || 0, create_time: c.create_time,
      user: (c.user && (c.user.nickname || c.user.unique_id)) || '', reply_total: c.reply_comment_total || 0,
    });
  }
  const all = [...map.values()].sort((a, b) => b.digg - a.digg);
  const payload = {
    url: TARGET, pages: pages.length, total: all.length,
    has_more: lastHasMore, last_cursor: lastCursor,
    comments: all, scraped_at: new Date().toISOString(),
  };
  fs.mkdirSync(OUT, { recursive: true });
  const m = (TARGET || '').match(/\/video\/(\d+)/);
  const vid = m ? m[1] : String(Date.now());
  const f1 = path.join(OUT, `v3_all_${vid}.json`);
  fs.writeFileSync(f1, JSON.stringify(payload, null, 2), 'utf8');
  fs.writeFileSync(path.join(OUT, `v3_top500_${vid}.json`),
    JSON.stringify({ ...payload, comments: all.slice(0, 500) }, null, 2), 'utf8');
  console.log(`\nsaved ${all.length} comments (pages=${pages.length}, has_more=${lastHasMore}) -> ${f1}`);
  console.log('top5 by digg:', all.slice(0, 5).map(c => `[${c.digg}] ${c.text.slice(0, 30)}`).join(' | '));
  ws.close();
}
main().catch(e => { console.error('FAILED', e.message); process.exit(1); });
