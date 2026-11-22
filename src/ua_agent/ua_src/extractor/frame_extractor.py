"""目标1：视频抽帧。

从本地视频文件按固定时间间隔抽帧，必要时可结合场景变化抽帧。
输出帧图片到 output_dir，并返回帧元数据列表。
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from typing import List, Optional

import cv2

from .. import utils


@dataclass
class Frame:
    path: str                 # 帧图片绝对路径
    index: int                # 全局序号（从 0 开始）
    timestamp: float          # 在视频中的时间（秒）
    width: int = 0
    height: int = 0
    md5: str = ""             # 图片内容指纹，便于去重追溯

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "index": self.index,
            "timestamp": round(self.timestamp, 3),
            "width": self.width,
            "height": self.height,
            "md5": self.md5,
        }


def _resize_frame(frame: cv2.typing.MatLike, long_edge: int):
    if not long_edge or long_edge <= 0:
        return frame
    h, w = frame.shape[:2]
    scale = long_edge / max(w, h)
    if scale >= 1.0:
        return frame
    new_w, new_h = int(w * scale), int(h * scale)
    return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)


def extract_frames(
    video_path: str,
    output_dir: str,
    interval_sec: float = 2.0,
    max_frames: int = 80,
    resize_long_edge: int = 1280,
    scene_change: bool = False,
    scene_threshold: float = 0.35,
    ext: str = "jpg",
) -> List[Frame]:
    """抽帧主函数。

    参数:
        video_path:       本地视频路径
        output_dir:       帧输出目录（不存在则创建）
        interval_sec:     时间间隔抽帧步长
        max_frames:       最大抽帧数
        resize_long_edge: 长边缩放像素（0 不缩放）
        scene_change:     是否在间隔抽帧之外，额外保留场景切换帧
        scene_threshold:  场景切换的直方图差异阈值
    返回:
        List[Frame]
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"视频不存在: {video_path}")

    os.makedirs(output_dir, exist_ok=True)
    # 清空旧帧，避免混淆
    for f in os.listdir(output_dir):
        if f.endswith(f".{ext}"):
            try:
                os.remove(os.path.join(output_dir, f))
            except OSError:
                pass

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    interval_frames = max(1, int(round(interval_sec * fps)))

    frames: List[Frame] = []
    idx = 0
    prev_hist = None
    last_saved_idx = -interval_frames  # 控制间隔
    frame_pos = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_pos += 1

        is_interval = (frame_pos - last_saved_idx) >= interval_frames
        is_scene = False
        if scene_change and prev_hist is not None:
            hist = cv2.calcHist([frame], [0, 1, 2], None, [8, 8], [0, 256, 0, 256])
            cv2.normalize(hist, hist)
            corr = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
            if (1.0 - corr) >= scene_threshold:
                is_scene = True
        try:
            hist_now = cv2.calcHist([frame], [0, 1, 2], None, [8, 8], [0, 256, 0, 256])
            cv2.normalize(hist_now, hist_now)
            prev_hist = hist_now
        except cv2.error:
            pass

        if is_interval or is_scene:
            if len(frames) >= max_frames:
                break
            out = _resize_frame(frame, resize_long_edge)
            h, w = out.shape[:2]
            ts = frame_pos / fps if fps else frame_pos
            fname = f"frame_{idx:05d}_t{ts:07.2f}.{ext}"
            fpath = os.path.join(output_dir, fname)
            cv2.imwrite(fpath, out, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            frames.append(Frame(
                path=fpath, index=idx, timestamp=ts,
                width=w, height=h, md5=utils.file_md5(fpath),
            ))
            last_saved_idx = frame_pos
            idx += 1

    cap.release()
    return frames


def video_info(video_path: str) -> dict:
    """返回视频基础信息（分辨率、时长、fps、帧数）。"""
    cap = cv2.VideoCapture(video_path)
    info = {
        "path": video_path,
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0),
        "fps": round(cap.get(cv2.CAP_PROP_FPS) or 0, 3),
        "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0),
    }
    info["duration_sec"] = round(info["frame_count"] / info["fps"], 2) if info["fps"] else 0
    cap.release()
    return info
