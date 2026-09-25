"""
HES Trade Agent - Read-only Raw Data Reader.
"""
import csv
import os
from typing import Iterator, List

DEFAULT_ACTIVE_FILE = "data/trades.csv"
DEFAULT_ARCHIVE_DIR = "data/archive"

class RawDataReader:
    """Discover and read active raw data plus archive CSVs without mutation."""
    def __init__(self, active_file: str = DEFAULT_ACTIVE_FILE, archive_dir: str = DEFAULT_ARCHIVE_DIR):
        self.active_file = active_file
        self.archive_dir = archive_dir

    def discover_files(self) -> List[str]:
        files = []
        if os.path.isfile(self.active_file):
            files.append(self.active_file)
        if os.path.isdir(self.archive_dir):
            for filename in sorted(os.listdir(self.archive_dir)):
                if not filename.lower().endswith(".csv"):
                    continue
                path = os.path.join(self.archive_dir, filename)
                if os.path.isfile(path):
                    files.append(path)
        return files

    def read_file(self, file_path: str) -> Iterator[dict]:
        with open(file_path, "r", encoding="utf-8", newline="") as file:
            for row in csv.DictReader(file):
                yield row

    def read_all(self) -> Iterator[dict]:
        for file_path in self.discover_files():
            yield from self.read_file(file_path)
