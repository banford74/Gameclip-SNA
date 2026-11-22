# -*- coding: utf-8 -*-
"""情感词典层：从 NRC-VAD / NRC-Emotion 多语言对齐表构建中文+英文词典并缓存。

数据来源（用户提供，仅字典可用）：
  NRC-VAD-Lexicon-ForVariousLanguages.txt   英文词 + V/A/D(0-1) + 各语言翻译列
  NRC-Emotion-Lexicon-ForVariousLanguages.txt  英文词 + 10 维情感 0/1 + 各语言翻译列

构建逻辑：以翻译列（Chinese-Simplified / Japanese / English 原词）为键，继承该行 VAD/情感分数。
输出缓存：data/lexicons/vad.json、emo.json（首次构建后直接读缓存）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data" / "lexicons"
VAD_SRC = Path(r"D:\old_E\C盘文件\学习\研\硕士\毕业论文\情感分析\NRC-VAD-Lexicon\NRC-VAD-Lexicon-ForVariousLanguages.txt")
EMO_SRC = Path(r"D:\old_E\C盘文件\学习\研\硕士\毕业论文\情感分析\NRC-Emotion-Lexicon\NRC-Emotion-Lexicon-ForVariousLanguages.txt")

EMOTIONS = ["anger", "anticipation", "disgust", "fear", "joy", "negative", "positive", "sadness", "surprise", "trust"]


def _read_tsv(path: Path):
    with open(path, encoding="utf-8", errors="replace") as f:
        rows = [line.rstrip("\n").split("\t") for line in f]
    header = rows[0]
    return header, rows[1:]


def _zh_col(header: list) -> int:
    for i, h in enumerate(header):
        if "Chinese-Simplified" in h:
            return i
    raise KeyError("Chinese-Simplified column not found")


def _clean_terms(s: str) -> list[str]:
    """翻译列可能是多词（用 ；/；、/ 或空格分隔）→ 拆成候选词。"""
    if not s:
        return []
    parts = re.split(r"[;；、/|，,\s]+", s.strip())
    return [p.strip() for p in parts if p.strip() and len(p.strip()) <= 8]


def build_vad(force: bool = False) -> dict:
    """构建 {lang: {term: [v,a,d]}}，lang ∈ zh/en。"""
    DATA.mkdir(parents=True, exist_ok=True)
    cache = DATA / "vad.json"
    if cache.exists() and not force:
        return json.loads(cache.read_text(encoding="utf-8"))
    if not VAD_SRC.exists():
        raise FileNotFoundError(VAD_SRC)
    header, rows = _read_tsv(VAD_SRC)
    zh_i = _zh_col(header)
    out = {"zh": {}, "en": {}}
    for r in rows:
        try:
            v, a, d = float(r[1]), float(r[2]), float(r[3])
        except (IndexError, ValueError):
            continue
        en = r[0].strip()
        if en:
            out["en"][en] = [v, a, d]
        if zh_i < len(r):
            for t in _clean_terms(r[zh_i]):
                out["zh"].setdefault(t, [v, a, d])
    cache.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def build_emo(force: bool = False) -> dict:
    """构建 {lang: {term: {emotion: 0/1}}}。"""
    DATA.mkdir(parents=True, exist_ok=True)
    cache = DATA / "emo.json"
    if cache.exists() and not force:
        return json.loads(cache.read_text(encoding="utf-8"))
    if not EMO_SRC.exists():
        raise FileNotFoundError(EMO_SRC)
    header, rows = _read_tsv(EMO_SRC)
    zh_i = _zh_col(header)
    idx = {e: header.index(e) for e in EMOTIONS if e in header}
    out = {"zh": {}, "en": {}}
    for r in rows:
        emo = {}
        for e, i in idx.items():
            try:
                emo[e] = int(float(r[i] or 0))
            except (ValueError, IndexError):
                emo[e] = 0
        if not any(emo.values()):
            continue
        en = r[0].strip()
        if en:
            out["en"][en] = emo
        if zh_i < len(r):
            for t in _clean_terms(r[zh_i]):
                out["zh"].setdefault(t, emo)
    cache.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


if __name__ == "__main__":
    v = build_vad()
    e = build_emo()
    print("vad zh/en:", len(v["zh"]), len(v["en"]))
    print("emo zh/en:", len(e["zh"]), len(e["en"]))
    for w in ["好玩", "太坑了", "可爱", "垃圾", "开心"]:
        print(w, v["zh"].get(w), e["zh"].get(w))
