"""目标6：报告生成（Markdown / JSON / HTML）。

把聚合结果渲染为可直接查看的报告，HTML 含情感分布条与关键帧文字摘要。
"""
from __future__ import annotations

import json
import os
from typing import List

from ..report.aggregator import AnalysisResult

LABEL_CN = {"positive": "正向", "neutral": "中性", "negative": "负向"}


def to_json(result: AnalysisResult, path: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
    return path


def to_markdown(result: AnalysisResult) -> str:
    r = result.to_dict()
    md = []
    md.append(f"# 官方视频物料分析报告\n")
    md.append(f"- 视频源：{r['source']}")
    vi = r["video_info"]
    if vi:
        md.append(f"- 分辨率：{vi.get('width')}x{vi.get('height')}　时长：{vi.get('duration_sec')}s　帧率：{vi.get('fps')}")
    sel = r["selection"]
    md.append(f"- 抽帧 {sel.get('total')} 张 → 关键帧 {sel.get('kept')} 张（去模糊 {sel.get('dropped_blur')}，去重 {sel.get('dropped_dup')}）")
    md.append("")

    cross = r.get("cross", {})
    if cross.get("brands"):
        md.append(f"## 一、画面关键信息")
        md.append(f"**品牌/Logo**：{', '.join(cross['brands'])}")
    if cross.get("top_key_points"):
        md.append(f"**核心卖点**：{'; '.join(cross['top_key_points'])}")
    if cross.get("top_on_screen_text"):
        md.append(f"**高频画面文字**：{'; '.join(cross['top_on_screen_text'])}")
    md.append("")

    md.append("### 关键帧逐帧摘要")
    for i, f in enumerate(r["frames"], 1):
        md.append(f"{i}. `[t={f['timestamp']}s]` {f.get('summary') or '(无)'}")
        if f.get("on_screen_text"):
            md.append(f"   - 画面文字：{' / '.join(f['on_screen_text'])}")
        if f.get("key_points"):
            md.append(f"   - 营销点：{'; '.join(f['key_points'])}")
    md.append("")

    sent = r.get("sentiment", {})
    if sent:
        md.append("## 二、评论情感")
        md.append(f"- 评论总数：{sent.get('total')}")
        d = sent.get("distribution", {})
        md.append(f"- 情感分布：正向 {d.get('positive')} / 中性 {d.get('neutral')} / 负向 {d.get('negative')}")
        md.append(f"- 正向占比：{sent.get('positive_ratio')}　负向占比：{sent.get('negative_ratio')}　平均情感分：{sent.get('average_score')}")
        if sent.get("top_aspects"):
            md.append(f"- 高频主题：{', '.join(sent['top_aspects'])}")
        md.append("")
        md.append("### 评论情感明细（前 10 条）")
        for s in r["sentiment_details"][:10]:
            md.append(f"- [{LABEL_CN.get(s['label'], s['label'])} {s['score']}] {s['text']}")
    return "\n".join(md)


def to_html(result: AnalysisResult) -> str:
    r = result.to_dict()
    sent = r.get("sentiment", {})
    d = sent.get("distribution", {})
    total = max(sent.get("total", 1), 1)
    pos_p = round(100 * d.get("positive", 0) / total)
    neu_p = round(100 * d.get("neutral", 0) / total)
    neg_p = round(100 * d.get("negative", 0) / total)

    frames_html = "".join(
        f"<li><b>t={f['timestamp']}s</b> {f.get('summary') or ''}"
        + (f"<br><small>画面文字：{' / '.join(f['on_screen_text'])}</small>" if f.get("on_screen_text") else "")
        + "</li>"
        for f in r["frames"]
    )
    comments_html = "".join(
        f"<li><span class='tag {s['label']}'>{LABEL_CN.get(s['label'], s['label'])}</span> {s['text']}</li>"
        for s in r["sentiment_details"][:20]
    )
    cross = r.get("cross", {})

    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>官方视频物料分析报告</title>
<style>
 body{{font-family:-apple-system,'Segoe UI',sans-serif;max-width:900px;margin:24px auto;padding:0 16px;color:#222}}
 h1{{border-bottom:3px solid #ff2e4d;padding-bottom:8px}}
 .bar{{display:flex;height:26px;border-radius:6px;overflow:hidden;margin:10px 0;font-size:12px;color:#fff}}
 .bar .p{{background:#2ecc71}} .bar .n{{background:#95a5a6}} .bar .neg{{background:#e74c3c}}
 .tag{{display:inline-block;padding:1px 8px;border-radius:10px;color:#fff;font-size:12px;margin-right:6px}}
 .tag.positive{{background:#2ecc71}} .tag.neutral{{background:#95a5a6}} .tag.negative{{background:#e74c3c}}
 ul{{line-height:1.7}}
</style></head><body>
<h1>官方视频物料分析报告</h1>
<p>视频源：{r['source']}</p>
<p>抽帧 {r['selection'].get('total')} → 关键帧 <b>{r['selection'].get('kept')}</b>（去模糊 {r['selection'].get('dropped_blur')}，去重 {r['selection'].get('dropped_dup')}）</p>
<h2>一、画面关键信息</h2>
<p><b>品牌/Logo：</b>{', '.join(cross.get('brands', [])) or '—'}</p>
<p><b>核心卖点：</b>{'; '.join(cross.get('top_key_points', [])) or '—'}</p>
<p><b>高频画面文字：</b>{'; '.join(cross.get('top_on_screen_text', [])) or '—'}</p>
<ul>{frames_html}</ul>
<h2>二、评论情感</h2>
<p>评论总数 <b>{sent.get('total')}</b>　平均情感分 {sent.get('average_score')}</p>
<div class="bar">
 <div class="p" style="width:{pos_p}%">正向 {pos_p}%</div>
 <div class="n" style="width:{neu_p}%">中性 {neu_p}%</div>
 <div class="neg" style="width:{neg_p}%">负向 {neg_p}%</div>
</div>
<ul>{comments_html or '<li>暂无评论</li>'}</ul>
</body></html>"""


def generate(result: AnalysisResult, formats: List[str], output_dir: str, name: str = "report") -> dict:
    """按指定格式生成报告，返回 {格式: 路径}。"""
    os.makedirs(output_dir, exist_ok=True)
    paths = {}
    if "json" in formats:
        paths["json"] = to_json(result, os.path.join(output_dir, f"{name}.json"))
    if "markdown" in formats or "md" in formats:
        p = os.path.join(output_dir, f"{name}.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(to_markdown(result))
        paths["markdown"] = p
    if "html" in formats:
        p = os.path.join(output_dir, f"{name}.html")
        with open(p, "w", encoding="utf-8") as f:
            f.write(to_html(result))
        paths["html"] = p
    return paths
