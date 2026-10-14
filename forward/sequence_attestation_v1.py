"""External-root Ed25519 attestation for sequence registry bytes.

The trusted public key is injected by the execution environment, never read from
the repository. The detached signature lives in the lock but is not trusted
unless it verifies against that external key. Uses OpenSSL's Ed25519 verifier.
"""
from __future__ import annotations

import base64
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class AttestationError(ValueError):
    """The registry has no valid attestation rooted outside the repository."""


def verify_registry_attestation(registry_bytes: bytes, lock: dict[str, Any]) -> None:
    public_key = os.environ.get("HES_SEQUENCE_TRUSTED_PUBLIC_KEY_PEM")
    signature_text = lock.get("registry_signature_ed25519_b64")
    if not isinstance(public_key, str) or not public_key.strip():
        raise AttestationError("TRUSTED_PUBLIC_KEY_MISSING")
    if not isinstance(signature_text, str) or not signature_text.strip():
        raise AttestationError("REGISTRY_SIGNATURE_MISSING")
    try:
        signature = base64.b64decode(signature_text, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise AttestationError("REGISTRY_SIGNATURE_ENCODING_INVALID") from exc
    if len(signature) != 64:
        raise AttestationError("REGISTRY_SIGNATURE_LENGTH_INVALID")

    try:
        with tempfile.TemporaryDirectory(prefix="hes-attestation-") as temp_dir:
            root = Path(temp_dir)
            key_path = root / "trusted-public.pem"
            sig_path = root / "registry.sig"
            data_path = root / "registry.bin"
            key_path.write_text(public_key, encoding="ascii")
            sig_path.write_bytes(signature)
            data_path.write_bytes(registry_bytes)
            result = subprocess.run(
                [
                    "openssl", "pkeyutl", "-verify", "-pubin",
                    "-inkey", str(key_path), "-rawin",
                    "-in", str(data_path), "-sigfile", str(sig_path),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
        raise AttestationError("ATTESTATION_VERIFIER_UNAVAILABLE") from exc
    if result.returncode != 0:
        raise AttestationError("REGISTRY_SIGNATURE_INVALID")
