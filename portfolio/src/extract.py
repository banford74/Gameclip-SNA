# -*- coding: utf-8 -*-
"""GameClip Task-A extractor: video metadata + sampled frames -> validated structured record.

Design:
  1. build_prompt()  — states the P/R codebook + required JSON shape once.
  2. call_model()    — JSON mode (response_format=json_object) so text parses; images as data URLs.
  3. validate()      — schema checks (enum/evidence/codebook membership); returns error list.
  4. extract()       — JSON parse -> validate -> (on error) repair round: re-ask with the error list,
                       max REPAIRS rounds; every attempt is logged.

Mock mode (--mock / mock=True) is deterministic and offline: it exercises the same
parse -> validate -> repair path with canned model outputs so the robustness harness
and unit checks run without API cost.
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

try:  # requests is convenient but optional — the repo must run on a bare stdlib Python too
    import requests
except ImportError:  # pragma: no cover
    requests = None

OPENCODE_BASE = os.environ.get("OPENCODE_BASE_URL", "https://opencode.ai/inference/openai/v1").rstrip("/")
API_URL = OPENCODE_BASE + "/chat/completions"
API_KEY = os.environ.get("OPENCODE_API_KEY", "")
MODEL = os.environ.get("OPENCODE_MODEL", "deepseek-v4.1-flash")
# 端点前面有 Cloudflare：显式带浏览器 UA，避免指纹规则变动时整批 403
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")

REPAIRS = 2                      # repair rounds after the first attempt
MAX_FRAMES = 20                  # hard cap on frames per request
MAX_IMAGE_BYTES = 512 * 1024     # per-frame budget (frames are ~512px jpg)

HERE = Path(__file__).resolve().parent
CODEBOOK = json.loads((HERE / "codebook.json").read_text(encoding="utf-8"))
P_IDS = {k for k in CODEBOOK["p"]}
R_IDS = {k for k in CODEBOOK["r"]}
STANCE = {"positive", "negative", "neutral", "mixed"}


class ItemError(Exception):
    """An input item we refuse to process (empty input, missing frames, ...)."""


def _codebook_lines(limit: int = 40) -> str:
    p = " | ".join(f"{k} {v['name']}" for k, v in CODEBOOK["p"].items())
    r = " | ".join(f"{k} {v['name']}" for k, v in list(CODEBOOK["r"].items())[:limit])
    return f"P 码（情节层，可多选）：{p}\nR 码（视觉特征，命中即列出）：{r}"


def build_prompt(item: dict) -> str:
    title = (item.get("title") or "").strip()
    author = (item.get("author") or "").strip()
    dur = item.get("duration_s")
    frames = item.get("frames") or []
    if not title and not frames:
        raise ItemError("empty item: no title and no frames")
    if not frames:
        raise ItemError("no frames")
    if dur is not None and (not isinstance(dur, (int, float)) or dur <= 0):
        raise ItemError(f"bad duration: {dur!r}")
    step = max(1, round((dur or len(frames) * 2) / max(1, len(frames))))
    n = min(len(frames), MAX_FRAMES)
    return f"""你是一名游戏买量素材创意分析师。对下面这条抖音游戏短视频，用「P 码情节层 + R 码视觉特征」体系拆解，并判断内容情绪倾向（四分类）。

【素材】{item.get('video_id', 'unknown')}
标题/描述：{title or '（无）'}
作者：{author or '（未知）'}；时长：{dur if dur is not None else '未知'}s；抽帧间隔：每 {step}s 一帧，共 {n} 帧（按时间顺序给出，帧名即时间点）。

【打标体系】
{_codebook_lines()}

