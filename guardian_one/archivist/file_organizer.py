"""FileOrganizer — auto-categorize files, clean trash, enforce taxonomy.

Watches directories for new files, classifies them by extension/content,
moves them into the standard Guardian One taxonomy, and enforces cleanup
rules for temp files, downloads, and trash.

Taxonomy:
  ~/Documents/medical/    — health records, prescriptions, lab results
  ~/Documents/financial/  — tax docs, bank statements, receipts
  ~/Documents/legal/      — contracts, agreements, legal correspondence
  ~/Documents/professional/ — CV, publications, certifications
  ~/Documents/personal/   — IDs, personal correspondence
  ~/Downloads/            — auto-clean after 30 days
  ~/Desktop/              — auto-clean after 7 days
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Extension → category mapping
EXTENSION_MAP: dict[str, str] = {
    # Financial
    ".csv": "financial",
    ".ofx": "financial",
    ".qfx": "financial",
    ".qbo": "financial",
    # Medical
    ".dcm": "medical",
    ".hl7": "medical",
    # Legal
    ".docx": "legal",
    ".doc": "legal",
    # Professional
    ".tex": "professional",
    ".bib": "professional",
    ".pptx": "professional",
    ".ppt": "professional",
    # General documents
    ".pdf": "pending_review",
    ".xlsx": "pending_review",
    ".xls": "pending_review",
    # Images
    ".jpg": "media",
    ".jpeg": "media",
    ".png": "media",
    ".gif": "media",
    ".heic": "media",
    ".webp": "media",
    # Code / tech
    ".py": "code",
    ".js": "code",
    ".ts": "code",
    ".json": "code",
    ".yaml": "code",
    ".yml": "code",
    ".sh": "code",
}

# Filename keyword → category overrides (checked before extension)
KEYWORD_MAP: dict[str, str] = {
    "tax": "financial",
    "w2": "financial",
    "w-2": "financial",
    "1099": "financial",
    "invoice": "financial",
    "receipt": "financial",
    "bank_statement": "financial",
    "statement": "financial",
    "prescription": "medical",
    "lab_result": "medical",
    "diagnosis": "medical",
    "insurance": "medical",
    "eob": "medical",
    "contract": "legal",
    "agreement": "legal",
    "lease": "legal",
    "nda": "legal",
    "resume": "professional",
    "cv": "professional",
    "cover_letter": "professional",
    "publication": "professional",
    "passport": "personal",
    "license": "personal",
    "birth_certificate": "personal",
    "social_security": "personal",
    "ssn": "personal",
}


@dataclass
class CleanupRule:
    """Rule for auto-cleaning a directory."""
    path: str
    max_age_days: int
    extensions: list[str] = field(default_factory=list)  # Empty = all files
    exclude_patterns: list[str] = field(default_factory=list)
    dry_run: bool = True  # Safety: default to dry run


@dataclass
class OrganizeResult:
    """Result of a file organization pass."""
    files_scanned: int = 0
    files_moved: int = 0
    files_skipped: int = 0
    files_cleaned: int = 0
    bytes_freed: int = 0
    errors: list[str] = field(default_factory=list)
    moves: list[dict[str, str]] = field(default_factory=list)
    cleanups: list[str] = field(default_factory=list)


class FileOrganizer:
    """Auto-categorize files and enforce cleanup rules.

    Usage:
        organizer = FileOrganizer(base_dir=Path.home() / "Documents")
        organizer.add_cleanup_rule(CleanupRule(
            path=str(Path.home() / "Downloads"),
            max_age_days=30,
        ))
        result = organizer.organize(Path.home() / "Downloads")
        result = organizer.cleanup()
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or Path.home() / "Documents"
        self._cleanup_rules: list[CleanupRule] = []
        self._category_dirs: dict[str, Path] = {
            "financial": self._base_dir / "financial",
            "medical": self._base_dir / "medical",
            "legal": self._base_dir / "legal",
            "professional": self._base_dir / "professional",
            "personal": self._base_dir / "personal",
            "media": self._base_dir / "media",
            "code": self._base_dir / "code",
            "pending_review": self._base_dir / "pending_review",
        }

    @property
    def categories(self) -> dict[str, Path]:
        return dict(self._category_dirs)

    def add_category(self, name: str, path: Path) -> None:
        self._category_dirs[name] = path

    def add_cleanup_rule(self, rule: CleanupRule) -> None:
        self._cleanup_rules.append(rule)

    def setup_default_rules(self) -> None:
        """Set up standard cleanup rules."""
        home = Path.home()
        self._cleanup_rules = [
            CleanupRule(
                path=str(home / "Downloads"),
                max_age_days=30,
                dry_run=True,
            ),
            CleanupRule(
                path=str(home / "Desktop"),
                max_age_days=7,
                exclude_patterns=["*.lnk", "*.desktop"],
                dry_run=True,
            ),
            CleanupRule(
                path=str(home / ".local" / "share" / "Trash" / "files"),
                max_age_days=14,
                dry_run=True,
            ),
        ]

    def classify(self, filename: str) -> str:
        """Classify a filename into a category.

        Checks keyword matches first, then falls back to extension.
        """
        lower = filename.lower()

        # Check keywords first
        for keyword, category in KEYWORD_MAP.items():
            if keyword in lower:
                return category

        # Fall back to extension
        ext = Path(filename).suffix.lower()
        return EXTENSION_MAP.get(ext, "pending_review")

    def organize(self, source_dir: Path, dry_run: bool = True) -> OrganizeResult:
        """Scan a directory and organize files into the taxonomy.

        Args:
            source_dir: Directory to scan.
            dry_run: If True, report what would happen without moving files.
        """
        result = OrganizeResult()

        if not source_dir.exists():
            result.errors.append(f"Source directory not found: {source_dir}")
            return result

        for entry in source_dir.iterdir():
            if entry.is_dir():
                continue
            if entry.name.startswith("."):
                continue

            result.files_scanned += 1
            category = self.classify(entry.name)
            dest_dir = self._category_dirs.get(category)

            if dest_dir is None:
                result.files_skipped += 1
                continue

            dest = dest_dir / entry.name

            # Skip if already in the right place
            if entry.parent == dest_dir:
                result.files_skipped += 1
                continue

            move_record = {
                "source": str(entry),
                "destination": str(dest),
                "category": category,
            }
            result.moves.append(move_record)

            if not dry_run:
                try:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    # Handle name collisions
                    if dest.exists():
                        stem = dest.stem
                        suffix = dest.suffix
                        counter = 1
                        while dest.exists():
                            dest = dest_dir / f"{stem}_{counter}{suffix}"
                            counter += 1
                    shutil.move(str(entry), str(dest))
                    result.files_moved += 1
                except OSError as exc:
                    result.errors.append(f"Failed to move {entry}: {exc}")
            else:
                result.files_moved += 1  # Count as "would move"

        return result

    def cleanup(self, dry_run: bool | None = None) -> OrganizeResult:
        """Run all cleanup rules to remove old files.

        Args:
            dry_run: Override per-rule dry_run setting. None = use rule setting.
        """
        result = OrganizeResult()
        now = datetime.now(timezone.utc)

        for rule in self._cleanup_rules:
            rule_dir = Path(rule.path)
            if not rule_dir.exists():
                continue

            use_dry_run = dry_run if dry_run is not None else rule.dry_run

            for entry in rule_dir.iterdir():
                if entry.is_dir():
                    continue
                if entry.name.startswith("."):
                    continue

                # Check extension filter
                if rule.extensions:
                    if entry.suffix.lower() not in rule.extensions:
                        continue

                # Check exclude patterns
                excluded = False
                for pattern in rule.exclude_patterns:
                    if entry.match(pattern):
                        excluded = True
                        break
                if excluded:
                    continue

                # Check age
                try:
                    mtime = datetime.fromtimestamp(
                        entry.stat().st_mtime, tz=timezone.utc
                    )
                except OSError:
                    continue

                age = now - mtime
                if age.days <= rule.max_age_days:
                    continue

                result.files_scanned += 1

                if not use_dry_run:
                    try:
                        size = entry.stat().st_size
                        entry.unlink()
                        result.files_cleaned += 1
                        result.bytes_freed += size
                        result.cleanups.append(str(entry))
                    except OSError as exc:
                        result.errors.append(f"Failed to delete {entry}: {exc}")
                else:
                    try:
                        result.bytes_freed += entry.stat().st_size
                    except OSError:
                        pass
                    result.files_cleaned += 1
                    result.cleanups.append(f"[dry-run] {entry}")

        return result

    def status(self) -> dict[str, Any]:
        """Get organizer status: category counts and cleanup rules."""
        category_counts: dict[str, int] = {}
        for name, path in self._category_dirs.items():
            if path.exists():
                category_counts[name] = sum(1 for f in path.iterdir() if f.is_file())
            else:
                category_counts[name] = 0

        return {
            "base_dir": str(self._base_dir),
            "categories": category_counts,
            "cleanup_rules": len(self._cleanup_rules),
        }
