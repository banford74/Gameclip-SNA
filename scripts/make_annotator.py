#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成在线标注工作台（docs/index.html）——支持 4 人分工。

分配策略（确定性，生成时算好并写进页面）：
  * 按 (游戏, 难度) 分层：难度 = 低置信(<0.6) / 无 P 码 / 待分析 记为 hard，其余 easy
  * 层内按 clip_id 稳定排序，逐条分给「当前条数最少」的标注员（4 人，约 551/550/550/550）
  * 每人拿到相近的游戏构成与相近的难易比例，且分工互不重叠

页面功能：
  * 标注员选择（1-4 / 全部），也可用 ?a=2 直接进入；选择记忆在 localStorage
  * 只显示本人分到的条目；进度条只算本人（另显示全局已标注）
  * 游戏/状态筛选、分页 + 跳页；四分类 + 强度 + P/R 码 + 证据 + 置信 + 备注
  * 自动存 localStorage；导出 CSV（仅本人已标注 / 全部已标注，含 annotator 列）；导入续标
用法: python scripts/make_annotator.py
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # Gameclip-SNA
WS = ROOT.parent                                        # workspace
CSV = ROOT / "data" / "clips.csv"
CODEBOOK = WS / "portfolio" / "src" / "codebook.json"
OUT = ROOT / "docs" / "index.html"
N_ANNOTATORS = 4


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


def is_hard(r: dict) -> bool:
    try:
        conf = float(r.get("conf") or 0)
    except ValueError:
        conf = 0.0
    return bool(r.get("status") == "pending_analysis" or not r.get("p") or conf < 0.6)


