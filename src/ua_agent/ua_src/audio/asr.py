"""本地音频转文本（ASR）——补齐「音频模态」。

为什么要做：版本、玩法、联动 IP、活动名这类信息大量只出现在**口播**里，
画面上根本没有（例如"和平精英 × 某某 IP 联动"，画面可能只有一个皮肤，
联动对象只有解说词里才出现）。只靠画面必然漏标。

实现：faster-whisper（CTranslate2 加速，CPU 可跑），全程本地，零 API 成本。
"""
from __future__ import annotations
import os
import subprocess
import threading
from typing import Optional

_MODEL_LOCK = threading.Lock()
_MODEL = None
_MODEL_SIZE = None


def get_model(model_size: str = "small", device: str = "cpu",
              compute_type: str = "int8"):
    """懒加载 + 全局单例（模型加载慢，不能每条都重新加载）。"""
    global _MODEL, _MODEL_SIZE
    with _MODEL_LOCK:
        if _MODEL is None or _MODEL_SIZE != model_size:
            from faster_whisper import WhisperModel
            _MODEL = WhisperModel(model_size, device=device, compute_type=compute_type)
            _MODEL_SIZE = model_size
    return _MODEL


def extract_audio(video_path: str, audio_path: Optional[str] = None) -> Optional[str]:
    """ffmpeg 从视频提取 16kHz 单声道 wav（Whisper 标准输入）。"""
    if audio_path is None:
        audio_path = os.path.splitext(video_path)[0] + ".wav"
    cmd = ["ffmpeg", "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000",
           "-f", "wav", audio_path]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=180)
        if r.returncode == 0 and os.path.exists(audio_path) \
                and os.path.getsize(audio_path) > 1000:
            return audio_path
    except Exception:
        pass
    return None


def _to_simplified(text: str) -> str:
    """繁转简。

    Whisper 中文常输出繁体（如"應通常都會"），而我们的标签词表是简体
    （"地铁逃生""超体模式"），繁体文本会导致关键词匹配全部失效，必须归一。
    """
    if not text:
        return ""
    try:
        import zhconv
        return zhconv.convert(text, "zh-cn")
    except Exception:
        return text


def transcribe(audio_path: str, language: str = "zh", vad_filter: bool = True,
               model=None) -> dict:
    """转写音频为文本（自动繁转简）。返回 {text, language, segments, ok}。"""
    try:
        m = model or get_model()
        segments, info = m.transcribe(audio_path, language=language,
                                      vad_filter=vad_filter)
        texts, segs = [], []
        for s in segments:
            t = _to_simplified((s.text or "").strip())
            if t:
                texts.append(t)
                segs.append({"start": round(s.start, 2),
                             "end": round(s.end, 2), "text": t})
        return {"text": _to_simplified(" ".join(texts)),
                "language": getattr(info, "language", ""),
                "segments": segs, "ok": True}
    except Exception as e:
        return {"text": "", "language": "", "segments": [], "ok": False,
                "error": str(e)[:200]}


def transcribe_video(video_path: str, keep_audio: bool = False, **kw) -> dict:
    """一步到位：视频 -> 提取音频 -> 转写文本（默认转写完删除临时音频）。"""
    ap = extract_audio(video_path)
    if not ap:
        return {"text": "", "segments": [], "ok": False,
                "error": "提取音频失败（可能无音轨）"}
    r = transcribe(ap, **kw)
    if not keep_audio:
        try:
            os.remove(ap)
        except OSError:
            pass
    return r
