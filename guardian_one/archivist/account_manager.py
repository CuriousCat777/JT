"""AccountManager — unified tracker for all accounts, services, and storage.

Tracks every account Jeremy has across every service — email, cloud storage,
financial, social, developer tools, subscriptions. For each account:
- Storage usage and quotas
- Password health (age, strength, reuse, 2FA status)
- Last activity / login
- Linked services (OAuth connections)

This is the "memory" of what accounts exist and their health.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AccountRecord:
    """A tracked account/service."""
    name: str                    # e.g. "Gmail", "GitHub", "Chase Bank"
    provider: str                # e.g. "google", "github", "chase"
    account_type: str = ""       # "email", "cloud_storage", "financial", "social", "developer", "subscription", "iot"
    email: str = ""              # Login email
    username: str = ""           # Login username
    url: str = ""                # Service URL
    storage_used_mb: float = 0   # Storage used (MB)
    storage_quota_mb: float = 0  # Storage quota (MB)
    has_2fa: bool = False
    password_age_days: int = 0
    password_strength: str = ""  # "weak", "fair", "strong", "very_strong"
    password_manager: str = ""   # "1password", "bitwarden", "none"
    last_activity: str = ""
    linked_services: list[str] = field(default_factory=list)
    notes: str = ""
    active: bool = True
    created: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def storage_usage_pct(self) -> float:
        if self.storage_quota_mb <= 0:
            return 0.0
        return round(self.storage_used_mb / self.storage_quota_mb * 100, 1)


class AccountManager:
    """Unified account and storage tracker.

    Maintains a registry of all accounts across all services,
    tracks storage usage, password health, and 2FA status.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or Path("data")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._accounts: dict[str, AccountRecord] = {}
        self._registry_file = self._data_dir / "account_registry.json"

    @property
    def accounts(self) -> dict[str, AccountRecord]:
        return dict(self._accounts)

    def add(self, account: AccountRecord) -> None:
        key = f"{account.provider}:{account.name}"
        self._accounts[key] = account
        logger.info("Account registered: %s (%s)", account.name, account.provider)

    def remove(self, provider: str, name: str) -> bool:
        key = f"{provider}:{name}"
        if key in self._accounts:
            del self._accounts[key]
            return True
        return False

    def get(self, provider: str, name: str) -> AccountRecord | None:
        return self._accounts.get(f"{provider}:{name}")

    def search(
        self,
        account_type: str | None = None,
        provider: str | None = None,
        active_only: bool = True,
    ) -> list[AccountRecord]:
        results = list(self._accounts.values())
        if active_only:
            results = [a for a in results if a.active]
        if account_type:
            results = [a for a in results if a.account_type == account_type]
        if provider:
            results = [a for a in results if a.provider == provider]
        return results

    # ------------------------------------------------------------------
    # Health checks
    # ------------------------------------------------------------------

    def password_health(self) -> dict[str, Any]:
        """Audit password health across all accounts."""
        weak = [a for a in self._accounts.values() if a.password_strength in ("weak", "")]
        old = [a for a in self._accounts.values() if a.password_age_days > 90]
        no_2fa = [a for a in self._accounts.values() if not a.has_2fa and a.active]
        no_manager = [a for a in self._accounts.values() if a.password_manager in ("none", "") and a.active]

        return {
            "total_accounts": len(self._accounts),
            "active": sum(1 for a in self._accounts.values() if a.active),
            "weak_passwords": [a.name for a in weak],
            "old_passwords_90d": [a.name for a in old],
            "missing_2fa": [a.name for a in no_2fa],
            "not_in_password_manager": [a.name for a in no_manager],
            "score": self._health_score(),
        }

    def _health_score(self) -> int:
        """Calculate overall account health score (0-100)."""
        if not self._accounts:
            return 100

        active = [a for a in self._accounts.values() if a.active]
        if not active:
            return 100

        total = len(active)
        score = 100

        # Deduct for weak passwords (-5 each)
        weak = sum(1 for a in active if a.password_strength in ("weak", ""))
        score -= min(30, weak * 5)

        # Deduct for missing 2FA (-3 each)
        no_2fa = sum(1 for a in active if not a.has_2fa)
        score -= min(30, no_2fa * 3)

        # Deduct for old passwords (-2 each)
        old = sum(1 for a in active if a.password_age_days > 90)
        score -= min(20, old * 2)

        # Deduct for missing password manager (-2 each)
        no_mgr = sum(1 for a in active if a.password_manager in ("none", ""))
        score -= min(20, no_mgr * 2)

        return max(0, score)

    def storage_summary(self) -> dict[str, Any]:
        """Get storage usage across all accounts."""
        cloud_accounts = [
            a for a in self._accounts.values()
            if a.storage_quota_mb > 0 and a.active
        ]

        total_used = sum(a.storage_used_mb for a in cloud_accounts)
        total_quota = sum(a.storage_quota_mb for a in cloud_accounts)

        over_80_pct = [
            a.name for a in cloud_accounts
            if a.storage_usage_pct > 80
        ]

        return {
            "accounts_with_storage": len(cloud_accounts),
            "total_used_gb": round(total_used / 1024, 2),
            "total_quota_gb": round(total_quota / 1024, 2),
            "usage_pct": round(total_used / total_quota * 100, 1) if total_quota > 0 else 0,
            "over_80_pct": over_80_pct,
            "per_account": [
                {
                    "name": a.name,
                    "provider": a.provider,
                    "used_gb": round(a.storage_used_mb / 1024, 2),
                    "quota_gb": round(a.storage_quota_mb / 1024, 2),
                    "usage_pct": a.storage_usage_pct,
                }
                for a in cloud_accounts
            ],
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        data = {key: record.to_dict() for key, record in self._accounts.items()}
        try:
            with open(self._registry_file, "w") as f:
                json.dump(data, f, indent=2)
        except OSError as exc:
            logger.error("Failed to save account registry: %s", exc)

    def load(self) -> None:
        if not self._registry_file.exists():
            return
        try:
            with open(self._registry_file) as f:
                data = json.load(f)
            for key, record_data in data.items():
                self._accounts[key] = AccountRecord(**{
                    k: v for k, v in record_data.items()
                    if k in AccountRecord.__dataclass_fields__
                })
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            logger.error("Failed to load account registry: %s", exc)

    def status(self) -> dict[str, Any]:
        return {
            "total_accounts": len(self._accounts),
            "active": sum(1 for a in self._accounts.values() if a.active),
            "by_type": self._count_by_type(),
            "health_score": self._health_score(),
        }

    def _count_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for a in self._accounts.values():
            counts[a.account_type] = counts.get(a.account_type, 0) + 1
        return counts
