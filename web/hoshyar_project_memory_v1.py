from __future__ import annotations

import hashlib
import re
import os
import stat
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ALLOWED_MEMORY_ROOTS = (
    "docs/checkpoints",
    "docs/architecture",
    "releases/deployment-records",
)
_TOKEN_RE = re.compile(r"[\w\u0600-\u06FF]{2,}", re.UNICODE)
_HEADING_RE = re.compile(r"^#{1,4}\s+(.+?)\s*$", re.MULTILINE)
_STOP_WORDS = {
    "the", "and", "for", "with", "from", "that", "this", "what", "when", "where", "which", "have", "has", "was", "were",
    "der", "die", "das", "und", "für", "mit", "von", "was", "wie", "war", "ist", "sind", "les", "des", "une", "pour", "avec", "dans", "que", "qui", "est",
    "از", "به", "در", "برای", "این", "آن", "چه", "چرا", "چطور", "است", "بود", "شد", "را", "که", "می", "کنیم", "کردیم", "درباره",
}

_SYNONYMS = {
    "مدل": {"model"}, "مدلی": {"model"}, "محلی": {"local"}, "تصمیم": {"decision"}, "تصمیمی": {"decision"},
    "گرفتیم": {"decide", "decision"}, "پروژه": {"project"}, "حافظه": {"memory"}, "چکپوینت": {"checkpoint"},
    "چکپوینت": {"checkpoint"}, "نقشه": {"roadmap"}, "راه": {"roadmap"}, "معماری": {"architecture"},
    "ایجنت": {"agent"}, "بازار": {"market"}, "ژورنال": {"journal"}, "ریسک": {"risk"}, "سیگنال": {"signal"},
    "داده": {"data"}, "استراتژی": {"strategy"}, "مدلهای": {"models"}, "مدلها": {"models"},
    "modell": {"model"}, "lokal": {"local"}, "entscheidung": {"decision"}, "projekt": {"project"},
    "speicher": {"memory"}, "mémoire": {"memory"}, "modèle": {"model"}, "décision": {"decision"},
    "projet": {"project"}, "marché": {"market"},
}


class HoshyarProjectMemoryReaderV1:
    """Read-only lexical retrieval over explicitly approved local HES Markdown roots."""

    def __init__(self, project_root: str | Path, *, max_files: int = 120, max_file_bytes: int = 512_000, max_matches: int = 4):
        self.project_root = Path(project_root).resolve()
        if not self.project_root.is_dir():
            raise ValueError("PROJECT_MEMORY_ROOT_INVALID")
        self.max_files = max(1, min(int(max_files), 250))
        self.max_file_bytes = max(1024, min(int(max_file_bytes), 1_000_000))
        self.max_matches = max(1, min(int(max_matches), 6))

    @staticmethod
    def _tokens(value: str) -> set[str]:
        normalized = unicodedata.normalize("NFC", value).casefold()
        tokens = {token for token in _TOKEN_RE.findall(normalized) if token not in _STOP_WORDS and len(token) > 1}
        expanded = set(tokens)
        for token in tokens:
            expanded.update(_SYNONYMS.get(token, set()))
        return expanded

    @staticmethod
    def _excerpt(content: str, query_tokens: set[str], limit: int = 900) -> tuple[str, str]:
        heading = ""
        active_heading = ""
        best_text = ""
        best_score = -1
        for block in re.split(r"\n\s*\n", content):
            block = block.strip()
            if not block:
                continue
            if block.startswith("#"):
                first = block.splitlines()[0]
                active_heading = re.sub(r"^#{1,6}\s*", "", first).strip()
                continue
            words = HoshyarProjectMemoryReaderV1._tokens(block)
            score = len(words & query_tokens)
            if score > best_score:
                best_score = score
                best_text = block
                heading = active_heading
        if not best_text:
            best_text = content.strip()
        if len(best_text) > limit:
            best_text = best_text[:limit].rsplit(" ", 1)[0] + "…"
        return heading, best_text

    def search(self, query: str) -> dict[str, Any]:
        if not isinstance(query, str) or not query.strip() or len(query) > 1000:
            return {"status": "BLOCKED", "reason": "query_invalid", "matches": [], "evidence_refs": [], "files_scanned": 0}
        query_tokens = self._tokens(query)
        if not query_tokens:
            return {"status": "BLOCKED", "reason": "query_has_no_search_terms", "matches": [], "evidence_refs": [], "files_scanned": 0}

        candidates: list[dict[str, Any]] = []
        scanned = 0
        for relative_root in ALLOWED_MEMORY_ROOTS:
            if scanned >= self.max_files:
                break
            allowed_root = self.project_root / relative_root
            try:
                allowed_real = allowed_root.resolve(strict=True)
            except OSError:
                continue
            if not allowed_real.is_relative_to(self.project_root):
                continue
            for path in sorted(allowed_real.rglob("*.md"), key=lambda item: str(item)):
                if scanned >= self.max_files:
                    break
                scanned += 1
                descriptor = None
                try:
                    if path.is_symlink():
                        continue
                    resolved = path.resolve(strict=True)
                    if not resolved.is_relative_to(allowed_real):
                        continue
                    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
                    info = os.fstat(descriptor)
                    if not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > self.max_file_bytes:
                        continue
                    chunks = []
                    remaining = self.max_file_bytes + 1
                    while remaining:
                        chunk = os.read(descriptor, min(65_536, remaining))
                        if not chunk:
                            break
                        chunks.append(chunk)
                        remaining -= len(chunk)
                    raw = b"".join(chunks)
                    if len(raw) > self.max_file_bytes:
                        continue
                    content = unicodedata.normalize("NFC", raw.decode("utf-8"))
                except (OSError, UnicodeDecodeError, RuntimeError):
                    continue
                finally:
                    if descriptor is not None:
                        os.close(descriptor)
                title_match = _HEADING_RE.search(content)
                title = title_match.group(1).strip() if title_match else path.stem.replace("_", " ").replace("-", " ")
                body_tokens = self._tokens(content)
                file_tokens = self._tokens(path.name)
                overlap = body_tokens & query_tokens
                score = len(overlap) + (2 * len(file_tokens & query_tokens))
                if score <= 0:
                    continue
                heading, excerpt = self._excerpt(content, query_tokens)
                digest = hashlib.sha256(raw).hexdigest()
                candidates.append({
                    "title": title[:180],
                    "path": str(path.relative_to(self.project_root)),
                    "heading": heading[:180],
                    "excerpt": excerpt,
                    "sha256": digest,
                    "modified_at": datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
                    "match_score": score,
                })

        candidates.sort(key=lambda item: (item["match_score"], item["modified_at"]), reverse=True)
        matches = candidates[: self.max_matches]
        refs = ["sha256:" + item["sha256"] for item in matches]
        combined = hashlib.sha256("".join(item["sha256"] for item in matches).encode("ascii")).hexdigest() if matches else ""
        return {
            "status": "PARTIAL" if matches else "EMPTY",
            "source": "local_project_markdown_readonly",
            "coverage": list(ALLOWED_MEMORY_ROOTS),
            "files_scanned": scanned,
            "matches": matches,
            "evidence_refs": refs,
            "trace_id": "project-memory-" + combined[:16] if combined else "",
            "uncertainties": ["Search covers only the approved local Markdown roots; Notion-only pages and other connected sources are not indexed."],
        }
