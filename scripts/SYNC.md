# 进度同步（可选）与「同步地址」说明

## 「同步地址」是什么

标注页每次保存（或点「💾 存档并回传」）会把**该标注员的全量标注**打包成 JSON
`{annotator, saved_at, count, labels:{clip_id: {stance, p_codes, ...}}}`，
POST 到一个 HTTPS/HTTP 端点。这个端点负责把数据**存到共享介质**（Google Sheet / 本机文件），
它就是「同步地址」。没有端点时，按钮自动退化为「导出 CSV」。

**我们现在没有**——需要一个一次性部署（见下面方案 A/B）。不配置也能用，就是每人点一下导出 CSV、发回负责人。

---

## 方案 A — 本机同步服务（零账号，推荐同 WiFi/同 Tailscale 的情况）

本仓库自带 `scripts/sync_server.py`：

```bash
python Gameclip-SNA/scripts/sync_server.py          # 监听 0.0.0.0:8787
```

- 标注员打开：`http://<本机IP>:8787/?a=1`（`?a=2..4`）——**注意必须从这个地址打开**，
  不能从 GitHub Pages（https）打开：https 页面 POST 到 http 局域网地址属于混合内容，浏览器会拦。
- 进度汇总：`http://<本机IP>:8787/progress.html?data=labels.csv`（同源，每 20 秒自动刷新）
- 数据落在 `D:/ua_data/annotations_sync.json`，`/labels.csv` 随时可导出
- 本机 IP：同一 WiFi 用 `10.32.92.208`；Tailscale 用 `100.92.131.96`
- 前提：这台电脑开着，标注员网络可达（同网段或同一 Tailscale 网络）

可选：Tailscale 用户可 `tailscale serve https / http://127.0.0.1:8787` 拿到合法的 https 地址，
这样即使从 Pages 打开也能回传（跨网络也安全）。

## 方案 B — Google Apps Script（跨网络、需 Google 账号，约 5 分钟）

1. https://script.google.com → 新建项目 → 粘贴 `scripts/sync_endpoint.gs` → 保存
2. 部署 → 新建部署 → Web 应用；执行身份＝我；访问权限＝任何人 → 复制 `.../exec` URL
3. 每个标注员在标注页「同步地址」粘贴一次（存其浏览器；或发 `?sync=<URL>` 链接）
4. 进度页：Sheet → 文件 → 共享 → 发布到网络 → `labels` 工作表 CSV → 链接贴进
   `progress.html?data=<CSV链接>` → 自动刷新

## 方案 C — 不配置（最省事）

每人点「💾 存档并回传」→ 自动下载 `human_labels_aN_日期.csv` → 发回负责人。
负责人用 `scripts/merge_labels.py` 合并（支持多人重复标注的 κ 统计）。

## 数据口径

- 每个 `(annotator, clip_id)` 只保留一次；写入/汇总都按 `annotated_at` 取最新
- 进度 = 该标注员名下已标注数 / 分到数（551/550/550/550）
- κ 需要重叠：当前分工互不重叠，只有人为让两人标同一批（如 gold set 30 条）时才会出现
