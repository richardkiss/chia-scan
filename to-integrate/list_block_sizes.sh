#!/bin/bash
# Quick script to list block sizes without exporting the actual block data
# Processes by rowid in chunks to show progress

DB_PATH="${1:-blockchain_v2_mainnet.sqlite}"
MIN_SIZE="${2:-0}"
CHUNK_SIZE=100

echo "Scanning blockchain for blocks with size >= $MIN_SIZE bytes"
echo "Database: $DB_PATH"
echo ""

# Get the range of rowids (should be fast)
echo "Fetching rowid range..." >&2
RANGE=$(sqlite3 "$DB_PATH" "SELECT MIN(rowid), MAX(rowid) FROM full_blocks;")

MIN_ROWID=$(echo "$RANGE" | cut -d'|' -f1)
MAX_ROWID=$(echo "$RANGE" | cut -d'|' -f2)
TOTAL_ROWS=$((MAX_ROWID - MIN_ROWID + 1))

echo "Rowid range: $MIN_ROWID to $MAX_ROWID ($TOTAL_ROWS rows)" >&2
echo "" >&2

# Print header
printf "%-10s %15s\n" "height" "compressed_size"
printf "%-10s %15s\n" "----------" "---------------"

# Process in chunks by rowid
CURRENT=$MIN_ROWID

while [ $CURRENT -le $MAX_ROWID ]; do
    CHUNK_END=$((CURRENT + CHUNK_SIZE - 1))
    if [ $CHUNK_END -gt $MAX_ROWID ]; then
        CHUNK_END=$MAX_ROWID
    fi
    
    # Calculate and display progress
    PROCESSED=$((CURRENT - MIN_ROWID))
    PERCENT=$((PROCESSED * 100 / TOTAL_ROWS))
    echo "Processing rowids $CURRENT-$CHUNK_END... ($PERCENT%)" >&2
    
    # Query this chunk by rowid
    sqlite3 "$DB_PATH" <<EOF
.mode list
.separator ' '
SELECT 
    printf('%10d', height) || ' ' || printf('%15d', length(block))
FROM full_blocks 
WHERE rowid >= $CURRENT
    AND rowid <= $CHUNK_END
    AND in_main_chain = 1 
    AND block IS NOT NULL
    AND length(block) >= $MIN_SIZE
ORDER BY length(block) DESC;
EOF
    
    CURRENT=$((CHUNK_END + 1))
done

echo "" >&2
echo "Done! Scanned all rows from $MIN_ROWID to $MAX_ROWID" >&2
