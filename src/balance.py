# -*- coding: utf-8 -*-
"""
多游戏/多形态平衡检查：对照 configs/balance_plan.json 检查 manifest（或 clips.csv）。

manifest 每条至少含：game, format（形态），可选 outcome（pos/neg/neu/mixed）。
用法：
  python pipeline/balance.py manifest.json
  python pipeline/balance.py data/clips.csv
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

PLAN = Path(__file__).resolve().parent / "configs" / "balance_plan.json"


def load_rows(path: str) -> list[dict]:
    p = Path(path)
    if p.suffix.lower() == ".csv":
        with open(p, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    j = json.loads(p.read_text(encoding="utf-8"))
    return j if isinstance(j, list) else j.get("items", [])


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print("usage: python pipeline/balance.py <manifest.json|clips.csv>")
        return
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    rows = load_rows(argv[0])
    n = len(rows)
    print(f"样本 {n} 条\n")

    def dist(key: str) -> Counter:
        return Counter((r.get(key) or "未标注") for r in rows)

    for key, target in (("game", plan["games"]), ("format", plan["formats"])):
        c = dist(key)
        print(f"== {key} 分布 ==")
        for name, share in target.items():
            got = c.get(name, 0) / n if n else 0
            flag = "OK" if abs(got - share) <= 0.05 else ("缺口" if got < share else "超配")
            print(f"  {name:24s} 目标 {share:.0%}  实际 {got:.0%}  {flag}")
        for name in c:
            if name not in target and name != "未标注" and c[name]:
                print(f"  {name:24s} 目标 —      实际 {c[name]/n:.0%}  （计划外）")
        print()

    max_game = plan["constraints"]["max_single_game"]
    max_fmt = plan["constraints"]["max_single_format"]
    for key, lim in (("game", max_game), ("format", max_fmt)):
        c = dist(key)
        top = c.most_common(1)
        if top and n and top[0][1] / n > lim:
            print(f"[警告] {key} 单类占比 {top[0][0]}={top[0][1]/n:.0%} 超过上限 {lim:.0%}")

    if "pr_p" in rows[0]:
        c = Counter()
        for r in rows:
            for pid in (r.get("pr_p") or "").replace("、", ",").split(","):
                if pid.strip():
                    c[pid.strip()] += 1
        low = [f"{k}={v}" for k, v in c.items() if v < plan["constraints"]["min_per_p_code"]]
        print(f"== P 码覆盖 ==\n  出现码 {len(c)} 个；低于最小样本量({plan['constraints']['min_per_p_code']})：{low or '无'}")


if __name__ == "__main__":
    main()
