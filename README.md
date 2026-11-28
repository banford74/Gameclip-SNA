# Gameclip-SNA · 游戏短视频 P/R 标注与情感向度工作流

> 下载 → 抽帧 → 多模态理解 → **P/R 创意特征打标** → **情感向度（VAD）** → 云端人工确认 → 软标签/微调。
> 服务 CSS5230《From Content to Contagion》Task A（内容 stance）/ Task B（评论 valence）。

## 标签体系

- **P 码 15 项**（情节层：社死/刚枪/变装/回忆杀…，可多选）
- **R 码 91 项**（视觉特征：开场钩子/战斗/BGM/画幅/剪辑节奏…，有/无 + 少量枚举）
- **情感向度**：内容与评论各算 VAD（valence/arousal/dominance）+ 强度 + 标签，词典来自 NRC-VAD/NRC-Emotion 多语言对齐表（中文列）+ 自建口语种子。
- 十级机械标签（和平精英版本体系）**已弃用**，其「知识蒸馏/投票/置信分层」方法已移植到 P/R。
- 口径：**内容四分类（含 mixed）+ 证据；评论只打 VAD（1-9，禁止 mixed）**；详见 [docs/PR-LABEL-SYSTEM.md](docs/PR-LABEL-SYSTEM.md)、[docs/SENTIMENT-VAD.md](docs/SENTIMENT-VAD.md)、[docs/ANNOTATION-MANUAL.md](docs/ANNOTATION-MANUAL.md)。

## 目录

```
src/
  ua_agent/            Agent：下载→抽帧→关键帧→VLM 理解→P/R 打标→情感→报告/标注
    agent.py           ClipAgent 主流程（G1–G6）
    pr_tagger.py       P/R 打标（VLM A 路 + 规则层 B 路，置信分层）
    pr_codebook.py     15 P + 91 R 码表与校验
    pr_sentiment.py    P/R → 评论 valence 先验映射（可被 bootstrapp 更新）
    download.py        抖音无登录下载（feed API + CDN）
    cloud.py           Release 上传 + clips.csv（预览列前置、human_correction）
    run.py             CLI
    ua_src/            多模态引擎（抽帧/关键帧/VLM/评论/报告）
  sentiment/           情感 VAD（词典 + 学习器 + 校准脚本）
    lexicons.py        NRC 多语言表 → 中文 VAD/Emotion 词典（缓存）
    analyze.py         最长匹配/否定/程度/转折/虚拟语气 → VAD
    learn.py           从标注评论学词表（bootstrapp，5 折 CV）
  config.py codebook.py soft_labels.py metrics.py models.py
  train_taskA.py taskB.py falsify.py ch_sims_check.py balance.py
configs/balance_plan.json   多游戏/多形态配比 + OOD 留出（防过拟合）
data/clips.csv              标注总表（预览/情感/人工回填）
data/lexicons/              vad.json / emo.json / zh_seed.json
docs/                       标签体系 / 情感设计 / 下载 playbook
scripts/                    make_player.py（Pages 播放页）、dl_mobile.js
```

## 快速开始

```bash
pip install -r requirements.txt
export OPENCODE_API_KEY=...   # OpenCode Models 的 key；逐帧视觉 + P/R 打标都走这个端点
                              # 默认模型 deepseek-v4.1-flash（可用 OPENCODE_BASE_URL / OPENCODE_MODEL 覆盖）

python -m src.ua_agent.run --video x.mp4 --game 和平精英 --format 实机录屏
python -m src.ua_agent.run --url "https://www.douyin.com/video/7709870849365478116"
python -m src.ua_agent.run --video x.mp4 --comments-file comments.json   # 带评论 → 评论 VAD + P/R 映射
```

产物：`outputs/<clip_id>/annotation.json`（pr + sentiment{content, by_frame, comments, pr_mapping}）+ `report.md`。

## 云端人工确认

```bash
export GITHUB_TOKEN=...  UA_CLOUD_REPO=banford74/Gameclip-SNA  UA_PAGES_BASE=https://banford74.github.io/Gameclip-SNA
python -m src.ua_agent.cloud
```

`clips.csv` 列顺序：`clip_id, game, format, preview_url, human_correction, review_status, pr_p, pr_conf, content_label, content_vae, comment_pred, ...`（预览与人工列前置）。
人工回填 `human_correction`（修正 P/R、改情感标签）→ `review_status=corrected` → 作为 gold 进 `soft_labels.py` / 训练。

## 情感校准（已跑，务必看结论）

在 780 条三 rater 评论上做聚合对比：v1 GT 净情绪 +0.254 vs 词典 +0.212（✅）；v2 GT −0.168 vs 词典 +0.14（❌ 偏乐观）。
——词典兜得住阳光内容、兜不住软性吐槽；v2 需要 LLM 上下文标注 + 微调。详见 [docs/SENTIMENT-VAD.md](docs/SENTIMENT-VAD.md)。

## 与论文的对应

- 本仓库打标 ≈ §2.6 的 **B5（商业 MLLM prompt 基线）**本地实现；
- `src/falsify.py` 内置 §2.7 预注册证伪（B6 vs B6′ parity+ECE、品类内置换、Audience-Prior Null）；
- 多游戏/形态配比与 OOD 留出见 `configs/balance_plan.json`。

## 说明

- 只用公开分发的视频流；不落盘 cookie、不逆向评论接口签名。
- Release 只镜像原片（下载用途），Pages 托管 480p 预览（可内嵌播放）；2000 条规模需分批 Pages 或对象存储。
