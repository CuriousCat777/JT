"""Tests for The Archivist — Developer Coach Agent."""

from __future__ import annotations

import tempfile
from pathlib import Path

from guardian_one.core.audit import AuditLog
from guardian_one.core.base_agent import AgentReport, AgentStatus
from guardian_one.core.config import AgentConfig
from guardian_one.core.db_schema import (
    CodeSnippet,
    LearningPath,
    ProjectRecord,
    ProjectStatus,
    RecommendationTier,
    SkillLevel,
    TechCategory,
    TechEntry,
    SQL_SCHEMA,
    NEO4J_SCHEMA,
    DGRAPH_SCHEMA,
)
from guardian_one.agents.dev_coach import DevCoach


def _make_audit() -> AuditLog:
    temp_dir = tempfile.TemporaryDirectory()
    audit = AuditLog(log_dir=Path(temp_dir.name))
    audit._temp_dir = temp_dir
    return audit


def _make_coach() -> DevCoach:
    cfg = AgentConfig(name="dev_coach")
    coach = DevCoach(config=cfg, audit=_make_audit())
    coach.initialize()
    return coach


# ------------------------------------------------------------------
# Lifecycle
# ------------------------------------------------------------------

class TestLifecycle:
    def test_init(self):
        cfg = AgentConfig(name="dev_coach")
        coach = DevCoach(config=cfg, audit=_make_audit())
        assert coach.name == "dev_coach"
        assert coach.status == AgentStatus.IDLE

    def test_initialize(self):
        coach = _make_coach()
        assert coach.status == AgentStatus.IDLE
        # Should have seeded tech registry
        assert len(coach._tech_registry) > 0
        # Should have seeded wisdom
        assert len(coach._fireship_wisdom) > 0
        # Should have discovered system components
        assert len(coach._system_components) > 0

    def test_run(self):
        coach = _make_coach()
        report = coach.run()
        assert isinstance(report, AgentReport)
        assert report.agent_name == "dev_coach"
        assert report.status == AgentStatus.IDLE.value

    def test_report(self):
        coach = _make_coach()
        report = coach.report()
        assert isinstance(report, AgentReport)
        assert report.agent_name == "dev_coach"
        assert "tech" in report.data or "technologies" in report.data or len(report.data) > 0

    def test_shutdown(self):
        coach = _make_coach()
        coach.shutdown()
        assert coach.status == AgentStatus.IDLE


# ------------------------------------------------------------------
# Tech Registry
# ------------------------------------------------------------------

class TestTechRegistry:
    def test_seeded_tech_entries(self):
        coach = _make_coach()
        assert "python" in coach._tech_registry
        assert "typescript" in coach._tech_registry
        assert "git" in coach._tech_registry

    def test_s_tier_entries(self):
        coach = _make_coach()
        tier_list = coach.get_tier_list()
        s_tier = tier_list.get("S", [])
        s_names = [t["id"] for t in s_tier]
        assert "python" in s_names
        assert "typescript" in s_names

    def test_add_tech(self):
        coach = _make_coach()
        entry = TechEntry(
            id="htmx",
            name="HTMX",
            category=TechCategory.LIBRARY,
            tier=RecommendationTier.A_TIER,
            description="HTML over the wire",
        )
        coach.add_tech(entry)
        assert "htmx" in coach._tech_registry

    def test_search_tech(self):
        coach = _make_coach()
        results = coach.search_tech("python")
        assert len(results) >= 1
        assert any(r.id == "python" for r in results)

    def test_search_tech_by_category(self):
        coach = _make_coach()
        results = coach.search_tech(category=TechCategory.LANGUAGE)
        assert len(results) >= 1
        assert all(r.category == TechCategory.LANGUAGE for r in results)

    def test_rate_tech(self):
        coach = _make_coach()
        coach.rate_tech("python", RecommendationTier.S_TIER, "Still the GOAT")
        entry = coach._tech_registry["python"]
        assert entry.tier == RecommendationTier.S_TIER
        assert "GOAT" in entry.notes

    def test_get_tier_list(self):
        coach = _make_coach()
        tiers = coach.get_tier_list()
        assert isinstance(tiers, dict)
        assert "S" in tiers
        assert "A" in tiers


# ------------------------------------------------------------------
# Code Snippets
# ------------------------------------------------------------------

class TestSnippets:
    def test_add_snippet(self):
        coach = _make_coach()
        snippet = CodeSnippet(
            id="async_fetch",
            title="Async Fetch Pattern",
            language="typescript",
            code="const data = await fetch(url).then(r => r.json());",
            use_this="Use async/await with fetch",
            not_that="Don't use XMLHttpRequest in 2026",
        )
        coach.add_snippet(snippet)
        assert "async_fetch" in coach._snippets

    def test_search_snippets(self):
        coach = _make_coach()
        snippet = CodeSnippet(
            id="py_list_comp",
            title="List Comprehension",
            language="python",
            code="[x for x in items if x > 0]",
        )
        coach.add_snippet(snippet)
        results = coach.search_snippets("list", language="python")
        assert len(results) >= 1


# ------------------------------------------------------------------
# Projects
# ------------------------------------------------------------------

