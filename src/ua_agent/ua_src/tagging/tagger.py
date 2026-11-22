"""买量视频十级标签打标（目标：根据标签系统为素材达标）。

设计：
- 输入：视频内容理解摘要（来自 G3 跨帧聚合）+ 十级字段受控词表（用户提供的 {层级: [候选值]}）
- 输出：每个层级选中的值（dict），严格限制在候选值内，避免自由发挥导致口径不一致
- 由 VLM 在候选值中做"最贴切匹配"，可选层级允许返回空/不适用
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

from ..vision.vlm_client import VLMClient

LEVEL_KEYS = ["一级字段", "二级字段", "三级字段", "四级字段", "五级字段",
              "六级字段", "七级字段", "八级字段", "九级字段", "十级字段"]

SYSTEM_PROMPT = (
    "你是买量视频标签专家。我会给你一段视频的内容理解摘要，以及十个层级各自的候选标签值。"
    "请为每一层级从对应候选值中选出最贴切的一个。规则：\n"
    "1. 只能从给定候选值中选，不得自行编造；\n"
    "2. 若某一层级内容确实不涉及、无合适候选，就选该层级候选中的「空/无/不适用」项（若无此类项则填空字符串）；\n"
    "3. 只输出 JSON，键为层级名（一级字段…十级字段），值为选中的候选值字符串。"
)

USER_TEMPLATE = (
    "【视频内容摘要】\n{summary}\n\n"
    "【各层级候选值】\n{candidates}\n\n"
    "请为每一层级选择最贴切的候选值，输出 JSON。"
)


def _format_candidates(vocab: Dict[str, List[str]]) -> str:
    lines = []
    for k in LEVEL_KEYS:
        vals = vocab.get(k, [])
        lines.append(f"- {k}: { ' / '.join(vals) if vals else '(无候选)' }")
    return "\n".join(lines)


class Tagger:
    def __init__(self, vlm: VLMClient):
        self.vlm = vlm

    def tag(self, content_summary: str, vocab: Dict[str, List[str]],
            retries: int = 2) -> Dict[str, str]:
        """根据内容摘要 + 受控词表，返回 {层级: 选中值}。"""
        prompt = USER_TEMPLATE.format(
            summary=content_summary,
            candidates=_format_candidates(vocab),
        )
        last_err = None
        for _ in range(retries + 1):
            try:
                raw = self.vlm.chat(SYSTEM_PROMPT, prompt, image_paths=[])
                data = self._parse(raw, vocab)
                if data:
                    return data
            except Exception as e:  # noqa: BLE001
                last_err = e
        # 兜底：全部留空，交由人工补
        return {k: "" for k in LEVEL_KEYS}

    @staticmethod
    def _parse(raw: str, vocab: Dict[str, List[str]]) -> Optional[Dict[str, str]]:
        import re
        text = raw.strip()
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            s, e = text.find("{"), text.rfind("}")
            if s != -1 and e != -1:
                try:
                    data = json.loads(text[s:e + 1])
                except json.JSONDecodeError:
                    return None
            else:
                return None
        # 校验：值必须在候选内（允许空字符串），超界则回退空
        allowed = {k: set(vocab.get(k, [])) for k in LEVEL_KEYS}
        out = {}
        for k in LEVEL_KEYS:
            v = data.get(k, "")
            if not isinstance(v, str):
                v = str(v)
            if v in allowed[k] or v == "":
                out[k] = v
            else:
                # 不在候选内：留空，避免脏数据
                out[k] = ""
        return out
