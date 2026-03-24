from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _to_float(value: str | None, default: float) -> float:
    if not value:
        return default
    return float(value)


def _to_int(value: str | None, default: int) -> int:
    if not value:
        return default
    return int(value)


@dataclass
class AppConfig:
    output_dir: Path = Path("./output")
    pages: int = 2
    timeout: float = 20.0
    detail_connect_timeout: float = 5.0
    detail_read_timeout: float = 8.0
    min_delay: float = 1.2
    max_delay: float = 2.8
    max_retries: int = 3
    detail_workers: int = 6
    browser_fallback: bool = False
    browser_headless: bool = True
    browser_debug_url: str = ""
    node_bin: str = "node"
    keywords_file: Optional[Path] = None
    cookie: str = ""
    since: Optional[date] = None
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    )
    request_headers: dict[str, str] = field(default_factory=dict)

    @property
    def state_dir(self) -> Path:
        return self.output_dir / "state"

    @property
    def runs_dir(self) -> Path:
        return self.output_dir / "runs"

    @property
    def catalog_jsonl_path(self) -> Path:
        return self.output_dir / "unreal_tutorials.jsonl"

    @property
    def catalog_csv_path(self) -> Path:
        return self.output_dir / "unreal_tutorials.csv"

    @property
    def catalog_xlsx_path(self) -> Path:
        return self.output_dir / "unreal_tutorials.xlsx"

    @property
    def markdown_index_path(self) -> Path:
        return self.output_dir / "index.md"

    def ensure_directories(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)


def load_config(
    output_dir: str | None = None,
    pages: int | None = None,
    keywords_file: str | None = None,
    browser_fallback: bool | None = None,
    since: str | None = None,
) -> AppConfig:
    if load_dotenv is not None:
        load_dotenv()

    env = os.environ
    resolved_since = since or env.get("BILIBILI_SINCE")
    config = AppConfig(
        output_dir=Path(output_dir or env.get("BILIBILI_OUTPUT_DIR", "./output")),
        pages=pages if pages is not None else _to_int(env.get("BILIBILI_PAGES"), 2),
        timeout=_to_float(env.get("BILIBILI_REQUEST_TIMEOUT"), 20.0),
        detail_connect_timeout=_to_float(env.get("BILIBILI_DETAIL_CONNECT_TIMEOUT"), 5.0),
        detail_read_timeout=_to_float(env.get("BILIBILI_DETAIL_READ_TIMEOUT"), 8.0),
        min_delay=_to_float(env.get("BILIBILI_REQUEST_MIN_DELAY"), 1.2),
        max_delay=_to_float(env.get("BILIBILI_REQUEST_MAX_DELAY"), 2.8),
        max_retries=_to_int(env.get("BILIBILI_MAX_RETRIES"), 3),
        detail_workers=_to_int(env.get("BILIBILI_DETAIL_WORKERS"), 6),
        browser_fallback=(
            browser_fallback
            if browser_fallback is not None
            else _to_bool(env.get("BILIBILI_BROWSER_FALLBACK"), False)
        ),
        browser_headless=_to_bool(env.get("BILIBILI_BROWSER_HEADLESS"), True),
        browser_debug_url=env.get("BILIBILI_BROWSER_DEBUG_URL", ""),
        node_bin=env.get("BILIBILI_NODE_BIN", "node"),
        keywords_file=Path(keywords_file or env["BILIBILI_KEYWORDS_FILE"])
        if keywords_file or env.get("BILIBILI_KEYWORDS_FILE")
        else None,
        cookie=env.get("BILIBILI_COOKIE", ""),
        since=date.fromisoformat(resolved_since) if resolved_since else None,
    )
    config.request_headers = {
        "User-Agent": config.user_agent,
        "Referer": "https://www.bilibili.com/",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if config.cookie:
        config.request_headers["Cookie"] = config.cookie
    if config.max_delay < config.min_delay:
        config.max_delay = config.min_delay
    if config.detail_workers < 1:
        config.detail_workers = 1
    return config
