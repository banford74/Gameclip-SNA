"""配置加载：读取 YAML，并展开 ${ENV_VAR} 环境变量。"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

import yaml

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        def _repl(m: re.Match) -> str:
            return os.environ.get(m.group(1), "")
        return _ENV_PATTERN.sub(_repl, value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


@dataclass
class Config:
    raw: dict = field(default_factory=dict)

    def get(self, *keys, default=None):
        """按嵌套键取值，缺失返回 default。default 须以关键字传入。"""
        node = self.raw
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node

    @property
    def vlm(self) -> dict:
        return self.raw.get("vlm", {})

    @property
    def frames(self) -> dict:
        return self.raw.get("frames", {})

    @property
    def keyframe(self) -> dict:
        return self.raw.get("keyframe", {})

    @property
    def comments(self) -> dict:
        return self.raw.get("comments", {})

    @property
    def report(self) -> dict:
        return self.raw.get("report", {})


def load_config(path: str = "config.yaml") -> Config:
    """加载配置文件；找不到则用内置默认值。"""
    if not os.path.exists(path):
        # 回退到项目根目录的样例配置
        fallback = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml.example")
        path = fallback if os.path.exists(fallback) else path
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    raw = _expand_env(raw)
    return Config(raw=raw)
