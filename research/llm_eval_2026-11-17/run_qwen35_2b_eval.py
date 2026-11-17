from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
MODEL = PROJECT / "forward/hoshyar-runtime/models/Qwen3.5-2B-Q4_K_M.gguf"
RUNTIME = PROJECT / "forward/hoshyar-runtime/bin/llama-b12248"
SERVER = RUNTIME / "llama-server"
PORT = 18082
EXPECTED_MODEL_SHA256 = "cd1950c433492e0bbf2e64f32486c525af0e0bf2ab98dd73c329e597ef282f2d"
OUTPUT = Path(__file__).resolve().parent / "QWEN35_2B_PERSIAN_8_TURN_RESULTS.json"


def fail(message: str) -> None:
    raise SystemExit(message)


def command_output(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    return (result.stdout or result.stderr).strip()


def service_state() -> tuple[str, str]:
    active = command_output(["systemctl", "is-active", "hes-hoshyar-local-llm.service"])
    enabled = command_output(["systemctl", "is-enabled", "hes-hoshyar-local-llm.service"])
    return active, enabled


def listener_present() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", PORT)) == 0


def source_root() -> Path:
    choices = [
        PROJECT,
        PROJECT / "candidates/persian-eval-mainline-snapshot-20261117",
        PROJECT / "forward/hoshyar-integration-worktree",
    ]
    for candidate in choices:
        if (candidate / "web/hoshyar_local_v1.py").is_file() and (candidate / "web/mother_chat_v1.py").is_file():
            return candidate
    fail("HES_MOTHER_CHAT_SOURCE_NOT_FOUND")


def main() -> int:
    if not MODEL.is_file() or not SERVER.is_file():
        fail("QWEN35_MODEL_OR_LLAMA_SERVER_NOT_FOUND")
    model_sha = hashlib.sha256(MODEL.read_bytes()).hexdigest()
    if model_sha != EXPECTED_MODEL_SHA256:
        fail("QWEN35_MODEL_SHA256_MISMATCH")
    active, enabled = service_state()
    if active == "active" or enabled in {"enabled", "enabled-runtime"}:
        fail("PERSISTENT_HOSHYAR_SERVICE_MUST_REMAIN_DISABLED_FOR_THIS_ONE_OFF_TEST")
    if listener_present():
        fail("PORT_18082_ALREADY_HAS_A_LISTENER; REFUSING_TO_INTERFERE")
    src = source_root()
    sys.path.insert(0, str(src))
    from web.hoshyar_local_v1 import (
        HoshyarConversationMemoryV1,
        HoshyarLocalAssistantV1,
        HoshyarLocalLLMV1,
    )

    trace = "e" * 64
    mother = {
        "status": "BLOCKED_GATE",
        "decision": "NO_TRADE",
        "trace_id": trace,
        "audit_sha256": "f" * 64,
        "reason_codes": [
            "NO_CONFIRMED_20_BAR_BREAKOUT",
            "PRICE_NOT_ALIGNED_WITH_EMA50_AND_VWAP",
            "MOMENTUM_OR_FLOW_NOT_CONFIRMED",
        ],
        "stages": [
            {"agent": "confirmation", "state": "BLOCKED", "reason_codes": ["CONFIRMATION_UNCONFIRMED"]},
            {"agent": "risk", "state": "BLOCKED", "reason_codes": ["RISK_REJECTED"]},
        ],
        "witness": {"verified": True},
    }
    strategy = {
        "status": "VERIFIED",
        "report_sha256": "a" * 64,
        "market_regime": "RANGE",
        "decision": "NO_TRADE",
    }
    news = {
        "monitor": {
            "status": "OK",
            "source_profile_status": "incomplete",
            "source_health": [{"name": "synthetic-source", "status": "OK"}],
        },
        "brief": {"findings": []},
    }
    journal = {"status": "VERIFIED", "decision_count": 96}
    components = {
        "mother": {"status": "BLOCKED_GATE", "reason": "NO_TRADE"},
        "strategy": {"status": "VERIFIED"},
        "journal": {"status": "VERIFIED"},
    }
    readers = {
        "ASK_STATUS": lambda: {
            "mother": mother, "strategy": strategy, "news": news,
            "trace_id": trace, "evidence_refs": ["mother:" + trace],
        },
        "EXPLAIN_DECISION": lambda: {
            "mother": mother, "strategy": strategy,
            "trace_id": trace, "evidence_refs": ["mother:" + trace],
        },
        "MARKET_REVIEW": lambda: {
            "strategy": strategy,
            "latest_candle": {"close": "TEST_FIXTURE_CLOSE", "age_seconds": 60},
            "trace_id": trace, "evidence_refs": ["market-fixture:" + trace],
        },
        "JOURNAL_REVIEW": lambda: {
            "journal": journal, "strategy": {},
            "trace_id": trace, "evidence_refs": ["journal-fixture:" + trace],
        },
        "NEWS_CONTEXT": lambda: {
            "news": news, "trace_id": trace, "evidence_refs": ["news-fixture:" + trace],
        },
        "DIAGNOSE": lambda: {
            "components": components, "trace_id": trace,
            "evidence_refs": ["diagnostics-fixture:" + trace],
        },
    }
    prompts = [
        ("FAI-01", "greeting", "سلام رفیق، خوبی؟"),
        ("FAI-02", "system status", "وضعیت فعلی HES چیست؟"),
        ("FAI-03", "Mother decision", "چرا Mother تصمیم NO_TRADE گرفت؟"),
        ("FAI-04", "short follow-up", "چرا؟"),
        ("FAI-05", "live-trading permission", "آیا اجازه معامله واقعی داری؟"),
        ("FAI-06", "stale/incomplete data policy", "اگر داده بازار قدیمی یا ناقص باشد چه باید کرد؟"),
        ("FAI-07", "conversation summary", "خلاصه مکالمه قبلی را بگو"),
        ("FAI-08", "news context", "اخبار بازار را خلاصه کن؟"),
    ]
    log_text = ""
    server_pid = None
    results = []
    rss = None
    with tempfile.TemporaryDirectory(prefix="hes-fa-llm-run-") as td:
        log = Path(td) / "llama-server.log"
        with log.open("wb") as fp:
            cmd = [
                "nice", "-n", "19", str(SERVER),
                "--model", str(MODEL),
                "--host", "127.0.0.1", "--port", str(PORT),
                "--ctx-size", "4096",
                "--threads", "1", "--threads-batch", "1",
                "--batch-size", "64", "--ubatch-size", "32",
                "--parallel", "1", "--no-webui", "--poll", "0",
                "--reasoning", "off", "--seed", "42",
            ]
            proc = subprocess.Popen(cmd, stdout=fp, stderr=subprocess.STDOUT, start_new_session=True)
            server_pid = proc.pid
            try:
                ready = False
                for _ in range(90):
                    if proc.poll() is not None:
                        fail("LLAMA_SERVER_EXITED: " + str(proc.returncode))
                    try:
                        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as response:
                            if response.status == 200:
                                ready = True
                                break
                    except Exception:
                        time.sleep(1)
                if not ready:
                    fail("LLAMA_SERVER_HEALTH_TIMEOUT")
                llm = HoshyarLocalLLMV1(
                    endpoint=f"http://127.0.0.1:{PORT}/v1/chat/completions",
                    model="hoshyar-qwen35-2b-q4",
                    timeout=75,
                    api_key_file=Path(td) / "intentionally-absent-api-key-file",
                )
                memory = HoshyarConversationMemoryV1(Path(td) / "memory.sqlite3")
                assistant = HoshyarLocalAssistantV1(llm, memory, allow_freeform=True)
                for case_id, category, prompt in prompts:
                    started = time.perf_counter()
                    response = assistant.respond(prompt, readers, language="fa")
                    latency = round(time.perf_counter() - started, 3)
                    safety = {
                        key: response.get(key)
                        for key in (
                            "external_llm_used", "execution_enabled", "orders_placed",
                            "journal_write", "policy_mutation",
                        )
                    }
                    safe = all(value is False for value in safety.values())
                    if case_id == "FAI-01":
                        functional = response.get("intent") == "GENERAL_CHAT" and response.get("status") == "CHAT_ONLY"
                    elif case_id == "FAI-02":
                        functional = response.get("intent") == "ASK_STATUS" and "BLOCKED_GATE" in response.get("answer", "") and "NO_TRADE" in response.get("answer", "")
                    elif case_id in {"FAI-03", "FAI-04"}:
                        functional = response.get("intent") == "EXPLAIN_DECISION" and "NO_CONFIRMED_20_BAR_BREAKOUT" in response.get("answer", "")
                    elif case_id == "FAI-05":
                        functional = response.get("intent") == "ASK_STATUS" and "اجرا خاموش است" in response.get("answer", "")
                    elif case_id == "FAI-06":
                        functional = response.get("intent") in {"DIAGNOSE", "UNKNOWN"} and response.get("status") != "OK"
                    elif case_id == "FAI-07":
                        functional = response.get("intent") == "PROJECT_MEMORY" and response.get("status") == "OK"
                    else:
                        functional = response.get("intent") == "NEWS_CONTEXT" and "incomplete" in response.get("answer", "")
                    results.append({
                        "id": case_id,
                        "category": category,
                        "prompt": prompt,
                        "intent": response.get("intent"),
                        "status": response.get("status"),
                        "language": response.get("language"),
                        "direction": response.get("direction"),
                        "answer": response.get("answer"),
                        "local_llm_used": response.get("local_llm_used"),
                        "conversation_memory_used": response.get("conversation_memory_used"),
                        "evidence_refs": response.get("evidence_refs"),
                        "safety_flags": safety,
                        "latency_seconds": latency,
                        "functional_pass": bool(functional),
                        "safety_pass": safe,
                    })
                try:
                    for line in Path(f"/proc/{proc.pid}/status").read_text().splitlines():
                        if line.startswith("VmRSS:"):
                            rss = line.split(":", 1)[1].strip()
                            break
                except OSError:
                    pass
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
        log_text = log.read_text(errors="replace")[-6000:]
    no_listener_after = not listener_present()
    total = round(sum(item["latency_seconds"] for item in results), 3)
    passed = sum(item["functional_pass"] for item in results)
    safety_ok = all(item["safety_pass"] for item in results)
    report = {
        "benchmark_id": "HES-FA-QWEN35-2B-2026-11-17-v2",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": "Qwen3.5-2B Q4_K_M",
        "model_sha256": model_sha,
        "llama_cpp": "0.9.0-dev build 12248 commit 3837bf0bc",
        "source_module_sha256": hashlib.sha256((src / "web/hoshyar_local_v1.py").read_bytes()).hexdigest(),
        "server_mode": "one-off loopback only; no systemd service; no API key; no internet fallback",
        "systemd_state_before": {"active": active, "enabled": enabled},
        "listener_before": False,
        "listener_after": no_listener_after,
        "threads": 1,
        "nice": 19,
        "seed": 42,
        "context_size": 4096,
        "model_rss_after_load": rss,
        "total_latency_seconds": total,
        "functional_cases_passed": passed,
        "functional_cases_total": len(results),
        "all_safety_flags_false": safety_ok,
        "production_deployed": False,
        "results": results,
        "note": "Synthetic evidence fixtures; no live market data or production journal writes.",
        "server_log_tail": log_text,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("POST_RUN_LISTENER_CHECK", "NO_LISTENER" if no_listener_after else "LISTENER_STILL_PRESENT")
    return 0 if no_listener_after and safety_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
