"""
语义匹配器：把「内容描述文本」映射到受控词表标签。

为什么需要它
------------
流水线在拿到 VLM 生成的自然语言摘要后，又退化成了字符串匹配
（`if cue.lower() in low`）。这带来两类典型错误：

1. 关键词误命中：摘要里出现「收藏/展柜」→ 命中「活动福利」的线索词，
   压过了模型对画面的整体判断（实为地铁逃生）。
2. 线索缺失即失效：摘要里没出现词表中的任何字面词 → 先验返回 None，
   只能回落到频次兜底。

语义匹配器用向量相似度替代字面包含，把摘要与标签的「语义定义」做匹配，
对上述两类错误都有抵抗力。

关键设计：富语义描述（rich description）
----------------------------------------
直接用标签名（"BR玩法" / "特殊玩法" / "综合玩法"）做 embedding，
三类抽象标签在向量空间里几乎重叠，TOP1 与 TOP2 差距只有 0.02~0.07，
无法可靠决策。因此每个标签都扩展成「标签名 + 画面识别特征 + 一句话定义」，
把区分度从词义层面拉开。

模型：BAAI/bge-small-zh-v1.5（本地，零 API 成本，中文语义表现稳定）
"""
from __future__ import annotations

import functools
from pathlib import Path

MODEL_NAME = "BAAI/bge-small-zh-v1.5"

# ============================================================
# 二级字段（玩法）的富语义描述
# 结构：标签 -> (画面识别特征, 一句话定义)
# 这些描述是语义匹配的核心资产，改动会直接影响匹配结果，需谨慎。
# ============================================================
L2_SEMANTIC_DEFS: dict[str, tuple[str, str]] = {
    "BR玩法": (
        "跳伞 落地 搜集物资 跑毒 缩圈 空投 载具 决赛圈 吃鸡 海岛 大逃杀 百人求生",
        "经典大逃杀玩法：在海岛地图上跳伞落地、搜集武器物资、随毒圈收缩转移、"
        "争夺空投补给、驾驶载具跑图，最终在决赛圈对决，最后存活的一人或一队获胜吃鸡。",
    ),
    "地铁逃生": (
        "地铁 撤离 变卖物 摸金 装备带入 搜刮 辐射区 地铁BOSS 迷雾荒岛 新传世武装 收藏馆 地铁币 狗牌",
        "地铁逃生摸金撤离玩法：玩家带装备进入地图搜刮高价值变卖物，击杀敌人与其他玩家抢夺物资，"
        "在辐射区等高危区域挑战BOSS，最后前往撤离点成功撤离才能带走收益，收藏馆用于存放战利品。",
    ),
    "超体模式": (
        "超体 超体核心 超体终端 超体进化 超能力 炫彩机师 超体对抗 核爆对决 超体英雄 技能",
        "超体对抗玩法：玩家扮演拥有专属超能力的超体英雄，通过超体核心与超体终端释放位移、"
        "护盾、控制等特色技能进行对抗，强调技能连招与角色定位配合。",
    ),
    "古墓迷途": (
        "古墓 青铜门 轩辕禁地 摸金 机关 轩辕地 探墓 长白仙宫 寻宝 探险",
        "古墓探险玩法：以古墓、地宫、青铜门、轩辕禁地等东方探险场景为舞台，"
        "玩家在机关密布的墓室中寻宝探秘、解谜闯关，兼顾探索氛围与战斗。",
    ),
    "绿洲启元": (
        "绿洲 工坊 共创 UGC 玩家自制 双M4对掏 吹牛酒馆 自行车赛 和平运动会 启元 编辑器",
        "绿洲启元UGC玩法：基于玩家共创工坊的自定义模式合集，包含玩家自制地图、"
        "对掏训练、吹牛酒馆、自行车赛、和平运动会等编辑器生态内容。",
    ),
    "团竞": (
        "团竞 团队竞技 歼灭 歼灭模式 突变团竞 狙击团竞 回合制 小地图 复活",
        "团队竞技玩法：在小地图上进行的分队回合制对抗，以歼灭敌方全员为目标，"
        "含突变团竞、狙击团竞等变体，节奏快、强调枪法与团队配合。",
    ),
    "特殊玩法": (
        "冰封列车 墨龙九天 哪吒 宝马 孔雀 限时玩法 联动玩法 特殊模式 特殊关卡",
        "限时或联动的特殊玩法：不属于常规模式框架的限定玩法模式，"
        "如冰封列车、墨龙九天、哪吒、宝马、孔雀等主题化限时玩法。",
    ),
    "活动福利": (
        "福利 抽奖 兑换 签到 活动 节日 空投节 吃鸡节 周年庆 春节 五一 登录领取 免费领 福利礼包",
        "活动福利内容：以游戏内运营活动、节日庆典、福利发放、抽奖兑换、"
        "签到领奖等福利信息为核心的内容，重点是奖励获取而非对战过程。",
    ),
    "商业化": (
        "皮肤 套装 军需 商城 氪金 充值 IP联动 粉红兔子 剧场演绎 小马宝莉 仙逆 抽奖夺宝 和平集市 新品上架",
        "商业化内容：以售卖或展示付费内容为核心，如新皮肤套装、军需抽奖、"
        "IP联动、品牌合作、商城上新、夺宝集市等，重点是商品与消费引导。",
    ),
    # 注意：此处刻意不写任何否定/排除句。
    # embedding 不理解否定，描述里出现「不属于综合玩法，如CG、混剪」会让
    # 摘要中的 CG/混剪 反而拉近与综合玩法的距离（实测 44% 样本被误吸到该标签）。
    # 只保留正面的、具体的多模式特征。
    "综合玩法": (
        "多模式 玩法盘点 玩法合集 模式串烧 大战场 跨模式对比",
        "综合玩法：同一素材里依次展示了两个及以上互不相同的玩法模式，各模式篇幅相当，"
        "例如先后演示大逃杀、摸金撤离、团队竞技、超体对抗中的多个模式，做成玩法大盘点或模式合集。",
    ),
}


