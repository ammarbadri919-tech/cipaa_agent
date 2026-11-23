
import logging
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from langgraph.graph import StateGraph, START, END
from agents.orchestrator.state import CryptoGuardianState

PROJECT_ROOT = Path(__file__).resolve().parents[2]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("CryptoGuardian")

# Existing agents — no new agents created.
AGENTS = {
    "market_results": "agents.market_scanner.agent",
    "news_results": "agents.news_agent.agent",
    "pattern_results": "agents.pattern_decision_agent.agent",
}

processes: dict[tuple[str, str], subprocess.Popen] = {}
session_directories: dict[str, str] = {}
_process_lock = threading.RLock()


def _write_process_manifest(session_id: str, result_key: str, module: str, pid: int) -> None:
    directory = session_directories.get(session_id)
    if not directory:
        return
    path = Path(directory) / "agent_processes.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        records = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        records = {}
    records[result_key] = {"pid": pid, "module": module}
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(records), encoding="utf-8")
    temporary.replace(path)


def _manifest_processes(session_id: str) -> dict[str, dict]:
    directory = session_directories.get(session_id)
    if not directory:
        return {}
    try:
        result = json.loads((Path(directory) / "agent_processes.json").read_text(encoding="utf-8"))
        return result if isinstance(result, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _pid_is_session_process(pid: int, session_id: str) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    proc = Path("/proc") / str(pid)
    if proc.exists():
        try:
            environment = (proc / "environ").read_bytes().split(b"\0")
            expected = f"CRYPTOGUARDIAN_SESSION_ID={session_id}".encode()
            return expected in environment
        except OSError:
            return False
    return True


def _pid_is_stopped(pid: int) -> bool:
    try:
        for line in (Path("/proc") / str(pid) / "status").read_text().splitlines():
            if line.startswith("State:"):
                return line.split()[1] in {"T", "t"}
    except OSError:
        pass
    return False


def launch_agent(state: CryptoGuardianState, result_key: str):
    """Launch an existing agent as a background service."""

    module = AGENTS[result_key]
    session_id = state.get("session_id", "default")
    process_key = (session_id, result_key)

    try:
        with _process_lock:
            session_dir = state.get("session_dir")
            if session_dir:
                session_directories[session_id] = str(session_dir)
            process = processes.get(process_key)
            if process and process.poll() is None:
                return {
                    result_key: {
                        "status": "already_running",
                        "pid": process.pid,
                    }
                }

            env = os.environ.copy()
            csv_path = state.get("csv_path")
            session_dir = state.get("session_dir")
            if csv_path:
                env["CRYPTOGUARDIAN_WATCHLIST"] = str(csv_path)
            if session_dir:
                env["CRYPTOGUARDIAN_SESSION_DIR"] = str(session_dir)
            env["CRYPTOGUARDIAN_SESSION_ID"] = session_id

            process = subprocess.Popen(
                [sys.executable, "-m", module],
                cwd=str(PROJECT_ROOT),
                env=env,
                start_new_session=True,
            )

            processes[process_key] = process
            _write_process_manifest(session_id, result_key, module, process.pid)

        logger.info("%s started | PID %s", module, process.pid)

        return {
            result_key: {
                "status": "started",
                "pid": process.pid,
            }
        }

    except Exception as exc:
        logger.exception("Failed to launch %s", module)

        return {
            result_key: {
                "status": "failed",
                "error": str(exc),
            }
        }


def market_scanner_node(state: CryptoGuardianState):
    return launch_agent(state, "market_results")


def news_agent_node(state: CryptoGuardianState):
    return launch_agent(state, "news_results")


def pattern_decision_node(state: CryptoGuardianState):
    return launch_agent(state, "pattern_results")


def coordinator_node(state: CryptoGuardianState):
    report = {
        "market_scanner": state.get("market_results", {}),
        "news_agent": state.get("news_results", {}),
        "pattern_decision": state.get("pattern_results", {}),
    }

    logger.info("All three agent services have been launched.")

    for name, result in report.items():
        logger.info("%s: %s", name, result)

    return {"final_report": report}


# LangGraph workflow
builder = StateGraph(CryptoGuardianState)

builder.add_node("market_scanner", market_scanner_node)
builder.add_node("news_agent", news_agent_node)
builder.add_node("pattern_decision", pattern_decision_node)
builder.add_node("coordinator", coordinator_node)

# Parallel execution
builder.add_edge(START, "market_scanner")
builder.add_edge(START, "news_agent")
builder.add_edge(START, "pattern_decision")

# Join all three agents
builder.add_edge(
    ["market_scanner", "news_agent", "pattern_decision"],
    "coordinator",
)

builder.add_edge("coordinator", END)

crypto_guardian_graph = builder.compile()


def run_cryptoguardian():
    return crypto_guardian_graph.invoke({})


def run_session(session_id: str, csv_path: str, session_dir: str, coins: list[dict[str, str]]):
    """Launch the existing agent services for one uploaded watchlist."""
    return crypto_guardian_graph.invoke({
        "session_id": session_id,
        "csv_path": csv_path,
        "session_dir": session_dir,
        "coins": coins,
    })


def session_processes(session_id: str) -> dict[str, subprocess.Popen]:
    with _process_lock:
        return {
            name: process
            for (owner, name), process in processes.items()
            if owner == session_id
        }


def session_process_states(session_id: str, session_dir: str | None = None) -> dict[str, dict]:
    """Return live process state, including children recovered after API restart."""
    if session_dir:
        session_directories[session_id] = session_dir
    states: dict[str, dict] = {}
    for name, process in session_processes(session_id).items():
        if process.poll() is None:
            status = "paused" if _pid_is_stopped(process.pid) else "running"
        else:
            status = "stopped"
        states[name] = {"pid": process.pid, "status": status}
    for name, record in _manifest_processes(session_id).items():
        if name in states:
            continue
        try:
            pid = int(record["pid"])
        except (KeyError, TypeError, ValueError):
            continue
        if _pid_is_session_process(pid, session_id):
            states[name] = {"pid": pid, "status": "paused" if _pid_is_stopped(pid) else "running"}
        else:
            states[name] = {"pid": pid, "status": "stopped"}
    return states


def signal_session(session_id: str, sig: int) -> None:
    """Send a signal to each live agent process group started for a session."""
    for state in session_process_states(session_id).values():
        if state["status"] in {"running", "paused"}:
            try:
                os.killpg(state["pid"], sig)
            except ProcessLookupError:
                pass


def stop_session(session_id: str, grace_seconds: float = 8.0) -> dict[str, int | None]:
    """Ask all existing agents to stop, then terminate any process still alive."""
    live = {
        name: state
        for name, state in session_process_states(session_id).items()
        if state["status"] in {"running", "paused"}
    }
    for name, state in live.items():
        try:
            # A SIGSTOP'ed worker cannot handle SIGINT until it is continued.
            os.killpg(state["pid"], signal.SIGCONT)
            os.killpg(state["pid"], signal.SIGINT)
        except ProcessLookupError:
            pass

    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline and any(_pid_is_session_process(state["pid"], session_id) for state in live.values()):
        time.sleep(0.1)

    local_processes = session_processes(session_id)
    for name, state in live.items():
        if _pid_is_session_process(state["pid"], session_id):
            try:
                os.killpg(state["pid"], signal.SIGTERM)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and any(_pid_is_session_process(state["pid"], session_id) for state in live.values()):
        time.sleep(0.1)

    for name, state in live.items():
        if _pid_is_session_process(state["pid"], session_id):
            try:
                os.killpg(state["pid"], signal.SIGKILL)
            except ProcessLookupError:
                pass
        process = local_processes.get(name)
        if process is not None:
            process.wait(timeout=2)

    return {name: state["pid"] for name, state in live.items()}


if __name__ == "__main__":
    result = run_cryptoguardian()

    print("\n========== CRYPTOGUARDIAN ==========")
    print(result["final_report"])
