"""Free, deterministic, read-only Mother Command Center boundary.

This module intentionally makes no LLM/provider calls. It classifies a bounded
set of intents and formats only evidence supplied by existing HES readers.
Authentication is a short-lived, signed, HttpOnly cookie backed by a local
operator-created token file. It has no market, strategy, journal-write or order
authority.
"""
from __future__ import annotations

from collections import deque
from http.cookies import SimpleCookie
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit
import errno
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import time


SCHEMA_VERSION = "hes.mother_chat.v1"
ROUTER_VERSION = "hes-mother-chat-deterministic-router-v1"
COOKIE_NAME = "hes_mother_session"
SESSION_MAX_AGE_SECONDS = 1800
MAX_MESSAGE_CHARS = 1000
MAX_BODY_BYTES = 4096
DEFAULT_TOKEN_FILE = "/var/lib/hes-news-monitor/mother-chat/token"


class MotherChatError(ValueError):
    def __init__(self, code: str, http_status: int = 400):
        super().__init__(code)
        self.code = code
        self.http_status = http_status


_INTENT_TERMS = {
    "NEWS_CONTEXT": ("اخبار", "خبر", "رویداد خبری", "news", "headline", "nachrichten", "meldung", "actualités", "nouvelles"),
    "JOURNAL_REVIEW": ("ژورنال", "نتایج معاملات", "نتیجه معاملات", "عملکرد ترید", "برد و باخت", "journal", "outcomes", "performance", "ergebnisse", "résultats"),
    "DIAGNOSE": ("عیب یابی", "عیب‌یابی", "خطا", "اشکال", "مشکل سیستم", "diagnose", "diagnostics", "error", "fault", "fehler", "erreur", "panne"),
    "ASK_STATUS": ("وضعیت", "سلامت", "سرویس ها", "سرویس‌ها", "الان چطوره", "status", "health", "services", "gesundheit", "dienste", "statut", "santé", "services"),
    "EXPLAIN_DECISION": ("چرا تصمیم", "دلیل تصمیم", "علت تصمیم", "چرا مادر", "چرا عدم ترید", "چرا no_trade", "تصمیم مادر", "تصمیم ایجنت", "explain", "why decision", "why no trade", "decision", "mother decision", "warum entscheidung", "warum no trade", "grund", "entscheidung", "pourquoi décision", "pourquoi no trade", "décision", "raison"),
    "MARKET_REVIEW": ("تحلیل بازار", "وضعیت بازار", "بازار", "قیمت", "کندل", "روند", "market", "candles", "price", "regime", "markt", "kerzen", "kurs", "trend", "marché", "bougie", "prix", "tendance"),
    "PREPARE_CHANGE": ("پیشنهاد تغییر", "پیشنویس تغییر", "پیش‌نویس تغییر", "طراحی تغییر", "prepare change", "draft change", "änderung vorbereiten", "proposition de changement", "préparer une modification"),
}


def _language(message: str) -> str:
    text = message.casefold()
    if any("\u0600" <= ch <= "\u06ff" for ch in message):
        return "fa"
    if re.search(r"\b(warum|weshalb|markt|kerzen|kurs|entscheidung|nachrichten|fehler|gesundheit|ergebnisse|änderung|dienste)\b", text):
        return "de"
    if re.search(r"\b(pourquoi|marché|bougie|prix|décision|actualités|erreur|statut|santé|résultats|proposition|changement)\b", text):
        return "fr"
    return "en"


def classify_intent(message: str) -> str:
    """Classify only explicit, supported command-center intents."""
    if not isinstance(message, str):
        return "UNKNOWN"
    text = " ".join(message.casefold().strip().split())
    if not text or len(text) > MAX_MESSAGE_CHARS:
        return "UNKNOWN"
    matches = []
    for intent, terms in _INTENT_TERMS.items():
        for term in terms:
            if any("\u0600" <= ch <= "\u06ff" for ch in term):
                found = term in text
            else:
                found = re.search(r"(?<![a-z0-9_])" + re.escape(term) + r"(?![a-z0-9_])", text) is not None
            if found:
                matches.append(intent)
                break
    unique = tuple(dict.fromkeys(matches))
    specific = tuple(intent for intent in unique if intent not in {"ASK_STATUS", "MARKET_REVIEW"})
    if len(specific) == 1:
        return specific[0]
    if len(specific) > 1:
        return "UNKNOWN"
    if "MARKET_REVIEW" in unique:
        return "MARKET_REVIEW"
    return "ASK_STATUS" if "ASK_STATUS" in unique else "UNKNOWN"


