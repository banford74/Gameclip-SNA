# -*- coding: utf-8 -*-
"""
P/R → 情感向度映射（Task A→B 的规则原型，后续用 bootstrap/微调替换先验）。

- 每个 P 码带一条情感先验：期望 valence / arousal / 标签倾向 / 解释
- 输入：P 码命中 + 内容 VAD（词典口径）+ 可选评论实测
- 输出：评论 valence 分布预测 {pos,neg,neu} + VAD + 依据（可解释）
- 先验表是可学习对象：bootstrap 阶段用 gold（human_correction）更新此表 → priors.json
"""
from __future__ import annotations

# P 码先验：p_id -> (valence 0-1, arousal 0-1, 主导情绪, 说明)
PRIORS = {
    "P101": (0.42, 0.75, "mixed", "社死名场面：尴尬+好笑，正文情绪偏混合，观众易共情但非真负面"),
    "P102": (0.48, 0.55, "neutral", "伏地魔：猥琐发育，好笑但偏中性"),
    "P103": (0.55, 0.85, "positive", "决赛圈：悬念拉满，胜负未知但爽感强"),
    "P104": (0.55, 0.85, "positive", "刚枪对掏：枪法爽感，正向高唤醒"),
    "P105": (0.68, 0.45, "positive", "回忆杀：情怀共鸣，正向中低唤醒"),
    "P106": (0.45, 0.65, "neutral", "伏击阴人：战术阴谋感，偏中性"),
    "P107": (0.62, 0.85, "positive", "团灭灭队：高光压制，正向高唤醒"),
    "P108": (0.48, 0.7, "neutral", "堵桥：一夫当关爽感但对抗性强"),
    "P109": (0.58, 0.6, "positive", "舔包搜刮：收集满足感，正向"),
    "P110": (0.48, 0.7, "neutral", "攻楼守楼：攻防紧张，偏中性"),
    "P111": (0.6, 0.75, "positive", "空投争夺：稀缺期待，正向高唤醒"),
    "P112": (0.55, 0.85, "positive", "刺激追逃：肾上腺素，正向高唤醒"),
    "P113": (0.6, 0.7, "positive", "载具追梦：极限操作名场面"),
    "P114": (0.65, 0.6, "positive", "变装变身：外观颜值向，正向"),
    "P115": (0.55, 0.7, "mixed", "真人整活：反差笑点，混合"),
}

# R 码对情感的辅助修正（少量强信号）
R_MODIFIERS = {
    "R455": -0.08,   # 吐槽/锐评：拉低 valence
    "R451": +0.02,   # 社死/搞笑梗：微调
    "R453": +0.06,   # 情感/回忆杀：拉高
    "R452": +0.05,   # 逆风翻盘/爽点
    "R501": +0.03,   # 福利文案
    "R502": +0.03,   # 福利CTA
    "R601": 0.0,     # 纯游戏实录：中性
}


def predict_comment_valence(pr: dict | None, content_vad: dict | None = None,
                            comment_obs: dict | None = None) -> dict:
    """
    pr: {"p_codes": [{"id": ...}], "r_codes": {...}}
    content_vad: {"valence":..., "arousal":...} 词典口径
    comment_obs: {"net": ..., "dist": ...} 实测（若有，作为校准）
    返回 {"valence","arousal","label","dist":{"pos","neg","neu"},"rationale","priors_used"}
    """
    pr = pr or {}
    hits = [p for p in (pr.get("p_codes") or [])]
    ids = [p["id"] if isinstance(p, dict) else p for p in hits]
    vs, ars, used = [], [], []
    for pid in ids:
        if pid in PRIORS:
            v, a, _l, _d = PRIORS[pid]
            vs.append(v); ars.append(a); used.append(pid)
    r_hits = pr.get("r_codes") or {}
    adj = sum(mod for rid, mod in R_MODIFIERS.items()
              if r_hits.get(rid) not in (None, "", "无"))
    if content_vad:
        vs.append(float(content_vad.get("valence", 0.5)) * 1.0)
        ars.append(float(content_vad.get("arousal", 0.5)))
        used.append("content_vad")
    val = (sum(vs) / len(vs) if vs else 0.5) + adj
    ar = sum(ars) / len(ars) if ars else 0.5
    val = max(0.05, min(0.95, val))
    # 由 valence 生成三分类分布（温度控制：越极端越集中）
    spread = 0.55
    pos = max(0.02, (val - 0.5) + spread * val * (1 - val))
    neg = max(0.02, (0.5 - val) + spread * val * (1 - val))
    neu = max(0.05, 1 - pos - neg)
    s = pos + neg + neu
    dist = {"pos": round(pos / s, 3), "neg": round(neg / s, 3), "neu": round(neu / s, 3)}
    label = "positive" if val >= 0.6 else ("negative" if val <= 0.4 else "neutral")
    rationale = f"基于 P 码先验 {used} + R 码修正 {adj:+.2f}；内容 VAD v={content_vad.get('valence') if content_vad else 'n/a'}"
    if comment_obs:
        rationale += f"；已观测评论净情绪 {comment_obs.get('net')}（可作为校准误差）"
    return {"valence": round(val, 4), "arousal": round(ar, 4), "label": label,
            "dist": dist, "rationale": rationale, "priors_used": used}


if __name__ == "__main__":
    demo = {"p_codes": [{"id": "P104"}, {"id": "P113"}], "r_codes": {"R451": "有", "R455": "无"}}
    print(predict_comment_valence(demo, {"valence": 0.62, "arousal": 0.7}))
