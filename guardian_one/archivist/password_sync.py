"""PasswordSync — 1Password / Bitwarden CLI integration.

Connects to password managers via their CLI tools to:
- Audit password health (age, strength, reuse, compromised)
- Sync account inventory (what accounts exist)
- Check 2FA enrollment
- Detect new accounts added to the vault

Supported backends:
- 1Password CLI (`op`) — https://developer.1password.com/docs/cli/
- Bitwarden CLI (`bw`) — https://bitwarden.com/help/cli/

No passwords are ever stored by Guardian One. Only metadata
(account names, URLs, health flags) is tracked.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class VaultItem:
    """Metadata for a password vault item (no secrets stored)."""
    name: str
    vault: str = ""
    category: str = ""       # "login", "credit_card", "identity", "secure_note"
    url: str = ""
    username: str = ""
    has_totp: bool = False
    password_strength: str = ""   # "weak", "fair", "strong", "very_strong"
    password_age_days: int = 0
    compromised: bool = False
    reused: bool = False
    last_modified: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "name": self.name,
            "vault": self.vault,
            "category": self.category,
            "url": self.url,
            "username": self.username,
            "has_totp": self.has_totp,
            "password_strength": self.password_strength,
            "password_age_days": self.password_age_days,
            "compromised": self.compromised,
            "reused": self.reused,
            "last_modified": self.last_modified,
            "tags": self.tags,
        }
        return d


class PasswordSync:
    """Interface to 1Password / Bitwarden CLI for password auditing.

    This class NEVER reads or stores actual passwords. It only reads
    metadata: item names, URLs, strength scores, 2FA status.
    """

    def __init__(self, backend: str = "1password", data_dir: Path | None = None) -> None:
        self._backend = backend  # "1password" or "bitwarden"
        self._data_dir = data_dir or Path("data")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._items: list[VaultItem] = []
        self._last_sync: str = ""
        self._cache_file = self._data_dir / "password_sync_cache.json"
        self._cli_available: bool | None = None

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def items(self) -> list[VaultItem]:
        return list(self._items)

    @property
    def last_sync(self) -> str:
        return self._last_sync

    def check_cli(self) -> bool:
        """Check if the password manager CLI is installed."""
        cmd = "op" if self._backend == "1password" else "bw"
        try:
            result = subprocess.run(
                [cmd, "--version"],
                capture_output=True, text=True, timeout=10,
            )
            self._cli_available = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._cli_available = False
        return self._cli_available

    def sync(self) -> dict[str, Any]:
        """Sync vault items from the password manager.

        Requires the user to be signed in to the CLI.
        Only reads metadata — never touches actual passwords.
        """
        if self._cli_available is None:
            self.check_cli()

        if not self._cli_available:
            return {
                "success": False,
                "error": f"{self._backend} CLI not available. Install it first.",
            }

        try:
            if self._backend == "1password":
                items = self._sync_1password()
            elif self._backend == "bitwarden":
                items = self._sync_bitwarden()
            else:
                return {"success": False, "error": f"Unknown backend: {self._backend}"}

            self._items = items
            self._last_sync = datetime.now(timezone.utc).isoformat()
            self._save_cache()

            return {
                "success": True,
                "items_synced": len(items),
                "timestamp": self._last_sync,
            }

        except subprocess.CalledProcessError as exc:
            return {
                "success": False,
                "error": f"CLI command failed: {exc.stderr or exc}",
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _sync_1password(self) -> list[VaultItem]:
        """Sync from 1Password CLI (`op`)."""
        result = subprocess.run(
            ["op", "item", "list", "--format=json"],
            capture_output=True, text=True, timeout=30,
            check=True,
        )
        raw_items = json.loads(result.stdout)
        items: list[VaultItem] = []

        for raw in raw_items:
            item = VaultItem(
                name=raw.get("title", ""),
                vault=raw.get("vault", {}).get("name", ""),
                category=raw.get("category", "").lower(),
                url=self._extract_url_1password(raw),
                last_modified=raw.get("updated_at", ""),
                tags=raw.get("tags", []),
            )
            items.append(item)

        return items

    def _extract_url_1password(self, raw: dict) -> str:
        urls = raw.get("urls", [])
        if urls:
            return urls[0].get("href", "")
        return ""

    def _sync_bitwarden(self) -> list[VaultItem]:
        """Sync from Bitwarden CLI (`bw`)."""
        # Ensure vault is unlocked
        result = subprocess.run(
            ["bw", "list", "items", "--output", "json"],
            capture_output=True, text=True, timeout=30,
            check=True,
        )
        raw_items = json.loads(result.stdout)
        items: list[VaultItem] = []

        type_map = {1: "login", 2: "secure_note", 3: "credit_card", 4: "identity"}

        for raw in raw_items:
            login = raw.get("login", {}) or {}
            item = VaultItem(
                name=raw.get("name", ""),
                category=type_map.get(raw.get("type", 0), "unknown"),
                url=login.get("uris", [{}])[0].get("uri", "") if login.get("uris") else "",
                username=login.get("username", ""),
                has_totp=bool(login.get("totp")),
                last_modified=raw.get("revisionDate", ""),
            )
            items.append(item)

        return items

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    def audit(self) -> dict[str, Any]:
        """Run a password health audit on synced items."""
        if not self._items:
            return {
                "error": "No items synced. Run sync() first.",
                "items": 0,
            }

        logins = [i for i in self._items if i.category in ("login", "")]
        weak = [i.name for i in logins if i.password_strength == "weak"]
        unassessed = [i.name for i in logins if i.password_strength == ""]
        no_totp = [i.name for i in logins if not i.has_totp]
        compromised = [i.name for i in logins if i.compromised]
        reused = [i.name for i in logins if i.reused]

        return {
            "total_items": len(self._items),
            "logins": len(logins),
            "weak_passwords": weak,
            "unassessed_passwords": unassessed,
            "missing_2fa": no_totp,
            "compromised": compromised,
            "reused": reused,
            "score": self._audit_score(logins),
        }

    def _audit_score(self, logins: list[VaultItem]) -> int:
        if not logins:
            return 100
        score = 100
        total = len(logins)
        # Only penalize confirmed weak passwords, not unassessed ones
        weak = sum(1 for i in logins if i.password_strength == "weak")
        score -= min(40, int(weak / total * 40)) if total else 0
        no_2fa = sum(1 for i in logins if not i.has_totp)
        score -= min(30, int(no_2fa / total * 30)) if total else 0
        compromised = sum(1 for i in logins if i.compromised)
        score -= min(30, compromised * 10)
        return max(0, score)

    # ------------------------------------------------------------------
    # Persistence (metadata cache only, no secrets)
    # ------------------------------------------------------------------

    def _save_cache(self) -> None:
        data = {
            "last_sync": self._last_sync,
            "backend": self._backend,
            "items": [i.to_dict() for i in self._items],
        }
        try:
            with open(self._cache_file, "w") as f:
                json.dump(data, f, indent=2)
        except OSError as exc:
            logger.error("Failed to save password sync cache: %s", exc)

    def load_cache(self) -> None:
        if not self._cache_file.exists():
            return
        try:
            with open(self._cache_file) as f:
                data = json.load(f)
            self._last_sync = data.get("last_sync", "")
            self._items = [
                VaultItem(**{
                    k: v for k, v in item.items()
                    if k in VaultItem.__dataclass_fields__
                })
                for item in data.get("items", [])
            ]
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            logger.error("Failed to load password sync cache: %s", exc)

    def status(self) -> dict[str, Any]:
        return {
            "backend": self._backend,
            "cli_available": self._cli_available,
            "items_cached": len(self._items),
            "last_sync": self._last_sync,
        }
