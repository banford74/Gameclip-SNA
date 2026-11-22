"""目标6 底座：结果聚合。

把各子目标的产出汇总为一个统一结构，供报告生成与下游消费。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ..comments.sentiment_analyzer import SentimentResult
from ..extractor.frame_extractor import video_info
from ..extractor.keyframe_selector import SelectionReport
from ..platforms.base import Comment, VideoMetadata
from ..vision.frame_analyzer import FrameAnalysis


@dataclass
class AnalysisResult:
    source: str = ""                       # 视频源（路径或 URL）
    video_info: Dict = field(default_factory=dict)
    selection: Dict = field(default_factory=dict)
    frames: List[Dict] = field(default_factory=list)
    cross: Dict = field(default_factory=dict)     # 跨帧品牌/卖点/高频文字
    metadata: Dict = field(default_factory=dict)
    comment_count: int = 0
    sentiment: Dict = field(default_factory=dict)
    sentiment_details: List[Dict] = field(default_factory=list)
    raw: Dict = field(default_factory=dict)       # 透传，便于扩展

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "video_info": self.video_info,
            "selection": self.selection,
            "frames": self.frames,
            "cross": self.cross,
            "metadata": self.metadata,
            "comment_count": self.comment_count,
            "sentiment": self.sentiment,
            "sentiment_details": self.sentiment_details,
        }


def assemble_result(
    source: str,
    vid_info: dict,
    selection: SelectionReport,
    frame_analyses: List[FrameAnalysis],
    cross: dict,
    metadata: VideoMetadata,
    comments: List[Comment],
    sentiment_results: List[SentimentResult],
    sentiment_sum: dict,
) -> AnalysisResult:
    return AnalysisResult(
        source=source,
        video_info=vid_info,
        selection=selection.to_dict(),
        frames=[a.to_dict() for a in frame_analyses],
        cross=cross,
        metadata=metadata.to_dict(),
        comment_count=len(comments),
        sentiment=sentiment_sum,
        sentiment_details=[r.to_dict() for r in sentiment_results],
    )
