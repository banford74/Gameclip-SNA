"""目标3：画面关键信息提取。

调用多模态大模型（VLMClient）对每张关键帧做结构化识别，输出：
  画面文字(OCR) / 品牌Logo / 主体产品 / 场景 / 人物 / 关键营销点 / 是否含字幕 / 一句话总结
结果以结构化 JSON 返回，解析失败时回退为文本摘要。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional

from ..extractor.frame_extractor import Frame
from ..vision.vlm_client import VLMClient

SYSTEM_PROMPT = (
    "你是一名资深内容审核与品牌物料分析师，擅长从视频单帧画面中提取关键信息。"
    "请只输出 JSON，不要任何解释或 markdown 代码块。"
)

USER_PROMPT = (
    "请分析这张视频帧，提取以下字段（严格 JSON 格式）：\n"
    "{\n"
    '  "on_screen_text": ["画面中可见的文字/标题/字幕/口播文案，逐条列出"],\n'
    '  "brand": "出现的品牌或 Logo 名称，没有则为 null",\n'
    '  "subject": "画面主体或推广的产品/服务",\n'
    '  "scene": "拍摄场景，如 演播室/门店/户外/电商详情页",\n'
    '  "people": "出现的人物及角色，如 主播/达人/用户",\n'
    '  "key_points": ["本帧想传达的关键营销点，逐条列出"],\n'
    '  "has_subtitle": true/false,\n'
    '  "summary": "一句话总结该帧核心信息"\n'
    "}"
)


@dataclass
class FrameAnalysis:
    frame_index: int
    timestamp: float
    image_path: str
    on_screen_text: List[str] = field(default_factory=list)
    brand: Optional[str] = None
    subject: str = ""
    scene: str = ""
    people: str = ""
    key_points: List[str] = field(default_factory=list)
    has_subtitle: bool = False
    summary: str = ""
    raw: str = ""          # 模型原始输出，便于追溯
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "frame_index": self.frame_index,
            "timestamp": self.timestamp,
            "image_path": self.image_path,
            "on_screen_text": self.on_screen_text,
            "brand": self.brand,
            "subject": self.subject,
            "scene": self.scene,
            "people": self.people,
            "key_points": self.key_points,
            "has_subtitle": self.has_subtitle,
            "summary": self.summary,
            "raw": self.raw,
            "error": self.error,
        }


def _extract_json(text: str) -> Optional[dict]:
    """从模型输出中尽量解析出 JSON（兼容 ```json 代码块 / 裸 JSON）。"""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 退一步：截取第一个 { 到最后一个 }
    s, e = text.find("{"), text.rfind("}")
    if s != -1 and e != -1 and e > s:
        try:
            return json.loads(text[s:e + 1])
        except json.JSONDecodeError:
            return None
    return None


def analyze_frame(frame: Frame, vlm: VLMClient) -> FrameAnalysis:
    out = vlm.chat(SYSTEM_PROMPT, USER_PROMPT, image_paths=[frame.path])
    result = FrameAnalysis(
        frame_index=frame.index, timestamp=frame.timestamp,
        image_path=frame.path, raw=out,
    )
    data = _extract_json(out)
    if not data:
        result.error = "JSON 解析失败"
        result.summary = out[:200]
        return result
    result.on_screen_text = data.get("on_screen_text") or []
    result.brand = data.get("brand")
    result.subject = data.get("subject") or ""
    result.scene = data.get("scene") or ""
    result.people = data.get("people") or ""
    result.key_points = data.get("key_points") or []
    result.has_subtitle = bool(data.get("has_subtitle", False))
    result.summary = data.get("summary") or ""
    return result


def analyze_frames(frames: List[Frame], vlm: VLMClient) -> List[FrameAnalysis]:
    return [analyze_frame(f, vlm) for f in frames]


def summarize_across_frames(analyses: List[FrameAnalysis]) -> dict:
    """跨帧聚合：提炼品牌、核心卖点、高频画面文字（供 G6 报告使用）。"""
    brands, points, texts = [], [], []
    for a in analyses:
        if a.brand:
            brands.append(a.brand)
        points.extend(a.key_points)
        texts.extend(a.on_screen_text)
    from collections import Counter
    return {
        "brands": [b for b, _ in Counter(brands).most_common(5)],
        "top_key_points": [p for p, _ in Counter(points).most_common(8)],
        "top_on_screen_text": [t for t, _ in Counter(texts).most_common(8)],
        "frame_summaries": [a.summary for a in analyses if a.summary],
    }
