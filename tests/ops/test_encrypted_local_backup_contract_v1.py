import gzip
import io
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/ops/hes_encrypted_local_backup_v1.sh"


def test_backup_script_shell_syntax_and_security_contract():
    text = SCRIPT.read_text(encoding="utf-8")
    syntax = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr

    assert "set -Eeuo pipefail" in text
    assert "umask 077" in text
    assert "--cipher-algo AES256" in text
    assert "--s2k-count \"$S2K_COUNT\"" in text
    assert "65011712" in text
    assert "flock -n 9" in text
    assert "gzip -t" in text
    assert "tar -tzf -" in text
    assert "sha256sum -c" in text
    assert "root/.ssh/authorized_keys" in text
    assert "var/lib/hes-gateio-1m-integrity" in text
    assert "var/lib/hes-news-monitor" in text
    assert "var/lib/sentinelx/hes-release-manifests" in text
    assert "root/.config/hes-backup/passphrase" not in text
    assert "etc/sentinelx/config.yaml" not in text


def test_backup_script_creates_verified_encrypted_recovery_bundle(tmp_path):
    if not shutil.which("gpg"):
        pytest.skip("gpg is required for the encrypted backup integration test")

    archive_root = tmp_path / "rootfs"
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir(mode=0o700)
    key_file = tmp_path / "passphrase"
    key_file.write_text("test-only-backup-passphrase\n", encoding="utf-8")
    key_file.chmod(0o600)
    lock_file = tmp_path / "backup.lock"
    healthcheck = Path("/bin/true")
    script_copy = tmp_path / "backup.sh"

    fixtures = {
        "opt/hes-trade-agent/releases/test/HES_RELEASE_MANIFEST_v1.json": '{"schema":"test"}\n',
        "etc/ssh/sshd_config": "PasswordAuthentication no\n",
        "etc/nftables.conf": "flush ruleset\n",
        "etc/systemd/system/hes-encrypted-local-backup.service": "[Service]\n",
        "root/.ssh/authorized_keys": "ssh-ed25519 TEST_PUBLIC_KEY\n",
        "root/.ssh/id_ed25519": "PRIVATE_KEY_MUST_NOT_BE_INCLUDED\n",
        "root/.config/hes-backup/passphrase": "DO_NOT_ARCHIVE_SECRET\n",
        "etc/sentinelx/config.yaml": "DO_NOT_CLONE_SENTINELX_IDENTITY\n",
        "usr/local/sbin/hes-encrypted-local-backup": "#!/bin/sh\n",
        "var/lib/hes-gateio-1m-integrity/observations.jsonl": '{"status":"PASS"}\n',
        "var/lib/hes-operational-health/last-issues": "",
        "var/lib/hes-news-monitor/mother-chat/token": "DASHBOARD_TOKEN\n",
        "var/lib/hes-tabdeal-readonly/snapshot.json": '{"readonly":true}\n',
        "var/lib/sentinelx/hes-release-manifests/manifest.json": '{"release":"test"}\n',
        "var/lib/sentinelx/hes-runtime-snapshots/snapshot.bundle": "runtime-evidence\n",
    }
    for relative, content in fixtures.items():
        path = archive_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    text = SCRIPT.read_text(encoding="utf-8")
    text = text.replace("ARCHIVE_ROOT=/\n", f"ARCHIVE_ROOT={archive_root}\n")
    text = text.replace("BACKUP_DIR=/var/backups/hes-trade-agent/encrypted-local\n", f"BACKUP_DIR={backup_dir}\n")
    text = text.replace("KEY_FILE=/root/.config/hes-backup/passphrase\n", f"KEY_FILE={key_file}\n")
    text = text.replace("LOCK_FILE=/run/lock/hes-encrypted-local-backup.lock\n", f"LOCK_FILE={lock_file}\n")
    text = text.replace("HEALTHCHECK_CMD=/usr/local/sbin/hes-operational-healthcheck\n", f"HEALTHCHECK_CMD={healthcheck}\n")
    text = text.replace("MIN_FREE_KB=5242880\n", "MIN_FREE_KB=0\n")
    text = text.replace("S2K_COUNT=65011712\n", "S2K_COUNT=65536\n")
    script_copy.write_text(text, encoding="utf-8")

    result = subprocess.run(["bash", str(script_copy)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "BACKUP_OK" in result.stdout

    archives = list(backup_dir.glob("hes-full-*.tar.gz.gpg"))
    assert len(archives) == 1
    archive = archives[0]
    sidecar = Path(str(archive) + ".sha256")
    assert sidecar.is_file()
    assert archive.stat().st_mode & 0o777 == 0o600
    assert sidecar.stat().st_mode & 0o777 == 0o600

    check = subprocess.run(["sha256sum", "-c", str(sidecar)], cwd=backup_dir, capture_output=True, text=True)
    assert check.returncode == 0, check.stdout + check.stderr

    decrypted = subprocess.run(
        ["gpg", "--batch", "--pinentry-mode", "loopback", "--passphrase-file", str(key_file), "--decrypt", str(archive)],
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(decrypted), mode="r:gz") as tar:
        names = set(tar.getnames())

    assert "opt/hes-trade-agent/releases/test/HES_RELEASE_MANIFEST_v1.json" in names
    assert "root/.ssh/authorized_keys" in names
    assert "var/lib/hes-gateio-1m-integrity/observations.jsonl" in names
    assert "var/lib/hes-news-monitor/mother-chat/token" in names
    assert "var/lib/sentinelx/hes-release-manifests/manifest.json" in names
    assert "var/lib/sentinelx/hes-runtime-snapshots/snapshot.bundle" in names
    assert "root/.ssh/id_ed25519" not in names
    assert "root/.config/hes-backup/passphrase" not in names
    assert "etc/sentinelx/config.yaml" not in names
