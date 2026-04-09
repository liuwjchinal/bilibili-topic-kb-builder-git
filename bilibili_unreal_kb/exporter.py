from __future__ import annotations

import json
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .models import VideoRecord
from .packs import PackDefinition, get_pack

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None

WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"


def _humanize_total_duration(total_seconds: int) -> str:
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}小时{minutes}分{seconds}秒"
    if minutes:
        return f"{minutes}分{seconds}秒"
    return f"{seconds}秒"


def _normalize_records(records: list[VideoRecord]) -> list[VideoRecord]:
    return [record for record in records if record.status != "filtered_irrelevant"]


def build_frontend_payload(
    records: list[VideoRecord],
    *,
    pack: PackDefinition | None = None,
    snapshot_meta: dict | None = None,
) -> dict:
    resolved_pack = pack or get_pack()
    relevant_records = _normalize_records(records)
    categories: dict[str, list[VideoRecord]] = defaultdict(list)
    uploaders: set[str] = set()
    for record in relevant_records:
        categories[record.primary_category].append(record)
        if record.uploader:
            uploaders.add(record.uploader)

    category_rows = []
    for category, items in categories.items():
        total_duration = sum(item.duration_seconds for item in items)
        category_rows.append(
            {
                "name": category,
                "count": len(items),
                "total_duration_seconds": total_duration,
                "total_duration_text": _humanize_total_duration(total_duration),
            }
        )
    category_rows.sort(key=lambda item: (-item["count"], item["name"]))

    videos = [
        record.to_json_dict()
        for record in sorted(
            relevant_records,
            key=lambda item: (item.primary_category, -item.play_count, item.title),
        )
    ]

    total_duration = sum(item.duration_seconds for item in relevant_records)
    return {
        "pack": {
            "slug": resolved_pack.slug,
            "display_name": resolved_pack.display_name,
            "description": resolved_pack.description,
            "domain_key": resolved_pack.domain.key,
            "domain_label": resolved_pack.domain.display_name,
        },
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "summary": {
            "total_videos": len(relevant_records),
            "total_categories": len(categories),
            "total_uploaders": len(uploaders),
            "total_duration_seconds": total_duration,
            "total_duration_text": _humanize_total_duration(total_duration),
        },
        "categories": category_rows,
        "videos": videos,
        "snapshot": snapshot_meta or {},
    }


def _write_web_viewer(payload: dict, output_dir: Path) -> str:
    web_dir = output_dir / "web"
    web_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(WEBAPP_DIR / "index.html", web_dir / "index.html")
    shutil.copy2(WEBAPP_DIR / "styles.css", web_dir / "styles.css")
    shutil.copy2(WEBAPP_DIR / "app.js", web_dir / "app.js")
    data_script = "window.__BILIBILI_KB_DATA__ = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n"
    (web_dir / "data.js").write_text(data_script, encoding="utf-8")
    return str(web_dir / "index.html")


def export_catalog(
    records: list[VideoRecord],
    output_dir: Path,
    *,
    pack: PackDefinition | None = None,
    snapshot_meta: dict | None = None,
) -> dict[str, str]:
    relevant_records = _normalize_records(records)
    rows = [record.to_export_row() for record in relevant_records]
    rows.sort(key=lambda row: (row["primary_category"], -int(row["play_count"])))
    jsonl_path = output_dir / "videos.jsonl"
    csv_path = output_dir / "videos.csv"
    xlsx_path = output_dir / "videos.xlsx"
    markdown_path = output_dir / "index.md"

    if pd is None:  # pragma: no cover
        raise RuntimeError("missing pandas; run `pip install -r requirements.txt` first")

    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path.write_text(
        "\n".join(json.dumps(record.to_json_dict(), ensure_ascii=False) for record in relevant_records),
        encoding="utf-8",
    )
    dataframe = pd.DataFrame(rows)
    dataframe.to_csv(csv_path, index=False, encoding="utf-8-sig")
    dataframe.to_excel(xlsx_path, index=False)
    markdown_path.write_text(build_markdown_index(relevant_records, pack=pack), encoding="utf-8")
    payload = build_frontend_payload(relevant_records, pack=pack, snapshot_meta=snapshot_meta)
    web_index_path = _write_web_viewer(payload, output_dir)
    return {
        "csv": str(csv_path),
        "xlsx": str(xlsx_path),
        "jsonl": str(jsonl_path),
        "index": str(markdown_path),
        "web_index": web_index_path,
    }


def build_markdown_index(records: list[VideoRecord], *, pack: PackDefinition | None = None) -> str:
    resolved_pack = pack or get_pack()
    relevant_records = _normalize_records(records)
    categories: dict[str, list[VideoRecord]] = defaultdict(list)
    for record in relevant_records:
        categories[record.primary_category].append(record)

    lines: list[str] = [f"# {resolved_pack.display_name} 视频知识库索引", ""]
    lines.append(f"- Pack: `{resolved_pack.slug}`")
    lines.append(f"- 视频总数：{len(relevant_records)}")
    lines.append(f"- 总时长：{_humanize_total_duration(sum(record.duration_seconds for record in relevant_records))}")
    lines.append("")

    for category, items in sorted(categories.items(), key=lambda item: (-len(item[1]), item[0])):
        items.sort(key=lambda record: (-record.play_count, record.title))
        total_duration = sum(record.duration_seconds for record in items)
        lines.append(f"## {category}")
        lines.append(f"- 数量：{len(items)}，总时长：{_humanize_total_duration(total_duration)}")
        for record in items[:8]:
            lines.append(
                f"- [{record.title}]({record.link}) | UP主：{record.uploader} | "
                f"时长：{record.duration_text} | 播放：{record.play_count}"
            )
        lines.append("")
    return "\n".join(lines).strip() + "\n"
