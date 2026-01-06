#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = [
#   "chia_rs>=0.2.0",
#   "zstandard>=0.18.0",
# ]
# ///

import sqlite3

import zstandard as zstd
from chia_rs import FullBlock, Program

conn = sqlite3.connect("blockchain_v2_mainnet.sqlite")
cursor = conn.cursor()
cursor.execute("SELECT block FROM full_blocks WHERE height = 1619372")
row = cursor.fetchone()

dctx = zstd.ZstdDecompressor()
block_data = dctx.decompress(row[0])
block = FullBlock.from_bytes(block_data)

gen_bytes = bytes(block.transactions_generator)
print(f"Original generator bytes: {len(gen_bytes)} bytes")

# Parse as Program
prog = Program.from_bytes(gen_bytes)
print(f"Parsed as Program: {type(prog)}")

# Try different serialization methods
to_bytes_result = bytes(prog)
print(f"\nbytes(prog): {len(to_bytes_result)} bytes")

stream_result = prog.stream_to_bytes()
print(f"stream_to_bytes(): {len(stream_result)} bytes")

print(f"\nAre they the same? {to_bytes_result == stream_result}")

# Check if they both deserialize correctly
p1 = Program.from_bytes(to_bytes_result)
p2 = Program.from_bytes(stream_result)
print(f"Both deserialize correctly? {p1 == p2 == prog}")
