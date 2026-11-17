from __future__ import annotations

import json

from web import mother_chat_local_llm_v1 as llm


def _result():
    return {
        "intent": "ASK_STATUS",
        "status": "OK",
        "language": "fa",
        "answer": "وضعیت Mother: OBSERVATION_ONLY؛ تصمیم: NO_TRADE.",
        "claims": [
            {"label": "Mother status", "value": "OBSERVATION_ONLY"},
            {"label": "Mother decision", "value": "NO_TRADE"},
        ],
        "uncertainties": [],
    }


def test_disabled_provider_uses_deterministic_answer(monkeypatch):
    monkeypatch.delenv("HES_MOTHER_CHAT_LLM_ENABLED", raising=False)
    result = llm.render_grounded_answer("وضعیت؟", _result())
    assert result["llm_used"] is False
    assert result["llm_provider"] == "deterministic_fallback"
    assert result["answer"] == _result()["answer"]


def test_local_provider_rejects_non_loopback_endpoint(monkeypatch):
    monkeypatch.setenv("HES_MOTHER_CHAT_LLM_ENABLED", "1")
    monkeypatch.setenv("HES_MOTHER_CHAT_OLLAMA_URL", "https://example.com/api/chat")
    result = llm.render_grounded_answer("وضعیت؟", _result())
    assert result["llm_used"] is False
    assert result["llm_reason"] == "LOCAL_LLM_ENDPOINT_REJECTED"
    assert result["answer"] == _result()["answer"]


def test_local_provider_accepts_grounded_structured_answer(monkeypatch):
    monkeypatch.setenv("HES_MOTHER_CHAT_LLM_ENABLED", "1")
    response = {
        "message": {
            "content": json.dumps({
                "answer": "وضعیت Mother برابر OBSERVATION_ONLY است و تصمیم ثبت‌شده NO_TRADE است.",
                "evidence_ids": [0, 1],
            }, ensure_ascii=False)
        }
    }

    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, size=-1):
            return json.dumps(response, ensure_ascii=False).encode("utf-8")

    captured = {}
    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data)
        return FakeResponse()

    monkeypatch.setattr(llm, "urlopen", fake_urlopen)
    result = llm.render_grounded_answer(
        "وضعیت Mother چطور است؟",
        _result(),
        history=[
            {"role": "user", "content": "قبلاً درباره وضعیت پرسیدم"},
            {"role": "assistant", "content": "پاسخ قبلی"},
        ],
    )
    assert result["llm_used"] is True
    assert result["llm_provider"] == "ollama_local"
    assert result["llm_evidence_claim_ids"] == [0, 1]
    assert captured["url"] == llm.DEFAULT_ENDPOINT
    assert captured["payload"]["model"] == llm.DEFAULT_MODEL
    assert captured["payload"]["stream"] is False
    sent = json.loads(captured["payload"]["messages"][1]["content"])
    assert len(sent["history"]) == 2
    assert sent["current_question"] == "وضعیت Mother چطور است؟"


def test_local_provider_rejects_invalid_evidence_ids_and_falls_back(monkeypatch):
    monkeypatch.setenv("HES_MOTHER_CHAT_LLM_ENABLED", "1")
    response = {
        "message": {
            "content": json.dumps({
                "answer": "There is a new market fact.",
                "evidence_ids": [99],
            })
        }
    }

    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, size=-1):
            return json.dumps(response).encode()

    monkeypatch.setattr(llm, "urlopen", lambda *args, **kwargs: FakeResponse())
    result = llm.render_grounded_answer("status", _result())
    assert result["llm_used"] is False
    assert result["llm_reason"] == "LOCAL_LLM_EVIDENCE_ID_OUT_OF_RANGE"
    assert result["answer"] == _result()["answer"]


def test_blocked_or_change_proposal_never_calls_model(monkeypatch):
    monkeypatch.setenv("HES_MOTHER_CHAT_LLM_ENABLED", "1")
    def forbidden(*args, **kwargs):
        raise AssertionError("model must not be called")
    monkeypatch.setattr(llm, "urlopen", forbidden)
    blocked = _result() | {"status": "BLOCKED"}
    proposal = _result() | {"intent": "PREPARE_CHANGE"}
    assert llm.render_grounded_answer("status", blocked)["llm_used"] is False
    assert llm.render_grounded_answer("prepare change", proposal)["llm_used"] is False
