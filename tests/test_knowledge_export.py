"""Tests for KnowledgeExporter — Archivist data → Open WebUI RAG documents."""

import json
from pathlib import Path

import pytest

from guardian_one.archivist.knowledge_export import KnowledgeExporter


class TestKnowledgeExporter:
    @pytest.fixture
    def exporter(self, tmp_path):
        return KnowledgeExporter(
            data_dir=tmp_path,
            output_dir=tmp_path / "knowledge",
        )

    def test_export_all_empty(self, exporter, tmp_path):
        """Export with no data files should still produce documents."""
        results = exporter.export_all()
        assert all(v is True for v in results.values())
        assert (tmp_path / "knowledge" / "guardian_system_overview.md").exists()

    def test_overview_content(self, exporter, tmp_path):
        exporter.export_all()
        content = (tmp_path / "knowledge" / "guardian_system_overview.md").read_text()
        assert "Guardian One" in content
        assert "Jeremy Paulo Salvino Tabernero" in content
        assert "Archivist" in content
        assert "VARYS" in content

    def test_accounts_with_data(self, exporter, tmp_path):
        # Create account registry
        accounts = {
            "google:Gmail": {
                "name": "Gmail",
                "provider": "google",
                "account_type": "email",
                "has_2fa": True,
                "password_strength": "strong",
                "storage_used_mb": 10000,
                "storage_quota_mb": 15000,
            },
            "github:GitHub": {
                "name": "GitHub",
                "provider": "github",
                "account_type": "developer",
                "has_2fa": True,
                "password_strength": "very_strong",
                "storage_used_mb": 0,
                "storage_quota_mb": 0,
            },
        }
        (tmp_path / "account_registry.json").write_text(json.dumps(accounts))

        exporter.export_all()
        content = (tmp_path / "knowledge" / "accounts_and_storage.md").read_text()
        assert "Gmail" in content
        assert "GitHub" in content
        assert "2FA" in content
        assert "Storage:" in content

    def test_tech_registry_with_data(self, exporter, tmp_path):
        registry = {
            "service:github": {
                "name": "github",
                "tech_type": "service",
                "first_seen": "2025-01-01T00:00:00Z",
                "interaction_count": 42,
                "reviewed": True,
            },
            "ai_model:ollama": {
                "name": "ollama",
                "tech_type": "ai_model",
                "first_seen": "2025-02-15T00:00:00Z",
                "interaction_count": 10,
                "reviewed": False,
            },
        }
        (tmp_path / "tech_registry.json").write_text(json.dumps(registry))

        exporter.export_all()
        content = (tmp_path / "knowledge" / "technology_registry.md").read_text()
        assert "github" in content
        assert "ollama" in content
        assert "Pending review" in content
        assert "42 interactions" in content

    def test_recent_activity_with_data(self, exporter, tmp_path):
        events = [
            {"timestamp": "2025-03-01T10:00:00Z", "source": "github", "action": "push", "target": "JT/main"},
            {"timestamp": "2025-03-01T11:00:00Z", "source": "gmail", "action": "email_received", "target": "inbox"},
        ]
        with open(tmp_path / "telemetry.jsonl", "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        exporter.export_all()
        content = (tmp_path / "knowledge" / "recent_activity.md").read_text()
        assert "github" in content
        assert "gmail" in content
        assert "push" in content

    def test_file_index_with_data(self, exporter, tmp_path):
        state = {
            "file_index": {
                "/docs/resume.pdf": {
                    "path": "/docs/resume.pdf",
                    "category": "professional",
                    "retention": "keep_forever",
                    "encrypted": False,
                },
                "/docs/tax_2024.pdf": {
                    "path": "/docs/tax_2024.pdf",
                    "category": "financial",
                    "retention": "keep_7_years",
                    "encrypted": True,
                },
            },
        }
        (tmp_path / "archivist_state.json").write_text(json.dumps(state))

        exporter.export_all()
        content = (tmp_path / "knowledge" / "file_index.md").read_text()
        assert "resume.pdf" in content
        assert "tax_2024.pdf" in content
        assert "Encrypted" in content
        assert "Professional" in content

    def test_output_directory_created(self, tmp_path):
        out = tmp_path / "custom" / "knowledge"
        exporter = KnowledgeExporter(data_dir=tmp_path, output_dir=out)
        exporter.export_all()
        assert out.exists()
        assert (out / "guardian_system_overview.md").exists()
