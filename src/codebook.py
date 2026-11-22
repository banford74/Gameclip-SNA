# -*- coding: utf-8 -*-
"""
码表注册与扩容队列（proposal 的 active continued-learning loop）。
- P 码 15 个（P101..P115）、R 码 91 个（R1xx..R8xx）
- 首轮实测发现的缺口在此登记：P104/P114 在"测评类"素材上的越界误报 → 需要新增"测评/锐评"分支码
- 扩容来源 = 标注员分歧 + B6 残差（falsify.py 输出的 failure traces）
"""
import json
from pathlib import Path

CODEBOOK_PATH = Path(__file__).resolve().parent / "codebook.json"

# 种子码表（可执行版只列已确证的 P 码语义；R 码从 skill 码表 JSON 导入）
P_SEED = {
    "P101": "社死/出糗名场面",
    "P102": "极限操作/高光",
    "P103": "剧情反转",
    "P104": "氪金/付费展示",       # 注意：本轮 v2 误报高发码，扩容时收窄语义或拆分
    "P105": "回忆杀/情怀杀",
    "P114": "变装/变身",
    "P115": "观赛/反应类",         # gemini 在 v1 幻觉出的码 → 语义需要人工裁决
}

# 已知问题码（来自 2026-11-16 十平台实测残差，进扩容裁决队列）
KNOWN_ISSUES = [
    {"code": "P114", "issue": "测评类素材越界误报（deepseek/qwen-opus/fable/glm-flash 双平台复现）",
     "action": "拆分 P114→变装(P114a) / 武器形态切换(P114b)，或新增 R 码'形态切换展示'承接"},
    {"code": "P104", "issue": "flashx/gemini 在纯测评上误报（无付费展示画面）",
     "action": "收窄定义：必须有 UI 价格/通行证画面才算"},
    {"code": "P101", "issue": "校内 qwen/glm-flash 漏报（v1 出糗场面召回 0）",
     "action": "补负样本对：吃撑瘫桌 vs 普通进食"},
    {"code": "NEW", "issue": "测评/锐评/数据拆解类叙事无 P 码可挂（15 码全是买量创意）",
     "action": "新增 P116'测评锐评'、P117'攻略教学'，走扩容裁决后并入"},
]

def load_codebook() -> dict:
    """读 codebook.json（若不存在则由 skill 码表生成骨架）。"""
    if CODEBOOK_PATH.exists():
        return json.loads(CODEBOOK_PATH.read_text(encoding="utf-8"))
    return {"p_codes": P_SEED, "r_codes": {}, "expansion_queue": KNOWN_ISSUES}

def save_codebook(cb: dict) -> None:
    CODEBOOK_PATH.write_text(json.dumps(cb, ensure_ascii=False, indent=2), "utf-8")

def export_for_training(cb: dict, n_p: int, n_r: int) -> dict:
    """训练用索引映射：code_id → 连续 index；扩容新码追加到尾部，旧码 index 永不重排（重要：保 B6 可比性）。"""
    p_ids = sorted(cb["p_codes"].keys()) + [e["code"] for e in cb.get("expansion_queue", []) if e["code"].startswith("P") and e["code"] != "NEW"]
    r_ids = sorted(cb["r_codes"].keys())
    mapping = {}
    for i, c in enumerate(p_ids[:n_p + 8]):   # 预留 8 个扩容位
        mapping[c] = i
    for i, c in enumerate(r_ids[:n_r]):
        mapping[c] = n_p + 8 + i
    return mapping

def adjudicate(queue_item: dict, decision: str, new_def: str = "") -> dict:
    """裁决一条扩容申请：accept（进码表）/ split（拆分记录）/ reject。"""
    queue_item["decision"] = decision
    queue_item["new_def"] = new_def
    return queue_item

if __name__ == "__main__":
    cb = load_codebook()
    print("P 码种子：", list(cb["p_codes"]))
    print("扩容队列：")
    for it in cb.get("expansion_queue", []):
        print("  -", it["code"], "→", it["issue"], "→", it["action"])
