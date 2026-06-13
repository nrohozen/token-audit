from dataclasses import dataclass
from datetime import datetime


@dataclass
class TokenRecord:
    project: str
    session_file: str
    session_id: str
    model: str
    timestamp: datetime
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def date(self):
        return self.timestamp.date()

    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_creation_tokens
            + self.cache_read_tokens
        )


@dataclass
class ScanResult:
    records: list
    skipped_lines: int
    scanned_files: int
