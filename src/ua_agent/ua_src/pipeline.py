"""顶层编排：把 6 个子目标串成一条可运行的流水线。

调用顺序：
  G1 抽帧 → G2 关键帧筛选 → G3 多模态画面识别
                              ↓
                  G4 评论采集 → G5 评论情感 → G6 聚合与报告
"""
from __future__ import annotations

import os
from typing import List, Optional

from .comments.comment_collector import CommentCollector
from .comments.sentiment_analyzer import SentimentAnalyzer, sentiment_summary
from .config import Config, load_config
from .extractor.frame_extractor import extract_frames, video_info
from .extractor.keyframe_selector import select_keyframes
from .report.aggregator import assemble_result
from .vision.frame_analyzer import analyze_frames, summarize_across_frames
from .vision.vlm_client import VLMClient


class Pipeline:
    def __init__(self, config: Config):
        self.cfg = config
        self.vlm = VLMClient.from_config(config.vlm)

    def run(
        self,
        video_path: str,
        video_url: Optional[str] = None,
        local_comments: Optional[str] = None,
    ) -> dict:
        cfg = self.cfg
        # ---------- G1 抽帧 ----------
        vid_info = video_info(video_path)
        frames = extract_frames(
            video_path,
            output_dir=cfg.frames.get("output_dir", "outputs/frames"),
            interval_sec=cfg.frames.get("interval_sec", 2.0),
            max_frames=cfg.frames.get("max_frames", 80),
            resize_long_edge=cfg.frames.get("resize_long_edge", 1280),
        )
        # ---------- G2 关键帧筛选 ----------
        keyframes, selection = select_keyframes(
            frames,
            blur_threshold=cfg.keyframe.get("blur_threshold", 60.0),
            dedup_hamming=cfg.keyframe.get("dedup_hamming", 12),
            scene_change_threshold=cfg.keyframe.get("scene_change_threshold", 0.35),
        )
        # ---------- G3 画面识别 ----------
        analyses = analyze_frames(keyframes, self.vlm)
        cross = summarize_across_frames(analyses)

        # ---------- G4 评论采集 ----------
        meta, comments = VideoMetadata_empty(), []
        if video_url or local_comments:
            collector = CommentCollector(
                platform=cfg.comments.get("platform", "douyin"),
                local_file=local_comments or cfg.comments.get("local_file", ""),
                use_browser=cfg.comments.get("use_browser", True),
            )
            if video_url:
                meta, comments = collector.collect(
                    video_url, max_comments=cfg.comments.get("max_comments", 200))
            elif local_comments:
                from .platforms.base import load_comments_from_file
                comments = load_comments_from_file(local_comments)

        # ---------- G5 评论情感 ----------
        sa = SentimentAnalyzer(self.vlm)
        sentiment_results = sa.analyze(comments, use_llm=True) if comments else []
        sentiment_sum = sentiment_summary(sentiment_results) if sentiment_results else {}

        # ---------- G6 聚合 ----------
        result = assemble_result(
            source=video_url or video_path,
            vid_info=vid_info,
            selection=selection,
            frame_analyses=analyses,
            cross=cross,
            metadata=meta,
            comments=comments,
            sentiment_results=sentiment_results,
            sentiment_sum=sentiment_sum,
        )
        return result


def VideoMetadata_empty():
    from .platforms.base import VideoMetadata
    return VideoMetadata(platform="", video_id="", url="")
