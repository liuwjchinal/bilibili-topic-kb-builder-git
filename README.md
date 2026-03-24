# B站虚幻引擎教程知识库爬虫

一个面向“可重复更新”的本地批处理工具，用于采集 B 站虚幻引擎相关教程视频，完成去重、分类、增量更新、断点续跑和多格式导出。

## 功能概览

- 搜索页 HTML 抓取主链路，避免直接依赖高风险搜索接口
- 视频详情与标签补采，提高字段完整度
- 查询矩阵自动生成，默认覆盖 `虚幻引擎 / UE4 / UE5 / Unreal Engine`
- 规则分类器，输出主分类、次分类、命中关键词和置信度
- 增量更新与断点续跑
- 导出 `xlsx`、`csv`、`jsonl`、`Markdown` 和本地静态网页
- 空间抓取支持两种列表来源：
  - `yt-dlp` 获取 UP 主空间 BV 列表
  - 已登录 Chrome 的 `debug port` 接管空间页并抓取 BV 列表
- 空间详情补采支持有限并发，降低全量抓取耗时

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

复制 [`.env.example`](/D:/UnrealGit/Skills/unreal-source-analyzer/.env.example) 为 `.env` 后按需修改。

常用配置：

- `BILIBILI_OUTPUT_DIR`：输出目录
- `BILIBILI_PAGES`：每个关键词抓取页数
- `BILIBILI_REQUEST_MIN_DELAY` / `BILIBILI_REQUEST_MAX_DELAY`：搜索抓取限速抖动
- `BILIBILI_MAX_RETRIES`：通用请求重试次数
- `BILIBILI_DETAIL_WORKERS`：空间详情补采并发数，默认 `6`
- `BILIBILI_DETAIL_CONNECT_TIMEOUT`：详情接口连接超时，默认 `5`
- `BILIBILI_DETAIL_READ_TIMEOUT`：详情接口读取超时，默认 `8`
- `BILIBILI_BROWSER_FALLBACK`：启用搜索页 Playwright 兜底
- `BILIBILI_BROWSER_DEBUG_URL`：已登录 Chrome 的 CDP 地址，例如 `http://127.0.0.1:9222`
- `BILIBILI_KEYWORDS_FILE`：自定义关键词文件，一行一个
- `BILIBILI_SINCE`：仅保留不早于该日期的视频，格式 `YYYY-MM-DD`

## 使用方式

### 1. 关键词搜索抓取

```bash
python bilibili_crawler.py run --pages 2
```

单关键词 smoke run：

```bash
python bilibili_crawler.py run --keyword UE5 --pages 1 --orders default
```

### 2. 断点续跑

```bash
python bilibili_crawler.py resume
```

### 3. 重新导出已有结果

```bash
python bilibili_crawler.py export
```

### 4. 环境校验

```bash
python bilibili_crawler.py validate
```

### 5. 抓取 UP 主空间

默认使用 `yt-dlp` 获取空间列表：

```bash
python bilibili_crawler.py space --space-url https://space.bilibili.com/138827797/video --uploader-name "虚幻引擎官方"
```

如果你已经打开并登录了 Chrome，且用远程调试端口启动了浏览器，可以直接接管该浏览器抓取空间列表：

```bash
python bilibili_crawler.py space ^
  --space-url https://space.bilibili.com/138827797/video ^
  --uploader-name "虚幻引擎官方" ^
  --browser-debug-url http://127.0.0.1:9222 ^
  --refresh-playlist ^
  --detail-workers 8
```

建议的 Chrome 启动方式：

```bash
chrome.exe --remote-debugging-port=9222 --user-data-dir=D:\chrome-cdp-profile
```

说明：

- `--browser-debug-url` 会优先用真实浏览器抓空间页里的 BV 列表
- `--refresh-playlist` 会忽略本地缓存，重新抓一遍空间列表
- `--detail-workers` 用于控制详情补采并发，建议从 `4-8` 开始

## 输出目录

默认输出到 `output/`：

- `unreal_tutorials.xlsx`
- `unreal_tutorials.csv`
- `unreal_tutorials.jsonl`
- `index.md`
- `web/index.html`
- `space_playlist.json`
- `space_records_checkpoint.jsonl`
- `space_failed_bvids.jsonl`
- `state/seen_videos.json`
- `state/current_run.json`
- `state/last_run.json`
- `runs/<run_id>_summary.json`

## 说明

- 搜索抓取当前会遇到 `412`，因此主流程优先使用搜索结果页 HTML 与页面内嵌状态。
- 空间抓取如果直接访问接口被风控，优先使用已登录 Chrome 的 `debug port` 获取空间列表，再低并发补详情。
- 每次 `run`、`export` 或 `space` 成功后，都会同步生成静态网页，可直接打开 [output/web/index.html](/D:/UnrealGit/Skills/unreal-source-analyzer/output/web/index.html) 或对应输出目录下的 `web/index.html` 浏览分类结果。
- 请低频运行，并遵守站点规则与合规要求。
