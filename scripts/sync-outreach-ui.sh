#!/usr/bin/env bash
# Keep Quantum Console embed in sync with outreach/static (single source of truth).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/outreach/static"
DST="$ROOT/console/static/outreach"
mkdir -p "$DST"
cp -f "$SRC/index.html" "$SRC/app.js" "$SRC/styles.css" "$DST/"
echo "Synced outreach UI → console/static/outreach"
diff -q "$SRC/index.html" "$DST/index.html"
diff -q "$SRC/app.js" "$DST/app.js"
diff -q "$SRC/styles.css" "$DST/styles.css"
echo "OK: trees match"
