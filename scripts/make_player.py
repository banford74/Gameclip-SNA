#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 data/clips.csv 生成 GitHub Pages 播放页 docs/index.html（含 P/R 与情感标签）。"""
import csv
import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "clips.csv"
OUT = ROOT / "docs" / "index.html"


def main():
    if not CSV.exists():
        sys.exit("data/clips.csv 不存在")
    rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
    cards = []
    for r in rows:
        cid = html.escape(r.get("clip_id", "")[:10])
        game = html.escape(r.get("game") or "—")
        fmt = html.escape(r.get("format") or "—")
        preview = r.get("preview_url") or ""
        full = r.get("video_download_url") or ""
        src_platform = r.get("source_url") or ""
        keyframe = r.get("keyframe_url") or ""
        pr = html.escape(r.get("pr_p") or "—")
        conf = html.escape(r.get("pr_conf") or "")
        lab = html.escape(r.get("content_label") or "")
        vae = html.escape(r.get("content_vae") or "")
        cm = html.escape((r.get("comment_pred") or "")[:120])
        hc = html.escape(r.get("human_correction") or "")
        links = []
        if src_platform:
            links.append(f'<a href="{html.escape(src_platform)}" target="_blank">平台原链</a>')
        if full:
            links.append(f'<a href="{html.escape(full)}" target="_blank">原片下载</a>')
        if keyframe:
            links.append(f'<a href="{html.escape(keyframe)}" target="_blank">关键帧</a>')
        video_tag = (f'<video controls preload="metadata" src="{html.escape(preview)}"></video>'
                     if preview else '<div class="novideo">无预览</div>')
        cards.append(f"""
        <div class="card">
          <div class="meta"><b>{game}</b> · {fmt} · <code>{cid}</code></div>
          <div class="tags">P: <b>{pr}</b> <span class="conf">{conf}</span> · 情感 <b>{lab}</b> <span class="vae">{vae}</span></div>
          {video_tag}
          <div class="cm">评论预测 {cm}</div>
          <div class="links">{" · ".join(links)}</div>
          <div class="hc">{'人工已填：' + hc if hc else '待人工确认（human_correction）'}</div>
        </div>""")
    OUT.write_text(f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gameclip-SNA · 素材预览</title>
<style>
body{{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:#0f1115;color:#e6e6e6;margin:0;padding:24px}}
h1{{font-size:18px;font-weight:600}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px;margin-top:16px}}
.card{{background:#171a21;border:1px solid #242936;border-radius:10px;padding:12px}}
video{{width:100%;border-radius:6px;background:#000;margin-top:8px}}
.meta{{font-size:13px;color:#c9d1d9}} .tags{{font-size:12px;color:#9da7b3;margin-top:4px}}
.conf{{color:#7ee787}} .vae{{color:#79c0ff}}
.cm{{font-size:11px;color:#8b949e;margin-top:6px}} .links{{font-size:12px;margin-top:6px}}
a{{color:#58a6ff;text-decoration:none}} .hc{{font-size:11px;color:#d29922;margin-top:6px}}
.novideo{{padding:40px;text-align:center;color:#666}}
</style></head><body>
<h1>Gameclip-SNA · 素材预览（AI 预标 + 待人工确认）</h1>
<p style="color:#8b949e;font-size:13px">共 {len(cards)} 条 · 预览 480p（Pages）· 原片 Release · 人工在 data/clips.csv 填 human_correction</p>
<div class="grid">{''.join(cards)}</div>
</body></html>
""", encoding="utf-8")
    print(f"player written: {OUT} ({len(cards)} clips)")


if __name__ == "__main__":
    main()
