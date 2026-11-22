# -*- coding: utf-8 -*-
"""抖音无登录下载（移动端 feed 接口 + CDN 直链）——仓库自包含版本，无外部依赖。

用法：
    from .download import download_douyin
    path = download_douyin("https://www.douyin.com/video/7709870849365478116", "data/raw")

链路：aweme_id → feed API → bit_rate 最高档 → CDN 直链（带 Referer）→ 落盘 + meta
坑：feed 返回多条推荐位必须按 aweme_id 匹配；按 bit_rate 降序选档；必带 Referer；多 CDN 轮换
详见 docs/DOUYIN-DOWNLOAD-PLAYBOOK.md
"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

UA = "com.ss.android.ugc.aweme/290100 (Linux; U; Android 13; zh_CN)"


def _open(url: str, headers: dict, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, timeout=timeout).read()


def download_douyin(url_or_id: str, out_dir: str) -> str:
    m = re.search(r"/video/(\d+)", url_or_id) or re.search(r"(\d{15,})", url_or_id)
    if not m:
        raise ValueError(f"无法解析 aweme_id：{url_or_id}")
    aweme_id = m.group(1)
    feed = (f"https://aweme.snssdk.com/aweme/v1/feed/?aweme_id={aweme_id}"
            "&aid=1128&version_code=290100&device_platform=android&os_version=13")
    data = json.loads(_open(feed, {"User-Agent": UA}, 60).decode("utf-8"))
    lst = data.get("aweme_list") or []
    target = next((a for a in lst if str(a.get("aweme_id")) == aweme_id), None)
    if not target:
        raise RuntimeError(f"feed 未命中 aweme_id={aweme_id}（风控/删除/地区限制）")
    video = target.get("video") or {}
    tiers = [t for t in (video.get("bit_rate") or [])
             if (t.get("play_addr") or {}).get("url_list")]
    tiers.sort(key=lambda t: t.get("bit_rate", 0), reverse=True)
    urls = (tiers[0]["play_addr"]["url_list"] if tiers
            else (video.get("play_addr") or {}).get("url_list") or [])
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"{aweme_id}.mp4"
    for u in urls[:4]:
        try:
            buf = _open(u, {"User-Agent": UA, "Referer": "https://www.douyin.com/", "Accept": "*/*"})
            if len(buf) > 100_000:
                dest.write_bytes(buf)
                meta = {"aweme_id": aweme_id, "desc": target.get("desc", ""),
                        "duration_s": (video.get("duration") or 0) / 1000,
                        "author": (target.get("author") or {}).get("nickname"),
                        "gear": (tiers[0] if tiers else {}).get("gear_name", "default"),
                        "size_bytes": len(buf)}
                (out / f"{aweme_id}.meta.json").write_text(
                    json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
                return str(dest)
        except Exception:
            continue
    raise RuntimeError("所有 CDN 域名均失败（可能是签名过期/风控）")
