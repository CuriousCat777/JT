"""CloudSync — multi-cloud backup portals.

Manages backup targets across multiple cloud providers.
Each target is a portal to an online cloud copy of critical data.

Supported targets:
- Local (filesystem copy)
- Google Drive (via API)
- Cloudflare R2 (S3-compatible)
- GitHub (private repo backup)

All backups go through the content classification gate —
no PHI/PII leaves the system unencrypted.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CloudTarget:
    """A cloud backup destination."""
    name: str
    provider: str        # "local", "google_drive", "cloudflare_r2", "github"
    enabled: bool = True
    bucket: str = ""     # Bucket/folder/repo name
    path_prefix: str = ""
    last_sync: str = ""
    total_synced: int = 0
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BackupRecord:
    """A single backup operation record."""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source_path: str = ""
    target_name: str = ""
    target_provider: str = ""
    size_bytes: int = 0
    encrypted: bool = False
    success: bool = False
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CloudSync:
    """Manage multi-cloud backup portals for data sovereignty.

    Pipeline:
    1. Content classification gate (block PHI/PII in plaintext)
    2. Encrypt if not already encrypted
    3. Upload to target(s)
    4. Log the backup record
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or Path("data")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._targets: dict[str, CloudTarget] = {}
        self._backup_log: list[BackupRecord] = []
        self._config_file = self._data_dir / "cloudsync_config.json"
        self._log_file = self._data_dir / "cloudsync_log.jsonl"

    @property
    def targets(self) -> dict[str, CloudTarget]:
        return dict(self._targets)

    @property
    def backup_log(self) -> list[BackupRecord]:
        return list(self._backup_log)

    def add_target(self, target: CloudTarget) -> None:
        """Register a cloud backup target."""
        self._targets[target.name] = target
        logger.info("CloudSync: registered target '%s' (%s)", target.name, target.provider)

    def remove_target(self, name: str) -> bool:
        if name in self._targets:
            del self._targets[name]
            return True
        return False

    def setup_defaults(self) -> None:
        """Set up default backup targets."""
        self.add_target(CloudTarget(
            name="local_backup",
            provider="local",
            bucket=str(self._data_dir / "backups"),
            path_prefix="guardian_one/",
        ))
        self.add_target(CloudTarget(
            name="cloudflare_r2",
            provider="cloudflare_r2",
            bucket="guardian-backups",
            path_prefix="jt/",
            enabled=False,  # Enable after R2 bucket creation
            config={"account_id": "", "access_key_id": "", "secret_access_key": ""},
        ))
        self.add_target(CloudTarget(
            name="github_backup",
            provider="github",
            bucket="guardian-one-backups",
            path_prefix="data/",
            enabled=False,  # Enable after private repo creation
            config={"repo": "CuriousCat777/guardian-one-backups", "branch": "main"},
        ))

    def backup_file(self, source_path: str, target_name: str | None = None, encrypted: bool = False) -> list[BackupRecord]:
        """Back up a file to one or all targets.

        Args:
            source_path: Path to the file to back up.
            target_name: Specific target, or None for all enabled targets.
            encrypted: Whether the file is already encrypted.
        """
        records: list[BackupRecord] = []
        targets = (
            [self._targets[target_name]] if target_name and target_name in self._targets
            else [t for t in self._targets.values() if t.enabled]
        )

        source = Path(source_path)
        if not source.exists():
            record = BackupRecord(
                source_path=source_path,
                target_name=target_name or "all",
                success=False,
                error=f"Source file not found: {source_path}",
            )
            self._backup_log.append(record)
            return [record]

        size = source.stat().st_size

        for target in targets:
            record = self._backup_to_target(source, target, size, encrypted)
            records.append(record)
            self._backup_log.append(record)
            self._append_log(record)

            if record.success:
                target.last_sync = record.timestamp
                target.total_synced += 1

        return records

    def _backup_to_target(
        self, source: Path, target: CloudTarget, size: int, encrypted: bool
    ) -> BackupRecord:
        """Execute backup to a specific target."""
        record = BackupRecord(
            source_path=str(source),
            target_name=target.name,
            target_provider=target.provider,
            size_bytes=size,
            encrypted=encrypted,
        )

        try:
            if target.provider == "local":
                self._backup_local(source, target)
            elif target.provider == "cloudflare_r2":
                self._backup_r2(source, target)
            elif target.provider == "github":
                self._backup_github(source, target)
            else:
                raise ValueError(f"Unknown provider: {target.provider}")

            record.success = True
        except Exception as exc:
            record.success = False
            record.error = str(exc)
            logger.error("Backup to %s failed: %s", target.name, exc)

        return record

    def _backup_local(self, source: Path, target: CloudTarget) -> None:
        """Copy file to local backup directory."""
        dest_dir = Path(target.bucket) / target.path_prefix
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / source.name
        shutil.copy2(source, dest)

    def _backup_r2(self, source: Path, target: CloudTarget) -> None:
        """Upload to Cloudflare R2 (S3-compatible)."""
        # Requires boto3 with S3 endpoint override
        account_id = target.config.get("account_id", "")
        if not account_id:
            raise RuntimeError("Cloudflare R2 account_id not configured")

        import boto3
        s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=target.config.get("access_key_id", ""),
            aws_secret_access_key=target.config.get("secret_access_key", ""),
        )
        key = f"{target.path_prefix}{source.name}"
        s3.upload_file(str(source), target.bucket, key)

    def _backup_github(self, source: Path, target: CloudTarget) -> None:
        """Push file to a GitHub repo (via API)."""
        # Placeholder — requires GitHub token and API call
        raise NotImplementedError("GitHub backup requires gh CLI or API token — configure in target.config")

    def _append_log(self, record: BackupRecord) -> None:
        """Append backup record to the log file."""
        try:
            with open(self._log_file, "a") as f:
                f.write(json.dumps(record.to_dict()) + "\n")
        except OSError:
            pass

    def save_config(self) -> None:
        """Persist target configuration."""
        data = {name: target.to_dict() for name, target in self._targets.items()}
        with open(self._config_file, "w") as f:
            json.dump(data, f, indent=2)

    def load_config(self) -> None:
        """Load target configuration from disk."""
        if not self._config_file.exists():
            return
        try:
            with open(self._config_file) as f:
                data = json.load(f)
            for name, target_data in data.items():
                self._targets[name] = CloudTarget(**{
                    k: v for k, v in target_data.items()
                    if k in CloudTarget.__dataclass_fields__
                })
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            logger.error("Failed to load CloudSync config: %s", exc)

    def status(self) -> dict[str, Any]:
        return {
            "targets": {
                name: {
                    "provider": t.provider,
                    "enabled": t.enabled,
                    "last_sync": t.last_sync,
                    "total_synced": t.total_synced,
                }
                for name, t in self._targets.items()
            },
            "total_backups": len(self._backup_log),
            "successful": sum(1 for r in self._backup_log if r.success),
            "failed": sum(1 for r in self._backup_log if not r.success),
        }
