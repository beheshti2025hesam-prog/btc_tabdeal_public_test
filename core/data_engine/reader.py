"""
Mother Agent - Raw Data Reader
Data Engine v1.0
"""

import csv
import os
from typing import Iterator, List


DEFAULT_ACTIVE_FILE = "data/trades.csv"
DEFAULT_ARCHIVE_DIR = "data/archive"


class RawDataReader:
    """
    Discovers and reads the Active Raw Data file
    and all Raw Data archive files.

    This reader is intentionally read-only.
    It does not modify, sort, delete, or rewrite Raw Data.
    """

    def __init__(
        self,
        active_file: str = DEFAULT_ACTIVE_FILE,
        archive_dir: str = DEFAULT_ARCHIVE_DIR,
    ):
        self.active_file = active_file
        self.archive_dir = archive_dir

    def discover_files(self) -> List[str]:
        """
        Return Active Raw Data and all archive CSV files.
        """

        files = []

        if os.path.isfile(self.active_file):
            files.append(self.active_file)

        if os.path.isdir(self.archive_dir):
            for filename in sorted(os.listdir(self.archive_dir)):
                if not filename.lower().endswith(".csv"):
                    continue

                file_path = os.path.join(
                    self.archive_dir,
                    filename,
                )

                if os.path.isfile(file_path):
                    files.append(file_path)

        return files

    def read_file(self, file_path: str) -> Iterator[dict]:
        """
        Read one CSV file and yield rows as dictionaries.
        """

        with open(
            file_path,
            "r",
            encoding="utf-8",
            newline="",
        ) as file:
            reader = csv.DictReader(file)

            for row in reader:
                yield row

    def read_all(self) -> Iterator[dict]:
        """
        Read rows from Active Raw Data and all archives.
        """

        for file_path in self.discover_files():
            yield from self.read_file(file_path)
