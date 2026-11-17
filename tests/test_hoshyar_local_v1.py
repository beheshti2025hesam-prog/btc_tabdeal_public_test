import json
import os
from pathlib import Path

import pytest

from web.hoshyar_local_v1 import (
    ALLOWED_INTENTS,
    MAX_STORED_MESSAGES,
    HoshyarConversationMemoryV1,
    HoshyarLocalAssistantV1,
    HoshyarLocalError,
    HoshyarLocalLLMV1,
)


class FakeLLM:
    def __init__(self, intent="GENERAL_CHAT", answer="سلام، در خدمتم.", route_error=False, answer_error=False):
        self.intent = intent
        self.answer = answer
        self.route_error = route_error
        self.answer_error = answer_error
        self.route_calls = []
        self.answer_calls = []

    def route_intent(self, messages):
        self.route_calls.append(messages)
        if self.route_error:
            raise HoshyarLocalError("HOSHYAR_LOCAL_MODEL_UNAVAILABLE")
        return self.intent

    def general_answer(self, messages):
        self.answer_calls.append(messages)
        if self.answer_error:
            raise HoshyarLocalError("HOSHYAR_LOCAL_MODEL_UNAVAILABLE")
        return self.answer


class FakeHTTPResponse:
    def __init__(self, payload):
        self.raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit=-1):
        return self.raw[:limit]


def evidence_readers():
    return {
        "EXPLAIN_DECISION": lambda: {
            "mother": {
                "status": "BLOCKED_GATE",
                "decision": "NO_TRADE",
                "reason_codes": ["REQUIRED_CHECK_FAILED"],
                "stages": [{"agent": "Confirmation", "state": "BLOCKED", "reason_codes": ["REQUIRED_CHECK_FAILED"]}],
                "witness": {"verified": True},
            },
            "strategy": {"status": "VERIFIED", "decision": "NO_TRADE"},
            "trace_id": "trace-test",
            "evidence_refs": ["sha256:mother-test"],
        },
        "NEWS_CONTEXT": lambda: {"status": "VERIFIED", "items": [], "evidence_refs": ["sha256:news-test"]},
        "ASK_STATUS": lambda: {
            "mother": {"status": "BLOCKED_GATE", "decision": "NO_TRADE", "reason_codes": ["REQUIRED_CHECK_FAILED"], "witness": {"verified": True}},
            "strategy": {"status": "VERIFIED", "decision": "NO_TRADE"},
            "trace_id": "trace-status",
            "evidence_refs": ["sha256:status-test"],
        },
    }


def test_local_llm_route_and_answer_use_separate_bounded_json_schemas(monkeypatch, tmp_path):
    requests = []
    payloads = [
        {"choices": [{"message": {"content": '{"intent":"EXPLAIN_DECISION"}'}}]},
        {"choices": [{"message": {"content": '{"answer":"سلام، در خدمتم."}'}}]},
    ]

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeHTTPResponse(payloads.pop(0))

    monkeypatch.setattr("web.hoshyar_local_v1.urlopen", fake_urlopen)
    client = HoshyarLocalLLMV1(api_key_file=tmp_path / "missing-key")
    messages = [{"role": "system", "content": "route"}, {"role": "user", "content": "چرا؟"}]
    assert client.route_intent(messages) == "EXPLAIN_DECISION"
    assert client.general_answer(messages) == "سلام، در خدمتم."

    route_body = json.loads(requests[0][0].data)
    answer_body = json.loads(requests[1][0].data)
    assert route_body["max_tokens"] == 24
    assert route_body["response_format"]["type"] == "json_schema"
    assert set(route_body["response_format"]["json_schema"]["schema"]["properties"]) == {"intent"}
    assert answer_body["max_tokens"] == 64
    assert set(answer_body["response_format"]["json_schema"]["schema"]["properties"]) == {"answer"}
    assert all(timeout <= 120 for _, timeout in requests)


