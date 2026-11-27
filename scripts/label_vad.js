// 连续 VAD 标注（1-9）+ 与词典相关性评估
// 用法: node _probe/label_vad.js <comments_all.json> [out.json] [topN=300]
const fs = require('fs');

const SRC = process.argv[2];
const OUT = process.argv[3] || SRC.replace('.json', '_vad.json');
const TOPN = Number(process.argv[4] || 300);
const BATCH = 25;

// 密钥从环境变量读取（仓库里不存 key）：DEEPSEEK_API_KEY / ZAI_API_KEY
const RATERS = [
  { name: 'deepseek-flash', base: 'https://api.deepseek.com/v1', key: process.env.DEEPSEEK_API_KEY || '', model: 'deepseek-flash' },
  { name: 'glm-5.3-flashx', base: 'https://open.bigmodel.cn/api/paas/v4', key: process.env.ZAI_API_KEY || '', model: 'glm-5.3-flashx' },
];
for (const r of RATERS) {
  if (!r.key) { console.error(`[缺密钥] ${r.name} 需要环境变量：见脚本顶部注释`); process.exit(1); }
}

const SYS = `你是中文短视频评论情感评分员。对每条评论按 1-9 分打三个维度：
- valence（情感正负）：1=极负面 3=负面 5=中性 7=正面 9=极正面
- arousal（唤醒强度）：1=平静 5=中等 9=激烈（大笑/愤怒/震惊都算高唤醒）
- dominance（支配感）：1=无力/被动 5=中性 9=掌控/主导
反讽、阴阳怪气按真实意图判；梗/黑话按语境判。
只输出 JSON 数组，元素 {"i":序号,"v":1-9,"a":1-9,"d":1-9}，不要解释。`;

async function call(r, texts) {
  const user = texts.map((t, i) => `${i}. ${t.replace(/\n/g, ' ')}`).join('\n');
  const resp = await fetch(r.base + '/chat/completions', {
    method: 'POST', headers: { Authorization: 'Bearer ' + r.key, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: r.model, messages: [{ role: 'system', content: SYS }, { role: 'user', content: user }], max_tokens: 5000, temperature: 0 }),
    signal: AbortSignal.timeout(180000),
  });
  if (!resp.ok) throw new Error(`http ${resp.status}: ${(await resp.text()).slice(0, 120)}`);
  const j = await resp.json();
  const m = ((j.choices[0].message || {}).content || '').match(/\[[\s\S]*\]/);
  if (!m) throw new Error('no json');
  const arr = JSON.parse(m[0]);
  const out = texts.map(() => ({ v: 5, a: 5, d: 5 }));
  for (const o of arr) if (typeof o.i === 'number' && o.v) out[o.i] = { v: o.v, a: o.a, d: o.d };
  return out;
}

(async () => {
  const raw = JSON.parse(fs.readFileSync(SRC, 'utf8'));
  const list = (raw.comments || []).slice(0, TOPN);
  console.log('comments:', list.length);
  const scores = { deepseek: [], glm: [] };
  for (let s = 0; s < list.length; s += BATCH) {
    const batch = list.slice(s, s + BATCH);
    await Promise.all(RATERS.map(async r => {
      const out = await call(r, batch.map(c => c.text)).catch(e => { console.log(`[${r.name}] ${s} fail`, e.message); return batch.map(() => ({ v: 5, a: 5, d: 5 })); });
      (r.name === 'deepseek-flash' ? scores.deepseek : scores.glm).push(...out);
    }));
    process.stdout.write(`\r${Math.min(s + BATCH, list.length)}/${list.length}`);
  }
  console.log();
  const rows = list.map((c, i) => {
    const a = scores.deepseek[i], b = scores.glm[i];
    return {
      text: c.text, digg: c.digg,
      vad: { v: (a.v + b.v) / 2, a: (a.a + b.a) / 2, d: (a.d + b.d) / 2 },
      by_rater: { deepseek: a, glm: b },
    };
  });
  fs.writeFileSync(OUT, JSON.stringify({ source: SRC, top_n: rows.length, rows, labeled_at: new Date().toISOString() }, null, 2), 'utf8');
  console.log('saved', OUT);
})();
