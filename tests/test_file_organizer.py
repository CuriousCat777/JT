"""Tests for FileOrganizer — auto-categorize, cleanup, taxonomy enforcement."""

from pathlib import Path
from datetime import datetime, timezone, timedelta

import pytest

from guardian_one.archivist.file_organizer import (
    FileOrganizer, CleanupRule, EXTENSION_MAP, KEYWORD_MAP,
)


class TestClassification:
    @pytest.fixture
    def organizer(self, tmp_path):
        return FileOrganizer(base_dir=tmp_path / "docs")

    def test_keyword_override(self, organizer):
        assert organizer.classify("tax_return_2025.pdf") == "financial"
        assert organizer.classify("prescription_jan.pdf") == "medical"
        assert organizer.classify("nda_acme_corp.pdf") == "legal"
        assert organizer.classify("resume_latest.pdf") == "professional"

    def test_extension_fallback(self, organizer):
        assert organizer.classify("photo.jpg") == "media"
        assert organizer.classify("script.py") == "code"
        assert organizer.classify("data.csv") == "financial"

    def test_unknown_extension(self, organizer):
        assert organizer.classify("mystery.xyz") == "pending_review"

    def test_case_insensitive(self, organizer):
        assert organizer.classify("TAX_RETURN.PDF") == "financial"
        assert organizer.classify("Resume.PDF") == "professional"


class TestOrganize:
    @pytest.fixture
    def organizer(self, tmp_path):
        org = FileOrganizer(base_dir=tmp_path / "docs")
        return org

    def test_dry_run(self, organizer, tmp_path):
        source = tmp_path / "downloads"
        source.mkdir()
        (source / "tax_return.pdf").write_text("fake pdf")
        (source / "photo.jpg").write_text("fake jpg")

        result = organizer.organize(source, dry_run=True)
        assert result.files_scanned == 2
        assert result.files_moved == 2
        assert len(result.moves) == 2
        # Files should NOT actually be moved
        assert (source / "tax_return.pdf").exists()

    def test_actual_move(self, organizer, tmp_path):
        source = tmp_path / "downloads"
        source.mkdir()
        (source / "tax_return.pdf").write_text("fake pdf")

        result = organizer.organize(source, dry_run=False)
        assert result.files_moved == 1
        # File should be moved
        assert not (source / "tax_return.pdf").exists()
        dest = tmp_path / "docs" / "financial" / "tax_return.pdf"
        assert dest.exists()

    def test_collision_handling(self, organizer, tmp_path):
        source = tmp_path / "downloads"
        source.mkdir()
        dest_dir = tmp_path / "docs" / "financial"
        dest_dir.mkdir(parents=True)

        # Pre-existing file at destination
        (dest_dir / "tax_return.pdf").write_text("old")
        (source / "tax_return.pdf").write_text("new")

        result = organizer.organize(source, dry_run=False)
        assert result.files_moved == 1
        # Both files should exist (renamed)
        assert (dest_dir / "tax_return.pdf").exists()
        assert (dest_dir / "tax_return_1.pdf").exists()

    def test_skip_dotfiles(self, organizer, tmp_path):
        source = tmp_path / "downloads"
        source.mkdir()
        (source / ".hidden_file").write_text("hidden")
        (source / "visible.pdf").write_text("visible")

        result = organizer.organize(source, dry_run=True)
        assert result.files_scanned == 1

    def test_missing_source_dir(self, organizer, tmp_path):
        result = organizer.organize(tmp_path / "nonexistent")
        assert len(result.errors) == 1

    def test_skip_directories(self, organizer, tmp_path):
        source = tmp_path / "downloads"
        source.mkdir()
        (source / "subdir").mkdir()
        (source / "file.pdf").write_text("data")

        result = organizer.organize(source, dry_run=True)
        assert result.files_scanned == 1


class TestCleanup:
    def test_cleanup_old_files(self, tmp_path):
        organizer = FileOrganizer(base_dir=tmp_path / "docs")
        target = tmp_path / "cleanup"
        target.mkdir()

        # Create an "old" file
        old_file = target / "old_download.zip"
        old_file.write_text("old data")
        import os
        old_time = (datetime.now(timezone.utc) - timedelta(days=40)).timestamp()
        os.utime(old_file, (old_time, old_time))

        # Create a "new" file
        (target / "new_file.txt").write_text("fresh")

        organizer.add_cleanup_rule(CleanupRule(
            path=str(target),
            max_age_days=30,
            dry_run=True,
        ))

        result = organizer.cleanup()
        assert result.files_cleaned == 1
        assert "old_download.zip" in result.cleanups[0]
        # Dry run: file should still exist
        assert old_file.exists()

    def test_cleanup_actual_delete(self, tmp_path):
        organizer = FileOrganizer(base_dir=tmp_path / "docs")
        target = tmp_path / "trash"
        target.mkdir()

        old_file = target / "garbage.tmp"
        old_file.write_text("trash")
        import os
        old_time = (datetime.now(timezone.utc) - timedelta(days=20)).timestamp()
        os.utime(old_file, (old_time, old_time))

        organizer.add_cleanup_rule(CleanupRule(
            path=str(target),
            max_age_days=14,
            dry_run=False,
        ))

        result = organizer.cleanup()
        assert result.files_cleaned == 1
        assert not old_file.exists()

    def test_cleanup_respects_exclude(self, tmp_path):
        organizer = FileOrganizer(base_dir=tmp_path / "docs")
        target = tmp_path / "desktop"
        target.mkdir()

        old_file = target / "shortcut.lnk"
        old_file.write_text("link")
        import os
        old_time = (datetime.now(timezone.utc) - timedelta(days=20)).timestamp()
        os.utime(old_file, (old_time, old_time))

        organizer.add_cleanup_rule(CleanupRule(
            path=str(target),
            max_age_days=7,
            exclude_patterns=["*.lnk"],
            dry_run=True,
        ))

        result = organizer.cleanup()
        assert result.files_cleaned == 0


class TestStatus:
    def test_status_empty(self, tmp_path):
        organizer = FileOrganizer(base_dir=tmp_path / "docs")
        status = organizer.status()
        assert "categories" in status
        assert status["cleanup_rules"] == 0
