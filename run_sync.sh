#!/data/data/com.termux/files/usr/bin/bash

set -u
set -o pipefail

PROJECT_ROOT="/data/data/com.termux/files/home/autotable"
VENV_ACTIVATE="/data/data/com.termux/files/home/autotable/.venv/bin/activate"
PYTHON_SCRIPT="/data/data/com.termux/files/home/autotable/python-sync/tools/fetch_and_translate_unas.py"
OUTPUT_REPO="/data/data/com.termux/files/home/autotable-output"
SOURCE_CSV="/data/data/com.termux/files/home/autotable/python-sync/data/active_products_export.csv"
DEST_CSV="/data/data/com.termux/files/home/autotable-output/active_products_export.csv"
LOG_FILE="/data/data/com.termux/files/home/autotable/sync.log"

timestamp() {
  date "+%Y-%m-%d %H:%M:%S"
}

log() {
  printf '[%s] %s\n' "$(timestamp)" "$*" | tee -a "$LOG_FILE"
}

run_and_log() {
  "$@" 2>&1 | while IFS= read -r line; do
    printf '[%s] %s\n' "$(timestamp)" "$line" | tee -a "$LOG_FILE"
  done
  return ${PIPESTATUS[0]}
}

fail() {
  log "ERROR: $*"
  exit 1
}

mkdir -p "$(dirname "$LOG_FILE")" || {
  echo "[$(timestamp)] ERROR: Could not create log directory for $LOG_FILE" >&2
  exit 1
}

log "Starting sync run"

[ -d "$PROJECT_ROOT" ] || fail "Project root not found: $PROJECT_ROOT"
[ -f "$VENV_ACTIVATE" ] || fail "Virtualenv activate script not found: $VENV_ACTIVATE"
[ -f "$PYTHON_SCRIPT" ] || fail "Python sync script not found: $PYTHON_SCRIPT"
[ -d "$OUTPUT_REPO" ] || fail "Output repository not found: $OUTPUT_REPO"

log "Activating virtualenv: $VENV_ACTIVATE"
# shellcheck disable=SC1090
source "$VENV_ACTIVATE" || fail "Failed to activate virtualenv"

log "Running translation sync script"
run_and_log python "$PYTHON_SCRIPT" --max-items 1000 --page-limit 50 --delay 0 --resume
python_exit=$?
if [ "$python_exit" -ne 0 ]; then
  fail "Python sync script failed with exit code $python_exit"
fi

[ -f "$SOURCE_CSV" ] || fail "Expected CSV not found after sync: $SOURCE_CSV"

log "Copying CSV to output repo"
run_and_log cp "$SOURCE_CSV" "$DEST_CSV" || fail "Failed to copy CSV to output repo"

log "Staging CSV in output repo"
run_and_log git -C "$OUTPUT_REPO" add "active_products_export.csv" || fail "Failed to stage CSV"

if git -C "$OUTPUT_REPO" diff --cached --quiet; then
  log "No CSV changes detected; nothing to commit"
  log "Sync completed successfully"
  exit 0
fi

commit_message="sync: active_products_export.csv $(date '+%Y-%m-%d %H:%M:%S')"
log "Committing CSV update"
run_and_log git -C "$OUTPUT_REPO" commit -m "$commit_message" || fail "Git commit failed"

log "Pushing commit to remote"
run_and_log git -C "$OUTPUT_REPO" push || fail "Git push failed"

log "Sync completed successfully"
exit 0
