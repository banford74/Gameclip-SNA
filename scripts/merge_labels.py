#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把人工标注导出的 human_labels*.csv 合并回 data/clips.csv。

用法:
    python scripts/merge_labels.py human_labels_2026-11-26.csv [--clips data/clips.csv] [--dry-run]

行为:
  * 按 clip_id 匹配，写入 human_correction（JSON：stance/intensity/p_codes/r_codes/
    evidence/confidence/notes/annotated_at），review_status 置为 done
  * 原 clips.csv 备份为 clips.csv.bak-<时间>；--dry-run 只打印不写
"""
import argparse
import csv
import json
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # Gameclip-SNA
DEFAULT_CLIPS = ROOT / "data" / "clips.csv"
KEYS = ["stance", "intensity", "p_codes", "r_codes", "evidence", "confidence", "notes", "annotated_at"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("labels")
    ap.add_argument("--clips", type=Path, default=DEFAULT_CLIPS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    labels = {}
    with open(args.labels, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            cid = (r.get("clip_id") or "").strip()
            if cid:
                labels[cid] = {k: (r.get(k) or "").strip() for k in KEYS}
    print(f"labels: {len(labels)}")

    rows = list(csv.DictReader(open(args.clips, encoding="utf-8-sig")))
    fieldnames = list(rows[0].keys()) if rows else []
    updated, unknown = 0, []
    stance_dist = {}
    for r in rows:
        cid = r.get("clip_id", "")
        if cid in labels:
            lab = labels[cid]
            if not lab.get("stance"):
                continue
            r["human_correction"] = json.dumps(lab, ensure_ascii=False)
            r["review_status"] = "done"
            updated += 1
            stance_dist[lab["stance"]] = stance_dist.get(lab["stance"], 0) + 1
        else:
            continue
    unknown = sorted(set(labels) - {r.get("clip_id") for r in rows})
    print(f"matched={updated} unknown_ids={len(unknown)}")
    if stance_dist:
        print("stance:", json.dumps(stance_dist, ensure_ascii=False))
    if unknown:
        print("unknown (前5):", unknown[:5])
    if args.dry_run:
        print("dry-run: nothing written")
        return
    backup = args.clips.with_name(args.clips.name + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(args.clips, backup)
    with open(args.clips, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"written: {args.clips} (backup {backup.name})")


if __name__ == "__main__":
    main()
