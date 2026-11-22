"""多模态大模型客户端（目标3 底座）。

统一 OpenAI 兼容接口，可对接：
  - OpenAI:        base_url=https://api.openai.com/v1,  model=gpt-4o
  - 通义千问 VL:   base_url=https://dashscope.aliyuncs.com/compatible-mode/v1, model=qwen-vl-max
  - 智谱 GLM-4V:   base_url=https://open.bigmodel.cn/api/paas/v4, model=glm-4v
  - DeepSeek:     base_url=https://api.deepseek.com/v1, model=deepseek-vl / 自定义视觉模型
  - 腾讯云 MaaS:   base_url=https://tokenhub.tencentmaas.com/v1, model=deepseek/deepseek-v4-flash-vision-exp
      该网关同时支持 /chat/completions 与 /responses 两种接口；reasoning 型视觉模型
      建议用 api_style="responses"（用 instructions 传系统提示，最终答案落在 output_text）。
未配置 api_key 时自动降级为 MockVLM，便于离线自测整条链路。
"""
from __future__ import annotations

import base64
import json
import os
import time
from typing import List, Optional

import requests


class MockVLM:
    """离线占位实现：不调用任何 API，返回结构化占位结果，保证 pipeline 可端到端跑通。"""

    def chat(self, system: str, user_text: str, image_paths: List[str]) -> str:
        n = len(image_paths)
        return json.dumps({
            "mock": True,
            "note": "未配置 VLM_API_KEY，返回占位结果；配置后即为真实多模态识别。",
            "image_count": n,
            "on_screen_text": ["（示例）官方活动主视觉", "（示例）限时优惠 5 折"],
            "brand": "示例品牌",
            "subject": "产品宣传画面",
            "scene": "室内/演播室",
            "people": "主播 1 人",
            "key_points": ["主推新品", "强调性价比"],
            "has_subtitle": True,
            "summary": f"该帧为第 {n} 张关键帧示例，疑似官方营销物料。",
        }, ensure_ascii=False)


class VLMClient:
    def __init__(
        self,
        provider: str = "openai",
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "gpt-4o",
        max_tokens: int = 1500,
        temperature: float = 0.2,
        timeout: int = 60,
        api_style: str = "chat",
    ):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.api_style = api_style  # "chat" | "responses"
        self.mock = not api_key
        if self.mock:
            self._mock = MockVLM()

    @staticmethod
    def from_config(cfg: dict) -> "VLMClient":
        # 各 provider 默认 base_url，未显式配置时按 provider 回落
        _DEFAULT_BASE = {
            "openai": "https://api.openai.com/v1",
            "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "glm": "https://open.bigmodel.cn/api/paas/v4",
            "deepseek": "https://api.deepseek.com/v1",
        }
        provider = cfg.get("provider", "openai")
        api_style = cfg.get("api_style") or ("responses" if provider == "deepseek" else "chat")
        return VLMClient(
            provider=provider,
            base_url=cfg.get("base_url") or _DEFAULT_BASE.get(provider, "https://api.openai.com/v1"),
            api_key=cfg.get("api_key", "") or os.environ.get("VLM_API_KEY", "")
                    or os.environ.get("DEEPSEEK_API_KEY", ""),
            model=cfg.get("model", "gpt-4o"),
            max_tokens=cfg.get("max_tokens", 1500),
            temperature=cfg.get("temperature", 0.2),
            timeout=cfg.get("timeout", 60),
            api_style=api_style,
        )

    @staticmethod
    def _encode_image(path: str) -> str:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _build_messages(self, system: str, user_text: str, image_paths: List[str]):
        content = [{"type": "text", "text": user_text}]
        for p in image_paths:
            b64 = self._encode_image(p)
            ext = os.path.splitext(p)[1].lower().lstrip(".")
            mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "jpeg")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/{mime};base64,{b64}"},
            })
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ]

    def chat(self, system: str, user_text: str, image_paths: Optional[List[str]] = None,
             retries: int = 2) -> str:
        image_paths = image_paths or []
        if self.mock:
            return self._mock.chat(system, user_text, image_paths)
        if self.api_style == "responses":
            return self._chat_responses(system, user_text, image_paths, retries)
        return self._chat_chat(system, user_text, image_paths, retries)

    def _chat_chat(self, system: str, user_text: str, image_paths: List[str],
                   retries: int = 2) -> str:
        messages = self._build_messages(system, user_text, image_paths)
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        last_err = None
        for attempt in range(retries + 1):
            try:
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}",
                             "Content-Type": "application/json"},
                    json=payload, timeout=self.timeout,
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt < retries:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"VLM 调用失败: {last_err}")

    def _chat_responses(self, system: str, user_text: str, image_paths: List[str],
                        retries: int = 2) -> str:
        """OpenAI Responses API（instructions 传系统提示，支持 input_image 多模态）。"""
        content: list = [{"type": "input_text", "text": user_text}]
        for p in image_paths:
            b64 = self._encode_image(p)
            ext = os.path.splitext(p)[1].lower().lstrip(".")
            mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "jpeg")
            content.append({
                "type": "input_image",
                "image_url": f"data:image/{mime};base64,{b64}",
            })
        payload = {
            "model": self.model,
            "instructions": system,
            "input": [{"role": "user", "content": content}],
            "stream": False,
            "max_output_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        last_err = None
        for attempt in range(retries + 1):
            try:
                resp = requests.post(
                    f"{self.base_url}/responses",
                    headers={"Authorization": f"Bearer {self.api_key}",
                             "Content-Type": "application/json"},
                    json=payload, timeout=self.timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                return _extract_output_text(data) or json.dumps(data, ensure_ascii=False)[:500]
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt < retries:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"VLM(responses) 调用失败: {last_err}")


def _extract_output_text(data: dict) -> str:
    """从 Responses API 多种返回结构中稳健提取最终文本。

    兼容：顶层 output_text / output[].content[].output_text / output[].content 字符串 /
    任意结构里最长的非推理 text 字段（兜底，避免多图输入时结构偏移导致拿到原始 JSON）。
    注意：GLM 等模型返回带 reasoning 段（reasoning_text 常比最终答案更长），必须跳过，
          否则会错抓推理文本而非最终 JSON 答案。
    """
    if not isinstance(data, dict):
        return ""
    # 1) 顶层便捷字段
    if isinstance(data.get("output_text"), str) and data["output_text"].strip():
        return data["output_text"].strip()
    # 2) output 列表：优先取 message 段的 output_text（最终答案）
    for it in data.get("output", []) or []:
        if not isinstance(it, dict):
            continue
        if it.get("type") == "message":
            content = it.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(content, list):
                for c in content:
                    if (isinstance(c, dict) and c.get("type") == "output_text"
                            and isinstance(c.get("text"), str) and c["text"].strip()):
                        return c["text"].strip()
    # 3) 递归兜底：抓取任意最长字符串 text 字段（跳过 reasoning 段）
    def _walk(node, collector):
        if isinstance(node, dict):
            if node.get("type") == "reasoning":
                return  # 推理段不作为答案候选
            for k, v in node.items():
                if k in ("text", "output_text") and isinstance(v, str) and len(v) > 20:
                    collector.append(v)
                else:
                    _walk(v, collector)
        elif isinstance(node, list):
            for x in node:
                _walk(x, collector)
    coll = []
    _walk(data, coll)
    if coll:
        return max(coll, key=len).strip()
    return ""
