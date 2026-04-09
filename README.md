# B站虚幻引擎教程知识库爬虫

一个面向“可重复更新”的本地批处理工具，用于采集 B 站虚幻引擎相关视频，完成去重、分类、增量更新、断点续跑和多格式导出。

## 当前实现

- 主题搜索主链路已经改为纯 Python 解析搜索页内嵌状态，不再依赖 Node.js。
- 视频详情与标签补采仍走 Python HTTP 请求，遇到字段缺失时按需补齐。
- 空间抓取默认优先使用 `yt_dlp` Python API 获取 BV 列表。
- 若空间页需要登录态或站点风控更严格，可通过已登录 Chrome 的 `debug port` 走浏览器接管。
- 所有导出物以 `JSONL` 为主数据源，同步生成 `CSV`、`XLSX`、`Markdown` 和本地静态网页。

## 安装

```bash
pip install -r requirements.txt
```

可选浏览器能力：

```bash
pip install -r requirements-optional.txt
playwright install chromium
```

## 配置

复制 [`.env.example`](/D:/UnrealGit/Skills/unreal-source-analyzer/bilibili-topic-kb-builder-git/.env.example) 为 `.env` 后按需修改。

常用配置：

- `BILIBILI_OUTPUT_DIR`：输出目录
- `BILIBILI_PAGES`：每个关键词抓取页数
- `BILIBILI_REQUEST_TIMEOUT`：搜索页请求超时
- `BILIBILI_REQUEST_MIN_DELAY` / `BILIBILI_REQUEST_MAX_DELAY`：请求间隔抖动
- `BILIBILI_MAX_RETRIES`：通用重试次数
- `BILIBILI_DETAIL_WORKERS`：详情补采并发数
- `BILIBILI_DETAIL_CONNECT_TIMEOUT` / `BILIBILI_DETAIL_READ_TIMEOUT`：详情接口超时
- `BILIBILI_BROWSER_FALLBACK`：主题搜索失败时是否启用 Playwright 兜底
- `BILIBILI_BROWSER_DEBUG_URL`：空间抓取时接管已登录 Chrome 的 CDP 地址
- `BILIBILI_KEYWORDS_FILE`：自定义关键词文件，一行一个
- `BILIBILI_COOKIE`：详情接口或搜索页需要时的 Cookie
- `BILIBILI_SINCE`：仅保留不早于该日期的视频，格式 `YYYY-MM-DD`

## 用法

### 1. 主题搜索抓取

```bash
python bilibili_crawler.py run --pages 2
```

单关键词 smoke run：

```bash
python bilibili_crawler.py run --keyword UE5 --pages 1 --orders default
```

### 2. 继续未完成任务

```bash
python bilibili_crawler.py resume
```

### 3. 根据现有 JSONL 重新导出

```bash
python bilibili_crawler.py export
```

### 4. 环境探针

```bash
python bilibili_crawler.py validate
```

### 5. 抓取 UP 主空间

默认优先使用 `yt_dlp` Python API 抓取空间播放列表：

```bash
python bilibili_crawler.py space --space-url https://space.bilibili.com/138827797/video --uploader-name "虚幻引擎官方"
```

如果你已经打开并登录了 Chrome，且以远程调试端口启动，可直接接管浏览器抓取空间页：

```bash
python bilibili_crawler.py space ^
  --space-url https://space.bilibili.com/138827797/video ^
  --uploader-name "虚幻引擎官方" ^
  --browser-debug-url http://127.0.0.1:9222 ^
  --refresh-playlist ^
  --detail-workers 8
```

推荐的 Chrome 启动方式：

```bash
chrome.exe --remote-debugging-port=9222 --user-data-dir=D:\chrome-cdp-profile
```

### 6. 重试空间详情失败 BV

```bash
python bilibili_crawler.py retry-space-failed --uploader-name "虚幻引擎官方"
```

## 输出目录

默认输出到 `output/`：

- `unreal_tutorials.jsonl`
- `unreal_tutorials.csv`
- `unreal_tutorials.xlsx`
- `index.md`
- `web/index.html`
- `space_playlist.json`
- `space_records_checkpoint.jsonl`
- `space_failed_bvids.jsonl`
- `tutorial_only/unreal_tutorials.jsonl`
- `tutorial_only/index.md`
- `tutorial_only/web/index.html`
- `state/seen_videos.json`
- `state/current_run.json`
- `state/last_run.json`
- `runs/<run_id>_summary.json`
- `runs/<run_id>_space_summary.json`
- `runs/<run_id>_retry_space_failed_summary.json`

## 已验证链路

- `run` 主题搜索默认矩阵单页已真实跑通，72 个任务完成。
- `run -> export` 闭环已验证。
- 搜索页解析已改为纯 Python，并通过真实页面解析验证。
- `space` 的 `yt_dlp` 已切为 Python API，但真实网络环境下仍可能遇到站点侧 `SSL EOF`、风控或登录态限制。

## 当前风险

- B 站详情接口仍可能返回 `412`、超时或字段缺失，因此详情补采不能视为稳定接口。
- 空间抓取依赖 `yt_dlp` 或浏览器登录态，网络波动和站点风控会直接影响成功率。
- 搜索页结构若发生大改，纯 Python 解析器仍需要跟进。

## 入口示例

- 默认网页入口：[output/web/index.html](/D:/UnrealGit/Skills/unreal-source-analyzer/bilibili-topic-kb-builder-git/output/web/index.html)
- 默认汇总目录：[output](/D:/UnrealGit/Skills/unreal-source-analyzer/bilibili-topic-kb-builder-git/output)

