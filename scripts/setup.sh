#!/usr/bin/env bash
# Install python deps and (if needed) a browser. Idempotent.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

for c in ffmpeg ffprobe; do
  command -v "$c" >/dev/null || { echo "MISSING $c - install ffmpeg first" >&2; exit 1; }
done
echo "ffmpeg   $(ffmpeg -version | head -1 | awk '{print $3}')"

if [ ! -x .venv/bin/python ]; then
  if command -v uv >/dev/null; then uv venv .venv; else python3 -m venv .venv; fi
fi

if command -v uv >/dev/null; then
  uv pip install -q -r requirements.txt --python .venv
else
  .venv/bin/pip install -q -r requirements.txt
fi
echo "python   $(.venv/bin/python --version)  playwright $(.venv/bin/python -c 'import importlib.metadata as m; print(m.version("playwright"))' 2>/dev/null || echo '?')"
echo "edge-tts $(.venv/bin/edge-tts --version 2>/dev/null || echo 'installed')"

if [ -n "${CHROMIUM_PATH:-}" ] || command -v chromium >/dev/null 2>&1 \
   || command -v chromium-browser >/dev/null 2>&1 || command -v google-chrome >/dev/null 2>&1; then
  echo "browser  system chromium found (no download needed)"
else
  echo "browser  installing playwright chromium..."
  .venv/bin/playwright install chromium
fi

echo
echo "ready. next: edit script/story.json and run ./scripts/run.sh"
