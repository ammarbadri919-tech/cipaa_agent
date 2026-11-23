from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import backend
from agents.orchestrator import graph as orchestrator


class WatchlistParsingTests(unittest.TestCase):
    def test_normalizes_and_deduplicates_symbols(self):
        coins = backend.parse_watchlist_csv(
            b"coin_name,symbol\r\nBitcoin,btc/usdt\r\nBitcoin,BTCUSDT\r\nEthereum,ETH/USDT\r\n"
        )
        self.assertEqual(coins, [
            {"coin_name": "Bitcoin", "symbol": "BTC/USDT"},
            {"coin_name": "Ethereum", "symbol": "ETH/USDT"},
        ])

    def test_rejects_missing_required_columns(self):
        with self.assertRaisesRegex(ValueError, "coin_name and symbol"):
            backend.parse_watchlist_csv(b"name,ticker\nBitcoin,BTC")


class DashboardApiTests(unittest.TestCase):
    def test_health_and_chart_mount(self):
        with TestClient(backend.app) as client:
            self.assertEqual(client.get("/api/health").json()["status"], "ok")
            dashboard = client.get("/api/dashboard")
            self.assertEqual(dashboard.status_code, 200)
            self.assertIn("market", dashboard.json())
            with client.websocket_connect("/api/ws") as socket:
                frame = socket.receive_json()
                self.assertIn("patterns", frame)
                self.assertIn("news", frame)
            if (backend.CHART_ROOT / "BTC_USDT.png").exists():
                response = client.get("/charts/BTC_USDT.png")
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.headers["content-type"].startswith("image/png"))

    def test_upload_starts_one_session_and_controls_existing_workers(self):
        original_root = backend.SESSION_ROOT
        original_session = backend.manager.current
        original_task = backend.manager.launch_task
        with tempfile.TemporaryDirectory() as directory:
            backend.SESSION_ROOT = Path(directory)
            backend.manager.current = None
            backend.manager.launch_task = None
            try:
                launch_result = {"final_report": {
                    "market_scanner": {"status": "started"},
                    "news_agent": {"status": "started"},
                    "pattern_decision": {"status": "started"},
                }}
                with patch.object(backend.orchestrator, "run_session", return_value=launch_result), \
                     patch.object(backend.orchestrator, "session_process_states", return_value={}), \
                     patch.object(backend.orchestrator, "signal_session") as signal_workers, \
                     patch.object(backend.orchestrator, "stop_session") as stop_workers:
                    with TestClient(backend.app) as client:
                        file_data = ("watchlist.csv", b"coin_name,symbol\nBitcoin,BTC/USDT\n", "text/csv")
                        started = client.post("/api/monitoring/start", files={"file": file_data})
                        self.assertEqual(started.status_code, 202)
                        session_id = started.json()["session"]["id"]
                        duplicate = client.post("/api/monitoring/start", files={"file": file_data})
                        self.assertEqual(duplicate.status_code, 409)
                        self.assertEqual(client.post("/api/monitoring/pause").status_code, 200)
                        self.assertEqual(client.post("/api/monitoring/resume").status_code, 200)
                        stopped = client.post("/api/monitoring/stop")
                        self.assertEqual(stopped.status_code, 200)
                        self.assertEqual(stopped.json()["session"]["status"], "stopped")
                    self.assertEqual(signal_workers.call_count, 2)
                    stop_workers.assert_called_once_with(session_id)
            finally:
                backend.manager.current = original_session
                backend.manager.launch_task = original_task
                backend.SESSION_ROOT = original_root

    def test_reads_real_market_bridge_and_existing_pattern_report(self):
        original_reports = backend.PATTERN_REPORT_ROOT
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session_dir = root / "session"
            session_dir.mkdir()
            (session_dir / "market.json").write_text(json.dumps({"BTC": {
                "symbol": "BTC/USD",
                "current_price": 64000.5,
                "quote_currency": "USD",
                "change_24h_pct": 1.25,
                "volume_24h": 1000000,
                "market_trend": "Bullish",
                "forecasts": {"15m": {"predicted_price": 64100, "predicted_pct": 0.15}},
                "updated_at": "2026-11-23T10:00:00+05:30",
            }}), encoding="utf-8")
            market = backend._read_market(str(session_dir), [{"coin_name": "Bitcoin", "symbol": "BTC/USDT"}])
            self.assertEqual(market[0]["current_price"], 64000.5)
            self.assertEqual(market[0]["source_symbol"], "BTC/USD")

            report_dir = root / "BTC_USDT" / "reports"
            report_dir.mkdir(parents=True)
            report = {
                "symbol": "BTC/USDT",
                "timeframe": "15m",
                "fetched_at": "2026-11-23T10:01:00+05:30",
                "gemini_decision": {"decision": "WAIT", "decision_confidence": 0.72, "reason": "Await confirmation."},
                "vlm_analysis": {"current_detections": [{"name": "Bull Flag", "formation_state": "DEVELOPING"}], "tracked_patterns": []},
            }
            (report_dir / "2026-11-23_10-01-00.json").write_text(json.dumps(report), encoding="utf-8")
            backend.PATTERN_REPORT_ROOT = root
            try:
                results = backend._read_pattern_reports(
                    [{"coin_name": "Bitcoin", "symbol": "BTC"}],
                    "2026-11-23T04:00:00+00:00",
                )
            finally:
                backend.PATTERN_REPORT_ROOT = original_reports
            self.assertEqual(results[0]["decision"], "WAIT")
            self.assertTrue(results[0]["is_current"])
            self.assertEqual(results[0]["current_patterns"][0]["name"], "Bull Flag")

    def test_news_collection_status_and_postgres_reader_adapter(self):
        from agents.orchestrator.dashboard_bridge import (
            initialize_news_sources,
            publish_news_source,
        )

        with tempfile.TemporaryDirectory() as directory:
            old = os.environ.get("CRYPTOGUARDIAN_SESSION_DIR")
            os.environ["CRYPTOGUARDIAN_SESSION_DIR"] = directory
            try:
                initialize_news_sources()
                publish_news_source("rss", "connected")
                status = backend._read_news_sources(directory)
                self.assertEqual(status["rss"]["status"], "connected")
                self.assertEqual(status["tinyfish"]["status"], "scheduled")

                class FakeArticle:
                    def to_dict(self):
                        return {"id": 9, "source": "RSS", "headline": "Bitcoin update", "url": "https://example.test", "published_at": None, "fetched_at": None, "description": None}

                class FakeDatabase:
                    def fetch_news_by_coin(self, name, symbol, limit):
                        self.assertion = (name, symbol, limit)
                        return [FakeArticle()]

                fake_module = types.ModuleType("agents.news_agent.database")
                fake_module.NewsDatabase = FakeDatabase
                with patch.dict(sys.modules, {"agents.news_agent.database": fake_module}):
                    news = backend._fetch_news_sync([{"coin_name": "Bitcoin", "symbol": "BTC/USDT"}])
                self.assertEqual(news["items"][0]["headline"], "Bitcoin update")
                self.assertEqual(news["items"][0]["symbol"], "BTC/USDT")
            finally:
                if old is None:
                    os.environ.pop("CRYPTOGUARDIAN_SESSION_DIR", None)
                else:
                    os.environ["CRYPTOGUARDIAN_SESSION_DIR"] = old

    def test_orchestrator_passes_session_csv_and_environment_to_existing_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            session_id = "test-session"
            csv_path = str(Path(directory) / "watchlist.csv")
            Path(csv_path).write_text("coin_name,symbol\nBitcoin,BTC/USDT\n", encoding="utf-8")
            fake_process = MagicMock()
            fake_process.poll.return_value = None
            fake_process.pid = 424242
            key = (session_id, "market_results")
            try:
                with patch.dict(orchestrator.processes, {}, clear=True), \
                     patch.object(orchestrator.subprocess, "Popen", return_value=fake_process) as popen:
                    result = orchestrator.launch_agent({
                        "session_id": session_id,
                        "csv_path": csv_path,
                        "session_dir": directory,
                    }, "market_results")
                    self.assertEqual(result["market_results"]["status"], "started")
                    kwargs = popen.call_args.kwargs
                    self.assertTrue(kwargs["start_new_session"])
                    self.assertEqual(kwargs["env"]["CRYPTOGUARDIAN_WATCHLIST"], csv_path)
                    self.assertEqual(kwargs["env"]["CRYPTOGUARDIAN_SESSION_ID"], session_id)
                    manifest = json.loads((Path(directory) / "agent_processes.json").read_text())
                    self.assertEqual(manifest["market_results"]["pid"], 424242)
            finally:
                orchestrator.processes.pop(key, None)

    def test_recovers_and_stops_a_session_process_after_api_restart(self):
        original_root = backend.SESSION_ROOT
        with tempfile.TemporaryDirectory() as directory:
            backend.SESSION_ROOT = Path(directory)
            session_id = "recovered-session"
            session_dir = backend.SESSION_ROOT / session_id
            session_dir.mkdir()
            csv_path = session_dir / "watchlist.csv"
            csv_path.write_text("coin_name,symbol\nBitcoin,BTC/USDT\n", encoding="utf-8")
            worker_env = os.environ.copy()
            worker_env["CRYPTOGUARDIAN_SESSION_ID"] = session_id
            worker = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                env=worker_env,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                record = {
                    "id": session_id,
                    "status": "running",
                    "started_at": "2026-11-23T00:00:00+00:00",
                    "updated_at": "2026-11-23T00:00:00+00:00",
                    "csv_path": str(csv_path),
                    "session_dir": str(session_dir),
                    "coins": [{"coin_name": "Bitcoin", "symbol": "BTC/USDT"}],
                    "events": [],
                    "launch_report": {},
                    "error": None,
                }
                (session_dir / "session.json").write_text(json.dumps(record), encoding="utf-8")
                (session_dir / "agent_processes.json").write_text(json.dumps({
                    "news_results": {"pid": worker.pid, "module": "agents.news_agent.agent"},
                }), encoding="utf-8")
                recovered = backend.MonitoringManager()
                self.assertEqual(recovered.current["status"], "running")
                stopped = asyncio.run(recovered.stop())
                self.assertEqual(stopped["status"], "stopped")
                worker.wait(timeout=3)
                self.assertIsNotNone(worker.returncode)
            finally:
                backend.SESSION_ROOT = original_root
                if worker.poll() is None:
                    worker.kill()
                    worker.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