def assign(rows: list[dict], n: int = N_ANNOTATORS):
    """按 (游戏, 难度) 分层 + 最少条数优先，做确定性分工。"""
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
    rows = load_rows()
    rows, counts = assign(rows)
    rows.sort(key=lambda r: (r["a"], r["game"], r["id"]))
    cb = json.loads(CODEBOOK.read_text(encoding="utf-8"))
    codes = {"p": {k: v["name"] for k, v in cb["p"].items()},
             "r": {k: v["name"] for k, v in cb["r"].items()}}
    data = {"codes": codes, "rows": rows, "n": N_ANNOTATORS, "counts": counts}
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    OUT.write_text(HTML_TMPL.replace("__DATA__", payload), encoding="utf-8")
    print(f"annotator written: {OUT} rows={len(rows)} p={len(codes['p'])} r={len(codes['r'])}")
    print("assignment:", {k: v for k, v in sorted(counts.items())})


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
.progwrap{display:flex;align-items:center;gap:6px;flex:1 1 220px}
.prog{height:6px;background:#22262f;border-radius:3px;flex:1;overflow:hidden}
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
.legend{font-size:12px;color:var(--dim);background:#12151b;border:1px solid var(--line);border-radius:8px;padding:8px 10px;margin:8px 0 4px;line-height:1.7}
.legend b{color:#c9d1d9}
.vad{font-size:11px;color:#8b949e;border-top:1px dashed var(--line);padding-top:4px}
.vad b{color:#b8c0cc}
.ann{font-size:11px;color:var(--warn)}
.foot{margin-top:18px;color:var(--dim);font-size:11px;line-height:1.6}
a{color:var(--acc)}
</style></head><body>
<h1>Gameclip-SNA · 人工标注工作台 <span id="who" class="ann"></span></h1>
<div class="bar">
  <select id="fAnn"></select>
  <select id="fGame"></select>
  <select id="fStatus">
    <option value="all">全部</option><option value="pending">待标注</option><option value="done">已标注</option>
    <option value="lowconf">低置信 &lt;0.6</option><option value="nop">无 P 码</option><option value="review">待复核</option>
  </select>
  <select id="fPageSize"><option>24</option><option selected>48</option><option>96</option></select>
  <button id="prev">« 上一页</button>
  <input id="jump" type="number" min="1" placeholder="跳页" style="width:64px">
  <span id="pginfo" class="hint"></span>
  <button id="next">下一页 »</button>
  <div class="progwrap"><div class="prog" title="标注进度"><i id="prog"></i></div><span id="progtext" class="hint"></span></div>
  <button id="exp" class="primary">💾 存档并回传（一键）</button>
  <button id="expAll">导出全部已标注</button>
  <label class="imp">导入 CSV<input id="imp" type="file" accept=".csv" style="display:none"></label>
  <button id="clear" title="清空本浏览器的标注">重置</button>
  <a class="hint" href="progress.html" target="_blank" style="margin-left:auto">📊 进度汇总页</a>
</div>
<div class="bar" style="border-bottom:none;padding-top:0">
  <span class="hint">可选：共享同步地址（Apps Script 等），填一次存本浏览器；存标注时自动 POST 一份</span>
  <input id="syncUrl" type="text" placeholder="https://script.google.com/macros/s/.../exec" style="flex:1;min-width:240px">
  <span id="syncState" class="hint"></span>
  <span id="lastSave" class="hint"></span>
</div>
<div class="legend">
  <b>本页标注对象 = 视频内容（Task A）</b>：内容四分类 + 强度 + P/R 码 + 证据。
  「强度」指视频本身的情绪强度（1-4），「置信」是你对这次四分类判断的把握（0-1）。
  评论情绪（Task B）<b>不在本页标注</b>——它是自动算的 VAD（1-9 连续分），只读展示在每张卡片底部，仅供对照。
  <div style="margin-top:4px">分工：4 人各负责约 550 条（按游戏×难度分层确定性分配，互不重叠）；每人用 <code>?a=2</code> 这样的链接进入自己的视图。</div>
  <details style="margin-top:6px"><summary style="cursor:pointer;color:#58a6ff">四分类判定指引（mixed vs neutral，点开）</summary>
  <div style="margin-top:6px">
  <b>① 先问「这条片子的设计意图想让观众产生什么情绪」</b>，不是画面里发生了什么。列出情绪拍点：正向＝高光/夸奖/治愈/燃/期待；负向＝失败/吐槽/压抑/恐怖/遗憾/尴尬。<br>
  <b>② 只有单一极性有"有分量的拍点"</b>（能指到具体秒数、被设计出来）→ positive / negative。一个情绪拍点都没有（信息型：攻略、机制推演、纯外观展示）→ <b>neutral</b>。<br>
  <b>③ 两个极性都有有分量的拍点，且形成并置/反转结构</b>（先抑后扬、先扬后抑、反差打脸、自嘲+高燃、社死名场面）→ <b>mixed</b>。<br>
  <b>mixed 与 neutral 的区别</b>：neutral 是「没有情绪拍点」（信息型平铺）；mixed 是「有两个对立的情绪拍点」（情绪双峰）。所以：<br>
  · 「搞笑翻车」≠ neutral（有笑点=情绪设计）→ mixed（惨+笑）或 positive（笑点为主）；<br>
  · 「攻略+燃 BGM」可以是 neutral（信息为主、无情绪拍点），也可以是 positive（燃是设计核心）；<br>
  · 纯色调/画面冷暖对比 ≠ mixed（视觉对比不是情绪反转）；「情绪很强烈」≠ mixed（强度 4 也可以是 positive）；<br>
  · 标题吐槽但正片高燃：以正片是否有负向拍点为准，拿不准就选一个 + 置信 0.5-0.6 + 备注写清两段证据。<br>
  <b>别用 mixed 当"拿不准"的垃圾桶</b>：当前 AI 预标里 mixed 占 43.5%（positive 48.7 / negative 4.2 / neutral 3.2），大概率高估——人工标注时请反向校正。
  </div></details>
</div>
<div id="grid" class="grid"></div>
<div class="foot">
标注保存位置：本浏览器 localStorage（刷新不丢）。点「导出我的标注 CSV」得到 <code>human_labels_*.csv</code>（含 annotator 列），
然后运行 <code>python Gameclip-SNA/scripts/merge_labels.py human_labels_*.csv</code> 把结果写回
<code>data/clips.csv</code> 的 human_correction 列并推送。P/R 码表与 AI 预标来自自动流水线；人工只需确认/修正。
</div>
<script>
const DATA = __DATA__;
const LS = 'gameclip_labels_v1';
const ANN_KEY = 'gameclip_annotator';
const SYNC_KEY = 'gameclip_sync_url';
const STANCES = ['positive','negative','neutral','mixed'];
const ST_CN = {positive:'正向', negative:'负向', neutral:'中性', mixed:'混合'};
let labels = {};
try { labels = JSON.parse(localStorage.getItem(LS) || '{}'); } catch(e) { labels = {}; }
let page = 0;
let SYNC = (new URLSearchParams(location.search).get('sync') || localStorage.getItem(SYNC_KEY) || '').trim();
if (new URLSearchParams(location.search).get('sync')) localStorage.setItem(SYNC_KEY, SYNC);
let syncTimer = null;

function urlAnn(){
  const m = location.search.match(/[?&]a=(\d+)/);
  if (m) return parseInt(m[1], 10);
  const v = parseInt(localStorage.getItem(ANN_KEY) || '0', 10);
  return (v >= 1 && v <= DATA.n) ? v : 1;
}
let ANNOTATOR = urlAnn();

const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const splitCodes = s => String(s||'').replace(/、/g,';').split(';').map(x=>x.trim()).filter(Boolean);

function save(){
  localStorage.setItem(LS, JSON.stringify(labels));
  renderTop(); scheduleSync();
  const ls = document.getElementById('lastSave');
  if (ls) ls.textContent = '上次存档 ' + new Date().toLocaleTimeString();
}
function get(id){ return labels[id]; }
function scope(){ return ANNOTATOR === 'all' ? DATA.rows : DATA.rows.filter(r => r.a === ANNOTATOR); }

const ROWMAP = new Map(DATA.rows.map(r => [r.id, r]));
function myLabels(){
  const out = {};
  for (const [cid, rec] of Object.entries(labels)) {
    const a = String(rec.annotator || (ROWMAP.get(cid) || {}).a || '');
    if (ANNOTATOR === 'all' || a === String(ANNOTATOR)) out[cid] = rec;
  }
  return out;
}
function scheduleSync(){ if (!SYNC) return; clearTimeout(syncTimer); syncTimer = setTimeout(pushSync, 1200); }
async function saveNow(){
  save();                                   // 先落本地
  const st = document.getElementById('syncState');
  if (SYNC) {
    clearTimeout(syncTimer);
    await pushSync();                       // 一键回传
    if (st) st.textContent += ' ✓ 已回传';
  } else {
    exportCSV(false);                       // 未配置同步：直接导出 CSV
    const d = document.getElementById('drop') || document.getElementById('lastSave');
    if (st) st.textContent = '未配置同步地址，已导出 CSV（发回给负责人即可）';
    else if (d) d.textContent = '已导出 CSV，请发给负责人';
  }
}
async function pushSync(){
  const st = document.getElementById('syncState');
  if (!SYNC) return;
  const mine = myLabels();
  const payload = {annotator: ANNOTATOR === 'all' ? 'all' : ANNOTATOR, saved_at: new Date().toISOString(),
                   count: Object.keys(mine).length, labels: mine};
  try {
    await fetch(SYNC, {method: 'POST', mode: 'no-cors',
      headers: {'Content-Type': 'text/plain;charset=utf-8'}, body: JSON.stringify(payload)});
    if (st) { st.textContent = '已同步 ' + new Date().toLocaleTimeString() + '（' + Object.keys(mine).length + ' 条）'; st.className = 'hint'; }
  } catch (e) {
    if (st) { st.textContent = '同步失败：' + e.message; st.className = 'hint bad'; }
  }
}

function renderTop(){
  const rows = scope();
  let done = 0; rows.forEach(r => { if (get(r.id)) done++; });
  $('#prog').style.width = (100*done/Math.max(1,rows.length)).toFixed(1) + '%';
  let gdone = 0; DATA.rows.forEach(r => { if (get(r.id)) gdone++; });
  $('#progtext').textContent = `我 ${done}/${rows.length} · 全局 ${gdone}/${DATA.rows.length}`;
  $('#who').textContent = ANNOTATOR === 'all' ? '（全部标注员视图）' : `（标注员 ${ANNOTATOR}）`;
  const sel = $('#fAnn'); if (sel.value !== String(ANNOTATOR)) sel.value = String(ANNOTATOR);
}

function options(){
  const games = [...new Set(DATA.rows.map(r=>r.game))].sort();
  $('#fGame').innerHTML = '<option value="all">全部游戏</option>' + games.map(g=>`<option>${esc(g)}</option>`).join('');
  $('#fAnn').innerHTML = Array.from({length:DATA.n}, (_,i)=>`<option value="${i+1}">标注员 ${i+1}（${DATA.counts[i+1]||0} 条）</option>`).join('') + '<option value="all">全部</option>';
  $('#fAnn').value = String(ANNOTATOR);
}

function filtered(){
  const rows = scope();
  const g = $('#fGame').value, st = $('#fStatus').value;
  return rows.filter(r => {
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
  let vad = null;
  try { vad = r.vad ? JSON.parse(r.vad) : null; } catch (e) { vad = null; }
  const d = (vad && vad.dist) || {};
  const vadLine = (vad && vad.n)
    ? `<div class="vad">评论观测（自动·Task B，仅供对照，不在此标注）：n=${vad.n} · 正${Math.round((d.positive||0)*100)}% 中${Math.round((d.neutral||0)*100)}% 负${Math.round((d.negative||0)*100)}% · 均值 v=${(vad.mean_vad && vad.mean_vad.v) ?? '—'}（1-9）</div>`
    : '<div class="vad">评论观测：暂无</div>';
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
      <label>内容四分类（视频内容，必选）</label>
      <div class="stance" data-f="stance" data-id="${r.id}">
        ${STANCES.map(s=>`<label class="${stance===s?'sel':''}"><input type="radio" name="st_${r.id}" value="${s}" ${stance===s?'checked':''}>${ST_CN[s]}</label>`).join('')}
      </div>
      <div class="row2">
        <div><label>内容强度 1-4（视频本身情绪强弱，1=平 4=极强）</label><input type="number" min="1" max="4" value="${lab.intensity||''}" data-f="intensity" data-id="${r.id}" placeholder="1-4"></div>
        <div><label>标注置信 0-1（你对四分类判断的把握）</label><input type="number" min="0" max="1" step="0.05" value="${lab.confidence||''}" data-f="confidence" data-id="${r.id}" placeholder="0.7"></div>
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
    ${vadLine}
    <div class="ai"><a href="${esc(r.src)}" target="_blank">平台原片</a></div>
  </div>`;
}

function collect(id){
  const cardEl = document.querySelector(`[data-cid="${id}"]`);
  if (!cardEl) return;
  const rec = get(id) || {};
  const st = cardEl.querySelector(`input[name="st_${id}"]:checked`);
  if (st) rec.stance = st.value;
  cardEl.querySelectorAll('[data-f]').forEach(el => {
    const f = el.dataset.f; if (f === 'stance') return;
    if (el.type === 'checkbox' && f === 'p') {
      const set = new Set(rec.p_codes ? splitCodes(rec.p_codes) : []);
      if (el.checked) set.add(el.value); else set.delete(el.value);
      rec.p_codes = [...set].join(';');
      return;
    }
    if (['r_codes','intensity','confidence','evidence','notes'].includes(f)) rec[f] = el.value;
  });
  if (!rec.stance) return;
  rec.annotator = ANNOTATOR === 'all' ? (rec.annotator || '') : ANNOTATOR;
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
  document.querySelectorAll('.card').forEach(card => {
    const id = card.dataset.cid;
    card.querySelectorAll('input,textarea').forEach(el => el.addEventListener('change', () => collect(id)));
    card.querySelectorAll('.stance label').forEach(l => l.addEventListener('click', () => {
      card.querySelectorAll('.stance label').forEach(x=>x.classList.remove('sel'));
      l.classList.add('sel');
    }));
  });
}

function csvEscape(v){ v = String(v ?? ''); return /[",\n]/.test(v) ? '"' + v.replace(/"/g,'""') + '"' : v; }
function exportCSV(all){
  const list = all ? DATA.rows.filter(r => get(r.id)) : scope().filter(r => get(r.id));
  const head = ['clip_id','annotator','stance','intensity','p_codes','r_codes','evidence','confidence','notes','annotated_at'];
  const lines = [head.join(',')];
  list.forEach(r => {
    const l = get(r.id); if (!l) return;
    lines.push([r.id, l.annotator ?? r.a ?? '', l.stance||'', l.intensity||'', l.p_codes||'', l.r_codes||'', l.evidence||'', l.confidence||'', l.notes||'', l.annotated_at||''].map(csvEscape).join(','));
  });
  const blob = new Blob([lines.join('\n')], {type:'text/csv;charset=utf-8'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = (all ? 'human_labels_all_' : 'human_labels_a' + ANNOTATOR + '_') + new Date().toISOString().slice(0,10) + '.csv';
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
    const fields = ['annotator','stance','intensity','p_codes','r_codes','evidence','confidence','notes','annotated_at'];
    let n = 0;
    for (let i = 1; i < rows.length; i++) {
      const r = rows[i]; const cid = r[idx('clip_id')];
      if (!cid) continue;
      const rec = {};
      for (const k of fields) { const j = idx(k); if (j >= 0) rec[k] = r[j]; }
      if (rec.stance) { labels[cid.trim()] = rec; n++; }
    }
    save(); render();
    alert('导入 ' + n + ' 条标注');
  };
  fr.readAsText(file);
}

function main(){
  options();
  $('#fAnn').addEventListener('change', () => {
    const v = $('#fAnn').value;
    ANNOTATOR = v === 'all' ? 'all' : parseInt(v, 10);
    localStorage.setItem(ANN_KEY, ANNOTATOR === 'all' ? '' : String(ANNOTATOR));
    page = 0; renderTop(); render();
  });
  $('#fGame').addEventListener('change', () => { page = 0; render(); });
  $('#fStatus').addEventListener('change', () => { page = 0; render(); });
  $('#fPageSize').addEventListener('change', () => { page = 0; render(); });
  $('#prev').addEventListener('click', () => { page--; render(); });
  $('#next').addEventListener('click', () => { page++; render(); });
  $('#jump').addEventListener('change', e => {
    const n = parseInt(e.target.value, 10);
    const ps = parseInt($('#fPageSize').value, 10);
    const pages = Math.max(1, Math.ceil(filtered().length / ps));
    if (n >= 1 && n <= pages) { page = n - 1; render(); }
    e.target.value = '';
  });
  $('#exp').addEventListener('click', () => saveNow());
  $('#expAll').addEventListener('click', () => exportCSV(true));
  $('#imp').addEventListener('change', e => { if (e.target.files[0]) importCSV(e.target.files[0]); e.target.value = ''; });
  $('#clear').addEventListener('click', () => { if (confirm('清空本浏览器所有标注？建议先导出。')) { labels = {}; save(); render(); } });
  $('#syncUrl').value = SYNC;
  $('#syncUrl').addEventListener('change', () => {
    SYNC = $('#syncUrl').value.trim();
    localStorage.setItem(SYNC_KEY, SYNC);
    if (SYNC) pushSync();
  });
  renderTop(); render();
}
main();
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
