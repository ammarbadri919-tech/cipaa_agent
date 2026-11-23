"""Persistent paper-position state used by pattern recommendations.

These records track ENTER/EXIT recommendations only. They never place or close
an exchange order.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POSITIONS_FILE = Path(os.getenv("CRYPTOGUARDIAN_POSITIONS_FILE", PROJECT_ROOT / "runtime" / "analysis_positions.json"))
_thread_lock = threading.RLock()


def _read() -> dict[str, dict[str, Any]]:
    try:
        value = json.loads(POSITIONS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    positions = value.get("open_positions", {}) if isinstance(value, dict) else {}
    return positions if isinstance(positions, dict) else {}


def get_open_position(symbol: str) -> dict[str, Any] | None:
    with _thread_lock:
        POSITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with POSITIONS_FILE.with_suffix(".lock").open("a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH)
            try:
                return _read().get(symbol.upper())
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def open_position(symbol: str, direction: str, entry_price: float | None, timeframe: str) -> dict[str, Any]:
    normalized_symbol = symbol.upper()
    with _thread_lock:
        POSITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with POSITIONS_FILE.with_suffix(".lock").open("a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                positions = _read()
                existing = positions.get(normalized_symbol)
                if existing:
                    return existing
                position = {
                    "symbol": normalized_symbol,
                    "direction": direction.upper() if direction else "UNKNOWN",
                    "entry_price": entry_price,
                    "timeframe": timeframe,
                    "opened_at": datetime.now(timezone.utc).isoformat(),
                }
                positions[normalized_symbol] = position
                _write(positions)
                return position
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def close_position(symbol: str, exit_price: float | None, reason: str | None = None) -> dict[str, Any] | None:
    normalized_symbol = symbol.upper()
    with _thread_lock:
        POSITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with POSITIONS_FILE.with_suffix(".lock").open("a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                positions = _read()
                position = positions.pop(normalized_symbol, None)
                if position:
                    position = {
                        **position,
                        "exit_price": exit_price,
                        "closed_at": datetime.now(timezone.utc).isoformat(),
                        "exit_reason": reason,
                    }
                    _write(positions)
                return position
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _write(positions: dict[str, dict[str, Any]]) -> None:
    POSITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix="analysis_positions_", suffix=".json", dir=POSITIONS_FILE.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump({"open_positions": positions}, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_name, POSITIONS_FILE)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
