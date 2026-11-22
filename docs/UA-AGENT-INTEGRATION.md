# UA-ClipInsight 迁移包 → 本仓库微调工作流：集成说明

> 来源：`C:\Users\12275\OneDrive\Desktop\uavideo_portable_pack.zip`（原训练机迁移包，UA-ClipInsight + UAvideo skill + 实验文档）
> 集成位置：`pipeline/ua_agent/`（可运行 agent）+ `pipeline/`（既有微调脚手架）
> 验证：2026-11-22，`skilltest/newvideo/raw/v3.mp4`（31.2s 和平精英地铁逃生实录）全链路跑通，109.3s

---

## 一、迁移包里有什么（已核）

| 部分 | 内容 | 去向 |
|---|---|---|
| `UAvideo-skill/` | skill 本体（SKILL.md/references/scripts） | 与桌面 canonical 技能同源，未重复安装 |
| `pipeline-src/` | UA-ClipInsight 多模态分析引擎：extractor（抽帧+关键帧）/ vision（VLM 客户端+逐帧分析）/ comments（采集+情感）/ tagging（十级标签、学习型打标器、语义匹配）/ report / platforms / crawlers | **vendor 到 `pipeline/ua_agent/ua_src/`**（包内相对导入已修正） |
| `pipeline-docs/` | 方案与实验：CG37 融合方案、三路投票实验（86.9%）、300 条方案对比、优化后标签体系（四/五/六级）、UGC 五级规则库 v2.6、特征体系 v1.9 | 见 `portable2/pipeline-docs/`（UTF-8 重解包后的干净副本） |
| `ua-clipinsight-skeleton/` | GitHub 版标注闭环（clips.csv + release 直链 + 人工回填） | 参考其 `human_correction` 回填闭环设计 |
| 根目录 `和平精英素材打标分析.md` | 单条素材打标样例 | 样例参照 |

**注意**：迁移包里**没有**强化学习库 `v2_rl_library.xlsx`（`learned_tagger.from_library` 的学习源）和 torch 训练代码——权重级微调需另配。当前环境也无 torch/CUDA（GPU 存在但未装 CUDA torch）。

---

## 二、我们做了什么

### 1. 依赖修复（本机 python 缺 yaml/requests/openpyxl/cv2）
已 `pip install --user requests pyyaml openpyxl opencv-python-headless pillow`，全部可用。

### 2. 包内导入修正
`pipeline/ua_agent/ua_src/` 里 `from src.X` 按目录深度改写为相对导入（**14 个文件**），`import ua_agent.ua_src.pipeline` 通过。

### 3. 知识库（"训练 agent"的知识蒸馏层）
- `pipeline/ua_agent/knowledge.py`：从 `version_notes.py` 的富知识（LEVEL_HIERARCHY / L4_TO_L3 / L5_CATEGORY_MAP / L9_PROVENANCE_RULES）构建受控词表；四/五级采用《优化后标签体系》权威词表（四级 20 值、五级 38 值），九级按 provenance 规则（内录/混剪/CG 等 → 非AI），十级按宽高，八级按账号 token。
- `pipeline/ua_agent/train_agent.py`：
  - `--bootstrap`：无 RL 库即可生成 `knowledge.json`（已完成，三版本词表）
  - `--from-xlsx v2_rl_library.xlsx`：从强化学习库学习版本词表/少样本/关键词先验/共现先验/值频次（**等你的库文件，一放就能跑**）
  - `--eval gold.json`：逐级准确率 + 整体全对率

### 4. Agent 编排（`pipeline/ua_agent/agent.py`）
```
G1 抽帧(cv2) → G2 关键帧筛选(模糊/去重/场景) → G3 VLM 逐帧理解 + 跨帧聚合
→ G4 评论(可选,词典情感) → G5 十级打标（受控词表VLM + 六级自由文本 + 元数据分流）
→ G6 report.md + annotation.json（训练标注样本）
```
- 四级→三级按 `L4_TO_L3` 链式校正；七级→九级按 provenance；宽高→十级。
- VLM 走智谱 `glm-5.3-flashx`（config.yaml，`${ZAI_API_KEY}`），也支持 cuhksz/deepseek OpenAI 兼容端点；无 key 自动 MockVLM 离线跑通。