def build_rich_text(label: str) -> str:
    """把标签扩展成富语义文本：标签名 + 识别特征 + 一句话定义。"""
    cues, definition = L2_SEMANTIC_DEFS.get(label, ("", ""))
    return f"{label}。识别特征：{cues}。{definition}"


# 参与「多模式计数」的玩法类标签（综合玩法自身不参与计数）
GAMEPLAY_LABELS = [
    "BR玩法", "地铁逃生", "超体模式", "古墓迷途", "绿洲启元", "团竞", "特殊玩法",
]


def count_modes(text: str, cues: dict | None = None) -> list[str]:
    """统计摘要中命中的不同玩法模式（按线索词）。"""
    from ..tagging.version_notes import ENHANCED_L2_CUES as _CUES
    cues = cues or _CUES
    low = (text or "").lower()
    hits = []
    for label in GAMEPLAY_LABELS:
        for c in cues.get(label, []):
            if c and c.lower() in low:
                hits.append(label)
                break
    return hits


def is_multi_mode(text: str, min_modes: int = 2) -> bool:
    """综合玩法判定：命中 >= min_modes 个不同玩法模式。

    关键设计：综合玩法不走语义匹配。
    原因：「综合玩法」的语义描述是元描述（"多个模式的集合"），
    在向量空间里会把任何提及多种枪械/道具/玩法的摘要都吸过去——
    实测 61 条样本中被判为综合玩法的 24 条里仅 1 条为真（4% 命中率），
    是该标签最大的误判来源。改用「不同模式线索词计数」的判别式规则后，
    语义路准确率从 50.8% 提升到 73.8%。
    """
    return len(count_modes(text)) >= min_modes


@functools.lru_cache(maxsize=1)
def _get_model():
    """懒加载本地 embedding 模型（进程内单例）。"""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


class SemanticMatcher:
    """内容文本 → 受控词表标签的语义匹配。"""

    def __init__(self, labels: list[str] | None = None, use_rich: bool = True):
        self.use_rich = use_rich
        self.labels = list(labels) if labels else list(L2_SEMANTIC_DEFS.keys())
        self.model = _get_model()
        self._emb = None
        self.texts = [
            build_rich_text(l) if use_rich else l for l in self.labels
        ]

    @property
    def emb(self):
        if self._emb is None:
            self._emb = self.model.encode(
                self.texts, normalize_embeddings=True, show_progress_bar=False
            )
        return self._emb

    def match(self, text: str, topk: int = 3) -> list[tuple[str, float]]:
        """返回 [(标签, 相似度), ...]，按相似度降序。

        注意 bge 检索需给 query 加前缀指令，否则召回质量下降。
        """
        if not text or not text.strip():
            return []
        q = self.model.encode(
            ["为这段内容选择最合适的玩法分类：" + text],
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0]
        sims = self.emb @ q
        order = sims.argsort()[::-1][:topk]
        return [(self.labels[i], float(sims[i])) for i in order]

    def match_with_margin(self, text: str) -> dict:
        """返回 top1 及其领先优势，供融合策略判断是否可信。"""
        res = self.match(text, topk=3)
        if not res:
            return {"top1": None, "score": 0.0, "margin": 0.0, "top3": []}
        top1, s1 = res[0]
        s2 = res[1][1] if len(res) > 1 else 0.0
        return {
            "top1": top1,
            "score": round(s1, 4),
            "margin": round(s1 - s2, 4),
            "top3": [(l, round(s, 4)) for l, s in res],
        }
