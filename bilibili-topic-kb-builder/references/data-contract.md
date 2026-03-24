# 数据契约

## 记录字段

JSONL 记录默认包含：

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

`status` 最少支持：

- `ok`
- `needs_review`
- `filtered_irrelevant`

## 网页数据结构

`web/data.js` 默认写成：

```js
window.__BILIBILI_KB_DATA__ = {
  generated_at: "...",
  summary: {
    total_videos: 0,
    total_categories: 0,
    total_uploaders: 0,
    total_duration_seconds: 0,
    total_duration_text: "..."
  },
  categories: [
    {
      name: "基础入门",
      count: 10,
      total_duration_seconds: 0,
      total_duration_text: "..."
    }
  ],
  videos: [ /* JSONL 记录数组 */ ]
}
```

## 导出原则

- JSONL 是唯一源
- CSV/XLSX/Markdown/网页都从 JSONL 派生
- 网页层不要再做额外抓取
- 前端只负责展示、筛选和跳转
