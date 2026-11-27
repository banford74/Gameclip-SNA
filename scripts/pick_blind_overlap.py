#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""挑出「盲标 + 4 人重叠」轮用的 clip_id 清单（每游戏按条数比例，确定性）。

用途：现在的 4 人分工互不重叠，所以算不出标注一致性（κ）；而且页面会显示 AI 预标，
人工判断被锚定。这个 30 条的重叠盲标轮同时解决两件事：
  * 同一批条目 4 个人都标 → 可算 Fleiss κ / 两两一致率；
  * 页面用 --blind 抹掉 AI 结果 → 得到未被锚定的 gold（评测用）。

用法: python scripts/pick_blind_overlap.py [--n 30] [--out data/blind_ids.txt]
"""
import argparse
import csv
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "clips.csv"
GOLD = ROOT.parent / "portfolio" / "eval" / "gold.csv"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20261128)
    ap.add_argument("--out", default=str(ROOT / "data" / "blind_ids.txt"))
    args = ap.parse_args()

    labeled = set()
    if GOLD.exists():
        with open(GOLD, encoding="utf-8") as f:
            labeled = {r["clip_id"] for r in csv.DictReader(f)}

    pool = defaultdict(list)
    with open(CSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r.get("review_status") not in ("pending", "pending_analysis"):
                continue
            if r["clip_id"] in labeled or not r.get("pr_p"):
                continue
            if not (r.get("preview_url") or "").strip():   # 页面里放不出视频就没法标（盲标轮必须能看片）
                continue
            try:
                dur = float(r.get("duration_sec") or 0)
            except ValueError:
                dur = 0.0
            if dur and dur < 6:                      # 太短的片子没有可判定的情绪拍点
                continue
            pool[r.get("game") or "?"].append(r["clip_id"])

    total = sum(len(v) for v in pool.values())
    rng = random.Random(args.seed)
    picked = []
    for game in sorted(pool):
        ids = sorted(pool[game])
        rng.shuffle(ids)
        take = max(2, round(args.n * len(ids) / max(1, total)))
        picked += ids[:take]
    picked = sorted(picked)
    rng.shuffle(picked)
    picked = sorted(picked[: args.n])

    out = Path(args.out)
    out.write_text("\n".join(picked) + "\n", encoding="utf-8")
    games = {cid: g for g, ids in pool.items() for cid in ids}
    by_game = defaultdict(int)
    for cid in picked:
        by_game[games[cid]] += 1
    print(f"picked {len(picked)} clips from pool {total} -> {out}")
    print("by game:", dict(sorted(by_game.items())))


if __name__ == "__main__":
    main()
