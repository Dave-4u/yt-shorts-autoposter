#!/usr/bin/env bash
# One command to try it:  ./run.sh        -> Clip Studio on http://127.0.0.1:8765
#                         ./run.sh demo   -> offline demo, renders 2 Shorts to output/demo (no upload)
#                         ./run.sh test   -> test suite
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt -r requirements-dev.txt
fi
PY=.venv/bin/python
case "${1:-web}" in
  test) exec $PY -m pytest -q ;;
  demo) command -v ffmpeg >/dev/null || { echo "ffmpeg is required (sudo apt install ffmpeg)"; exit 1; }
        exec $PY -m shorts_bot demo --max-shorts 2 ;;
  web)  exec $PY -m shorts_bot web --port "${PORT:-8765}" ;;
  *)    shift 0; exec $PY -m shorts_bot "$@" ;;
esac
