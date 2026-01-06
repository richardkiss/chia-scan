#!/bin/bash
# Query to extract large blocks from blockchain database
# Run this on your remote box

DB_PATH="${1:-blockchain_v2_mainnet.sqlite}"
MIN_SIZE="${2:-50000}"
LIMIT="${3:-20}"
OUTPUT_FILE="large_blocks_${MIN_SIZE}_dump.txt"

echo "Exporting up to $LIMIT blocks with compressed size >= $MIN_SIZE bytes"
echo "Database: $DB_PATH"
echo "Output: $OUTPUT_FILE"
echo ""
echo "Running query (this may take a while)..."

# Export the blocks
sqlite3 "$DB_PATH" <<EOF
.mode csv
.headers on
.output $OUTPUT_FILE

-- Get blocks with generators larger than threshold, compressed
SELECT 
    height,
    hex(header_hash) as header_hash_hex,
    length(block) as compressed_size,
    hex(block) as block_hex
FROM full_blocks 
WHERE in_main_chain = 1 
    AND block IS NOT NULL
    AND length(block) >= $MIN_SIZE
ORDER BY length(block) DESC
LIMIT $LIMIT;
EOF

EXPORTED=$(wc -l < "$OUTPUT_FILE")
EXPORTED=$((EXPORTED - 1))  # Subtract header line

echo ""
echo "Done! Exported $EXPORTED blocks to $OUTPUT_FILE"
echo "File size: $(ls -lh $OUTPUT_FILE | awk '{print $5}')"
echo ""
echo "Next steps:"
echo "  1. Compress: gzip $OUTPUT_FILE"
echo "  2. Download: scp user@remote:$OUTPUT_FILE.gz ."
