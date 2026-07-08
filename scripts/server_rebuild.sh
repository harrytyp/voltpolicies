#!/usr/bin/env bash
set -euo pipefail

# Server-side rebuild: fetch latest raw data, build FAISS index, push back.
# Called by cron after CI has committed new raw data.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Use HERMES_GIT_TOKEN if available (from cron env)
if [ -n "${HERMES_GIT_TOKEN:-}" ]; then
    git remote set-url origin "https://harrytyp:${HERMES_GIT_TOKEN}@github.com/harrytyp/voltpolicies.git"
fi

# Use HF_TOKEN if available (faster model downloads)
if [ -n "${HF_TOKEN:-}" ]; then
    export HF_TOKEN
fi

echo "=== Server Rebuild $(date -u '+%Y-%m-%d %H:%M UTC') ==="

# 1. Pull latest raw data from CI
echo "--- Pulling latest from GitHub ---"
git pull --rebase origin main

# 2. Rebuild FAISS index (heavy lifting — sentence-transformers)
echo "--- Building FAISS semantic index ---"
uv run python scripts/build_index.py

INDEX_SIZE=$(find cache/faiss.index -printf "%s" 2>/dev/null | numfmt --to=iec 2>/dev/null || ls -lh cache/faiss.index | awk '{print $5}')
CHUNK_COUNT=$(python3 -c "import json; d=json.load(open('cache/chunks.json')); print(len(d))" 2>/dev/null || echo "?")
echo "Index built: $INDEX_SIZE, $CHUNK_COUNT chunks"

# 3. Generate STATUS.md and SOURCES.md
echo "--- Generating STATUS.md ---"
uv run python .github/scripts/generate_status.py

echo "--- Generating SOURCES.md ---"
uv run python .github/scripts/generate_sources.py

# 4. Commit and push
echo "--- Committing and pushing ---"
git config user.name "Volt Policies Server"
git config user.email "server@voltpolicies.local"

git add cache/ STATUS.md SOURCES.md

if git diff --cached --quiet; then
    echo "No changes — nothing to push"
else
    CHANGED=$(git diff --cached --stat | tail -1)
    git commit -m "Server rebuild: $CHANGED"
    git pull --rebase origin main
    git push origin main
    echo "Pushed! ✅"
fi

echo "=== Done $(date -u '+%Y-%m-%d %H:%M UTC') ==="
