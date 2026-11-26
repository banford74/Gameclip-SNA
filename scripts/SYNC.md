# 进度同步设置（B：Google Apps Script，推荐跨网络用）

## 0. 一句话

标注页每次保存（或点「💾 存档并回传」）会把该标注员的全量标注 POST 到一个端点；端点把数据
写进 Google Sheet。这个端点 URL 就叫「同步地址」。**部署一次，4 个人共用。**

---

## 1. 部署端点（约 5 分钟，需你的 Google 账号）

1. 打开 https://script.google.com → 左上「**新建项目**」→ 项目名填 `gameclip-sync`
2. 打开 `scripts/sync_endpoint.gs` → 全选复制 → 粘贴覆盖编辑器里的 `Code.gs` 内容 → **Ctrl+S 保存**
3. 右上「**部署**」→「**新建部署**」→ 齿轮图标选「**Web 应用**」
   - 说明：`gameclip-sync`
   - **执行身份**：`我（Me）`
   - **访问权限**：`任何人（Anyone）`
4. 点「部署」→ 首次会跳授权：选你的账号 →「高级」→「转至 gameclip-sync（不安全）」→「允许」
5. 复制生成的「**Web 应用 URL**」：`https://script.google.com/macros/s/..../exec`
   —— 这就是同步地址

> 以后改了脚本：部署 → 管理部署 → 编辑（铅笔）→「版本」选**新版本** → 部署，才会生效。

## 2. 验证端点

```bash
python Gameclip-SNA/scripts/test_sync_endpoint.py https://script.google.com/macros/s/.../exec
```

期望：GET 返回 `{"ok": true, "message": ..., "spreadsheetUrl": ...}`；
POST 返回 `{"ok": true, "updated": 0, "appended": 1, "spreadsheetUrl": ...}`，
并在 Google 云端硬盘里出现《Gameclip labels》表格（工作表 `labels`）。
（测试行 annotator=test / clip_id=__probe__，用完手动删掉即可。）

## 3. 发给标注员（每人一次）

- 打开自己的标注页（如 `https://banford74.github.io/Gameclip-SNA/?a=2`）
- 在「同步地址」输入框粘贴上面的 `/exec` URL → 回车（存在其浏览器 localStorage）
- 或直接发带参数的链接（一次搞定）：
  `https://banford74.github.io/Gameclip-SNA/?a=2&sync=https%3A%2F%2Fscript.google.com%2Fmacros%2Fs%2Fxxx%2Fexec`
- 之后每次保存都会自动回传；点「💾 存档并回传」= 立即回传一次；右上角显示「已同步 时间（N 条）」

## 4. 让进度汇总页自动刷新

1. 打开 Google 表格《Gameclip labels》→ 文件 → 共享 → **发布到网络**
2. 选工作表 `labels`、格式 **CSV** → 发布 → 复制链接
3. 打开 `https://banford74.github.io/Gameclip-SNA/progress.html?data=<CSV链接>`（收藏，20 秒自动刷新）

> 注意：发布到网络的 CSV 有几分钟缓存，进度页显示的可能是几分钟前的数据，属正常。

## 5. 安全与配额

- 拿到 URL 的人都能写入（无鉴权）——只发给 4 个标注员，不要公开
- Apps Script 免费配额：每天执行时间足够 4 人（每次保存 1 次执行）；URL 抓取配额充裕
- 数据只存在你的 Google 表格里；需要备份就直接下载 Sheet

---

## 备选方案（不用也能跑）

- **A 本机同步服务**：`python Gameclip-SNA/scripts/sync_server.py`，标注员开 `http://<本机IP>:8787/?a=N`
  （必须从该地址打开，https 页面 POST 到 http 局域网地址会被浏览器拦）
- **C 不配置**：每人点「存档并回传」自动下载 CSV，发回负责人合并（`scripts/merge_labels.py`）
