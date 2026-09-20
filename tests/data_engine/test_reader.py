"""
Tests for Mother Agent Raw Data Reader.
"""

import os

from core.data_engine.reader import RawDataReader


def test_reader_discovers_active_file(tmp_path):
    active_file = tmp_path / "trades.csv"
    active_file.write_text(
        "symbol,price,amount,side,updated,sequence\n"
        "BTC_USDT,100000,0.001,buy,2026-09-20T10:00:00Z,123\n",
        encoding="utf-8",
    )

    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()

    reader = RawDataReader(
        active_file=str(active_file),
        archive_dir=str(archive_dir),
    )

    files = reader.discover_files()

    assert files == [str(active_file)]


def test_reader_discovers_active_and_archives(tmp_path):
    active_file = tmp_path / "trades.csv"
    active_file.write_text(
        "symbol,price,amount,side,updated,sequence\n",
        encoding="utf-8",
    )

    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()

    archive_1 = archive_dir / "trades_archive_001.csv"
    archive_2 = archive_dir / "trades_archive_002.csv"

    archive_1.write_text(
        "symbol,price,amount,side,updated,sequence\n",
        encoding="utf-8",
    )

    archive_2.write_text(
        "symbol,price,amount,side,updated,sequence\n",
        encoding="utf-8",
    )

    reader = RawDataReader(
        active_file=str(active_file),
        archive_dir=str(archive_dir),
    )

    files = reader.discover_files()

    assert files == [
        str(active_file),
        str(archive_1),
        str(archive_2),
    ]


def test_reader_does_not_modify_raw_files(tmp_path):
    active_file = tmp_path / "trades.csv"
    original_content = (
        "symbol,price,amount,side,updated,sequence\n"
        "BTC_USDT,100000,0.001,buy,2026-09-20T10:00:00Z,123\n"
    )

    active_file.write_text(
        original_content,
        encoding="utf-8",
    )

    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()

    reader = RawDataReader(
        active_file=str(active_file),
        archive_dir=str(archive_dir),
    )

    list(reader.read_all())

    assert active_file.read_text(encoding="utf-8") == original_content
