# -*- coding: utf-8 -*-
"""
§2.7 预注册证伪测试（跑在真实实验之后，判定读法，杜绝事后讲故事）：
1) B6 vs B6′：parity（|ΔF1|≤δ）且 ECE(B6)<ECE(B6′) → 码层=零成本可解释；B6>B6′ → 归纳偏置有效；B6<B6′ → 瓶颈，触发码表残差分析
2) Within-Genre Label Permutation：同品类内打乱 B 目标 → 真实增益必须塌缩到 null 水平
3) B6 vs Audience-Prior Null：J-S 配对 bootstrap
"""
import numpy as np

import config
from metrics import macro_f1, ece, js_divergence, paired_bootstrap_js

def read_b6_vs_b6p(f1_b6: float, ece_b6: float, f1_b6p: float, ece_b6p: float) -> dict:
    delta = f1_b6 - f1_b6p
    if abs(delta) <= config.FALSIFY["parity_delta_f1"]:
        if ece_b6 < ece_b6p:
            verdict = "PARITY+LOWER-ECE → 码表作为可解释机制成立（零精度成本）"
        else:
            verdict = "PARITY but ECE 未占优 → 可解释性成立但校准收益未证实"
    elif delta > 0:
        verdict = "B6 > B6′ → 创意码表是有效归纳偏置（小样本学习增益）"
    else:
        verdict = "B6 < B6′ → 码层是信息瓶颈 → 触发残差分析修订码表（codebook.expansion_queue）"
    return {"delta_f1": float(delta), "ece_b6": float(ece_b6), "ece_b6p": float(ece_b6p), "verdict": verdict}

def within_genre_permutation(model_js: float, truth: np.ndarray, genres: np.ndarray,
                             model_pred: np.ndarray, seed: int = None) -> dict:
    """同品类内打乱 B 目标：真实模型的 J-S 应显著变差（≈ null 水平），否则增益是品类先验造成的。"""
    seed = seed if seed is not None else config.FALSIFY["permutation_seed"]
    rng = np.random.default_rng(seed)
    js_shuffled = []
    y = truth.copy()
    for _ in range(config.FALSIFY["bootstrap_n"]):
        y_perm = y.copy()
        for g in np.unique(genres):
            idx = np.where(genres == g)[0]
            y_perm[idx] = y_perm[rng.permutation(idx)]
        js_shuffled.append(js_divergence(model_pred, y_perm))
    return {"js_real": model_js, "js_perm_mean": float(np.mean(js_shuffled)),
            "js_perm_ci95": [float(np.percentile(js_shuffled, 2.5)), float(np.percentile(js_shuffled, 97.5))],
            "gain_collapses_to_chance": bool(model_js >= float(np.percentile(js_shuffled, 97.5)))}

def audience_prior_null_test(pred: np.ndarray, null_pred: np.ndarray, truth: np.ndarray) -> dict:
    t = paired_bootstrap_js(pred, null_pred, truth, n=config.FALSIFY["bootstrap_n"], seed=config.SEED)
    t["verdict"] = ("B 显著优于 Audience-Prior Null（clip 特征有增量信息）" if t["p_value"] < config.FALSIFY["null_beat_alpha"]
                    else "未能击败 Null：评论 valence 由创作者先验解释，clip 特征无增量 → Task B 主张被证伪")
    return t

def self_test():
    rng = np.random.default_rng(config.SEED)
    y_true = rng.dirichlet([2, 1, 1], size=80)
    # 1) parity 场景
    print(read_b6_vs_b6p(0.72, 0.05, 0.725, 0.09))
    # 2) 置换：模型预测=真值+噪声 → 置换后应塌缩
    pred = y_true + rng.normal(0, 0.02, y_true.shape)
    genres = rng.integers(0, 3, 80)
    print(within_genre_permutation(js_divergence(pred, y_true), y_true, genres, pred))
    # 3) null 对比：模型≈真值，null=常数分布 → 应显著优于
    null = np.tile([0.6, 0.2, 0.2], (80, 1))
    print(audience_prior_null_test(pred, null, y_true))

if __name__ == "__main__":
    self_test()
