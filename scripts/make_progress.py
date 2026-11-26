#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成进度汇总页 docs/progress.html。

数据来源（三选一，可叠加）：
  1) 拖入/选择各标注员导出的 human_labels*.csv
  2) 读取本浏览器 localStorage（如果和标注页同浏览器）
  3) ?data=<CSV URL>：定时拉取（例如 Google Sheet「发布到网络」的 CSV 链接）→ 自动刷新
页面内嵌：clip→game 映射 + 分工归属（来自 make_annotator 的同一套确定性分配）。
用法: python scripts/make_progress.py
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WS = ROOT.parent
CSV = ROOT / "data" / "clips.csv"
OUT = ROOT / "docs" / "progress.html"
N_ANNOTATORS = 4


def load_rows():
    rows = []
    with open(CSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append({"id": r["clip_id"], "game": r.get("game", ""),
                         "conf": r.get("pr_conf", ""), "p": r.get("pr_p", ""),
                         "status": r.get("review_status", "")})
    return rows


def is_hard(r: dict) -> bool:
    try:
        conf = float(r.get("conf") or 0)
    except ValueError:
        conf = 0.0
    return bool(r.get("status") == "pending_analysis" or not r.get("p") or conf < 0.6)


def assign(rows, n=N_ANNOTATORS):
    strata: dict = {}
    for r in rows:
        strata.setdefault((r["game"], is_hard(r)), []).append(r)
    counts = {i: 0 for i in range(1, n + 1)}
    out = []
    for key in sorted(strata):
        items = sorted(strata[key], key=lambda r: r["id"])
        for r in items:
            a = min(counts, key=lambda k: (counts[k], k))
            rec = dict(r)
            rec["a"] = a
            counts[a] += 1
            out.append(rec)
    return out, counts


def main():
    rows, counts = assign(load_rows())
    games = sorted({r["game"] for r in rows})
    data = {"n": N_ANNOTATORS, "counts": counts, "games": games,
            "rows": [[r["id"], r["game"], r["a"]] for r in rows]}
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    OUT.write_text(HTML_TMPL.replace("__DATA__", payload), encoding="utf-8")
    print(f"progress page written: {OUT} rows={len(rows)} counts={counts}")


HTML_TMPL = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gameclip-SNA · 标注进度汇总</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--line:#242936;--fg:#e6e6e6;--dim:#8b949e;--acc:#58a6ff;--ok:#7ee787;--warn:#d29922;--bad:#f85149}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--fg);margin:0;padding:16px}
h1{font-size:17px;margin:0 0 6px}
.sub{font-size:12px;color:var(--dim);margin-bottom:10px}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:10px 0}
.bar button,.bar input{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:5px 9px;font-size:12px;cursor:pointer}
.bar button.primary{border-color:var(--acc);color:var(--acc)}
.drop{border:2px dashed var(--line);border-radius:10px;padding:14px;text-align:center;color:var(--dim);font-size:12px;margin:8px 0}
.drop.on{border-color:var(--acc);color:var(--acc)}
.overall{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;margin:8px 0}
.overall .row{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:#c9d1d9;align-items:center}
.prog{height:10px;background:#22262f;border-radius:5px;overflow:hidden;margin:8px 0}
.prog i{display:block;height:100%;background:var(--ok)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px;margin-top:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}
.card h2{font-size:14px;margin:0 0 6px;display:flex;justify-content:space-between}
.card .p{height:8px;background:#22262f;border-radius:4px;overflow:hidden;margin:6px 0}
.card .p i{display:block;height:100%;background:var(--ok)}
.mini{font-size:11px;color:var(--dim);line-height:1.7}
.mini b{color:#c9d1d9}
.gbar{display:flex;height:8px;border-radius:4px;overflow:hidden;margin:4px 0}
.gbar i{display:block;height:100%}
.stance{display:flex;gap:10px;font-size:11px;color:var(--dim);flex-wrap:wrap}
table{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}
th,td{border-bottom:1px solid var(--line);padding:4px 6px;text-align:left}
th{color:var(--dim);font-weight:500}
.tag{font-size:10px;border-radius:4px;padding:1px 5px;background:#30363d;color:#8b949e}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}
.foot{margin-top:16px;color:var(--dim);font-size:11px;line-height:1.7}
a{color:var(--acc)}
</style></head><body>
<h1>Gameclip-SNA · 标注进度汇总</h1>
<div class="sub">共 2201 条 · 4 名标注员各约 550 条（按游戏×难度分层分配）。数据三路可选：拖入导出 CSV / 读本浏览器 / <code>?data=CSV链接</code> 自动刷新。</div>
<div class="bar">
  <button id="readLocal" class="primary">读取本浏览器标注</button>
  <label class="tag" style="padding:5px 9px;cursor:pointer">选择 CSV 文件<input id="files" type="file" accept=".csv" multiple style="display:none"></label>
  <input id="dataUrl" placeholder="?data=CSV 链接（如 Google Sheet 发布链接）" style="flex:1;min-width:260px">
  <button id="loadUrl">拉取并自动刷新</button>
  <button id="clear" class="tag" style="padding:5px 9px">清空</button>
</div>
<div class="drop" id="drop">把 4 个 human_labels*.csv 拖进来（或多选文件）</div>
<div class="overall" id="overall"></div>
<div id="cards" class="grid"></div>
<div id="detail"></div>
<div class="foot">
数据口径：每个 clip_id 取该标注员最近一次（annotated_at 最大）的标注；进度 = 该标注员名下已标注数 / 分到数。
若两人标注过同一条（重叠 ≥10 条）会显示 stance 一致性 Cohen's κ。
标注页入口：<a href="?a=1">标注员1</a> · <a href="?a=2">标注员2</a> · <a href="?a=3">标注员3</a> · <a href="?a=4">标注员4</a>
</div>
<script>
const DATA = __DATA__;
const ROW = new Map(DATA.rows.map(r => [r[0], {game: r[1], a: r[2]}]));
const GAMES = DATA.games;
const COLORS = ['#58a6ff','#7ee787','#d29922','#f85149','#bc8cff','#39c5cf','#ff7b72','#a5d6ff'];
const ST = ['positive','negative','neutral','mixed'];
const ST_CN = {positive:'正向', negative:'负向', neutral:'中性', mixed:'混合'};

let labels = new Map();   // key: annotator|clip_id -> record
let timer = null;

function parseCSV(text){
  const rows = []; let cur = [], field = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"') { if (text[i+1] === '"') { field += '"'; i++; } else q = false; } else field += c; }
    else if (c === '"') q = true;
    else if (c === ',') { cur.push(field); field = ''; }
    else if (c === '\n' || c === '\r') { if (field !== '' || cur.length) { cur.push(field); rows.push(cur); cur = []; field = ''; } }
    else field += c;
  }
  if (field !== '' || cur.length) { cur.push(field); rows.push(cur); }
  return rows;
}

function ingestText(text, src){
  const rows = parseCSV(text);
  if (!rows.length) return 0;
  const head = rows[0].map(x => x.trim());
  const idx = n => head.indexOf(n);
  let n = 0;
  for (let i = 1; i < rows.length; i++) {
    const r = rows[i];
    const cid = (r[idx('clip_id')] || '').trim();
    if (!cid) continue;
    const a = (r[idx('annotator')] || '').trim() || (ROW.get(cid) ? String(ROW.get(cid).a) : '?');
    const stance = (r[idx('stance')] || '').trim();
    if (!stance) continue;
    const at = (r[idx('annotated_at')] || '').trim();
    const key = a + '|' + cid;
    const prev = labels.get(key);
    if (prev && prev.at && at && prev.at > at) continue;
    labels.set(key, {a, cid, stance, at, src,
      p: (r[idx('p_codes')] || '').trim(), r: (r[idx('r_codes')] || '').trim(),
      item: ROW.get(cid) || null});
    n++;
  }
  render();
  return n;
}

function fromLocal(){
  let obj = {};
  try { obj = JSON.parse(localStorage.getItem('gameclip_labels_v1') || '{}'); } catch (e) { obj = {}; }
  let n = 0;
  for (const [cid, rec] of Object.entries(obj)) {
    if (!rec || !rec.stance) continue;
    const a = String(rec.annotator || (ROW.get(cid) ? ROW.get(cid).a : '?'));
    labels.set(a + '|' + cid, {a, cid, stance: rec.stance, at: rec.annotated_at || '', src: 'local',
      p: rec.p_codes || '', r: rec.r_codes || '', item: ROW.get(cid) || null});
    n++;
  }
  render();
  return n;
}

async function loadUrl(url){
  if (!url) return;
  try {
    const r = await fetch(url, {cache: 'no-store'});
    if (!r.ok) throw new Error('http ' + r.status);
    const text = await r.text();
    labels = new Map();                 // URL 模式以远端为准
    const n = ingestText(text, url);
    document.getElementById('drop').textContent = `已从 URL 载入 ${n} 条，每 20 秒自动刷新`;
    if (timer) clearInterval(timer);
    timer = setInterval(() => loadUrl(url), 20000);
  } catch (e) {
    document.getElementById('drop').textContent = '拉取失败：' + e.message;
  }
}

function annKeys(){
  const ks = Object.keys(DATA.counts).map(String);
  const extra = [...new Set([...labels.values()].map(v => v.a))].filter(a => !ks.includes(a));
  return ks.concat(extra.sort());
}

function render(){
  const byAnn = {};
  for (const k of annKeys()) byAnn[k] = {done: 0, games: {}, stance: {}};
  for (const v of labels.values()) {
    if (!byAnn[v.a]) byAnn[v.a] = {done: 0, games: {}, stance: {}};
    byAnn[v.a].done++;
    const g = v.item ? v.item.game : '?';
    byAnn[v.a].games[g] = (byAnn[v.a].games[g] || 0) + 1;
    byAnn[v.a].stance[v.stance] = (byAnn[v.a].stance[v.stance] || 0) + 1;
  }
  // 总览（只保留总进度 + 每人进度）
  const total = DATA.rows.length;
  const allDone = [...labels.values()].length;
  const per = Object.values(byAnn).reduce((a, b) => a + b.done, 0);
  let html = `<div class="row"><b>总进度：</b><span>${per} / ${total}（${(100*per/total).toFixed(1)}%）</span>
    <span class="tag">已收 ${allDone} 条标注记录</span>`;
  for (const a of Object.keys(DATA.counts)) {
    const st = byAnn[String(a)] || {done:0};
    html += `<span class="tag">标注员 ${a}: ${st.done}/${DATA.counts[a]}</span>`;
  }
  html += `</div><div class="prog"><i style="width:${(100*per/total).toFixed(1)}%"></i></div>`;
  document.getElementById('overall').innerHTML = html;

  // 每人卡片（完成数 / 分到数 / 最近更新 / stance 分布）
  const cards = document.getElementById('cards');
  cards.innerHTML = annKeys().map(a => {
    const st = byAnn[a] || {done: 0, games: {}, stance: {}};
    const assigned = DATA.counts[a] || st.done;
    const pct = (100 * st.done / Math.max(1, assigned)).toFixed(1);
    const stance = ST.map(s => `${ST_CN[s]} ${st.stance[s] || 0}`).join(' · ');
    return `<div class="card">
      <h2><span>标注员 ${a}</span><span class="${pct >= 100 ? 'ok' : 'warn'}">${pct}%</span></h2>
      <div class="p"><i style="width:${pct}%"></i></div>
      <div class="mini">完成 <b>${st.done}</b> / ${assigned} 条 · 最近更新：${lastAt(a)}</div>
      <div class="mini">stance：${stance || '—'}</div>
    </div>`;
  }).join('');

  // 同意度（重叠）
  const overlaps = {};
  const seen = new Map();  // cid -> [a...]
  for (const v of labels.values()) {
    if (!v.item) continue;
    if (!seen.has(v.cid)) seen.set(v.cid, []);
    seen.get(v.cid).push(v);
  }
  const pairs = {};
  for (const arr of seen.values()) {
    if (arr.length < 2) continue;
    for (let i = 0; i < arr.length; i++) for (let j = i + 1; j < arr.length; j++) {
      const key = [arr[i].a, arr[j].a].sort().join('-');
      (pairs[key] = pairs[key] || []).push([arr[i].stance, arr[j].stance]);
    }
  }
  const parts = Object.entries(pairs).filter(([, v]) => v.length >= 10);
  document.getElementById('detail').innerHTML = parts.length ? `<div class="overall"><b>重叠一致性（Cohen's κ）</b><table><tr><th>标注员对</th><th>重叠条数</th><th>一致率</th><th>κ</th></tr>` +
    parts.map(([k, v]) => { const kappa = cohenKappa(v); return `<tr><td>${k}</td><td>${v.length}</td><td>${(v.filter(([x, y]) => x === y).length / v.length * 100).toFixed(1)}%</td><td>${kappa.toFixed(3)}</td></tr>`; }).join('') + `</table></div>` : '';
}

function lastAt(a){
  let m = '';
  for (const v of labels.values()) if (v.a === a && v.at && v.at > m) m = v.at;
  return m ? m.slice(0, 16).replace('T', ' ') : '—';
}

function cohenKappa(pairs){
  const cats = ST;
  const n = pairs.length;
  let agree = 0;
  const p1 = {}, p2 = {};
  for (const [x, y] of pairs) { if (x === y) agree++; p1[x] = (p1[x]||0)+1; p2[y] = (p2[y]||0)+1; }
  const po = agree / n;
  let pe = 0;
  for (const c of cats) pe += ((p1[c]||0)/n) * ((p2[c]||0)/n);
  return pe === 1 ? 1 : (po - pe) / (1 - pe);
}

function readFiles(files){
  const list = [...files];
  let left = list.length, n = 0;
  if (!left) return;
  list.forEach(f => {
    const fr = new FileReader();
    fr.onload = () => {
      n += ingestText(fr.result, f.name);
      if (--left === 0) {
        document.getElementById('drop').textContent = `已导入 ${list.length} 个文件，共 ${n} 条标注`;
        render();
      }
    };
    fr.readAsText(f);
  });
}

document.getElementById('readLocal').addEventListener('click', () => {
  const n = fromLocal();
  document.getElementById('drop').textContent = `已从本浏览器读取 ${n} 条标注`;
});
document.getElementById('files').addEventListener('change', e => readFiles(e.target.files));
document.getElementById('drop').addEventListener('dragover', e => { e.preventDefault(); e.currentTarget.classList.add('on'); });
document.getElementById('drop').addEventListener('dragleave', e => e.currentTarget.classList.remove('on'));
document.getElementById('drop').addEventListener('drop', e => {
  e.preventDefault(); e.currentTarget.classList.remove('on');
  readFiles(e.dataTransfer.files);
});
document.getElementById('loadUrl').addEventListener('click', () => loadUrl(document.getElementById('dataUrl').value.trim()));
document.getElementById('clear').addEventListener('click', () => { labels = new Map(); render(); document.getElementById('drop').textContent = '已清空'; });
render();
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