class TestProjects:
    def test_seeded_projects(self):
        coach = _make_coach()
        assert len(coach._projects) > 0

    def test_add_project(self):
        coach = _make_coach()
        project = ProjectRecord(
            id="new_app",
            name="New App",
            status=ProjectStatus.PLANNING,
            tech_stack=["typescript", "nextjs"],
        )
        coach.add_project(project)
        assert "new_app" in coach._projects

    def test_get_project(self):
        coach = _make_coach()
        project = coach.get_project("guardian_one")
        assert project is not None
        assert project.id == "guardian_one"
        assert project.name == "guardian_one"
        assert project.status == ProjectStatus.ACTIVE


# ------------------------------------------------------------------
# Stack Recommendations
# ------------------------------------------------------------------

class TestRecommendations:
    def test_recommend_saas(self):
        coach = _make_coach()
        rec = coach.recommend_stack("saas")
        assert "stack" in rec
        assert len(rec["stack"]) > 0

    def test_recommend_api(self):
        coach = _make_coach()
        rec = coach.recommend_stack("api")
        assert "stack" in rec

    def test_recommend_static(self):
        coach = _make_coach()
        rec = coach.recommend_stack("static_site")
        assert "stack" in rec

    def test_recommend_ai_app(self):
        coach = _make_coach()
        rec = coach.recommend_stack("ai_app")
        assert "stack" in rec

    def test_recommend_unknown(self):
        coach = _make_coach()
        rec = coach.recommend_stack("quantum_blockchain")
        assert "summary" in rec


# ------------------------------------------------------------------
# Web Audit
# ------------------------------------------------------------------

class TestWebAudit:
    def test_web_audit(self):
        coach = _make_coach()
        audit = coach.web_audit("jtmdai.com")
        assert isinstance(audit, dict)
        assert "performance" in audit
        assert "https" in audit
        assert "headers" in audit

    def test_web_audit_unknown_domain(self):
        coach = _make_coach()
        audit = coach.web_audit("example.com")
        assert isinstance(audit, dict)


# ------------------------------------------------------------------
# Fireship Wisdom
# ------------------------------------------------------------------

class TestWisdom:
    def test_get_wisdom(self):
        coach = _make_coach()
        tip = coach.get_wisdom()
        assert isinstance(tip, str)
        assert len(tip) > 10

    def test_wisdom_variety(self):
        coach = _make_coach()
        tips = {coach.get_wisdom() for _ in range(20)}
        # Should get at least a few different tips
        assert len(tips) >= 3


# ------------------------------------------------------------------
# System Discovery
# ------------------------------------------------------------------

class TestSystemDiscovery:
    def test_system_components_discovered(self):
        coach = _make_coach()
        inventory = coach.get_system_inventory()
        assert isinstance(inventory, list)
        assert len(inventory) > 0

    def test_has_os_component(self):
        coach = _make_coach()
        types = [c["type"] for c in coach.get_system_inventory()]
        assert "os" in types or "cpu" in types


# ------------------------------------------------------------------
# Learning Paths
# ------------------------------------------------------------------

class TestLearningPaths:
    def test_add_learning_path(self):
        coach = _make_coach()
        path = LearningPath(
            id="fullstack_2026",
            title="Full-Stack Developer 2026",
            tech_ids=["typescript", "nextjs", "postgresql"],
            steps=["Learn TypeScript", "Build with Next.js", "Master PostgreSQL"],
            estimated_hours=120,
            priority=1,
        )
        coach.add_learning_path(path)
        assert "fullstack_2026" in coach._learning_paths

    def test_skill_assessment(self):
        coach = _make_coach()
        assessment = coach.skill_assessment()
        assert isinstance(assessment, dict)


# ------------------------------------------------------------------
# Database Schemas
# ------------------------------------------------------------------

class TestSchemas:
    def test_sql_schema_exists(self):
        assert isinstance(SQL_SCHEMA, str)
        assert "CREATE TABLE" in SQL_SCHEMA
        assert "tech_entries" in SQL_SCHEMA
        assert "FOREIGN" in SQL_SCHEMA or "REFERENCES" in SQL_SCHEMA

    def test_neo4j_schema_exists(self):
        assert isinstance(NEO4J_SCHEMA, str)
        assert "Technology" in NEO4J_SCHEMA
        assert "DEPENDS_ON" in NEO4J_SCHEMA

    def test_dgraph_schema_exists(self):
        assert isinstance(DGRAPH_SCHEMA, str)
        assert "Technology" in DGRAPH_SCHEMA
        assert "techId" in DGRAPH_SCHEMA

    def test_coach_returns_schemas(self):
        coach = _make_coach()
        assert isinstance(coach.get_sql_schema(), str)
        assert isinstance(coach.get_neo4j_schema(), str)
        assert isinstance(coach.get_dgraph_schema(), str)


# ------------------------------------------------------------------
# Code Review Tips
# ------------------------------------------------------------------

class TestCodeReview:
    def test_code_review_tips_python(self):
        coach = _make_coach()
        tips = coach.code_review_tips("python")
        assert isinstance(tips, list)
        assert len(tips) > 0

    def test_code_review_tips_typescript(self):
        coach = _make_coach()
        tips = coach.code_review_tips("typescript")
        assert isinstance(tips, list)
        assert len(tips) > 0

    def test_code_review_tips_unknown(self):
        coach = _make_coach()
        tips = coach.code_review_tips("brainfuck")
        assert isinstance(tips, list)
