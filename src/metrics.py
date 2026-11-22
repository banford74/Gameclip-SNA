# -*- coding: utf-8 -*-
"""
MERBench 对齐的评测指标（numpy-only，无 torch 依赖，可直接自测）：
macro-F1 / UAR / ordinal MAE / Spearman ρ / ECE / Jensen-Shannon 散度。
"""
import numpy as np


def macro_f1(y_true: np.ndarray, y_pred: np.ndarray, n_classes: int) -> float:
    f1s = []
    for c in range(n_classes):
        tp = np.sum((y_pred == c) & (y_true == c))
        fp = np.sum((y_pred == c) & (y_true != c))
        fn = np.sum((y_pred != c) & (y_true == c))
        f1s.append(2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0)
    return float(np.mean(f1s))


def uar(y_true: np.ndarray, y_pred: np.ndarray, n_classes: int) -> float:
    """unbiased average recall：MERBench 抗不平衡口径。"""
    recs = []
    for c in range(n_classes):
        denom = np.sum(y_true == c)
        recs.append(np.sum((y_pred == c) & (y_true == c)) / denom if denom else 0.0)
    return float(np.mean(recs))


def ordinal_mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y_true - y_pred)))


def spearman_rho(a: np.ndarray, b: np.ndarray) -> float:
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean(); rb -= rb.mean()
    denom = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / denom) if denom else 0.0


def ece(conf: np.ndarray, correct: np.ndarray, n_bins: int = 10) -> float:
    """Expected Calibration Error（等宽分桶）。"""
    bins = np.minimum((conf * n_bins).astype(int), n_bins - 1)
    e = 0.0
    for b in range(n_bins):
        m = bins == b
        if m.sum() == 0:
            continue
        e += m.mean() * abs(conf[m].mean() - correct[m].mean())
    return float(e)


def js_divergence(p: np.ndarray, q: np.ndarray, eps: float = 1e-9) -> float:
    """Jensen-Shannon（以 2 为底，0..1）。p/q 形状 (..., K)，自动裁剪负值并归一。"""
    p = np.clip(np.asarray(p, float), 0, None)
    q = np.clip(np.asarray(q, float), 0, None)
    p = p + eps; p = p / p.sum(axis=-1, keepdims=True)
    q = q + eps; q = q / q.sum(axis=-1, keepdims=True)
    m = 0.5 * (p + q)
    kl = lambda x, y: np.sum(x * np.log(x / y), axis=-1)
    return float(np.mean(0.5 * kl(p, m) + 0.5 * kl(q, m)) / np.log(2))


def paired_bootstrap_js(pred_a: np.ndarray, pred_b: np.ndarray, truth: np.ndarray,
                        n: int = 2000, seed: int = 0) -> dict:
    """配对 bootstrap：模型 A 的 J-S 是否显著优于模型 B（如 B6 vs Audience-Prior Null）。"""
    rng = np.random.default_rng(seed)
    n_samples = truth.shape[0]
    deltas = []
    for _ in range(n):
        idx = rng.integers(0, n_samples, n_samples)
        d = js_divergence(pred_b[idx], truth[idx]) - js_divergence(pred_a[idx], truth[idx])  # >0 ⇒ A 更好
        deltas.append(d)
    deltas = np.array(deltas)
    return {"mean_delta_js": float(np.mean(deltas)),
            "ci95": [float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5))],
            "p_value": float((deltas <= 0).mean())}


def self_test():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 3, 500)
    yp = rng.integers(0, 3, 500)
    print("macro-F1:", round(macro_f1(y, yp, 3), 4), " UAR:", round(uar(y, yp, 3), 4))
    print("ordinal MAE:", round(ordinal_mae(rng.integers(1, 5, 100), rng.integers(1, 5, 100)), 4))
    print("spearman:", round(spearman_rho(rng.normal(size=200), rng.normal(size=200)), 4))
    conf = rng.uniform(0.5, 1.0, 300)
    print("ECE:", round(ece(conf, (rng.uniform(size=300) < conf).astype(float)), 4))
    t = rng.dirichlet([2, 1, 1], size=50)
    print("JS(pred≈truth):", round(js_divergence(t + 0.01, t), 4),
          " JS(rand,truth):", round(js_divergence(rng.dirichlet([1, 1, 1], size=50), t), 4))


if __name__ == "__main__":
    self_test()
