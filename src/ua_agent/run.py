# -*- coding: utf-8 -*-
"""
CLI：一条命令跑完「下载 → 抽帧 → 画面理解 → 十级打标 → 报告 + 标注」。

  python -m pipeline.ua_agent.run --video path/x.mp4 [--version CG37]
  python -m pipeline.ua_agent.run --url "https://www.douyin.com/video/xxx" [--keep-video]
  python -m pipeline.ua_agent.run --video x.mp4 --comments-file comments.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent import ClipAgent
from .knowledge import GENERIC_VERSION


def _download(url: str) -> str:
    """抖音无登录降级下载（仓库自包含实现）。"""
    from .download import download_douyin
    out_dir = Path(__file__).resolve().parent / "outputs" / "_downloads"
    return download_douyin(url, str(out_dir))


def main(argv=None):
    ap = argparse.ArgumentParser(description="UA ClipAgent：视频 → 十级标签 + 报告")
    ap.add_argument("--video", help="本地视频路径")
    ap.add_argument("--url", help="平台链接（走无登录下载）")
    ap.add_argument("--version", default=GENERIC_VERSION, help="版本（CG36/CG37/通用版本）")
    ap.add_argument("--labels", choices=["pr", "ua10", "both"], help="标签模式（默认取 config labels.mode）")
    ap.add_argument("--game", default="", help="游戏名（进 clips.csv，供配比检查）")
    ap.add_argument("--format", dest="format_", default="", help="形态（实机录屏/短剧/攻略/音乐舞蹈/混剪/真人/图文）")
    ap.add_argument("--out", help="输出目录（默认 outputs/<md5>）")
    ap.add_argument("--comments-file", help="评论 json（字符串数组或 {text} 数组）")
    ap.add_argument("--config", help="config.yaml 路径")
    ap.add_argument("--knowledge", help="knowledge.json 路径（默认 agent/knowledge.json）")
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
        comments = json.loads(Path(args.comments_file).read_text(encoding="utf-8"))

    agent = ClipAgent(config_path=args.config, knowledge_path=args.knowledge, labels=args.labels)
    res = agent.analyze(video, version=args.version, url=url, comments=comments, out_dir=args.out,
                        game=args.game, format_=args.format_)
    print(json.dumps({"clip_id": res["clip_id"], "out_dir": res["out_dir"],
                      "name": res["tags"].get("规范名"), "tags": res["tags"],
                      "pr_p": [p["id"] for p in ((res.get("pr") or {}).get("p_codes") or [])],
                      "pr_confidence": (res.get("pr") or {}).get("confidence"),
                      "elapsed_s": res["annotation"]["elapsed_s"]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
