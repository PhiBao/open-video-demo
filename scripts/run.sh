#!/usr/bin/env bash
# One command: narration -> recording -> assembly -> QA for one video project.
#
#   ./scripts/run.sh                          the only project, or $DEMO_DIR
#   ./scripts/run.sh --project acme-demo      videos/acme-demo (or a path)
#   ./scripts/run.sh --project acme --only s3_app
#   ./scripts/run.sh --project acme --force   regenerate all audio and clips
#   ./scripts/run.sh --project acme --no-record
set -euo pipefail
TEMPLATE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PY="$TEMPLATE/.venv/bin/python"
[ -x "$PY" ] || PY="${PYTHON:-python3}"

ONLY=(); FORCE=""; PROJECT="${DEMO_DIR:-}"; DO_TTS=1; DO_REC=1; DO_BUILD=1; DO_QA=1
while [ $# -gt 0 ]; do
  case "$1" in
    --project) shift; PROJECT="${1:?--project needs a name}"; shift ;;
    --only) shift; while [ $# -gt 0 ] && [[ "$1" != --* ]]; do ONLY+=("$1"); shift; done ;;
    --force) FORCE="--force"; shift ;;
    --no-tts) DO_TTS=0; shift ;;
    --no-record) DO_REC=0; shift ;;
    --no-build) DO_BUILD=0; shift ;;
    --no-qa) DO_QA=0; shift ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done

if [ -n "$PROJECT" ]; then
  case "$PROJECT" in
    /*) DEMO_DIR="$PROJECT" ;;
    *)  if [ -d "$PROJECT" ]; then DEMO_DIR="$(cd "$PROJECT" && pwd)"
        else DEMO_DIR="$TEMPLATE/videos/$PROJECT"; fi ;;
  esac
  if [ ! -f "$DEMO_DIR/script/story.json" ]; then
    echo "not a project: $DEMO_DIR (expected script/story.json)" >&2
    echo "create one with: ./scripts/new.sh <name>" >&2
    exit 2
  fi
  export DEMO_DIR
fi

step() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }

if [ "$DO_TTS" = 1 ]; then
  step "tts    narrate script/story.json"
  if [ ${#ONLY[@]} -gt 0 ]; then
    "$PY" "$TEMPLATE/scripts/tts.py" $FORCE --only "${ONLY[@]}"
  else
    "$PY" "$TEMPLATE/scripts/tts.py" $FORCE
  fi
fi
if [ "$DO_REC" = 1 ]; then
  step "record scenes -> clips/"
  if [ ${#ONLY[@]} -gt 0 ]; then
    "$PY" "$TEMPLATE/scripts/record.py" $FORCE --only "${ONLY[@]}"
  else
    "$PY" "$TEMPLATE/scripts/record.py" $FORCE
  fi
fi
if [ "$DO_BUILD" = 1 ]; then
  step "build  ffmpeg assembly"
  "$PY" "$TEMPLATE/scripts/build.py"
fi
if [ "$DO_QA" = 1 ]; then
  step "qa     validation + contact sheet"
  "$PY" "$TEMPLATE/scripts/qa.py"
fi
step "done"
