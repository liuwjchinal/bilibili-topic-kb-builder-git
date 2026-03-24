---
name: bilibili-topic-kb-builder
description: Build, adapt, or review a Bilibili topic video knowledge-base pipeline that searches topic videos, enriches metadata, classifies content, exports CSV/XLSX/JSONL/Markdown, and generates a local static web viewer. Use when Codex needs to create or modify a B站专题爬虫/知识库工具，补充断点续跑、增量更新、规则分类、网页展示，或把现有实现抽成可复用模板。
---

# Bilibili Topic KB Builder

构建一个面向“可重复更新”的 B 站专题视频知识库工具，而不是一次性脚本。

默认目标：

- 低频本地批处理
- HTTP 优先，浏览器兜底
- JSONL 作为主数据源
- 同步导出表格、Markdown 索引和本地静态网页
- 中文总结和可点击文件链接
- 所有文本文件统一使用 UTF-8

## 工作流

### 1. 先界定任务边界

优先确认这些事实：

- 主题词是什么，是否只限单一专题
- 是一次性采集，还是可重复更新工具
- 最终交付需要哪些导出物
- 是否需要网页展示

如果仓库里已经有原型，先复用现有目录和数据格式，不要平行造第二套。

### 2. 用稳定链路设计采集器

优先采用：

1. 搜索结果页 HTML
2. 页面内嵌状态解析
3. 详情接口补全缺失字段
4. 浏览器自动化兜底

不要把脆弱的 HTML 选择器解析当成唯一主链路。

搜索 API 或视频 API 遇到 `412`、限流或字段缺失时：

- 先检查是否能从搜索页内嵌状态直接拿到结果
- 只对缺失记录做详情补采
- 只在确有必要时启用浏览器兜底

在 Windows 上调用 Node 子进程解析页面时，强制使用 UTF-8 读写，避免中文解码失败。

### 3. 按模块拆分项目

默认拆分为这些模块：

- `config`：环境变量、路径、限速、重试
- `planner`：关键词矩阵、分页任务、排序策略
- `collector`：搜索页抓取、详情补采、标签补采、浏览器兜底
- `normalizer`：字段标准化、去重、状态判定
- `classifier`：规则分类、置信度、无关内容过滤
- `store`：断点续跑、失败日志、seen 索引
- `exporter`：CSV/XLSX/JSONL/Markdown/网页导出
- `runner`：CLI 入口和编排

当你需要完整布局、CLI 约定和状态文件规则时，读取 [architecture.md](./references/architecture.md)。

### 4. 固定数据契约

保持 JSONL 为主数据源，其他导出全部从 JSONL 派生。

最低字段集合：

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

当前端或导出字段调整时，读取 [data-contract.md](./references/data-contract.md)。

### 5. 生成网页展示

如果需求包含“网页展示”或“本地浏览页”：

- 直接复用 [webapp](./assets/webapp) 模板
- 在导出阶段生成 `web/data.js`
- 页面直接读取 `window.__BILIBILI_KB_DATA__`
- 默认支持分类筛选、关键词搜索、排序、详情面板、原视频跳转

如果现有项目已经有导出器，把网页生成接到导出链路里，不要另起独立脚本。

### 6. 保证稳定性

默认必须具备：

- 请求间隔随机抖动
- 可恢复状态码重试
- 任务粒度断点续跑
- 失败日志
- `seen_videos` 增量索引
- `needs_review` 质量标记

优先级原则：

1. 先让单关键词单页 smoke run 跑通
2. 再补查询矩阵和去重
3. 再补分类、状态、续跑
4. 最后补网页和浏览器兜底

### 7. 验证

至少执行这三类验证：

- 单元测试：`planner`、`classifier`、`normalizer`、`exporter`
- 环境探针：验证详情接口或当前主链路是否可用
- smoke run：单关键词、单页、默认排序，确认导出物和网页都生成

完成后，优先汇报：

- 关键变更
- 真实验证命令
- 输出入口路径
- 仍然存在的风险

## 资源

### references/

- [architecture.md](./references/architecture.md)：推荐模块边界、CLI、状态文件和验证流程
- [data-contract.md](./references/data-contract.md)：记录级字段和网页 `data.js` 结构

### assets/

- [webapp](./assets/webapp)：静态网页模板
- [env.example](./assets/env.example)：环境变量模板

优先复制模板后再改，不要每次从零重写网页壳子。
