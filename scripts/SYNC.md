# 进度同步（已内置默认端点，开箱即用）

## 0. 现状（2026-11-27）

- **同步地址已内置到标注页**（`make_annotator.py` 的 `DEFAULT_SYNC`），总链接和 `?a=N` 链接都自动回传，
  不需要每个人再配置。
- 端点：`https://script.google.com/macros/s/AKfycbzHkV6B6xXSp6S_DyoJFZM3PWOQY2oZVD0uwbyNrOLtfymoc9sZHgsPuyOrCkKzA1qQmA/exec`
- 数据表：https://docs.google.com/spreadsheets/d/1mDYOaQtzTm6qOseEsgs_IW093fDYbfhSTr9vzr5CuIc/edit （工作表 `labels`）
- 已验证：标注 → 自动 POST → Sheet 行数增长；点「💾 存档并回传」可立即强制回传一次。

## 1. 标注页怎么用

- 总链接：`https://banford74.github.io/Gameclip-SNA/`（默认标注员 1）
- 分工链接：`?a=1` / `?a=2` / `?a=3` / `?a=4`
- 每次改动自动存本地（localStorage）+ 自动回传（防抖 1.2 秒）；「💾 存档并回传」= 立即回传并显示结果

## 2. 进度汇总页（自动刷新）

**方式一（推荐，需先重新部署一次 v2 脚本）**：脚本已加 `?format=csv` 输出，进度页直接读端点：

```
https://banford74.github.io/Gameclip-SNA/progress.html?data=<exec URL>?format=csv
```

> 重新部署方法：打开 Apps Script 项目 → 用仓库里最新的 `scripts/sync_endpoint.gs` 覆盖保存 →
> 部署 → 管理部署 → 编辑（铅笔）→「版本」选**新版本** → 部署。然后上面的链接即可自动刷新（20 秒）。

**方式二（不用重新部署）**：Google 表格 → 文件 → 共享 → 发布到网络 → 选 `labels` 工作表 CSV → 链接贴进
`progress.html?data=<CSV链接>`（有几分钟缓存）。

## 3. 验证

```bash
python Gameclip-SNA/scripts/test_sync_endpoint.py <exec URL>
```

期望 GET 返回 `{"ok": true, "spreadsheetUrl": ...}`；POST 返回 `{"ok": true, "updated": 0, "appended": 1}`。

## 4. 备选（不用也能跑）

- 本机同步服务：`python Gameclip-SNA/scripts/sync_server.py`（标注员开 `http://<本机IP>:8787/?a=N`）
- 不配置：点「存档并回传」自动下载 CSV，发回负责人合并（`scripts/merge_labels.py`）

## 5. 安全

- 拿到端点 URL 的人都能写入（无鉴权）——只发给 4 个标注员；如泄露可在 Apps Script 重新部署换 URL
  （页面里的 `DEFAULT_SYNC` 需要同步更新）。

