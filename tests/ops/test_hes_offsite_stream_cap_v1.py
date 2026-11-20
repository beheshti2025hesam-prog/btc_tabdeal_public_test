import shutil
import subprocess
from pathlib import Path

import pytest

BUILDER = "scripts/ops/hes_dropbox_offsite_build_v2.sh"


def test_builder_caps_encrypted_output_during_streaming():
    source = Path(__file__).resolve().parents[2] / BUILDER
    text = source.read_text()
    assert '| head -c "$MAX_BYTES" > "$tmp"' in text
    assert "set -Eeuo pipefail" in text
    assert "BUILD_REJECTED_STREAM_CAP" in text
    assert 'stat -c %s "$tmp"' in text


@pytest.mark.skipif(not shutil.which("gpg") or not shutil.which("zstd"), reason="gpg/zstd required")
def test_encrypted_stream_cap_bounds_partial_and_allows_small_archive(tmp_path):
    key = tmp_path / "passphrase"
    key.write_text("unit-test-only-passphrase\n")
    key.chmod(0o600)
    cap = 256 * 1024
    large = tmp_path / "large.gpg"
    small = tmp_path / "small.gpg"

    over = subprocess.run(
        ["bash", "-c", r'''set -uo pipefail
        head -c 2097152 /dev/urandom | zstd -q -T1 -1 \
          | gpg --batch --yes --pinentry-mode loopback --symmetric \
              --cipher-algo AES256 --passphrase-file "$1" --output - \
          | head -c "$2" > "$3"
        ''', "cap-test", str(key), str(cap), str(large)],
        check=False, capture_output=True, text=True,
    )
    assert over.returncode != 0
    assert large.stat().st_size == cap

    under = subprocess.run(
        ["bash", "-c", r'''set -euo pipefail
        head -c 32768 /dev/urandom | zstd -q -T1 -1 \
          | gpg --batch --yes --pinentry-mode loopback --symmetric \
              --cipher-algo AES256 --passphrase-file "$1" --output - \
          | head -c "$2" > "$3"
        gpg --batch --pinentry-mode loopback --passphrase-file "$1" \
          --decrypt "$3" 2>/dev/null | zstd -t -q
        ''', "cap-test", str(key), str(cap), str(small)],
        check=False, capture_output=True, text=True,
    )
    assert under.returncode == 0, under.stderr
    assert 0 < small.stat().st_size < cap
