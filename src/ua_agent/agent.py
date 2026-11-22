# -*- coding: utf-8 -*-
"""
ClipAgent：从视频到「十级标签 + 规范名 + 报告 + 训练标注」的完整 agent。

链路（对应 UA-ClipInsight 的 G1–G6 + 打标层）：
  G1 抽帧            → extractor.frame_extractor.extract_frames (cv2)
  G2 关键帧筛选      → keyframe_selector.select_keyframes（模糊/去重/场景）
  G3 画面理解        → vision.frame_analyzer.analyze_frames（VLM 逐帧）+ 跨帧聚合
  G4 评论（可选）    → comments.sentiment_analyzer（词典/LLM 双路）
  G5 打标            → 受控词表 VLM（二/三/四/五/七级）+ 六级自由文本 + 元数据分流（八/九/十级）
  G6 产出            → report.md + annotation.json（可直接作为微调标注样本）

用法（见 run.py）：
  agent = ClipAgent()
  res = agent.analyze("x.mp4", version="通用版本")
  res["report_md"], res["annotation"]
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .ua_src.config import load_config
from .ua_src.extractor.frame_extractor import extract_frames, video_info
from .ua_src.extractor.keyframe_selector import select_keyframes
from .ua_src.vision.vlm_client import VLMClient
from .ua_src.vision.frame_analyzer import analyze_frames, summarize_across_frames
from .ua_src.comments.sentiment_analyzer import lexicon_sentiment, SentimentResult, sentiment_summary
from .ua_src.platforms.base import Comment
from .knowledge import (LEVEL_KEYS, GENERIC_VERSION, load_knowledge, vocab_for,
                        l9_from_l7, l10_from_size, l8_from_account)
from .pr_tagger import PRTagger

TAG_SYSTEM = (
    "你是买量视频标签专家。根据视频内容理解结果，为素材打十级标签。"
    "只能从候选词表中选值（六级除外）。只输出 JSON，不要解释。"
)

TAG_USER = """【视频内容理解】
{summary}

【候选词表】（除六级外，只能从中选）
{candidates}

【规则】
1. 二/三/四/五/七级：必须从候选值中选择；确实无合适项时填空字符串 ""。
2. 六级字段：自由文本「看点/具体情节」，一句话，≤20 字，不要套用候选词。
3. 一级/八/九/十级已由元数据确定，输出时保持原样。
4. 只输出一个 JSON 对象，键为：一级字段…十级字段。

