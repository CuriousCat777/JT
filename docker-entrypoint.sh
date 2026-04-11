#!/bin/bash
# Guardian One — Docker Entrypoint
# ==================================
# Auto-initializes the database on first run, then passes control to
# main.py with whatever arguments were given.

set -e

# Parse the user's args so the auto-init step can target the same DB
# file that the user's command will use.
user_db_path=""
user_wants_db_init=0

i=1
while [ $i -le $# ]; do
    arg=$(eval echo "\${$i}")
    case "$arg" in
        --db-init)
            user_wants_db_init=1
            ;;
        --db-path)
            next=$((i + 1))
            user_db_path=$(eval echo "\${$next}")
            ;;
        --db-path=*)
            user_db_path="${arg#--db-path=}"
            ;;
    esac
    i=$((i + 1))
done

# Resolve the database path used by the auto-init check. If the user
# passed --db-path, honor it so we don't initialize a stale default
# DB alongside the one the user actually reads/writes. Otherwise fall
# back to GUARDIAN_DATA_DIR/guardian.db (matching GuardianDatabase's
# own default-resolution).
if [ -n "$user_db_path" ]; then
    DB_PATH="$user_db_path"
else
    DB_PATH="${GUARDIAN_DATA_DIR:-data}/guardian.db"
fi

# First-run: initialize the database and import existing data, but
# skip when the user has already asked for --db-init (otherwise
# initialization would run twice in one container start and
# import_audit_jsonl would duplicate system_logs rows).
if [ ! -f "$DB_PATH" ] && [ "$user_wants_db_init" -eq 0 ]; then
    echo "=== First run detected — initializing database at $DB_PATH ==="
    if [ -n "$user_db_path" ]; then
        python main.py --db-init --db-path "$user_db_path"
    else
        python main.py --db-init
    fi
    echo "=== Database initialized ==="
    echo ""
fi

# Pass through to main.py with all arguments
exec python main.py "$@"
