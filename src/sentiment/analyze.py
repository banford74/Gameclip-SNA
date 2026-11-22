# -*- coding: utf-8 -*-
"""
情感向度分析器：词典 + 否定/程度修饰 → VAD（valence/arousal/dominance）+ 标签 + 强度。

- 词典 = 中文种子词典（口语/网络语） ∪ NRC 多语言对齐表导出的中文词表（可开关）
- 匹配 = 最长匹配优先（1–4 字窗口扫描）
- 否定 = 词前 2 字内出现 不/没/无/别/未/莫/非 → valence 翻转
- 程度 = 前 1–2 字出现 太/超/特别/非常/极其/巨/贼 → arousal+0.1，|v-0.5| 放大
- 输出 label = positive/negative/neutral/mixed；intensity = 1–4；emotions 来自 NRC-Emotion
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .lexicons import build_vad, build_emo, EMOTIONS
from .emoji import scan_emoji, _BRACKET

SEED = Path(__file__).resolve().parents[2] / "data" / "lexicons" / "zh_seed.json"

NEGATORS = set("不没无别未莫非")
INTENSIFIERS = ["太", "超", "特别", "非常", "极其", "巨", "贼", "很", "最"]
# 高频功能词/名词：NRC 词级翻译里会误入情感词，禁止参与打分
STOPWORDS = set("""什么 根本 一般 感觉 皮肤 游戏 这波 东西 时候 一样 可能 现在 已经 就是 还是 但是 因为 所以 然后
如果 没有 一个 这种 那种 真的 不是 自己 知道 觉得 看到 听到 一起 大家 我们 你们 他们 这个 那个 一些 可以
需要 应该 希望 事情 问题 情况 地方 世界 生活 工作 时间 今天 昨天 明天 视频 主播 玩家 角色 武器 地图 模式 版本
活动 更新 抽奖 概率 价格 数值 伤害 攻击 防御 技能 装备 时装 特效 画面 音效 剧情 玩法 操作 手感 强度 平衡 来源
其实 确实 当然 虽然 不过 而且 并且 或者 还有 以及 关于 对于 由于 通过 根据 按照 随着 比如 例如 包括 其中
儿子 奶粉 养老金 兄弟 最佳 手法 奔跑 以前 信条 怜悯 僵尸 近战 修罗 沙鹰 暗区 突围 三角洲 黑海 北极星 重塑
黑伤 影之刃 刀光 刀皮 一般般 一般 还行 凑合 差不多 随便 无所谓 感觉 不知道 可能 大概""".split())

_vad = None
_emo = None
_seed = None
_terms = None
_SEED_TERMS = set()


def _load():
    global _vad, _emo, _seed, _terms, _SEED_TERMS
    if _vad is not None:
        return
    _vad = build_vad()
    _emo = build_emo()
    _seed = json.loads(SEED.read_text(encoding="utf-8"))
    merged = dict(_vad.get("zh") or {})
    _SEED_TERMS = set()
    for group in ("positive", "negative", "mixed"):
        for w, v in _seed.get(group, {}).items():
            merged[w] = v
            _SEED_TERMS.add(w)
    _terms = {}
    for t, v in merged.items():
        if re.search(r"[A-Za-z?？!！]", t) or len(t) > 6 or t in STOPWORDS:
            continue
        if len(t) >= 4 and re.search(r"(.)\1", t):   # 去重复字符的乱码词（保留「绝绝子」等三字叠词）
            continue
        # NRC 派生词（非种子）要求强极性，弱情感词一律丢弃（噪声主要来源）
        if t not in _SEED_TERMS and abs(v[0] - 0.5) < 0.2:
            continue
        _terms.setdefault(len(t), {})[t] = v
    # 单字只保留常见情感字
    keep1 = set("好差烂坑爽帅美丑香臭赞惨棒绝强弱烦怕笑哭怒喜乐悲苦甜酸辣累慌尬酷萌秀菜牛吊蠢笨神魔")
    if 1 in _terms:
        _terms[1] = {t: v for t, v in _terms[1].items() if t in keep1}


def _scan(text: str):
    """返回 [(term, vad)]，最长匹配、不重叠。"""
    _load()
    hits = []
    i = 0
    maxlen = max(_terms) if _terms else 0
    while i < len(text):
        matched = False
        for L in range(min(maxlen, len(text) - i), 0, -1):
            bucket = _terms.get(L)
            if bucket:
                t = text[i:i + L]
                if t in bucket:
                    hits.append((t, bucket[t], i))
                    i += L
                    matched = True
                    break
        if not matched:
            i += 1
    return hits


def analyze(text: str, use_nrc: bool = True) -> dict:
    """对一段文本算情感 VAD。"""
    if not text or not text.strip():
        return {"label": "neutral", "intensity": 1, "valence": 0.5, "arousal": 0.3,
                "dominance": 0.5, "n_hits": 0, "hits": [], "emotions": {}}
    # 转折：只取最后一个转折词之后的内容（「这个好，但是那个不行」以尾句为准）
    m = None
    for conj in ("但是", "不过", "可是", "然而", "可惜"):
        i = text.rfind(conj)
        if i > 0 and (m is None or i > m):
            m = i
    if m is not None and len(text) - m >= 5:
        text = text[m + 2:]
    # 虚拟语气吐槽：「要是/如果…就好了/就爽了」= 抱怨现状
    if re.search(r"(要是|如果|假如|倘若)", text) and re.search(r"(就好|就爽|就帅|就美|就完美|就舒服)", text):
        return {"label": "negative", "intensity": 2, "valence": 0.35, "arousal": 0.5,
                "dominance": 0.4, "n_hits": 0, "hits": [{"term": "虚拟语气吐槽", "v": 0.35}], "emotions": {}}
    emoji_hits = scan_emoji(text)
    scan_text = _BRACKET.sub(" ", text)          # 方括号表情已单独识别，避免重复计分
    hits = _scan(scan_text)
    if not use_nrc:
        hits = [h for h in hits if h[0] in _seed_index()]
    if not hits and not emoji_hits:
        return {"label": "neutral", "intensity": 1, "valence": 0.5, "arousal": 0.3,
                "dominance": 0.5, "n_hits": 0, "hits": [], "emotions": {}}
    vs, ars, ds, ws = [], [], [], []
    emo_agg = {}
    pos_score = neg_score = 0.0
    last = None  # (term, v2, end_idx)
    for term, (v, a, d), idx in hits:
        v2 = v
        # 否定：词前 2 字
        before = scan_text[max(0, idx - 2):idx]
        if any(ch in NEGATORS for ch in before):
            v2 = 1.0 - v2
        # 程度修饰
        intn = 1.0
        before3 = scan_text[max(0, idx - 3):idx]
        if any(w in before3 for w in INTENSIFIERS):
            intn = 1.2
            a = min(1.0, a + 0.1)
        v2 = 0.5 + (v2 - 0.5) * intn
        # 「好/太/超 + 负面词」：好不是正面，是程度加强
        if last and v2 < 0.5 and last[1] > 0.5 and last[2] == idx and last[0] in ("好", "太", "超", "很", "巨", "贼"):
            vs.pop(); ars.pop(); ds.pop(); ws.pop()
            v2 = max(0.0, 0.5 - (0.5 - v2) * 1.3)   # 好/太 + 负面词 = 更负面
            last = None
        w_ = 2.0 if term in _SEED_TERMS else 1.0   # 种子词典更可靠，双权重
        vs.append(v2); ars.append(a); ds.append(d); ws.append(w_)
        last = (term, v2, idx + len(term))
        if v2 > 0.5:
            pos_score += (v2 - 0.5) * 2 * w_
        else:
            neg_score += (0.5 - v2) * 2 * w_
    # emoji（强信号，权重 2.5）
    for surface, (v, a, d, lab, emos) in emoji_hits:
        vs.append(v); ars.append(a); ds.append(d); ws.append(2.5)
        for k, val_ in (emos or {}).items():
            emo_agg[k] = emo_agg.get(k, 0) + val_
        if v > 0.5:
            pos_score += (v - 0.5) * 2 * 2.5
        else:
            neg_score += (0.5 - v) * 2 * 2.5
    total_w = sum(ws)
    if total_w < 2.0:                              # 证据不足 → 中性（宁可保守）
        return {"label": "neutral", "intensity": 1, "valence": 0.5, "arousal": 0.3,
                "dominance": 0.5, "n_hits": len(hits), "hits": [{"term": t, "v": round(v[0], 3)} for t, v, _ in hits[:12]],
                "emotions": {}}
    val = sum(v * w for v, w in zip(vs, ws)) / total_w
    ar = sum(ars) / len(ars)
    dom = sum(ds) / len(ds)
    if pos_score > 0 and neg_score > 0 and min(pos_score, neg_score) / max(pos_score, neg_score) > 0.5:
        label = "mixed"
    elif val >= 0.6:
        label = "positive"
    elif val <= 0.4:
        label = "negative"
    else:
        label = "neutral"
    intensity = 1
    if abs(val - 0.5) >= 0.3:
        intensity = 4
    elif abs(val - 0.5) >= 0.15:
        intensity = 3
    elif abs(val - 0.5) >= 0.05:
        intensity = 2
    # 情感细分（NRC + emoji）
    emo = dict(emo_agg)
    for term, _v, _i in hits:
        e = (_emo.get("zh") or {}).get(term)
        if e:
            for k, val_ in e.items():
                if val_:
                    emo[k] = emo.get(k, 0) + 1
    return {"label": label, "intensity": intensity,
            "valence": round(val, 4), "arousal": round(ar, 4), "dominance": round(dom, 4),
            "n_hits": len(hits) + len(emoji_hits), "hits": [{"term": t, "v": round(v[0], 3)} for t, v, _ in hits[:12]]
            + [{"term": s, "v": round(v, 3)} for s, (v, _a, _d, _l, _e) in emoji_hits[:6]],
            "emotions": emo}


def _seed_index():
    return {w for g in ("positive", "negative", "mixed") for w in _seed.get(g, {})}


def analyze_many(texts: list[str]) -> dict:
    """评论集合 → 分布 + 均值 VAD。"""
    from collections import Counter
    labels = []
    v = a = d = 0.0
    n = 0
    details = []
    for t in texts:
        r = analyze(t)
        labels.append(r["label"])
        v += r["valence"]; a += r["arousal"]; d += r["dominance"]; n += 1
        details.append(r)
    c = Counter(labels)
    total = max(n, 1)
    return {"n": n, "dist": {k: round(c.get(k, 0) / total, 4) for k in ("positive", "negative", "neutral", "mixed")},
            "net": round((c.get("positive", 0) - c.get("negative", 0)) / total, 4),
            "mean_valence": round(v / total, 4), "mean_arousal": round(a / total, 4),
            "mean_dominance": round(d / total, 4), "details": details}


if __name__ == "__main__":
    for s in ["这个皮肤太好看了，冲了", "太坑了，根本不好玩", "一般般吧，没什么感觉", "笑死，这也太离谱了"]:
        print(s, "->", json.dumps(analyze(s), ensure_ascii=False))
