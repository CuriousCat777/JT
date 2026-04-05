"""Input Cortex — keystroke intelligence agent with daemon collector.

Responsibilities:
- Receive encrypted keystroke batches from phone (Android IME / iOS keyboard)
- Process raw input into classified, PHI-scrubbed context blocks
- Run as a background daemon that listens for incoming payloads
- Store processed sessions in encrypted vault
- Provide queryable context for other agents and AI sessions
- Generate behavioral summaries (what was Jeremy doing today?)
- Expose skill interface for Guardian One and external AI dispatch

Architecture:
    Phone keyboard ──► HTTP listener (localhost or LAN) ──► InputCortex
         │                                                       │
         └── encrypted payload ──────────────────────► process_batch()
                                                            │
                                                   ┌───────┴────────┐
                                                   │ classify       │
                                                   │ scrub PHI/PII  │
                                                   │ extract intent  │
                                                   │ summarize       │
                                                   └───────┬────────┘
                                                            │
                                              ┌─────────────┴──────────────┐
                                              │ session_*.json (vault)     │
                                              │ cortex_index.jsonl         │
                                              │ daily_digest.json          │
                                              └────────────────────────────┘

Daemon modes:
    listener   — HTTP server accepting keystroke payloads from phone
    watcher    — File watcher monitoring a drop directory for payloads
    both       — listener + watcher combined

Skill interface (for AI dispatch):
    InputCortex exposes these operations as invocable skills:
    - query_context(category, app, since, limit)
    - daily_digest(date)
    - session_summary(session_id)
    - behavioral_pattern(days)
"""

from __future__ import annotations

import json
import os
import signal
import threading
import time
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.base_agent import AgentReport, AgentStatus, BaseAgent
from guardian_one.core.config import AgentConfig
from guardian_one.integrations.input_stream import (
    ContextBlock,
    InputCategory,
    InputStreamProcessor,
    RawKeystrokeBatch,
)


