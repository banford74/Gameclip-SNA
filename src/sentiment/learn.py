# -*- coding: utf-8 -*-
"""从人工标注评论反向学习中文情感词表（bootstrapp 第一层）：
- 统计评论中的 2–3 字 n-gram，按多数票标签算极性均值（pos=+1/neg=-1/neu=0）
- 过滤：出现次数 ≥ 4、|极性| ≥ 0.6 → 入表
- 5 折交叉验证给出诚实准确率；产物 data/lexicons/zh_learned.json
"""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "lexicons"
OUT = DATA / "zh_learned.json"
POL = {"pos": 1.0, "neg": -1.0, "neu": 0.0, "neutral": 0.0, "mixed": 0.0}


def ngrams(text: str, lo: int = 2, hi: int = 3):
    for n in range(lo, hi + 1):
        for i in range(len(text) - n + 1):
            g = text[i:i + n]
            if all("\u4e00" <= ch <= "\u9fff" for ch in g):
                yield g


def build(texts, labels, min_count: int = 4, min_abs: float = 0.6):
    acc = defaultdict(list)
    for t, y in zip(texts, labels):
        pol = POL.get(y, 0.0)
        for g in set(ngrams(t)):
            acc[g].append(pol)
    out = {}
    for g, pols in acc.items():
        if len(pols) < min_count:
            continue
        mean = sum(pols) / len(pols)
        if abs(mean) >= min_abs:
            out[g] = round(mean, 3)
    return out


def load_learned():
    if OUT.exists():
        return json.loads(OUT.read_text(encoding="utf-8"))
    return {}


def score(text: str, learned: dict, seed_terms: set) -> float:
    """投票式打分：learned 词按极性，seed 词权重更高。返回 [-1,1] 的净极性。"""
    num = den = 0.0
    for n in (3, 2):
        for i in range(len(text) - n + 1):
            g = text[i:i + n]
            if g in learned:
                num += learned[g] * 2.0
                den += 2.0
    for s in seed_terms:
        if s in text:
            num += 0.0  # seed 只作为非中性证据（不细调），下面单独处理
    return num / den if den else 0.0


def predict(text: str, learned: dict, seed_pos: set, seed_neg: set, thr: float = 0.15) -> str:
    pos = neg = 0.0
    for n in (3, 2):
        for i in range(len(text) - n + 1):
            g = text[i:i + n]
            if g in learned:
                pol = learned[g]
                (pos if pol > 0 else neg) and None
                if pol > 0:
                    pos += pol * 2.0
                else:
                    neg += -pol * 2.0
    for s in seed_pos:
        if s in text:
            pos += 3.0
    for s in seed_neg:
        if s in text:
            neg += 3.0
    if pos == 0 and neg == 0:
        return "neutral"
    if pos >= neg * 1.3 and pos > thr:
        return "positive"
    if neg >= pos * 1.3 and neg > thr:
        return "negative"
    return "neutral"


def cv(texts, labels, folds: int = 5, seed: int = 0):
    idx = list(range(len(texts)))
    random.Random(seed).shuffle(idx)
    fs = [idx[i::folds] for i in range(folds)]
    seed_data = json.loads((DATA / "zh_seed.json").read_text(encoding="utf-8"))
    sp = set(seed_data["positive"]) | set(seed_data["mixed"])
    sn = set(seed_data["negative"])
    correct = total = 0
    for k in range(folds):
        test = set(fs[k])
        tr = [i for i in idx if i not in test]
        learned = build([texts[i] for i in tr], [labels[i] for i in tr])
        for i in fs[k]:
            pred = predict(texts[i], learned, sp, sn)
            correct += int(pred == labels[i])
            total += 1
    return correct / total, total


if __name__ == "__main__":
    raw = json.loads(Path("skilltest/comments/v2_raw_7704603474591239451.json").read_text(encoding="utf-8"))
    lab = json.loads(Path("skilltest/comments/v2_raw_7704603474591239451_labeled.json").read_text(encoding="utf-8"))
    texts = raw["comments"]
    raters = list(lab["ratings"].values())
    labels = []
    from collections import Counter
    for i in range(len(texts)):
        votes = [r["labels"][i] for r in raters if i < len(r["labels"])]
        if not votes:
            labels.append("neutral")
            continue
        maj = Counter(votes).most_common(1)[0][0]
        labels.append("neutral" if maj == "neu" else maj)
    acc, n = cv(texts, labels)
    print(f"CV acc = {acc:.3f} (n={n})")
    learned = build(texts, labels)
    OUT.write_text(json.dumps(learned, ensure_ascii=False, indent=1), encoding="utf-8")
    print("learned terms:", len(learned))
    for g in ["好玩", "垃圾", "坑", "好看", "退钱", "离了", "笑死", "香", "贵", "拉胯"]:
        print(g, learned.get(g))
