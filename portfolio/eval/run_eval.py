# -*- coding: utf-8 -*-
"""Score Task-A predictions (out/rows.csv) against a gold set (eval/gold.csv).

gold.csv columns:
    clip_id, stance, p_codes, r_codes
  - stance: positive|negative|neutral|mixed  (content stance, 4-class)
  - p_codes / r_codes: semicolon-joined (e.g. "P104;P107"), may be empty

    python eval/run_eval.py eval/gold.csv out/rows.csv
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict

STANCE = ["positive", "negative", "neutral", "mixed"]


def read_csv(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def set_metrics(gold_sets, pred_sets):
    """Micro precision/recall/F1 over code sets + exact-match rate."""
    tp = fp = fn = 0
    exact = 0
    for g, p in zip(gold_sets, pred_sets):
        g, p = set(g), set(p)
        tp += len(g & p)
        fp += len(p - g)
        fn += len(g - p)
        if g == p:
            exact += 1
    p_, r_, f_ = prf(tp, fp, fn)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(p_, 3),
            "recall": round(r_, 3), "f1": round(f_, 3),
            "exact_match": round(exact / max(1, len(gold_sets)), 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gold")
    ap.add_argument("pred")
    ap.add_argument("--json", action="store_true", help="dump machine-readable summary")
    args = ap.parse_args()
    gold = {r["clip_id"]: r for r in read_csv(args.gold)}
    pred = {r["clip_id"]: r for r in read_csv(args.pred)}

    ids = sorted(set(gold) & set(pred))
    missing = sorted(set(gold) - set(pred))
    print(f"gold={len(gold)} pred={len(pred)} matched={len(ids)} missing_in_pred={len(missing)}")
    if missing:
        print("  missing ids:", missing[:10])

    # ---- stance: accuracy + per-class P/R/F1 + confusion matrix ----
    cm = defaultdict(Counter)
    ok = 0
    for cid in ids:
        g = (gold[cid].get("stance") or "").strip()
        p = (pred[cid].get("stance") or "").strip()
        cm[g][p] += 1
        ok += g == p
    acc = ok / max(1, len(ids))
    print(f"\nstance accuracy: {acc:.3f} ({ok}/{len(ids)})")
    rows = []
    for c in STANCE:
        tp = cm[c][c]
        fp = sum(cm[g][c] for g in STANCE if g != c)
        fn = sum(cm[c][p] for p in STANCE if p != c)
        p_, r_, f_ = prf(tp, fp, fn)
        rows.append((c, tp, fp, fn, p_, r_, f_))
    print(f"{'class':10s} {'tp':>4s} {'fp':>4s} {'fn':>4s} {'P':>6s} {'R':>6s} {'F1':>6s}")
    for c, tp, fp, fn, p_, r_, f_ in rows:
        print(f"{c:10s} {tp:4d} {fp:4d} {fn:4d} {p_:6.3f} {r_:6.3f} {f_:6.3f}")
    macro_f1 = sum(r[6] for r in rows) / len(rows)
    print(f"macro F1: {macro_f1:.3f}")
    print("\nconfusion (rows=gold, cols=pred):")
    print(f"{'':10s}" + "".join(f"{c[:8]:>10s}" for c in STANCE))
    for g in STANCE:
        print(f"{g:10s}" + "".join(f"{cm[g][p]:10d}" for p in STANCE))

    # ---- P/R code sets ----
    def split(s):
        return [x.strip() for x in (s or "").replace("、", ";").split(";") if x.strip()]
    pm = set_metrics([split(gold[c].get("p_codes")) for c in ids],
                     [split(pred[c].get("p_codes")) for c in ids])
    rm = set_metrics([split(gold[c].get("r_codes")) for c in ids],
                     [split(pred[c].get("r_codes")) for c in ids])
    print(f"\nP codes: micro-F1={pm['f1']} (P={pm['precision']} R={pm['recall']}) exact={pm['exact_match']}")
    print(f"R codes: micro-F1={rm['f1']} (P={rm['precision']} R={rm['recall']}) exact={rm['exact_match']}")

    if args.json:
        print(json.dumps({"n": len(ids), "stance_acc": round(acc, 3), "macro_f1": round(macro_f1, 3),
                          "p": pm, "r": rm, "missing": missing}, ensure_ascii=False))


if __name__ == "__main__":
    main()
