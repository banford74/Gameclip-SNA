# 进度同步（可选）

标注页本身已经**自动保存**（浏览器 localStorage，刷新/关页不丢）。跨人自动更新需要共享写入口，
有两种方式：

## 方案 A — 零设置（现在就能用）

1. 每人标注完（或每天）点「导出我的标注 CSV」
2. 打开 https://banford74.github.io/Gameclip-SNA/progress.html
3. 把 4 个 CSV 拖进页面 → 立刻看到每人进度、各游戏完成率、stance 分布；有重叠条目时自动算 Cohen's κ

## 方案 B — 自动同步（一次性约 5 分钟设置）

**1. 建同步端点（Apps Script）**

1. https://script.google.com → 新建项目 → 粘贴 `scripts/sync_endpoint.gs` → 保存
2. 部署 → 新建部署 → Web 应用；执行身份＝我；访问权限＝任何人
3. 复制 `https://script.google.com/macros/s/.../exec`

**2. 发给标注员（每人一次）**

- 打开自己的标注页（如 `?a=2`），在「同步地址」粘贴上一步 URL 即可（会存在其浏览器里）
- 或者直接发带 sync 参数的链接：
  `https://banford74.github.io/Gameclip-SNA/?a=2&sync=https%3A%2F%2Fscript.google.com%2Fmacros%2Fs%2F...%2Fexec`
- 之后每次保存（防抖 1.2 秒）都会自动 POST 一份该标注员的全量标注；页面右上角显示「已同步 时间（N 条）」

**3. 让进度页自动刷新**

1. Google Sheet → 文件 → 共享 → 发布到网络 → 选 `labels` 工作表、格式 CSV → 复制链接
2. 打开 `https://banford74.github.io/Gameclip-SNA/progress.html?data=<CSV 链接>`（可收藏，每 20 秒自动刷新）

> 说明：Apps Script 的 POST 用 `mode:'no-cors'`（无法读响应，但写入生效）；进度页走「发布到网络的 CSV」读取（有 CORS）。

## 数据口径

- 每个 `(annotator, clip_id)` 只保留一次；写入/汇总都按 `annotated_at` 取最新
- 进度 = 该标注员名下已标注数 / 分到数（551/550/550/550）
- κ 需要重叠：当前分工互不重叠，只有人为让两人标同一批（如 gold set 30 条）时才会出现
