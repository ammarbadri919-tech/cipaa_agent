"""Small file bridge from the existing long-running agents to FastAPI."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_write_lock = threading.RLock()


def _session_dir() -> Path | None:
    value = os.getenv("CRYPTOGUARDIAN_SESSION_DIR")
    return Path(value) if value else None


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, default=str)
    temporary.replace(path)


def publish_market_result(result: dict[str, Any]) -> None:
    """Publish a real result returned by the existing Market Scanner."""
    directory = _session_dir()
    if directory is None:
        return
    symbol = str(result.get("symbol", ""))
    key = symbol.split("/")[0].upper()
    if not key:
        return
    path = directory / "market.json"
    with _write_lock:
        try:
            current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, json.JSONDecodeError):
            current = {}
        current[key] = result
        _atomic_json(path, current)


def initialize_news_sources() -> None:
    directory = _session_dir()
    if directory is None:
        return
    path = directory / "news_status.json"
    now = datetime.now(timezone.utc).isoformat()
    with _write_lock:
        _atomic_json(path, {
            "rss": {"status": "starting", "updated_at": now},
            "tinyfish": {"status": "scheduled", "updated_at": now},
        })


def publish_news_source(source: str, status: str, error_type: str | None = None) -> None:
    directory = _session_dir()
    if directory is None or source not in {"rss", "tinyfish"}:
        return
    path = directory / "news_status.json"
    with _write_lock:
        try:
            current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, json.JSONDecodeError):
            current = {}
        current[source] = {
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **({"error_type": error_type} if error_type else {}),
        }
        _atomic_json(path, current)
