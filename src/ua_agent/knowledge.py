# -*- coding: utf-8 -*-
"""
知识库：十级标签的版本词表 + 确定性规则。

两个来源：
1) bootstrap —— 直接从 version_notes.py 的富知识（LEVEL_HIERARCHY / L4_TO_L3 /
   L5_CATEGORY_MAP / L9_PROVENANCE_RULES）构建，无需 RL 库文件，开箱可用；
2) train_agent.py --from-xlsx —— 从「强化学习库」xlsx 学习版本词表/少样本/关键词先验/
   共现先验（唯一需要的增量是用户那份 v2_rl_library.xlsx），产物存 knowledge.json。
"""
from __future__ import annotations

import json
from pathlib import Path

from .ua_src.tagging import version_notes as vn

LEVEL_KEYS = ["一级字段", "二级字段", "三级字段", "四级字段", "五级字段",
              "六级字段", "七级字段", "八级字段", "九级字段", "十级字段"]
GENERIC_VERSION = "通用版本"
DEFAULT_KNOWLEDGE_PATH = Path(__file__).resolve().parent / "knowledge.json"

# 《优化后标签体系_四五六级》权威词表（v3 标准化修订版；优先级高于 version_notes 的历史值）
OPTIMIZED_L4 = [
    "攻略解说", "玩家游戏梗", "网络流行梗", "热血燃向", "搭子故事", "剧场演绎",
    "刚枪手感", "音乐舞蹈", "怀旧情怀", "游戏角色", "竞技成就", "联动IP", "社交认同",
    "画质展示", "错过血亏", "群像", "策划割肉", "操控体验", "热点借势", "量级对比",
]
OPTIMIZED_L5 = [
    "电玩嘉年华主题海岛", "和平七周年", "51综合福利",
    "97MG轻机枪", "新武器", "动力装甲",
    "新地图轩辕禁地", "火山地图更新", "地图",
    "时装", "小黄衣套装",
    "HIT1.7安全系统", "3D收藏馆", "PC模拟器优化",
    "鹅仔载具宠物", "宠物猫变卖物", "仓库鹅", "企鹅沙发", "变卖物", "鹅仔游戏厅",
    "小马宝莉", "仙逆联动套装", "粉红兔子",
    "超体角色", "超体进化度假岛", "老六玩法",
    "青铜门探险", "摸金",
    "地铁7周年大金", "地铁BOSS",
    "歼灭模式度假岛",
    "新道具", "海岛冰茶", "叮咚鸡动作", "舞蹈动作", "战斗体验优化",
    "刺激刚枪", "综合卖点",
]


def bootstrap_vocab(version: str = GENERIC_VERSION) -> dict:
    """从 version_notes 构建受控词表；四/五级用优化后权威词表；六级是自由文本。"""
    lh = vn.LEVEL_HIERARCHY
    return {
        "一级字段": list(lh.get("一级字段", {}).keys()) or [version],
        "二级字段": list(lh.get("二级字段", {}).keys()),
        "三级字段": list(lh.get("三级字段", {}).keys()),
        "四级字段": OPTIMIZED_L4,
        "五级字段": OPTIMIZED_L5,
        "六级字段": [],                       # 自由文本，不参与约束
        "七级字段": list(lh.get("七级字段", {}).keys()),
        "八级字段": list(lh.get("八级字段", {}).keys()),
        "九级字段": list(lh.get("九级字段", {}).keys()),
        "十级字段": list(lh.get("十级字段", {}).keys()),
    }


def load_knowledge(path: str | Path | None = None) -> dict:
    """加载训练产物 knowledge.json；没有则返回 bootstrap 版本。"""
    p = Path(path) if path else DEFAULT_KNOWLEDGE_PATH
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"version": GENERIC_VERSION, "vocab": bootstrap_vocab(), "source": "bootstrap",
            "fewshot": [], "keyword_prior": [], "cooccur": {}, "meta": {}}


def vocab_for(knowledge: dict, version: str) -> dict:
    vocabs = knowledge.get("vocab_by_version") or {}
    if version in vocabs:
        return vocabs[version]
    if GENERIC_VERSION in vocabs:
        return vocabs[GENERIC_VERSION]
    return knowledge.get("vocab") or bootstrap_vocab()


def l9_from_l7(l7: str) -> str:
    """九级（AI/非AI）走 provenance 规则，画面不猜。
    version_notes 只覆盖部分七级值；其余已知七级（内录/混剪/素人/KOL/明星代言/图片）
    按人工制作口径一律「非AI」，未知才留空。"""
    if not l7:
        return ""
    rule = vn.L9_PROVENANCE_RULES.get(l7)
    if rule:
        return rule
    known_l7 = set(vn.LEVEL_HIERARCHY.get("七级字段", {}).keys())
    return "非AI" if l7 in known_l7 else ""


def l10_from_size(width: int, height: int) -> str:
    return "横" if (width or 0) >= (height or 0) else "竖"


def l8_from_account(account: str = "") -> str:
    """八级（产出方）走账号/文件名 token，画面不猜。"""
    for tok in vn.LEVEL_HIERARCHY.get("八级字段", {}).keys():
        if tok and account and tok in account:
            return tok
    return ""


if __name__ == "__main__":
    k = load_knowledge()
    print(json.dumps({"source": k["source"], "version": k["version"],
                      "n_vocab": {lv: len(v) for lv, v in k["vocab"].items()}},
                     ensure_ascii=False, indent=1))
