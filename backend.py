from __future__ import annotations

import asyncio
import csv
import fcntl
import io
import json
import os
import re
import signal
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from agents.orchestrator import graph as orchestrator

PROJECT_ROOT = Path(__file__).resolve().parent
SESSION_ROOT = PROJECT_ROOT / "runtime" / "dashboard_sessions"
PATTERN_REPORT_ROOT = PROJECT_ROOT / "runtime" / "pattern_reports"
CHART_ROOT = PROJECT_ROOT / "charts"
MAX_CSV_BYTES = 5 * 1024 * 1024
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._/-]{0,19}$")
AGENT_KEYS = {
    "market_scanner": "market_results",
    "news_agent": "news_results",
    "pattern_decision": "pattern_results",
}


def parse_watchlist_csv(contents: bytes) -> list[dict[str, str]]:
    """Validate and canonicalize the uploaded CSV for the existing agents."""
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Upload a UTF-8 encoded CSV file.") from exc

    reader = csv.DictReader(io.StringIO(text, newline=""))
    headers = {str(name or "").strip().lower() for name in (reader.fieldnames or [])}
    if not {"coin_name", "symbol"}.issubset(headers):
        raise ValueError("CSV must contain coin_name and symbol columns.")

    # Use case-insensitive header lookup while preserving the original CSV contract.
    name_header = next(name for name in reader.fieldnames or [] if name.strip().lower() == "coin_name")
    symbol_header = next(name for name in reader.fieldnames or [] if name.strip().lower() == "symbol")
    coins: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in reader:
        name = (row.get(name_header) or "").strip()
        symbol = (row.get(symbol_header) or "").strip().upper()
        if not name or not symbol or not SYMBOL_PATTERN.fullmatch(symbol):
            continue
        duplicate_key = symbol.replace("/", "")
        if duplicate_key in seen:
            continue
        seen.add(duplicate_key)
        coins.append({"coin_name": name, "symbol": symbol})

    if not coins:
        raise ValueError("No valid coin rows found in the CSV.")
    return coins


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_symbol(symbol: str) -> str:
    value = symbol.strip().upper()
    if "/" in value:
        return value.split("/", 1)[0]
    for quote in ("USDT", "USDC", "USD"):
        if value.endswith(quote) and len(value) > len(quote):
            return value[:-len(quote)]
    return value


def _safe_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


