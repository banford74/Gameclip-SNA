"""抖音适配器（目标4）。

- 视频 ID 解析：支持 https://www.douyin.com/video/{id}
- 评论采集：默认走浏览器自动化（BrowserCommentScraper），选择器随前端变化，已集中在此处便于维护
- 元数据：尽力从页面读取，失败则返回含 video_id 的最小结构
"""
from __future__ import annotations

import re
from typing import List

from ..platforms.base import Comment, PlatformAdapter, VideoMetadata
from ..platforms.browser_scraper import BrowserCommentScraper


class DouyinAdapter(PlatformAdapter):
    platform = "douyin"

    def parse_video_id(self, url: str) -> str:
        m = re.search(r"/video/(\w+)", url)
        return m.group(1) if m else url

    def comment_selectors(self) -> dict:
        # 抖音网页端 data-e2e 属性，随版本可能变化
        return {
            "item": '[data-e2e="comment-item"]',
            "user": '[data-e2e="comment-username"]',
            "text": '[data-e2e="comment-text"]',
            "likes": '[data-e2e="comment-like-count"]',
            "time": '[data-e2e="comment-time"]',
        }

    def get_metadata(self, url: str) -> VideoMetadata:
        vid = self.parse_video_id(url)
        return VideoMetadata(platform=self.platform, video_id=vid, url=url)

    def collect_comments(self, url: str, max_comments: int = 200,
                         use_browser: bool = True) -> List[Comment]:
        if use_browser:
            return BrowserCommentScraper().scrape(url, self, max_comments)
        return []
