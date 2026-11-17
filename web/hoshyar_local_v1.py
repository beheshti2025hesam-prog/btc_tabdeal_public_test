"""Local-only HOSHYAR conversation layer for the existing Mother evidence boundary.

The model may classify a natural-language follow-up or answer general chat. It has
no tools, no order access and no production-write authority. HES facts continue to
come exclusively from the existing deterministic evidence readers.
"""
from __future__ import annotations

import json
import os
from contextlib import closing
import re
import sqlite3
import stat
import time
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from web.mother_chat_v1 import build_chat_response, classify_intent, _language


SCHEMA_VERSION = "hes.hoshyar.local.v1"
DEFAULT_ENDPOINT = "http://127.0.0.1:18082/v1/chat/completions"
DEFAULT_MODEL = "hoshyar-qwen35-2b-q4"
DEFAULT_MEMORY_DB = "/var/lib/hes-news-monitor/hoshyar-memory.sqlite3"
DEFAULT_API_KEY_FILE = "/var/lib/hes-news-monitor/hoshyar-llm-api-keys"
MAX_HISTORY_MESSAGES = 8
MAX_STORED_MESSAGES = 200
MEMORY_RETENTION_SECONDS = 30 * 24 * 60 * 60
ALLOWED_INTENTS = frozenset({
    "ASK_STATUS", "EXPLAIN_DECISION", "MARKET_REVIEW", "JOURNAL_REVIEW",
    "NEWS_CONTEXT", "DIAGNOSE", "PREPARE_CHANGE", "EXPLAIN_CHANGE_CONTROL", "PROJECT_MEMORY", "UNKNOWN", "GENERAL_CHAT",
})

ROUTE_SYSTEM_PROMPT = (
    "Classify the last user message using recent conversation history. Choose exactly one intent from: "
    "ASK_STATUS, EXPLAIN_DECISION, MARKET_REVIEW, JOURNAL_REVIEW, NEWS_CONTEXT, DIAGNOSE, "
    "PREPARE_CHANGE, EXPLAIN_CHANGE_CONTROL, PROJECT_MEMORY, UNKNOWN, GENERAL_CHAT. "
    "EXPLAIN_DECISION means why a recorded Mother/Strategy decision was made; "
    "EXPLAIN_CHANGE_CONTROL means the owner's approval process for a proposed change; "
    "PROJECT_MEMORY means retrieve an earlier project decision/checkpoint. "
    "GENERAL_CHAT is only ordinary non-HES conversation. Resolve short follow-ups from history; if unclear choose UNKNOWN. "
    "Return JSON only with the single key intent. No explanation, no answer, no facts."
)
GENERAL_CHAT_SYSTEM_PROMPT = (
    "You are HES Trade AI, a private local assistant. Reply in the user's selected language with one concise, natural sentence. "
    "Do not state current HES facts or claim actions. HES facts are answered by the evidence readers, not by you. "
    "Return JSON only with the single key answer."
)

_ACTION_CLAIM_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"\b(?:i|we)\s+(?:have\s+)?(?:placed|submitted|executed|opened|closed)\s+(?:the\s+)?(?:order|trade)",
    r"\b(?:i|we)\s+(?:have\s+)?(?:changed|updated|edited|merged|deployed|published)\s+(?:the\s+)?(?:production|risk|strategy|code|system)",
    r"\b(?:order|trade)\s+(?:has been|was)\s+(?:placed|submitted|executed)",
    r"(?:سفارش|معامله).{0,24}(?:ثبت شد|اجرا شد|ارسال شد)",
    r"(?:تغییر|ریسک|استراتژی|کد|نسخه عملیاتی).{0,30}(?:اعمال شد|منتشر شد|استقرار یافت)",
    r"(?:auftrag|handel).{0,30}(?:ausgeführt|platziert|abgeschickt)",
    r"(?:ordre|transaction).{0,30}(?:exécuté|passé|envoyé)",
))
_CASUAL_GREETING_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"(?:^|[\s،,])(?:سلام(?:\s+رفیق)?|چه\s+خبری?|خوبی|چطوری|حالت\s+چطوره)(?:$|[\s؟?!.,])",
    r"\b(?:hi|hello|hey|how are you|what's up|how's it going)\b",
    r"\b(?:hallo|guten tag|wie geht'?s|was gibt'?s neues)\b",
    r"\b(?:salut|bonjour|ça va|quoi de neuf)\b",
))
_EXPLICIT_NEWS_TERMS = ("اخبار", "خبرهای", "news", "headlines", "nachrichten", "actualités", "nouvelles")