class InputCortex(BaseAgent):
    """Keystroke intelligence agent — processes phone input into searchable context.

    Extends BaseAgent so it integrates with Guardian One's scheduler,
    audit log, and AI engine.
    """

    def __init__(
        self,
        config: AgentConfig,
        audit: AuditLog,
        data_dir: str = "data",
    ) -> None:
        super().__init__(config=config, audit=audit)
        self._data_dir = Path(data_dir) / "input_cortex"
        self._drop_dir = Path(data_dir) / "input_cortex" / "incoming"
        self._processor: InputStreamProcessor | None = None

        # Daemon state
        self._daemon_thread: threading.Thread | None = None
        self._http_server: HTTPServer | None = None
        self._stop_event = threading.Event()

        # Stats
        self._batches_processed = 0
        self._batches_redacted = 0
        self._sessions_flushed = 0
        self._last_batch_time: str = ""

        # Auth token for HTTP listener (generated on initialize, or from config)
        self._auth_token: str = ""

    # ── Public properties ─────────────────────────────────────────────────

    @property
    def drop_dir(self) -> Path:
        """Directory watched by the daemon for payload JSON files."""
        return self._drop_dir

    @property
    def data_dir(self) -> Path:
        """Directory where processed session data is written."""
        return self._data_dir

    @property
    def auth_token(self) -> str:
        """Auth token required for HTTP listener (empty string when disabled)."""
        return self._auth_token

    # ── BaseAgent Lifecycle ───────────────────────────────────────────────

    def initialize(self) -> None:
        """Set up the processor and directories.

        Idempotent: repeated calls do NOT reset in-memory processor state
        or running counters/sessions if already initialized.
        """
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._drop_dir.mkdir(parents=True, exist_ok=True)

        session_timeout = self.config.custom.get(
            "session_timeout_seconds", 300
        )
        min_words = self.config.custom.get("min_words_to_store", 3)

        if self._processor is None:
            self._processor = InputStreamProcessor(
                output_dir=self._data_dir,
                min_words_to_store=min_words,
                session_timeout_seconds=session_timeout,
            )

        # Generate an auth token on first init (or load from config/env)
        if not self._auth_token:
            import os
            import secrets
            self._auth_token = (
                self.config.custom.get("listener_auth_token")
                or os.environ.get("CORTEX_AUTH_TOKEN")
                or secrets.token_urlsafe(24)
            )

        self._set_status(AgentStatus.IDLE)
        self.log(
            "input_cortex_initialized",
            details={
                "data_dir": str(self._data_dir),
                "drop_dir": str(self._drop_dir),
                "session_timeout": session_timeout,
            },
        )

    def run(self) -> AgentReport:
        """Periodic run cycle — process any pending drop files + flush stale sessions."""
        self._set_status(AgentStatus.RUNNING)
        actions = []
        alerts = []

        # Process any files in the drop directory
        drop_count = self._process_drop_dir()
        if drop_count:
            actions.append(f"Processed {drop_count} drop file(s)")

        # Flush stale sessions (older than timeout)
        flushed = self._flush_stale_sessions()
        if flushed:
            actions.append(f"Flushed {len(flushed)} stale session(s)")
            self._sessions_flushed += len(flushed)

        # Generate daily digest if past midnight
        digest = self._maybe_generate_digest()
        if digest:
            actions.append("Generated daily digest")

        self._set_status(AgentStatus.IDLE)

        summary = (
            f"Cortex: {self._batches_processed} batches processed, "
            f"{self._batches_redacted} redacted, "
            f"{self._sessions_flushed} sessions flushed"
        )

        return AgentReport(
            agent_name=self.name,
            status="ok",
            summary=summary,
            actions_taken=actions,
            alerts=alerts,
            data={
                "batches_processed": self._batches_processed,
                "batches_redacted": self._batches_redacted,
                "sessions_flushed": self._sessions_flushed,
                "last_batch": self._last_batch_time,
                "open_sessions": (
                    len(self._processor.get_open_sessions())
                    if self._processor else 0
                ),
            },
        )

    def report(self) -> AgentReport:
        """Read-only status report."""
        open_sessions = (
            self._processor.get_open_sessions() if self._processor else []
        )
        return AgentReport(
            agent_name=self.name,
            status=self.status.value,
            summary=(
                f"InputCortex: {self._batches_processed} processed, "
                f"{len(open_sessions)} open sessions"
            ),
            data={
                "batches_processed": self._batches_processed,
                "batches_redacted": self._batches_redacted,
                "sessions_flushed": self._sessions_flushed,
                "open_sessions": open_sessions,
                "daemon_running": self._daemon_thread is not None
                    and self._daemon_thread.is_alive(),
            },
        )

    def shutdown(self) -> None:
        """Stop daemon and flush all sessions."""
        self.stop_daemon()
        if self._processor:
            paths = self._processor.flush_all()
            if paths:
                self.log(
                    "shutdown_flush",
                    details={"sessions_flushed": len(paths)},
                )
        super().shutdown()

    # ── Daemon Mode ───────────────────────────────────────────────────────

    def start_daemon(
        self,
        mode: str = "both",
        port: int = 9473,
        bind: str = "127.0.0.1",
    ) -> None:
        """Start the background daemon for receiving keystroke payloads.

        Args:
            mode: "listener" (HTTP), "watcher" (file drop), or "both"
            port: HTTP listener port (default 9473)
            bind: interface to bind (default loopback 127.0.0.1). Pass
                "0.0.0.0" ONLY when you understand the exposure and have
                a reverse proxy / firewall / auth token enforced.
        """
        if self._daemon_thread and self._daemon_thread.is_alive():
            self.log("daemon_already_running", severity=Severity.WARNING)
            return

        self._stop_event.clear()

        def _daemon_loop():
            threads = []

            if mode in ("listener", "both"):
                t = threading.Thread(
                    target=self._run_listener, args=(port, bind), daemon=True
                )
                t.start()
                threads.append(t)
                self.log(
                    "listener_started",
                    details={"port": port, "bind": bind},
                )

            if mode in ("watcher", "both"):
                t = threading.Thread(
                    target=self._run_watcher, daemon=True
                )
                t.start()
                threads.append(t)
                self.log("watcher_started")

            # Wait for stop signal
            self._stop_event.wait()

            # Cleanup
            if self._http_server:
                self._http_server.shutdown()
            for t in threads:
                t.join(timeout=5)

        self._daemon_thread = threading.Thread(
            target=_daemon_loop, daemon=True
        )
        self._daemon_thread.start()

        self.log(
            "daemon_started",
            details={"mode": mode, "port": port},
        )

    def stop_daemon(self) -> None:
        """Stop the background daemon."""
        self._stop_event.set()
        if self._http_server:
            self._http_server.shutdown()
        if self._daemon_thread:
            self._daemon_thread.join(timeout=10)
            self._daemon_thread = None
        self.log("daemon_stopped")

    def _run_listener(self, port: int, bind: str = "127.0.0.1") -> None:
        """HTTP listener that accepts keystroke payloads.

        Requires a matching X-Cortex-Token header on all requests.
        """
        cortex = self

        def _authorized(handler) -> bool:
            if not cortex._auth_token:
                return True  # auth disabled (token empty)
            token = handler.headers.get("X-Cortex-Token", "")
            # Constant-time comparison
            import hmac
            return hmac.compare_digest(token, cortex._auth_token)

        class _Handler(BaseHTTPRequestHandler):
            def _reject(self):
                self.send_response(401)
                self.send_header("WWW-Authenticate", "X-Cortex-Token")
                self.end_headers()
                self.wfile.write(b"unauthorized")

            def do_POST(self):
                if not _authorized(self):
                    self._reject()
                    return
                if self.path == "/input":
                    length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(length)
                    try:
                        payload = json.loads(body)
                        block = cortex.ingest_payload(payload)
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        result = {
                            "status": "ok",
                            "block_id": block.block_id if block else None,
                            "redacted": block is None,
                        }
                        self.wfile.write(json.dumps(result).encode())
                    except Exception as e:
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(str(e).encode())
                elif self.path == "/batch":
                    length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(length)
                    try:
                        payloads = json.loads(body)
                        results = []
                        for p in payloads:
                            block = cortex.ingest_payload(p)
                            results.append({
                                "block_id": block.block_id if block else None,
                                "redacted": block is None,
                            })
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({
                            "status": "ok",
                            "results": results,
                        }).encode())
                    except Exception as e:
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(str(e).encode())
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_GET(self):
                if not _authorized(self):
                    self._reject()
                    return
                if self.path == "/status":
                    report = cortex.report()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(report.data).encode())
                elif self.path.startswith("/query"):
                    # Simple query: /query?category=search&limit=10
                    from urllib.parse import urlparse, parse_qs
                    params = parse_qs(urlparse(self.path).query)
                    results = cortex.query_context(
                        category=params.get("category", [None])[0],
                        app=params.get("app", [None])[0],
                        since=params.get("since", [None])[0],
                        limit=int(params.get("limit", [50])[0]),
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(results).encode())
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass  # Suppress default logging

        self._http_server = HTTPServer((bind, port), _Handler)
        self._http_server.serve_forever()

    def _run_watcher(self) -> None:
        """File watcher that processes JSON payloads dropped into incoming/."""
        while not self._stop_event.is_set():
            self._process_drop_dir()
            self._stop_event.wait(timeout=2)

    # ── Ingestion ─────────────────────────────────────────────────────────

    def ingest_payload(self, payload: dict[str, Any]) -> ContextBlock | None:
        """Ingest a single keystroke payload dict and process it."""
        if not self._processor:
            self.initialize()
            assert self._processor is not None

        batch = RawKeystrokeBatch(
            device_id=payload.get("device_id", "unknown"),
            app_package=payload.get("app_package", ""),
            app_label=payload.get("app_label", "Unknown"),
            timestamp_start=payload.get(
                "timestamp_start",
                datetime.now(timezone.utc).isoformat(),
            ),
            timestamp_end=payload.get(
                "timestamp_end",
                datetime.now(timezone.utc).isoformat(),
            ),
            text=payload.get("text", ""),
            field_hint=payload.get("field_hint", ""),
            input_type=payload.get("input_type", ""),
            word_count=len(payload.get("text", "").split()),
            session_id=payload.get("session_id", "default"),
        )

        block = self._processor.process_batch(batch)

        if block:
            self._batches_processed += 1
            self._last_batch_time = batch.timestamp_start
            self.log(
                "batch_processed",
                details={
                    "block_id": block.block_id,
                    "category": block.category,
                    "app": block.app_label,
                    "words": block.word_count,
                },
            )
        else:
            self._batches_redacted += 1
            self.log(
                "batch_redacted",
                details={"app": batch.app_label},
            )

        return block

    def _process_drop_dir(self) -> int:
        """Process all JSON files in the drop directory."""
        if not self._drop_dir.exists():
            return 0

        count = 0
        for path in sorted(self._drop_dir.glob("*.json")):
            try:
                with open(path) as f:
                    data = json.load(f)

                # Handle single or batch payloads
                payloads = data if isinstance(data, list) else [data]
                for p in payloads:
                    self.ingest_payload(p)
                    count += 1

                # Move processed file
                processed_dir = self._drop_dir / "processed"
                processed_dir.mkdir(exist_ok=True)
                path.rename(processed_dir / path.name)

            except Exception as e:
                self.log(
                    "drop_file_error",
                    severity=Severity.WARNING,
                    details={"file": path.name, "error": str(e)},
                )
        return count

    def _flush_stale_sessions(self) -> list[Path]:
        """Flush sessions idle longer than the configured session_timeout.

        Uses the InputStreamProcessor's monotonic last-update tracker —
        does NOT flush active sessions.
        """
        if not self._processor:
            return []
        return self._processor.flush_stale_sessions()

    # ── Skill Interface (AI-invocable) ────────────────────────────────────

    def query_context(
        self,
        *,
        category: str | None = None,
        app: str | None = None,
        since: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query processed context blocks. Invocable as a skill by other agents/AI."""
        if not self._processor:
            return []
        return self._processor.query_index(
            category=category, app=app, since=since, limit=limit
        )

    def daily_digest(self, date: str | None = None) -> dict[str, Any]:
        """Generate a behavioral digest for a given date.

        Returns app usage, category distribution, intent signals,
        and word count totals — no raw text, just patterns.
        """
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        entries = self.query_context(since=date, limit=500)

        # Aggregate
        app_words: dict[str, int] = {}
        cat_counts: dict[str, int] = {}
        total_words = 0
        total_sessions = len(entries)

        for e in entries:
            words = e.get("words", 0)
            total_words += words
            cat = e.get("category", "unknown")
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
            for app_name in e.get("apps", []):
                app_words[app_name] = app_words.get(app_name, 0) + words

        digest = {
            "date": date,
            "total_sessions": total_sessions,
            "total_words": total_words,
            "category_distribution": cat_counts,
            "app_usage": dict(
                sorted(app_words.items(), key=lambda x: -x[1])
            ),
            "generated": datetime.now(timezone.utc).isoformat(),
        }

        # Save digest
        digest_path = self._data_dir / f"digest_{date}.json"
        with open(digest_path, "w") as f:
            json.dump(digest, f, indent=2)

        return digest

    def behavioral_pattern(self, days: int = 7) -> dict[str, Any]:
        """Analyze behavioral patterns over N days.

        Returns trends in app usage, typing volume, category shifts,
        and recurring intent signals.
        """
        since = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).strftime("%Y-%m-%d")

        entries = self.query_context(since=since, limit=2000)

        daily_words: dict[str, int] = {}
        daily_sessions: dict[str, int] = {}
        app_frequency: dict[str, int] = {}
        cat_frequency: dict[str, int] = {}

        for e in entries:
            day = e.get("started", "")[:10]
            words = e.get("words", 0)
            daily_words[day] = daily_words.get(day, 0) + words
            daily_sessions[day] = daily_sessions.get(day, 0) + 1
            cat = e.get("category", "unknown")
            cat_frequency[cat] = cat_frequency.get(cat, 0) + 1
            for app_name in e.get("apps", []):
                app_frequency[app_name] = app_frequency.get(app_name, 0) + 1

        return {
            "period_days": days,
            "since": since,
            "daily_words": daily_words,
            "daily_sessions": daily_sessions,
            "top_apps": dict(
                sorted(app_frequency.items(), key=lambda x: -x[1])[:10]
            ),
            "category_distribution": cat_frequency,
            "avg_words_per_day": (
                sum(daily_words.values()) // max(len(daily_words), 1)
            ),
        }

    def session_summary(self, session_id: str) -> dict[str, Any] | None:
        """Return a detailed summary of a specific typing session.

        Looks up the session in the on-disk index first, then loads the
        full session JSON. Returns None if the session isn't found.
        """
        if not self._processor:
            return None

        # First check open in-memory sessions
        for s in self._processor.get_open_sessions():
            if s["session_id"] == session_id:
                return {**s, "status": "open"}

        # Check index for completed sessions
        index_path = self._data_dir / "cortex_index.jsonl"
        if not index_path.exists():
            return None

        with open(index_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("session_id") != session_id:
                    continue
                # Load full session file
                session_file = self._data_dir / entry.get("file", "")
                if session_file.exists():
                    with open(session_file) as sf:
                        data = json.load(sf)
                    data["status"] = "flushed"
                    return data
                return {**entry, "status": "flushed_file_missing"}
        return None

    def _maybe_generate_digest(self) -> dict[str, Any] | None:
        """Generate today's digest if it doesn't exist yet."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        digest_path = self._data_dir / f"digest_{today}.json"
        if digest_path.exists():
            return None
        # Only generate if we have data
        entries = self.query_context(since=today, limit=1)
        if not entries:
            return None
        return self.daily_digest(today)

    # ── Skill Manifest ────────────────────────────────────────────────────

    @staticmethod
    def skill_manifest() -> dict[str, Any]:
        """Return the skill manifest for AI dispatch integration.

        Other AI sessions can use this to know what InputCortex can do
        and how to invoke it via the dispatch protocol.
        """
        return {
            "agent": "input_cortex",
            "version": "1.0.0",
            "description": (
                "Keystroke intelligence agent. Processes phone input into "
                "classified, PHI-scrubbed context blocks. Provides behavioral "
                "digests and pattern analysis."
            ),
            "skills": [
                {
                    "name": "query_context",
                    "description": "Search processed input sessions by category, app, or date",
                    "params": {
                        "category": "search|message|note|command|navigation|code|form",
                        "app": "app name filter",
                        "since": "ISO date",
                        "limit": "max results (default 50)",
                    },
                    "returns": "list of session index entries",
                },
                {
                    "name": "daily_digest",
                    "description": "Behavioral digest for a date — app usage, categories, word counts",
                    "params": {"date": "YYYY-MM-DD (default today)"},
                    "returns": "digest object with aggregated stats",
                },
                {
                    "name": "behavioral_pattern",
                    "description": "Multi-day behavioral trend analysis",
                    "params": {"days": "lookback period (default 7)"},
                    "returns": "pattern object with trends and top apps",
                },
                {
                    "name": "session_summary",
                    "description": "Detailed summary of a specific typing session",
                    "params": {"session_id": "session identifier"},
                    "returns": "session object with all blocks",
                },
            ],
            "daemon_modes": ["listener", "watcher", "both"],
            "default_port": 9473,
            "default_bind": "127.0.0.1",
            "auth": "X-Cortex-Token header required on all requests",
            "endpoints": {
                "POST /input": "Single keystroke payload",
                "POST /batch": "Array of keystroke payloads",
                "GET /status": "Agent status and stats",
                "GET /query": "Query processed sessions",
            },
            "privacy": {
                "phi_scrubbing": True,
                "credential_detection": True,
                "raw_text_stored": False,
                "encryption_at_rest": "filesystem-level (OS/disk); Vault-backed encryption is roadmap",
            },
            "dispatch_roles": ["researcher", "builder", "auditor"],
        }
