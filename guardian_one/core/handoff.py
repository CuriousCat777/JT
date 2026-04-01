"""Dynamic handoff tracker — auto-generates session briefs from git + audit data.

Backs up each handoff to the Vault (encrypted) so nothing is lost even if
the markdown files are deleted.

Usage:
    python main.py --handoff              # Generate latest handoff
    python main.py --handoff-history      # List all stored handoffs
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from guardian_one.core.audit import AuditLog, Severity


@dataclass
class HandoffEntry:
    """A single session handoff record."""
    session_id: str
    timestamp: str
    branch: str
    commits: list[dict[str, str]]
    files_changed: list[str]
    summary: str
    test_result: str
    audit_snapshot: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        lines = [
            f"# Handoff: {self.summary}",
            "",
            f"**Date:** {self.timestamp}",
            f"**Branch:** `{self.branch}`",
            f"**Tests:** {self.test_result}",
            "",
            "---",
            "",
            "## Commits",
        ]
        for c in self.commits:
            lines.append(f"- `{c['hash'][:8]}` {c['message']}")
        lines += [
            "",
            "## Files Changed",
        ]
        for f in self.files_changed:
            lines.append(f"- `{f}`")
        if self.audit_snapshot:
            lines += [
                "",
                "## Recent Audit Activity",
            ]
            for a in self.audit_snapshot[:10]:
                lines.append(
                    f"- [{a.get('severity', 'info').upper()}] "
                    f"{a.get('agent', '?')}: {a.get('action', '?')}"
                )
        lines.append("")
        return "\n".join(lines)


class HandoffTracker:
    """Generates, stores, and retrieves session handoff briefs.

    Handoffs are written to ``handoffs-and-briefs/`` as markdown files
    and encrypted into the Vault under ``HANDOFF_<session_id>`` keys.
    """

    VAULT_PREFIX = "HANDOFF_"
    VAULT_INDEX_KEY = "HANDOFF_INDEX"

    def __init__(
        self,
        repo_root: Path | None = None,
        output_dir: Path | None = None,
        audit: AuditLog | None = None,
        vault: Any | None = None,
    ) -> None:
        self._repo = repo_root or Path.cwd()
        self._output_dir = output_dir or self._repo / "handoffs-and-briefs"
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._audit = audit
        self._vault = vault

    # ------------------------------------------------------------------
    # Git helpers
    # ------------------------------------------------------------------

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self._repo), *args],
            capture_output=True, text=True, timeout=15,
        )
        return result.stdout.strip()

    def _current_branch(self) -> str:
        return self._git("rev-parse", "--abbrev-ref", "HEAD")

    def _recent_commits(self, n: int = 10) -> list[dict[str, str]]:
        raw = self._git("log", f"-{n}", "--pretty=format:%H|%s|%ai")
        commits = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            parts = line.split("|", 2)
            if len(parts) == 3:
                commits.append({
                    "hash": parts[0],
                    "message": parts[1],
                    "date": parts[2],
                })
        return commits

    def _files_changed_since(self, n_commits: int = 5) -> list[str]:
        raw = self._git("diff", "--name-only", f"HEAD~{n_commits}", "HEAD")
        return [f for f in raw.splitlines() if f.strip()]

    def _run_tests_summary(self) -> str:
        """Run pytest and return a one-line summary."""
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "tests/", "-q", "--tb=no"],
                capture_output=True, text=True, timeout=120,
                cwd=str(self._repo),
            )
            for line in result.stdout.splitlines():
                if "passed" in line or "failed" in line or "error" in line:
                    return line.strip()
            return result.stdout.strip().split("\n")[-1] if result.stdout else "unknown"
        except Exception as e:
            return f"test run failed: {e}"

    # ------------------------------------------------------------------
    # Generate handoff
    # ------------------------------------------------------------------

    def generate(self, run_tests: bool = True, n_commits: int = 5) -> HandoffEntry:
        """Build a handoff from the current repo + audit state."""
        now = datetime.now(timezone.utc)
        session_id = now.strftime("%Y%m%d_%H%M%S")

        branch = self._current_branch()
        commits = self._recent_commits(n_commits)
        files = self._files_changed_since(min(n_commits, len(commits) or 1))

        # Summarise from most recent commit message
        summary = commits[0]["message"] if commits else "No recent commits"

        # Test results
        test_result = self._run_tests_summary() if run_tests else "skipped"

        # Audit snapshot
        audit_snapshot: list[dict[str, Any]] = []
        if self._audit:
            entries = self._audit.query(limit=10)
            audit_snapshot = [e.to_dict() for e in entries]

        entry = HandoffEntry(
            session_id=session_id,
            timestamp=now.strftime("%Y-%m-%d %H:%M UTC"),
            branch=branch,
            commits=commits,
            files_changed=files,
            summary=summary,
            test_result=test_result,
            audit_snapshot=audit_snapshot,
        )

        # Write markdown
        filename = f"{now.strftime('%Y-%m-%d')}_{_slug(summary)}.md"
        md_path = self._output_dir / filename
        md_path.write_text(entry.to_markdown(), encoding="utf-8")

        # Audit the handoff itself
        if self._audit:
            self._audit.record(
                agent="handoff_tracker",
                action=f"handoff_generated: {session_id}",
                severity=Severity.INFO,
                details={"file": str(md_path), "commits": len(commits)},
            )

        # Backup to Vault
        self._vault_backup(entry)

        return entry

    # ------------------------------------------------------------------
    # Vault backup / restore
    # ------------------------------------------------------------------

    def _vault_backup(self, entry: HandoffEntry) -> None:
        """Encrypt and store the handoff in the Vault."""
        if self._vault is None:
            return

        key = f"{self.VAULT_PREFIX}{entry.session_id}"
        payload = json.dumps(entry.to_dict())
        self._vault.store(
            key_name=key,
            value=payload,
            service="handoff_tracker",
            scope="read",
            rotation_days=365,
        )

        # Update the index (list of all handoff keys)
        index_raw = self._vault.retrieve(self.VAULT_INDEX_KEY) or "[]"
        try:
            index = json.loads(index_raw)
        except json.JSONDecodeError:
            index = []
        index.append({
            "session_id": entry.session_id,
            "timestamp": entry.timestamp,
            "summary": entry.summary,
            "key": key,
        })
        self._vault.store(
            key_name=self.VAULT_INDEX_KEY,
            value=json.dumps(index),
            service="handoff_tracker",
            scope="read",
            rotation_days=365,
        )

    def list_handoffs(self) -> list[dict[str, str]]:
        """Return all backed-up handoffs from the Vault."""
        if self._vault is None:
            return []
        raw = self._vault.retrieve(self.VAULT_INDEX_KEY)
        if not raw:
            return []
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return []

    def restore_handoff(self, session_id: str) -> HandoffEntry | None:
        """Decrypt and restore a handoff from the Vault."""
        if self._vault is None:
            return None
        key = f"{self.VAULT_PREFIX}{session_id}"
        raw = self._vault.retrieve(key)
        if not raw:
            return None
        data = json.loads(raw)
        return HandoffEntry(**data)


def _slug(text: str, max_len: int = 40) -> str:
    """Convert text to a filename-safe slug."""
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-")
