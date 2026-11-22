# -*- coding: utf-8 -*-
"""
Task B：A→B 映射 + Audience-Prior Null + B4/B5 prompt 基线钩子。
- 输入特征 = Task A 输出（106 码概率 + stance 分布 + 强度/VA）+ creator priors
- 目标 = 6/24/72h 评论 valence 分布 {pos, neg, neu}，损失 = J-S，校准 = ECE
- 预注册对照：B6 vs B6′（码层 vs 端到端）；B vs Audience-Prior Null
"""
import numpy as np
import config
from metrics import js_divergence, ece, paired_bootstrap_js

def make_priors(rows: list) -> np.ndarray:
    """creator priors: [历史 pos/neg/neu 分布(3), log粉丝, 发布小时 sin/cos(2), 品类 onehot 前3]"""
    out = []
    for r in rows:
        hist = np.asarray(r["creator_hist_valence"], float)
        hist = hist / max(hist.sum(), 1e-9)
        out.append(np.concatenate([hist, [np.log1p(r.get("followers", 0))],
                                   [np.sin(2 * np.pi * r.get("hour", 12) / 24), np.cos(2 * np.pi * r.get("hour", 12) / 24)],
                                   np.eye(3)[min(r.get("genre", 0), 2)]]))
    return np.stack(out)

def train_taskB(taskA_outputs: dict, rows: list, epochs: int = 300, lr: float = 1e-3, seed: int = config.SEED):
    """taskA_outputs: {codes:(N,106) softmax 后, stance:(N,4), intensity:(N,), va:(N,2)}"""
    if not __import__("models").HAS_TORCH:
        raise RuntimeError("需要 torch")
    import torch
    from models import TaskBMapping, js_loss
    torch.manual_seed(seed)
    X = np.concatenate([taskA_outputs["codes"], taskA_outputs["stance"],
                        taskA_outputs["intensity"][:, None], taskA_outputs["va"],
                        make_priors(rows)], axis=1)
    Y = np.stack([r["comment_valence_dist"] for r in rows])   # (N,3) 实测分布
    xt = torch.tensor(X, dtype=torch.float32); yt = torch.tensor(Y, dtype=torch.float32)
    model = TaskBMapping(n_codes=X.shape[1] - (4 + 2 + 8) - 2)
    opt = torch.optim.AdamW(model.parameters(), lr=lr)
    for ep in range(epochs):
        opt.zero_grad()
        loss = js_loss(model(xt), yt)
        loss.backward(); opt.step()
    return model, X, Y

def evaluate_against_null(pred: np.ndarray, null_pred: np.ndarray, truth: np.ndarray, conf: np.ndarray, correct: np.ndarray):
    res = {
        "js_model": js_divergence(pred, truth),
        "js_null": js_divergence(null_pred, truth),
        "ece": ece(conf, correct),
        "null_test": paired_bootstrap_js(pred, null_pred, truth, n=config.FALSIFY["bootstrap_n"], seed=config.FALSIFY["permutation_seed"]),
    }
    res["beats_null"] = res["null_test"]["p_value"] < config.FALSIFY["null_beat_alpha"]
    return res

# ---- prompt 基线钩子（不需要训练，走 API）----
def b5_commercial_mllm(skill_results_dir: str):
    """B5 = 商业多模态 LLM prompt 基线：直接读 skilltest/results/*.json 的 parsed.audience_response / content_sentiment。
    （我们 2026-11-16 十平台实测就是 B5 水位：观众命中 8/20。）"""
    import json, glob, os
    out = {}
    for f in glob.glob(os.path.join(skill_results_dir, "*", "v*.json")):
        j = json.loads(open(f, encoding="utf-8").read())
        p = j.get("parsed") or {}
        out.setdefault(j.get("model"), []).append({
            "video": j.get("video"), "audience": (p.get("audience_response") or {}).get("label"),
            "sentiment": (p.get("content_sentiment") or {}).get("label")})
    return out

def b4_text_llm_placeholder():
    """B4 = 文本-only LLM 基线（ASR+OCR+元数据，无画面）。TODO：接入 ASR（faster-whisper）+ OCR 后走 chat API。"""
    raise NotImplementedError("接入 faster-whisper ASR + OCR 文本后复用 _probe/chat.js 通道")

if __name__ == "__main__":
    try:
        print("B5 导入（本轮实测）：", {k: len(v) for k, v in b5_commercial_mllm(str(config.SKILL_RESULTS)).items()})
    except Exception as e:
        print("B5 导入失败：", e)
