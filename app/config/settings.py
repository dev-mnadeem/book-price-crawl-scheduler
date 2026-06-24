from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Mongo
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "books_monitor"

    # Crawl target and behavior
    base_url: str = "https://books.toscrape.com"
    concurrency: int = 12
    request_timeout: int = 20  # seconds
    max_retries: int = 3
    user_agent: str = "BooksMonitorBot/1.0 (+https://example.com/bot)"

    # API (as plain string from env, e.g., "key1,key2" or JSON array)
    api_keys: str = "dev-key-1"
    rate_limit_per_hour: int = 100

    # Logging
    log_level: str = "INFO"
    logs_dir: str = "logs"

    # Scheduler
    scheduler_cron: str = "0 2 * * *"  # daily at 02:00
    scheduler_interval_seconds: Optional[int] = None  # if set, use interval trigger instead of cron
    scheduler_run_on_start: bool = True  # run one job immediately on startup
    run_scheduler_in_api: bool = True  # start APScheduler inside FastAPI app by default

    # Reports
    report_dir: str = "reports"

    # Redis
    redis_url: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def api_keys_list(self) -> List[str]:
        s = (self.api_keys or "").strip()
        if not s:
            return []
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if str(x).strip()]
            except Exception:
                pass
        return [p.strip() for p in s.split(",") if p.strip()]

    @property
    def logs_path(self) -> Path:
        return Path(self.logs_dir)

    @property
    def reports_path(self) -> Path:
        return Path(self.report_dir)


settings = Settings()
