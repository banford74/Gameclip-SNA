# 抖音下载 Playbook：登录墙 / 风控下的降级链

> 适用：买量素材、达人内容、竞品视频的批量取数（本项目 2000 对语料备料）。
> 结论先行：**无登录、无 Cookie 的首选路径是「移动端 feed 接口 + CDN 直链」**；登录墙/强风控时才上「浏览器 CDP 接管」。
> 实测记录：2026-11-20，`/video/7709870849365478116` 用 P0 路径一次成功（3.45MB / 826×576 / 31.2s）。

---

## 一、先认信号：遇到的是哪种拦

| 现象 | 判定 | 对应解法 |
|---|---|---|
| 页面 HTML 200 但 `<body></body>` 为空，带 `var glb;_$jsvmprt=...` 混淆 JS | 服务端渲染被反爬壳挡（2026-11 起常见） | 不走页面解析，走 P0 |
| HTML 里搜不到 `play_addr` | 视频数据不落 SSR，走接口 | P0 / P3 |
| yt-dlp 报 `Fresh cookies are needed` | extractor 要新鲜 `ttwid/msToken/odin_tt`（**不是登录态**） | P2 不稳 → P0 |
| feed 接口 403 / `aweme_list` 空 / `status_code≠0` | 接口风控（UA/Referer/频率） | 换 UA+Referer、降频、换 CDN；仍失败 → P3 |
| 页面弹扫码登录、评论区不可见 | 登录墙 | P3（浏览器真实会话） |
| 视频 CDN 直链 403 | 缺 Referer 或链接过期（带签名） | 补 `Referer: https://www.douyin.com/`；重新取链接 |

---

## 二、方法阶梯（按可靠性降序）

### P0 · 移动端 feed 接口（无登录，首选）✅ 实测可用

```
aweme_id → https://aweme.snssdk.com/aweme/v1/feed/?aweme_id=<ID>&aid=1128&version_code=290100&device_platform=android&os_version=13
         → JSON.aweme_list[]（按 aweme_id 精确匹配）
         → video.bit_rate[] 按 bit_rate 降序取最高档
         → play_addr.url_list（3–4 个 CDN 域名）
         → 下载（Android UA + Referer）→ 落盘
```

**四个必守细节**（踩过的坑）：

1. **id 核对**：feed 会带回 7 条推荐位；必须 `aweme_list.find(x => x.aweme_id === ID)`，**禁止取 `[0]`**——否则会存成别的视频（本次实测列表 7 条、目标在第 1 位，但顺序不保证）。
2. **选档**：按 `bit_rate` 降序取最高档，而不是 `play_addr.url_list[0]`（后者常是低码率/水印版本）。
3. **下载头**：`User-Agent: com.ss.android.ugc.aweme/290100 (Linux; U; Android 13; zh_CN)` + `Referer: https://www.douyin.com/`（缺 Referer 常 403）。
4. **多 CDN 轮换**：url_list 里通常有 3–4 个域名（如 `v5-gz-a.douyinvod.com`），逐个重试，全部失败才放弃。

**脚本**：`_probe/dl_mobile.js <id|url|短链> [outdir]`（可复用；同时输出 `*.meta.json`：desc/时长/作者/BGM/互动数）。
**短链**（`v.douyin.com/xxx`）：脚本内自动跟随跳转，从最终 URL 或 HTML 正则 `/video/(\d+)` 取 id。

### P1 · 页面渲染数据（RENDER_DATA / `_ROUTER_DATA`）⚠️ 2026-11 已基本失效

原理：老版抖音页面把视频 JSON 内嵌在 HTML（`window._ROUTER_DATA`）。本次实测：**返回空 body + 反爬壳 JS，`play_addr` 零命中**。仅在极老缓存页/第三方镜像上偶发可用，不作主路径。

### P2 · yt-dlp（`download_media.py`）⚠️ 依赖新鲜 Cookie，受限环境不稳

```powershell
python <skill>\scripts\download_media.py "<url>" -o out
```

