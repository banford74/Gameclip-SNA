"""目标2：关键帧筛选。

从抽出的所有帧中，按以下规则筛选信息量高的关键帧：
  1. 丢弃模糊帧（拉普拉斯方差 < blur_threshold）
  2. 感知哈希去重（汉明距离 < dedup_hamming 的视为重复，保留首个）
  3. 可选：仅在场景发生明显变化时保留，进一步压缩数量
输出筛选后的关键帧列表，显著降低后续大模型调用成本。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from ..extractor.frame_extractor import Frame
from .. import utils


@dataclass
class SelectionReport:
    total: int
    dropped_blur: int
    dropped_dup: int
    kept: int
    details: List[Dict] = None  # 每帧的筛选轨迹，便于追溯

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "dropped_blur": self.dropped_blur,
            "dropped_dup": self.dropped_dup,
            "kept": self.kept,
            "details": self.details or [],
        }


def select_keyframes(
    frames: List[Frame],
    blur_threshold: float = 60.0,
    dedup_hamming: int = 12,
    scene_change_threshold: float = 0.35,
    use_scene_filter: bool = False,
    verbose: bool = False,
) -> (List[Frame], SelectionReport):
    """筛选关键帧。

    参数:
        frames:             抽帧得到的 Frame 列表（建议按时间排序）
        blur_threshold:     清晰度阈值，低于此值丢弃
        dedup_hamming:      感知哈希去重汉明距离
        scene_change_threshold: 场景过滤阈值（use_scene_filter=True 时生效）
        use_scene_filter:   开启后，仅保留与前一关键帧场景差异足够大的帧
    返回:
        (关键帧列表, SelectionReport)
    """
    kept: List[Frame] = []
    seen_hashes: List[str] = []
    dropped_blur = 0
    dropped_dup = 0
    details: List[Dict] = []

    for fr in frames:
        score = utils.blur_score(fr.path)
        h = utils.dhash(fr.path)
        is_blur = score < blur_threshold
        is_dup = any(utils.hamming(h, s) < dedup_hamming for s in seen_hashes)

        reason = "keep"
        if is_blur:
            reason = "blur"
            dropped_blur += 1
        elif is_dup:
            reason = "dup"
            dropped_dup += 1

        if reason == "keep":
            if use_scene_filter and kept:
                dist = utils.histogram_distance(kept[-1].path, fr.path)
                if dist < scene_change_threshold:
                    reason = "scene_stable"
                    dropped_dup += 1  # 场景无变化，视作冗余
                    if verbose:
                        details.append({"index": fr.index, "reason": reason,
                                        "blur": round(score, 2), "scene_dist": round(dist, 3)})
                    continue
            kept.append(fr)
            seen_hashes.append(h)

        if verbose:
            details.append({
                "index": fr.index,
                "reason": reason,
                "blur": round(score, 2),
                "hash": h,
            })

    report = SelectionReport(
        total=len(frames),
        dropped_blur=dropped_blur,
        dropped_dup=dropped_dup,
        kept=len(kept),
        details=details,
    )
    return kept, report
