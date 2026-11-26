#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成在线标注工作台（docs/index.html）：

- 从 data/clips.csv + portfolio/src/codebook.json 生成单文件页面（数据内嵌，无需后端）
- 人工逐条点击标注：内容四分类 + 强度 + P 码(20) + R 码(96) + 证据 + 置信 + 备注
- 标注自动存浏览器 localStorage（刷新不丢），可导出 human_labels.csv / 再导入续标
- 顶部：进度、筛选（游戏/未标/已标/低置信/无P码）、分页
用法: python Gameclip-SNA/scripts/make_annotator.py
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # Gameclip-SNA
WS = ROOT.parent                                        # workspace
CSV = ROOT / "data" / "clips.csv"
CODEBOOK = WS / "portfolio" / "src" / "codebook.json"
OUT = ROOT / "docs" / "index.html"


def load_rows():
    rows = []
    with open(CSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append({
                "id": r["clip_id"], "game": r.get("game", ""), "fmt": r.get("format", ""),
                "prev": r.get("preview_url", ""), "kf": r.get("keyframe_url", ""),
                "src": r.get("source_url", ""), "p": r.get("pr_p", ""), "r": r.get("pr_r", ""),
                "conf": r.get("pr_conf", ""), "stance": r.get("content_label", ""),
                "vad": r.get("comment_vad", ""), "status": r.get("review_status", ""),
                "notes": r.get("notes", ""), "dur": r.get("duration_sec", ""),
            })
    return rows


def main():
    rows = load_rows()
    cb = json.loads(CODEBOOK.read_text(encoding="utf-8"))
    codes = {"p": {k: v["name"] for k, v in cb["p"].items()},
             "r": {k: v["name"] for k, v in cb["r"].items()}}
    data = {"codes": codes, "rows": rows}
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

    html = HTML_TMPL.replace("__DATA__", payload)
    OUT.write_text(html, encoding="utf-8")
    print(f"annotator written: {OUT} rows={len(rows)} p={len(codes['p'])} r={len(codes['r'])}")


HTML_TMPL = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gameclip-SNA · 人工标注工作台</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--line:#242936;--fg:#e6e6e6;--dim:#8b949e;--acc:#58a6ff;--ok:#7ee787;--warn:#d29922;--bad:#f85149}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--fg);margin:0;padding:16px}
h1{font-size:17px;margin:0 0 8px}
.bar{position:sticky;top:0;z-index:20;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.bar select,.bar input,.bar button{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:5px 8px;font-size:12px}
.bar button{cursor:pointer}.bar button.primary{border-color:var(--acc);color:var(--acc)}
.prog{height:6px;background:#22262f;border-radius:3px;flex:1 1 180px;overflow:hidden}
.prog i{display:block;height:100%;background:var(--ok);width:0}
.hint{font-size:12px;color:var(--dim)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:12px;margin-top:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px;display:flex;flex-direction:column;gap:6px}
.card.done{border-color:#2b5f3b}
.meta{font-size:12px;color:#c9d1d9;display:flex;justify-content:space-between;gap:6px}
.meta code{color:var(--dim)}
.tags{font-size:11px;color:var(--dim);line-height:1.5}
.tags b{color:#c9d1d9}
video,img{width:100%;border-radius:6px;background:#000;display:block;max-height:200px;object-fit:contain}
.ai{font-size:11px;color:var(--dim);border-top:1px dashed var(--line);padding-top:4px}
.f{margin-top:4px;display:flex;flex-direction:column;gap:4px}
.f label{font-size:11px;color:var(--dim)}
.stance{display:flex;gap:6px;flex-wrap:wrap}
.stance label{display:flex;align-items:center;gap:3px;font-size:12px;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:3px 7px;cursor:pointer}
.stance input{accent-color:var(--acc)}
.stance label.sel{border-color:var(--acc);background:#1b2a3d}
.chips{display:flex;flex-wrap:wrap;gap:4px;max-height:96px;overflow:auto}
.chips label{display:flex;align-items:center;gap:3px;font-size:11px;color:#b8c0cc;border:1px solid var(--line);border-radius:5px;padding:2px 5px;cursor:pointer}
.chips label.on{border-color:var(--ok);color:var(--ok)}
.chips input{display:none}
textarea,input[type=text],input[type=number]{background:#0d1014;color:var(--fg);border:1px solid var(--line);border-radius:5px;padding:4px 6px;font-size:12px;width:100%}
.badge{font-size:10px;border-radius:4px;padding:1px 5px}
.b-pend{background:#30363d;color:#8b949e}.b-done{background:#1f6f43;color:#d7ffe4}
.row2{display:flex;gap:6px}.row2>*{flex:1}
.imp{color:var(--acc);text-decoration:underline;cursor:pointer;font-size:12px}
.foot{margin-top:18px;color:var(--dim);font-size:11px;line-height:1.6}
a{color:var(--acc)}
</style></head><body>
<h1>Gameclip-SNA · 人工标注工作台</h1>
<div class="bar">
  <select id="fGame"></select>
  <select id="fStatus">
    <option value="all">全部</option><option value="pending">待标注</option><option value="done">已标注</option>
    <option value="lowconf">低置信 &lt;0.6</option><option value="nop">无 P 码</option><option value="review">待复核</option>
  </select>
  <select id="fPageSize"><option>24</option><option selected>48</option><option>96</option></select>
  <button id="prev">« 上一页</button><span id="pginfo" class="hint"></span><button id="next">下一页 »</button>
  <div class="prog" title="标注进度"><i id="prog"></i></div>
  <span id="progtext" class="hint"></span>
  <button id="exp" class="primary">导出标注 CSV</button>
  <button id="expAll" class="primary">导出全部（含未改）</button>
  <label class="imp">导入 CSV<input id="imp" type="file" accept=".csv" style="display:none"></label>
  <button id="clear" title="清空本浏览器的标注">重置</button>
</div>
<div id="grid" class="grid"></div>
<div class="foot">
标注保存位置：本浏览器 localStorage（刷新不丢）。点「导出标注 CSV」得到 <code>human_labels_*.csv</code>，
然后运行 <code>python Gameclip-SNA/scripts/merge_labels.py human_labels_*.csv</code> 把结果写回
<code>data/clips.csv</code> 的 human_correction 列并推送。P/R 码表与 AI 预标来自自动流水线；人工只需确认/修正。
</div>
<script>
const DATA = __DATA__;
const LS = 'gameclip_labels_v1';
const STANCES = ['positive','negative','neutral','mixed'];
const ST_CN = {positive:'正向', negative:'负向', neutral:'中性', mixed:'混合'};
let labels = {};
try { labels = JSON.parse(localStorage.getItem(LS) || '{}'); } catch(e) { labels = {}; }
let page = 0;

const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const splitCodes = s => String(s||'').replace(/、/g,';').split(';').map(x=>x.trim()).filter(Boolean);

function save(){ localStorage.setItem(LS, JSON.stringify(labels)); renderTop(); }
function get(id){ return labels[id]; }

function renderTop(){
  let done = 0; const total = DATA.rows.length;
  DATA.rows.forEach(r => { if (get(r.id)) done++; });
  $('#prog').style.width = (100*done/total).toFixed(1) + '%';
  $('#progtext').textContent = '已标注 ' + done + ' / ' + total;
}

function options(){
  const games = [...new Set(DATA.rows.map(r=>r.game))].sort();
  const sel = $('#fGame');
  sel.innerHTML = '<option value="all">全部游戏</option>' + games.map(g=>`<option>${esc(g)}</option>`).join('');
}

function filtered(){
  const g = $('#fGame').value, st = $('#fStatus').value;
  return DATA.rows.filter(r => {
    if (g !== 'all' && r.game !== g) return false;
    const lab = get(r.id);
    if (st === 'pending' && lab) return false;
    if (st === 'done' && !lab) return false;
    if (st === 'lowconf' && !(r.conf && parseFloat(r.conf) < 0.6)) return false;
    if (st === 'nop' && r.p) return false;
    if (st === 'review' && !(r.status === 'pending' || !r.p)) return false;
    return true;
  });
}

function chips(field, id, selected){
  const out = [];
  for (const [code, name] of Object.entries(DATA.codes[field])) {
    const on = selected.includes(code);
    out.push(`<label class="${on?'on':''}" title="${esc(name)}"><input type="checkbox" data-f="${field}" data-id="${id}" value="${code}" ${on?'checked':''}><span>${code} ${esc(name.slice(0,6))}</span></label>`);
  }
  return out.join('');
}

function card(r){
  const lab = get(r.id) || {};
  const aiP = splitCodes(r.p), aiR = splitCodes(r.r);
  const pSel = lab.p_codes ? splitCodes(lab.p_codes) : aiP;
  const rSel = lab.r_codes ? splitCodes(lab.r_codes) : aiR;
  const stance = lab.stance || '';
  const media = r.prev ? `<video controls preload="metadata" src="${esc(r.prev)}"></video>`
              : r.kf ? `<a href="${esc(r.src||r.kf)}" target="_blank"><img src="${esc(r.kf)}" loading="lazy"></a>`
              : '<div class="novideo">无预览</div>';
  const done = !!get(r.id);
  const st = r.status === 'deprioritized' ? '降级' : (r.status === 'pending_analysis' ? '待分析' : '待复核');
  return `<div class="card ${done?'done':''}" data-cid="${r.id}">
    <div class="meta"><span><b>${esc(r.game)}</b> · ${esc(r.fmt||'—')} · <code>${esc(r.id)}</code></span>
      <span class="badge ${done?'b-done':'b-pend'}">${done?'已标注':'待标注'}</span></div>
    ${media}
    <div class="tags">AI：P <b>${esc(r.p||'—')}</b> · R <b>${esc(r.r||'—')}</b> · 内容 <b>${esc(r.stance||'—')}</b> · conf ${esc(r.conf||'—')} · ${esc(r.dur||'')}s · ${st}</div>
    <div class="f">
      <label>内容四分类（必选）</label>
      <div class="stance" data-f="stance" data-id="${r.id}">
        ${STANCES.map(s=>`<label class="${stance===s?'sel':''}"><input type="radio" name="st_${r.id}" value="${s}" ${stance===s?'checked':''}>${ST_CN[s]}</label>`).join('')}
      </div>
      <div class="row2">
        <div><label>强度 1-4</label><input type="number" min="1" max="4" value="${lab.intensity||''}" data-f="intensity" data-id="${r.id}" placeholder="1-4"></div>
        <div><label>置信 0-1</label><input type="number" min="0" max="1" step="0.05" value="${lab.confidence||''}" data-f="confidence" data-id="${r.id}" placeholder="0.7"></div>
      </div>
      <label>P 码（可多选；空=无合适码）</label>
      <div class="chips">${chips('p', r.id, pSel)}</div>
      <label>R 码（分号分隔，可留空）</label>
      <input type="text" data-f="r_codes" data-id="${r.id}" value="${esc(rSel.join(';'))}" placeholder="如 R101;R452">
      <label>证据（帧/秒数，必填）</label>
      <textarea rows="1" data-f="evidence" data-id="${r.id}" placeholder="f_04 12s 第一滴血…">${esc(lab.evidence||'')}</textarea>
      <label>备注（可选）</label>
      <input type="text" data-f="notes" data-id="${r.id}" value="${esc(lab.notes||'')}" placeholder="存疑点 / 修正原因">
    </div>
    <div class="ai"><a href="${esc(r.src)}" target="_blank">平台原片</a></div>
  </div>`;
}

function collect(id){
  const card = document.querySelector(`[data-cid="${id}"]`);
  if (!card) return;
  const rec = get(id) || {};
  const st = card.querySelector(`input[name="st_${id}"]:checked`);
  if (st) rec.stance = st.value;
  card.querySelectorAll('[data-f]').forEach(el => {
    const f = el.dataset.f; if (f === 'stance') return;
    if (el.type === 'checkbox' && el.dataset.f !== 'r_codes') {
      const set = new Set(rec.p_codes ? splitCodes(rec.p_codes) : []);
      if (el.checked) set.add(el.value); else set.delete(el.value);
      if (el.dataset.f === 'p') rec.p_codes = [...set].join(';');
      return;
    }
    if (el.dataset.f === 'r_codes' || el.dataset.f === 'intensity' || el.dataset.f === 'confidence' || el.dataset.f === 'evidence' || el.dataset.f === 'notes') rec[el.dataset.f] = el.value;
  });
  if (!rec.stance) return;            // 四分类必选前不落库
  rec.annotated_at = new Date().toISOString();
  labels[id] = rec; save();
}

function render(){
  const list = filtered();
  const ps = parseInt($('#fPageSize').value, 10);
  const pages = Math.max(1, Math.ceil(list.length / ps));
  if (page >= pages) page = pages - 1;
  if (page < 0) page = 0;
  const slice = list.slice(page*ps, (page+1)*ps);
  $('#grid').innerHTML = slice.map(card).join('') || '<p class="hint">没有符合条件的条目。</p>';
  $('#pginfo').textContent = `第 ${page+1}/${pages} 页 · 共 ${list.length} 条`;
  bindGrid();
}

function bindGrid(){
  document.querySelectorAll('.card').forEach(card => {
    const id = card.dataset.cid;
    card.querySelectorAll('input,textarea').forEach(el => {
      el.addEventListener('change', () => { collect(id); });
    });
    card.querySelectorAll('.stance label').forEach(l => l.addEventListener('click', () => {
      card.querySelectorAll('.stance label').forEach(x=>x.classList.remove('sel'));
      l.classList.add('sel');
    }));
  });
}

function csvEscape(v){ v = String(v ?? ''); return /[",\n]/.test(v) ? '"' + v.replace(/"/g,'""') + '"' : v; }
function exportCSV(all){
  const list = all ? DATA.rows : DATA.rows.filter(r => get(r.id));
  const head = ['clip_id','stance','intensity','p_codes','r_codes','evidence','confidence','notes','annotated_at'];
  const lines = [head.join(',')];
  list.forEach(r => {
    const l = get(r.id) || (all ? {stance:'', intensity:'', p_codes:'', r_codes:'', evidence:'', confidence:'', notes:''} : null);
    if (!l) return;
    lines.push([r.id, l.stance||'', l.intensity||'', l.p_codes||'', l.r_codes||'', l.evidence||'', l.confidence||'', l.notes||'', l.annotated_at||''].map(csvEscape).join(','));
  });
  const blob = new Blob([lines.join('\n')], {type:'text/csv;charset=utf-8'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = (all ? 'human_labels_all_' : 'human_labels_') + new Date().toISOString().slice(0,10) + '.csv';
  a.click(); URL.revokeObjectURL(a.href);
}

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

function importCSV(file){
  const fr = new FileReader();
  fr.onload = () => {
    const rows = parseCSV(fr.result);
    if (!rows.length) return;
    const head = rows[0].map(x => x.trim());
    const idx = n => head.indexOf(n);
    const map = {stance:'stance', intensity:'intensity', p_codes:'p_codes', r_codes:'r_codes', evidence:'evidence', confidence:'confidence', notes:'notes', annotated_at:'annotated_at'};
    let n = 0;
    for (let i = 1; i < rows.length; i++) {
      const r = rows[i]; const cid = r[idx('clip_id')];
      if (!cid) continue;
      const rec = {};
      for (const [k, col] of Object.entries(map)) { const j = idx(col); if (j >= 0) rec[k] = r[j]; }
      if (rec.stance) { labels[cid.trim()] = rec; n++; }
    }
    save(); render();
    alert('导入 ' + n + ' 条标注');
  };
  fr.readAsText(file);
}

function main(){
  options();
  $('#fGame').addEventListener('change', () => { page = 0; render(); });
  $('#fStatus').addEventListener('change', () => { page = 0; render(); });
  $('#fPageSize').addEventListener('change', () => { page = 0; render(); });
  $('#prev').addEventListener('click', () => { page--; render(); });
  $('#next').addEventListener('click', () => { page++; render(); });
  $('#exp').addEventListener('click', () => exportCSV(false));
  $('#expAll').addEventListener('click', () => exportCSV(true));
  $('#imp').addEventListener('change', e => { if (e.target.files[0]) importCSV(e.target.files[0]); e.target.value = ''; });
  $('#clear').addEventListener('click', () => { if (confirm('清空本浏览器所有标注？建议先导出。')) { labels = {}; save(); render(); } });
  renderTop(); render();
}
main();
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
