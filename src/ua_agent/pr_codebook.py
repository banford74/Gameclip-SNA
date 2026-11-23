# -*- coding: utf-8 -*-
"""
P/R 双层特征体系（UAvideo 创意/情节体系）——本项目主标签体系。

- P 码 15 项（情节层，叙事骨架；可多选；带 R 码表里映射）
- R 码 91 项（视觉特征层：有/无 + 少量枚举/自由项）
- 来源：skill references/feature-system.md（内置快照，仅定义无统计）

与十级标签体系的关系：十级=和平精英版本机械化标签（版本词表+玩法），
P/R=跨游戏的创意/情节体系（本项目主用）；十级的知识蒸馏方法（词表/先验/
共现/投票/置信分层）在这里复用，见 pr_tagger.py。
"""
from __future__ import annotations

P_CODES = {
    "P101": {"name": "社死名场面", "tier": "P0", "meaning": "当众尴尬、翻车社死，共情式尴尬抓人", "r_map": ["R451", "R401"]},
    "P102": {"name": "伏地魔", "tier": "P0", "meaning": "趴草丛苟分、猥琐发育，猥琐与反差幽默", "r_map": ["R252", "R454"]},
    "P103": {"name": "决赛圈", "tier": "P0", "meaning": "决赛圈残局/1v1，胜负悬念拉满", "r_map": ["R102", "R452", "R701"]},
    "P104": {"name": "刚枪对掏", "tier": "P0", "meaning": "正面刚枪对掏，硬碰硬突出枪法爽感", "r_map": ["R201", "R251", "R452"]},
    "P105": {"name": "回忆杀", "tier": "P0", "meaning": "老玩家情怀、经典复刻、情感共鸣", "r_map": ["R453", "R407"]},
    "P106": {"name": "伏击阴人", "tier": "P1", "meaning": "蹲点偷袭、草丛阴人，以静制动", "r_map": ["R252", "R454"]},
    "P107": {"name": "团灭灭队", "tier": "P1", "meaning": "团灭/一穿四高光，秀极限操作", "r_map": ["R201", "R102", "R452"]},
    "P108": {"name": "堵桥", "tier": "P1", "meaning": "桥头架枪拦截，一夫当关爽感", "r_map": ["R253", "R452"]},
    "P109": {"name": "舔包搜刮", "tier": "P1", "meaning": "舔包搜刮物资，收集欲与养成感", "r_map": ["R304", "R308"]},
    "P110": {"name": "攻楼守楼", "tier": "P1", "meaning": "攻楼守楼/房区近战，攻防博弈", "r_map": ["R201", "R253"]},
    "P111": {"name": "空投争夺", "tier": "P1", "meaning": "空投/红装争夺开箱，稀缺感", "r_map": ["R304", "R308"]},
    "P112": {"name": "刺激追逃", "tier": "P1", "meaning": "追杀逃亡追逐战，肾上腺素", "r_map": ["R201", "R605", "R454"]},
    "P113": {"name": "载具追梦", "tier": "P2", "meaning": "载具名场面/翻车追车，极限逃生", "r_map": ["R205", "R254"]},
    "P114": {"name": "变装变身", "tier": "P2", "meaning": "换装变身/人物切换，时装展示与反差", "r_map": ["R302", "R352", "R454"]},
    "P115": {"name": "真人整活", "tier": "P2", "meaning": "真人出镜实拍剧情整活，生活反差笑点", "r_map": ["R103", "R151", "R403"]},
}

