# -*- coding: utf-8 -*-
"""
软标签构建（proposal：soft annotator-vote targets + confidence-gated distillation）。
输入：每条样本的多 rater 投票（人 + VLM rater 混合）+ 分歧记录。
输出：Task A 的软目标（码 → 概率向量；stance → 分布；强度/VA → 带权均值）。
"""
import numpy as np
from config import AGREE_TAU, DISTILL_WEIGHT_MIN

# 一致性（简单一致率；正式版换 Fleiss κ，阈值同 proposal §4.4）
def agreement(votes: list) -> float:
    """votes: [label_idx, ...] 多 rater。返回最大占比。"""
    if not votes:
        return 0.0
    counts = np.bincount(np.asarray(votes, int))
    return float(counts.max() / len(votes))

def soft_code_target(rater_code_probs: np.ndarray, votes: list) -> tuple:
    """
    rater_code_probs: (R, n_codes) 各 rater（含 VLM teacher）给出的码概率
    votes: 码级人工投票（哪些码被勾选）
    返回 (soft_target (n_codes,), sample_weight)
    - 一致率高（≥AGREE_TAU）：收紧（锐化）目标 → 硬目标蒸馏
    - 分歧大：保留软分布，样本权重降到 DISTILL_WEIGHT_MIN
    """
    base = rater_code_probs.mean(axis=0)
    agr = agreement(votes)
    if agr >= AGREE_TAU:
        # 收紧：向硬目标（勾选=1/未勾=0）插值 70%
        hard = np.zeros_like(base)
        hard[list(set(votes))] = 1.0
        target = 0.7 * hard + 0.3 * base
        w = 1.0
    else:
        target = base
        w = DISTILL_WEIGHT_MIN + (agr / AGREE_TAU) * (1 - DISTILL_WEIGHT_MIN)
    return np.clip(target, 0.0, 1.0), float(w)

def soft_stance_target(rater_stance: np.ndarray, votes: list) -> tuple:
    """rater_stance: (R, 4)。同上，KL 蒸馏用分布。"""
    dist = rater_stance.mean(axis=0)
    dist = dist / dist.sum()
    agr = agreement(votes)
    if agr >= AGREE_TAU:
        hard = np.zeros_like(dist); hard[int(np.argmax(dist))] = 1.0
        dist = 0.7 * hard + 0.3 * dist
        w = 1.0
    else:
        w = DISTILL_WEIGHT_MIN + (agr / AGREE_TAU) * (1 - DISTILL_WEIGHT_MIN)
    return dist, float(w)

def build_soft_dataset(records: list) -> dict:
    """
    records: [{clip_id, rater_code_probs, rater_stance, votes, ...}, ...]
    返回可训练张量组（numpy）。2000 对语料在此接入。
    """
    X_code, y_code, w_code = [], [], []
    y_stance, w_stance = [], []
    for r in records:
        t, w = soft_code_target(np.asarray(r["rater_code_probs"]), r["votes"])
        X_code.append(t); y_code.append(t); w_code.append(w)  # 自蒸馏占位：正式版 y 来自人工码标注
        s, ws = soft_stance_target(np.asarray(r["rater_stance"]), r["stance_votes"])
        y_stance.append(s); w_stance.append(ws)
    return {"code_soft": np.stack(y_code), "code_weight": np.array(w_code),
            "stance_soft": np.stack(y_stance), "stance_weight": np.array(w_stance)}

if __name__ == "__main__":
    rng = np.random.default_rng(0)
    rec = {"clip_id": "demo", "rater_code_probs": rng.dirichlet(np.ones(8) * 0.6, size=3),
           "votes": [0, 2], "rater_stance": rng.dirichlet(np.ones(4), size=3), "stance_votes": [1, 1, 0]}
    d = build_soft_dataset([rec])
    print("code_soft:", d["code_soft"].shape, "weight:", d["code_weight"])
    print("stance_soft:", np.round(d["stance_soft"][0], 3), "weight:", d["stance_weight"])
