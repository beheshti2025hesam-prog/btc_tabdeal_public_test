import json
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

import pytest

from web import dashboard


class FakeSecurity:
    def check_origin(self, headers):
        return "https"

    def check_rate_limit(self, *args, **kwargs):
        return None

    def has_valid_session(self, headers):
        return True

    def clear_session_cookie(self, *, secure):
        return "hes_mother_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"


class FakeAssistant:
    def __init__(self):
        self.cleared = False
        self.language = None
        self.messages = [{"role": "user", "content": "سلام"}, {"role": "assistant", "content": "سلام، خوش آمدی"}]

    def respond(self, message, readers, *, language=None):
        self.language = language
        return {
            "schema_version": "hes.mother_chat.v1", "intent": "GENERAL_CHAT",
            "status": "CHAT_ONLY", "answer": "سلام، خوش آمدی", "language": language,
            "local_llm_used": True, "conversation_memory_used": True,
            "external_llm_used": False, "execution_enabled": False,
            "orders_placed": False, "journal_write": False, "policy_mutation": False,
        }

    def read_history(self):
        return list(self.messages)

    def clear_memory(self):
        self.cleared = True
        self.messages.clear()


@contextmanager
def running_dashboard(monkeypatch, assistant):
    monkeypatch.setattr(dashboard, "_MOTHER_CHAT_SECURITY", FakeSecurity())
    monkeypatch.setattr(dashboard, "_HOSHYAR_LOCAL_ASSISTANT", assistant)
    server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def call(base, path, *, method="GET", payload=None):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    headers = {"Sec-Fetch-Site": "same-origin"}
    if method == "POST":
        headers.update({"Origin": base, "Content-Type": "application/json"})
    request = Request(base + path, data=data, headers=headers, method=method)
    with urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode())


def test_history_endpoint_returns_only_authenticated_local_memory(monkeypatch):
    assistant = FakeAssistant()
    with running_dashboard(monkeypatch, assistant) as base:
        status, payload = call(base, "/api/mother-chat/history")
    assert status == 200
    assert payload["local_llm_enabled"] is True
    assert payload["messages"] == assistant.messages
    assert payload["execution_enabled"] is False
    assert payload["orders_placed"] is False


def test_clear_endpoint_clears_local_memory_only(monkeypatch):
    assistant = FakeAssistant()
    with running_dashboard(monkeypatch, assistant) as base:
        status, payload = call(base, "/api/mother-chat/clear", method="POST", payload={})
    assert status == 200
    assert payload["status"] == "CLEARED"
    assert assistant.cleared is True
    assert assistant.messages == []
    assert payload["execution_enabled"] is False
    assert payload["orders_placed"] is False


def test_chat_endpoint_uses_local_assistant_and_keeps_execution_disabled(monkeypatch):
    assistant = FakeAssistant()
    with running_dashboard(monkeypatch, assistant) as base:
        status, payload = call(base, "/api/mother-chat", method="POST", payload={"message": "سلام"})
    assert status == 200
    assert payload["local_llm_used"] is True
    assert payload["external_llm_used"] is False
    assert payload["answer"] == "سلام، خوش آمدی"
    assert payload["execution_enabled"] is False
    assert payload["orders_placed"] is False


def test_history_endpoint_reports_disabled_when_local_assistant_is_off(monkeypatch):
    with running_dashboard(monkeypatch, None) as base:
        status, payload = call(base, "/api/mother-chat/history")
    assert status == 200
    assert payload["local_llm_enabled"] is False
    assert payload["messages"] == []



def test_chat_endpoint_passes_selected_response_language(monkeypatch):
    assistant = FakeAssistant()
    with running_dashboard(monkeypatch, assistant) as base:
        status, payload = call(base, "/api/mother-chat", method="POST", payload={"message": "Guten Tag", "language": "de"})
    assert status == 200
    assert assistant.language == "de"
    assert payload["language"] == "de"


def test_project_memory_query_uses_only_the_read_only_local_reader(monkeypatch):
    class FakeProjectMemory:
        def search(self, query):
            assert "مدل محلی" in query
            return {
                "status": "PARTIAL",
                "matches": [{"title": "Local model decision", "path": "docs/checkpoints/LOCAL_MODEL.md", "excerpt": "Qwen3.5-2B is the selected local model.", "sha256": "a" * 64, "modified_at": "2026-11-17T00:00:00Z"}],
                "evidence_refs": ["sha256:" + "a" * 64],
                "trace_id": "project-memory-test",
                "uncertainties": ["Notion-only pages are not indexed."],
            }

    monkeypatch.setattr(dashboard, "_PROJECT_MEMORY_READER", FakeProjectMemory())
    with running_dashboard(monkeypatch, None) as base:
        status, payload = call(base, "/api/mother-chat", method="POST", payload={"message": "چه تصمیمی درباره مدل محلی گرفتیم؟", "language": "fa"})
    assert status == 200
    assert payload["intent"] == "PROJECT_MEMORY"
    assert payload["status"] == "PARTIAL"
    assert "Qwen3.5-2B" in payload["answer"]
    assert payload["evidence_refs"] == ["sha256:" + "a" * 64]
    assert payload["execution_enabled"] is False
    assert payload["orders_placed"] is False



def test_command_center_uses_canonical_hes_trade_ai_user_facing_name():
    from pathlib import Path
    project_root = Path(__file__).resolve().parents[1]
    html = (project_root / "web" / "dashboard.py").read_text(encoding="utf-8")
    javascript = (project_root / "web" / "static" / "dashboard.js").read_text(encoding="utf-8")
    assert "HES Trade AI · Private local AI" in html
    assert "HES Command Center</a>" in html
    assert "Unlock HES Command Center" in html
    assert "Message HES Trade AI" in html
    assert "HES Trade AI is ready." in javascript
    assert "HES Trade AI / Mother · history" in javascript
    assert "HES Trade AI / Mother · '+(status||'EVIDENCE')" in javascript
    assert "HOSHYAR · Private local AI" not in html
    assert "Message HOSHYAR" not in html
    assert "HES_PRODUCT_NAMING_V1.md" not in html