def test_model_routes_followup_using_recent_history_and_mother_evidence(tmp_path):
    memory = HoshyarConversationMemoryV1(tmp_path / "memory.sqlite3")
    memory.append_turn("چرا تصمیم Mother برابر NO_TRADE بود؟", "Mother decision: NO_TRADE.")
    llm = FakeLLM(intent="EXPLAIN_DECISION")
    assistant = HoshyarLocalAssistantV1(llm, memory)
    result = assistant.respond("پس علتش چه بود؟", evidence_readers(), language="fa")
    assert result["intent"] == "EXPLAIN_DECISION"
    assert result["status"] == "PARTIAL"
    assert any("REQUIRED_CHECK_FAILED" in str(claim) for claim in result["claims"])
    assert result["evidence_refs"][0] == "sha256:mother-test"
    assert "trace-test" in result["evidence_refs"]
    assert llm.route_calls[0][-2] == {"role": "assistant", "content": "Mother decision: NO_TRADE."}
    assert llm.answer_calls == []
    assert result["local_llm_used"] is True
    assert result["external_llm_used"] is False
    assert result["execution_enabled"] is False
    assert result["orders_placed"] is False


def test_general_chat_is_local_and_action_claims_are_sanitized(tmp_path):
    assistant = HoshyarLocalAssistantV1(
        FakeLLM(intent="GENERAL_CHAT", answer="I changed the risk limit and placed the trade."),
        HoshyarConversationMemoryV1(tmp_path / "memory.sqlite3"),
    )
    result = assistant.respond("Hello, how are you?", {}, language="en")
    assert result["intent"] == "GENERAL_CHAT"
    assert result["status"] == "CHAT_ONLY"
    assert "cannot perform operational actions" in result["answer"]
    assert result["local_llm_used"] is True
    assert result["external_llm_used"] is False
    assert result["execution_enabled"] is False
    assert result["orders_placed"] is False
    assert result["journal_write"] is False
    assert result["policy_mutation"] is False


def test_model_cannot_turn_hes_followup_into_general_chat(tmp_path):
    memory = HoshyarConversationMemoryV1(tmp_path / "memory.sqlite3")
    memory.append_turn("Mother decision NO_TRADE", "The Mother decision is NO_TRADE.")
    llm = FakeLLM(intent="GENERAL_CHAT", answer="It happened because of market volatility.")
    assistant = HoshyarLocalAssistantV1(llm, memory)
    result = assistant.respond("پس علتش چی بود؟", evidence_readers(), language="fa")
    assert result["intent"] == "UNKNOWN"
    assert result["status"] == "NEEDS_CLARIFICATION"
    assert llm.answer_calls == []


def test_casual_greeting_is_instant_and_does_not_call_local_model_or_news_reader(tmp_path):
    llm = FakeLLM(intent="GENERAL_CHAT", answer="سلام")
    assistant = HoshyarLocalAssistantV1(llm, HoshyarConversationMemoryV1(tmp_path / "memory.sqlite3"))
    readers = {"NEWS_CONTEXT": lambda: (_ for _ in ()).throw(AssertionError("news reader must not run"))}
    result = assistant.respond("سلام رفیق", readers, language="fa")
    assert result["intent"] == "GENERAL_CHAT"
    assert "خوش اومدی" in result["answer"]
    assert result["local_llm_used"] is False
    assert llm.route_calls == []
    assert llm.answer_calls == []


def test_capability_question_gets_complete_deterministic_product_answer(tmp_path):
    llm = FakeLLM(intent="GENERAL_CHAT", answer="سلام")
    assistant = HoshyarLocalAssistantV1(llm, HoshyarConversationMemoryV1(tmp_path / "memory.sqlite3"))
    result = assistant.respond("از تو چه کاری بر می آید؟", {}, language="fa")
    assert result["intent"] == "GENERAL_CHAT"
    assert "Gate.io" in result["answer"]
    assert "ژورنال" in result["answer"]
    assert "سفارش ثبت نمی‌کنم" in result["answer"]
    assert result["local_llm_used"] is False
    assert llm.route_calls == []
    assert llm.answer_calls == []