def _is_casual_greeting(message: str) -> bool:
    text = message.casefold().strip()
    if any(term in text for term in _EXPLICIT_NEWS_TERMS):
        return False
    return any(pattern.search(text) for pattern in _CASUAL_GREETING_PATTERNS)


_HES_CONTEXT_TERMS = (
    "hes", "mother", "gate.io", "btc", "bitcoin", "no_trade", "strategy v2", "journal", "risk gate",
    "signal", "trade", "market", "decision", "ترید", "معامله", "مادر", "ایجنت", "تصمیم", "بازار",
    "ژورنال", "ریسک", "سیگنال", "گیت.آی‌او", "گیت ای او", "کندل", "استراتژی", "اخبار بازار",
)
_CONTEXTUAL_FOLLOWUP_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"(?:پس|بنابراین).{0,18}(?:علت|دلیل|چرا)|(?:علتش|دلیلش|چرایش|همون|در موردش|راجع بهش)",
    r"\b(?:why was that|what about that|and why|the reason|why did it)\b",
    r"\b(?:warum das|weshalb das|und warum|der grund dazu)\b",
    r"\b(?:pourquoi cela|et pourquoi|la raison|pourquoi alors)\b",
))


def _has_hes_context(message: str) -> bool:
    text = str(message or "").casefold()
    return any(term in text for term in _HES_CONTEXT_TERMS)


def _is_contextual_followup(message: str) -> bool:
    return any(pattern.search(str(message or "")) for pattern in _CONTEXTUAL_FOLLOWUP_PATTERNS)


class HoshyarLocalError(RuntimeError):
    pass


