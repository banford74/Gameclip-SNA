# -*- coding: utf-8 -*-
"""
CH-SIMS 防退化门（§2.6）：骨干适配到抖音游戏域后，定期在 CH-SIMS 上回归测试，
macro-F1 掉幅 > max_f1_drop 则报警（灾难性遗忘 → 回退 LoRA rank/增加回放数据）。
数据集接入：CH-SIMS v2（2,281 段中文视频，单模态+多模态标签）。
"""
import numpy as np

import config
from metrics import macro_f1

def sanity_check(f1_before_adapt: float, f1_after_adapt: float) -> dict:
    drop = f1_before_adapt - f1_after_adapt
    return {"f1_before": f1_before_adapt, "f1_after": f1_after_adapt, "drop": float(drop),
            "gate_pass": bool(drop <= config.CH_SIMS["max_f1_drop"]),
            "verdict": "通过：域适配未伤通用情感能力" if drop <= config.CH_SIMS["max_f1_drop"]
                       else "报警：灾难性遗忘 → 降 LoRA rank / 提高回放混合比 / 降学习率"}

def run_ch_sims_eval(model, loader):
    """model: 已适配骨干 + stance 头；loader: CH-SIMS v2 测试 loader（yield (features, y_stance_idx)）。"""
    ys, yps = [], []
    for feat, y in loader:
        out = model(feat)
        ys.append(y.numpy()); yps.append(out["stance"].argmax(-1).numpy())
    return macro_f1(np.concatenate(ys), np.concatenate(yps), 4)

if __name__ == "__main__":
    print(sanity_check(0.74, 0.735))   # 应通过
    print(sanity_check(0.74, 0.68))    # 应报警
