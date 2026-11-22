"""抖音「买量广告」信息流爬虫（带登录态）。

适用场景：已知 和平精英 等关键词，在抖音中检索带「广告」标识的信息流素材，
抽取 标题/作者/发布时间/封面/链接，并尝试下载视频供 G1–G6 分析流水线消费。

重要前提（已实测）：
  - 抖音搜索与巨量创意(cc.oceanengine.com)是不同域，Cookie 不通用。
    抖音主站(www.douyin.com)必须单独提供已登录 Cookie。
  - 抖音是实时推荐信息流，无法精确回溯历史日期窗口(如 8/7–8/9)；
    搜索到的多为自然内容，真正的买量广告需用「广告/了解详情/下载游戏」等信号识别。
  - 视频下载依赖登录态 + 抖音签名，部分视频可能 403/需签名，会安全跳过并标注。
本爬虫支持传入已登录 Cookie 进行真实抓取；拿到数据后即可接入 G1–G6 分析。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Optional

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# 买量广告信号：命中任一即视为广告素材（强弱不同）
AD_SIGNALS = ["广告", "了解详情", "下载游戏", "立即下载", "下载", "点击进入", "推广"]

WALL_KEYWORDS = ["登录后即可", "立即登录", "扫码登录", "手机号登录", "请先登录", "登录后观看"]


@dataclass
class AdCreative:
    platform: str = "douyin"
    keyword: str = ""
    title: str = ""
    author: str = ""
    publish_date: str = ""       # 页面可见的发布时间文本
    publish_ts: Optional[float] = None
    is_ad: bool = False
    ad_tag: str = ""             # 命中的最强广告信号
    cover: str = ""
    url: str = ""
    video_path: str = ""         # 下载到本地的视频路径（如成功）
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["raw"] = self.raw
        del d["raw"]  # raw 中可能含不可序列化内容，改存精简字段
        d["extra"] = {
            "video_path": self.video_path,
            "cover": self.cover,
        }
        return d


class DouyinAdsCrawler:
    def __init__(self, cookies_path: Optional[str] = None, headless: bool = True,
                 source: str = "douyin"):
        self.cookies_path = cookies_path
        self.headless = headless
        self.source = source  # douyin / oceanengine
        self._check_playwright()

    @staticmethod
    def _check_playwright():
        try:
            import playwright  # noqa: F401
        except ImportError:
            raise ImportError("请先安装: pip install playwright && playwright install chromium")

    def _search_url(self, keyword: str) -> str:
        import urllib.parse
        kw = urllib.parse.quote(keyword)
        if self.source == "oceanengine":
            return f"https://cc.oceanengine.com/creative/search?keyword={kw}"
        return f"https://www.douyin.com/search/{kw}"

    @staticmethod
    def _normalize_cookies(raw):
        """把 Cookie-Editor 导出格式转成 Playwright add_cookies 认的格式。"""
        out = []
        for c in raw:
            if "name" not in c or "value" not in c:
                continue
            item = {
                "name": c["name"],
                "value": c["value"],
                "domain": c.get("domain", ""),
                "path": c.get("path", "/"),
            }
            if c.get("secure"):
                item["secure"] = True
            if c.get("httpOnly"):
                item["httpOnly"] = True
            exp = c.get("expirationDate", c.get("expires"))
            if exp:
                try:
                    item["expires"] = int(float(exp))
                except (TypeError, ValueError):
                    pass
            s = c.get("sameSite")
            if s in ("Lax", "Strict", "None"):
                item["sameSite"] = s
            elif s == "no_restriction":
                item["sameSite"] = "None"
            out.append(item)
        return out

    def _inject_cookies(self, context):
        if not self.cookies_path or not os.path.exists(self.cookies_path):
            return False
        with open(self.cookies_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        cookies = self._normalize_cookies(raw)
        context.add_cookies(cookies)
        return True

    @staticmethod
    def _parse_date(text: str) -> Optional[float]:
        m = re.search(r"(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})", text)
        if m:
            try:
                return datetime(*map(int, m.groups())).timestamp()
            except ValueError:
                return None
        return None

    def _is_wall(self, body: str) -> bool:
        return any(k in body for k in WALL_KEYWORDS)

    # ------------------------------------------------------------------ #
    # 主爬取
    # ------------------------------------------------------------------ #
    def crawl(self, keyword: str = "和平精英", max_items: int = 6,
              date_from: Optional[str] = None, date_to: Optional[str] = None,
              scroll_times: int = 20, fetch_video: bool = False,
              video_dir: Optional[str] = None) -> List[AdCreative]:
        from playwright.sync_api import sync_playwright

        url = self._search_url(keyword)
        results: List[AdCreative] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            ctx = browser.new_context(user_agent=UA)
            self._inject_cookies(ctx)
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000)

            body = page.evaluate("document.body ? document.body.innerText : ''") or ""
            if self._is_wall(body):
                browser.close()
                raise PermissionError(
                    "命中登录墙：抖音/巨量创意要求登录。请提供对应站点已登录的 Cookie "
                    f"({self.cookies_path or '<cookies.json>'}) 再试。")

            # 抖音：等待视频卡片加载（SPA 异步渲染）
            if self.source == "douyin":
                try:
                    page.wait_for_selector('a[href*="/video/"]', timeout=20000)
                except Exception:
                    pass

            # 滚动加载更多
            for _ in range(scroll_times):
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(1200)

            cards = page.query_selector_all('a[href*="/video/"]')
            seen = set()
            for node in cards[: max_items * 4]:
                href = node.get_attribute("href") or ""
                if "/video/" not in href:
                    continue
                if href in seen:
                    continue
                seen.add(href)
                full = href if href.startswith("http") else "https://www.douyin.com" + href
                text = (node.inner_text() or "").strip()
                ad = AdCreative(platform=self.source, keyword=keyword, url=full)
                ad.raw["href"] = href

                # 广告信号识别
                hit = next((s for s in AD_SIGNALS if s in text), "")
                if hit:
                    ad.is_ad = True
                    ad.ad_tag = hit

                # 标题/作者/时间（按行切分）
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                if lines:
                    ad.title = lines[0]
                    if len(lines) > 1:
                        ad.author = lines[1]
                for l in lines:
                    ts = self._parse_date(l)
                    if ts:
                        ad.publish_date = l
                        ad.publish_ts = ts
                        break
                results.append(ad)
                if len(results) >= max_items * 3:
                    break
            browser.close()

        # 时间窗过滤
        if date_from or date_to:
            lo = self._parse_date(date_from) if date_from else None
            hi = self._parse_date(date_to) if date_to else None
            filtered = []
            for r in results:
                t = r.publish_ts
                if t is None:
                    continue
                if lo and t < lo:
                    continue
                if hi and t > hi:
                    continue
                filtered.append(r)
            results = filtered

        # 可选：下载视频
        if fetch_video:
            vdir = video_dir or os.path.join("outputs", "ads", "videos")
            os.makedirs(vdir, exist_ok=True)
            for ad in results:
                if ad.url:
                    try:
                        ad.video_path = self.download_video(ad.url, vdir) or ""
                    except Exception as e:
                        print(f"  [warn] 下载失败 {ad.url}: {e}")
                        ad.video_path = ""
        return results

    # ------------------------------------------------------------------ #
    # 进详情页抓真实视频流地址并下载
    # ------------------------------------------------------------------ #
    def download_video(self, video_url: str, out_dir: str) -> Optional[str]:
        """进入抖音视频详情页，监听真实视频流响应并下载到本地。

        返回本地路径；失败返回 None。抖音 web 视频常需签名，失败时安全返回 None。
        """
        import urllib.request
        from playwright.sync_api import sync_playwright

        os.makedirs(out_dir, exist_ok=True)
        video_urls: List[tuple] = []  # (size_hint, url)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            ctx = browser.new_context(user_agent=UA)
            self._inject_cookies(ctx)
            page = ctx.new_page()

            def on_resp(resp):
                u = resp.url
                ct = resp.headers.get("content-type") or ""
                if ("video" in ct or u.endswith(".mp4") or ".m3u8" in u
                        or "vod" in u or "douyinvod" in u):
                    try:
                        size = len(resp.body() or b"")
                    except Exception:
                        size = 0
                    video_urls.append((size, u))

            page.on("response", on_resp)
            page.goto(video_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(6000)
            # 尝试触发播放
            for sel in ["video", '[class*="play"]', "xgplayer"]:
                try:
                    page.click(sel, timeout=2000)
                    break
                except Exception:
                    pass
            page.wait_for_timeout(5000)
            browser.close()

        if not video_urls:
            return None

        # 取体积最大的作为最佳源
        best = sorted(video_urls, key=lambda x: x[0], reverse=True)[0][1]

        # mp4 直链直接下载
        if best.endswith(".mp4") or "mp4" in best.split("?")[0]:
            out = os.path.join(out_dir, self._safe_name(video_url) + ".mp4")
            if self._http_download(best, out):
                return out
            return None

        # m3u8 分片：用 ffmpeg 合并
        if ".m3u8" in best:
            out = os.path.join(out_dir, self._safe_name(video_url) + ".mp4")
            rc = os.system(
                f'ffmpeg -y -loglevel error -headers "User-Agent: {UA}\\r\\nReferer: https://www.douyin.com/\\r\\n" '
                f'-i "{best}" -c copy "{out}"')
            if rc == 0 and os.path.exists(out) and os.path.getsize(out) > 10000:
                return out
            return None
        return None

    @staticmethod
    def _safe_name(video_url: str) -> str:
        h = hashlib.md5(video_url.encode()).hexdigest()[:12]
        return f"douyin_{h}"

    @staticmethod
    def _http_download(url: str, out_path: str) -> bool:
        import urllib.request
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Referer": "https://www.douyin.com/"})
            with urllib.request.urlopen(req, timeout=40) as r, open(out_path, "wb") as f:
                data = r.read()
                if len(data) < 10000:
                    return False
                f.write(data)
            return True
        except Exception:
            # 回退到 requests（若可用）
            try:
                import requests
                r = requests.get(url, headers={"User-Agent": UA,
                                  "Referer": "https://www.douyin.com/"}, timeout=40)
                if r.status_code == 200 and len(r.content) > 10000:
                    with open(out_path, "wb") as f:
                        f.write(r.content)
                    return True
            except Exception:
                pass
            return False

    def save(self, items: List[AdCreative], path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump([i.to_dict() for i in items], f, ensure_ascii=False, indent=2)
        return path
