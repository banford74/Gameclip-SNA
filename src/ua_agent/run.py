# -*- coding: utf-8 -*-
"""
CLI：下载 → 抽帧 → VLM 理解 → P/R 打标 → 情感 VAD → 报告/标注。

  python -m pipeline.ua_agent.run --video path/x.mp4 --game 和平精英 --format 实机录屏
  python -m pipeline.ua_agent.run --url "https://www.douyin.com/video/xxx"
  python -m pipeline.ua_agent.run --video x.mp4 --comments-file comments.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agent import ClipAgent


def _download(url: str) -> str:
    from .download import download_douyin
    out_dir = Path(__file__).resolve().parent / "outputs" / "_downloads"
    return download_douyin(url, str(out_dir))


def main(argv=None):
    ap = argparse.ArgumentParser(description="ClipAgent：视频 → P/R + 情感 VAD + 报告")
    ap.add_argument("--video", help="本地视频路径")
    ap.add_argument("--url", help="平台链接（无登录下载）")
    ap.add_argument("--out", help="输出目录（默认 outputs/<md5>）")
    ap.add_argument("--comments-file", help="评论 json（字符串数组或 [{text}]）")
    ap.add_argument("--game", default="", help="游戏名（进 clips.csv，供配比检查）")
    ap.add_argument("--format", dest="format_", default="", help="形态（实机录屏/短剧/攻略/音乐舞蹈/混剪/真人/图文）")
    ap.add_argument("--config", help="config.yaml 路径")
    args = ap.parse_args(argv)

    video = args.video
    url = args.url or ""
    if not video:
        if not url:
            ap.error("必须给 --video 或 --url")
        video = _download(url)
        print(f"[run] 已下载：{video}")

    comments = None
    if args.comments_file:
        raw = json.loads(Path(args.comments_file).read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw = raw.get("comments") or raw.get("rows") or []
        comments = raw

    agent = ClipAgent(config_path=args.config)
    res = agent.analyze(video, url=url, comments=comments, out_dir=args.out,
                        game=args.game, format_=args.format_)
    ann = res["annotation"]
    print(json.dumps({
        "clip_id": res["clip_id"], "out_dir": res["out_dir"],
        "pr_p": [p["id"] for p in (res["pr"] or {}).get("p_codes", [])],
        "pr_confidence": (res["pr"] or {}).get("confidence"),
        "content_label": ann.get("content_label"),
        "comment_vad": ann["sentiment"].get("comments"),
        "comment_pred": (ann["sentiment"].get("pr_mapping") or {}).get("dist"),
        "elapsed_s": ann["elapsed_s"],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
