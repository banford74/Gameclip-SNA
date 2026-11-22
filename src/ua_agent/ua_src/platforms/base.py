"""目标4 基础：平台适配器抽象 + 评论数据模型。

抖音/快手 的网页评论接口带签名参数（X-Bogus / a_bogus 等），纯 requests 难以稳定调用。
因此本框架采用「浏览器自动化兜底 + 本地文件导入」双通道：
  - 有 playwright 且开启 use_browser 时，用浏览器滚动抓取评论区（见 BrowserCommentScraper）
  - 否则从本地 jsonl/csv 读取（适合手动导出的评论，也用于离线自测）
具体平台只需实现 metadata 解析与评论区选择器即可。
"""
from __future__ import annotations

import csv
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class Comment:
    id: str
    text: str
    user: str = ""
    likes: int = 0
    time: str = ""
    replies: int = 0
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["raw"] = self.raw
        return d


@dataclass
class VideoMetadata:
    platform: str
    video_id: str
    url: str
    title: str = ""
    author: str = ""
    description: str = ""
    likes: int = 0
    comments: int = 0
    shares: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class PlatformAdapter(ABC):
    platform: str = ""

    @abstractmethod
    def parse_video_id(self, url: str) -> str:
        ...

    @abstractmethod
    def get_metadata(self, url: str) -> VideoMetadata:
        ...

    @abstractmethod
    def comment_selectors(self) -> dict:
        """返回 playwright 抓取评论区所需的选择器。"""
        ...


def load_comments_from_file(path: str) -> List[Comment]:
    """从本地文件导入评论（jsonl 或 csv），用于离线/手动导出场景。

    jsonl 每行: {"text": "...", "user": "...", "likes": 0, "time": ""}
    csv 表头:    text,user,likes,time
    """
    comments: List[Comment] = []
    if path.endswith(".csv"):
        with open(path, "r", encoding="utf-8") as f:
            for i, row in enumerate(csv.DictReader(f)):
                comments.append(Comment(
                    id=f"c{i}", text=(row.get("text") or "").strip(),
                    user=row.get("user", ""), likes=int(row.get("likes") or 0),
                    time=row.get("time", ""),
                ))
    else:  # jsonl / json
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        data = json.loads(content) if content.startswith("[") else [
            json.loads(l) for l in content.splitlines() if l.strip()
        ]
        for i, d in enumerate(data):
            comments.append(Comment(
                id=str(d.get("id", f"c{i}")), text=(d.get("text") or "").strip(),
                user=d.get("user", ""), likes=int(d.get("likes") or 0),
                time=d.get("time", ""), replies=int(d.get("replies") or 0),
                raw=d,
            ))
    return [c for c in comments if c.text]
