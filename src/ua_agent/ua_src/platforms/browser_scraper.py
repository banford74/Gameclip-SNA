"""浏览器自动化评论采集器（playwright）。

抖音/快手 评论接口带签名，纯接口难稳定调用；用真实浏览器打开视频页、滚动加载评论区，
再按平台选择器提取文字/用户/点赞。选择器的稳定性随前端改版变化，已抽到各平台适配器里。
"""
from __future__ import annotations

import re
from typing import List

from ..platforms.base import Comment, PlatformAdapter


class BrowserCommentScraper:
    def __init__(self, headless: bool = True):
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "未安装 playwright。请执行: pip install playwright && playwright install chromium\n"
                "或配置 comments.local_file 直接读取本地导出的评论。"
            ) from e
        self.headless = headless

    @staticmethod
    def _to_int(s: str) -> int:
        if not s:
            return 0
        s = s.strip().replace(",", "")
        m = re.match(r"([\d.]+)\s*([万wW]?)", s)
        if not m:
            return 0
        val = float(m.group(1))
        if m.group(2):
            val *= 10000
        return int(val)

    def scrape(self, url: str, adapter: PlatformAdapter, max_comments: int = 200,
               scroll_times: int = 30) -> List[Comment]:
        from playwright.sync_api import sync_playwright

        sel = adapter.comment_selectors()
        comments: List[Comment] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=60000)
            # 等待评论区出现
            try:
                page.wait_for_selector(sel["item"], timeout=15000)
            except Exception:  # noqa: BLE001
                pass

            for _ in range(scroll_times):
                page.mouse.wheel(0, 2000)
                page.wait_for_timeout(800)
                items = page.query_selector_all(sel["item"])
                if len(items) >= max_comments:
                    break

            items = page.query_selector_all(sel["item"])
            for i, node in enumerate(items[:max_comments]):
                def _txt(sel_key):
                    el = node.query_selector(sel.get(sel_key, ""))
                    return el.inner_text().strip() if el else ""
                text = _txt("text")
                if not text:
                    continue
                comments.append(Comment(
                    id=f"{adapter.platform}_{i}",
                    text=text,
                    user=_txt("user"),
                    likes=self._to_int(_txt("likes")),
                    time=_txt("time"),
                ))
            browser.close()
        return comments
