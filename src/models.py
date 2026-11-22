# -*- coding: utf-8 -*-
"""
backbone + Task A/B heads（torch/peft 受保护导入；无 GPU 环境下仅暴露接口，训练在本地 GPU 跑）。

设计（对齐 proposal）：
- backbone：多模态 VLM（GLM-5.3-Flash / Qwen-VL 类），视频 → 1–2s micro-clip 特征
- SALFT：selective affective layer fine-tuning —— 冻结骨干大部分层，只对"情感相关层"
  （最后 N 个 block + 跨模态融合层）挂 LoRA；比标准 LoRA（B3）更省、更抗过拟合
- Task A heads：106 码 sigmoid 多标签 + stance 4 分类 + 强度 ordinal(4) + VA 回归(2)
- B6 = 以上软目标训练；B6′ = 同骨干直接端到端 frame→stance（无码层）
"""
import numpy as np

try:
    import torch
    import torch.nn as nn
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    nn = None


def build_salfot_lora(target_backbone: str = "glm-5.3-flash-9b", n_affect_layers: int = 6, rank: int = 16):
    """
    返回 peft LoraConfig：只挂骨干尾部 n_affect_layers 个 block 的 qkv/o 投影。
    B3（标准 PEFT）= 全层 LoRA；B4/B5 为 prompt 基线不走这里。
    """
    if not HAS_TORCH:
        raise RuntimeError("torch/peft 未安装：训练请在本地 GPU 环境（requirements.txt）")
    from peft import LoraConfig
    return LoraConfig(
        r=rank, lora_alpha=2 * rank, lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        layers_to_transform=list(range(-n_affect_layers, 0)),  # 仅最后 N 层（SALFT 选择性）
        task_type="CAUSAL_LM",
    )


if HAS_TORCH:
    class TaskAHeads(nn.Module):
        """挂在 backbone pooled 特征上的轻头。106 码 + stance + 强度 + VA。"""
        def __init__(self, d_model: int, n_codes: int, n_stance: int = 4, intensity_levels: int = 4, va_dim: int = 2):
            super().__init__()
            self.code_head = nn.Sequential(nn.Linear(d_model, 512), nn.GELU(), nn.Linear(512, n_codes))
            self.stance_head = nn.Linear(d_model, n_stance)
            self.intensity_head = nn.Linear(d_model, intensity_levels)   # ordinal → 用 CORAL 或 soft-ordinal CE
            self.va_head = nn.Linear(d_model, va_dim)

        def forward(self, feat):
            return {"codes": self.code_head(feat),          # logits (B, n_codes) → BCEWithLogits(soft target)
                    "stance": self.stance_head(feat),       # logits (B, 4) → KL(soft)
                    "intensity": self.intensity_head(feat), # logits (B, 4) → ordinal
                    "va": self.va_head(feat)}               # (B, 2) → MSE

    class TaskBMapping(nn.Module):
        """A→B：码分布 + stance/VA + creator priors → 评论 valence 分布（K=3），J-S 目标。"""
        def __init__(self, n_codes: int, n_stance: int = 4, prior_dim: int = 8, n_out: int = 3):
            super().__init__()
            d_in = n_codes + n_stance + 2 + prior_dim     # 码 + stance + (强度,VA) + priors
            self.net = nn.Sequential(nn.Linear(d_in, 256), nn.GELU(),
                                     nn.Linear(256, 128), nn.GELU(), nn.Linear(128, n_out))
        def forward(self, x):
            return torch.softmax(self.net(x), dim=-1)     # 分布输出，配 JS loss

    class AudiencePriorNull(nn.Module):
        """§2.7 Audience-Prior Null Model：只看创作者历史评论分布/粉丝量/发布时间——B 必须赢它。"""
        def __init__(self, prior_dim: int = 8, n_out: int = 3):
            super().__init__()
            self.head = nn.Linear(prior_dim, n_out)       # 甚至可以只用历史分布直方图
        def forward(self, priors):
            return torch.softmax(self.head(priors), dim=-1)


def js_loss(pred_dist, target_dist, eps: float = 1e-9):
    """Task B 训练损失：J-S 前向 KL 的可导近似。"""
    if not HAS_TORCH:
        raise RuntimeError("需要 torch")
    m = 0.5 * (pred_dist + target_dist)
    kl = lambda x, y: (x * torch.log((x + eps) / (y + eps))).sum(-1)
    return (0.5 * kl(pred_dist, m) + 0.5 * kl(target_dist, m)).mean()
