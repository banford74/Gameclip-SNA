# -*- coding: utf-8 -*-
"""
P/R 码表演化循环（RL / bootstrapp 路线）。

奖励（reward）= 码表与人工/LLM 真值的一致性（P/R 命中 F1、映射支撑度、置信校准）
策略（policy）= 码表（新增/拆分/收窄）+ P↔R 映射规则 + 阈值
迭代：harvest（统计残差）→ propose（候选新码/映射修正）→ review（人工或 LLM 裁决）
     → activate（写入 pr_codebook_ext.json）→ 重跑分析 → 回到 harvest。

用法：
  python -m pipeline.codebook_loop harvest [--results DIR ...] [--out data/codebook_loop]
  python -m pipeline.codebook_loop propose
  python -m pipeline.codebook_loop activate --codes P116,R901   # 审核通过后启用
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOOP_DIR = ROOT / "data" / "codebook_loop"
EXT = ROOT / "configs" / "pr_codebook_ext.json"

P_PROPOSALS = {
    "P116": {"name": "音乐/舞蹈演绎", "tier": "P2", "meaning": "以 BGM/舞蹈/卡点表演为核心的素材（非战斗、非剧情）",
             "r_map": ["R605", "R606"], "why": "音乐/舞蹈形式在 8 游戏语料中缺失 P 码（原体系是买量战斗向）"},
    "P117": {"name": "攻略教学/清单", "tier": "P1", "meaning": "以步骤讲解、清单盘点、教学演示为核心的素材",
             "r_map": ["R154", "R351", "R655", "R903"], "why": "攻略/教学类占比高（752/2031），但无对应情节码"},
    "P118": {"name": "日常 Vlog/生活化", "tier": "P2", "meaning": "生活化记录、日常碎片、开黑日常，弱剧情",
             "r_map": ["R151", "R403", "R407"], "why": "真人出镜/日常类内容无 P 码可挂"},
    "P119": {"name": "开箱/抽卡展示", "tier": "P1", "meaning": "开箱、抽卡、爆装、收益展示（收集/赌性驱动）",
             "r_map": ["R304", "R308", "R504"], "why": "开箱类在二次元/派对游戏高频，现只能勉强挂 P109/P111"},
    "P120": {"name": "联动/活动预告", "tier": "P1", "meaning": "IP 联动、版本活动、福利预告（营销信息型）",
             "r_map": ["R501", "R502", "R702", "R904"], "why": "联动/活动类无独立情节码，常误挂 P114"},
}

R_PROPOSALS = {
    "R914": {"name": "舞蹈动作展示", "type": "内容", "why": "音乐/舞蹈类需要动作级证据（现 R6 组无舞蹈维度）"},
    "R915": {"name": "卡点/节奏剪辑", "type": "内容", "why": "卡点节奏是音乐类核心特征，现有 R803 剪辑节奏不含卡点语义"},
    "R916": {"name": "步骤/清单标注", "type": "内容", "why": "攻略教学类需要步骤标注证据（R903 只覆盖地图攻略）"},
    "R917": {"name": "抽卡/爆装瞬间", "type": "平台", "why": "开箱抽卡需要概率/爆装高光证据，R304 只覆盖物资拾取"},
}


def _iter_results(dirs):
    for d in dirs:
        for f in Path(d).rglob("*.json"):
            if f.name.endswith(("_summary.json", ".meta.json")):
                continue
            try:
                j = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(j, dict):
                continue
            parsed = j.get("parsed")
            if not isinstance(parsed, dict):
                continue
            yield {"file": str(f), "game": j.get("game", ""), "form": j.get("form", ""),
                   "source": j.get("aweme_id") or j.get("video") or f.stem, "parsed": parsed}


def harvest(dirs, out=LOOP_DIR) -> dict:
    items = list(_iter_results(dirs))
    p_freq, r_freq = Counter(), Counter()
    cooc = defaultdict(Counter)          # p -> r counts
    uncovered, weak = [], []
    for it in items:
        p = [x["id"] if isinstance(x, dict) else x for x in (it["parsed"].get("p_codes") or [])]
        r_raw = it["parsed"].get("r_codes_hit") or it["parsed"].get("r_codes") or []
        if isinstance(r_raw, dict):
            r = [k for k, v in r_raw.items() if v not in (None, "", "无")]
        else:
            r = [x["id"] if isinstance(x, dict) else x for x in r_raw]
        for pid in p:
            p_freq[pid] += 1
            for rid in r:
                cooc[pid][rid] += 1
        for rid in r:
            r_freq[rid] += 1
        if not p:
            uncovered.append(it)
        elif float(it["parsed"].get("confidence") or 0) < 0.6:
            weak.append(it)
    mapping = {}
    for pid, rs in cooc.items():
        tot = p_freq[pid]
        mapping[pid] = {rid: round(c / tot, 3) for rid, c in rs.most_common(8)}
    out.mkdir(parents=True, exist_ok=True)
    report = {
        "n_items": len(items),
        "p_freq": dict(p_freq.most_common()),
        "r_freq": dict(r_freq.most_common(40)),
        "mapping_support": mapping,
        "uncovered": [{"source": u["source"], "game": u["game"], "form": u["form"],
                       "one_liner": (u["parsed"].get("one_liner") or "")[:100]} for u in uncovered][:50],
        "n_uncovered": len(uncovered), "n_weak_confidence": len(weak),
    }
    (out / "harvest.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


def propose(harvest_report: dict | None = None) -> dict:
    harvest_report = harvest_report or json.loads((LOOP_DIR / "harvest.json").read_text(encoding="utf-8"))
    # 新码候选：未被覆盖的素材按形式聚类（音乐舞蹈/攻略/日常/开箱/联动）
    forms = Counter()
    for u in harvest_report.get("uncovered", []):
        forms[u.get("form") or "未标注"] += 1
    proposals = {
        "p_new": P_PROPOSALS,
        "r_new": R_PROPOSALS,
        "form_gap": dict(forms),
        "evidence": {
            "n_uncovered": harvest_report.get("n_uncovered", 0),
            "note": "P116-P120 / R914-R917 依据形式缺口与未覆盖样本提出；启用前需人工/LLM 裁决（activate）。",
        },
    }
    (LOOP_DIR / "proposals.json").write_text(json.dumps(proposals, ensure_ascii=False, indent=1), encoding="utf-8")
    return proposals


def load_ext() -> dict:
    if EXT.exists():
        return json.loads(EXT.read_text(encoding="utf-8"))
    return {"active_p": {}, "active_r": {}, "mapping_overrides": {}, "history": []}


def activate(codes: list[str]) -> dict:
    ext = load_ext()
    for c in codes:
        c = c.strip()
        if c in P_PROPOSALS:
            ext["active_p"][c] = P_PROPOSALS[c]
        elif c in R_PROPOSALS:
            ext["active_r"][c] = R_PROPOSALS[c]
        else:
            raise KeyError(f"未知候选码 {c}")
    ext.setdefault("history", []).append({"action": "activate", "codes": codes})
    EXT.parent.mkdir(parents=True, exist_ok=True)
    EXT.write_text(json.dumps(ext, ensure_ascii=False, indent=1), encoding="utf-8")
    return ext


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "harvest"
    dirs = [str(ROOT / "skilltest" / "results"), str(ROOT / "skilltest" / "results_batch")]
    if cmd == "harvest":
        rep = harvest(dirs)
        print(json.dumps({"n_items": rep["n_items"], "n_uncovered": rep["n_uncovered"],
                          "p_freq": rep["p_freq"], "form_gap": dict(Counter(u["form"] for u in rep["uncovered"]))},
                         ensure_ascii=False, indent=1))
    elif cmd == "propose":
        print(json.dumps(propose(), ensure_ascii=False, indent=1)[:1200])
    elif cmd == "activate":
        print(json.dumps(activate(argv[2].split(",")), ensure_ascii=False, indent=1)[:600])
    else:
        print(__doc__)


if __name__ == "__main__":
    import sys
    main(sys.argv)
