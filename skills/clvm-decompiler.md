# Skill: CLVM Decompiler

Decompile serialized CLVM bytecode (`.clvm.hex` files) into human-readable Chialisp (`.clsp` files).

**Reference**: Based on [clvm_tools_rs](https://github.com/Chia-Network/clvm_tools_rs)

## The Goal

Produce a **single high-level `.clsp` file** that:

1. **Uses `mod`, `defun`, `defconstant`** - proper Chialisp, not raw s-expressions
2. **Compiles with `run -d` to byte-identical hex** - exact same bytecode as original
3. **Is readable, editable, tweakable** - named arguments, helper functions, comments

This ONE file serves all three purposes: reading, building, and editing.

## Verification

```bash
# THE test - must produce empty output
diff <(cat original.clvm.hex) <(run -d decompiled.clsp)
```

If this diff is not empty, the decompilation is not complete.

## Input/Output

- **Input**: Hex-encoded serialized CLVM (e.g., `ff02ffff01ff02...`)
- **Output**: `puzzle.clsp` - high-level Chialisp that compiles with `run -d` to identical hex

## CLVM Serialization Format

CLVM programs are binary trees of **atoms** (byte strings) and **cons pairs**.

From `clvm_tools_rs/src/classic/clvm/serialize.rs`:

```
read a byte
if it's 0xff, it's a cons box. Read two items, build cons
otherwise, number of leading set bits is length in bytes to read size
0-0x7f are literal one byte values
0x80 is nil (empty atom)
0x80-0xbf is a size of one byte (perform logical AND of first byte with 0x3f to get size)
0xc0-0xdf is a size of two bytes (perform logical AND of first byte with 0x1f)
0xe0-0xef is 3 bytes (perform logical AND of first byte with 0x0f)
0xf0-0xf7 is 4 bytes (perform logical AND of first byte with 0x07)
```

### Atom Encoding Summary

| First Byte  | Meaning                                                      |
| ----------- | ------------------------------------------------------------ |
| `0x00-0x7f` | Single-byte atom (the byte itself, value 0-127)              |
| `0x80`      | NIL (empty atom `()`)                                        |
| `0x81-0xbf` | Atom, length = `byte & 0x3f` (1-63 bytes follow)             |
| `0xc0-0xdf` | Atom, length = `((byte & 0x1f) << 8) + next_byte`            |
| `0xe0-0xef` | Atom, length = `((byte & 0x0f) << 16) + next_2_bytes`        |
| `0xf0-0xf7` | Atom, length = `((byte & 0x07) << 24) + next_3_bytes`        |
| `0xff`      | **CONS pair** - two serialized elements follow (first, rest) |

### Parsing Algorithm

```python
def parse(data: bytes, offset: int = 0) -> tuple[Any, int]:
    b = data[offset]

    if b == 0xff:  # Cons pair
        first, offset = parse(data, offset + 1)
        rest, offset = parse(data, offset)
        return (first, rest), offset

    elif b == 0x80:  # NIL
        return (), offset + 1

    elif b <= 0x7f:  # Single byte atom
        return bytes([b]), offset + 1

    else:  # Multi-byte atom
        if b <= 0xbf:
            length = b & 0x3f
            start = offset + 1
        elif b <= 0xdf:
            length = ((b & 0x1f) << 8) | data[offset + 1]
            start = offset + 2
        elif b <= 0xef:
            length = ((b & 0x0f) << 16) | (data[offset + 1] << 8) | data[offset + 2]
            start = offset + 3
        else:  # 0xf0-0xf7
            length = ((b & 0x07) << 24) | (data[offset + 1] << 16) | (data[offset + 2] << 8) | data[offset + 3]
            start = offset + 4

        return data[start:start + length], start + length
```

## CLVM Opcodes (Complete List)

From `clvm_tools_rs/src/classic/clvm/mod.rs` - the authoritative keyword mappings:

### Version 0 (Core CLVM)

| Byte   | Operator         | Description                          |
| ------ | ---------------- | ------------------------------------ |
| `0x01` | `q`              | Quote - return argument unevaluated  |
| `0x02` | `a`              | Apply - `(a PROGRAM ENV)`            |
| `0x03` | `i`              | If - `(i COND THEN ELSE)`            |
| `0x04` | `c`              | Cons - `(c FIRST REST)`              |
| `0x05` | `f`              | First - `(f PAIR)`                   |
| `0x06` | `r`              | Rest - `(r PAIR)`                    |
| `0x07` | `l`              | Listp - returns 1 if cons, 0 if atom |
| `0x08` | `x`              | Raise - `(x ...)` raises exception   |
| `0x09` | `=`              | Equal - `(= A B)`                    |
| `0x0a` | `>s`             | Greater (byte comparison)            |
| `0x0b` | `sha256`         | SHA256 hash                          |
| `0x0c` | `substr`         | Substring - `(substr S START END)`   |
| `0x0d` | `strlen`         | String length                        |
| `0x0e` | `concat`         | Concatenate atoms                    |
| `0x10` | `+`              | Addition                             |
| `0x11` | `-`              | Subtraction                          |
| `0x12` | `*`              | Multiplication                       |
| `0x13` | `/`              | Division                             |
| `0x14` | `divmod`         | Division with remainder              |
| `0x15` | `>`              | Greater than (numeric)               |
| `0x16` | `ash`            | Arithmetic shift                     |
| `0x17` | `lsh`            | Logical shift                        |
| `0x18` | `logand`         | Bitwise AND                          |
| `0x19` | `logior`         | Bitwise OR                           |
| `0x1a` | `logxor`         | Bitwise XOR                          |
| `0x1b` | `lognot`         | Bitwise NOT                          |
| `0x1d` | `point_add`      | BLS12-381 G1 point addition          |
| `0x1e` | `pubkey_for_exp` | G1 generator × scalar                |
| `0x20` | `not`            | Logical NOT                          |
| `0x21` | `any`            | Logical OR (short-circuit)           |
| `0x22` | `all`            | Logical AND (short-circuit)          |
| `0x24` | `softfork`       | Softfork extension point             |

### Version 1 (CHIP-11 Extensions)

| Byte         | Operator               | Description                |
| ------------ | ---------------------- | -------------------------- |
| `0x30`       | `coinid`               | Compute coin ID            |
| `0x31`       | `g1_subtract`          | G1 point subtraction       |
| `0x32`       | `g1_multiply`          | G1 scalar multiplication   |
| `0x33`       | `g1_negate`            | G1 point negation          |
| `0x34`       | `g2_add`               | G2 point addition          |
| `0x35`       | `g2_subtract`          | G2 point subtraction       |
| `0x36`       | `g2_multiply`          | G2 scalar multiplication   |
| `0x37`       | `g2_negate`            | G2 point negation          |
| `0x38`       | `g1_map`               | Hash to G1                 |
| `0x39`       | `g2_map`               | Hash to G2                 |
| `0x3a`       | `bls_pairing_identity` | BLS pairing check          |
| `0x3b`       | `bls_verify`           | BLS signature verify       |
| `0x13d61f00` | `secp256k1_verify`     | secp256k1 signature verify |
| `0x1c3a8f00` | `secp256r1_verify`     | secp256r1 signature verify |

## Environment Path Encoding

In CLVM, atoms that aren't operators are **paths** into the environment tree:

| Value       | Meaning                        |
| ----------- | ------------------------------ |
| `0` or `()` | NIL                            |
| `1`         | The entire environment (`@`)   |
| `2`         | First of environment - `(f @)` |
| `3`         | Rest of environment - `(r @)`  |
| `4`         | `(f (f @))`                    |
| `5`         | `(f (r @))`                    |
| `6`         | `(r (f @))`                    |
| `7`         | `(r (r @))`                    |

**Path decoding algorithm** (CRITICAL - get this right!):

For path `n > 1`:

1. Convert `n` to binary
2. Remove the leading `1` bit
3. Read remaining bits **RIGHT-TO-LEFT** (LSB first)
4. Each bit: `0` = `f` (first), `1` = `r` (rest)
5. Apply operations from innermost to outermost

**Examples**:

- Path 5 = `101` → bits after leading 1: `01` → read R-to-L: `1,0` → r,f → `f(r(env))`
- Path 6 = `110` → bits: `10` → read R-to-L: `0,1` → f,r → `r(f(env))`
- Path 11 = `1011` → bits: `011` → read R-to-L: `1,1,0` → r,r,f → `f(r(r(env)))`
- Path 22 = `10110` → bits: `0110` → read R-to-L: `0,1,1,0` → f,r,r,f → `f(r(r(f(env))))`

**Empirical verification**: When confused, test with `brun`:

```bash
brun '5' '((A . B) . (X . Y))'
# Output: 88 (ASCII for 'X') = f(r(env)) = f((X.Y)) = X ✓
```

**IMPORTANT: Negative numbers as paths**

When `opd` shows a negative number like `-65`, it's still treated as a path during execution!
The atom `-65` (encoded as `0x81bf`) is interpreted as **unsigned path 191** (since `0xbf` = 191).

```bash
# These are ALL equivalent:
brun '-65' '(A B C D E F G)'   # → G (path 191)
brun '191' '(A B C D E F G)'   # → G (path 191)
brun '0xbf' '(A B C D E F G)'  # → G (path 191)
```

So when you see `(= 5 -65)` in decompiled code, it means "compare path 5 with path 191" -
comparing two solution elements, NOT comparing against a literal -65 value!

### Common Paths in Curried Programs

When CLVM is `(a (q . CODE) (c (q . CONST) 1))`, runtime env = `(CONST . SOL)`:

| Path | Formula      | In `(CONST . SOL)`          |
| ---- | ------------ | --------------------------- |
| 2    | `f(env)`     | CONST                       |
| 3    | `r(env)`     | SOL                         |
| 4    | `f(f(env))`  | `f(CONST)`                  |
| 5    | `f(r(env))`  | `f(SOL)` = sol[0]           |
| 6    | `r(f(env))`  | `r(CONST)`                  |
| 7    | `r(r(env))`  | `r(SOL)`                    |

**Key insight**: Even paths (2,4,6,8...) traverse into CONST, odd paths (3,5,7,11...) into SOL.

For the complete solution path table (sol[0] through sol[14]), see "Solution Argument Paths" below.

## Disassembly Logic

From `clvm_tools_rs/src/classic/clvm_tools/binutils.rs`:

The disassembler converts atoms to their representation based on context:

1. **Empty atom** → `()`
2. **Printable string** (length > 2) → `"string"`
3. **Known keyword** (when in operator position) → operator name like `a`, `sha256`
4. **Small integer** (canonical form) → decimal number
5. **Otherwise** → hex like `0xabcd`

### Keyword Context

Keywords are only recognized in **operator position** (first element of a list). The disassembler tracks whether the current position allows keywords:

```rust
// From binutils.rs
if let SExp::Pair(_, _) = allocator.sexp(l) {
    allow_keyword = true;  // Reset for nested list
}
let v0 = disassemble_to_ir_with_kw(allocator, l, keyword_from_atom, allow_keyword);
let v1 = disassemble_to_ir_with_kw(allocator, r, keyword_from_atom, false);  // Args don't get keywords
```

## Decompilation Process

### Step 1: Parse Hex to Tree

```python
def parse_hex(hex_string: str):
    data = bytes.fromhex(hex_string)
    tree, _ = parse(data, 0)
    return tree
```

### Step 2: Convert Tree to Chialisp

```python
OPCODES = {
    1: 'q', 2: 'a', 3: 'i', 4: 'c', 5: 'f', 6: 'r', 7: 'l', 8: 'x',
    9: '=', 10: '>s', 11: 'sha256', 12: 'substr', 13: 'strlen', 14: 'concat',
    16: '+', 17: '-', 18: '*', 19: '/', 20: 'divmod', 21: '>',
    22: 'ash', 23: 'lsh', 24: 'logand', 25: 'logior', 26: 'logxor', 27: 'lognot',
    29: 'point_add', 30: 'pubkey_for_exp',
    32: 'not', 33: 'any', 34: 'all', 36: 'softfork',
    48: 'coinid', 49: 'g1_subtract', 50: 'g1_multiply', 51: 'g1_negate',
    52: 'g2_add', 53: 'g2_subtract', 54: 'g2_multiply', 55: 'g2_negate',
    56: 'g1_map', 57: 'g2_map', 58: 'bls_pairing_identity', 59: 'bls_verify',
}

def atom_to_int(atom: bytes) -> int:
    """Convert atom to signed integer."""
    if len(atom) == 0:
        return 0
    val = int.from_bytes(atom, 'big')
    # Check sign bit
    if atom[0] & 0x80:
        val -= (1 << (len(atom) * 8))
    return val

def atom_to_str(atom: bytes, allow_keyword: bool = False) -> str:
    if len(atom) == 0:
        return "()"

    # Check for keyword (only if allowed and 1-2 bytes)
    if allow_keyword and len(atom) <= 2:
        val = atom_to_int(atom)
        if val in OPCODES:
            return OPCODES[val]

    # Try as small integer (canonical form)
    if len(atom) <= 2:
        val = atom_to_int(atom)
        # Check for non-canonical sign extension
        if not has_oversized_sign_extension(atom):
            return str(val)

    # Try as printable string
    if len(atom) > 2:
        try:
            s = atom.decode('utf-8')
            if s.isprintable():
                return f'"{s}"'
        except:
            pass

    # Fallback to hex
    return "0x" + atom.hex()

def tree_to_clsp(tree, allow_keyword: bool = True) -> str:
    if isinstance(tree, bytes):
        return atom_to_str(tree, allow_keyword)
    if tree == ():
        return "()"

    # It's a cons pair (first, rest)
    first, rest = tree

    # Check if first is itself a pair (resets keyword allowance)
    first_is_pair = isinstance(first, tuple) and first != ()

    # Build list representation
    elements = []
    current = tree
    is_first = True
    while isinstance(current, tuple) and current != ():
        head, current = current
        kw = (is_first and allow_keyword) or first_is_pair
        elements.append(tree_to_clsp(head, allow_keyword=kw))
        is_first = False

    if current != () and not isinstance(current, tuple):
        # Improper list: (a b . c)
        elements.append(".")
        elements.append(tree_to_clsp(current, allow_keyword=False))

    return "(" + " ".join(elements) + ")"
```

### Step 3: Pretty Print

For readability, add newlines and indentation for complex structures:

```python
def pretty_print(clsp: str, max_line: int = 80) -> str:
    """Add newlines and indentation for readability."""
    # Implementation: break after ( if line would exceed max_line
    # Indent nested structures
    ...
```

## Recognizing Common Patterns

### Quote: `(q . VALUE)`

When first element is `1` (quote opcode), the structure `(1 . X)` displays as `(q . X)`:

```clsp
(q . 100)        ; Quoted integer
(q . "hello")    ; Quoted string
(q . (1 2 3))    ; Quoted list
```

### Fixed-Output Puzzles (Quoted Conditions)

A puzzle that starts with `q` at the top level ignores its solution entirely and returns hardcoded conditions:

```clsp
(q (51 0xPUZZLE_HASH 1000000)    ; CREATE_COIN
   (52 0x1000))                   ; RESERVE_FEE
```

This pattern is used for:

- Pre-committed transactions (conditions decided at coin creation)
- Offer/settlement puzzle components
- "Anyone can spend" coins that do exactly one thing

These are trivially spendable - any solution works!

### Apply: `(a CODE ENV)`

The apply operator runs CODE with ENV as the environment:

```clsp
(a (q . (+ 2 5)) (q . (10 20)))  ; Runs (+ 2 5) with env (10 20)
```

### Curried Functions

Currying uses this pattern:

```clsp
(a (q . MOD_CODE) (c (q . ARG1) (c (q . ARG2) 1)))
```

This applies `MOD_CODE` with `ARG1` and `ARG2` prepended to the environment.

### Conditionals

```clsp
(i CONDITION THEN_BRANCH ELSE_BRANCH)
```

Often wrapped in `(a (i ...) 1)` to force evaluation of selected branch.

## CLVM Tools (from `clvm_tools` package)

### Installation

```bash
# Pure Python implementation (by Richard Kiss)
pip install clvm_tools

# Or Rust implementation (faster, same CLI)
pip install -i https://pypi.chia.net/simple/ clvm_tools_rs
```

### Tool Overview

| Tool   | Purpose                                | Example                                 |
| ------ | -------------------------------------- | --------------------------------------- |
| `opc`  | Compile s-expression to hex            | `opc '(+ 2 5)'` → `ff10ff02ff0580`      |
| `opd`  | Disassemble hex to s-expression        | `opd ff10ff02ff0580` → `(+ 2 5)`        |
| `brun` | Execute compiled CLVM with environment | `brun '(+ 2 5)' '(10 20)'` → `30`       |
| `run`  | Compile Chialisp source to CLVM        | `run '(mod (X Y) (+ X Y))'` → `(+ 2 5)` |

### opd - Disassemble hex to readable CLVM

```bash
# Disassemble hex
opd ff10ff02ff0580
# Output: (+ 2 5)

# From file
opd $(cat puzzle.clvm.hex)

# Show only tree hash (for puzzle identification)
opd -H ff10ff02ff0580
# Output: 123abc...
```

### opc - Compile s-expression to hex

```bash
# Compile CLVM s-expression to hex
opc '(+ 2 5)'
# Output: ff10ff02ff0580

# Also shows tree hash with -H
opc -H '(+ 2 5)'
```

### brun - Execute compiled CLVM

```bash
# Run CLVM program with environment
brun '(+ 2 5)' '(10 20)'
# Output: 30  (because 2→10, 5→20, 10+20=30)

# Run with hex input
brun -x ff10ff02ff0580 ff0aff1480
# (hex env = (10 20))

# Show execution cost
brun -c '(+ 2 5)' '(10 20)'
# Output: cost = 833, result = 30

# Dump result as hex
brun -d '(q . (hello world))' '()'
# Output: ff8568656c6c6fff85776f726c6480

# Verbose mode - show all reductions (debugging)
brun -v '(+ 2 5)' '(10 20)'
```

### run - Compile Chialisp to CLVM

```bash
# Compile Chialisp module
run '(mod (X Y) (+ X Y))'
# Output: (+ 2 5)

# Dump as hex
run -d '(mod (X Y) (+ X Y))'
# Output: ff10ff02ff0580

# With optimizer
run -O '(mod (X Y) (+ X Y))'

# With include paths
run -i ./includes '(mod () (include "utils.clib") ...)'
```

### Full Pipeline Example

```bash
# 1. Write Chialisp source
echo '(mod (A B) (* A (+ A B)))' > formula.clsp

# 2. Compile to CLVM
run formula.clsp
# Output: (* 2 (+ 2 5))

# 3. Compile to hex
run -d formula.clsp > formula.clvm.hex

# 4. Execute with arguments
brun $(cat formula.clvm.hex) '(3 7)'
# Output: 30  (because 3 * (3 + 7) = 30)

# 5. Disassemble to verify
opd $(cat formula.clvm.hex)
# Output: (* 2 (+ 2 5))
```

## Using Python

```python
from clvm_rs import Program

# From hex string
p = Program.fromhex("ff10ff02ff0580")
print(p)  # (+ 2 5)

# Run with environment
env = Program.to([10, 20])
cost, result = p.run_with_cost(env)
print(result)  # 30
```

## Standard Chia Puzzles Reference

The [chia_puzzles](https://github.com/Chia-Network/chia_puzzles) repository contains all standard on-chain puzzles.

### Key Puzzles and Their Hashes

| Puzzle                                 | Hash          | Description                 |
| -------------------------------------- | ------------- | --------------------------- |
| `p2_delegated_puzzle_or_hidden_puzzle` | `e9aaa49f...` | Standard transaction puzzle |
| `cat_v2` (CAT)                         | `37bef360...` | Chia Asset Token            |
| `singleton_top_layer_v1_1`             | `7faa3253...` | Singleton wrapper           |
| `nft_state_layer`                      | —             | NFT state management        |
| `did_innerpuz`                         | —             | DID inner puzzle            |

### Include Libraries (`.clib` files)

Standard libraries to include in Chialisp:

| Library                 | Purpose                                                 |
| ----------------------- | ------------------------------------------------------- |
| `condition_codes.clib`  | Condition opcodes (CREATE_COIN=51, AGG_SIG_ME=50, etc.) |
| `curry.clib`            | Currying utilities and hash calculation                 |
| `sha256tree.clib`       | Tree hashing                                            |
| `singleton_truths.clib` | Singleton data accessors                                |
| `cat_truths.clib`       | CAT data accessors                                      |
| `utility_macros.clib`   | Common macros (assert, etc.)                            |

### Condition Codes (from `condition_codes.clib`)

```chialisp
AGG_SIG_UNSAFE      49    ; Signature without coin binding
AGG_SIG_ME          50    ; Signature bound to coin
CREATE_COIN         51    ; Create new coin
RESERVE_FEE         52    ; Reserve fee
CREATE_COIN_ANNOUNCEMENT  60
ASSERT_COIN_ANNOUNCEMENT  61
CREATE_PUZZLE_ANNOUNCEMENT 62
ASSERT_PUZZLE_ANNOUNCEMENT 63
ASSERT_MY_COIN_ID   70
ASSERT_MY_PARENT_ID 71
ASSERT_MY_PUZZLEHASH 72
ASSERT_MY_AMOUNT    73
ASSERT_SECONDS_RELATIVE 80
ASSERT_SECONDS_ABSOLUTE 81
ASSERT_HEIGHT_RELATIVE  82
ASSERT_HEIGHT_ABSOLUTE  83
REMARK              1     ; No-op, ignored
SOFTFORK            90    ; Soft-fork extension
```

### Recognizing Standard Puzzles

When decompiling, look for these patterns:

**p2_delegated_puzzle_or_hidden_puzzle** (standard tx):

- Curried with a synthetic public key
- Uses `point_add` and `pubkey_for_exp` for hidden puzzle verification
- Returns `AGG_SIG_ME` condition

**CAT v2**:

- Ring signature mechanism with announcements
- Uses `0xcb` prefix for ring announcements
- Morphs `CREATE_COIN` to wrap in CAT puzzle

**Singleton**:

- Launcher ID curried in
- Lineage proof verification
- Creates exactly one output coin

## Complete Decompilation Workflow

### Achieving Byte-Identical Output

The key is controlling the **CONST tree structure** that the compiler produces.

#### How the Compiler Builds CONST

The `run` compiler:

1. Collects all `defconstant` and `defun` definitions
2. Sorts them **alphabetically by name**
3. Builds a **balanced binary tree** using recursive midpoint splitting

```python
def build_tree(items):
    if len(items) == 1: return items[0]
    mid = len(items) // 2
    return (build_tree(items[:mid]), build_tree(items[mid:]))

# 4 items [A,B,C,D] → ((A . B) . (C . D))
# 5 items [A,B,C,D,E] → ((A . B) . (C . (D . E)))
```

#### Matching the Original CONST Structure

1. **Analyze the original**: Look at `opd` output to see the CONST tree shape
2. **Count helpers**: How many items in the CONST tree?
3. **Name strategically**: Use `_NNN_` prefixes to control alphabetical order
4. **Verify tree shape**: The number and order of helpers determines the tree

```chialisp
; To produce CONST = ((A . B) . (C . (D . E))):
(defconstant _000_first A_VALUE)   ; position 0
(defconstant _001_second B_VALUE)  ; position 1
(defconstant _002_third C_VALUE)   ; position 2
(defconstant _003_fourth D_VALUE)  ; position 3
(defconstant _004_fifth E_VALUE)   ; position 4
```

#### Handling Complex CONST Structures

Some puzzles have CONST structures that don't match the compiler's balanced tree:

- Flat improper lists: `(A B C D . E)` instead of `((A.B).(C.(D.E)))`
- Irregular nesting
- Inline expressions mixed with functions

**Strategy**: Reverse-engineer what Chialisp source WOULD produce this structure, or find equivalent restructuring that achieves the same runtime paths.

#### CONST Tree Shape Analysis

The compiler produces specific tree shapes based on number of helpers:

```bash
# Test what shape N helpers produce
cat << 'EOF' > /tmp/test.clsp
(mod (X)
  (defun f1 (x) (+ x 1))
  (defun f2 (x) (+ x 2))
  ; ... add more
  (f1 (f2 X)))
EOF
run /tmp/test.clsp  # Look at the (c (q CONST) 1) part
```

**Key insight**: The compiler NEVER produces flat improper lists like `(A B C D E . F)`. It always creates nested pairs like `((A . B) (C . D) E . F)`.

If the original puzzle has a flat improper list CONST, it was hand-crafted and **cannot be byte-identically reproduced** by any standard compiler.

In this case:

1. Document the exact blocker (CONST tree shape mismatch)
2. Produce the best high-level equivalent
3. Note that byte-identical is architecturally impossible without compiler modifications

### Modern vs Classic Compiler

There are TWO Chialisp compilers with different output structures.

**Reference**: https://chialisp.com/modern-chialisp/

#### Classic Compiler (default)

```chialisp
(mod (X)
  (defconstant MY_CONST 50)
  (defun helper (x) (+ x 1))
  (helper X))
```

- Produces keyword-based output: `(a (q 2 4 ...) (c (q ...) 1))`
- `defconstant` and `defconst` are **identical** in classic compiler (both place in CONST tree)
- CONST tree structure uses recursive midpoint splitting (see table below)

#### Modern Compiler (with sigil)

```chialisp
(mod (X)
  (include *standard-cl-24*)  ; Current sigil
  (defconst MY_CONST 50)      ; Places in CONST tree
  (defconstant OLD_CONST 51)  ; INLINES into code
  (defun helper (x) (+ x 1))
  (helper X))
```

- **Current sigil: `*standard-cl-24*`** (not 21 or 23)
- Produces numeric opcode output: `(2 (1 2 4 ...) (4 (1 ...) 1))`
- Supports `let`, `let*`, `assign`, `lambda`, `@` destructuring
- **Sigil guarantees identical compilation forever** (per the docs)

#### CRITICAL: `defconst` vs `defconstant` (Modern Compiler)

| Form          | Behavior                                        | Output                           |
| ------------- | ----------------------------------------------- | -------------------------------- |
| `defconst`    | Placed in CONST tree, referenced by path        | `(2 (1 ... 4 ...) (4 (1 50) 1))` |
| `defconstant` | **INLINED** directly into CODE as `(q . value)` | `(+ (1 . 50) ...)`               |

**This matters for byte-identical decompilation:**

- Original has `(q . 50)` inlined in CODE → use `defconstant`
- Original has `50` in CONST tree, path refs in CODE → use `defconst`

```chialisp
; defconstant INLINES:
(mod (X) (include *standard-cl-24*) (defconstant A 50) (+ A X))
; → (16 (1 . 50) 2)  -- (+ (q . 50) arg)

; defconst uses CONST tree:
(mod (X) (include *standard-cl-24*) (defconst A 50) (+ A X))
; → (2 (1 16 2 5) (4 (1 . 50) 1))  -- path 2 refs CONST
```

#### Key Modern Features for Decompilation

| Feature     | Syntax                  | Use                                   |
| ----------- | ----------------------- | ------------------------------------- |
| `defconst`  | `(defconst NAME expr)`  | Compile-time constant, auto-optimized |
| `let`       | `(let ((x 1)) body)`    | Local bindings (parallel)             |
| `assign`    | `(assign x 1 y 2 body)` | Reordered bindings                    |
| `lambda`    | `(lambda (x) body)`     | Anonymous functions                   |
| `@` capture | `(@ whole (a . b))`     | Destructure + bind whole              |

#### Sigil Behavior

```
Programs with a specific sigil compile to the same representation forever.
It is a bug if a program changes representation in a future compiler release.
```

This means: **if you identify which sigil was used, you can reproduce identical bytecode.**

#### Trying Different Compilers

```bash
# Classic (no sigil)
run -d puzzle.clsp

# Modern cl-24
# Add: (include *standard-cl-24*) after (mod ...)
run -d puzzle.clsp

# Get hex from modern (run -d shows s-expr, pipe through opc)
opc "$(run puzzle.clsp)"
```

### Step-by-Step Process for Complex Puzzles

#### 1. Initial Analysis

```bash
# Get the hash (for identification)
opd -H $(cat puzzle.clvm.hex)

# Disassemble to see structure
opd $(cat puzzle.clvm.hex)
```

#### 2. Identify the Outer Structure

Most puzzles follow the curried pattern:

```
(a (q . CODE) (c (q . CONST) 1))
```

Look at the END of the `opd` output to find CONST:

```bash
# The last part typically shows: (c (q . CONST_TREE) 1))
```

#### 3. Map the CONST Tree

CONST often contains condition codes in a specific tree structure.
Trace paths to find which numbers map to which condition codes:

```bash
# Create the runtime environment structure
ENV='(CONST . (sol0 sol1 sol2 sol3 sol4 sol5 sol6 sol7 sol8))'

# Find condition code paths
for p in 8 10 12 22 30; do
  echo -n "path $p: "
  brun "$p" "$ENV"
done
```

Common condition code paths in curried puzzles:

- Look for paths that yield 50 (AGG_SIG_ME), 51 (CREATE_COIN), 60 (announcement), 72, 73

#### 4. Map the Solution Structure

Identify what each solution element means by analyzing how paths are used:

```bash
# Solution paths follow the pattern: 5, 11, 23, 47, 95, 191, 383, 767, 1535...
# These are f(r^n(env)) for increasing n

for p in 5 11 23 47 95 191 383 767 1535; do
  echo "path $p: sol[$(($(echo "l($p)/l(2)" | bc -l | cut -d. -f1) - 2))]"
done
```

#### 5. Understand the Logic Flow

Trace through the conditionals to understand what the puzzle does:

- What are the entry conditions?
- What modes/branches exist?
- What conditions are output in each case?

#### 6. Create Byte-Identical Version

Copy the `opd` output directly into a `.clsp` file:

```bash
opd $(cat puzzle.clvm.hex) > puzzle.clsp
# Verify round-trip
opc "$(cat puzzle.clsp)" > /tmp/test.hex
diff puzzle.clvm.hex /tmp/test.hex  # Should be empty
```

#### 7. Create High-Level Chialisp

Write proper Chialisp with:

- `mod` wrapper with named arguments matching solution structure
- `defconstant` with `_NNN_` prefixes to control CONST tree order
- `defun` for helper functions (sha256tree, list builders, etc.)
- Comments explaining solution structure and logic

```chialisp
(mod (arg1 arg2 arg3 ...)

  ; Constants ordered to match original CONST tree
  (defconstant _000_AGG_SIG_ME 50)
  (defconstant _001_CREATE_COIN 51)
  ; ... order matters for byte-identical!

  ; Helper functions
  (defun sha256tree (tree)
    (if (l tree)
        (sha256 2 (sha256tree (f tree)) (sha256tree (r tree)))
        (sha256 1 tree)))

  ; Main logic
  (if (= mode 1)
      ; ...
      ))
```

#### 8. Iterate Until Byte-Identical

```bash
# Compile and compare
run -d puzzle.clsp > /tmp/my.hex
diff original.clvm.hex /tmp/my.hex

# If diff is not empty:
# 1. Check CONST tree structure (number and order of helpers)
# 2. Check path references in code match
# 3. Adjust helper naming/ordering
# 4. Repeat
```

#### 9. Final Verification

```bash
# Byte-identical check
diff <(cat original.clvm.hex) <(run -d puzzle.clsp)
# Must be empty!

# Also verify with actual execution
SOL='(test solution here)'
brun "$(opd $(cat original.clvm.hex))" "$SOL"
brun "$(run puzzle.clsp)" "$SOL"
# Must produce identical output!
```

### Debugging Strategies

#### Isolate Code Fragments

When the full puzzle fails, test pieces in isolation:

```bash
# Extract just the inner code (without the curry wrapper)
INNER_CODE='(i (= 5 11) (q . "yes") (q . "no"))'
INNER_ENV='((50 . 73) match match c d e)'
brun "$INNER_CODE" "$INNER_ENV"
```

#### Build the Environment Manually

```bash
# Evaluate the curry expression separately
ENV_EXPR='(c (q . ((50 . 73) 72 51 . 60)) 1)'
SOL='(a b c d e f g h i)'
INNER_ENV=$(brun "$ENV_EXPR" "$SOL")
echo "Inner env: $INNER_ENV"
```

#### Trace Path Access

```bash
# When you see a path in code, verify what it accesses
brun '383' '(((50 . 73) 72 51 . 60) a b c d e f 12345 h i)'
# Shows what value path 383 retrieves
```

#### Systematic Path Mapping

Create a test environment matching the puzzle's CONST structure and trace all paths:

```python
import subprocess

# Build test env: (CONST . SOL)
const = "(((50 . 73) 72 . 63) (81 . 2) 51 60 . 4)"  # from puzzle
test_env = f"(({const} F0 F1 F2 F3 F4 . F5) . (s0 s1 s2 s3 s4 s5 s6 s7 s8 s9 s10 s11 s12 . s13))"

# Trace all paths used in the code
paths_to_trace = [32, 40, 44, 48, 56, 92,  # condition codes
                  50, 42, 90,               # mode markers
                  5, 11, 23, 47, 95, 191, 383, 767, 1535, 3071, 6143, 12287, 24575, 49151]  # solution

for p in paths_to_trace:
    result = subprocess.run(['brun', str(p), test_env], capture_output=True, text=True)
    print(f"path {p:5d} = {result.stdout.strip()}")
```

#### Identify Negative Number Paths

When `opd` shows negative numbers like `-65` or `-16385`, convert to unsigned paths:

```python
# -65 in signed 8-bit = 0xBF = 191 unsigned
# -16385 in signed 16-bit = 0xBFFF = 49151 unsigned

def signed_to_path(n):
    if n >= 0:
        return n
    # Find minimum bytes needed
    for nbytes in [1, 2, 3, 4]:
        max_neg = -(1 << (nbytes * 8 - 1))
        if n >= max_neg:
            return n + (1 << (nbytes * 8))
    return n

print(signed_to_path(-65))    # → 191 = sol[5]
print(signed_to_path(-16385)) # → 49151 = sol[13]
```

## Byte-for-Byte Decompilation

Reconstruct `.clsp` that compiles with `run` to **identical bytecode**.

### The Alphabetical Helper Ordering Trick

The compiler sorts ALL helpers (constants AND `defun`) **alphabetically by name**,
then places them in a **balanced binary tree** using recursive midpoint splitting.

Use `_NNN_` prefixes to control ordering while keeping readable names:

```chialisp
; For CONST = ((50 . 73) 72 51 . 60), use:
; (Use defconstant for classic compiler, defconst for modern)
(defconstant _000_AGG_SIG_ME 50)              ; position 0 → path 8
(defconstant _001_ASSERT_MY_AMOUNT 73)        ; position 1 → path 12
(defconstant _002_ASSERT_MY_PUZZLEHASH 72)    ; position 2 → path 10
(defconstant _003_CREATE_COIN 51)             ; position 3 → path 22
(defconstant _004_CREATE_COIN_ANNOUNCEMENT 60) ; position 4 → path 30
```

**Note**: In modern compiler, `defconstant` INLINES values (no CONST tree entry).
Use `defconst` in modern compiler to place values in the CONST tree.

### How the Tree is Built (from clvm_tools_rs source)

```rust
fn build_tree(start, end, helpers) {
    if end - start == 1 { return helpers[start] }
    mid = (end + start) / 2
    cons(build_tree(start, mid), build_tree(mid, end))
}
```

### CONST Tree Structures

The compiler uses `mid = len // 2` splitting recursively:

| N   | Tree Structure                    | Paths → positions 0,1,2...         |
| --- | --------------------------------- | ---------------------------------- |
| 1   | `A`                               | 2                                  |
| 2   | `(A . B)`                         | 4, 6                               |
| 3   | `(A . (B . C))`                   | 4, 10, 14                          |
| 4   | `((A . B) . (C . D))`             | 8, 12, 10, 14                      |
| 5   | `((A . B) . (C . (D . E)))`       | 8, 12, 10, 22, 30                  |
| 6   | `((A . (B . C)) . (D . (E . F)))` | 8, 20, 28, 10, 22, 30              |

**Note**: `(A B . C)` is shorthand for `(A . (B . C))` — they serialize identically.

**This table applies to:**
- Classic compiler with `defconstant` or `defconst` (identical output)
- Modern compiler with `defconst`

**Exception**: Modern compiler with `defconstant` produces **no CONST tree** — values are inlined directly into CODE as `(q . value)`. See "CRITICAL: defconst vs defconstant" in the Modern Compiler section above.

**Functions AND constants share the same tree** - sorted together alphabetically!

### Recursive and Mutually Recursive Functions

Functions reference themselves and siblings via CONST paths:

```chialisp
; Recursive - factorial calls itself via path 2 (full CONST)
(defun factorial (n acc)
  (if (= n 0) acc (factorial (- n 1) (* n acc))))
; Compiles to: (a 2 (c 2 (c (- 5 (q . 1)) (c (* 5 11) ()))))
;                  ^-- path 2 = the function itself

; Mutually recursive - is_even and is_odd call each other
(defun is_even (n) (if (= n 0) 1 (is_odd (- n 1))))   ; calls path 6
(defun is_odd (n) (if (= n 0) 0 (is_even (- n 1))))   ; calls path 4
; Sorted alphabetically: is_even @ path 4, is_odd @ path 6
```

### Solution Argument Paths

Arguments in `(mod (A B C D E F G H I) ...)` get paths:

- 5, 11, 23, 47, 95, 191, 383, 767, 1535, 3071, 6143, 12287, 24575, 49151...

Pattern: Each path is `2 * previous + 1` after the first (5).

**Complete table for common solution sizes:**

| Index   | Path  | opd Display | Hex     |
| ------- | ----- | ----------- | ------- |
| sol[0]  | 5     | 5           | 0x05    |
| sol[1]  | 11    | 11          | 0x0B    |
| sol[2]  | 23    | 23          | 0x17    |
| sol[3]  | 47    | 47          | 0x2F    |
| sol[4]  | 95    | 95          | 0x5F    |
| sol[5]  | 191   | **-65**     | 0xBF    |
| sol[6]  | 383   | 383         | 0x17F   |
| sol[7]  | 767   | 767         | 0x2FF   |
| sol[8]  | 1535  | 1535        | 0x5FF   |
| sol[9]  | 3071  | 3071        | 0xBFF   |
| sol[10] | 6143  | 6143        | 0x17FF  |
| sol[11] | 12287 | 12287       | 0x2FFF  |
| sol[12] | 24575 | 24575       | 0x5FFF  |
| sol[13] | 49151 | **-16385**  | 0xBFFF  |
| sol[14] | 98303 | 98303       | 0x17FFF |

**Why negative display?** When the first byte of the minimal encoding has its high bit set (≥0x80),
`opd` interprets it as a signed negative. Path 191 = 0xBF has high bit set → displays as -65.
Path 3071 = 0x0BFF does NOT (first byte is 0x0B) → displays as 3071.

### Verification

```bash
diff <(cat original.clvm.hex) <(run -d reconstructed.clsp)
# Empty output = BYTE-FOR-BYTE IDENTICAL!
```

### Quick Reference: `opd` Output as `opc` Input

If you just need to verify round-trip, `opd` output is valid `opc` input:

```bash
opc "$(opd HEXSTRING)"   # Should reproduce HEXSTRING exactly
```

## Common Pitfalls

### Shell Parsing Issues

Shell can corrupt s-expressions. Always use hex for reliable testing:

```bash
# WRONG - shell may mangle this
brun '(= 5 -65)' '(a b c)'

# CORRECT - use hex
PROG_HEX=$(opc '(= 5 -65)')
SOL_HEX=$(opc '(a b c)')
brun -x $PROG_HEX $SOL_HEX
```

### Zero vs Nil Confusion

In CLVM, `0` and `()` are the SAME (nil/empty atom):

```bash
opc '0'   # → 80
opc '()'  # → 80
```

This affects solution parsing - a `0` in your solution becomes `()`.

### Condition Codes as Path Results

When `opd` shows numeric literals in condition-building code like `(c 22 (c 23 ...))`:

- These numbers (22, 23) are **paths**, not literal values
- Path 22 might yield 51 (CREATE_COIN), path 23 might yield a puzzle hash from solution
- Always trace paths to understand what values they produce

### `run` vs `opc` Output Differences

- `run` compiles Chialisp → reorganizes constants/functions alphabetically
- `opc` compiles raw s-expressions → preserves exact structure
- For byte-identical output, you MUST use `opc` with raw s-expressions

### Alphabetical Ordering Affects CONST Tree

The compiler sorts `defconstant` and `defun` **alphabetically by name**, then builds a tree.
Use `_NNN_` prefixes to control ordering. See "The Alphabetical Helper Ordering Trick" section for details.

### Mode Markers as Path Comparisons

When you see `(= 5 -65)` in decompiled code:

- `-65` is NOT a literal—it's path 191 (unsigned interpretation of 0xbf)
- This compares two solution elements, not a value against -65
- The pattern `(= X MARKER)` is common for mode selection where X and MARKER are both paths into the solution

## Final Output

A complete decompilation produces ONE file: `puzzle.clsp`

### Structure

```chialisp
; ============================================================================
; DECOMPILED: puzzle_name
; Original Hash: abc123...
; ============================================================================
;
; Solution structure: (arg1 arg2 arg3 ...)
; Mode 1: description
; Mode 2: description
;
; ============================================================================

(mod (arg1 arg2 arg3 ...)

  ; ----- CONSTANTS -----
  ; Named with _NNN_ prefix to control tree position
  (defconstant _000_AGG_SIG_ME 50)
  (defconstant _001_CREATE_COIN 51)
  ; ...

  ; ----- HELPER FUNCTIONS -----
  (defun sha256tree (tree)
    (if (l tree)
        (sha256 2 (sha256tree (f tree)) (sha256tree (r tree)))
        (sha256 1 tree)))

  ; ----- MAIN LOGIC -----
  (if (= mode 1)
      ; Mode 1 conditions
      (if (= mode 2)
          ; Mode 2 conditions
          (x)))  ; invalid
)
```

### Verification

```bash
# Must produce empty output - this is the ONLY test that matters
diff <(cat original.clvm.hex) <(run -d puzzle.clsp)
```

### When Stuck

If you can't achieve byte-identical output:

1. **Don't give up** - analyze WHY the bytes differ
2. **Compare structures**: `opd $(cat original.hex)` vs `run puzzle.clsp`
3. **Check CONST tree**: Is it the shape? The order? Missing/extra elements?
4. **Document the blocker**: If truly impossible, explain exactly what compiler limitation prevents it

Common blockers:

- CONST tree shape doesn't match compiler's balanced tree algorithm
- Inline expressions that compiler won't produce
- Specific byte sequences the compiler can't generate

**The goal is still byte-identical** - document blockers as bugs to fix, not as acceptable outcomes.

## Tips

- **Disassemble with opd**: `opd $(cat file.clvm.hex)` shows the s-expression
- **Compare outputs**: Your decompilation should match `opd` output
- **Large puzzles**: NFTs, DIDs have deeply nested structures - focus on outer MOD first
- **Unknown opcodes**: May indicate softfork extensions or newer CLVM versions
- **Negative numbers**: Check sign bit (0x80) in first byte for signed interpretation
- **Identify puzzles**: Use `opd -H` to get tree hash, compare against known hashes in `chia_puzzles_py.programs`
- **Decode hex amounts**: `int("0xABCD", 16)` to get mojos; divide by 10¹² for XCH
- **Quick workflow**: `opd -H` (identify) → `opd` (decompile) → analyze conditions → write annotated .clsp
- **Empirical path finding**: When confused about paths, iterate with `brun` to find which path gives which value:
  ```bash
  for p in $(seq 1 50); do echo -n "path $p: "; brun "$p" 'ENV' 2>&1 | head -1; done
  ```
- **Use hex for testing**: See "Shell Parsing Issues" in Common Pitfalls
- **Test code fragments**: When debugging, isolate and test individual branches before the full puzzle
- **Build env manually**: Use `brun` to evaluate `(c (q . CONST) 1)` with your solution to see the actual runtime environment
- **Check both outputs**: Create byte-identical (opc) AND readable (run) versions—verify they produce same results
