"""Database reader for accessing blockchain data."""

from __future__ import annotations

import sqlite3
import threading
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


class GeneratorRefCache:
    """Thread-safe cache for generator references with LRU eviction.

    Generator refs are immutable and heavily reused across blocks.
    This cache dramatically reduces DB I/O by caching fetched refs.
    """

    def __init__(self, db_path: str | Path, max_size: int = 1000):
        self.db_path = str(db_path)
        self.max_size = max_size
        self._cache: dict[int, bytes] = {}
        self._access_order: list[int] = []  # LRU tracking
        self._lock = threading.Lock()
        # Thread-local storage for DB connections
        self._local = threading.local()

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a thread-local DB connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def close_connection(self) -> None:
        """Close the thread-local connection if it exists."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None

    def get_refs(self, ref_heights: list[int]) -> list[bytes]:
        """Get generator bytes for the given heights.

        Returns a list in the same order as ref_heights.
        Uses cache when possible, fetches from DB for misses.
        """
        if not ref_heights:
            return []

        result: list[bytes | None] = [None] * len(ref_heights)
        heights_to_fetch: list[tuple[int, int]] = []  # (index, height)

        # Check cache first
        with self._lock:
            for i, height in enumerate(ref_heights):
                if height in self._cache:
                    result[i] = self._cache[height]
                    # Update LRU order
                    if height in self._access_order:
                        self._access_order.remove(height)
                    self._access_order.append(height)
                else:
                    heights_to_fetch.append((i, height))

        # Fetch missing from DB
        if heights_to_fetch:
            fetched = self._fetch_from_db([h for _, h in heights_to_fetch])

            with self._lock:
                for idx, height in heights_to_fetch:
                    if height in fetched:
                        gen_bytes = fetched[height]
                        result[idx] = gen_bytes

                        # Add to cache with LRU eviction
                        if height not in self._cache:
                            if len(self._cache) >= self.max_size:
                                # Evict least recently used
                                oldest = self._access_order.pop(0)
                                self._cache.pop(oldest, None)
                            self._cache[height] = gen_bytes
                            self._access_order.append(height)

        # Return empty bytes for any missing refs
        return [r if r is not None else b"" for r in result]

    def _fetch_from_db(self, heights: list[int]) -> dict[int, bytes]:
        """Fetch generators from DB using thread-local connection."""
        if not heights:
            return {}

        conn = self._get_connection()
        placeholders = ",".join("?" * len(heights))
        cursor = conn.execute(
            f"""
            SELECT height, block
            FROM full_blocks
            WHERE height IN ({placeholders}) AND in_main_chain = 1
            """,
            heights,
        )

        result = {}
        for row in cursor:
            block_bytes = zstd.decompress(row["block"])
            full_block = FullBlock.from_bytes(block_bytes)
            if full_block.transactions_generator is not None:
                result[row["height"]] = bytes(full_block.transactions_generator)

        return result

    def prefetch(self, heights: list[int]) -> None:
        """Prefetch generators for given heights into cache."""
        # Filter out already cached heights
        with self._lock:
            heights_to_fetch = [h for h in heights if h not in self._cache]

        if heights_to_fetch:
            # Fetch in batches to avoid huge queries
            batch_size = 100
            for i in range(0, len(heights_to_fetch), batch_size):
                batch = heights_to_fetch[i : i + batch_size]
                fetched = self._fetch_from_db(batch)

                with self._lock:
                    for height, gen_bytes in fetched.items():
                        if height not in self._cache:
                            if len(self._cache) >= self.max_size:
                                oldest = self._access_order.pop(0)
                                self._cache.pop(oldest, None)
                            self._cache[height] = gen_bytes
                            self._access_order.append(height)


class BlockReader:
    """Efficient block reader with connection reuse and batching.

    Provides an optimized way to iterate blocks with their generator refs.
    """

    def __init__(self, db_path: str | Path, cache_size: int = 1000):
        self.db_path = str(db_path)
        self.ref_cache = GeneratorRefCache(db_path, max_size=cache_size)
        self._conn: sqlite3.Connection | None = None

    def __enter__(self) -> BlockReader:
        self._conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        self._conn.row_factory = sqlite3.Row
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
        self.ref_cache.close_connection()

    def iterate_blocks_with_refs(
        self,
        start_height: int,
        end_height: int,
        batch_size: int = 100,
    ) -> Iterator[tuple[BlockData, list[bytes]]]:
        """Iterate blocks with their generator refs efficiently.

        Prefetches refs in batches to reduce DB round-trips.

        Args:
            start_height: Start height (inclusive)
            end_height: End height (inclusive)
            batch_size: Number of blocks to prefetch refs for

        Yields:
            Tuple of (BlockData, list of ref generator bytes)
        """
        if self._conn is None:
            raise RuntimeError("BlockReader must be used as context manager")

        cursor = self._conn.execute(
            """
            SELECT header_hash, height, block
            FROM full_blocks
            WHERE height >= ? AND height <= ? AND in_main_chain = 1
            ORDER BY height
            """,
            (start_height, end_height),
        )

        # Buffer blocks for batch prefetching
        block_buffer: list[BlockData] = []

        for row in cursor:
            height = row["height"]
            header_hash = bytes(row["header_hash"])

            block_bytes = zstd.decompress(row["block"])
            full_block = FullBlock.from_bytes(block_bytes)

            if full_block.transactions_generator is None:
                continue

            block = BlockData(
                height=height,
                header_hash=header_hash,
                generator=bytes(full_block.transactions_generator),
                generator_ref_list=list(full_block.transactions_generator_ref_list),
            )
            block_buffer.append(block)

            # When buffer is full, prefetch all refs and yield blocks
            if len(block_buffer) >= batch_size:
                yield from self._yield_buffered_blocks(block_buffer)
                block_buffer.clear()

        # Yield remaining blocks
        if block_buffer:
            yield from self._yield_buffered_blocks(block_buffer)

    def _yield_buffered_blocks(
        self, blocks: list[BlockData]
    ) -> Iterator[tuple[BlockData, list[bytes]]]:
        """Prefetch refs for all blocks and yield them."""
        # Collect all unique ref heights
        all_ref_heights: set[int] = set()
        for block in blocks:
            all_ref_heights.update(block.generator_ref_list)

        # Prefetch all refs at once
        if all_ref_heights:
            self.ref_cache.prefetch(list(all_ref_heights))

        # Yield blocks with their refs
        for block in blocks:
            refs = self.ref_cache.get_refs(block.generator_ref_list)
            yield (block, refs)