# 91 项 R 码：type=主/内容/平台特征；kind=bool(有/无) | enum(已知枚举) | free(自由)
R_CODES = {
    # R1 组（10）
    "R101": {"name": "前3秒进入战斗", "type": "主", "kind": "bool"},
    "R102": {"name": "前3秒高光爆点", "type": "主", "kind": "bool"},
    "R103": {"name": "前3秒真人出镜", "type": "主", "kind": "bool"},
    "R104": {"name": "前3秒大字报", "type": "主", "kind": "enum"},
    "R105": {"name": "开头画面主体", "type": "主", "kind": "enum"},
    "R106": {"name": "口播钩子句式", "type": "主", "kind": "enum"},
    "R151": {"name": "真人出镜开场", "type": "内容", "kind": "bool"},
    "R152": {"name": "界面/录屏开场", "type": "内容", "kind": "bool"},
    "R153": {"name": "图文/梗图开场", "type": "内容", "kind": "bool"},
    "R154": {"name": "攻略/教学直入", "type": "内容", "kind": "bool"},
    # R2 组（10）
    "R201": {"name": "连续击杀镜头组", "type": "主", "kind": "bool"},
    "R202": {"name": "残血反杀", "type": "主", "kind": "bool"},
    "R203": {"name": "逆风翻盘", "type": "主", "kind": "bool"},
    "R204": {"name": "组队协作画面", "type": "主", "kind": "bool"},
    "R205": {"name": "载具画面", "type": "主", "kind": "bool"},
    "R206": {"name": "PVE/Boss战", "type": "主", "kind": "bool"},
    "R251": {"name": "对掏/刚枪流", "type": "内容", "kind": "bool"},
    "R252": {"name": "苟分/潜行流", "type": "内容", "kind": "bool"},
    "R253": {"name": "团队协同流", "type": "内容", "kind": "bool"},
    "R254": {"name": "载具/机动战", "type": "内容", "kind": "bool"},
    # R3 组（14）
    "R301": {"name": "新内容演示", "type": "主", "kind": "bool"},
    "R302": {"name": "时装外观特写", "type": "主", "kind": "bool"},
    "R303": {"name": "官方宠物出镜", "type": "主", "kind": "bool"},
    "R304": {"name": "开箱/物资瞬间", "type": "主", "kind": "bool"},
    "R305": {"name": "周边实体出镜", "type": "主", "kind": "bool"},
    "R306": {"name": "载具外观展示", "type": "主", "kind": "bool"},
    "R307": {"name": "官方吉祥物/IP形象出镜", "type": "主", "kind": "bool"},
    "R308": {"name": "特殊物品/道具展示", "type": "主", "kind": "bool"},
    "R309": {"name": "坐骑与特殊载具", "type": "主", "kind": "bool"},
    "R351": {"name": "地图/模式攻略", "type": "内容", "kind": "bool"},
    "R352": {"name": "外观/时装展示", "type": "内容", "kind": "bool"},
    "R353": {"name": "玩法机制演示", "type": "内容", "kind": "bool"},
    "R354": {"name": "武器/枪械内容", "type": "内容", "kind": "bool"},
    "R355": {"name": "剧情/世界观演绎", "type": "内容", "kind": "bool"},
    # R4 组（15）
    "R401": {"name": "失败/搞笑画面", "type": "主", "kind": "bool"},
    "R402": {"name": "线下活动/演出画面", "type": "主", "kind": "bool"},
    "R403": {"name": "真人出镜占比", "type": "主", "kind": "free"},
    "R404": {"name": "IP形象出镜(网感)", "type": "主", "kind": "bool"},
    "R405": {"name": "聊天体叙事", "type": "主", "kind": "bool"},
    "R406": {"name": "梗图表情包贴片", "type": "主", "kind": "bool"},
    "R407": {"name": "情感文案主线", "type": "主", "kind": "bool"},
    "R408": {"name": "跨设备与屏摄猎奇", "type": "主", "kind": "bool"},
    "R409": {"name": "NPC剧场演绎", "type": "主", "kind": "bool"},
    "R410": {"name": "线下联动实拍", "type": "主", "kind": "bool"},
    "R451": {"name": "社死/搞笑梗", "type": "内容", "kind": "bool"},
    "R452": {"name": "逆风翻盘/爽点", "type": "内容", "kind": "bool"},
    "R453": {"name": "情感/回忆杀", "type": "内容", "kind": "bool"},
    "R454": {"name": "悬念/反差钩子", "type": "内容", "kind": "bool"},
    "R455": {"name": "吐槽/锐评", "type": "内容", "kind": "bool"},
    # R5 组（4）
    "R501": {"name": "福利文案露出", "type": "主", "kind": "bool"},
    "R502": {"name": "福利CTA", "type": "主", "kind": "bool"},
    "R503": {"name": "口令码与共创引导", "type": "主", "kind": "bool"},
    "R504": {"name": "收益可视化钩子", "type": "主", "kind": "bool"},
    # R6 组（12）
    "R601": {"name": "纯游戏实录", "type": "主", "kind": "bool"},
    "R602": {"name": "画面特效包装", "type": "主", "kind": "bool"},
    "R603": {"name": "非引擎渲染占比", "type": "主", "kind": "enum"},
    "R604": {"name": "录屏直出", "type": "主", "kind": "bool"},
    "R605": {"name": "快节奏BGM", "type": "主", "kind": "enum"},
    "R606": {"name": "命中音效强化", "type": "主", "kind": "enum"},
    "R607": {"name": "主体观感缺陷", "type": "平台", "kind": "bool"},
    "R651": {"name": "第一人称视角", "type": "内容", "kind": "bool"},
    "R652": {"name": "多角色剧演", "type": "内容", "kind": "bool"},
    "R653": {"name": "前后对比式", "type": "内容", "kind": "bool"},
    "R654": {"name": "盘点/清单式", "type": "内容", "kind": "bool"},
    "R655": {"name": "问答/教学式", "type": "内容", "kind": "bool"},
    # R7 组（7）
    "R701": {"name": "胜利/撤离结算", "type": "主", "kind": "bool"},
    "R702": {"name": "新版本承接", "type": "主", "kind": "bool"},
    "R703": {"name": "悬念/互动收尾", "type": "主", "kind": "bool"},
    "R751": {"name": "引导收藏/关注", "type": "内容", "kind": "bool"},
    "R752": {"name": "引导搜索/体验", "type": "内容", "kind": "bool"},
    "R753": {"name": "福利/码值收尾", "type": "内容", "kind": "bool"},
    "R754": {"name": "悬念/下集收尾", "type": "内容", "kind": "bool"},
    # R8 组（13）
    "R801": {"name": "总时长", "type": "主", "kind": "free"},
    "R802": {"name": "版式", "type": "主", "kind": "enum"},
    "R803": {"name": "剪辑节奏", "type": "主", "kind": "enum"},
    "R804": {"name": "字幕功能类型", "type": "主", "kind": "enum"},
    "R805": {"name": "画幅填充方式", "type": "主", "kind": "enum"},
    "R806": {"name": "画幅混编构图", "type": "主", "kind": "enum"},
    "R807": {"name": "解说字幕全程", "type": "主", "kind": "bool"},
    "R808": {"name": "画质缺陷", "type": "平台", "kind": "bool"},
    "R809": {"name": "色彩光影缺陷", "type": "平台", "kind": "bool"},
    "R810": {"name": "分屏呈现", "type": "平台", "kind": "bool"},
    "R811": {"name": "简单拼接剪辑", "type": "平台", "kind": "bool"},
    "R812": {"name": "字幕缺陷", "type": "平台", "kind": "bool"},
    "R813": {"name": "文字遮挡", "type": "平台", "kind": "bool"},
    # R9 组（6）
    "R901": {"name": "直播贴片与数据条", "type": "主", "kind": "bool"},
    "R902": {"name": "搬运二创痕迹", "type": "主", "kind": "bool"},
    "R903": {"name": "攻略可视化标注", "type": "主", "kind": "bool"},
    "R904": {"name": "定版卡", "type": "主", "kind": "bool"},
    "R905": {"name": "品牌包装元素", "type": "主", "kind": "bool"},
    "R906": {"name": "直播/数据贴片", "type": "主", "kind": "bool"},
}