【硬性纪律】
1. 每个结论必须能指到具体帧/秒数（如 "f_04 12s"）；没有证据的不要写。
2. content_sentiment.label 只能是 positive / negative / neutral / mixed 之一：mixed 指同一素材内正负情绪并置或反转（先惨后爽、反差打脸），"情绪强烈"或"正向为主但带吐槽"不算 mixed。
3. confidence 为 0-1 小数。
4. 只输出一个 JSON 对象，不要 markdown、不要解释。字段严格如下：
{{"one_liner": "…", "content_sentiment": {{"label": "positive|negative|neutral|mixed", "intensity": 1, "evidence": "…"}},
 "p_codes": [{{"id": "P104", "evidence": "12-18s 帧 f_07-f_09"}}], "r_codes_hit": ["R101", "R201"], "confidence": 0.7}}"""


def _frame_parts(item: dict) -> list[dict]:
    parts = []
    for i, f in enumerate(item.get("frames") or []):
        p = Path(f)
        if not p.exists():
            continue
        data = p.read_bytes()
        if len(data) > MAX_IMAGE_BYTES:
            continue
        parts.append({"type": "text", "text": f"帧 {p.name}（t≈{i}s）"})
        parts.append({"type": "image_url",
                      "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(data).decode()}})
    return parts


def _post_json(url: str, headers: dict, payload: dict, timeout_s: int) -> tuple[int, str]:
    """POST JSON, return (status, body_text). Uses requests when installed, else urllib."""
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if requests is not None:
        r = requests.post(url, headers=headers, data=raw, timeout=(15, timeout_s))
        return r.status_code, r.text
    req = urllib.request.Request(url, data=raw, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def call_model(prompt: str, item: dict, timeout_s: int = 300) -> tuple[str, dict]:
    """One HTTP call in JSON mode. Returns (raw_text, usage)."""
    content = [{"type": "text", "text": prompt}] + _frame_parts(item)
    body = {"model": MODEL, "messages": [{"role": "user", "content": content}],
            "response_format": {"type": "json_object"},
            "max_tokens": 4000, "temperature": 0.3, "stream": False}
    status, text = _post_json(API_URL, {"Authorization": f"Bearer {API_KEY}",
                                       "Content-Type": "application/json",
                                       "User-Agent": UA}, body, timeout_s)
    if status != 200:
        raise RuntimeError(f"http {status}: {text[:200]}")
    j = json.loads(text)
    out = ((j["choices"][0].get("message") or {}).get("content") or "").strip()
    return out, (j.get("usage") or {})


def validate(rec: dict) -> list[str]:
    """Manual schema validation (no jsonschema dependency). Returns error strings."""
    errs = []
    if not isinstance(rec, dict):
        return ["not a JSON object"]
    extra = set(rec) - {"one_liner", "content_sentiment", "p_codes", "r_codes_hit", "confidence"}
    if extra:
        errs.append(f"extra fields: {sorted(extra)}")
    if not isinstance(rec.get("one_liner"), str) or len(rec["one_liner"].strip()) < 8:
        errs.append("one_liner missing/too short")
    cs = rec.get("content_sentiment")
    if not isinstance(cs, dict):
        errs.append("content_sentiment missing")
    else:
        if cs.get("label") not in STANCE:
            errs.append(f"content_sentiment.label invalid: {cs.get('label')!r}")
        if not isinstance(cs.get("intensity"), int) or not (1 <= cs["intensity"] <= 4):
            errs.append("content_sentiment.intensity must be int 1-4")
        if not isinstance(cs.get("evidence"), str) or len(cs["evidence"].strip()) < 4:
            errs.append("content_sentiment.evidence missing/too short")
    p = rec.get("p_codes")
    if not isinstance(p, list):
        errs.append("p_codes must be a list")
    else:
        for x in p:
            if not isinstance(x, dict) or "id" not in x or "evidence" not in x:
                errs.append(f"p_codes entry malformed: {x!r}")
                continue
            if x["id"] not in P_IDS:
                errs.append(f"unknown P code {x['id']!r}")
            if not isinstance(x["evidence"], str) or len(x["evidence"].strip()) < 2:
                errs.append(f"p_codes[{x['id']}] needs evidence")
    r = rec.get("r_codes_hit")
    if not isinstance(r, list):
        errs.append("r_codes_hit must be a list")
    else:
        for x in r:
            if not isinstance(x, str) or x not in R_IDS:
                errs.append(f"unknown R code {x!r}")
        if len(set(r)) != len(r):
            errs.append("r_codes_hit has duplicates")
    c = rec.get("confidence")
    if not isinstance(c, (int, float)) or not (0 <= c <= 1):
        errs.append("confidence must be number 0-1")
    return errs


class MockBackend:
    """Deterministic offline model. `script` maps item id -> list of raw responses per attempt."""

    def __init__(self, script: dict | None = None):
        self.script = script or {}

    def __call__(self, item: dict, attempt: int) -> tuple[str, dict]:
        aid = item.get("video_id", "")
        seq = self.script.get(aid) or self.script.get("*") or []
        if seq:
            raw = seq[min(attempt, len(seq) - 1)]
        else:
            raw = json.dumps({
                "one_liner": f"{aid or '样本'} 是一条高光混剪，前三秒即进入战斗并靠连杀播报制造爽感。",
                "content_sentiment": {"label": "positive", "intensity": 3,
                                      "evidence": "f_02 第一滴血、f_06 连续击败播报，整体为高光爽感"},
                "p_codes": [{"id": "P104", "evidence": "0-8s 帧 f_01-f_04 正面交火"}],
                "r_codes_hit": ["R101", "R201", "R452"],
                "confidence": 0.72,
            }, ensure_ascii=False)
        return raw, {"prompt_tokens": 0, "completion_tokens": 0}


def extract(item: dict, mock: bool = False, mock_backend: MockBackend | None = None,
            log: list | None = None, timeout_s: int = 300) -> dict:
    """Extract one item. Returns record; raises ItemError / RuntimeError on failure.

    log: optional list collecting attempt dicts {"attempt","ms","tokens","errors"}.
    """
    prompt = build_prompt(item)          # raises ItemError for bad inputs
    last_text, last_errors = "", []
    for attempt in range(REPAIRS + 1):
        t0 = time.time()
        text = ""
        try:
            if mock:
                text, usage = (mock_backend or MockBackend())(item, attempt)
            else:
                if not API_KEY:
                    raise RuntimeError("OPENCODE_API_KEY is not set")
                full = prompt if attempt == 0 else (
                    prompt + f"\n\n你上一次的输出是：\n{last_text}\n\n它有以下问题：{'；'.join(last_errors)}。"
                             "请只输出修正后的完整 JSON 对象。")
                text, usage = call_model(full, item, timeout_s=timeout_s)
            rec = json.loads(text)
            errs = validate(rec)
            if log is not None:
                log.append({"attempt": attempt, "ms": int((time.time() - t0) * 1000),
                            "tokens": usage.get("total_tokens"), "errors": errs})
            if not errs:
                return rec
            last_text, last_errors = text, errs
        except json.JSONDecodeError as e:
            if log is not None:
                log.append({"attempt": attempt, "ms": int((time.time() - t0) * 1000),
                            "tokens": None, "errors": [f"json decode: {e.msg}"]})
            last_text, last_errors = text, [f"invalid JSON: {e.msg}"]
    raise RuntimeError(f"validation failed after {REPAIRS + 1} attempts: {last_errors}")
