# -*- coding: utf-8 -*-
"""
词典 × LLM 混合 VAD：LLM 锚点校准词典 + 分歧挖词（持续扩充）。

1) fit_calibration(labeled_vad.json)：
   用 LLM 双 rater 的 1–9 VAD 当锚点，逐维拟合 词典型 VAD → LLM VAD 的线性校准
   （y = a*x + b），存 data/lexicons/vad_calibration.json；
   5 折 CV 输出校准前后 Spearman，避免过拟合假象。
2) calibrated_analyze / calibrated_many：
   词典打分 → 应用校准 → 输出与 LLM 同尺度的 v/a/d；标签仍按校准后 v 阈值派生。
3) mine_queue：
   锚点里「词典与 LLM 偏差 ≥2 分」的片段 → 候选未登录词（附建议 VAD 与出现次数）
   → data/lexicons/zh_queue.json，人工/LLM 复核后并入 zh_seed.json。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .analyze import analyze, analyze_many

DATA = Path(__file__).resolve().parents[2] / "data" / "lexicons"
CAL = DATA / "vad_calibration.json"
QUEUE = DATA / "zh_queue.json"

# 词典分数域：[0,1] ↔ LLM 域：[1,9]
def to_llm(x: float) -> float:
    return 1 + 8 * float(x)

def to_lex(x: float) -> float:
    return (float(x) - 1) / 8


def _rows(labeled_path) -> list:
    j = json.loads(Path(labeled_path).read_text(encoding="utf-8"))
    return j.get("rows") or []


def _lex(rows, dim: str) -> np.ndarray:
    key = {"v": "valence", "a": "arousal", "d": "dominance"}[dim]
    return np.array([to_llm(analyze(r["text"])[key]) for r in rows], dtype=float)


def _llm(rows, dim: str) -> np.ndarray:
    return np.array([r["vad"][dim] for r in rows], dtype=float)


def _spearman(a, b) -> float:
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean(); rb -= rb.mean()
    den = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / den) if den else 0.0


def _fit(x, y):
    a, b = np.polyfit(x, y, 1)
    return float(a), float(b)


def fit_calibration(labeled_path, folds: int = 5) -> dict:
    rows = _rows(labeled_path)
    out = {"n": len(rows), "dims": {}}
    for dim in ("v", "a", "d"):
        x, y = _lex(rows, dim), _llm(rows, dim)
        a, b = _fit(x, y)
        # 5 折 CV：校准前后 Spearman
        idx = np.arange(len(rows))
        rng = np.random.default_rng(0)
        rng.shuffle(idx)
        sp_before, sp_after = [], []
        for k in range(folds):
            test = idx[k::folds]
            tr = np.setdiff1d(idx, test)
            aa, bb = _fit(x[tr], y[tr])
            sp_before.append(_spearman(x[test], y[test]))
            sp_after.append(_spearman(aa * x[test] + bb, y[test]))
        r2 = 1 - ((y - (a * x + b)) ** 2).sum() / ((y - y.mean()) ** 2).sum()
        out["dims"][dim] = {"a": round(a, 4), "b": round(b, 4), "r2": round(float(r2), 4),
                            "spearman_before": round(float(np.mean(sp_before)), 3),
                            "spearman_after": round(float(np.mean(sp_after)), 3)}
    CAL.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def load_calibration() -> dict | None:
    if CAL.exists():
        return json.loads(CAL.read_text(encoding="utf-8"))
    return None


def _apply(cal: dict, dim: str, x: float) -> float:
    d = cal["dims"].get(dim)
    if not d:
        return float(x)
    return float(np.clip(d["a"] * float(x) + d["b"], 1.0, 9.0))


def calibrated_analyze(text: str, cal: dict | None = None) -> dict:
    cal = cal or load_calibration()
    r = analyze(text, include_mixed=False)
    if not cal:
        return r
    v = _apply(cal, "v", 1 + 8 * r["valence"])
    a = _apply(cal, "a", 1 + 8 * r["arousal"])
    d = _apply(cal, "d", 1 + 8 * r["dominance"])
    out = dict(r)
    out["vad_llm_scale"] = {"v": round(v, 3), "a": round(a, 3), "d": round(d, 3)}
    # 标签按校准后 v 派生
    if v >= 6.0:
        out["label"] = "positive"
    elif v <= 4.0:
        out["label"] = "negative"
    else:
        out["label"] = "neutral"
    out["valence"], out["arousal"], out["dominance"] = round(v / 9, 4), round(a / 9, 4), round(d / 9, 4)
    return out


def calibrated_many(texts: list[str], cal: dict | None = None) -> dict:
    from collections import Counter
    cal = cal or load_calibration()
    det = [calibrated_analyze(t, cal) for t in texts]
    c = Counter(r["label"] for r in det)
    n = max(len(det), 1)
    vs = [r["vad_llm_scale"]["v"] for r in det if "vad_llm_scale" in r]
    as_ = [r["vad_llm_scale"]["a"] for r in det if "vad_llm_scale" in r]
    ds = [r["vad_llm_scale"]["d"] for r in det if "vad_llm_scale" in r]
    return {"n": len(det),
            "dist": {k: round(c.get(k, 0) / n, 4) for k in ("positive", "negative", "neutral")},
            "net": round((c.get("positive", 0) - c.get("negative", 0)) / n, 4),
            "mean_vad_llm": {"v": round(float(np.mean(vs)), 3) if vs else None,
                             "a": round(float(np.mean(as_)), 3) if as_ else None,
                             "d": round(float(np.mean(ds)), 3) if ds else None},
            "details": det}


# ---------- 词典 × LLM 蒸馏 × 校准 三合一（评论默认口径） ----------
def hybrid_analyze(text: str, cal: dict | None = None, learned: dict | None = None) -> dict:
    """词典打分 → learned VAD 覆盖（梗词）→ 派生三分类（无 mixed）。
    注意：线性校准只用于「平均值对齐报告」，不参与标签阈值（否则分布被压回中心）。"""
    from . import learn_vad
    learned = learned if learned is not None else learn_vad.load()
    r = analyze(text, include_mixed=False)
    lv, la, ld = 1 + 8 * r["valence"], 1 + 8 * r["arousal"], 1 + 8 * r["dominance"]
    lv, la, ld, hits = learn_vad.score_with_overlay(text, learned, lv, la, ld)
    label = "positive" if lv >= 6.0 else ("negative" if lv <= 4.0 else "neutral")
    out = dict(r)
    out.update({"label": label, "vad_llm_scale": {"v": round(lv, 3), "a": round(la, 3), "d": round(ld, 3)},
                "learned_hits": hits,
                "valence": round(lv / 9, 4), "arousal": round(la / 9, 4), "dominance": round(ld / 9, 4)})
    return out


def hybrid_many(texts: list[str], cal: dict | None = None, learned: dict | None = None) -> dict:
    from collections import Counter
    det = [hybrid_analyze(t, cal, learned) for t in texts]
    c = Counter(r["label"] for r in det)
    n = max(len(det), 1)
    vs = [r["vad_llm_scale"]["v"] for r in det]
    as_ = [r["vad_llm_scale"]["a"] for r in det]
    ds = [r["vad_llm_scale"]["d"] for r in det]
    return {"n": len(det),
            "dist": {k: round(c.get(k, 0) / n, 4) for k in ("positive", "negative", "neutral")},
            "net": round((c.get("positive", 0) - c.get("negative", 0)) / n, 4),
            "mean_vad_llm": {"v": round(float(np.mean(vs)), 3), "a": round(float(np.mean(as_)), 3),
                             "d": round(float(np.mean(ds)), 3)},
            "details": det}


def mine_queue(labeled_path, min_dev: float = 2.0, lo: int = 2, hi: int = 4) -> dict:
    """从锚点分歧里挖候选词：词典 v 与 LLM v 偏差 ≥ min_dev 的 2–4 字片段。"""
    rows = _rows(labeled_path)
    from collections import defaultdict
    cand = defaultdict(lambda: {"n": 0, "llm_v": [], "lex_v": []})
    for r in rows:
        t = r["text"]
        llm_v = r["vad"]["v"]
        r2 = analyze(t)
        lex_v = to_llm(r2["valence"])
        if abs(lex_v - llm_v) < min_dev:
            continue
        seen = set()
        for n in range(lo, hi + 1):
            for i in range(len(t) - n + 1):
                g = t[i:i + n]
                if not all("\u4e00" <= ch <= "\u9fff" for ch in g) or g in seen:
                    continue
                seen.add(g)
                cand[g]["n"] += 1
                cand[g]["llm_v"].append(llm_v)
                cand[g]["lex_v"].append(lex_v)
    out = []
    for term, d in sorted(cand.items(), key=lambda kv: -kv[1]["n"])[:300]:
        out.append({"term": term, "n": d["n"],
                    "llm_v_mean": round(float(np.mean(d["llm_v"])), 2),
                    "lex_v_mean": round(float(np.mean(d["lex_v"])), 2),
                    "suggested_v": round(float(np.mean(d["llm_v"])), 2)})
    QUEUE.write_text(json.dumps({"n_anchors": len(rows), "candidates": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"n_candidates": len(out), "file": str(QUEUE)}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "fit":
        print(json.dumps(fit_calibration(sys.argv[2]), ensure_ascii=False, indent=1))
    elif len(sys.argv) > 1 and sys.argv[1] == "mine":
        print(json.dumps(mine_queue(sys.argv[2]), ensure_ascii=False, indent=1))
    else:
        cal = load_calibration()
        print("calibration:", json.dumps(cal, ensure_ascii=False)[:300] if cal else "none")
        print(calibrated_analyze("待我用神识探查下"))
