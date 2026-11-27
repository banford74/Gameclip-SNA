#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补齐缺失的 preview（480p 预览片）到 GitHub Pages，并回写 clips.csv 的 preview_url。

背景：目标集 1053 条里只有 311 条推过 media/review/*.mp4，其余 741 条标注页只能显示一张
关键帧 + 跳转原片链接——单帧判不出 mixed，标注质量差。这个脚本把缺的补齐。

用法：
    python scripts/add_previews.py --manifest _probe/preview_manifest.json   # 只生成上传清单
    python scripts/add_previews.py --apply        # 上传完再回写 clips.csv 的 preview_url
"""
import argparse
import csv
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WS = ROOT.parent
CSV = ROOT / "data" / "clips.csv"
PREVIEWS = Path("D:/ua_data/previews")
BASE = "https://banford74.github.io/Gameclip-SNA/media/review/"
TARGET_STATUS = ("pending", "pending_analysis")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=str(WS / "_probe" / "preview_manifest.json"))
    ap.add_argument("--apply", action="store_true", help="回写 clips.csv 的 preview_url")
    args = ap.parse_args()

    with open(CSV, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)

    todo, manifest, no_local = [], [], []
    for r in rows:
        if r.get("review_status") not in TARGET_STATUS:
            continue
        if (r.get("preview_url") or "").strip():
            continue
        p = PREVIEWS / f"{r['clip_id']}.mp4"
        if not p.exists():
            no_local.append(r["clip_id"])
            continue
        todo.append(r)
        manifest.append({"local": str(p).replace("\\", "/"),
                         "repo": f"docs/media/review/{r['clip_id']}.mp4"})

    Path(args.manifest).write_text(json.dumps(manifest, ensure_ascii=False, indent=0), encoding="utf-8")
    mb = sum(os.path.getsize(m["local"]) for m in manifest) / 1e6
    print(f"need preview: {len(todo)} files, {mb:.1f} MB -> manifest {args.manifest}")
    if no_local:
        print(f"no local file for {len(no_local)} clips: {no_local[:5]}")

    if args.apply:
        for r in todo:
            r["preview_url"] = BASE + r["clip_id"] + ".mp4"
        with open(CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(f"clips.csv updated: {len(todo)} rows got preview_url")


if __name__ == "__main__":
    main()
