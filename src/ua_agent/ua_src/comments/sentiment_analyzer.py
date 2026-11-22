"""目标5：评论情感分析。

两路实现：
  1) 大模型批量分析（优先）：一次请求对全部评论打标 positive/neutral/negative + 主题 aspect
  2) 中文情感词典兜底（离线）：正负向词表 + 否定词处理，无 API 也能跑

输出每条评论的情感标签与置信度，并可汇总分布与高频主题。
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Optional

from ..platforms.base import Comment
from ..vision.vlm_client import VLMClient

# ---------------- 中文情感词典（精简可扩展） ----------------
LEXICON_POS = {
    "喜欢", "爱", "好评", "赞", "不错", "好", "棒", "厉害", "强", "香", "绝",
    "支持", "种草", "入手", "买", "值", "划算", "实惠", "好看", "好用", "舒服",
    "满意", "惊喜", "推荐", "可爱", "美", "牛", "真香", "可以", "优秀", "贴心",
}
LEXICON_NEG = {
    "差", "烂", "坑", "骗", "假", "贵", "坑人", "无语", "垃圾", "难用", "难看",
    "失望", "后悔", "踩雷", "劝退", "恶心", "虚假", "夸大", "割韭菜", "退款",
    "差评", "敷衍", "丑", "丑陋", "慢", "卡", "崩", "糊", "low", "lowb", "low逼",
}
NEGATIONS = {"不", "没", "无", "别", "莫", "非", "未", "甭", "毫不", "绝不", "没有"}


@dataclass
class SentimentResult:
    comment_id: str
    text: str
    label: str = "neutral"      # positive / neutral / negative
    score: float = 0.5          # 0(极负) ~ 1(极正)
    aspect: str = ""            # 情感指向的主题
    method: str = "lexicon"     # lexicon / llm
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "comment_id": self.comment_id, "text": self.text, "label": self.label,
            "score": round(self.score, 3), "aspect": self.aspect,
            "method": self.method, "error": self.error,
        }


def lexicon_sentiment(text: str) -> (str, float):
    """基于词典与否定词的情感打分，返回 (label, score)。

    采用子串检索而非分词：在文本中查找每个词典词，检测其前方 2 字内是否含否定词，
    若否定则极性反转。可正确处理「划算/入手/踩雷」等多字中文情感词。
    """
    text = text.lower()
    pos = neg = 0

    def _count(words, flip_sign):
        nonlocal pos, neg
        for w in words:
            for m in re.finditer(re.escape(w), text):
                window = text[max(0, m.start() - 2):m.start()]
                negated = any(n in window for n in NEGATIONS)
                sign = -1 if negated else 1
                if flip_sign > 0:
                    pos += sign
                else:
                    neg += sign

    _count(LEXICON_POS, 1)
    _count(LEXICON_NEG, -1)

    if pos > neg:
        return "positive", min(1.0, 0.5 + 0.1 * (pos - neg))
    if neg > pos:
        return "negative", max(0.0, 0.5 - 0.1 * (neg - pos))
    return "neutral", 0.5


class SentimentAnalyzer:
    def __init__(self, vlm: Optional[VLMClient] = None):
        self.vlm = vlm

    # ---------- 离线词典分析 ----------
    def analyze_lexicon(self, comments: List[Comment]) -> List[SentimentResult]:
        out = []
        for c in comments:
            label, score = lexicon_sentiment(c.text)
            out.append(SentimentResult(
                comment_id=c.id, text=c.text, label=label, score=score, method="lexicon"))
        return out

    # ---------- 大模型批量分析 ----------
    def analyze_llm(self, comments: List[Comment]) -> List[SentimentResult]:
        if not self.vlm or self.vlm.mock:
            return self.analyze_lexicon(comments)
        items = [{"id": c.id, "text": c.text} for c in comments]
        system = "你是中文评论情感分析专家，只输出 JSON 数组，不输出任何解释。"
        user = (
            "对下列评论做情感分析，返回 JSON 数组，每项格式：\n"
            '{"id": "评论id", "label": "positive|neutral|negative", '
            '"score": 0到1之间的小数, "aspect": "情感指向的主题，如 价格/质量/客服"}\n'
            f"评论列表：\n{json.dumps(items, ensure_ascii=False)}"
        )
        raw = self.vlm.chat(system, user, image_paths=None)
        data = self._extract_json_list(raw)
        mapping = {d.get("id"): d for d in data} if data else {}
        out = []
        for c in comments:
            d = mapping.get(c.id)
            if d:
                out.append(SentimentResult(
                    comment_id=c.id, text=c.text,
                    label=d.get("label", "neutral"), score=float(d.get("score", 0.5)),
                    aspect=d.get("aspect", ""), method="llm"))
            else:
                label, score = lexicon_sentiment(c.text)
                out.append(SentimentResult(
                    comment_id=c.id, text=c.text, label=label, score=score, method="lexicon-fallback"))
        return out

    @staticmethod
    def _extract_json_list(text: str):
        text = text.strip()
        m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            s, e = text.find("["), text.rfind("]")
            if s != -1 and e != -1:
                try:
                    return json.loads(text[s:e + 1])
                except json.JSONDecodeError:
                    return None
        return None

    def analyze(self, comments: List[Comment], use_llm: bool = True) -> List[SentimentResult]:
        if use_llm and self.vlm and not self.vlm.mock:
            return self.analyze_llm(comments)
        return self.analyze_lexicon(comments)


def sentiment_summary(results: List[SentimentResult]) -> dict:
    """汇总情感分布与高频主题。"""
    total = len(results) or 1
    dist = Counter(r.label for r in results)
    aspects = Counter(r.aspect for r in results if r.aspect)
    avg_score = sum(r.score for r in results) / total
    return {
        "total": len(results),
        "distribution": {
            "positive": dist.get("positive", 0),
            "neutral": dist.get("neutral", 0),
            "negative": dist.get("negative", 0),
        },
        "positive_ratio": round(dist.get("positive", 0) / total, 3),
        "negative_ratio": round(dist.get("negative", 0) / total, 3),
        "average_score": round(avg_score, 3),
        "top_aspects": [a for a, _ in aspects.most_common(8)],
    }
