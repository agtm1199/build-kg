#!/usr/bin/env bash
set -euo pipefail

FILE="${1:-}"

if [[ -z "$FILE" || ! -f "$FILE" ]]; then
  echo "Usage: $0 <markdown-file>"
  exit 1
fi

MARKER='## You are here'

# Ensure marker exists
if ! grep -qF "$MARKER" "$FILE"; then
  echo "Marker not found: $MARKER"
  exit 2
fi

# Remove everything up to and including the marker line
tmp="$(mktemp)"
awk -v marker="$MARKER" '
  found { print }
  $0 == marker { found=1; next }
' "$FILE" > "$tmp"

mv "$tmp" "$FILE"

echo "Updated: $FILE"

