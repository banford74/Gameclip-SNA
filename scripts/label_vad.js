// 连续 VAD 标注（1-9）+ 与词典相关性评估
// 用法: node scripts/label_vad.js <comments_all.json> [out.json] [topN=300]
const fs = require('fs');

const SRC = process.argv[2];
const OUT = process.argv[3] || SRC.replace('.json', '_vad.json');
const TOPN = Number(process.argv[4] || 300);
const BATCH = 25;

// 密钥从环境变量读取（仓库里不存 key）：OPENCODE_API_KEY
// 端点统一走 OpenCode Go，默认模型 deepseek-v4.1-flash（x-opencode-session 由 llm_endpoints 自动带）
const { endpoint, chatJSON } = require('./llm_endpoints');
const RATERS = [
  endpoint('deepseek-v4.1-flash'),
  endpoint('kimi-k3.1-pro'),
];

const SYS = `你是中文短视频评论情感评分员。对每条评论按 1-9 分打三个维度：
- valence（情感正负）：1=极负面 3=负面 5=中性 7=正面 9=极正面
- arousal（唤醒强度）：1=平静 5=中等 9=激烈（大笑/愤怒/震惊都算高唤醒）
- dominance（支配感）：1=无力/被动 5=中性 9=掌控/主导
反讽、阴阳怪气按真实意图判；梗/黑话按语境判。
只输出 JSON 数组，元素 {"i":序号,"v":1-9,"a":1-9,"d":1-9}，不要解释。`;

async function call(r, texts) {
  const user = texts.map((t, i) => `${i}. ${t.replace(/\n/g, ' ')}`).join('\n');
  const j = await chatJSON(r, {
    messages: [{ role: 'system', content: SYS }, { role: 'user', content: user }],
    max_tokens: 5000, temperature: 0,
  });
  const m = ((j.choices[0].message || {}).content || '').match(/\[[\s\S]*\]/);
  if (!m) throw new Error('no json');
  const arr = JSON.parse(m[0]);
  const out = texts.map(() => ({ v: 5, a: 5, d: 5 }));
  for (const o of arr) if (typeof o.i === 'number' && o.v) out[o.i] = { v: o.v, a: o.a, d: o.d };
  return out;
}

(async () => {
  const raw = JSON.parse(fs.readFileSync(SRC, 'utf8'));
  const list = (raw.comments || []).map(c => (typeof c === 'string' ? { text: c } : c)).slice(0, TOPN);
  console.log('comments:', list.length);
  const scores = Object.fromEntries(RATERS.map(r => [r.name, []]));
  for (let s = 0; s < list.length; s += BATCH) {
    const batch = list.slice(s, s + BATCH);
    await Promise.all(RATERS.map(async r => {
      const out = await call(r, batch.map(c => c.text)).catch(e => { console.log(`[${r.name}] ${s} fail`, e.message); return batch.map(() => ({ v: 5, a: 5, d: 5 })); });
      scores[r.name].push(...out);
    }));
    process.stdout.write(`\r${Math.min(s + BATCH, list.length)}/${list.length}`);
  }
  console.log();
  const names = RATERS.map(r => r.name);
  const rows = list.map((c, i) => {
    const per = names.map(n => scores[n][i]);
    const avg = k => per.reduce((acc, o) => acc + o[k], 0) / per.length;
    return {
      text: c.text, digg: c.digg,
      vad: { v: avg('v'), a: avg('a'), d: avg('d') },
      by_rater: Object.fromEntries(names.map((n, j) => [n, per[j]])),
    };
  });
  fs.writeFileSync(OUT, JSON.stringify({ source: SRC, top_n: rows.length, rows, labeled_at: new Date().toISOString() }, null, 2), 'utf8');
  console.log('saved', OUT);
})();
