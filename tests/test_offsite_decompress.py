#!/usr/bin/env python3
import gzip
import subprocess
import sys
import unittest
from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / "scripts" / "hes-offsite-decompress.py"

class DecompressDetectionTests(unittest.TestCase):
    def run_helper(self, payload):
        return subprocess.run([sys.executable, str(HELPER)], input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_gzip_magic(self):
        payload = gzip.compress(b"HES-RESTORE-TEST\n")
        result = self.run_helper(payload)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stdout, b"HES-RESTORE-TEST\n")
        self.assertIn(b"DETECTED=gzip", result.stderr)

    def test_zstd_magic(self):
        compressed = subprocess.run(["zstd", "-q", "-c"], input=b"HES-RESTORE-TEST\n", stdout=subprocess.PIPE, check=True).stdout
        result = self.run_helper(compressed)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stdout, b"HES-RESTORE-TEST\n")
        self.assertIn(b"DETECTED=zstd", result.stderr)

    def test_unknown_magic_fails_closed(self):
        result = self.run_helper(b"NOPE-data")
        self.assertEqual(result.returncode, 65)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"UNSUPPORTED_COMPRESSION_MAGIC", result.stderr)

if __name__ == "__main__":
    unittest.main()
