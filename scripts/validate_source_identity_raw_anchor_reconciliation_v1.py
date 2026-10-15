from __future__ import annotations

import csv
import hashlib
import io
import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANCHOR_PATH = ROOT / "archive/source_identity_raw_anchor_reconciliation_v1_20261012.json"
ANCHOR_LOCK_PATH = ROOT / "archive/source_identity_raw_anchor_reconciliation_v1_20261012.lock.json"
IDENTITY_PATH = ROOT / "evidence/source_identity_reconciliation_v1.json"
IDENTITY_LOCK_PATH = ROOT / "evidence/source_identity_reconciliation_v1.lock.json"


def git(*args: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout if binary else result.stdout.decode("utf-8").strip()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def record_key(record: dict, fields: list[str]) -> tuple:
    return tuple(record[field] for field in fields)


def row_anchor(row: dict | None) -> dict:
    if row is None:
        return {"sequence": None, "price": None, "updated": None, "side": None}
    return {
        "sequence": int(row["sequence"]),
        "price": float(row["price"]),
        "updated": row["updated"],
        "side": row["side"],
    }


def main() -> None:
    anchor_raw = ANCHOR_PATH.read_bytes()
    anchor = json.loads(anchor_raw)
    anchor_lock = json.loads(ANCHOR_LOCK_PATH.read_text(encoding="utf-8"))
    identity_raw = IDENTITY_PATH.read_bytes()
    identity = json.loads(identity_raw)
    identity_lock = json.loads(IDENTITY_LOCK_PATH.read_text(encoding="utf-8"))

    anchor_sha = hashlib.sha256(anchor_raw).hexdigest()
    assert anchor_lock["artifact_path"] == str(ANCHOR_PATH.relative_to(ROOT))
    assert anchor_lock["artifact_sha256"] == anchor_sha
    assert anchor_lock["artifact_bytes"] == len(anchor_raw)
    assert anchor_lock["artifact_git_blob_sha1"] == hashlib.sha1(
        b"blob " + str(len(anchor_raw)).encode("ascii") + b"\0" + anchor_raw
    ).hexdigest()
    assert anchor_lock["claim_boundary"] == anchor["claim_boundary"]

    identity_sha = hashlib.sha256(identity_raw).hexdigest()
    assert identity_lock["artifact_path"] == str(IDENTITY_PATH.relative_to(ROOT))
    assert identity_lock["artifact_sha256"] == identity_sha
    assert identity_lock["artifact_bytes"] == len(identity_raw)
    assert anchor["source_identity_artifact"]["sha256"] == identity_sha
    assert anchor["source_identity_artifact"]["record_count"] == 42

    assert anchor["status"] == "RAW_ANCHORS_PASS_EXIT_LINK_INFERRED_SOURCE_IDENTITY_OPEN"
    assert identity["status"] == "SOURCE_IDENTITY_LOCKED"
    assert len(identity["records"]) == 42
    assert anchor["counts"]["records"] == 42
    assert anchor["counts"]["prior_survivors"] == 14
    assert anchor["counts"]["current_winners"] == 28
    assert anchor["claim_boundary"]["feature_extraction"] is False
    assert anchor["claim_boundary"]["effective_evidence_calculation"] is False
    assert anchor["claim_boundary"]["trading_authorized"] is False

    # Fetch only the two immutable source commits; no checkout, reset, or source mutation.
    source_specs = {
        "prior_14_survivor": anchor["sources"]["prior"],
        "current_28_winner": anchor["sources"]["current"],
    }
    raw_rows_by_lineage: dict[str, list[dict]] = {}
    raw_bytes_by_lineage: dict[str, bytes] = {}
    seq_maps: dict[str, dict[int, dict]] = {}

    for lineage, spec in source_specs.items():
        commit = spec["commit"]
        expected_blob = spec["blob"]
        subprocess.run(
            ["git", "fetch", "--no-tags", "origin", commit],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        actual_blob = git("rev-parse", f"{commit}:data/trades.csv")
        assert actual_blob == expected_blob, (lineage, actual_blob, expected_blob)
        raw = git("show", f"{commit}:data/trades.csv", binary=True)
        assert len(raw) == spec["bytes"]
        assert hashlib.sha256(raw).hexdigest() == spec["sha256"]
        decoded = raw.decode("utf-8")
        rows = list(csv.DictReader(io.StringIO(decoded, newline="")))
        assert len(rows) == spec["rows"]
        sequences = [int(row["sequence"]) for row in rows]
        assert len(sequences) == len(set(sequences)), f"duplicate source sequence in {lineage}"
        raw_bytes_by_lineage[lineage] = raw
        raw_rows_by_lineage[lineage] = rows
        seq_maps[lineage] = {int(row["sequence"]): row for row in rows}

    identity_fields = identity["record_key"]
    identity_lookup = {
        (record["lineage"], record_key(record, identity_fields)): record
        for record in identity["records"]
    }
    assert len(identity_lookup) == 42

    counts = {
        "records": 0,
        "sequence_bounds_present": 0,
        "entry_price_matches_raw_sequence_last": 0,
        "inferred_exit_price_matches_after_entry": 0,
        "inferred_exit_match_within_record_minute": 0,
        "gross_return_formula_consistent": 0,
    }

    for record in anchor["records"]:
        lineage = record["lineage"]
        source_lineage = "prior_14_survivor" if lineage == "prior_14_survivor" else "current_28_winner"
        source_spec = source_specs[source_lineage]
        assert record["source"]["commit"] == source_spec["commit"]
        assert record["source"]["raw_blob_sha"] == source_spec["blob"]
        assert record["source"]["path"] == "data/trades.csv"

        key = record_key(record, identity_fields)
        assert (lineage, key) in identity_lookup, ("record missing from locked identity artifact", lineage, key)
        original = identity_lookup[(lineage, key)]
        assert original["evaluated"] is True
        assert original["fold_index"] == record["fold_index"]

        rows = raw_rows_by_lineage[source_lineage]
        by_sequence = seq_maps[source_lineage]
        first = by_sequence.get(int(record["sequence_first"]))
        entry = by_sequence.get(int(record["sequence_last"]))
        assert first is not None and entry is not None
        assert int(record["sequence_first"]) <= int(record["sequence_last"])
        assert parse_time(first["updated"]) <= parse_time(entry["updated"])
        assert row_anchor(first) == record["raw_anchors"]["first"]
        assert row_anchor(entry) == record["raw_anchors"]["entry"]
        counts["sequence_bounds_present"] += 1

        assert float(entry["price"]) == float(record["entry_price"])
        counts["entry_price_matches_raw_sequence_last"] += 1

        # The historical record lacks an explicit exit sequence. This deterministic
        # price match is a diagnostic anchor, not proof of the authoritative exit event.
        exit_row = next(
            (
                row for row in rows
                if int(row["sequence"]) > int(record["sequence_last"])
                and float(row["price"]) == float(record["exit_price"])
            ),
            None,
        )
        assert exit_row is not None
        exit_delta_ms = int(
            (parse_time(exit_row["updated"]) - parse_time(record["timestamp"])).total_seconds() * 1000
        )
        expected_exit_anchor = row_anchor(exit_row)
        expected_exit_anchor["delta_ms_from_record_timestamp"] = exit_delta_ms
        assert expected_exit_anchor == record["raw_anchors"]["exit_price_first_match_after_entry"]
        counts["inferred_exit_price_matches_after_entry"] += 1
        assert 0 <= exit_delta_ms < 60_000
        counts["inferred_exit_match_within_record_minute"] += 1

        if record["direction"] == "LONG":
            calculated = (float(record["exit_price"]) - float(record["entry_price"])) / float(record["entry_price"])
        else:
            assert record["direction"] == "SHORT"
            calculated = (float(record["entry_price"]) - float(record["exit_price"])) / float(record["entry_price"])
        assert abs(calculated - float(record["gross_return"])) < 1e-12
        counts["gross_return_formula_consistent"] += 1
        counts["records"] += 1

    assert counts == {
        "records": 42,
        "sequence_bounds_present": 42,
        "entry_price_matches_raw_sequence_last": 42,
        "inferred_exit_price_matches_after_entry": 42,
        "inferred_exit_match_within_record_minute": 42,
        "gross_return_formula_consistent": 42,
    }
    print(json.dumps({
        "status": "PASS_RAW_ANCHOR_RECONCILIATION",
        "counts": counts,
        "source_identity_gate": "OPEN_EXIT_SEQUENCE_NOT_EXPLICIT_LIVE_SOURCE_ATTESTATION_AND_SINGLE_WRITER_PROOF_OPEN",
        "source_files_modified": False,
        "feature_extraction": False,
        "effective_evidence_calculation": False,
        "trading_authorized": False,
    }, indent=2))


if __name__ == "__main__":
    main()
