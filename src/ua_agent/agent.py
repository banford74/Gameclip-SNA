# -*- coding: utf-8 -*-
"""
ClipAgent：游戏短视频 → P/R 创意特征 + 情感向度（VAD）+ 报告 + 训练标注。

链路：
  G1 抽帧 → G2 关键帧筛选 → G3 VLM 逐帧理解 + 跨帧聚合
  G4 评论（可选，JSON 导入）→ 词典 VAD 聚合
  G5 P/R 打标（VLM A + 规则层 B 投票）
  G6 情感：内容 VAD（词典）、逐帧 VAD、P/R→评论 valence 映射
  产出：report.md + annotation.json（微调标注样本）

用法见 run.py；情感词典见 pipeline/sentiment/。
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .ua_src.config import load_config
from .ua_src.extractor.frame_extractor import extract_frames, video_info
from .ua_src.extractor.keyframe_selector import select_keyframes
from .ua_src.vision.vlm_client import VLMClient
from .ua_src.vision.frame_analyzer import analyze_frames, summarize_across_frames
from .ua_src.comments.sentiment_analyzer import lexicon_sentiment
from .pr_tagger import PRTagger
from .pr_sentiment import predict_comment_valence
from ..sentiment.analyze import analyze as vad_analyze
from ..sentiment.hybrid import hybrid_analyze, hybrid_many


def _clip_id(video_path: str) -> str:
    h = hashlib.md5()
    with open(video_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class ClipAgent:
    def __init__(self, config_path: str | Path | None = None, vlm: VLMClient | None = None):
        self.cfg = load_config(str(config_path or (Path(__file__).resolve().parent / "config.yaml")))
        self.vlm = vlm or VLMClient.from_config(self.cfg.vlm)
        tagger_cfg = self.cfg.get("vlm_tagger") or self.cfg.vlm
        self.vlm_tagger = vlm or VLMClient.from_config(tagger_cfg)

    # ---------- 主流程 ----------
    def analyze(self, video_path: str, url: str = "", comments: list | None = None,
                out_dir: str | Path | None = None, game: str = "", format_: str = "") -> dict:
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
            f"- 帧{i}({a.timestamp:.1f}s): {a.summary}" for i, a in enumerate(analyses) if a.summary)
        content_summary = "\n".join(filter(None, [
            "画面要点：" + "、".join(cross.get("top_key_points", [])[:8]) if cross.get("top_key_points") else "",
            "画面文字：" + "、".join(cross.get("top_on_screen_text", [])[:8]) if cross.get("top_on_screen_text") else "",
            "品牌/主体：" + "、".join(cross.get("brands", []) or []) if cross.get("brands") else "",
            summary_text,
        ]))
        # G5 P/R 打标
        pr_res = PRTagger(self.vlm_tagger).tag(keyframes, content_summary, info.get("duration_sec", 0))

        # G6 情感：内容→四分类（AI 预标）；评论→VAD（hybrid：词典×蒸馏×校准，无 mixed）
        self.vad_mode = (self.cfg.get("sentiment", "mode", default="hybrid") or "hybrid").lower()
        if self.vad_mode == "hybrid":
            content_label = hybrid_analyze(content_summary)["label"]
            content_diag = hybrid_analyze(content_summary)
            frame_vad = [{"t": a.timestamp, **hybrid_analyze(a.summary)} for a in analyses if a.summary]
        else:
            content_label = vad_analyze(content_summary, include_mixed=True)["label"]
            content_diag = vad_analyze(content_summary, include_mixed=False)
            frame_vad = [{"t": a.timestamp, **vad_analyze(a.summary, include_mixed=False)} for a in analyses if a.summary]
        comment_vad = None
        comment_details = []
        if comments:
            texts = [c if isinstance(c, str) else (c.get("text") or "") for c in comments]
            agg = hybrid_many(texts) if self.vad_mode == "hybrid" else None
            if agg is None:
                agg = None
            comment_vad = {k: agg[k] for k in ("n", "dist", "net", "mean_vad_llm")} if agg else None
            comment_details = [{"text": t[:100], **d} for t, d in zip(texts, agg["details"])][:200] if agg else []
        pr_mapping = predict_comment_valence(pr_res, content_label, comment_vad)

        annotation = {
            "clip_id": clip_id, "source": url or str(video),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "meta": {k: info.get(k) for k in ("width", "height", "fps", "duration_sec", "frame_count")},
            "game": game, "format": format_,
            "pr": pr_res,
            "content_label": content_label,          # 内容四分类（AI 预标，人工复核）
            "sentiment": {
                "comments": comment_vad,             # 评论 VAD（无 mixed）
                "pr_mapping": pr_mapping,
                "model_diag": {"content_vad": content_diag, "by_frame_vad": frame_vad},
                "lexicon": {"zh": "NRC-VAD + NRC-Emo (Chinese-Simplified 列) + emoji + 种子词典"},
            },
            "content_summary": content_summary,
            "frame_analyses": [a.to_dict() for a in analyses],
            "comment_details": comment_details,
            "elapsed_s": round(time.time() - t0, 1),
        }
        (out / "annotation.json").write_text(json.dumps(annotation, ensure_ascii=False, indent=2), encoding="utf-8")
        md = self._report(annotation, out)
        (out / "report.md").write_text(md, encoding="utf-8")
        return {"clip_id": clip_id, "out_dir": str(out), "annotation": annotation,
                "report_md": md, "pr": pr_res}

    # ---------- 报告 ----------
    @staticmethod
    def _report(a: dict, out: Path) -> str:
        lines = [f"# 素材标注报告 · {a['clip_id'][:8]}", ""]
        m = a["meta"]
        lines += [f"- 来源：{a['source']}",
                  f"- 时长/分辨率：{m.get('duration_sec')}s / {m.get('width')}x{m.get('height')}",
                  f"- 游戏/形态：{a.get('game') or '—'} / {a.get('format') or '—'}"]
        pr = a.get("pr") or {}
        s = a.get("sentiment") or {}
        lines += ["", "## P 码（情节层）", ""]
        if pr.get("p_codes"):
            lines += ["| P 码 | 名称 | 来源 | 证据 |", "|---|---|---|---|"]
            for p in pr["p_codes"]:
                lines.append(f"| {p['id']} | {p['name']} | {'+'.join(p.get('source', []))} | {p.get('evidence', '')} |")
        else:
            lines.append("（未命中）")
        hit_r = {k: v for k, v in (pr.get("r_codes") or {}).items() if v not in (None, "", "无")}
        lines += ["", f"## R 码（视觉特征，{len(hit_r)} 项命中）", ""]
        lines.append("、".join(f"{k}={v}" for k, v in hit_r.items()) if hit_r else "（无）")
        lines += ["", f"- 置信度：{pr.get('confidence')}"
                 + (f"　规则层候选：{'/'.join(pr.get('rule_p_candidates') or [])}" if pr.get("rule_p_candidates") else "")]
        # 情感
        lines += ["", "## 内容情绪（四分类，AI 预标）", "",
                  f"- **{a.get('content_label') or '—'}**（人工复核请写 human_correction）"]
        if s.get("comments"):
            cm = s["comments"]
            mv = cm.get("mean_vad_llm") or {}
            lines.append(f"- 评论实测（{cm['n']} 条）：正 {cm['dist'].get('positive', 0):.1%} / 负 {cm['dist'].get('negative', 0):.1%} / 中 {cm['dist'].get('neutral', 0):.1%}，净情绪 {cm['net']}"
                         + f"　均值 VAD：v={mv.get('v')} a={mv.get('a')} d={mv.get('d')}")
        pm = s.get("pr_mapping") or {}
        if pm:
            lines.append(f"- P/R→评论预测：{pm.get('label')}（v={pm.get('valence')}）分布 {pm.get('dist')}")
            lines.append(f"  - 依据：{pm.get('rationale')}")
        lines += ["", "## 内容理解", ""] + (a.get("content_summary") or "（无）").splitlines()
        lines += ["", "## 逐帧", "", "| 帧 | 时间 | 摘要 | 情感 |", "|---|---|---|---|"]
        for f in a["frame_analyses"]:
            lines.append(f"| {f.get('frame_index')} | {f.get('timestamp', 0):.1f}s | {(f.get('summary') or '').replace('|', '/')} | — |")
        return "\n".join(lines) + "\n"
