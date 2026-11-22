"""
学习型打标器 v2：基于「强化学习库」+「版本卖点备注」双知识源，
做 few-shot + 受控词表 + 关键词先验 + 语义定义 的四件套约束。

v1 → v2 变更：
- 新增「版本卖点备注」(version_notes.py) 作为辅助知识源，提供：
  1) 完整的层级父子关系（二级玩法→细分卖点、三级形式→子项等）
  2) 增强版 L2_CUES（覆盖 BR玩法/全部玩法的识别线索）
  3) 增强版 CROSS_CUES（跨级先验覆盖三~七级）
  4) 各级详细语义定义（替换原有简化版）
  5) 版本约束（如 CG36 二级仅 BR玩法）

设计要点（针对「超体核心升级 被打成 BR玩法」这类错误）：
1. 版本专属受控词表：CG36 用 CG36 词表，通用版本用全量。
2. 少样本标杆：每个 (版本, 二级字段) 取代表样本。
3. 关键词先验：内容线索 token → 标签的强信号纠偏。
4. 语义定义：各级详细口径说明，对齐人类标注风格。
"""
from __future__ import annotations
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# 导入版本卖点备注（辅助知识源）
from ..tagging.version_notes import (
    ENHANCED_L2_CUES as L2_CUES,
    ENHANCED_CROSS_CUES as CROSS_CUES,
    ENHANCED_LEVEL_SEMANTICS as LEVEL_SEMANTICS,
    LEVEL_HIERARCHY,
    VERSION_LEVEL_CONSTRAINTS,
    NAMING_EXAMPLE,
    ALIAS_NORMALIZE,
    L4_TO_L3,
    EVENT_TOKEN_L2,
    L9_PROVENANCE_RULES,
    L6_FREE_TEXT,
    L5_CATEGORY_MAP,
)

LEVEL_KEYS = [
    "一级字段", "二级字段", "三级字段", "四级字段", "五级字段",
    "六级字段", "七级字段", "八级字段", "九级字段", "十级字段",
]

GENERIC_VERSION = "通用版本"


@dataclass
class LearnedKnowledge:
    vocab_by_version: dict = field(default_factory=dict)
    fewshot: list = field(default_factory=list)
    keyword_prior: list = field(default_factory=list)
    cooccur: dict = field(default_factory=dict)       # level -> {"v1|v2": {value: count}}
    value_freq: dict = field(default_factory=dict)     # level -> {value: count}
    l5_to_l2: dict = field(default_factory=dict)      # L5值 -> 主导L2（数据驱动，确定性反推玩法）
    _token_index: dict = field(default_factory=dict)


