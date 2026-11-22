# -*- coding: utf-8 -*-
"""从 LLM 锚点蒸馏词级 VAD（覆盖层）：让「神识/绝密/四级蛋」这类梗词进入词典。

- build(texts, vads)：2–4 字片段 → 该片段出现文本的 LLM VAD 均值；出现 ≥3 次才收录
- overlay：analyze 时优先使用覆盖层（权重 3），词典/种子为兜底
- CV：留出评估（learned 只用训练折，测测试折 Spearman）
产物 data/lexicons/zh_learned_vad.json
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from .analyze import analyze

DATA = Path(__file__).resolve().parents[2] / "data" / "lexicons"
OUT = DATA / "zh_learned_vad.json"


def build(rows, lo: int = 2, hi: int = 4, min_n: int = 3) -> dict:
    acc = defaultdict(lambda: {"v": [], "a": [], "d": []})
    for r in rows:
        t = r["text"]
        for n in range(lo, hi + 1):
            for i in range(len(t) - n + 1):
                g = t[i:i + n]
                if not all("\u4e00" <= ch <= "\u9fff" for ch in g):
                    continue
                acc[g]["v"].append(r["vad"]["v"])
                acc[g]["a"].append(r["vad"]["a"])
                acc[g]["d"].append(r["vad"]["d"])
    out = {}
    for g, d in acc.items():
        if len(d["v"]) < min_n:
            continue
        out[g] = {"v": round(float(np.mean(d["v"])), 3),
                  "a": round(float(np.mean(d["a"])), 3),
                  "d": round(float(np.mean(d["d"])), 3), "n": len(d["v"])}
    return out


def save(learned: dict) -> None:
    OUT.write_text(json.dumps(learned, ensure_ascii=False, indent=1), encoding="utf-8")


def load() -> dict:
    if OUT.exists():
        return json.loads(OUT.read_text(encoding="utf-8"))
    return {}


def score_with_overlay(text: str, learned: dict, lex_v: float, lex_a: float, lex_d: float):
    """覆盖层命中 → 与词典结果混合（覆盖层权重 0.6，长词优先）。"""
    hits = []
    for n in (4, 3, 2):
        for i in range(len(text) - n + 1):
            g = text[i:i + n]
            if g in learned:
                hits.append((g, learned[g]))
    if not hits:
        return lex_v, lex_a, lex_d, []
    v = 0.4 * lex_v + 0.6 * float(np.mean([h[1]["v"] for h in hits]))
    a = 0.4 * lex_a + 0.6 * float(np.mean([h[1]["a"] for h in hits]))
    d = 0.4 * lex_d + 0.6 * float(np.mean([h[1]["d"] for h in hits]))
    return v, a, d, [h[0] for h in hits]


def spearman(a, b) -> float:
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean(); rb -= rb.mean()
    den = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / den) if den else 0.0


def cv(rows, folds: int = 5):
    idx = np.arange(len(rows))
    np.random.default_rng(0).shuffle(idx)
    base, over = [], []
    for k in range(folds):
        test = idx[k::folds]
        tr = np.setdiff1d(idx, test)
        learned = build([rows[i] for i in tr])
        xb, xo, y = [], [], []
        for i in test:
            r = rows[i]
            a = analyze(r["text"])
            lv, la, ld = 1 + 8 * a["valence"], 1 + 8 * a["arousal"], 1 + 8 * a["dominance"]
            v2, a2, d2, _ = score_with_overlay(r["text"], learned, lv, la, ld)
            xb.append(lv); xo.append(v2); y.append(r["vad"]["v"])
        base.append(spearman(np.array(xb), np.array(y)))
        over.append(spearman(np.array(xo), np.array(y)))
    return float(np.mean(base)), float(np.mean(over))


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else "skilltest/comments/v3_all_7709870849365478116_vad.json"
    rows = json.loads(Path(src).read_text(encoding="utf-8"))["rows"]
    b, o = cv(rows)
    print(f"CV Spearman valence: lexicon={b:.3f} -> +learned_overlay={o:.3f}")
    learned = build(rows)
    save(learned)
    print("learned terms:", len(learned))
    for g in ["神识", "绝密", "四级蛋", "背景图", "千万别看"]:
        print(g, learned.get(g))
