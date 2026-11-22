# Gameclip-SNA · 游戏短视频多模态标注与微调工作流

> 把「游戏短视频」从下载 → 抽帧 → 多模态理解 → **P/R 创意特征打标** → 云端人工确认 → 软标签 → 微调，
> 收成一条可复现的流水线。服务于 CSS5230 项目《From Content to Contagion》的 Task A/B。

## 标签体系（主：P/R 双层）

- **P 码 15 项**（情节层：社死/刚枪/变装/回忆杀…，叙事骨架，可多选）
- **R 码 91 项**（视觉特征：开场钩子/战斗/BGM/画幅/剪辑节奏…，有/无 + 少量枚举）
- 十级机械标签（和平精英版本体系）保留为**辅助**（`ua10` 字段），其「知识蒸馏+投票+置信分层」方法已移植到 P/R。
- 详见 [docs/PR-LABEL-SYSTEM.md](docs/PR-LABEL-SYSTEM.md)。

## 目录

```
src/
  ua_agent/            Agent：下载→抽帧→关键帧→VLM理解→P/R打标→报告/标注
    agent.py           ClipAgent 主编排（G1-G6）
    pr_tagger.py       P/R 打标器（A=VLM 直判 + B=规则层表里映射；置信分层）
    pr_codebook.py     15 P + 91 R 码表与校验
    knowledge.py       十级标签词表/元数据规则（辅助体系）
    download.py        抖音无登录下载（feed API + CDN）
    cloud.py           GitHub Release 上传 + clips.csv 人工确认闭环
    train_agent.py     知识库构建（bootstrap / --from-xlsx 学习型）
    run.py             CLI：--video / --url / --labels / --game / --format
    ua_src/            多模态引擎（抽帧/关键帧/VLM/评论/报告，vendor 自 UA-ClipInsight）
  config.py codebook.py soft_labels.py metrics.py models.py
  train_taskA.py taskB.py falsify.py ch_sims_check.py balance.py
configs/balance_plan.json   多游戏/多形态配比与切分（防过拟合）
data/clips.csv              标注总表（AI 预标 + human_correction 回填）
docs/                       下载 playbook / 标签体系 / 集成说明
scripts/dl_mobile.js        抖音下载参考实现（node）
```

## 快速开始

```bash
pip install -r requirements.txt
export ZAI_API_KEY=...        # glm-5.3-flashx（视觉逐帧）
export DEEPSEEK_API_KEY=...   # deepseek-flash（P/R 打标通道）

# 单条：本地视频
python -m src.ua_agent.run --video path/to/x.mp4 --labels both --game 和平精英 --format 实机录屏

# 单条：平台链接（无登录下载）
python -m src.ua_agent.run --url "https://www.douyin.com/video/7709870849365478116"

# 训练 agent 的知识库
python -m src.ua_agent.train_agent --bootstrap
python -m src.ua_agent.train_agent --from-xlsx v2_rl_library.xlsx
```

产物：`outputs/<clip_id>/annotation.json`（P/R + ua10 + 逐帧）与 `report.md`。

## 云端人工确认真值（2000 条）

```bash
export GITHUB_TOKEN=...  UA_CLOUD_REPO=banford74/Gameclip-SNA
python -m src.ua_agent.cloud      # CloudPublisher：关键帧传 release → clips.csv 追加行
```

人工在 `data/clips.csv` 的 `human_correction` 列回填修正，`review_status` 置 `corrected`；
回写后作为 gold → `src/soft_labels.py` → `src/train_taskA.py` / `src/taskB.py`。

## 预览链路（不经过平台，一键播放/下载）

每条 clip 在 `clips.csv` 里有三类链接：

| 列 | 用途 | 示例 |
|---|---|---|
| `source_url` | 平台原链（溯源） | `https://www.douyin.com/video/...` |
| `preview_url` | **480p 压缩预览，浏览器内直接播放**（GitHub Pages 托管） | `https://banford74.github.io/Gameclip-SNA/media/xxx_preview.mp4` |
| `video_download_url` | 原片（GitHub Release 资产，点击下载） | `https://github.com/.../releases/download/clips-v1/xxx.mp4` |
| `keyframe_url` | 首帧预览图 | Release 资产 |

**播放页**：<https://banford74.github.io/Gameclip-SNA/>（由 `scripts/make_player.py` 从 clips.csv 生成）

```bash
python scripts/make_player.py     # 读 data/clips.csv → docs/index.html
```

**2000 条规模注意**：GitHub Pages 站点约 1GB 上限，480p 预览约 2MB/条 → 2000 条约 4GB，需分批：
- 每 300–400 条一个批次 Pages（`docs/batch-01/…`，`make_player.py --batch`），或
- 预览/原片迁到对象存储（Cloudflare R2 / 腾讯 COS 预签名 URL），clips.csv 换直链；
- Release 只镜像原片（下载用途），不作为内嵌播放源（`Content-Type: octet-stream` 不能内嵌）。


## 与论文/实验的对应

- 本仓库打标结果 ≈ 论文 §2.6 的 **B5（商业 MLLM prompt 基线）** 的本地实现；
- `src/falsify.py` 内置 §2.7 预注册证伪（B6 vs B6′ parity+ECE、品类内置换、Audience-Prior Null）；
- 多游戏/多形态配比见 `configs/balance_plan.json`（含 OOD 留出：光遇 + 音乐/舞蹈）。

## 说明

- 只用公开分发的视频流；不落盘 cookie、不逆向评论接口签名。
- GitHub Release 只上传关键帧做预览（视频留本地/对象存储），单批 ≤100–200 资产。