class LearnedTagger:
    def __init__(self, knowledge: LearnedKnowledge):
        self.k = knowledge
        for item in self.k.keyword_prior:
            self.k._token_index[item["token"].lower()] = item["l2"]

    # ========== 构建：从强化学习库 xlsx 学习 ==========
    @classmethod
    def from_library(cls, xlsx_path: str) -> "LearnedTagger":
        import openpyxl
        wb = openpyxl.load_workbook(xlsx_path, data_only=True)
        ws = wb["Sheet1"]
        rows = list(ws.iter_rows(values_only=True))
        hdr, data = rows[0], rows[1:]
        levels = list(range(3, 13))
        lnames = list(hdr[3:13])

        byver = defaultdict(list)
        for r in data:
            if r[3]:
                byver[r[3]].append(r)

        # 1) 版本专属词表
        vocab = {}
        for ver, rs in byver.items():
            voc = {}
            for li, name in zip(levels, lnames):
                c = defaultdict(int)
                for r in rs:
                    v = r[li]
                    if v not in (None, ""):
                        c[v] += 1
                voc[name] = sorted(c.keys())
            vocab[ver] = voc
        if GENERIC_VERSION not in vocab:
            allv = defaultdict(set)
            for voc in vocab.values():
                for name, vals in voc.items():
                    allv[name].update(vals)
            vocab[GENERIC_VERSION] = {n: sorted(v) for n, v in allv.items()}

        # 2) 少样本
        few = {}
        for r in data:
            ver, l2 = r[3], r[4]
            if not l2:
                continue
            key = (ver, l2)
            if key not in few:
                few[key] = {
                    "name": re.sub(r"\.mp4$", "", str(r[0])),
                    "labels": {lnames[i - 3]: r[i] for i in levels},
                }
        fewshot = list(few.values())

        # 3) 关键词先验
        token2l2 = defaultdict(lambda: defaultdict(int))
        for r in data:
            l2 = r[4]
            if not l2:
                continue
            toks = set(re.split(r"[-_/\s]+", re.sub(r"\.mp4$", "", str(r[0]))))
            skip = {
                "BR玩法", "通用版本", "内录", "非AI", "AI", "竖", "横",
                "JP", "JP1", "CG36", "CG35", "通用",
            }
            for t in toks:
                if t in skip:
                    continue
                token2l2[t][l2] += 1
        prior = []
        for t, c in token2l2.items():
            total = sum(c.values())
            top, topn = max(c.items(), key=lambda kv: kv[1])
            if total >= 2 and topn == total:
                prior.append({"token": t, "l2": top, "n": total})
        prior.sort(key=lambda x: -x["n"])

        # 4) 层级共现先验：level -> {(一级,二级): {value: count}} + 全局频次
        #    用于「给定版本+玩法，该层级最常见值是什么」的强兜底（五级/六级/八级稀有值密集）。
        cooccur = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        value_freq = defaultdict(lambda: defaultdict(int))
        lnames_idx = {name: i for i, name in zip(LEVEL_KEYS, LEVEL_KEYS)}
        for r in data:
            vals = {}
            for name in LEVEL_KEYS:
                i = 3 + LEVEL_KEYS.index(name)
                v = r[i]
                vals[name] = str(v).strip() if v not in (None, "") else ""
            v1, v2 = vals["一级字段"], vals["二级字段"]
            for name in LEVEL_KEYS[1:]:  # 二级..十级
                v = vals[name]
                value_freq[name][v] += 1
                ctx = (v1,) if name == "二级字段" else (v1, v2)
                cooccur[name][ctx][v] += 1
        # 转为普通 dict 便于序列化与查找
        cooccur_d = {}
        for name, ctxmap in cooccur.items():
            cooccur_d[name] = {}
            for ctx, vmap in ctxmap.items():
                cooccur_d[name]["|".join(ctx)] = dict(vmap)
        value_freq_d = {name: dict(vmap) for name, vmap in value_freq.items()}

        # 5) L5 -> 主导L2 数据驱动映射（确定性反推玩法用）
        #    规则：某 L5 值在 ≥80% 的行里对应同一 L2，则记录该 L2。
        l5_to_l2 = {}
        l5_l2_counts = defaultdict(lambda: defaultdict(int))
        for r in data:
            l5 = r[7]   # 五级字段列索引=7
            l2 = r[4]   # 二级字段列索引=4
            if l5 not in (None, "") and l2 not in (None, ""):
                l5_l2_counts[str(l5).strip()][str(l2).strip()] += 1
        for l5, c in l5_l2_counts.items():
            total = sum(c.values())
            top, topn = max(c.items(), key=lambda kv: kv[1])
            if topn / total >= 0.8:
                l5_to_l2[l5] = top

        return cls(LearnedKnowledge(vocab, fewshot, prior, cooccur_d, value_freq_d, l5_to_l2))

    # ========== 词表约束 ==========
    def candidate_levels(self, version: str) -> dict:
        """返回某版本下每个层级的候选值列表，叠加版本约束。"""
        base = {}
        if version in self.k.vocab_by_version:
            base = self.k.vocab_by_version[version]
        else:
            merged = defaultdict(set)
            for voc in self.k.vocab_by_version.values():
                for name, vals in voc.items():
                    merged[name].update(vals)
            base = {n: sorted(v) for n, v in merged.items()}

        # 叠加版本级别硬约束（如 CG36 二级仅允许 BR玩法）
        if version in VERSION_LEVEL_CONSTRAINTS:
            for lvl, allowed in VERSION_LEVEL_CONSTRAINTS[version].items():
                if allowed:  # 非空列表 = 限制候选
                    base[lvl] = allowed

        return base

    # ========== 关键词先验纠偏（玩法维度）==========
    def prior_l2(self, text: str) -> str | None:
        """用增强版 L2_CUES + 学习库 token 双源检索玩法线索。"""
        if not text:
            return None
        low = text.lower()
        best, best_len = None, 0
        # 1) 版本备注扩充词典（最丰富）
        for label, cues in L2_CUES.items():
            for cue in cues:
                if cue and cue.lower() in low and len(cue) > best_len:
                    best, best_len = label, len(cue)
        # 2) 学习库文件名 token 信号
        for tok, l2 in self.k._token_index.items():
            if tok and tok.lower() in low and len(tok) >= best_len:
                best, best_len = l2, len(tok)
        return best

    # ========== 层级共现兜底（稀有值密集层级）==========
    def cooccur_fill(self, labels: dict, min_ratio: float = 0.5) -> dict:
        """对仍为空的三级..十级，用「(一级,二级) 上下文下最常见值」兜底。

        - 仅当该上下文下某非空前值占比 >= min_ratio 时才填充（避免对稀疏/多空层级乱填）。
        - 上下文查不到时回落到「仅按版本」(一级,*) 再回落到全局频次。
        """
        v1 = labels.get("一级字段", "")
        v2 = labels.get("二级字段", "")
        for name in LEVEL_KEYS[2:]:  # 三级..十级
            if labels.get(name):  # 已有值则不覆盖
                continue
            d = self.k.cooccur.get(name, {}).get(f"{v1}|{v2}", {})
            if not d:
                d = self.k.cooccur.get(name, {}).get(f"{v1}|*", {})
            if not d:
                continue
            total = sum(d.values())
            best, bestc = max(d.items(), key=lambda kv: kv[1])
            if best and bestc / total >= min_ratio:
                labels[name] = best
        return labels

    # ========== 构建系统提示词 ==========
    def build_system(self, version: str) -> str:
        cand = self.candidate_levels(version)
        enum_lines = []
        for name, vals in cand.items():
            if name == "六级字段":
                enum_lines.append("- 六级字段（自由文本「看点」：可填具体情节/标题描述，不限制词表，不计入准确率考核）")
            elif name == "九级字段":
                enum_lines.append("- 九级字段（由素材来源元数据给定，你无需猜测；输出时填「非AI」即可）")
            else:
                enum_lines.append(f"- {name}（候选：{('、'.join(vals) if vals else '（可空）')}）")
        enum_lines = "\n".join(enum_lines)
        sem_lines = "\n".join(f"- {k}：{v}" for k, v in LEVEL_SEMANTICS.items())

        # 五级分类提示（先定大类再定具体值，匹配更稳）
        cat_lines = "\n".join(
            f"  · {cat}：{('、'.join(v for v, c in L5_CATEGORY_MAP.items() if c == cat))}"
            for cat in ["版本活动", "武器载具", "地图场景", "角色时装", "玩法系统",
                        "宠物社交", "IP联动", "超体玩法", "古墓玩法", "地铁玩法", "绿洲玩法",
                        "通用玩法", "战斗主题", "综合"]
        )

        # 从版本备注中提取各层级的子项/展开信息，注入提示词
        hierarchy_lines = self._build_hierarchy_hint(version)

        return (
            "你是和平精英买量视频的标签标注专家。依据给定的「版本专属候选词表」"
            "「标杆样本」「层级语义定义」，为视频内容打十级标签。\n"
            "【必须遵守】\n"
            "1. 除「六级字段(看点)」外，每一级只能从对应层级的「候选」中选取一个值；若该视频确实无对应内容，可填空字符串。\n"
            "2. 严禁自由发挥造词——只能选候选里的值（六级看点除外）。\n"
            "3. 一级字段(版本)已由调用方给定，不要更改。九级字段由来源元数据给定，输出「非AI」即可。\n"
            f"4. 当前版本={version}。通用版本不受限制；CG36 使用 CG36 专属候选。\n\n"
            "【各级候选词表】\n" + enum_lines + "\n\n"
            "【各级语义定义（对齐人类标注口径）】\n" + sem_lines + "\n\n"
            "【五级字段分类（先定大类再选具体值）】\n" + cat_lines + "\n\n"
            "【层级展开关系（来自版本卖点备注）】\n" + hierarchy_lines + "\n"
            "【命名规范示例】" + NAMING_EXAMPLE + "\n"
        )

    def _build_hierarchy_hint(self, version: str) -> str:
        """从 LEVEL_HIERARCHY 提取与当前版本相关的层级展开信息。"""
        lines = []
        for lvl_name in ["二级字段", "三级字段", "四级字段"]:
            if lvl_name not in LEVEL_HIERARCHY:
                continue
            items = LEVEL_HIERARCHY[lvl_name]
            # 只展示在当前版本候选范围内的项
            cand = self.candidate_levels(version).get(lvl_name, [])
            matched = [k for k in items if k in cand]
            if not matched:
                continue
            detail_parts = []
            for k in matched[:15]:  # 最多展示15个避免过长
                info = items[k]
                subs = info.get("_sub_items", [])
                desc = info.get("_desc", "")
                sub_str = f"（子项：{' / '.join(subs)}）" if subs else ""
                desc_str = f"——{desc}" if desc else ""
                detail_parts.append(f"  · {k}{sub_str}{desc_str}")
            lines.append(f"{lvl_name}：\n" + "\n".join(detail_parts))
        return "\n".join(lines) if lines else "（无额外展开信息）"

    # ========== 构建用户提示词 ==========
    def build_user(self, version: str, content_text: str) -> str:
        # 少样本标杆
        fs = [f for f in self.k.fewshot if f["labels"].get("一级字段") == version]
        if len(fs) < 4:
            fs += [f for f in self.k.fewshot if f not in fs]
        fs = fs[:8]
        ex_lines = []
        for f in fs:
            lab = f["labels"]
            seq = " > ".join(str(lab.get(k, "")) for k in LEVEL_KEYS if lab.get(k))
            ex_lines.append(f"- 样本《{f['name']}》→ {seq}")
        examples = "\n".join(ex_lines) if ex_lines else "（无同版本标杆）"

        # 玩法维度的强提醒（使用增强版 L2_CUES 动态生成）
        l2_cands = self.candidate_levels(version).get("二级字段", [])
        l2_detail = self._build_l2_detail(l2_cands)
        l2_rule = (
            "【玩法维度(二级字段)特别注意 —— 必须从真实画面判定】\n"
            "绝不能见『对局/刚枪/吃鸡』就默认填 BR玩法！\n\n"
            + l2_detail +
            f"\n当前版本玩法候选：{('、'.join(l2_cands) if l2_cands else '（全量）')}\n"
        )

        return (
            "【标杆样本（仅学风格，不要照搬）】\n" + examples + "\n\n"
            + l2_rule + "\n"
            "【待标注视频的内容识别结果】\n" + content_text + "\n\n"
            "请输出 JSON：{" + ", ".join(f'"{k}": "<候选值或空>"' for k in LEVEL_KEYS)
            + ', "画面摘要": "<80字内描述画面实际展示的玩法内容>"' + "}\n"
            "注意：六级字段为自由文本「看点」（可填具体情节/标题），九级字段固定输出「非AI」；"
            "一级字段固定为「" + version + "」。\n"
            "「画面摘要」用于语义匹配校验，请客观描述画面里真实发生的玩法内容，"
            "不要复述标签，也不要写剪辑手法之外的推测。"
        )

    def _build_l2_detail(self, l2_cands: list[str]) -> str:
        """根据当前版本的玩法候选，动态生成玩法识别规则详情。"""
        parts = []
        for mode in l2_cands:
            if mode not in L2_CUES:
                continue
            cues = L2_CUES[mode]
            # 分组显示：核心特征（前几个）+ 扩展特征
            core = cues[:5]
            ext = cues[5:]
            line = f"  · **{mode}**：识别到 {' / '.join(core)}"
            if ext:
                line += f"（还有：{' / '.join(ext)}）"
            parts.append(line)
        return "\n".join(parts) if parts else "（无额外线索）"

    # ========== 打标主流程 ==========
    # 强信号层级：CROSS_CUES 命中时「覆盖」非空错值（不止填空）。
    # 仅限线索确凿的层级；六级已降为自由文本看点，不参与覆盖。
    CROSS_OVERRIDE_LEVELS = {"二级字段", "五级字段"}

    # ---------- 辅助：别名归一化 ----------
    @staticmethod
    def normalize_label(level: str, val: str) -> str:
        if not val:
            return ""
        m = ALIAS_NORMALIZE.get(level)
        return m.get(val, val) if m else val

    # ---------- 辅助：确定性反推二级（覆盖 VLM 偏见）----------
    def _deterministic_l2(self, content_text: str, name: str = "", l5: str = "", use_name: bool = True):
        """返回确定性二级（内容驱动；name 仅作「无视觉内容时」的兜底，不介入视觉判定，避免作弊）。

        - 显式「综合玩法」信号 或 多玩法 token 混合 → 综合玩法
        - 单一玩法 token 命中 → 该玩法
        - 否则 L5主导L2 / prior_l2 兜底
        """
        low = (content_text or "").lower()
        name_low = (name or "").lower() if use_name else ""

        def hits(src: str):
            modes = set()
            for mode, toks in EVENT_TOKEN_L2.items():
                for t in toks:
                    if t and t.lower() in src:
                        modes.add(mode)
                        break
            return modes

        allmodes = hits(low) | hits(name_low)
        # 综合玩法：仅认显式信号（真实视频中由多模式内容/元数据判定，不走"多token拼接"误判）
        if "综合玩法" in allmodes:
            return "综合玩法"
        specific = allmodes - {"综合玩法"}
        if specific:
            # 若 L5 主导映射与命中玩法一致则优先采用，否则取其一
            if l5 and l5 in self.k.l5_to_l2 and self.k.l5_to_l2[l5] in specific:
                return self.k.l5_to_l2[l5]
            return next(iter(specific))
        # 回退：L5 主导 / prior_l2
        if l5 and l5 in self.k.l5_to_l2:
            return self.k.l5_to_l2[l5]
        return self.prior_l2(content_text)

    # ---------- 辅助：九级(纯元数据)判定，不依赖内容识别 ----------
    def _infer_l9(self, meta: dict, out: dict) -> str:
        """九级判定走 provenance 元数据，不用视觉内容识别。
        优先级：文件名token > 产出方/制作方式规则 > 多数类默认(非AI)。
        """
        name = (meta or {}).get("name", "") or ""
        # 1) 文件名 token
        for t in re.split(r"[-_\s#]+", name):
            if t in ("AI", "非AI"):
                return t
        # 2) 产出方/制作方式 规则
        for src_lvl in ("八级字段", "七级字段"):
            v = out.get(src_lvl, "") or (meta.get(src_lvl, "") if isinstance(meta, dict) else "")
            if v in L9_PROVENANCE_RULES:
                return L9_PROVENANCE_RULES[v]
        # 3) 多数类默认（库内 非AI 占 82%）
        return "非AI"

    def tag(self, version: str, content_text: str, vlm, image_paths=None, meta=None,
            diagnostics: dict | None = None) -> dict:
        """vlm: 具备 chat(system, user, image_paths) 的对象。返回十级字段 dict。

        meta: 可选视频元数据 dict（含 width/height/name），用于确定性判定画幅/八级/九级。
        设计：二/三级以「确定性推理」为主（事件token、L5→L2、L4→L3），
              VLM 视觉识别仅作为无可推信号时的残差兜底。

        diagnostics: 传入一个 dict 时，会回填三路投票所需的中间量
              （vlm_raw_l2 / vlm_summary / rule_l2 / content_text），
              供 vote_l2() 使用。不传则行为与原先完全一致。
        """
        system = self.build_system(version)
        user = self.build_user(version, content_text)
        raw = vlm.chat(system, user, image_paths=image_paths or [])
        labels = _extract_tag_json(raw) or {}

        if diagnostics is not None:
            diagnostics["vlm_raw_l2"] = str(labels.get("二级字段", "") or "").strip()
            diagnostics["vlm_summary"] = str(labels.get("画面摘要", "") or "").strip()
            diagnostics["content_text"] = content_text

        cand = self.candidate_levels(version)
        out = {"一级字段": version}
        for k in LEVEL_KEYS:
            if k == "一级字段":
                continue
            if k == "六级字段":
                # 看点：自由文本，不约束词表、不被跨级覆盖
                out[k] = str(labels.get(k, "") or "").strip()
                continue
            val = str(labels.get(k, "") or "").strip()
            val = self.normalize_label(k, val)
            if val and cand.get(k) and val not in cand[k]:
                val = ""
            out[k] = val

        low = (content_text or "").lower()
        name = (meta or {}).get("name", "") if meta else ""

        # --- 跨级关键词先验（仅二级/五级可覆盖非空；其余填空）---
        applied = set()
        for cue, mapping in sorted(CROSS_CUES.items(), key=lambda x: -len(x[0])):
            if cue.lower() in low:
                for lvl, val in mapping.items():
                    if lvl in applied:
                        continue
                    if val not in cand.get(lvl, []):
                        continue
                    if lvl in self.CROSS_OVERRIDE_LEVELS or not out.get(lvl):
                        out[lvl] = val
                        applied.add(lvl)

        # --- 层级共现兜底（稀有值密集层级填空）---
        self.cooccur_fill(out)

        # --- 二级：确定性反推（覆盖 VLM「见战斗默认BR」偏见）---
        # 关键修正：有视觉内容时，二级只由 VLM 内容（玩法token/L5卖点）驱动，文件名不介入，避免「抄答案」；
        #           仅当无抽帧/无媒体（text_only）时，才允许用文件名做兜底判定。
        #           八/九/十级仍走文件名/账号等元数据（来源/AI/画幅），属合规元数据属性。
        if out.get("二级字段") != "综合玩法":
            has_media = bool(image_paths)
            det = self._deterministic_l2(
                content_text,
                name if not has_media else "",
                out.get("五级字段", ""),
                use_name=not has_media,
            )
            if det and det in cand.get("二级字段", []):
                out["二级字段"] = det

        # --- 三级：由四级确定性反推（不再依赖视觉）---
        l3 = L4_TO_L3.get(out.get("四级字段", ""))
        if l3 and l3 in cand.get("三级字段", []):
            out["三级字段"] = l3

        # --- 画幅（十级）由视频宽高比确定性判定 ---
        if meta and meta.get("width") and meta.get("height"):
            out["十级字段"] = "横" if meta["width"] >= meta["height"] else "竖"

        # --- 八级(素材产出方) 属元数据，从文件名抽取 ---
        if meta and meta.get("name"):
            name_meta = self._meta_from_name(meta["name"], cand)
            for lvl, val in name_meta.items():
                if lvl == "九级字段":
                    continue  # 九级统一走 _infer_l9
                if val and (not out.get(lvl) or out.get(lvl) not in cand.get(lvl, [])):
                    out[lvl] = val

        # --- 九级：始终以 provenance 元数据判定（不依赖内容识别）---
        out["九级字段"] = self._infer_l9(meta or {}, out)

        if diagnostics is not None:
            diagnostics["rule_l2"] = out.get("二级字段", "")

        return out

    # ========== 二级字段三路投票 ==========
    # 实测（61 条人工真值）结论：
    #   A 模型直判 75.4%   B 规则层 77.0%   C 语义匹配 73.8%   A+B+C 投票 86.9%
    # 关键发现：
    #   1. 两路投票无效（77.0%/75.4%/77.0%，与单路持平）——两路只有「一致/不一致」，
    #      不一致时无信息增益；三路才真正构成「多数」。
    #   2. 「语义高置信就推翻规则」是负收益（-1.6%）。语义的正确用法是当平等的第三票，
    #      不是当纠偏器。
    #   3. 三路一致性 = 免费的高质量置信度：三路一致 32 条准确率 100%，
    #      2:1 分歧 81.8%，三路全不同 42.9%。可直接用于自动放行 / 转人工分流。
    VOTE_MIN_SCORE = 0.60      # 语义单独纠偏的最低相似度（默认偏高，几乎不触发）
    VOTE_MIN_MARGIN = 0.03     # 语义单独纠偏的最低领先优势

    def vote_l2(self, version: str, out: dict, diagnostics: dict) -> tuple[str, dict]:
        """对二级字段做 A(模型) / B(规则) / C(语义) 三路投票。

        返回 (最终值, 投票明细)。语义路不可用时自动退化为 A+B 两路。
        """
        cand = self.candidate_levels(version).get("二级字段", []) or []
        cand_set = set(cand)

        def _valid(v: str) -> str:
            v = self.normalize_label("二级字段", (v or "").strip())
            if not v:
                return ""
            if not cand_set or v in cand_set:
                return v
            # 模型常输出「BR玩法（异变怪物玩法）」这类带补充说明的形式，
            # 取括号前的主体部分回表，避免整条票被判为词表外而白白弃权。
            m = re.match(r"^([^（(]+)", v)
            if m:
                head = m.group(1).strip()
                if head in cand_set:
                    return head
            return ""

        a_raw = self.normalize_label("二级字段",
                                     str(diagnostics.get("vlm_raw_l2", "") or "").strip())
        a = _valid(a_raw)
        # 经过括号清洗才入表的票，说明模型输出带补充说明（模型自身也不确定），
        # 它与规则层撞出的「一致」属于虚假共识，不允许构成 high 置信。
        a_cleaned = bool(a) and a != a_raw
        # 模型有判断但落在词表外（如通用版本下的「特殊玩法」）——该票不能参与组成结果，
        # 但要记为「模型与规则存在分歧」，否则置信度会被高估。
        a_oov = bool(a_raw) and not a
        b = _valid(out.get("二级字段", "") or diagnostics.get("rule_l2", ""))
        c, c_score, c_margin, multi_hit, c_full = "", 0.0, 0.0, False, ""

        # C 路：语义匹配（本地 embedding，零 API 成本；不可用时优雅降级）
        text = diagnostics.get("vlm_summary") or diagnostics.get("content_text") or ""
        if text:
            try:
                sem = self._get_semantic_matcher(cand)
                if sem:
                    r = sem.match_with_margin(text)
                    c = _valid(r["top1"] or "")
                    c_score, c_margin = r["score"], r["margin"]
                    full = self._get_semantic_matcher_full(cand)
                    if full:
                        from ..tagging.semantic_matcher import is_multi_mode
                        t = full.match(text, topk=1)
                        c_full = t[0][0] if t else ""
                        multi_hit = is_multi_mode(text)
            except Exception:
                c = ""

        # 综合玩法双闸门：多模式规则命中 且 语义(含综合玩法候选)也判综合
        if multi_hit and _valid(c_full) == "综合玩法" and (not cand_set or "综合玩法" in cand_set):
            return "综合玩法", {"final": "综合玩法", "votes": [a, b, c],
                                "confidence": "high", "reason": "多模式双闸门命中"}

        votes = [v for v in (a, b, c) if v]
        final, reason = "", ""
        for v in votes:
            if votes.count(v) >= 2:
                final, reason = v, "多数投票"
                break
        if not final and c and c_score >= self.VOTE_MIN_SCORE and c_margin >= self.VOTE_MIN_MARGIN:
            final, reason = c, "语义强证据纠偏"
        if not final:
            final, reason = (b or a or c), "回落规则层"

        uniq = {v for v in (a, b, c) if v}
        if len(votes) == 3 and len(uniq) == 1 and not a_cleaned:
            confidence = "high"      # 三路一致：实测 100% 可靠，可自动放行
        elif len(votes) == 3 and len(uniq) == 3:
            confidence = "low"       # 三路全不同：实测 42.9%，必须人工
        elif a_oov and b and c and b != c:
            # 模型判了词表外的值，且规则与语义互相冲突 → 三方无共识，转人工
            confidence = "low"
        elif len(votes) >= 2:
            confidence = "medium"
        else:
            confidence = "unknown"   # 有效票不足两票，无法评估

        return final, {
            "A_模型直判": a, "B_规则层": b, "C_语义": c,
            "A_原始输出": a_raw, "A_词表外": a_oov,
            "C_score": c_score, "C_margin": c_margin,
            "final": final, "reason": reason, "confidence": confidence,
        }

    def tag_with_vote(self, version: str, content_text: str, vlm, image_paths=None,
                      meta=None) -> tuple[dict, dict]:
        """打标 + 二级字段三路投票。返回 (十级字段 dict, 投票明细)。"""
        diag: dict = {}
        out = self.tag(version, content_text, vlm, image_paths=image_paths,
                       meta=meta, diagnostics=diag)
        final, info = self.vote_l2(version, out, diag)
        out["二级字段"] = final
        return out, info

    # ---------- 语义匹配器（懒加载，进程内单例）----------
    _sem_cache: dict = {}

    @classmethod
    def _sem(cls, key: str, labels: list[str]):
        try:
            from ..tagging.semantic_matcher import SemanticMatcher
        except Exception:
            return None
        ck = (key, tuple(sorted(labels)))
        if ck not in cls._sem_cache:
            try:
                cls._sem_cache[ck] = SemanticMatcher(labels=labels, use_rich=True)
            except Exception:
                cls._sem_cache[ck] = None
        return cls._sem_cache[ck]

    def _get_semantic_matcher(self, cand: list[str]):
        """玩法类标签的语义匹配器（不含「综合玩法」，避免元描述黑洞）。"""
        from ..tagging.semantic_matcher import L2_SEMANTIC_DEFS
        labels = [l for l in L2_SEMANTIC_DEFS
                  if l != "综合玩法" and (not cand or l in cand)]
        return self._sem("play", labels) if labels else None

    def _get_semantic_matcher_full(self, cand: list[str]):
        """含「综合玩法」的语义匹配器，仅用于双闸门的第二道闸。"""
        from ..tagging.semantic_matcher import L2_SEMANTIC_DEFS
        labels = [l for l in L2_SEMANTIC_DEFS if (not cand or l in cand)]
        return self._sem("full", labels) if labels else None

    # ---------- 离线/文件名启发式打标：对已填标签做确定性纠偏 ----------
    def normalize_and_fix(self, tags: dict, name: str = "", account: str = "", validate: bool = True) -> dict:
        """对「文件名解析/启发式」已产出的标签做与 tag() 一致的确定性纠偏。

        用于无 VLM 时的兜底打标：输入已是十级 dict，这里统一做
        别名归一、候选校验、共现兜底、L4→L3 反推、八级(文件名)与九级(provenance)修正。

        validate=False 时跳过候选词表校验（用于已标准化命名，避免把 CG37 专属值误清空）。
        """
        version = tags.get("一级字段") or "CG37"
        cand = self.candidate_levels(version)
        out = {"一级字段": version}

        # 1) 别名归一 + 候选校验（六级自由文本除外）
        for k in LEVEL_KEYS:
            if k == "一级字段":
                continue
            if k == "六级字段":
                out[k] = str(tags.get(k, "") or "").strip()
                continue
            val = self.normalize_label(k, str(tags.get(k, "") or "").strip())
            if validate and val and cand.get(k) and val not in cand[k]:
                val = ""
            out[k] = val

        # 2) 共现兜底（填空）
        self.cooccur_fill(out)

        # 3) L4 → L3 确定性反推（仅校验模式：启发式/VLM 结果需对齐；标准名已含正确 L3 时跳过）
        if validate:
            l3 = L4_TO_L3.get(out.get("四级字段", ""))
            if l3 and l3 in cand.get("三级字段", []):
                out["三级字段"] = l3

        # 4) 八级：从文件名抽取元数据（达人名/机构 token）
        if name:
            name_meta = self._meta_from_name(name, cand)
            for lvl, val in name_meta.items():
                if lvl == "九级字段":
                    continue
                if val and (not out.get(lvl) or out.get(lvl) not in cand.get(lvl, [])):
                    out[lvl] = val
        # 账号作为八级兜底（达人名/官号）
        if not out.get("八级字段") and account:
            acc = account.strip().rstrip(",").strip(" ,")
            if acc and acc not in ("-",):
                out["八级字段"] = acc

        # 5) 九级：provenance 判定（文件名 token > 八级/七级规则 > 默认非AI）
        meta = {"name": name}
        out["九级字段"] = self._infer_l9(meta, out)

        return out

    @staticmethod
    def _meta_from_name(name: str, cand: dict) -> dict:
        """从文件名抽取八级(产出方)/九级(AI标识)。仅命中候选词表才采纳。

        八级为纯元数据（JP/SNK/DX/达人名等），画面无法识别，文件名才是最可靠来源；
        九级 AI/非AI 同理常写在文件名里。
        """
        res = {}
        toks = re.split(r"[-_\s#]+", name)
        # 九级
        for t in toks:
            if t == "非AI":
                res["九级字段"] = "非AI"; break
            if t == "AI":
                res["九级字段"] = "AI"; break
        # 八级：已知短码优先
        known8 = {"JP", "JP1", "SNK", "DX", "NQ", "CM", "SW"}
        for t in toks:
            if t in known8:
                if t in cand.get("八级字段", []):
                    res["八级字段"] = t
                break
        # 八级：达人名（文件名含「达人X」或结尾 #X），模糊匹配候选词表
        if "八级字段" not in res:
            cand8 = cand.get("八级字段", [])
            for t in toks:
                if "达人" in t or (t and t in "abcdefghijklmnopqrstuvwxyz"):
                    pass
            # 在整串里找「达人」后的词
            m = re.search(r"达人([^\-_#\s]+)", name)
            seed = m.group(1) if m else ""
            if not seed:
                # # 后的达人名
                m2 = re.search(r"#([^\-_#\s]+)$", name)
                if m2:
                    seed = m2.group(1)
            if seed:
                for c in cand8:
                    if seed in c or c in seed or ("达人" in c and seed in c):
                        res["八级字段"] = c
                        break
        return res