def p_list_text() -> str:
    return " | ".join(f"{k} {v['name']}（{v['tier']}）" for k, v in P_CODES.items())


def _load_ext() -> tuple[dict, dict, dict]:
    """加载演化扩展（codebook_loop 启用后生效）：active_p / active_r / mapping_overrides。"""
    from pathlib import Path
    import json
    p = Path(__file__).resolve().parents[2] / "configs" / "pr_codebook_ext.json"
    if not p.exists():
        return {}, {}, {}
    try:
        j = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}, {}, {}
    return j.get("active_p", {}), j.get("active_r", {}), j.get("mapping_overrides", {})


EXT_P, EXT_R, EXT_MAP = _load_ext()
for _k, _v in EXT_P.items():
    P_CODES.setdefault(_k, _v)
for _k, _v in EXT_R.items():
    R_CODES.setdefault(_k, {"name": _v.get("name", ""), "type": _v.get("type", "内容"), "kind": "bool"})
for _pid, _over in EXT_MAP.items():
    if _pid in P_CODES:
        P_CODES[_pid]["r_map"] = _over


def r_list_text() -> str:
    return " | ".join(f"{k} {v['name']}{'/枚举' if v['kind'] == 'enum' else ('/数值' if v['kind'] == 'free' else '')}"
                      for k, v in R_CODES.items())


def normalize_r_value(kind: str, raw) -> str:
    """归一化 R 码值：bool → 有/无；enum/free → 去空白字符串。"""
    if kind == "bool":
        s = str(raw).strip().lower()
        if s in ("有", "是", "true", "yes", "1", "hit"):
            return "有"
        if s in ("无", "否", "false", "no", "0", "miss", ""):
            return "无"
        return "有" if s else "无"
    return str(raw).strip()


def validate_pr(pr: dict) -> dict:
    """校验 P/R 打标结果；返回 {"pr": 清洗后, "errors": [...], "p_missing_support": [...]}"""
    errors = []
    p_out = []
    for item in (pr.get("p_codes") or []):
        if isinstance(item, str):
            pid, ev = item, ""
        else:
            pid, ev = item.get("id", ""), item.get("evidence", "")
        if pid not in P_CODES:
            errors.append(f"未知 P 码 {pid}")
            continue
        p_out.append({"id": pid, "name": P_CODES[pid]["name"], "evidence": ev})
    r_out = {}
    for rid, val in (pr.get("r_codes") or {}).items():
        if rid not in R_CODES:
            errors.append(f"未知 R 码 {rid}")
            continue
        r_out[rid] = normalize_r_value(R_CODES[rid]["kind"], val)
    # 表里一致性提示：P 命中但无任何映射 R 码支撑
    missing = []
    for p in p_out:
        mapped = P_CODES[p["id"]]["r_map"]
        if not any(r_out.get(r) in ("有", "是", "1") or (r_out.get(r) not in (None, "", "无")) for r in mapped):
            missing.append(p["id"])
    return {"pr": {"p_codes": p_out, "r_codes": r_out}, "errors": errors, "p_missing_support": missing}


def rule_p_codes(r_codes: dict) -> list:
    """规则层（B 路）：R 码命中的表里反推 P 码候选（≥2 个映射 R 命中才成立）。"""
    hits = {k for k, v in r_codes.items() if v not in (None, "", "无")}
    cands = []
    for pid, meta in P_CODES.items():
        n = sum(1 for r in meta["r_map"] if r in hits)
        if n >= 2:
            cands.append(pid)
    return cands