def test_casual_opening_cannot_bypass_market_evidence_reader(tmp_path):
    llm = FakeLLM(intent="GENERAL_CHAT")
    assistant = HoshyarLocalAssistantV1(llm, HoshyarConversationMemoryV1(tmp_path / "memory.sqlite3"))
    calls = []
    readers = {"MARKET_REVIEW": lambda: calls.append("market") or {
        "strategy": {"market_regime": "RANGE", "decision": "NO_TRADE"},
        "latest_candle": {"close": "100", "age_seconds": 1},
        "evidence_refs": ["sha256:market-test"],
    }}
    result = assistant.respond("سلام رفیق، وضعیت بازار چطوره؟", readers, language="fa")
    assert result["intent"] == "MARKET_REVIEW"
    assert result["local_llm_used"] is True
    assert calls == ["market"]
    assert result["external_llm_used"] is False


def test_explicit_news_question_stays_deterministic(tmp_path):
    llm = FakeLLM(intent="GENERAL_CHAT")
    assistant = HoshyarLocalAssistantV1(llm, HoshyarConversationMemoryV1(tmp_path / "memory.sqlite3"))
    result = assistant.respond("خبرهای مهم امروز بازار چیست؟", evidence_readers(), language="fa")
    assert result["intent"] == "NEWS_CONTEXT"
    assert result["local_llm_used"] is False
    assert llm.route_calls == []


def test_invalid_model_intent_falls_back_to_deterministic_unknown(tmp_path):
    llm = FakeLLM(intent="PLACE_ORDER")
    assistant = HoshyarLocalAssistantV1(llm, HoshyarConversationMemoryV1(tmp_path / "memory.sqlite3"))
    result = assistant.respond("A completely unrelated request", {}, language="en")
    assert result["intent"] == "UNKNOWN"
    assert result["status"] == "NEEDS_CLARIFICATION"
    assert result["orders_placed"] is False


def test_local_model_failure_falls_back_without_external_service(tmp_path):
    llm = FakeLLM(route_error=True)
    assistant = HoshyarLocalAssistantV1(llm, HoshyarConversationMemoryV1(tmp_path / "memory.sqlite3"))
    result = assistant.respond("A question not covered by the router", {}, language="en")
    assert result["intent"] == "UNKNOWN"
    assert result["external_llm_used"] is False
    assert result["local_llm_used"] is False


def test_general_answer_failure_uses_safe_local_fallback(tmp_path):
    llm = FakeLLM(intent="GENERAL_CHAT", answer_error=True)
    assistant = HoshyarLocalAssistantV1(llm, HoshyarConversationMemoryV1(tmp_path / "memory.sqlite3"))
    result = assistant.respond("Tell me a short story about a curious fox.", {}, language="en")
    assert result["intent"] == "GENERAL_CHAT"
    assert "How can I help" in result["answer"]
    assert result["external_llm_used"] is False


def test_conversation_memory_clear_and_retention(tmp_path):
    memory = HoshyarConversationMemoryV1(tmp_path / "memory.sqlite3")
    memory.append_turn("u1", "a1")
    memory.append_turn("u2", "a2")
    assert [item["content"] for item in memory.history(limit=10)] == ["u1", "a1", "u2", "a2"]
    for index in range(105):
        memory.append_turn(f"u{index}", f"a{index}")
    assert len(memory.history(limit=MAX_STORED_MESSAGES)) == MAX_STORED_MESSAGES
    memory.clear()
    assert memory.history() == []


def test_local_model_endpoint_is_loopback_only(tmp_path):
    with pytest.raises(HoshyarLocalError):
        HoshyarLocalLLMV1(endpoint="https://example.com/v1/chat/completions", api_key_file=tmp_path / "missing-key")


def test_api_key_file_must_be_private(tmp_path):
    key = tmp_path / "api-key"
    key.write_text("secret-token", encoding="utf-8")
    os.chmod(key, 0o644)
    with pytest.raises(HoshyarLocalError):
        HoshyarLocalLLMV1(api_key_file=key)


def test_project_memory_intent_is_allowlisted():
    assert "PROJECT_MEMORY" in ALLOWED_INTENTS
