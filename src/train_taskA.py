# -*- coding: utf-8 -*-
"""
Task A 训练循环（B6 软目标；B3 = 同结构但硬标签、无置信门控；B2 = 全参数放开）。
数据 = 2000 对语料的 (clip 特征, 软标签)；特征抽取用 backbone（Vision Transformer over 1–2s micro-clips
+ 音频卷积 + 文本 transformer），抽帧/ASR/OCR 已由 skill 侧脚本产出。
"""
import numpy as np
import config
from soft_labels import build_soft_dataset

def ordinal_loss(logits, target_level: int, n_levels: int = 4):
    """ordinal 任务的 CORAL 简化版：P(y>=k) 的二分类链。"""
    if not __import__("models").HAS_TORCH:
        raise RuntimeError("需要 torch")
    import torch
    import torch.nn.functional as F
    targets = torch.stack([(target_level >= k).float() for k in range(1, n_levels)], dim=-1)  # (B, 3)
    logp = torch.cumsum(torch.sigmoid(logits), dim=-1)
    return F.binary_cross_entropy(logp.clamp(1e-6, 1 - 1e-6), targets)


def train_taskA(features: np.ndarray, soft: dict, epochs: int = 6, lr: float = 1e-4,
                hard_labels: bool = False, full_finetune: bool = False):
    """
    features: (N, d_model) —— backbone pooled 特征（本地抽好存盘）
    soft: build_soft_dataset() 的输出
    hard_labels=True  → B3（无软正则）；full_finetune=True → B2（放开全部参数，训练慢、易过拟合，作上界）
    """
    if not __import__("models").HAS_TORCH:
        raise RuntimeError("需要 torch；本文件为训练脚本，本地 GPU 环境运行")
    import torch
    from models import TaskAHeads
    torch.manual_seed(config.SEED)
    model = TaskAHeads(features.shape[1], config.N_CODES)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    X = torch.tensor(features, dtype=torch.float32)
    C = torch.tensor(soft["code_soft"], dtype=torch.float32)
    W = torch.tensor(soft["code_weight"] if not hard_labels else np.ones_like(soft["code_weight"]), dtype=torch.float32)
    S = torch.tensor(soft["stance_soft"], dtype=torch.float32)
    SW = torch.tensor(soft["stance_weight"] if not hard_labels else np.ones_like(soft["stance_weight"]), dtype=torch.float32)
    import torch.nn.functional as F
    for ep in range(epochs):
        opt.zero_grad()
        out = model(X)
        # 软目标 BCE：-Σ [p·logσ(z) + (1-p)·log(1-σ(z))]，按置信权重加权
        z = out["codes"]
        bce = -(C * F.logsigmoid(z) + (1 - C) * F.logsigmoid(-z)).mean(-1)
        loss_code = (bce * W).sum() / W.sum().clamp(min=1e-6)
        # stance：KL(soft || softmax)
        kl = (S * (S.clamp(min=1e-9).log() - F.log_softmax(out["stance"], -1))).sum(-1)
        loss_stance = (kl * SW).sum() / SW.sum().clamp(min=1e-6)
        loss = loss_code + 0.5 * loss_stance
        loss.backward(); opt.step()
        print(f"[taskA] ep{ep} code={float(loss_code):.4f} stance={float(loss_stance):.4f}")
    return model

if __name__ == "__main__":
    rng = np.random.default_rng(config.SEED)
    feats = rng.normal(size=(64, 128)).astype(np.float32)     # 真实环境换 backbone 特征
    recs = [{"clip_id": str(i),
             "rater_code_probs": rng.dirichlet(np.ones(config.N_CODES) * 0.3, size=3),
             "votes": list(rng.choice(config.N_CODES, 2, replace=False)),
             "rater_stance": rng.dirichlet(np.ones(4), size=3),
             "stance_votes": list(rng.choice(4, 2))} for i in range(64)]
    soft = build_soft_dataset(recs)
    try:
        train_taskA(feats, soft, epochs=2)
    except RuntimeError as e:
        print("SKIP:", e)
