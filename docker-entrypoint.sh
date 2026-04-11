#!/bin/bash
# Guardian One — Docker Entrypoint
# ==================================
# Auto-initializes the database on first run, then passes control to
# main.py with whatever arguments were given.
#
# Init tracking:
#   Auto-init would be naive if it only checked whether the DB file
#   exists, because --db-init creates the schema file *before*
#   running optional imports. A mid-init failure (e.g. malformed
#   ledger JSON, a signal kill) could leave behind a DB file that
#   looks "initialized" to a naive entrypoint, so the next container
#   start would silently proceed without ever importing seed data.
#
#   We track successful initialization with a sentinel file
#   ("${DB_PATH}.init_complete") that is only written after a
#   zero-exit --db-init. If the DB file exists but the sentinel
#   does not, auto-init is re-run.

set -e

# Parse the user's args so the auto-init step can target the same DB
# file that the user's command will use.
user_db_path=""
user_wants_db_init=0

i=1
while [ $i -le $# ]; do
    # Bash indirect parameter expansion (``${!i}``) — safer than
    # ``eval echo "\${$i}"`` which would silently drop values that
    # look like ``echo`` flags (``-n``, ``-e``, …).
    arg="${!i}"
    case "$arg" in
        --db-init)
            user_wants_db_init=1
            ;;
        --db-path)
            next=$((i + 1))
            user_db_path="${!next}"
            ;;
        --db-path=*)
            user_db_path="${arg#--db-path=}"
            ;;
    esac
    i=$((i + 1))
done

# Resolve the database path used by the auto-init check. If the user
# passed --db-path, honor it so we don't initialize a stale default
# DB alongside the one the user actually reads/writes. Otherwise
# fall back to GUARDIAN_DATA_DIR/guardian.db (matching
# GuardianDatabase's own default-resolution).
if [ -n "$user_db_path" ]; then
    DB_PATH="$user_db_path"
else
    DB_PATH="${GUARDIAN_DATA_DIR:-data}/guardian.db"
fi
INIT_SENTINEL="${DB_PATH}.init_complete"

# Persist the resolved DB path so the Docker HEALTHCHECK probe can
# verify the *same* file the main process is actually using, even
# when the container was started with a custom --db-path. The file
# lives in /tmp so it's container-local and doesn't need to be
# mounted. Best-effort; failure is non-fatal.
printf '%s' "$DB_PATH" > /tmp/.guardian_db_path 2>/dev/null || true

# If the user's command IS --db-init, run it directly (no exec) so we
# can touch the sentinel on success. This keeps re-runs of --db-init
# idempotent for the sentinel tracking.
if [ "$user_wants_db_init" -eq 1 ]; then
    status=0
    python main.py "$@" || status=$?
    if [ $status -eq 0 ]; then
        touch "$INIT_SENTINEL"
    fi
    exit $status
fi

# Auto-init when either the DB file or the sentinel is missing.
# Missing sentinel means a previous --db-init never reached its
# success tail, so imports may be incomplete — re-run to recover.
if [ ! -f "$DB_PATH" ] || [ ! -f "$INIT_SENTINEL" ]; then
    if [ -f "$DB_PATH" ]; then
        echo "=== Previous init incomplete (no sentinel) — re-running ==="
    else
        echo "=== First run detected — initializing database at $DB_PATH ==="
    fi
    if [ -n "$user_db_path" ]; then
        python main.py --db-init --db-path "$user_db_path"
    else
        python main.py --db-init
    fi
    touch "$INIT_SENTINEL"
    echo "=== Database initialized ==="
    echo ""
fi

# Pass through to main.py with all arguments
exec python main.py "$@"
