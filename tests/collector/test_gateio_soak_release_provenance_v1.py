import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "soak_gateio_feed_24h_v2.py"
SPEC = importlib.util.spec_from_file_location("gateio_soak_v3", SCRIPT)
soak = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(soak)


def test_release_provenance_binds_commit_manifest_and_exact_script(tmp_path):
    commit = "a" * 40
    release_root = tmp_path / commit
    scripts = release_root / "scripts"
    scripts.mkdir(parents=True)
    manifest = release_root / "HES_RELEASE_MANIFEST_v1.json"
    raw = json.dumps({"commit_sha": commit, "file_count": 1}).encode()
    manifest.write_bytes(raw)
    (release_root / "HES_RELEASE_MANIFEST_v1.sha256").write_text(
        hashlib.sha256(raw).hexdigest() + "  HES_RELEASE_MANIFEST_v1.json\\n",
        encoding="utf-8",
    )
    script = scripts / "soak.py"
    script.write_text("immutable soak source\n", encoding="utf-8")

    result = soak.release_provenance(root=release_root, script_path=script)

    assert result["code_release_id"] == commit
    assert result["release_manifest_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["soak_script_sha256"] == hashlib.sha256(script.read_bytes()).hexdigest()


def test_release_provenance_rejects_manifest_directory_identity_mismatch(tmp_path):
    release_root = tmp_path / ("b" * 40)
    release_root.mkdir()
    (release_root / "HES_RELEASE_MANIFEST_v1.json").write_text(
        json.dumps({"commit_sha": "c" * 40}), encoding="utf-8"
    )
    script = release_root / "soak.py"
    script.write_text("source\n", encoding="utf-8")

    try:
        soak.release_provenance(root=release_root, script_path=script)
    except ValueError as exc:
        assert str(exc) == "SOAK_RELEASE_ID_MISMATCH"
    else:
        raise AssertionError("release identity mismatch must fail closed")


def test_sample_checks_1m_and_all_four_market_timeframes_with_release_identity(tmp_path, monkeypatch):
    now = 2_000_000_000
    monkeypatch.setattr(soak, "MARKET_DATA_ROOT", tmp_path)
    monkeypatch.setattr(soak.time, "time", lambda: now)
    monkeypatch.setattr(soak.time, "monotonic", lambda: 150.0)

    def rows():
        return [{"close_time": now - 10, "close": 100.0}]

    monkeypatch.setattr(soak, "load_market_input", lambda root: {
        "source": "gateio_public_spot",
        "symbol": "BTC_USDT",
        "timeframes": {"15m": rows(), "1h": rows(), "4h": rows()},
    })
    reader_calls = []

    def read_1m(timeframe, *, root, min_bars=200):
        reader_calls.append((timeframe, root, min_bars))
        return rows()

    monkeypatch.setattr(soak, "read_closed_candles", read_1m)
    monkeypatch.setattr(soak.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=0, stdout="active\n"
    ))
    release = {
        "code_release_id": "a" * 40,
        "release_manifest_sha256": "b" * 64,
        "soak_script_sha256": "c" * 64,
    }

    result = soak.sample(1, 100.0, "run-1", release)

    assert result["ok"] is True
    assert set(result["timeframes"]) == {"1m", "15m", "1h", "4h"}
    assert reader_calls == [("1m", tmp_path, 200)]
    assert result["run_id"] == "run-1"
    assert result["code_release_id"] == "a" * 40
    assert result["release_manifest_sha256"] == "b" * 64
    assert result["soak_script_sha256"] == "c" * 64
    assert result["execution_enabled"] is False
    assert result["orders_placed"] is False
    assert all(value == "active" for value in result["services"].values())
    assert "hes-global-market-data-gateio-1m.service" in result["services"]
    assert "hes-global-market-data-gateio-1m-integrity.timer" in result["services"]


def test_sample_fails_closed_when_1m_canonical_reader_detects_a_gap(tmp_path, monkeypatch):
    now = 2_000_000_000
    monkeypatch.setattr(soak, "MARKET_DATA_ROOT", tmp_path)
    monkeypatch.setattr(soak.time, "time", lambda: now)
    monkeypatch.setattr(soak, "load_market_input", lambda root: {
        "source": "gateio_public_spot",
        "symbol": "BTC_USDT",
        "timeframes": {
            timeframe: [{"close_time": now - 10, "close": 100.0}]
            for timeframe in ("15m", "1h", "4h")
        },
    })

    def reject_1m(*args, **kwargs):
        raise ValueError("CANDLE_INTERVAL_GAP")

    monkeypatch.setattr(soak, "read_closed_candles", reject_1m)
    result = soak.sample(1, 100.0, "run-1", {
        "code_release_id": "a" * 40,
        "release_manifest_sha256": "b" * 64,
        "soak_script_sha256": "c" * 64,
    })
    assert result["ok"] is False
    assert "CANDLE_INTERVAL_GAP" in result["error"]
