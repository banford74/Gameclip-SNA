"""目标4 编排：评论采集入口。

按平台选择适配器；优先从本地文件导入（离线/手动导出），否则走浏览器自动化。
"""
from __future__ import annotations

from typing import List, Tuple

from ..platforms.base import Comment, VideoMetadata, load_comments_from_file
from ..platforms.douyin import DouyinAdapter
from ..platforms.kuaishou import KuaishouAdapter


class CommentCollector:
    def __init__(self, platform: str = "douyin", local_file: str = "", use_browser: bool = True):
        self.platform = platform
        self.local_file = local_file
        self.use_browser = use_browser
        self.adapter = DouyinAdapter() if platform == "douyin" else KuaishouAdapter()

    def collect(self, url: str, max_comments: int = 200) -> Tuple[VideoMetadata, List[Comment]]:
        meta = self.adapter.get_metadata(url)
        if self.local_file:
            comments = load_comments_from_file(self.local_file)
        else:
            comments = self.adapter.collect_comments(url, max_comments, self.use_browser)
        return meta, comments[:max_comments]
