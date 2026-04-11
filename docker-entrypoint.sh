#!/bin/bash
# Guardian One — Docker Entrypoint
# ==================================
# Auto-initializes the database on first run, then passes
# control to main.py with whatever arguments were given.

set -e

DB_PATH="${GUARDIAN_DATA_DIR:-data}/guardian.db"

# Detect whether the user already asked for --db-init; if so, skip
# the automatic first-run init to avoid running it twice in the same
# container start (which would re-import audit.jsonl and duplicate
# system_logs rows, since that table has no unique constraint).
user_wants_db_init=0
for arg in "$@"; do
    if [ "$arg" = "--db-init" ]; then
        user_wants_db_init=1
        break
    fi
done

# First-run: initialize database and import existing data, but only
# when the user has not already asked for --db-init.
if [ ! -f "$DB_PATH" ] && [ "$user_wants_db_init" -eq 0 ]; then
    echo "=== First run detected — initializing database ==="
    python main.py --db-init
    echo "=== Database initialized at $DB_PATH ==="
    echo ""
fi

# Pass through to main.py with all arguments
exec python main.py "$@"
