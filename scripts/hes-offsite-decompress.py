#!/usr/bin/env python3
"""Stream-decompress a GPG-decrypted HES archive by its actual magic bytes.

Accepted payloads: gzip (1f 8b) and Zstandard (28 b5 2f fd).
Reads stdin and writes the decompressed tar stream to stdout; no plaintext
archive is staged on disk.
"""
from __future__ import annotations
import shutil
import subprocess
import sys

MAGIC = {
    b"\x1f\x8b": (["gzip", "-dc"], "gzip"),
    b"\x28\xb5\x2f\xfd": (["zstd", "-q", "-dc"], "zstd"),
}

def main() -> int:
    source = sys.stdin.buffer
    prefix = source.read(4)
    match = next(((cmd, name) for magic, (cmd, name) in MAGIC.items() if prefix.startswith(magic)), None)
    if match is None:
        print("HES_RESTORE_UNSUPPORTED_COMPRESSION_MAGIC=" + prefix.hex(), file=sys.stderr)
        return 65
    command, name = match
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=sys.stdout.buffer)
    assert proc.stdin is not None
    try:
        proc.stdin.write(prefix)
        shutil.copyfileobj(source, proc.stdin, length=1024 * 1024)
        proc.stdin.close()
    except BrokenPipeError:
        try:
            proc.stdin.close()
        except BrokenPipeError:
            pass
    rc = proc.wait()
    if rc:
        print(f"HES_RESTORE_DECOMPRESSION_FAILED format={name} rc={rc}", file=sys.stderr)
        return rc
    print(f"HES_RESTORE_COMPRESSION_DETECTED={name}", file=sys.stderr)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