def _extract_tag_json(text: str) -> dict:
    if not text:
        return {}
    s = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, re.S)
    if m:
        s = m.group(1)
    else:
        m = re.search(r"\{[^{}]*\}", s, re.S)
        if m:
            s = m.group(0)
    try:
        return json.loads(s)
    except Exception:
        out = {}
        for key in LEVEL_KEYS:
            mm = re.search(rf'"{key}"\s*:\s*"(.*?)"', s)
            if mm:
                out[key] = mm.group(1)
        return out


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "/workspace/outputs/_ref/xlsx/v2_rl_library.xlsx"
    t = LearnedTagger.from_library(p)
    print("版本:", list(t.k.vocab_by_version.keys()))
    print("少样本数:", len(t.k.fewshot))
    print("关键词先验数:", len(t.k.keyword_prior))
    print("--- 自检：玩法线索映射 ---")
    print("prior('超体核心升级 超体终端')=", t.prior_l2("超体核心升级 超体终端"))
    print("prior('地铁装甲变卖物')=", t.prior_l2("地铁装甲变卖物"))
    print("prior('青铜门古墓摸金')=", t.prior_l2("青铜门古墓摸金"))
    print("prior('经典海岛跳伞吃鸡')=", t.prior_l2("经典海岛跳伞吃鸡"))
    print("prior('小马宝莉联动')=", t.prior_l2("小马宝莉联动"))
    print("--- CG36 候选二级:", t.candidate_levels("CG36").get("二级字段", []))
    print("--- 通用候选二级:", t.candidate_levels("通用版本").get("二级字段", []))
