# -*- coding: utf-8 -*-
"""emoji 情感识别：Unicode emoji + 抖音方括号表情（[笑哭]/[捂脸]/[色]…）。

值 = (valence, arousal, dominance, label, emotions)
emoji 是强信号：analyze.py 里按权重 2.5 计入。
"""
from __future__ import annotations

import re

E = {
    # 正向 / 开心
    "😂": (0.75, 0.82, 0.55, "positive", {"joy": 1, "positive": 1}),
    "🤣": (0.75, 0.82, 0.55, "positive", {"joy": 1, "positive": 1}),
    "😊": (0.78, 0.5, 0.6, "positive", {"joy": 1, "trust": 1}),
    "🙂": (0.7, 0.4, 0.55, "positive", {"joy": 1}),
    "😀": (0.75, 0.55, 0.6, "positive", {"joy": 1}),
    "😁": (0.78, 0.6, 0.6, "positive", {"joy": 1}),
    "😆": (0.78, 0.75, 0.55, "positive", {"joy": 1}),
    "😍": (0.88, 0.7, 0.55, "positive", {"joy": 1, "trust": 1}),
    "🥰": (0.88, 0.65, 0.55, "positive", {"joy": 1, "trust": 1}),
    "❤️": (0.88, 0.65, 0.55, "positive", {"trust": 1, "positive": 1}),
    "❤": (0.88, 0.65, 0.55, "positive", {"trust": 1, "positive": 1}),
    "💕": (0.85, 0.65, 0.55, "positive", {"trust": 1}),
    "💖": (0.85, 0.65, 0.55, "positive", {"trust": 1}),
    "😘": (0.85, 0.65, 0.55, "positive", {"trust": 1}),
    "👍": (0.78, 0.55, 0.6, "positive", {"trust": 1, "positive": 1}),
    "🫡": (0.7, 0.5, 0.55, "positive", {"trust": 1}),
    "🔥": (0.8, 0.78, 0.6, "positive", {"joy": 1, "positive": 1}),
    "💯": (0.82, 0.65, 0.6, "positive", {"trust": 1}),
    "🎉": (0.82, 0.7, 0.55, "positive", {"joy": 1}),
    "👏": (0.78, 0.6, 0.55, "positive", {"trust": 1}),
    "🙏": (0.7, 0.55, 0.5, "positive", {"trust": 1}),
    "😭": (0.35, 0.72, 0.35, "negative", {"sadness": 1, "negative": 1}),
    "😢": (0.3, 0.65, 0.35, "negative", {"sadness": 1}),
    "😥": (0.35, 0.6, 0.35, "negative", {"sadness": 1}),
    "🥲": (0.5, 0.65, 0.45, "mixed", {"sadness": 1, "joy": 1}),
    # 负向
    "😡": (0.12, 0.85, 0.4, "negative", {"anger": 1, "negative": 1}),
    "🤬": (0.08, 0.9, 0.4, "negative", {"anger": 1, "negative": 1}),
    "😤": (0.2, 0.8, 0.4, "negative", {"anger": 1}),
    "👎": (0.2, 0.6, 0.4, "negative", {"negative": 1}),
    "💀": (0.5, 0.68, 0.5, "mixed", {}),
    "🤡": (0.35, 0.6, 0.45, "negative", {"disgust": 1}),
    "🙄": (0.35, 0.55, 0.4, "negative", {"disgust": 1}),
    "😅": (0.6, 0.6, 0.5, "mixed", {}),
    "🤔": (0.5, 0.5, 0.5, "neutral", {}),
    "😮": (0.5, 0.8, 0.4, "neutral", {"surprise": 1}),
    "😱": (0.4, 0.9, 0.35, "negative", {"fear": 1, "surprise": 1}),
    "🫠": (0.45, 0.65, 0.4, "mixed", {}),
    "🥴": (0.4, 0.6, 0.4, "mixed", {}),
}

