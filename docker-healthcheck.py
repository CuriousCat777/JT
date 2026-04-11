#!/usr/bin/env python3
"""Non-mutating Docker HEALTHCHECK for the Guardian One database.

Reads the resolved DB path from ``/tmp/.guardian_db_path`` (written
by ``docker-entrypoint.sh`` when it parses the container's startup
args), falling back to ``${GUARDIAN_DATA_DIR:-data}/guardian.db`` if
no marker exists yet.  The check:

* exits ``1`` (unhealthy) if the DB file does not exist — the
  entrypoint has not yet finished initializing the schema, or the
  container was started with a stale ``--db-path`` that was never
  created;
* opens the file with ``mode=ro`` so the probe cannot create or
  mutate the database (unlike ``GuardianDatabase()`` which runs
  ``_initialize_schema`` on every instantiation);
* runs a trivial ``SELECT 1`` to make sure the file is actually a
  valid SQLite database.

Using a script (instead of an inline ``python -c`` in the
Dockerfile) keeps the logic readable and testable.
"""

from __future__ import annotations

import os
import sqlite3
import sys

_MARKER = "/tmp/.guardian_db_path"


def _resolve_db_path() -> str:
    try:
        with open(_MARKER, encoding="utf-8") as f:
            path = f.read().strip()
        if path:
            return path
    except OSError:
        pass
    data_dir = os.environ.get("GUARDIAN_DATA_DIR", "data")
    return os.path.join(data_dir, "guardian.db")


def main() -> int:
    db_path = _resolve_db_path()
    if not db_path or not os.path.exists(db_path):
        return 1
    try:
        conn = sqlite3.connect(
            f"file:{db_path}?mode=ro", uri=True, timeout=5
        )
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
