# 情感向度（VAD）设计：词典 + 学习 + 边界

> 目标：给「视频内容」和「评论」都打出可比较的情感向度——valence（正负）/ arousal（唤醒）/ dominance（支配）与强度，用于 Task A（内容 stance）与 Task B（评论 valence 预测）。

## 一、数据与词典

| 资源 | 用法 |
|---|---|
| NRC-VAD-Lexicon-ForVariousLanguages（用户提供） | 英文词 + V/A/D(0-1) + 100+ 语言翻译列；取 `Chinese-Simplified` 列构建中文 VAD 词典（约 1.4 万词条） |
| NRC-Emotion-Lexicon-ForVariousLanguages | 同上，10 维情感（anger/anticipation/disgust/fear/joy/negative/positive/sadness/surprise/trust）⊕ 中文翻译列（约 5 千词条） |
| `data/lexicons/zh_seed.json`（自建） | 中文口语/网络语种子（约 200 条）：好评/拉胯/绝绝子/退钱/不要买/不如…，VAD 手工标定，权重 ×2 |
| `data/lexicons/zh_learned.json`（可选） | 从人工标注评论反向学习的 2–3 字 n-gram 极性（bootstrapp 第一层） |

## 二、分析器（`src/sentiment/analyze.py`）

- 最长匹配扫描（1–4 字窗口）
- 否定翻转（词前 2 字含 不/没/无/别/未/莫/非）
- 程度修饰（太/超/特别/非常/极其/巨/贼 → arousal+0.1、|v−0.5|×1.2）
- 「好/太 + 负面词」→ 更负面（修过一个把「好垃圾」判成正面的 bug）
- 虚拟语气吐槽：「要是/如果…就好了/就爽了」→ 判负
- 转折拆句：取最后一个 但是/不过/可是/然而 之后的片段
- NRC 派生词只保留强极性（|v−0.5|≥0.2），并过滤功能词/名词噪声
- 输出：`{label, intensity 1-4, valence, arousal, dominance, hits, emotions}`

## 三、校准结果（关键，务必看）

在两条真实视频的 780 条三 rater 评论上做**聚合对比**（逐条准确率不是目标，Task B 看分布）：

| 视频 | GT 净情绪（pos−neg） | 词典净情绪 | 判断 |
|---|---|---|---|
| v1 原神二创 | **+0.254** | **+0.212** | ✅ 方向与量级都对 |
| v2 黑伤测评 | **−0.168** | **+0.14** | ❌ 仍偏正（与 10 个模型相同的乐观偏差） |

结论：**词典能兜住"阳光内容"，兜不住"软性吐槽"**——v2 的负向是"不如北极星/不要买/有点隔应/服了"这类语境抱怨，纯词表匹配抓不全。这正好是 Task B 需要 LLM 上下文标注 + 微调的原因，也是我们此前 10 平台 v2 全部预测正面（0/10）的同一现象在词表上的复现。

## 四、下一步（bootstrapp / 强化学习）

1. **LLM 评论标注**（已有 3-rater 流程，κ≈0.7）：给每条评论输出 label + VAD + 证据词，作为 Task B 的 gold 软标签。
2. **bootstrapp**：用 gold 反向更新 `zh_learned.json` 与 P/R 先验表（`pr_sentiment.PRIORS`），每轮用 v1/v2 口径回归验证。
3. **P/R → 情感映射**：`pr_sentiment.predict_comment_valence()` 当前是规则先验（15 个 P 码各带 V/A/标签），下一步用 gold 学成小模型（码向量 → valence 分布，J-S 损失）。
4. **评论爬取对照**：CDP DOM 抓取（`scripts/scrape_comments.js`），与视频标注对齐后进入 Task B 训练。
