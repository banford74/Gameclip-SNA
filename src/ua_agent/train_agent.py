# -*- coding: utf-8 -*-
"""
「训练 agent」= 构建/更新 agent 的知识库（知识蒸馏，无需 GPU）。

两档：
  1) --bootstrap           从 version_notes 富知识构建默认词表（无 RL 库即可用）
  2) --from-xlsx <path>    从强化学习库 xlsx 学习：版本词表 / 少样本标杆 / 关键词先验 /
                           共现先验 / 值频次 / L5→L2 反推（这是用户训练资产的核心）
可选：
  --eval <json>            在人工标注集上评估（逐级准确率 + 整体一致率，需 VLM 凭据）

产物 knowledge.json 即 agent 的「已训练」状态，agent.py 启动时自动加载。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .knowledge import (LEVEL_KEYS, GENERIC_VERSION, DEFAULT_KNOWLEDGE_PATH,
                        bootstrap_vocab, load_knowledge, vocab_for)
from .ua_src.config import load_config
from .ua_src.vision.vlm_client import VLMClient
from .ua_src.tagging import version_notes as vn
from .ua_src.tagging.tagger import Tagger


def build_bootstrap(version: str = GENERIC_VERSION) -> dict:
    versions = list(vn.LEVEL_HIERARCHY.get("一级字段", {}).keys()) or [GENERIC_VERSION]
    return {
        "source": "bootstrap-version_notes",
        "version": version,
        "vocab": bootstrap_vocab(version),
        "vocab_by_version": {v: bootstrap_vocab(v) for v in versions},
        "fewshot": [], "keyword_prior": [], "cooccur": {}, "value_freq": {}, "l5_to_l2": {},
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_samples": 0,
    }


def build_from_xlsx(xlsx_path: str) -> dict:
    from .ua_src.tagging.learned_tagger import LearnedTagger
    tagger = LearnedTagger.from_library(xlsx_path)
    k = tagger.k
    n_rows = None
    try:
        import openpyxl
        wb = openpyxl.load_workbook(xlsx_path, data_only=True)
        n_rows = max(0, wb["Sheet1"].max_row - 1)
    except Exception:
        pass
    return {
        "source": "rl-library-xlsx",
        "source_file": str(xlsx_path),
        "version": GENERIC_VERSION,
        "vocab": k.vocab_by_version.get(GENERIC_VERSION) or bootstrap_vocab(),
        "vocab_by_version": {v: {lv: sorted(set(vals)) for lv, vals in voc.items()}
                             for v, voc in k.vocab_by_version.items()},
        "fewshot": k.fewshot,
        "keyword_prior": k.keyword_prior,
        "cooccur": k.cooccur,
        "value_freq": k.value_freq,
        "l5_to_l2": k.l5_to_l2,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_samples": n_rows,
    }


def eval_on_labels(knowledge: dict, labels_path: str, config_path: str | None = None) -> dict:
    """人工标注集评估：逐级准确率 + 整体全对率。样例格式：
    [{"content_text": "...", "version": "通用版本", "labels": {"二级字段": "BR玩法", ...}}, ...]
    """
    cfg = load_config(str(config_path or (Path(__file__).resolve().parent / "config.yaml")))
    vlm = VLMClient.from_config(cfg.vlm)
    tagger = Tagger(vlm)
    samples = json.loads(Path(labels_path).read_text(encoding="utf-8"))
    per_level = {lv: [0, 0] for lv in LEVEL_KEYS}
    exact = 0
    for s in samples:
        vocab = vocab_for(knowledge, s.get("version", GENERIC_VERSION))
        pred = tagger.tag(s["content_text"], vocab)
        gold = s.get("labels", {})
        all_ok = True
        for lv in LEVEL_KEYS:
            if lv in gold:
                ok = (pred.get(lv, "") == gold[lv])
                per_level[lv][1] += 1
                per_level[lv][0] += int(ok)
                if not ok:
                    all_ok = False
        exact += int(all_ok)
    table = {lv: (round(n_ok / n, 4) if n else None) for lv, (n_ok, n) in per_level.items()}
    return {"n": len(samples), "per_level_accuracy": table,
            "exact_match": round(exact / max(len(samples), 1), 4)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="训练 UA ClipAgent 的知识库")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--bootstrap", action="store_true", help="从 version_notes 构建默认知识")
    src.add_argument("--from-xlsx", help="强化学习库 xlsx 路径（v2_rl_library.xlsx）")
    ap.add_argument("--out", default=str(DEFAULT_KNOWLEDGE_PATH))
    ap.add_argument("--version", default=GENERIC_VERSION)
    ap.add_argument("--eval", help="人工标注集 json（评估用，需 VLM 凭据）")
    args = ap.parse_args(argv)

    if args.bootstrap:
        k = build_bootstrap(args.version)
    else:
        k = build_from_xlsx(args.from_xlsx)
    out = Path(args.out)
    out.write_text(json.dumps(k, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[train] 知识库已写：{out}（来源={k['source']}，样本={k.get('n_samples')}）")
    print(f"[train] 词表规模：" + ", ".join(f"{lv}={len(v)}" for lv, v in k["vocab"].items() if v))
    if args.eval:
        res = eval_on_labels(k, args.eval)
        print(json.dumps(res, ensure_ascii=False, indent=1))
        (out.parent / "eval_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
