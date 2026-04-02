#!/bin/bash
# Guardian One — Docker Entrypoint
# ==================================
# Auto-initializes the database on first run, then passes
# control to main.py with whatever arguments were given.

set -e

DB_PATH="${GUARDIAN_DATA_DIR:-data}/guardian.db"

# First-run: initialize database and import existing data
if [ ! -f "$DB_PATH" ]; then
    echo "=== First run detected — initializing database ==="
    python main.py --db-init
    echo "=== Database initialized at $DB_PATH ==="
    echo ""
fi

# Pass through to main.py with all arguments
exec python main.py "$@"