### 5. CLI（`pipeline/ua_agent/run.py`）
```powershell
# 本地视频
python -m pipeline.ua_agent.run --video skilltest/newvideo/raw/v3.mp4 --out pipeline/ua_agent/outputs/v3
# 平台链接（走无登录下载：pipeline/skill_bridge.UAVideo.download_douyin）
python -m pipeline.ua_agent.run --url "https://www.douyin.com/video/7709870849365478116"
```

---

## 三、验证结果（v3.mp4）

| 项 | 值 |
|---|---|
| 耗时 | 109.3s（11 关键帧 × 1 次 VLM + 1 次打标） |
| 二级 | 地铁逃生 |
| 三级 | 游戏体验（由四级链式校正） |
| 四级 | 刚枪手感 |
| 五级 | 刺激刚枪 |
| 六级（自由文本） | 撤离模式搜刮高价值物资并刚枪追击敌人 |
| 七级 | 内录 |
| 八级 | —（无账号 token） |
| 九级 | 非AI（provenance 规则） |
| 十级 | 横 |
| 规范名 | `通用版本-地铁逃生-游戏体验-刚枪手感-刺激刚枪-[…]-内录-非AI-横` |
| 产物 | `pipeline/ua_agent/outputs/v3/{report.md, annotation.json}` |

逐帧理解质量抽查：识别出「和平精英」「淘汰数 0」「物资总值 285.37 万」「撤离倒计时 8:30」「饲料大开挖活动入口」等 UI 与活动信息；11 帧摘要均可追溯到具体时间点。

---

## 四、与本项目（CSS5230 微调）的对应关系

| 项目需求 | 迁移包/agent 提供 | 状态 |
|---|---|---|
| Task A 打标（P/R 码 + 十级标签） | 十级标签 agent（本包）；P/R 码仍走既有 skill pipeline（`_probe/zai_run.js`） | ✅ 十级；P/R 双轨可并存 |
| Task A 软标签 | `annotation.json` 的 `ua10` 字段 + 人工回填 `human_correction`（skeleton 闭环） | ✅ 可对接 `pipeline/soft_labels.py` |
| Task B 评论 valence | `comment_sentiment`（词典口径）+ 可换 LLM | ✅ 已产出字段，评论采集沿用 CDP 方案 |
| B0/B5 基线 | 本 agent ≈ B5（商业 MLLM prompt 管线）的本地实现 | ✅ |
| 知识蒸馏训练 | `train_agent.py --bootstrap`（已跑）/ `--from-xlsx`（待库） | ⏳ 等 `v2_rl_library.xlsx` |
| 权重级微调（LoRA/SALFT） | `pipeline/models.py + train_taskA.py`（需 torch/CUDA） | ⏳ 本机未装 CUDA torch |

**三路投票（86.9%）**：`ua_src/tagging/semantic_matcher.py`（bge-small-zh）与 `learned_tagger.tag_with_vote` 已在包内；缺 `sentence_transformers` 与 bge 模型权重，装上后即可启用 A+B+C 投票与 high/medium/low 置信分流（文档实测：high 组 100%、medium 80%、low 43%）。

---

## 五、下一步（按依赖排序）

1. **给 `v2_rl_library.xlsx`**（359 行 RL 库）→ 跑 `python -m pipeline.ua_agent.train_agent --from-xlsx <路径>`，agent 立刻从"bootstrap 词表"升级为"学习型打标器"（词表/少样本/先验/共现全部来自真值库）。
2. **装 `sentence-transformers` + bge-small-zh** → 启用三路投票 + 置信度分流（离线评估脚本 `ua_src` 下已有实验口径）。
3. **装 CUDA torch** → 跑 `pipeline/train_taskA.py`（软标签头）+ `taskB.py`（A→B 映射 + Audience-Prior Null），进 B6。
4. 规模化：agent 已支持批处理（逐条 `run.py`），2000 条约 1 天（下载受风控约束），详见 `docs/DOUYIN-DOWNLOAD-PLAYBOOK.md` 与报告中的耗时测算。
