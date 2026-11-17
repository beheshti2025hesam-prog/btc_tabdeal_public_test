from pathlib import Path

from web.hoshyar_project_memory_v1 import HoshyarProjectMemoryReaderV1


def test_project_memory_reader_returns_verified_local_checkpoint_with_hash(tmp_path):
    root = tmp_path / "project"
    checkpoint = root / "docs" / "checkpoints" / "HOSHYAR_LOCAL_AI.md"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text("# HOSHYAR Local AI\n\nQwen3.5-2B is the selected local Persian model. The Mother router remains authoritative.\n", encoding="utf-8")
    reader = HoshyarProjectMemoryReaderV1(root)
    result = reader.search("HOSHYAR local Persian model Qwen3.5")
    assert result["status"] == "PARTIAL"
    assert result["source"] == "local_project_markdown_readonly"
    assert result["matches"][0]["path"] == "docs/checkpoints/HOSHYAR_LOCAL_AI.md"
    assert result["matches"][0]["sha256"]
    assert result["evidence_refs"][0].startswith("sha256:")
    assert "Notion-only pages" in result["uncertainties"][0]


def test_project_memory_reader_ignores_unapproved_roots_and_symlinks(tmp_path):
    root = tmp_path / "project"
    allowed = root / "docs" / "checkpoints"
    private = root / "secrets" / "private.md"
    allowed.mkdir(parents=True)
    private.parent.mkdir(parents=True)
    private.write_text("HOSHYAR private api-key secret-token", encoding="utf-8")
    (root / "docs" / "checkpoints" / "public.md").write_text("# Public\n\nNothing related to this query.\n", encoding="utf-8")
    try:
        (allowed / "linked-secret.md").symlink_to(private)
    except OSError:
        pass
    result = HoshyarProjectMemoryReaderV1(root).search("HOSHYAR api-key secret-token")
    assert all("secrets" not in item["path"] and "linked-secret" not in item["path"] for item in result["matches"])


def test_project_memory_reader_rejects_empty_or_oversized_query(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    reader = HoshyarProjectMemoryReaderV1(root)
    assert reader.search(" ")["status"] == "BLOCKED"
    assert reader.search("x" * 1001)["status"] == "BLOCKED"


def test_project_memory_reader_does_not_read_large_files(tmp_path):
    root = tmp_path / "project"
    checkpoint = root / "docs" / "checkpoints" / "large.md"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text("Qwen3.5 " + ("large model " * 1000), encoding="utf-8")
    result = HoshyarProjectMemoryReaderV1(root, max_file_bytes=1024).search("Qwen3.5 large model")
    assert result["matches"] == []


def test_mother_chat_routes_project_history_to_read_only_memory(tmp_path):
    from web.mother_chat_v1 import build_chat_response, classify_intent

    root = tmp_path / "project"
    checkpoint = root / "docs" / "checkpoints" / "LOCAL_MODEL_DECISION.md"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text("# Local model decision\n\nQwen3.5-2B is the selected local multilingual model. Mother remains authoritative.\n", encoding="utf-8")
    message = "چه تصمیمی درباره مدل محلی گرفتیم؟"
    assert classify_intent(message) == "PROJECT_MEMORY"
    reader = HoshyarProjectMemoryReaderV1(root)
    result = build_chat_response(message, {"PROJECT_MEMORY": lambda: reader.search(message)}, language="fa")
    assert result["intent"] == "PROJECT_MEMORY"
    assert result["status"] == "PARTIAL"
    assert "Qwen3.5-2B" in result["answer"]
    assert result["evidence_refs"] and result["evidence_refs"][0].startswith("sha256:")
    assert result["execution_enabled"] is False
    assert result["orders_placed"] is False



def test_project_memory_reader_bounds_candidate_traversal(tmp_path):
    root = tmp_path / "project"
    docs = root / "docs" / "checkpoints"
    docs.mkdir(parents=True)
    for index in range(12):
        (docs / f"{index:02d}.md").write_text(f"# Note {index}\n\nQwen model checkpoint {index}.\n", encoding="utf-8")
    result = HoshyarProjectMemoryReaderV1(root, max_files=3).search("Qwen model checkpoint")
    assert result["files_scanned"] == 3
    assert len(result["matches"]) <= 3


def test_project_memory_reader_rejects_symlinked_approved_document(tmp_path):
    root = tmp_path / "project"
    docs = root / "docs" / "checkpoints"
    docs.mkdir(parents=True)
    outside = root / "private.md"
    outside.write_text("Qwen model private credential secret", encoding="utf-8")
    try:
        (docs / "linked.md").symlink_to(outside)
    except OSError:
        return
    result = HoshyarProjectMemoryReaderV1(root).search("Qwen model private credential")
    assert result["matches"] == []



def test_canonical_notion_dna_snapshot_is_available_to_local_memory_reader():
    project_root = Path(__file__).resolve().parents[1]
    result = HoshyarProjectMemoryReaderV1(project_root).search("HES Trade AI HOSHYAR retired user-facing name")
    assert result["status"] == "PARTIAL"
    snapshot = next(item for item in result["matches"] if item["path"] == "docs/checkpoints/HES_TRADE_AI_DNA_2026-11-17.md")
    assert "HES Trade AI" in snapshot["excerpt"]
    assert "HOSHYAR" in snapshot["excerpt"]
    assert snapshot["sha256"]
