#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = [
#   "chia_rs>=0.2.0",
# ]
# ///

import inspect

from chia_rs import Program

# Check what methods Program has for serialization
print("Program methods:")
for name in dir(Program):
    if not name.startswith("_"):
        print(f"  {name}")

# Try to create a simple program and see serialization options
p = Program.to([1, 2, 3])
print(f"\nProgram: {p}")
print(f"Type: {type(p)}")

# Check if there are serialization methods
if hasattr(p, "to_bytes"):
    print(
        f"\nto_bytes: {inspect.signature(p.to_bytes) if callable(p.to_bytes) else 'not callable'}"
    )
if hasattr(p, "as_bin"):
    print(f"as_bin: {inspect.signature(p.as_bin) if callable(p.as_bin) else 'not callable'}")
if hasattr(p, "stream"):
    print(f"stream: {inspect.signature(p.stream) if callable(p.stream) else 'not callable'}")

# Try serialization
print(f"\nbytes(p) / to_bytes(): {bytes(p)}")
print(f"  Length: {len(bytes(p))}")

if hasattr(p, "stream_to_bytes"):
    stream_bytes = p.stream_to_bytes()
    print(f"\nstream_to_bytes(): {stream_bytes}")
    print(f"  Length: {len(stream_bytes)}")
    print(f"  Same as to_bytes? {stream_bytes == bytes(p)}")

    # Try to deserialize both
    p1 = Program.from_bytes(bytes(p))
    p2 = Program.from_bytes(stream_bytes)
    print(f"\nDeserialization works: p1={p1}, p2={p2}")
    print(f"Equal: {p1 == p2 == p}")
