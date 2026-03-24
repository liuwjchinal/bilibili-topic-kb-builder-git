# 架构模板

## 目标形态

构建一个本地批处理工具，支持：

- B 站专题视频采集
- 元数据补全
- 规则分类
- JSONL 主数据源
- 表格、Markdown、静态网页导出
- 增量更新与断点续跑

## 推荐目录

```text
project/
├─ crawler.py
├─ package_or_module/
│  ├─ config.py
│  ├─ planner.py
│  ├─ collector.py
│  ├─ parser.py
│  ├─ normalizer.py
│  ├─ classifier.py
│  ├─ store.py
│  ├─ exporter.py
│  └─ runner.py
├─ tests/
└─ webapp/
```

## CLI 约定

至少保留这些命令：

- `run`
- `resume`
- `export`
- `validate`

常用参数：

- `--pages`
- `--keyword`
- `--keywords-file`
- `--output-dir`
- `--browser-fallback`
- `--since`
- `--orders`

## 状态文件

输出目录建议包含：

- `topic_videos.jsonl`
- `topic_videos.csv`
- `topic_videos.xlsx`
- `index.md`
- `web/index.html`
- `web/data.js`
- `state/current_run.json`
- `state/last_run.json`
- `state/seen_videos.json`
- `runs/<run_id>_summary.json`

## 执行顺序

1. 生成关键词与分页任务
2. 拉取搜索结果页
3. 解析页面内嵌状态
4. 对缺失字段记录做详情补采
5. 做分类、去重和状态标记
6. 写入 JSONL
7. 从 JSONL 导出 CSV/XLSX/Markdown/网页
8. 写入 run summary 和 seen 索引

## 验证清单

- 单关键词单页能抓到记录
- 重复运行不会大面积重复
- `resume` 能跳过已完成任务
- `export` 能从已有 JSONL 重建所有派生文件
- `web/index.html` 可直接打开并展示数据