class HoshyarLocalLLMV1:
    """Minimal OpenAI-compatible client restricted to the local loopback endpoint."""

    def __init__(self, *, endpoint: str | None = None, model: str | None = None, timeout: float = 75.0, api_key_file: str | os.PathLike[str] | None = None):
        self.endpoint = endpoint or os.environ.get("HES_HOSHYAR_LOCAL_LLM_URL", DEFAULT_ENDPOINT)
        self.model = model or os.environ.get("HES_HOSHYAR_LOCAL_LLM_MODEL", DEFAULT_MODEL)
        self.timeout = max(5.0, min(float(timeout), 120.0))
        key_path = api_key_file if api_key_file is not None else os.environ.get("HES_HOSHYAR_LOCAL_LLM_API_KEY_FILE", DEFAULT_API_KEY_FILE)
        self.api_key_file = Path(key_path)
        self.api_key = None
        if self.api_key_file.exists():
            descriptor = None
            try:
                descriptor = os.open(self.api_key_file, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > 4096:
                    raise HoshyarLocalError("HOSHYAR_API_KEY_PERMISSIONS_INVALID")
                raw_key = os.read(descriptor, 4097)
                if len(raw_key) > 4096:
                    raise HoshyarLocalError("HOSHYAR_API_KEY_FILE_TOO_LARGE")
                key_text = raw_key.decode("utf-8")
                self.api_key = next((line.strip() for line in key_text.splitlines() if line.strip() and not line.lstrip().startswith("#")), None)
            except HoshyarLocalError:
                raise
            except (OSError, UnicodeDecodeError) as exc:
                raise HoshyarLocalError("HOSHYAR_API_KEY_FILE_UNAVAILABLE") from exc
            finally:
                if descriptor is not None:
                    os.close(descriptor)
            if not self.api_key:
                raise HoshyarLocalError("HOSHYAR_API_KEY_EMPTY")
        parsed = urlsplit(self.endpoint)
        if (
            parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
            or parsed.port != 18082 or parsed.path != "/v1/chat/completions"
            or parsed.username or parsed.password or parsed.query or parsed.fragment
        ):
            raise HoshyarLocalError("HOSHYAR_LOCAL_ENDPOINT_REJECTED")
        if not self.model or len(self.model) > 100:
            raise HoshyarLocalError("HOSHYAR_MODEL_ID_INVALID")

    def _post(self, messages: list[dict[str, str]], *, max_tokens: int, response_format: dict[str, Any], temperature: float = 0.1) -> str:
        if not isinstance(messages, list) or not 1 <= len(messages) <= 12:
            raise HoshyarLocalError("HOSHYAR_MESSAGES_INVALID")
        for message in messages:
            if (
                not isinstance(message, dict)
                or message.get("role") not in {"system", "user", "assistant"}
                or not isinstance(message.get("content"), str)
                or len(message["content"]) > 5000
            ):
                raise HoshyarLocalError("HOSHYAR_MESSAGES_INVALID")
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": max(0.0, min(float(temperature), 0.7)),
            "max_tokens": max(16, min(int(max_tokens), 100)),
            "stream": False,
            "response_format": response_format,
        }
        request = Request(
            self.endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json", "Accept": "application/json",
                **({"Authorization": "Bearer " + self.api_key} if self.api_key else {}),
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read(32_769)
        except (OSError, URLError, TimeoutError) as exc:
            raise HoshyarLocalError("HOSHYAR_LOCAL_MODEL_UNAVAILABLE") from exc
        if len(raw) > 32_768:
            raise HoshyarLocalError("HOSHYAR_LOCAL_RESPONSE_TOO_LARGE")
        try:
            payload = json.loads(raw.decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise HoshyarLocalError("HOSHYAR_LOCAL_RESPONSE_INVALID") from exc
        if not isinstance(content, str) or not content.strip() or len(content) > 8_000:
            raise HoshyarLocalError("HOSHYAR_LOCAL_CONTENT_INVALID")
        return content.strip()

    def route_intent(self, messages: list[dict[str, str]]) -> str:
        schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "hoshyar_intent",
                "schema": {
                    "type": "object",
                    "properties": {"intent": {"type": "string", "enum": sorted(ALLOWED_INTENTS)}},
                    "required": ["intent"],
                    "additionalProperties": False,
                },
            },
        }
        content = self._post(messages, max_tokens=24, response_format=schema, temperature=0.1)
        try:
            payload = json.loads(content)
        except (TypeError, json.JSONDecodeError) as exc:
            raise HoshyarLocalError("HOSHYAR_LOCAL_INTENT_INVALID") from exc
        if not isinstance(payload, Mapping) or set(payload) != {"intent"} or payload.get("intent") not in ALLOWED_INTENTS:
            raise HoshyarLocalError("HOSHYAR_LOCAL_INTENT_INVALID")
        return str(payload["intent"])

    def general_answer(self, messages: list[dict[str, str]]) -> str:
        schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "hoshyar_answer",
                "schema": {
                    "type": "object",
                    "properties": {"answer": {"type": "string", "maxLength": 500}},
                    "required": ["answer"],
                    "additionalProperties": False,
                },
            },
        }
        content = self._post(messages, max_tokens=64, response_format=schema, temperature=0.2)
        try:
            payload = json.loads(content)
        except (TypeError, json.JSONDecodeError) as exc:
            raise HoshyarLocalError("HOSHYAR_LOCAL_ANSWER_INVALID") from exc
        answer = payload.get("answer") if isinstance(payload, Mapping) and set(payload) == {"answer"} else None
        if not isinstance(answer, str) or len(answer) > 500:
            raise HoshyarLocalError("HOSHYAR_LOCAL_ANSWER_INVALID")
        return answer.strip()