class MonitoringManager:
    """Single-session supervisor for the existing LangGraph-launched agents."""

    def __init__(self) -> None:
        self.current: dict[str, Any] | None = None
        self.lock = asyncio.Lock()
        self.stop_lock = asyncio.Lock()
        self.launch_task: asyncio.Task[None] | None = None
        self._recover_session()

    def _save_session(self, session: dict[str, Any] | None = None) -> None:
        target = session if session is not None else self.current
        if target is None:
            return
        path = Path(target["session_dir"]) / "session.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(target, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)

    def _recover_session(self) -> None:
        try:
            session_files = sorted(SESSION_ROOT.glob("*/session.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        except OSError:
            return
        live_records: list[dict[str, Any]] = []
        for path in session_files:
            record = _safe_json(path, None)
            if not isinstance(record, dict) or record.get("status") not in {"starting", "running", "paused", "stopping"}:
                continue
            session_id = str(record.get("id", ""))
            if not session_id:
                continue
            session_dir = str(path.parent)
            states = orchestrator.session_process_states(session_id, session_dir)
            live_states = [state["status"] for state in states.values() if state["status"] in {"running", "paused"}]
            if not live_states:
                record["status"] = "error" if record.get("status") not in {"stopping", "stopped"} else "stopped"
                record["error"] = "No live agent processes were found while recovering the previous API session."
                record["updated_at"] = _iso_now()
                self._save_session(record)
                continue
            record["status"] = "paused" if all(state == "paused" for state in live_states) else "running"
            record["session_dir"] = session_dir
            record["csv_path"] = str(path.parent / "watchlist.csv")
            live_records.append(record)
        if live_records:
            self.current = live_records[0]
            self._save_session(self.current)
            # If more than one prior session survived an unclean API exit,
            # keep the newest and stop the extras before accepting new starts.
            for duplicate in live_records[1:]:
                orchestrator.stop_session(duplicate["id"])
                duplicate["status"] = "stopped"
                duplicate["updated_at"] = _iso_now()
                duplicate.setdefault("events", []).insert(0, {
                    "timestamp": duplicate["updated_at"],
                    "action": "stopped",
                    "coin_count": len(duplicate.get("coins", [])),
                })
                self._save_session(duplicate)

    def _write_watchlist(self, path: Path, coins: list[dict[str, str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=["coin_name", "symbol"])
            writer.writeheader()
            writer.writerows(coins)

    def _has_persisted_active_session(self) -> bool:
        now = time.time()
        try:
            files = SESSION_ROOT.glob("*/session.json")
            for path in files:
                record = _safe_json(path, None)
                if not isinstance(record, dict) or record.get("status") not in {"starting", "running", "paused", "stopping"}:
                    continue
                if self.current and record.get("id") == self.current.get("id"):
                    continue
                session_id = str(record.get("id", ""))
                if not session_id:
                    continue
                states = orchestrator.session_process_states(session_id, str(path.parent))
                if any(state["status"] in {"running", "paused"} for state in states.values()):
                    return True
                if record.get("status") in {"starting", "stopping"} and now - path.stat().st_mtime < 60:
                    return True
        except OSError:
            return True
        return False

    def _public_session(self, session: dict[str, Any] | None = None) -> dict[str, Any] | None:
        target = session if session is not None else self.current
        if target is None:
            return None
        process_map = orchestrator.session_process_states(target["id"], target.get("session_dir"))
        agents: dict[str, dict[str, Any]] = {}
        launch_report = target.get("launch_report", {})
        for public_name, result_key in AGENT_KEYS.items():
            process = process_map.get(result_key)
            if process is None:
                launch_item = launch_report.get(public_name, {})
                state = "error" if launch_item.get("status") == "failed" else "starting"
                detail = launch_item.get("error") or "Agent launch is pending."
            elif process["status"] in {"running", "paused"}:
                state = process["status"]
                detail = "Existing agent process is active."
            else:
                state = "stopped" if target["status"] in {"stopping", "stopped"} else "error"
                detail = "Agent process exited."
            agents[public_name] = {"status": state, "detail": detail}

        return {
            "id": target["id"],
            "status": target["status"],
            "started_at": target["started_at"],
            "updated_at": target["updated_at"],
            "error": target.get("error"),
            "coins": target["coins"],
            "agents": agents,
            "events": target["events"],
        }

    async def start(self, coins: list[dict[str, str]]) -> dict[str, Any]:
        async with self.lock:
            SESSION_ROOT.mkdir(parents=True, exist_ok=True)
            lock_path = SESSION_ROOT / ".monitoring.lock"
            with lock_path.open("a+") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    if self.current and self.current["status"] in {"starting", "running", "paused", "stopping"}:
                        raise HTTPException(status_code=409, detail="A monitoring session is already active.")
                    if self._has_persisted_active_session():
                        raise HTTPException(status_code=409, detail="A monitoring session is already active in another API worker.")

                    session_id = uuid.uuid4().hex
                    session_dir = SESSION_ROOT / session_id
                    csv_path = session_dir / "watchlist.csv"
                    self._write_watchlist(csv_path, coins)
                    now = _iso_now()
                    self.current = {
                        "id": session_id,
                        "status": "starting",
                        "started_at": now,
                        "updated_at": now,
                        "csv_path": str(csv_path),
                        "session_dir": str(session_dir),
                        "coins": coins,
                        "events": [{"timestamp": now, "action": "started", "coin_count": len(coins)}],
                        "launch_report": {},
                        "error": None,
                    }
                    self._save_session()
                    self.launch_task = asyncio.create_task(self._launch(session_id))
                    return self._public_session()
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    async def _launch(self, session_id: str) -> None:
        session = self.current
        if session is None or session["id"] != session_id:
            return
        try:
            result = await asyncio.to_thread(
                orchestrator.run_session,
                session_id,
                session["csv_path"],
                session["session_dir"],
                session["coins"],
            )
            report = result.get("final_report", {}) if isinstance(result, dict) else {}
            failures = [
                value for value in report.values()
                if isinstance(value, dict) and value.get("status") == "failed"
            ]
            async with self.lock:
                if self.current is None or self.current["id"] != session_id:
                    return
                self.current["launch_report"] = report
                self.current["updated_at"] = _iso_now()
                if failures:
                    self.current["status"] = "error"
                    self.current["error"] = "One or more existing agent processes could not be started."
                elif self.current["status"] == "starting":
                    self.current["status"] = "running"
                self._save_session()
        except Exception as exc:
            async with self.lock:
                if self.current and self.current["id"] == session_id:
                    self.current["status"] = "error"
                    self.current["error"] = f"Orchestrator launch failed ({type(exc).__name__})."
                    self.current["updated_at"] = _iso_now()
                    self._save_session()
        finally:
            current = self.current
            if current and current["id"] == session_id and current["status"] == "error":
                await asyncio.to_thread(orchestrator.stop_session, session_id)

    async def _refresh_terminal_state(self) -> None:
        async with self.lock:
            session = self.current
            if not session or session["status"] not in {"running", "paused"}:
                return
            process_map = orchestrator.session_process_states(session["id"], session.get("session_dir"))
            if process_map and all(process["status"] == "stopped" for process in process_map.values()):
                session["status"] = "error"
                session["error"] = "All agent processes exited unexpectedly."
                session["updated_at"] = _iso_now()
                self._save_session(session)

    async def status(self) -> dict[str, Any] | None:
        await self._refresh_terminal_state()
        return self._public_session()

    async def _signal(self, action: str, signum: int, expected: str, next_state: str) -> dict[str, Any]:
        async with self.lock:
            session = self.current
            if session is None or session["status"] != expected:
                raise HTTPException(status_code=409, detail=f"Cannot {action} unless the session is {expected}.")
            session_id = session["id"]
            session["status"] = next_state
            session["updated_at"] = _iso_now()
            self._save_session(session)
        try:
            await asyncio.to_thread(orchestrator.signal_session, session_id, signum)
        except Exception as exc:
            async with self.lock:
                if self.current and self.current["id"] == session_id:
                    self.current["status"] = "error"
                    self.current["error"] = f"Could not {action} agent processes ({type(exc).__name__})."
                    self._save_session(self.current)
            raise HTTPException(status_code=500, detail=f"Could not {action} the monitoring session.") from exc
        async with self.lock:
            session = self.current
            if session is None or session["id"] != session_id:
                raise HTTPException(status_code=409, detail="Monitoring session changed during control action.")
            action_name = "paused" if next_state == "paused" else "resumed"
            session["events"].insert(0, {"timestamp": _iso_now(), "action": action_name, "coin_count": len(session["coins"])})
            session["updated_at"] = _iso_now()
            self._save_session(session)
            return self._public_session(session)

    async def pause(self) -> dict[str, Any]:
        return await self._signal("pause", signal.SIGSTOP, "running", "paused")

    async def resume(self) -> dict[str, Any]:
        return await self._signal("resume", signal.SIGCONT, "paused", "running")

    async def stop(self) -> dict[str, Any] | None:
        async with self.stop_lock:
            return await self._stop_impl()

    async def _stop_impl(self) -> dict[str, Any] | None:
        async with self.lock:
            session = self.current
            if session is None:
                return None
            if session["status"] == "stopped":
                return self._public_session(session)
            if session["status"] == "starting":
                session["status"] = "stopping"
            elif session["status"] in {"running", "paused", "error"}:
                session["status"] = "stopping"
            elif session["status"] == "stopping":
                pass
            session_id = session["id"]
            launch_task = self.launch_task
            session["updated_at"] = _iso_now()

        if launch_task and not launch_task.done():
            await asyncio.gather(launch_task, return_exceptions=True)
        await asyncio.to_thread(orchestrator.stop_session, session_id)

        async with self.lock:
            session = self.current
            if session and session["id"] == session_id:
                session["status"] = "stopped"
                session["updated_at"] = _iso_now()
                session["events"].insert(0, {"timestamp": session["updated_at"], "action": "stopped", "coin_count": len(session["coins"])})
                self._save_session(session)
                return self._public_session(session)
        return None

    async def shutdown(self) -> None:
        if self.current and self.current["status"] in {"starting", "running", "paused", "stopping", "error"}:
            await self.stop()


manager = MonitoringManager()
_news_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _agent_public_status(session: dict[str, Any] | None) -> dict[str, Any]:
    if not session:
        return {name: {"status": "idle", "detail": "No monitoring session."} for name in AGENT_KEYS}
    return session["agents"]


def _read_market(session_dir: str | None, coins: list[dict[str, str]]) -> list[dict[str, Any]]:
    if not session_dir:
        return []
    values = _safe_json(Path(session_dir) / "market.json", {})
    if not isinstance(values, dict):
        return []
    results = []
    for coin in coins:
        base = _base_symbol(coin["symbol"])
        item = values.get(base)
        result = {"coin_name": coin["coin_name"], "symbol": coin["symbol"]}
        if isinstance(item, dict):
            result.update(item)
            result["source_symbol"] = item.get("symbol")
            result["symbol"] = coin["symbol"]
            result["coin_name"] = coin["coin_name"]
        results.append(result)
    return results


def _read_news_sources(session_dir: str | None) -> dict[str, Any]:
    if not session_dir:
        return {"rss": {"status": "idle"}, "tinyfish": {"status": "idle"}}
    value = _safe_json(Path(session_dir) / "news_status.json", {})
    if not isinstance(value, dict):
        value = {}
    return {
        source: value.get(source, {"status": "waiting"})
        for source in ("rss", "tinyfish")
    }


def _read_pattern_reports(coins: list[dict[str, str]], started_at: str | None) -> list[dict[str, Any]]:
    results = []
    session_start = datetime.fromisoformat(started_at) if started_at else None
    for coin in coins:
        symbol = coin["symbol"]
        base_symbol = _base_symbol(symbol)
        safe_symbol = f"{base_symbol}_USDT"
        report_dir = PATTERN_REPORT_ROOT / safe_symbol / "reports"
        try:
            files = sorted(report_dir.glob("*.json"), key=lambda item: item.name, reverse=True)
        except OSError:
            files = []
        reports = []
        for path in files[:30]:
            report = _safe_json(path, None)
            if isinstance(report, dict):
                reports.append(report)
        if not reports:
            continue

        latest = reports[0]
        latest_timestamp = latest.get("fetched_at")
        try:
            is_current = bool(session_start and latest_timestamp and datetime.fromisoformat(latest_timestamp) >= session_start)
        except (TypeError, ValueError):
            is_current = False
        decision = latest.get("gemini_decision") or {}
        analysis = latest.get("vlm_analysis") or {}
        history = []
        for report in reports[:10]:
            report_decision = report.get("gemini_decision") or {}
            history.append({
                "timestamp": report.get("fetched_at"),
                "decision": report_decision.get("decision"),
                "confidence": report_decision.get("decision_confidence"),
                "reason": report_decision.get("reason"),
            })
        results.append({
            "coin_name": coin["coin_name"],
            "symbol": symbol,
            "timeframe": latest.get("timeframe"),
            "timestamp": latest_timestamp,
            "is_current": is_current,
            "decision": decision.get("decision"),
            "confidence": decision.get("decision_confidence"),
            "reason": decision.get("reason"),
            "current_patterns": analysis.get("current_detections", []),
            "tracked_patterns": analysis.get("tracked_patterns", []),
            "market_snapshot": latest.get("market_snapshot"),
            "position": latest.get("position"),
            "history": history,
        })
    return results


def _fetch_news_sync(coins: list[dict[str, str]]) -> dict[str, Any]:
    from agents.news_agent.database import NewsDatabase

    database = NewsDatabase()
    if hasattr(database, "fetch_news_for_coins"):
        items = database.fetch_news_for_coins(coins, limit_per_coin=20)
    else:
        # Keep compatibility with older database adapters while they are upgraded.
        items = []
        for coin in coins:
            articles = database.fetch_news_by_coin(coin["coin_name"], coin["symbol"], limit=20)
            items.extend({
                **article.to_dict(),
                "coin_name": coin["coin_name"],
                "symbol": coin["symbol"],
            } for article in articles)
    items.sort(key=lambda item: item.get("published_at") or item.get("fetched_at") or "", reverse=True)
    return {"items": items[:100], "status": "connected"}


async def _read_news(session_id: str | None, coins: list[dict[str, str]]) -> dict[str, Any]:
    if not session_id:
        return {"items": [], "status": "idle"}
    now = asyncio.get_running_loop().time()
    cached = _news_cache.get(session_id)
    if cached and now - cached[0] < 10:
        return cached[1]
    try:
        result = await asyncio.to_thread(_fetch_news_sync, coins)
    except Exception as exc:
        result = {"items": [], "status": "error", "error_type": type(exc).__name__}
    _news_cache[session_id] = (now, result)
    return result


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await manager.shutdown()


app = FastAPI(title="CryptoGuardian API", version="1.0.0", lifespan=lifespan)
origins = [item.strip() for item in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:4173").split(",") if item.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
CHART_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/charts", StaticFiles(directory=CHART_ROOT), name="charts")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "cryptoguardian-api"}


@app.post("/api/monitoring/start", status_code=202)
async def start_monitoring(file: UploadFile = File(...)) -> dict[str, Any]:
    if file.filename and not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a .csv file.")
    contents = await file.read(MAX_CSV_BYTES + 1)
    if len(contents) > MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="CSV file exceeds the 5 MB upload limit.")
    try:
        coins = parse_watchlist_csv(contents)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"session": await manager.start(coins), "coins": coins}


@app.get("/api/monitoring/status")
async def monitoring_status() -> dict[str, Any]:
    return {"session": await manager.status()}


@app.post("/api/monitoring/pause")
async def pause_monitoring() -> dict[str, Any]:
    return {"session": await manager.pause()}


@app.post("/api/monitoring/resume")
async def resume_monitoring() -> dict[str, Any]:
    return {"session": await manager.resume()}


@app.post("/api/monitoring/stop")
async def stop_monitoring() -> dict[str, Any]:
    return {"session": await manager.stop()}


@app.get("/api/dashboard")
async def dashboard_snapshot() -> dict[str, Any]:
    session = await manager.status()
    session_id = session.get("id") if session else None
    coins = session.get("coins", []) if session else []
    session_dir = manager.current.get("session_dir") if manager.current else None
    started_at = session.get("started_at") if session else None
    agents = _agent_public_status(session)
    news_task = _read_news(session_id, coins)
    market = _read_market(session_dir, coins)
    sources = _read_news_sources(session_dir)
    patterns = _read_pattern_reports(coins, started_at)
    news = await news_task
    pattern_live = any(item.get("is_current") for item in patterns)
    latest_pattern = max((item.get("timestamp") for item in patterns if item.get("timestamp")), default=None)
    return {
        "session": session,
        "coins": coins,
        "agents": {
            **agents,
            "market_scanner": {
                **agents["market_scanner"],
                "last_update": max((item.get("updated_at") for item in market if item.get("updated_at")), default=None),
            },
            "news_agent": {
                **agents["news_agent"],
                "sources": sources,
                "data_status": news.get("status"),
            },
            "pattern_decision": {
                **agents["pattern_decision"],
                "last_update": latest_pattern,
                "has_current_result": pattern_live,
            },
        },
        "market": market,
        "news": news,
        "patterns": patterns,
        "server_time": _iso_now(),
    }


@app.websocket("/api/ws")
async def dashboard_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(await dashboard_snapshot())
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return
