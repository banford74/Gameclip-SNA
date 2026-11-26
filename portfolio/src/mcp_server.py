# -*- coding: utf-8 -*-
"""Minimal MCP server exposing the labeled clip dataset as tools (real data access).

Run (stdio transport):
    pip install mcp
    python src/mcp_server.py

Wire it into an MCP client (Claude Code / any MCP host) with:
    "command": "python", "args": ["src/mcp_server.py"]

Tools: list_clips / get_clip / codebook_stats, all backed by the repo's
data/clips.csv (2201 rows: 1053 target-set clips + 1148 deprioritized legacy).
"""
from __future__ import annotations

import csv
import json
import os
from collections import Counter
from pathlib import Path

from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[2]          # repo root
CSV = Path(os.environ.get("GAMECLIP_CSV", ROOT / "data" / "clips.csv"))
mcp = FastMCP("gameclip-codebook")


def _rows() -> list[dict]:
    if not CSV.exists():
        raise RuntimeError(f"clips.csv not found at {CSV}; set GAMECLIP_CSV")
    with open(CSV, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _split(s: str) -> list[str]:
    return [x for x in (s or "").replace("、", ";").split(";") if x]


@mcp.tool()
def list_clips(game: str = "", stance: str = "", p_code: str = "", limit: int = 20) -> str:
    """List clips filtered by game / content stance / P-code. Returns compact JSON rows."""
    out = []
    for r in _rows():
        if game and r.get("game") != game:
            continue
        if stance and r.get("content_label") != stance:
            continue
        if p_code and p_code not in _split(r.get("pr_p")):
            continue
        out.append({k: r.get(k) for k in ("clip_id", "game", "format", "content_label",
                                          "pr_p", "pr_r", "pr_conf", "source_url")})
        if len(out) >= max(1, min(limit, 200)):
            break
    return json.dumps({"n": len(out), "rows": out}, ensure_ascii=False)


@mcp.tool()
def get_clip(clip_id: str) -> str:
    """Full record for one clip (P/R codes, stance, confidence, comment VAD, source URL)."""
    for r in _rows():
        if r.get("clip_id") == clip_id:
            return json.dumps(r, ensure_ascii=False)
    return json.dumps({"error": "not found", "clip_id": clip_id}, ensure_ascii=False)


@mcp.tool()
def codebook_stats() -> str:
    """P/R code frequencies over the dataset (what the codebook actually covers)."""
    p, r, stance = Counter(), Counter(), Counter()
    for row in _rows():
        for x in _split(row.get("pr_p")):
            p[x] += 1
        for x in _split(row.get("pr_r")):
            r[x] += 1
        stance[row.get("content_label") or "?"] += 1
    return json.dumps({"p_top": p.most_common(20), "r_top": r.most_common(20),
                       "stance": dict(stance)}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