class HoshyarConversationMemoryV1:
    """Single-owner local SQLite conversation memory with bounded retention."""

    def __init__(self, path: str | os.PathLike[str] | None = None):
        self.path = Path(path or os.environ.get("HES_HOSHYAR_MEMORY_DB", DEFAULT_MEMORY_DB))

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        connection = sqlite3.connect(str(self.path), timeout=3.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=3000")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS messages ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT NOT NULL CHECK(role IN ('user','assistant')), "
            "content TEXT NOT NULL, created_at INTEGER NOT NULL)"
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_hoshyar_messages_created ON messages(id)")
        connection.commit()
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            connection.close()
            raise HoshyarLocalError("HOSHYAR_MEMORY_PERMISSIONS_INVALID")
        return connection

    def history(self, limit: int = MAX_HISTORY_MESSAGES) -> list[dict[str, str]]:
        limit = max(0, min(int(limit), MAX_STORED_MESSAGES))
        if not limit:
            return []
        try:
            with closing(self._connect()) as db:
                rows = db.execute(
                    "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
        except (OSError, sqlite3.Error) as exc:
            raise HoshyarLocalError("HOSHYAR_MEMORY_UNAVAILABLE") from exc

    def append_turn(self, user_message: str, assistant_message: str) -> None:
        now = int(time.time())
        try:
            with closing(self._connect()) as db:
                db.executemany(
                    "INSERT INTO messages(role, content, created_at) VALUES(?,?,?)",
                    [("user", user_message[:1000], now), ("assistant", assistant_message[:4000], now)],
                )
                db.execute("DELETE FROM messages WHERE created_at < ?", (now - MEMORY_RETENTION_SECONDS,))
                db.execute(
                    "DELETE FROM messages WHERE id NOT IN (SELECT id FROM messages ORDER BY id DESC LIMIT ?)",
                    (MAX_STORED_MESSAGES,),
                )
                db.commit()
        except (OSError, sqlite3.Error) as exc:
            raise HoshyarLocalError("HOSHYAR_MEMORY_WRITE_FAILED") from exc

    def clear(self) -> None:
        try:
            with closing(self._connect()) as db:
                db.execute("DELETE FROM messages")
                db.commit()
        except (OSError, sqlite3.Error) as exc:
            raise HoshyarLocalError("HOSHYAR_MEMORY_CLEAR_FAILED") from exc


class HoshyarLocalAssistantV1:
    """Conversation router: local model selects a fixed intent; existing readers retain authority."""

    def __init__(self, llm: HoshyarLocalLLMV1, memory: HoshyarConversationMemoryV1):
        self.llm = llm
        self.memory = memory

    @staticmethod
    def _safe_general_answer(answer: str, language: str) -> str:
        if not answer:
            return {
                "fa": "سلام، در خدمتم. چه کمکی از دستم برمی‌آید؟",
                "de": "Hallo, ich bin da. Wie kann ich helfen?",
                "fr": "Bonjour, je suis là. Comment puis-je aider ?",
                "en": "Hello, I'm here. How can I help?",
            }.get(language, "Hello, I'm here. How can I help?")
        if any(pattern.search(answer) for pattern in _ACTION_CLAIM_PATTERNS):
            return {
                "fa": "می‌توانم توضیح بدهم و پیشنهاد آماده کنم؛ اما هیچ اقدام عملیاتی انجام نمی‌دهم. هر تغییر عملیاتی به تأیید صریح همان تغییر از طرف صاحب پروژه نیاز دارد.",
                "de": "Ich kann erklären und Vorschläge vorbereiten, aber keine operativen Änderungen ausführen. Jede Änderung benötigt die ausdrückliche Freigabe genau dieser Änderung durch den Eigentümer.",
                "fr": "Je peux expliquer et préparer des propositions, mais je n'effectue aucune action opérationnelle. Toute modification exige l'approbation explicite de cette modification précise par le propriétaire.",
                "en": "I can explain and prepare proposals, but I cannot perform operational actions. Any change requires the owner's explicit approval of that exact change.",
            }.get(language, "I can explain and prepare proposals, but I cannot perform operational actions.")
        return answer

    def respond(
        self,
        message: str,
        readers: Mapping[str, Callable[[], Mapping[str, Any]]],
        *,
        language: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(message, str) or not message.strip() or len(message) > 1000:
            raise ValueError("CHAT_MESSAGE_INVALID")
        if language not in {None, "auto", "fa", "en", "de", "fr"}:
            raise ValueError("CHAT_LANGUAGE_INVALID")
        effective_language = language if language in {"fa", "en", "de", "fr"} else _language(message)
        history: list[dict[str, str]] = []
        memory_ok = False
        try:
            history = self.memory.history()
            memory_ok = True
        except HoshyarLocalError:
            history = []

        deterministic_intent = "UNKNOWN" if _is_casual_greeting(message) else classify_intent(message)
        local_used = False
        intent = deterministic_intent
        if deterministic_intent == "UNKNOWN":
            messages = [
                {"role": "system", "content": ROUTE_SYSTEM_PROMPT},
                *history[-MAX_HISTORY_MESSAGES:],
                {"role": "user", "content": message},
            ]
            try:
                intent = self.llm.route_intent(messages)
                local_used = True
            except HoshyarLocalError:
                intent = "UNKNOWN"

        if intent not in ALLOWED_INTENTS:
            intent = "UNKNOWN"
        if intent == "GENERAL_CHAT":
            has_recent_hes_context = any(_has_hes_context(item.get("content", "")) for item in history[-4:])
            if _has_hes_context(message) or (
                not _is_casual_greeting(message)
                and _is_contextual_followup(message)
                and has_recent_hes_context
            ):
                intent = "UNKNOWN"
            else:
                system_prompt = GENERAL_CHAT_SYSTEM_PROMPT + f" Selected response language: {effective_language}."
                messages = [
                    {"role": "system", "content": system_prompt},
                    *history[-MAX_HISTORY_MESSAGES:],
                    {"role": "user", "content": message},
                ]
                try:
                    answer = self.llm.general_answer(messages)
                    local_used = True
                except HoshyarLocalError:
                    answer = ""
                answer = self._safe_general_answer(answer, effective_language)
                result = {
                    "schema_version": "hes.mother_chat.v1",
                    "router_version": "hes-hoshyar-local-llm-v2",
                    "intent": "GENERAL_CHAT", "status": "CHAT_ONLY", "answer": answer, "language": effective_language,
                    "claims": [], "uncertainties": [], "evidence_refs": [], "trace_id": "",
                    "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "external_llm_used": False, "execution_enabled": False,
                    "orders_placed": False, "journal_write": False, "policy_mutation": False,
                    "local_llm_used": local_used, "conversation_memory_used": memory_ok,
                }
        if intent != "GENERAL_CHAT":
            if intent in ALLOWED_INTENTS - {"UNKNOWN"}:
                result = build_chat_response(message, readers, language=language, intent_override=intent)
            else:
                result = build_chat_response(message, readers, language=language)
            result["local_llm_used"] = local_used
            result["conversation_memory_used"] = memory_ok

        if memory_ok:
            try:
                self.memory.append_turn(message, str(result.get("answer") or ""))
            except HoshyarLocalError:
                result["conversation_memory_used"] = False
                result.setdefault("uncertainties", []).append("Local conversation memory could not be saved.")
        result["external_llm_used"] = False
        result["execution_enabled"] = False
        result["orders_placed"] = False
        result["journal_write"] = False
        result["policy_mutation"] = False
        return result

    def clear_memory(self) -> None:
        self.memory.clear()

    def read_history(self) -> list[dict[str, str]]:
        return self.memory.history(limit=MAX_STORED_MESSAGES)
