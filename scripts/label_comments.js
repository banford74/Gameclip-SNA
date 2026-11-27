// 三 rater 评论情感标注（deepseek-flash / glm-5.3-flashx / qwen3.8-27b），输出 majority + κ
// 用法: node _probe/label_comments3.js skilltest/comments/v3_net_7709870849365478116.json [out.json]
const fs = require('fs');

const SRC = process.argv[2];
const OUT = process.argv[3] || SRC.replace('.json', '_labeled.json');
const BATCH = 25;

// 密钥从环境变量读取（仓库里不存 key）：DEEPSEEK_API_KEY / ZAI_API_KEY / CUHKSZ_API_KEY
const RATERS = [
  { name: 'deepseek-flash', base: 'https://api.deepseek.com/v1', key: process.env.DEEPSEEK_API_KEY || '', model: 'deepseek-flash' },
  { name: 'glm-5.3-flashx', base: 'https://open.bigmodel.cn/api/paas/v4', key: process.env.ZAI_API_KEY || '', model: 'glm-5.3-flashx' },
  { name: 'qwen3.8-27b', base: 'http://10.27.130.10:32788/v1', key: process.env.CUHKSZ_API_KEY || '', model: 'qwen3.8-27b' },
];
for (const r of RATERS) {
  if (!r.key) { console.error(`[缺密钥] ${r.name} 需要环境变量：见脚本顶部注释`); process.exit(1); }
}

const SYS = `你是中文短视频评论情感标注员。对每条评论判断情感倾向：
pos（正面/认可/期待）/ neg（负面/吐槽/不满）/ neu（中性/无感/纯信息）。
评论不做 mixed——正负并存的评论也必须在三种中选主导倾向；不存在 mixed 标签。
反讽、阴阳怪气按真实意图判（如「笑死，这也叫测评？」= neg）。
只输出 JSON 数组，与输入顺序一一对应，元素为 {"i":序号,"label":"pos|neg|neu"}，不要解释。`;

async function call(r, texts) {
  const user = texts.map((t, i) => `${i}. ${t.replace(/\n/g, ' ')}`).join('\n');
  const body = { model: r.model, messages: [{ role: 'system', content: SYS }, { role: 'user', content: user }], max_tokens: 4000, temperature: 0 };
  const resp = await fetch(r.base + '/chat/completions', {
    method: 'POST', headers: { Authorization: 'Bearer ' + r.key, 'Content-Type': 'application/json' },
    body: JSON.stringify(body), signal: AbortSignal.timeout(180000),
  });
  if (!resp.ok) throw new Error(`http ${resp.status}: ${(await resp.text()).slice(0, 120)}`);
  const j = await resp.json();
  const text = (j.choices[0].message || {}).content || '';
  const m = text.match(/\[[\s\S]*\]/);
  if (!m) throw new Error('no json: ' + text.slice(0, 100));
  const arr = JSON.parse(m[0]);
  const out = new Array(texts.length).fill('neu');
  for (const o of arr) if (typeof o.i === 'number' && o.label) out[o.i] = o.label;
  return out;
}

function kappa(labelsByRater) {
  // Fleiss kappa（3 类：评论无 mixed）
  const n = labelsByRater[0].length, R = labelsByRater.length;
  const cats = ['pos', 'neg', 'neu'];
  let agree = 0, total = 0;
  const pj = Object.fromEntries(cats.map(c => [c, 0]));
  for (let i = 0; i < n; i++) {
    const cnt = {};
    for (const lab of labelsByRater) { const v = lab[i]; cnt[v] = (cnt[v] || 0) + 1; pj[v] = (pj[v] || 0) + 1; }
    let s = 0; for (const k in cnt) s += cnt[k] * (cnt[k] - 1);
    agree += s / (R * (R - 1)); total++;
  }
  const Pbar = agree / total;
  const Pe = cats.reduce((acc, c) => acc + (pj[c] / (total * R)) ** 2, 0);
  return (Pbar - Pe) / (1 - Pe);
}

(async () => {
  const raw = JSON.parse(fs.readFileSync(SRC, 'utf8'));
  const items = (raw.comments || []).map(c => (typeof c === 'string' ? c : c.text));
  console.log('comments:', items.length);
  const labels = Object.fromEntries(RATERS.map(r => [r.name, []]));
  for (let start = 0; start < items.length; start += BATCH) {
    const batch = items.slice(start, start + BATCH);
    await Promise.all(RATERS.map(async r => {
      const out = await call(r, batch).catch(e => { console.log(`[${r.name}] batch ${start} fail:`, e.message); return new Array(batch.length).fill('neu'); });
      labels[r.name].push(...out);
    }));
    process.stdout.write(`\rlabeled ${Math.min(start + BATCH, items.length)}/${items.length}`);
  }
  console.log();
  const names = RATERS.map(r => r.name);
  const rows = items.map((t, i) => {
    const votes = names.map(n => labels[n][i]);
    const cnt = {};
    for (const v of votes) cnt[v] = (cnt[v] || 0) + 1;
    const maj = Object.entries(cnt).sort((a, b) => b[1] - a[1])[0][0];
    return { text: t, votes: Object.fromEntries(names.map((n, k) => [n, votes[k]])), majority: maj };
  });
  const dist = {};
  for (const r of rows) dist[r.majority] = (dist[r.majority] || 0) + 1;
  const total = rows.length;
  const k = kappa(names.map(n => labels[n]));
  const payload = {
    source: SRC, raters: names, n: total,
    kappa: Number(k.toFixed(4)),
    distribution: Object.fromEntries(Object.entries(dist).map(([a, b]) => [a, Number((b / total).toFixed(4))])),
    net: Number(((dist.pos || 0) - (dist.neg || 0)) / total).toFixed(4),
    rows,
    labeled_at: new Date().toISOString(),
  };
  fs.writeFileSync(OUT, JSON.stringify(payload, null, 2), 'utf8');
  console.log('saved', OUT, '| kappa', k.toFixed(3), '| dist', payload.distribution, '| net', payload.net);
})().catch(e => { console.error('FAILED', e.message); process.exit(1); });
