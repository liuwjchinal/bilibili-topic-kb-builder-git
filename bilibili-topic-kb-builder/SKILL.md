---
name: bilibili-topic-kb-builder
description: Build, adapt, or review a Bilibili topic or uploader-space video knowledge-base pipeline that searches topic videos, crawls uploader spaces, enriches metadata, classifies content, retries failed records, exports CSV/XLSX/JSONL/Markdown, and generates a local static web viewer.
---

# Bilibili Topic KB Builder

构建一个面向“可重复更新”的 B 站专题视频知识库工具，而不是一次性脚本。

默认目标：

- 本地低频批处理
- HTTP 优先，浏览器兜底
- JSONL 作为主数据源
- 同步导出表格、Markdown 索引和本地静态网页
- 中文总结和可点击文件链接
- 所有文本文件统一使用 UTF-8

## 强制规则

### 1. 先判定执行场景

- 若用户提供 `space.bilibili.com`、`browser-debug-url`、`retry-space-failed`，优先判定为空间场景。
- 若用户没有给出空间入口，默认走主题搜索 `run` 场景。
- 不要把空间抓取误做成关键词搜索。

### 2. 主题搜索主链路

- 当前主题搜索主链路已经是纯 Python 解析搜索页内嵌状态，不再依赖 Node.js。
- 详情接口遇到 `412`、超时或字段缺失时，只对缺字段记录做补采。
- 只有纯 Python 主链路失败时，才启用 Playwright 搜索兜底。

### 3. 空间抓取主链路

- 空间播放列表默认优先使用 `yt_dlp` Python API。
- 若用户提供 `browser-debug-url`，优先接管已登录 Chrome 抓取空间页。
- 详情补采使用 Python 并发请求，必须保留失败清单和 checkpoint。

### 4. 空间场景交付闭环

- `space` / `retry-space-failed` 场景必须检查这些文件：
  - `space_playlist.json`
  - `space_records_checkpoint.jsonl`
  - `space_failed_bvids.jsonl`
  - `runs/*_space_summary.json` 或 `runs/*_retry_space_failed_summary.json`
  - `unreal_tutorials.jsonl`
  - `index.md`
  - `web/index.html`
- 若生成教程子集，还必须同步生成：
  - `tutorial_only/unreal_tutorials.jsonl`
  - `tutorial_only/index.md`
  - `tutorial_only/web/index.html`

### 5. UTF-8 全链路

- Windows 下所有文本文件必须显式使用 UTF-8。
- 输出 `summary`、`index.md`、`checkpoint`、配置文件后，要回读检查是否出现乱码。

### 6. 回执要求

- 总结默认使用中文。
- 所有本地路径默认用可点击 Markdown 文件链接。
- 回执至少给出：
  - 真实执行命令
  - `summary` 路径
  - 主数据入口
  - 网页入口
  - 残留风险

### 7. 验证要求

- 至少执行单元测试。
- 至少执行与本次场景匹配的一次真实命令。
- 对 `run` 场景至少验证 `run -> export` 闭环。
- 对 `space` 场景至少验证 playlist、checkpoint、export 和失败清单。

## 工作流

### 1. 先界定任务边界

确认：

- 走 `run`、`space` 还是 `retry-space-failed`
- 关键词矩阵或 UP 主空间链接
- 是否需要静态网页
- 最终要哪些导出物

### 2. 模块边界

- `config`：环境变量、路径、限速、重试
- `planner`：关键词矩阵、分页任务、排序策略
- `collector`：搜索页抓取、详情补采、标签补采、浏览器兜底
- `space_collector`：空间列表、详情并发补采、失败记录
- `normalizer`：字段标准化、去重、状态判断
- `classifier`：规则分类、置信度、无关内容过滤
- `store`：断点续跑、失败日志、seen 索引
- `exporter`：CSV/XLSX/JSONL/Markdown/网页导出
- `runner`：CLI 和编排

### 3. 数据契约

以 JSONL 为主数据源，其他导出都从 JSONL 派生。

至少稳定这些字段：

- `video_id`
- `bvid`
- `title`
- `link`
- `duration_seconds`
- `duration_text`
- `uploader`
- `play_count`
- `publish_time`
- `query_keywords`
- `source_pages`
- `primary_category`
- `secondary_categories`
- `category_confidence`
- `match_keywords`
- `tags`
- `desc_excerpt`
- `crawl_time`
- `run_id`
- `status`

若模型里新增字段，例如封面或头像，必须同步验证 `run -> export -> reload -> export` 闭环。

### 4. 网页导出

- 复用 [assets/webapp](./assets/webapp) 模板。
- 在导出阶段生成 `web/data.js`。
- 页面读取 `window.__BILIBILI_KB_DATA__`。

### 5. 风险判断

- 详情接口 `412`、超时、字段缺失
- 空间列表依赖 `yt_dlp` 或浏览器登录态
- 搜索页结构变更导致解析器失效
- JSONL 契约变更导致独立 `export` 失败

## 资源

### references/

- [architecture.md](./references/architecture.md)
- [data-contract.md](./references/data-contract.md)

### assets/

- [webapp](./assets/webapp)
- [env.example](./assets/env.example)

