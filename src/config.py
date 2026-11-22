# -*- coding: utf-8 -*-
"""
Task A/B 全局配置：路径、码表规模、 horizon、预注册证伪阈值。
与 proposal §2.6/§2.7 一一对应；改实验口径只改这里。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "pipeline" / "data"          # 2000-pair 语料（clip + 评论快照）
SKILL_RESULTS = ROOT / "skilltest" / "results"      # 本轮 10 平台 B5 实测（可导入）
SKILL_RESULTS_NOSKILL = ROOT / "skilltest" / "results_noskill"
RUNS = ROOT / "pipeline" / "runs"          # 训练/评估产物

SEED = 20261113

# ---- 码表（proposal：15 P 码 + 91 R 码；允许扩容）----
N_P_CODES = 15
N_R_CODES = 91
N_CODES = N_P_CODES + N_R_CODES            # 106

# ---- Task A 输出维度 ----
STANCE_CLASSES = ["positive", "negative", "neutral", "mixed"]
INTENSITY_LEVELS = 4                        # ordinal 1..4
VA_DIM = 2                                  # valence, arousal（回归）

# ---- Task B ----
HORIZONS_H = [6, 24, 72]                    # 评论快照时点
B_CLASSES = ["pos", "neg", "neu"]           # 评论 valence 分布的目标桶

# ---- 软标签 / 置信门控（§ proposal soft fine-tuning）----
AGREE_TAU = 0.67                            # κ ≥ 0.67 → 收紧为硬目标（confidence-gated）
SOFT_LOSS = "bce_soft"                      # 码头: 软目标 BCE；stance: KL
DISTILL_WEIGHT_MIN = 0.3                    # 低一致样本的损失权重下限

# ---- 预注册证伪阈值（§2.7，写死防事后讲故事）----
FALSIFY = {
    "parity_delta_f1": 1.0,                 # B6 与 B6′ macro-F1 差 |Δ| ≤ 1.0 视为 parity
    "ece_required_lower": True,             # 且 ECE(B6) < ECE(B6′)
    "permutation_seed": SEED,
    "bootstrap_n": 2000,
    "null_beat_alpha": 0.05,                # B6 对 Audience-Prior Null 的 J-S 配对检验
}

# ---- CH-SIMS 防退化门（domain-transfer sanity）----
CH_SIMS = {
    "max_f1_drop": 2.0,                     # 适配后 CH-SIMS macro-F1 掉幅 > 2pt → 报警
    "eval_every_epochs": 2,
}

# ---- 基线注册表（名字 → 是否需要 torch 训练）----
BASELINES = ["B0", "B1", "B2", "B3", "B4", "B5", "B6", "B6p"]
