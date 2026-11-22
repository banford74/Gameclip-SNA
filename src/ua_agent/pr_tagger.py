# -*- coding: utf-8 -*-
"""
P/R 打标器（本项目主体系）——复用十级体系的「知识蒸馏+投票+置信分层」思路：
  A 路：VLM 直判（P 码 + R 码）
  B 路：规则层（P↔R 表里映射反推：≥2 个映射 R 码命中 → P 候选）
  C 路：语义匹配（可选，bge 可用时启用；当前未装则自动跳过）
  投票：A+B（两路一致→high；单路→medium/low）；A+B+C 时任意两路一致才高置信。
"""
from __future__ import annotations

import json
import re

from .pr_codebook import (P_CODES, R_CODES, p_list_text, r_list_text,
                          validate_pr, rule_p_codes)

PR_SYSTEM = (
    "你是游戏买量素材创意分析师，使用「P 码情节层（15 项）+ R 码视觉特征（91 项）」双层体系打标。"
    "只输出 JSON，不要解释。"
)

PR_USER = """【素材】时长 {duration}s，共 {n} 个关键帧（按时间顺序给出）。
{frame_lines}

【P 码情节层】（可多选；命中必须给证据时间段/帧号；不确定的写「疑似」）
{p_list}

【R 码视觉特征】（91 项；有/无；枚举项给具体值；只列你确认命中的）
{r_list}

【判据】
1. P 码看叙事骨架：整条素材讲什么情节；R 码看画面证据。
2. 每个 P 命中至少对应 1 个 R 码证据；P 与 R 映射表里不一不强制，但要复查。
3. 不得编造效果数值。

【输出 JSON】
{{
  "p_codes": [{{"id": "P104", "evidence": "12-18s 帧3-5"}}],
  "r_codes": {{"R201": "有", "R403": "0%", "R605": "有"}}
}}"""


def _extract_json(text: str):
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}")
        if s != -1 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except json.JSONDecodeError:
                return None
    return None


class PRTagger:
    def __init__(self, vlm):
        self.vlm = vlm

    def tag(self, keyframes, content_summary: str = "", duration: float = 0.0) -> dict:
        frame_lines = "\n".join(
            f"- 帧{i}（t≈{f.timestamp:.1f}s）" for i, f in enumerate(keyframes))
        user = PR_USER.format(
            duration=round(duration, 1), n=len(keyframes), frame_lines=frame_lines,
            p_list=p_list_text(), r_list=r_list_text())
        raw = self.vlm.chat(PR_SYSTEM, user, image_paths=[f.path for f in keyframes])
        data = _extract_json(raw) or {}
        # 降级 1：输出为空（reasoning 吃满预算）→ 只发前 6 帧重试
        if not data and raw.strip() == "" and len(keyframes) > 6:
            raw = self.vlm.chat(PR_SYSTEM, user, image_paths=[f.path for f in keyframes[:6]])
            data = _extract_json(raw) or {}
        # 降级 2：仍为空 → 用画面摘要纯文本再判
        if not data and content_summary:
            raw = self.vlm.chat(PR_SYSTEM, PR_USER.format(
                duration=round(duration, 1), n=len(keyframes), frame_lines=content_summary[:3000],
                p_list=p_list_text(), r_list=r_list_text()), image_paths=[])
            data = _extract_json(raw) or {}
        checked = validate_pr(data)
        pr = checked["pr"]
        # B 路规则层
        rule_p = rule_p_codes(pr["r_codes"])
        a_set = {p["id"] for p in pr["p_codes"]}
        b_set = set(rule_p)
        merged = {pid: {"id": pid, "name": P_CODES[pid]["name"], "source": []} for pid in (a_set | b_set)}
        for pid in merged:
            if pid in a_set:
                merged[pid]["source"].append("vlm")
                merged[pid]["evidence"] = next((p["evidence"] for p in pr["p_codes"] if p["id"] == pid), "")
            if pid in b_set:
                merged[pid]["source"].append("rule")
        # 置信分层（A+B 两路）
        if a_set and b_set:
            agree = a_set & b_set
            confidence = "high" if agree else "medium"
        elif a_set:
            confidence = "medium"
        elif b_set:
            confidence = "low"
        else:
            confidence = "none"
        return {
            "p_codes": list(merged.values()),
            "r_codes": pr["r_codes"],
            "rule_p_candidates": rule_p,
            "confidence": confidence,
            "diagnostics": {
                "p_missing_support": checked["p_missing_support"],
                "errors": checked["errors"],
                "raw_excerpt": raw[:500],
            },
        }
