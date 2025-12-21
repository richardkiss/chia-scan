"""Shared utilities for chia-scan tools."""

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

# Default mainnet database path
DEFAULT_DB_PATH = str(Path.home() / ".chia/mainnet/db/blockchain_v2_mainnet.sqlite")

# Size multipliers
_SIZE_MULTIPLIERS = {"k": 1024, "m": 1024**2, "g": 1024**3}


def parse_size(size_str: str) -> int:
    """Parse a size string like '100k', '1M', '500' into bytes."""
    s = size_str.strip().lower()
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([kmg]?)$", s)
    if not match:
        raise ValueError(f"Invalid size format: {size_str}")
    return int(float(match.group(1)) * _SIZE_MULTIPLIERS.get(match.group(2), 1))


def format_size(size_bytes: int) -> str:
    """Format bytes into human-readable string."""
    if size_bytes >= 1024**2:
        return f"{size_bytes / 1024**2:.1f}M"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f}K"
    return f"{size_bytes}B"


def parse_range(range_str: str, is_size: bool = False) -> tuple[int | None, int | None]:
    """Parse a range string like '1000-2000', '1000-', '-2000', or '1000'.

    Returns tuple of (min_value, max_value) where either can be None.
    """
    s = range_str.strip()
    if "-" not in s:
        val = parse_size(s) if is_size else int(s)
        return (val, val)

    left, right = s.split("-", 1)
    parse = parse_size if is_size else int
    return (
        None if left == "" else parse(left),
        None if right == "" else parse(right),
    )


@contextmanager
def open_db(db_path: str) -> Iterator[sqlite3.Connection]:
    """Open blockchain database in read-only mode."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        yield conn
    finally:
        conn.close()
