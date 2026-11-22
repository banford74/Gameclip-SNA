"""快手适配器（目标4）。

- 视频 ID 解析：支持 https://www.kuaishou.com/short-video/{id}
- 评论采集：浏览器自动化（BrowserCommentScraper），选择器随前端变化，集中维护
"""
from __future__ import annotations

import re
from typing import List

from ..platforms.base import Comment, PlatformAdapter, VideoMetadata
from ..platforms.browser_scraper import BrowserCommentScraper


class KuaishouAdapter(PlatformAdapter):
    platform = "kuaishou"

    def parse_video_id(self, url: str) -> str:
        m = re.search(r"/short-video/([\w-]+)", url)
        return m.group(1) if m else url

    def comment_selectors(self) -> dict:
        return {
            "item": ".comment-item",       # 快手网页端评论条目
            "user": ".author-name",
            "text": ".comment-text",
            "likes": ".like-count",
            "time": ".comment-time",
        }

    def get_metadata(self, url: str) -> VideoMetadata:
        vid = self.parse_video_id(url)
        return VideoMetadata(platform=self.platform, video_id=vid, url=url)

    def collect_comments(self, url: str, max_comments: int = 200,
                         use_browser: bool = True) -> List[Comment]:
        if use_browser:
            return BrowserCommentScraper().scrape(url, self, max_comments)
        return []