class MotherChatSecurityV1:
    """Local token-file authentication, origin checks, signed expiring sessions and rate limits."""

    def __init__(self, token_file: str | os.PathLike[str] | None = None):
        self.token_file = Path(token_file or os.environ.get("HES_MOTHER_CHAT_TOKEN_FILE", DEFAULT_TOKEN_FILE))
        self._lock = Lock()
        self._events: dict[tuple[str, str], deque[float]] = {}

    @staticmethod
    def check_origin(headers: Any) -> str:
        origin = headers.get("Origin", "")
        host = headers.get("Host", "")
        try:
            parsed = urlsplit(origin)
        except ValueError as exc:
            raise MotherChatError("CHAT_ORIGIN_REJECTED", 403) from exc
        if (
            not origin or not host or parsed.scheme not in {"http", "https"}
            or parsed.netloc.casefold() != host.casefold()
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
        ):
            raise MotherChatError("CHAT_ORIGIN_REJECTED", 403)
        fetch_site = headers.get("Sec-Fetch-Site")
        if fetch_site and fetch_site not in {"same-origin", "none"}:
            raise MotherChatError("CHAT_CROSS_SITE_REQUEST_REJECTED", 403)
        return parsed.scheme

    def check_rate_limit(self, client: str, action: str, *, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        key = (action, client or "unknown")
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and now - events[0] >= window_seconds:
                events.popleft()
            if len(events) >= limit:
                raise MotherChatError("CHAT_RATE_LIMITED", 429)
            events.append(now)
            if len(self._events) > 4096:
                cutoff = now - max(window_seconds, 600)
                self._events = {
                    k: v for k, v in self._events.items()
                    if v and v[-1] >= cutoff
                }

    def _load_secret(self) -> bytes:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(self.token_file, flags)
        except FileNotFoundError as exc:
            raise MotherChatError("CHAT_NOT_CONFIGURED", 503) from exc
        except OSError as exc:
            code = "CHAT_TOKEN_FILE_INVALID" if exc.errno == errno.ELOOP else "CHAT_TOKEN_FILE_UNAVAILABLE"
            raise MotherChatError(code, 503) from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise MotherChatError("CHAT_TOKEN_FILE_INVALID", 503)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise MotherChatError("CHAT_TOKEN_FILE_PERMISSIONS_INVALID", 503)
            if info.st_size > 256:
                raise MotherChatError("CHAT_TOKEN_FILE_INVALID", 503)
            raw = os.read(fd, 257)
            if len(raw) > 256:
                raise MotherChatError("CHAT_TOKEN_FILE_INVALID", 503)
        finally:
            os.close(fd)
        try:
            secret = raw.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise MotherChatError("CHAT_TOKEN_FILE_INVALID", 503) from exc
        if len(secret) < 32 or len(secret) > 256:
            raise MotherChatError("CHAT_TOKEN_FILE_INVALID", 503)
        return secret.encode("utf-8")

    def create_session_cookie(self, supplied_token: Any, *, secure: bool = False) -> str:
        if not isinstance(supplied_token, str) or not 32 <= len(supplied_token) <= 256:
            raise MotherChatError("CHAT_AUTHENTICATION_FAILED", 401)
        secret = self._load_secret()
        if not hmac.compare_digest(supplied_token.encode("utf-8"), secret):
            raise MotherChatError("CHAT_AUTHENTICATION_FAILED", 401)
        expires = int(time.time()) + SESSION_MAX_AGE_SECONDS
        nonce = secrets.token_urlsafe(24)
        payload = f"{expires}.{nonce}"
        signature = hmac.new(secret, payload.encode("ascii"), hashlib.sha256).hexdigest()
        cookie = f"{COOKIE_NAME}={payload}.{signature}; Max-Age={SESSION_MAX_AGE_SECONDS}; Path=/api/mother-chat; HttpOnly; SameSite=Strict"
        if secure:
            cookie += "; Secure"
        return cookie

    def has_valid_session(self, headers: Any) -> bool:
        try:
            secret = self._load_secret()
            parsed = SimpleCookie()
            parsed.load(headers.get("Cookie", ""))
            morsel = parsed.get(COOKIE_NAME)
            if morsel is None:
                return False
            expires_text, nonce, signature = morsel.value.split(".", 2)
            expires = int(expires_text)
            now = int(time.time())
            if expires < now or expires > now + SESSION_MAX_AGE_SECONDS + 60:
                return False
            payload = f"{expires_text}.{nonce}"
            expected = hmac.new(secret, payload.encode("ascii"), hashlib.sha256).hexdigest()
            return hmac.compare_digest(signature, expected)
        except (MotherChatError, ValueError, TypeError):
            return False

    @staticmethod
    def clear_session_cookie(*, secure: bool = False) -> str:
        cookie = f"{COOKIE_NAME}=; Max-Age=0; Path=/api/mother-chat; HttpOnly; SameSite=Strict"
        return cookie + ("; Secure" if secure else "")


def read_json_body(handler: Any, *, max_bytes: int = MAX_BODY_BYTES) -> dict[str, Any]:
    content_type = handler.headers.get("Content-Type", "").split(";", 1)[0].strip().casefold()
    if content_type != "application/json":
        raise MotherChatError("CHAT_JSON_REQUIRED", 415)
    try:
        length = int(handler.headers.get("Content-Length", ""))
    except (TypeError, ValueError):
        raise MotherChatError("CHAT_CONTENT_LENGTH_INVALID", 400)
    if length < 1 or length > max_bytes:
        raise MotherChatError("CHAT_BODY_SIZE_INVALID", 413)
    raw = handler.rfile.read(length)
    if len(raw) != length:
        raise MotherChatError("CHAT_BODY_TRUNCATED", 400)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise MotherChatError("CHAT_JSON_INVALID", 400)
    if not isinstance(value, dict):
        raise MotherChatError("CHAT_JSON_OBJECT_REQUIRED", 400)
    return value


def _refs(*values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, str) and value and value not in result:
            result.append(value)
    return result[:32]


def _claim(label: str, value: Any, ref: str | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {"label": label, "value": value}
    if ref:
        row["evidence_ref"] = ref
    return row


def build_chat_response(
    message: str,
    readers: Mapping[str, Callable[[], Mapping[str, Any]]],
    *,
    now: float | None = None,
) -> dict[str, Any]:
    """Return a bounded, evidence-only response; never invokes a model or mutates state."""
    if not isinstance(message, str) or not message.strip() or len(message) > MAX_MESSAGE_CHARS:
        raise MotherChatError("CHAT_MESSAGE_INVALID", 400)
    intent = classify_intent(message)
    language = _language(message)
    is_fa = language == "fa"
    if intent == "UNKNOWN":
        answers = {
            "fa": "درخواست را دقیق‌تر مشخص کن: وضعیت، توضیح تصمیم، بررسی بازار، ژورنال، اخبار یا عیب‌یابی.",
            "de": "Bitte wähle eine unterstützte Aufgabe: Status, Entscheidung erklären, Markt, Journal, Nachrichten oder Diagnose.",
            "fr": "Précisez une tâche prise en charge : statut, explication de décision, marché, journal, actualités ou diagnostic.",
            "en": "Please specify one supported task: status, explain the decision, market review, journal, news, or diagnostics.",
        }
        answer = answers[language]
        return _response(intent, "NEEDS_CLARIFICATION", answer, [], [], "", now)
    if intent == "PREPARE_CHANGE":
        answers = {
            "fa": "برای تهیهٔ پیش‌نویس، نام بخش و تغییر موردنظر را مشخص کن. این رابط فقط پیش‌نویس می‌سازد و هیچ تغییری را اعمال نمی‌کند.",
            "de": "Nenne die Komponente und die gewünschte Änderung. Diese Oberfläche kann nur einen Vorschlag erstellen und nichts anwenden.",
            "fr": "Indiquez le composant et la modification souhaitée. Cette interface peut préparer une proposition, mais ne peut rien appliquer.",
            "en": "Specify the component and requested change. This interface can prepare a proposal only; it cannot apply changes.",
        }
        answer = answers[language]
        return _response(intent, "NEEDS_CLARIFICATION", answer, [], [], "", now)
    reader = readers.get(intent)
    if not callable(reader):
        return _response(intent, "BLOCKED", "Evidence reader is not configured.", [], ["CHAT_READER_NOT_CONFIGURED"], "", now)
    try:
        data = reader()
    except Exception:
        return _response(
            intent, "BLOCKED",
            {"fa": "شواهد معتبر در دسترس نیست؛ پاسخ با حالت ایمن متوقف شد.", "de": "Verifizierte Nachweise sind nicht verfügbar; die Anfrage wurde sicher blockiert.", "fr": "Les preuves vérifiées sont indisponibles ; la demande a été bloquée par sécurité.", "en": "Verified evidence is unavailable; the request was safely blocked."}[language],
            [], ["CHAT_EVIDENCE_UNAVAILABLE"], "", now,
        )
    if not isinstance(data, Mapping):
        return _response(intent, "BLOCKED", "Evidence payload is invalid.", [], ["CHAT_EVIDENCE_INVALID"], "", now)

    claims: list[dict[str, Any]] = []
    uncertainties: list[str] = []
    evidence = data.get("evidence_refs", [])
    if not isinstance(evidence, list):
        evidence = []
    trace_id = str(data.get("trace_id") or "")
    status = "OK"

    if intent in {"ASK_STATUS", "EXPLAIN_DECISION"}:
        mother = data.get("mother", {})
        strategy = data.get("strategy", {})
        if not isinstance(mother, Mapping) or not isinstance(strategy, Mapping):
            return _response(intent, "BLOCKED", "Mother/Strategy evidence is malformed.", [], ["CHAT_EVIDENCE_INVALID"], trace_id, now)
        m_status = str(mother.get("status") or "UNKNOWN")
        decision = str(mother.get("decision") or "NO_TRADE")
        s_status = str(strategy.get("status") or "UNKNOWN")
        witness = mother.get("witness", {})
        witness_ok = isinstance(witness, Mapping) and witness.get("verified") is True
        paper_gate = mother.get("paper_execution_gate", {})
        paper_status = str(paper_gate.get("status") or "BLOCKED") if isinstance(paper_gate, Mapping) else "BLOCKED"
        paper_reasons = paper_gate.get("reason_codes", []) if isinstance(paper_gate, Mapping) else []
        claims.extend([
            _claim("Mother status", m_status, str(mother.get("trace_id") or "") or None),
            _claim("Mother decision", decision, str(mother.get("audit_sha256") or "") or None),
            _claim("Live strategy runtime", s_status, str(strategy.get("snapshot_sha256") or "") or None),
            _claim("Independent witness", "VERIFIED" if witness_ok else "NOT VERIFIED"),
            _claim("Paper simulation gate", paper_status),
            _claim("Paper gate blockers", paper_reasons if isinstance(paper_reasons, list) else []),
            _claim("Sequence evidence", mother.get("sequence_validation", {}).get("basis", "UNKNOWN") if isinstance(mother.get("sequence_validation"), Mapping) else "UNKNOWN"),
            _claim("Trade sequence used", mother.get("sequence_validation", {}).get("trade_sequence_used", True) if isinstance(mother.get("sequence_validation"), Mapping) else True),
        ])
        reasons = mother.get("reason_codes", [])
        if isinstance(reasons, list):
            claims.append(_claim("Mother reason codes", reasons))
        if m_status != "OBSERVATION_ONLY" or not witness_ok or s_status not in {"VERIFIED", "LIVE_RUNTIME"} or paper_status != "READY_FOR_PAPER_SIMULATION":
            status = "PARTIAL"
            uncertainties.append("Mother, specialist, witness or paper-simulation gates are not fully ready.")
        if intent == "EXPLAIN_DECISION":
            stages = mother.get("stages", [])
            if isinstance(stages, list):
                for stage in stages:
                    if isinstance(stage, Mapping):
                        claims.append(_claim(
                            "Stage " + str(stage.get("agent") or "unknown"),
                            str(stage.get("state") or "UNKNOWN")
                            + ((" · " + ", ".join(stage.get("reason_codes", []))) if isinstance(stage.get("reason_codes"), list) else ""),
                        ))
            answers = {
                "fa": f"تصمیم زندهٔ Mother: {decision}. وضعیت: {m_status}. شاهد مستقل: {'تأیید' if witness_ok else 'تأییدنشده'}. دروازهٔ شبیه‌سازی کاغذی: {paper_status}. اجرای واقعی و ثبت سفارش غیرفعال است.",
                "de": f"Live-Mother-Entscheidung: {decision}. Status: {m_status}. Unabhängiger Zeuge: {'verifiziert' if witness_ok else 'nicht verifiziert'}. Paper-Simulationsgate: {paper_status}. Live-Ausführung und Orderübermittlung bleiben deaktiviert.",
                "fr": f"Décision Mother en direct : {decision}. Statut : {m_status}. Témoin indépendant : {'vérifié' if witness_ok else 'non vérifié'}. Porte de simulation papier : {paper_status}. L’exécution réelle et l’envoi d’ordres restent désactivés.",
                "en": f"Live Mother decision: {decision}. Status: {m_status}. Independent witness: {'verified' if witness_ok else 'not verified'}. Paper simulation gate: {paper_status}. Live execution and order submission remain disabled.",
            }
            answer = answers[language]
        else:
            news = data.get("news", {})
            news_monitor = news.get("monitor", {}) if isinstance(news, Mapping) else {}
            news_status = news_monitor.get("status", "UNKNOWN") if isinstance(news_monitor, Mapping) else "UNKNOWN"
            claims.append(_claim("News monitor", str(news_status)))
            answers = {
                "fa": f"وضعیت زندهٔ Mother: {m_status}؛ تصمیم: {decision}؛ موتور استراتژی: {s_status}؛ دروازهٔ شبیه‌سازی کاغذی: {paper_status}؛ پایش اخبار: {news_status}. منبع تحلیل بازار فقط Gate.io Public Spot BTC_USDT است؛ اجرا خاموش است.",
                "de": f"Mother: {m_status}; Entscheidung: {decision}; Strategielaufzeit: {s_status}; Paper-Simulationsgate: {paper_status}; News-Monitor: {news_status}. Gate.io Public Spot BTC_USDT bleibt die einzige Analysequelle; Ausführung ist deaktiviert.",
                "fr": f"Mother : {m_status} ; décision : {decision} ; moteur de stratégie : {s_status} ; porte de simulation papier : {paper_status} ; surveillance des actualités : {news_status}. Gate.io Public Spot BTC_USDT reste l’unique source d’analyse ; l’exécution est désactivée.",
                "en": f"Mother: {m_status}; decision: {decision}; Strategy runtime: {s_status}; Paper simulation gate: {paper_status}; News monitor: {news_status}. Gate.io Public Spot BTC_USDT remains the sole analysis source; execution is off.",
            }
            answer = answers[language]

    elif intent == "MARKET_REVIEW":
        strategy = data.get("strategy", {})
        candle = data.get("latest_candle", {})
        if not isinstance(strategy, Mapping) or not isinstance(candle, Mapping):
            return _response(intent, "BLOCKED", "Market evidence is malformed.", [], ["CHAT_EVIDENCE_INVALID"], trace_id, now)
        regime = str(strategy.get("market_regime") or "UNKNOWN")
        decision = str(strategy.get("decision") or "NO_TRADE")
        close = str(candle.get("close") or "UNKNOWN")
        age = candle.get("age_seconds")
        claims.extend([
            _claim("Market source", "Gate.io Public Spot BTC_USDT"),
            _claim("Live market regime", regime, str(strategy.get("snapshot_sha256") or "") or None),
            _claim("Strategy decision", decision),
            _claim("Latest closed 15m candle close", close),
            _claim("Latest candle age seconds", age),
        ])
        if not isinstance(age, (int, float)) or age < 0 or age > 1080:
            status = "PARTIAL"
            uncertainties.append("The latest 15m candle is stale or its freshness could not be verified.")
        answers = {
            "fa": f"رژیم ثبت‌شده: {regime}؛ تصمیم Strategy V2: {decision}؛ بسته‌شدن آخرین کندل ۱۵ دقیقه‌ای: {close}؛ سن داده: {age if age is not None else 'نامشخص'} ثانیه. این خلاصه جایگزین محاسبهٔ تازه یا سیگنال نیست.",
            "de": f"Aufgezeichnetes Marktregime: {regime}; Strategy-V2-Entscheidung: {decision}; letzter Schlusskurs der 15m-Kerze: {close}; Datenalter: {age if age is not None else 'unbekannt'} Sekunden. Dies ist eine Zusammenfassung, kein neues Signal.",
            "fr": f"Régime enregistré : {regime} ; décision Strategy V2 : {decision} ; dernière clôture 15 min : {close} ; ancienneté des données : {age if age is not None else 'inconnue'} secondes. Ceci est un résumé, pas un nouveau signal.",
            "en": f"Recorded regime: {regime}; Strategy V2 decision: {decision}; latest closed 15m close: {close}; candle age: {age if age is not None else 'unknown'} seconds. This is an evidence summary, not a new signal.",
        }
        answer = answers[language]

    elif intent == "JOURNAL_REVIEW":
        journal = data.get("journal", {})
        strategy = data.get("strategy", {})
        if not isinstance(journal, Mapping):
            return _response(intent, "BLOCKED", "Journal evidence is malformed.", [], ["CHAT_EVIDENCE_INVALID"], trace_id, now)
        j_status = str(journal.get("status") or "UNKNOWN")
        count = journal.get("decision_count", journal.get("count", 0))
        claims.extend([
            _claim("Journal status", j_status),
            _claim("Decision records", count),
        ])
        if isinstance(strategy, Mapping):
            for key in ("wins", "losses", "timeouts"):
                if key in strategy:
                    claims.append(_claim("Reported " + key, strategy[key]))
        if j_status not in {"VERIFIED", "EMPTY"}:
            status = "PARTIAL"
            uncertainties.append("Journal is not verified; outcome statistics are not inferred.")
        answers = {
            "fa": f"وضعیت ژورنال: {j_status}؛ تعداد تصمیم‌های ثبت‌شده: {count}. نتایج فقط در صورت ثبت و بلوغ معتبر گزارش می‌شوند؛ از روی سیگنال نتیجه‌سازی نمی‌شود.",
            "de": f"Journal-Status: {j_status}; aufgezeichnete Entscheidungen: {count}. Ergebnisse werden nur bei gültiger Aufzeichnung und Reife gemeldet, niemals aus einem Signal abgeleitet.",
            "fr": f"Statut du journal : {j_status} ; décisions enregistrées : {count}. Les résultats ne sont rapportés que s’ils sont enregistrés et arrivés à maturité ; ils ne sont jamais déduits d’un signal.",
            "en": f"Journal status: {j_status}; recorded decisions: {count}. Outcomes are reported only when recorded and matured; they are never inferred from a signal.",
        }
        answer = answers[language]

    elif intent == "NEWS_CONTEXT":
        news = data.get("news", {})
        monitor = news.get("monitor", {}) if isinstance(news, Mapping) else {}
        if not isinstance(monitor, Mapping):
            return _response(intent, "BLOCKED", "News evidence is malformed.", [], ["CHAT_EVIDENCE_INVALID"], trace_id, now)
        n_status = str(monitor.get("status") or "UNKNOWN")
        coverage = str(monitor.get("source_profile_status") or "UNKNOWN")
        health = monitor.get("source_health", [])
        findings = news.get("brief", {}).get("findings", []) if isinstance(news.get("brief"), Mapping) else []
        claims.extend([
            _claim("News transport status", n_status),
            _claim("News source coverage", coverage),
            _claim("Sources with health records", len(health) if isinstance(health, list) else 0),
        ])
        if coverage != "complete":
            status = "PARTIAL"
            uncertainties.append("News coverage is partial or not explicitly complete.")
        top_interpretation = None
        if isinstance(findings, list):
            for item in findings[:5]:
                if not isinstance(item, Mapping):
                    continue
                claims.append(_claim("News item", str(item.get("title") or "Untitled") + " · " + str(item.get("source") or "source unknown")))
                interpretation = item.get("interpretation")
                localized = interpretation.get("localized", {}).get(language) if isinstance(interpretation, Mapping) else None
                if isinstance(interpretation, Mapping) and interpretation.get("schema_version") == "hes.news_item_interpretation.v1":
                    claims.append(_claim("News interpretation schema", str(interpretation.get("schema_version"))))
                    claims.append(_claim("News potential effect", str(interpretation.get("potential_effect") or "mixed_or_unknown")))
                    claims.append(_claim("News relevance scope", str(interpretation.get("relevance_scope") or "unconfirmed_relevance")))
                    if isinstance(localized, Mapping):
                        claims.append(_claim("Economic mechanism", str(localized.get("why_it_matters") or "Not established")))
                        claims.append(_claim("What to monitor", str(localized.get("what_to_monitor") or "Not established")))
                        if top_interpretation is None:
                            top_interpretation = localized
                else:
                    uncertainties.append("NEWS_INTERPRETATION_UNAVAILABLE:" + str(item.get("item_id") or "unknown"))
        answers = {
            "fa": f"وضعیت انتقال اخبار: {n_status}؛ پوشش منابع: {coverage}. اخبار فقط زمینهٔ کمکی هستند و به‌تنهایی جهت معامله یا مجوز ورود ایجاد نمی‌کنند.",
            "de": f"Nachrichtenübertragung: {n_status}; Quellenabdeckung: {coverage}. Nachrichten sind nur Kontext und können weder Handelsrichtung noch Einstieg autorisieren.",
            "fr": f"Transport des actualités : {n_status} ; couverture des sources : {coverage}. Les actualités ne sont qu’un contexte et ne peuvent ni créer une direction ni autoriser une entrée.",
            "en": f"News transport: {n_status}; source coverage: {coverage}. News is contextual evidence only and cannot create trade direction or authorize entry.",
        }
        answer = answers[language]
        if top_interpretation is not None:
            answer += " " + str(top_interpretation.get("why_it_matters") or "") + " " + str(top_interpretation.get("potential_effect") or "")

    elif intent == "DIAGNOSE":
        components = data.get("components", {})
        if not isinstance(components, Mapping):
            return _response(intent, "BLOCKED", "Diagnostic evidence is malformed.", [], ["CHAT_EVIDENCE_INVALID"], trace_id, now)
        for name, component in components.items():
            if isinstance(component, Mapping):
                claims.append(_claim(str(name), str(component.get("status") or "UNKNOWN") + ((" · " + str(component.get("reason"))) if component.get("reason") else "")))
        failed = [name for name, item in components.items() if isinstance(item, Mapping) and item.get("status") not in {"OK", "VERIFIED", "EMPTY", "OBSERVATION_ONLY"}]
        if failed:
            status = "PARTIAL"
            uncertainties.append("One or more components are blocked, unavailable or not verified.")
        answers = {
            "fa": "خلاصهٔ عیب‌یابی فقط از وضعیت خواندنی اجزای موجود ساخته شده است. هیچ سرویس یا تنظیمی تغییر داده نشده است.",
            "de": "Die Diagnose verwendet ausschließlich lesbare Komponentennachweise. Es wurden keine Dienste oder Einstellungen geändert.",
            "fr": "Le diagnostic utilise uniquement les preuves lisibles des composants. Aucun service ni paramètre n’a été modifié.",
            "en": "Diagnostics use read-only component evidence. No service or configuration was changed.",
        }
        answer = answers[language]

    refs = _refs(*evidence, trace_id or None)
    return _response(intent, status, answer, claims, uncertainties, trace_id, now, refs)


def _response(
    intent: str,
    status: str,
    answer: str,
    claims: list[dict[str, Any]],
    uncertainties: list[str],
    trace_id: str,
    now: float | None,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "router_version": ROUTER_VERSION,
        "intent": intent,
        "status": status,
        "answer": answer,
        "claims": claims[:40],
        "uncertainties": uncertainties[:20],
        "evidence_refs": (evidence_refs or [])[:32],
        "trace_id": trace_id,
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now if now is not None else time.time())),
        "external_llm_used": False,
        "execution_enabled": False,
        "orders_placed": False,
        "journal_write": False,
        "policy_mutation": False,
    }
