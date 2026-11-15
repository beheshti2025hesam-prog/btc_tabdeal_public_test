#!/usr/bin/env python3
"""Streaming, non-extracting verifier for encrypted HES gzip/zstd backup archives."""
from __future__ import annotations
import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
from typing import Any

def compression_for_archive(path: Path) -> str:
    name = path.name
    if name.endswith(".tar.gz.gpg"): return "gzip"
    if name.endswith(".tar.zst.gpg"): return "zstd"
    raise ValueError("unsupported archive suffix; expected .tar.gz.gpg or .tar.zst.gpg")

def validate_members(members: list[str], active_release: str, rollback_release: str) -> dict[str, Any]:
    if not members:
        raise ValueError("archive contains no members")
    unsafe = []
    normalized = set()
    for raw in members:
        name = raw.rstrip("\n")
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\x00" in name:
            unsafe.append(name)
        normalized.add(name.rstrip("/"))
    if unsafe:
        raise ValueError("unsafe archive member path detected")
    active = active_release.strip("/")
    rollback = rollback_release.strip("/")
    if active not in normalized or rollback not in normalized:
        raise ValueError("active or rollback release path missing")
    return {"members": len(members), "active_release_present": True, "rollback_release_present": True,
            "unsafe_paths": 0}

def verify_archive(archive: Path, key_file: Path, active_release: str, rollback_release: str) -> dict[str, Any]:
    if not archive.is_file() or not archive.stat().st_size:
        raise ValueError("archive missing or empty")
    if not key_file.is_file() or not key_file.stat().st_size:
        raise ValueError("GPG key file missing or empty")
    compression = compression_for_archive(archive)
    gpg = subprocess.Popen(
        ["gpg", "--batch", "--pinentry-mode", "loopback", "--passphrase-file", str(key_file),
         "--decrypt", str(archive)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert gpg.stdout is not None
    decoder_cmd = ["zstd", "-q", "-dc"] if compression == "zstd" else ["gzip", "-dc"]
    decoder = subprocess.Popen(decoder_cmd, stdin=gpg.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    gpg.stdout.close()
    assert decoder.stdout is not None
    tar = subprocess.Popen(["tar", "-tf", "-", "--quoting-style=escape"],
                           stdin=decoder.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    decoder.stdout.close()
    assert tar.stdout is not None
    members = []
    for line in tar.stdout:
        members.append(line.rstrip("\n"))
    tar.stdout.close()
    tar_stderr_raw = tar.stderr.read() if tar.stderr else b""
    tar_stderr = tar_stderr_raw.decode("utf-8", "replace") if isinstance(tar_stderr_raw, bytes) else str(tar_stderr_raw)
    tar_rc = tar.wait()
    decoder_stderr = decoder.stderr.read().decode("utf-8", "replace") if decoder.stderr else ""
    decoder_rc = decoder.wait()
    gpg_stderr = gpg.stderr.read().decode("utf-8", "replace") if gpg.stderr else ""
    gpg_rc = gpg.wait()
    if gpg_rc or decoder_rc or tar_rc:
        raise RuntimeError("verification pipeline failed: gpg={} decoder={} tar={}; {}".format(
            gpg_rc, decoder_rc, tar_rc, (tar_stderr or decoder_stderr or gpg_stderr).strip()[:500]))
    validation = validate_members(members, active_release, rollback_release)
    return {"status":"PASS","archive":str(archive),"archive_bytes":archive.stat().st_size,
            "compression":compression,"encryption":"GPG symmetric AES-256 (decrypted successfully)",
            **validation,"extraction_performed":False}

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive",type=Path,required=True)
    parser.add_argument("--key-file",type=Path,required=True)
    parser.add_argument("--active-release",required=True)
    parser.add_argument("--rollback-release",required=True)
    args=parser.parse_args()
    result=verify_archive(args.archive,args.key_file,args.active_release,args.rollback_release)
    print(json.dumps(result,sort_keys=True))
    return 0

if __name__=="__main__": raise SystemExit(main())