# 抖音方括号表情（[笑哭] 等）
B = {
    "色": (0.75, 0.72, 0.55, "positive", {"joy": 1}),
    "笑哭": (0.72, 0.82, 0.5, "positive", {"joy": 1}),
    "捂脸": (0.55, 0.65, 0.45, "mixed", {}),
    "流泪": (0.3, 0.7, 0.35, "negative", {"sadness": 1}),
    "怒": (0.1, 0.8, 0.4, "negative", {"anger": 1}),
    "点赞": (0.78, 0.55, 0.6, "positive", {"trust": 1}),
    "鼓掌": (0.75, 0.6, 0.55, "positive", {"trust": 1}),
    "比心": (0.85, 0.65, 0.55, "positive", {"trust": 1}),
    "打脸": (0.4, 0.65, 0.45, "negative", {"disgust": 1}),
    "灵机一动": (0.55, 0.6, 0.55, "neutral", {}),
    "玫瑰": (0.8, 0.5, 0.55, "positive", {"trust": 1}),
    "裂开": (0.35, 0.72, 0.4, "negative", {"sadness": 1}),
    "快哭了": (0.35, 0.7, 0.35, "negative", {"sadness": 1}),
    "我想静静": (0.4, 0.45, 0.4, "neutral", {}),
    "摸头": (0.7, 0.45, 0.5, "positive", {"trust": 1}),
    "机智": (0.65, 0.55, 0.55, "positive", {}),
    "微笑": (0.5, 0.4, 0.5, "neutral", {}),
    "尬笑": (0.45, 0.6, 0.4, "mixed", {}),
    "哈欠": (0.4, 0.3, 0.4, "neutral", {}),
    "奋斗": (0.65, 0.6, 0.55, "positive", {}),
    "加油": (0.7, 0.6, 0.55, "positive", {"trust": 1}),
    "干饭": (0.65, 0.55, 0.5, "positive", {}),
    "舔屏": (0.7, 0.7, 0.5, "positive", {"joy": 1}),
    "狗头": (0.6, 0.55, 0.5, "mixed", {}),
    "吃瓜": (0.6, 0.5, 0.5, "neutral", {}),
    "666": (0.8, 0.7, 0.6, "positive", {"trust": 1}),
    "中国赞": (0.8, 0.6, 0.55, "positive", {"trust": 1}),
    "赞": (0.78, 0.55, 0.6, "positive", {"trust": 1}),
    "看": (0.5, 0.5, 0.5, "neutral", {}),
    "嘘": (0.5, 0.5, 0.5, "neutral", {}),
    "what": (0.5, 0.6, 0.45, "neutral", {"surprise": 1}),
    "晕": (0.4, 0.6, 0.4, "mixed", {}),
    "睡": (0.4, 0.3, 0.4, "neutral", {}),
    "酷": (0.7, 0.55, 0.55, "positive", {}),
    "耶": (0.78, 0.65, 0.55, "positive", {"joy": 1}),
    "抱抱": (0.75, 0.5, 0.5, "positive", {"trust": 1}),
    "亲亲": (0.8, 0.6, 0.55, "positive", {"trust": 1}),
    "委屈": (0.35, 0.6, 0.35, "negative", {"sadness": 1}),
    "崩溃": (0.25, 0.75, 0.35, "negative", {"sadness": 1}),
    "吐": (0.2, 0.65, 0.35, "negative", {"disgust": 1}),
    "震惊": (0.5, 0.8, 0.4, "neutral", {"surprise": 1}),
    "泪目": (0.6, 0.7, 0.45, "mixed", {"sadness": 1}),
    "呲牙": (0.72, 0.6, 0.55, "positive", {"joy": 1}),
    "吃瓜群众": (0.6, 0.5, 0.5, "neutral", {}),
}

_BRACKET = re.compile(r"\[([^\[\]]{1,6})\]")


def scan_emoji(text: str) -> list:
    """返回 [(surface, (v,a,d,label,emotions))]，按出现顺序。"""
    hits = []
    for ch in text:
        if ch in E:
            hits.append((ch, E[ch]))
    for m in _BRACKET.finditer(text):
        name = m.group(1).strip()
        if name in B:
            hits.append((m.group(0), B[name]))
    return hits


if __name__ == "__main__":
    for s in ["快去看主播收藏[色]", "笑死😂这也太离谱了", "退钱👎[怒]", "有点东西👍[666]"]:
        print(s, "->", scan_emoji(s))
