"""Database reader for accessing blockchain data."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import zstd

from chia_rs import FullBlock


@dataclass
class BlockData:
    """Container for block data relevant to MOD analysis."""

    height: int
    header_hash: bytes
    generator: bytes | None
    generator_ref_list: list[int]


def iterate_blocks(
    db_path: str | Path,
    start_height: int,
    end_height: int,
) -> Iterator[BlockData]:
    """Iterate over blocks in the given height range.

    Yields BlockData for each block that has a generator (transaction block).

    Args:
        db_path: Path to the blockchain database
        start_height: Start height (inclusive)
        end_height: End height (inclusive)

    Yields:
        BlockData for each transaction block in range
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.execute(
            """
            SELECT header_hash, height, block
            FROM full_blocks
            WHERE height >= ? AND height <= ? AND in_main_chain = 1
            ORDER BY height
            """,
            (start_height, end_height),
        )

        for row in cursor:
            height = row["height"]
            header_hash = bytes(row["header_hash"])

            # Decompress and parse the block
            block_bytes = zstd.decompress(row["block"])
            full_block = FullBlock.from_bytes(block_bytes)

            # Skip blocks without transactions
            if full_block.transactions_generator is None:
                continue

            yield BlockData(
                height=height,
                header_hash=header_hash,
                generator=bytes(full_block.transactions_generator),
                generator_ref_list=list(full_block.transactions_generator_ref_list),
            )

    finally:
        conn.close()


def get_generators_for_refs(
    db_path: str | Path,
    ref_heights: list[int],
) -> dict[int, bytes]:
    """Fetch generators for referenced block heights.

    Args:
        db_path: Path to the blockchain database
        ref_heights: List of block heights to fetch generators for

    Returns:
        Dict mapping height to generator bytes
    """
    if not ref_heights:
        return {}

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    try:
        placeholders = ",".join("?" * len(ref_heights))
        cursor = conn.execute(
            f"""
            SELECT height, block
            FROM full_blocks
            WHERE height IN ({placeholders}) AND in_main_chain = 1
            """,
            ref_heights,
        )

        result = {}
        for row in cursor:
            block_bytes = zstd.decompress(row["block"])
            full_block = FullBlock.from_bytes(block_bytes)
            if full_block.transactions_generator is not None:
                result[row["height"]] = bytes(full_block.transactions_generator)

        return result

    finally:
        conn.close()