JSON："""


def _clip_id(video_path: str) -> str:
    h = hashlib.md5()
    with open(video_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fmt_candidates(vocab: dict, skip=("一级字段", "六级字段", "八级字段", "九级字段", "十级字段")) -> str:
    lines = []
    for lv in LEVEL_KEYS:
        if lv in skip:
            continue
        vals = vocab.get(lv) or []
        lines.append(f"- {lv}: {' / '.join(vals) if vals else '（无候选，留空）'}")
    return "\n".join(lines)


def _extract_json(text: str):
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}")
        if s != -1 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except json.JSONDecodeError:
                return None
    return None


class ClipAgent:
    def __init__(self, config_path: str | Path | None = None, knowledge_path: str | Path | None = None,
                 vlm: VLMClient | None = None, labels: str | None = None):
        self.cfg = load_config(str(config_path or (Path(__file__).resolve().parent / "config.yaml")))
        self.vlm = vlm or VLMClient.from_config(self.cfg.vlm)
        tagger_cfg = self.cfg.get("vlm_tagger") or self.cfg.vlm
        self.vlm_tagger = vlm or VLMClient.from_config(tagger_cfg)
        self.knowledge = load_knowledge(knowledge_path)
        self.labels = (labels or self.cfg.get("labels", "mode", default="both")).lower()

    # ---------- 打标 ----------
    def tag(self, content_summary: str, version: str, meta: dict, account: str = "") -> dict:
        vocab = vocab_for(self.knowledge, version)
        candidates = _fmt_candidates(vocab)
        user = TAG_USER.format(summary=content_summary[:4000], candidates=candidates)
        raw = self.vlm.chat(TAG_SYSTEM, user, image_paths=[])
        data = _extract_json(raw) or {}

        out = {lv: "" for lv in LEVEL_KEYS}
        # 元数据层级：确定性
        out["一级字段"] = version
        out["八级字段"] = l8_from_account(account) or ""
        out["十级字段"] = ""
        # 受控层级：校验词表
        for lv in ("二级字段", "三级字段", "四级字段", "五级字段", "七级字段"):
            v = data.get(lv, "")
            v = v if isinstance(v, str) else str(v)
            allowed = set(vocab.get(lv) or [])
            out[lv] = v if v in allowed else ("" if v.strip() in ("", "无", "不适用", "null", "None") else "")
        # 六级自由文本
        v6 = data.get("六级字段", "")
        out["六级字段"] = v6.strip() if isinstance(v6, str) else ""
        # 链式一致性：四级 → 三级（L4_TO_L3），七级 → 九级（provenance），宽高 → 十级
        from .ua_src.tagging.version_notes import L4_TO_L3
        if out["四级字段"] and out["四级字段"] in L4_TO_L3:
            out["三级字段"] = L4_TO_L3[out["四级字段"]]
        out["九级字段"] = l9_from_l7(out["七级字段"]) or ""
        out["十级字段"] = l10_from_size(meta.get("width", 0), meta.get("height", 0))
        # 规范名
        parts = []
        for lv in LEVEL_KEYS:
            val = out.get(lv, "")
            parts.append(f"[{val}]" if lv == "六级字段" and val else val)
        name = "-".join(p for p in parts if p)
        out["规范名"] = name
        return {"tags": out, "raw": raw}

    # ---------- 主流程 ----------
    def analyze(self, video_path: str, version: str = GENERIC_VERSION, url: str = "",
                comments: list | None = None, out_dir: str | Path | None = None,
                comment_llm: bool = False, game: str = "", format_: str = "") -> dict:
        t0 = time.time()
        video = Path(video_path).expanduser().resolve()
        if not video.exists():
            raise FileNotFoundError(video)
        clip_id = _clip_id(str(video))
        out = Path(out_dir) if out_dir else Path(__file__).resolve().parent / "outputs" / clip_id
        out.mkdir(parents=True, exist_ok=True)

        # G1 抽帧
        info = video_info(str(video))
        frames = extract_frames(str(video), str(out / "frames"),
                                interval_sec=self.cfg.frames.get("interval_sec", 2.0),
                                max_frames=self.cfg.frames.get("max_frames", 80),
                                resize_long_edge=self.cfg.frames.get("resize_long_edge", 1280))
        # G2 关键帧
        keyframes, selection = select_keyframes(
            frames,
            blur_threshold=self.cfg.keyframe.get("blur_threshold", 60.0),
            dedup_hamming=self.cfg.keyframe.get("dedup_hamming", 12),
            scene_change_threshold=self.cfg.keyframe.get("scene_change_threshold", 0.35),
        )
        # G3 画面理解
        analyses = analyze_frames(keyframes, self.vlm)
        cross = summarize_across_frames(analyses)
        summary_text = "\n".join(
            [f"- 帧{t}({a.timestamp:.1f}s): {a.summary}" for t, a in
             ((i, a) for i, a in enumerate(analyses) if a.summary)]
        )
        content_summary = "\n".join(filter(None, [
            "画面要点：" + "、".join(cross.get("top_key_points", [])[:8]) if cross.get("top_key_points") else "",
            "画面文字：" + "、".join(cross.get("top_on_screen_text", [])[:8]) if cross.get("top_on_screen_text") else "",
            "品牌/主体：" + "、".join(cross.get("brands", []) or []) if cross.get("brands") else "",
            summary_text,
        ]))
        # G5 打标（P/R 主体系 + 十级可选）
        pr_res = None
        tag_res = {"tags": {}}
        if "pr" in self.labels or "both" in self.labels:
            pr_res = PRTagger(self.vlm_tagger).tag(keyframes, content_summary, info.get("duration_sec", 0))
        if "ua10" in self.labels or "both" in self.labels:
            tag_res = self.tag(content_summary, version, info)
        # G4 评论情感（可选）
        senti = {}
        senti_details = []
        if comments:
            for i, c in enumerate(comments[: self.cfg.comments.get("max_comments", 200)]):
                text = c if isinstance(c, str) else (c.get("text") or "")
                label, score = lexicon_sentiment(text)
                senti_details.append({"text": text[:80], "label": label, "score": round(score, 3)})
            from collections import Counter
            cnt = Counter(d["label"] for d in senti_details)
            n = max(len(senti_details), 1)
            senti = {"n": len(senti_details),
                     "dist": {k: round(v / n, 3) for k, v in cnt.items()},
                     "net": round((cnt.get("positive", 0) - cnt.get("negative", 0)) / n, 3)}

        annotation = {
            "clip_id": clip_id, "source": url or str(video),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "meta": {k: info.get(k) for k in ("width", "height", "fps", "duration_sec", "frame_count")},
            "labels_mode": self.labels,
            "game": game, "format": format_,
            "knowledge_source": self.knowledge.get("source", "bootstrap"),
            "pr": pr_res,
            "ua10": tag_res["tags"],
            "name": tag_res["tags"].get("规范名", ""),
            "content_summary": content_summary,
            "frame_analyses": [a.to_dict() for a in analyses],
            "comment_sentiment": senti,
            "comment_details": senti_details,
            "elapsed_s": round(time.time() - t0, 1),
        }
        (out / "annotation.json").write_text(json.dumps(annotation, ensure_ascii=False, indent=2), encoding="utf-8")
        md = self._report(annotation, tag_res["tags"], out)
        (out / "report.md").write_text(md, encoding="utf-8")
        return {"clip_id": clip_id, "out_dir": str(out), "annotation": annotation,
                "report_md": md, "tags": tag_res["tags"], "pr": pr_res}

    # ---------- 报告 ----------
    @staticmethod
    def _report(a: dict, tags: dict, out: Path) -> str:
        lines = [f"# 素材标注报告 · {a['clip_id'][:8]}", ""]
        m = a["meta"]
        lines += [f"- 来源：{a['source']}",
                  f"- 时长/分辨率：{m.get('duration_sec')}s / {m.get('width')}x{m.get('height')}",
                  f"- 标签模式：{a.get('labels_mode')}", ""]
        pr = a.get("pr") or {}
        if pr:
            lines += ["## P 码（情节层）", ""]
            if pr.get("p_codes"):
                lines += ["| P 码 | 名称 | 来源 | 证据 |", "|---|---|---|---|"]
                for p in pr["p_codes"]:
                    lines.append(f"| {p['id']} | {p['name']} | {'+'.join(p.get('source', []))} | {p.get('evidence', '')} |")
            else:
                lines.append("（未命中）")
            hit_r = {k: v for k, v in (pr.get("r_codes") or {}).items() if v not in (None, "", "无")}
            lines += ["", f"## R 码（视觉特征，{len(hit_r)} 项命中）", ""]
            if hit_r:
                lines.append("、".join(f"{k}={v}" for k, v in hit_r.items()))
            lines.append(f"\n- 置信度：{pr.get('confidence')}"
                         + (f"　规则层候选：{'/'.join(pr.get('rule_p_candidates') or [])}" if pr.get("rule_p_candidates") else ""))
        if tags:
            lines += ["", "## 十级标签", "", "| 层级 | 值 |", "|---|---|"]
            for k, v in tags.items():
                if k != "规范名":
                    lines.append(f"| {k} | {v or '—'} |")
            lines += ["", f"**规范名**：`{tags.get('规范名', '')}`"]
        lines += ["", "## 内容理解", ""]
        lines += (a["content_summary"] or "（无）").splitlines()
        if a.get("comment_sentiment"):
            s = a["comment_sentiment"]
            lines += ["", "## 评论区情感（词典口径）", "",
                      f"- 样本 {s['n']} 条，分布 {s['dist']}，净情绪 {s['net']}"]
        lines += ["", "## 逐帧", "", "| 帧 | 时间 | 摘要 | 画面文字 |", "|---|---|---|---|"]
        for f in a["frame_analyses"]:
            text = "、".join(f.get("on_screen_text", [])[:3]).replace("|", "/")
            lines.append(f"| {f.get('frame_index')} | {f.get('timestamp', 0):.1f}s | {(f.get('summary') or '').replace('|', '/')} | {text} |")
        return "\n".join(lines) + "\n"