- 需要 `ttwid / msToken / odin_tt` 组合的新鲜 Cookie（**无需登录**），单给一个字段仍会被拦；
- `--cookies-from-browser` 在本机基本不可行：浏览器运行期 Cookie DB 被锁 + Chrome v20 app-bound 加密，外部无法解密（**不要在这条路上耗时间**）；
- 结论：P2 作辅助，不做主路径。

### P3 · 浏览器 CDP 接管（登录墙/强风控的兜底）✅

真实浏览器会话，天然携带 Cookie/登录态/风控指纹：

```powershell
# 1) 先完全退出 Edge，再以调试端口启动（脚本：_probe/start-browser-debug.cmd）
start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\Microsoft\Edge\User Data" --remote-allow-origins=* "https://www.douyin.com/"

# 2) 验证端口
curl http://127.0.0.1:9222/json/version

# 3) 抓评论（同一套 CDP 通道）：DOM 滚动抓取，避免评论接口签名
node _probe/scrape_via_cdp.js "<video_url>" skilltest/comments
```

- CDP 也能取视频流：页面里 `document.querySelector('video').src` / Performance 日志里的 `douyinvod` 请求，再走 P0 的直链下载逻辑；
- **评论接口** `aweme/v1/comment/list/` 需要签名（直接调返回空列表）→ 评论只能走这条 DOM 抓取线。

### P4 · 短链解析（并入 P0）

`v.douyin.com/xxx` / `iesdouyin.com/share/video/xxx` → 跟随 302 取 `aweme_id` → 走 P0。

---

## 三、决策树

```
URL 进来
 ├─ 能否拿到 aweme_id？（数字/URL/短链跳转）
 │    └─ 否 → P3 浏览器打开，从网络面板/页面变量取
 ├─ 先跑 P0（feed 接口）──成功 → 下载最高码率档 ✅
 │        └─ 失败：403/空列表 → 降频重试 1 次（换 UA）→ 仍失败 →
 ├─ P2 yt-dlp（有新鲜 cookie 时）──成功 → 下载
 │        └─ 失败（Fresh cookies）→ 不纠缠 →
 └─ P3 CDP 接管：真实浏览器取流（登录墙/强风控兜底）
       └─ 仍失败：向用户说明平台限制，不反复重试
```

---

## 四、批量与合规注意

- **频率**：单条间隔 ≥2s；2000 条按 10 条/分钟估算 ≈ 3.3 小时，夜间跑批；
- **失败重试**：同一条路失败 2 次即换路，不原地重试（风控会累加）；
- **Cookie**：不落盘、不跨会话复用；不实现登录态自动登录；
- **只取公开分发流**（`play_addr`），不逆向评论接口签名；
- **数据留痕**：每条落 `*.meta.json`（id/desc/时长/作者/互动数），便于核对"素材对不上"这类问题。

---

## 五、本次实测（2026-11-20）

| 步骤 | 结果 |
|---|---|
| 输入 | `https://www.douyin.com/video/7709870849365478116` |
| P0 feed | 200 / status_code=0 / list=7 / 目标命中 |
| 选档 | `540_2_1` 826×576 885kbps（仅 1 档） |
| 下载 | `v5-gz-a.douyinvod.com` 首个域名即成功，3.45MB |
| ffprobe | 31.23s / 826×576 / HEVC / 30fps / 3.5MB ✅ |
| 元数据 | 作者「轩白」；和平精英地铁逃生；赞 9.28w / 评 8553 / 转 9909 / 藏 9545 |
| P1 对照 | 页面 HTML 72KB 空 body + 反爬壳，`play_addr` 无命中 |

## 六、代码位置

| 用途 | 路径 |
|---|---|
| 无登录下载（参考实现） | `_probe/dl_mobile.js` |
| 批量（旧版，双视频） | `_probe/dl.js` |
| skill 下载（yt-dlp 封装） | 桌面 skill `scripts/download_media.py` |
| CDP 启动 | `_probe/start-browser-debug.cmd` |
| CDP 抓评论 | `_probe/scrape_via_cdp.js` |
| pipeline 桥接兜底 | `pipeline/skill_bridge.py` → `UAVideo.download_douyin()` |
| skill 官方环境指南 | skill `ENVIRONMENT-NOTES.md`（本 playbook 的 P0 部分已同步进该文档） |
