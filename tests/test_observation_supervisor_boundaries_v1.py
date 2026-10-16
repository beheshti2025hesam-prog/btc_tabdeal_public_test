"""Static guardrails for the ledger-only supervisor primitive.

These checks are defense-in-depth against accidental scope creep; they are not
a sandbox and do not replace independent review.
"""
import ast
from pathlib import Path


FORBIDDEN_IMPORT_ROOTS = {
    "aiohttp",
    "asyncio",
    "ftplib",
    "http",
    "httpx",
    "paramiko",
    "pexpect",
    "requests",
    "socket",
    "smtplib",
    "subprocess",
    "telnetlib",
    "urllib",
    "websocket",
    "websockets",
}
FORBIDDEN_CALL_NAMES = {
    "__import__",
    "connect",
    "create_connection",
    "eval",
    "exec",
    "open_connection",
    "popen",
    "Popen",
    "request",
    "run",
    "system",
    "urlopen",
}


def test_supervisor_has_no_network_or_process_control_imports():
    source_path = Path(__file__).resolve().parents[1] / "forward" / "observation_supervisor_v1.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))

    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])

    assert not (imported_roots & FORBIDDEN_IMPORT_ROOTS), (
        "Supervisor ledger must remain free of network/process-control imports: "
        + ", ".join(sorted(imported_roots & FORBIDDEN_IMPORT_ROOTS))
    )


def test_supervisor_has_no_direct_network_or_process_control_calls():
    source_path = Path(__file__).resolve().parents[1] / "forward" / "observation_supervisor_v1.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))

    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)

    assert not (calls & FORBIDDEN_CALL_NAMES), (
        "Supervisor ledger must not call network/process-control APIs: "
        + ", ".join(sorted(calls & FORBIDDEN_CALL_NAMES))
    )
