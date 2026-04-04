"""DevCoach — The Archivist Developer Coach Agent.

The Archivist is your Developer Yoda. Inspired by Fireship's
high-intensity, no-BS approach to software engineering.

Personality: Fast. Witty. Opinionated. Ships code, not excuses.
Tone: Jeff Delaney meets Master Yoda — concise wisdom, spicy takes,
      practical advice. "In 100 seconds or less."

Responsibilities:
- Track and rate every technology in Jeremy's stack (S-F tier list)
- Maintain a "Code This Not That" pattern vault
- Web development architecture advisory
- System component discovery and inventory
- Learning path management and skill tracking
- Project tech stack analysis and recommendations
- Performance and security best practice enforcement
- Developer productivity analytics

Advisory Role:
  Sits alongside Varys (security/intel) as a strategic advisor.
  Varys watches the network. The Archivist watches the code.
"""

from __future__ import annotations

import os
import platform
import random
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any

from guardian_one.core.audit import AuditLog
from guardian_one.core.base_agent import AgentReport, AgentStatus, BaseAgent
from guardian_one.core.config import AgentConfig
from guardian_one.core.db_schema import (
    DGRAPH_SCHEMA,
    NEO4J_SCHEMA,
    SQL_SCHEMA,
    CodeSnippet,
    LearningPath,
    ProjectRecord,
    ProjectStatus,
    RecommendationTier,
    SkillLevel,
    SystemComponent,
    TechCategory,
    TechEntry,
    DevSession,
)


class DevCoach(BaseAgent):
    """The Archivist — Developer Coach for Guardian One.

    Fireship-inspired, opinionated, practical developer advisory agent.
    Tracks tech, rates frameworks, discovers systems, and drops wisdom.
    """

    def __init__(self, config: AgentConfig, audit: AuditLog) -> None:
        super().__init__(config, audit)
        self._tech_registry: dict[str, TechEntry] = {}
        self._snippets: dict[str, CodeSnippet] = {}
        self._projects: dict[str, ProjectRecord] = {}
        self._learning_paths: dict[str, LearningPath] = {}
        self._system_components: dict[str, SystemComponent] = {}
        self._dev_sessions: list[DevSession] = []
        self._recommendations: list[dict[str, Any]] = []
        self._fireship_wisdom: list[str] = []

    def _custom_flag_enabled(self, flag_name: str, default: bool = True) -> bool:
        """Return a boolean feature flag from config.custom, falling back safely."""
        custom = getattr(self.config, "custom", None)
        if not isinstance(custom, dict):
            return default
        value = custom.get(flag_name, default)
        return value if isinstance(value, bool) else default

    def initialize(self) -> None:
        self._set_status(AgentStatus.IDLE)
        tier_list_enabled = self._custom_flag_enabled("tier_list_enabled", default=True)
        system_discovery_enabled = self._custom_flag_enabled("system_discovery", default=True)

        if tier_list_enabled:
            self._seed_tech_registry()
        self._seed_fireship_wisdom()
        if system_discovery_enabled:
            self._discover_system()
        self._seed_projects()
        self.log("initialized", details={
            "tier_list_enabled": tier_list_enabled,
            "system_discovery_enabled": system_discovery_enabled,
            "tech_entries": len(self._tech_registry),
            "wisdom_tips": len(self._fireship_wisdom),
            "system_components": len(self._system_components),
            "projects": len(self._projects),
        })

    # ------------------------------------------------------------------
    # Seed data
    # ------------------------------------------------------------------

    def _seed_tech_registry(self) -> None:
        """Populate with Fireship's opinionated tier list."""
        techs = [
            # S-Tier — ship it yesterday
            TechEntry(id="python", name="Python", category=TechCategory.LANGUAGE,
                      tier=RecommendationTier.S_TIER, skill_level=SkillLevel.ADVANCED,
                      notes="The Toyota Camry of programming. Not the fastest but it gets you everywhere."),
            TechEntry(id="typescript", name="TypeScript", category=TechCategory.LANGUAGE,
                      tier=RecommendationTier.S_TIER, skill_level=SkillLevel.INTERMEDIATE,
                      notes="JavaScript that went to college. You cannot build production code without it."),
            TechEntry(id="git", name="Git", category=TechCategory.TOOL,
                      tier=RecommendationTier.S_TIER, skill_level=SkillLevel.ADVANCED,
                      notes="If you're not using git you're not a developer, you're a gambler."),
            TechEntry(id="linux", name="Linux", category=TechCategory.PLATFORM,
                      tier=RecommendationTier.S_TIER, skill_level=SkillLevel.INTERMEDIATE,
                      notes="Every server you've ever used runs this. Learn it or cry."),
            TechEntry(id="docker", name="Docker", category=TechCategory.INFRASTRUCTURE,
                      tier=RecommendationTier.S_TIER, skill_level=SkillLevel.INTERMEDIATE,
                      notes="Works on my machine? Ship the damn machine."),
            TechEntry(id="postgresql", name="PostgreSQL", category=TechCategory.DATABASE,
                      tier=RecommendationTier.S_TIER, skill_level=SkillLevel.INTERMEDIATE,
                      notes="The database that does everything and does it well. ACID or go home."),
            TechEntry(id="vscode", name="VS Code", category=TechCategory.TOOL,
                      tier=RecommendationTier.S_TIER, skill_level=SkillLevel.ADVANCED,
                      notes="The text editor that ate the IDE market for breakfast."),
            # A-Tier — solid choice
            TechEntry(id="nextjs", name="Next.js", category=TechCategory.FRAMEWORK,
                      tier=RecommendationTier.A_TIER, skill_level=SkillLevel.INTERMEDIATE,
                      notes="React's responsible older sibling. SSR, SSG, API routes — it just works."),
            TechEntry(id="sveltekit", name="SvelteKit", category=TechCategory.FRAMEWORK,
                      tier=RecommendationTier.A_TIER, skill_level=SkillLevel.BEGINNER,
                      notes="The framework that compiled away the framework. Fewer KB, more joy."),
            TechEntry(id="tailwind", name="Tailwind CSS", category=TechCategory.LIBRARY,
                      tier=RecommendationTier.A_TIER, skill_level=SkillLevel.INTERMEDIATE,
                      notes="Inline styles that somehow don't suck. Fight me."),
            TechEntry(id="fastapi", name="FastAPI", category=TechCategory.FRAMEWORK,
                      tier=RecommendationTier.A_TIER, skill_level=SkillLevel.INTERMEDIATE,
                      notes="Flask grew up, learned type hints, and got a swagger UI."),
            TechEntry(id="rust", name="Rust", category=TechCategory.LANGUAGE,
                      tier=RecommendationTier.A_TIER, skill_level=SkillLevel.BEGINNER,
                      notes="C++ that went to therapy. Memory safety without garbage collection."),
            TechEntry(id="golang", name="Go", category=TechCategory.LANGUAGE,
                      tier=RecommendationTier.A_TIER, skill_level=SkillLevel.BEGINNER,
                      notes="Concurrency in 100 seconds. Google's gift to backend developers."),
            TechEntry(id="redis", name="Redis", category=TechCategory.DATABASE,
                      tier=RecommendationTier.A_TIER, skill_level=SkillLevel.INTERMEDIATE,
                      notes="A cache so fast it makes your database feel like a floppy disk."),
            TechEntry(id="neo4j", name="Neo4j", category=TechCategory.DATABASE,
                      tier=RecommendationTier.A_TIER, skill_level=SkillLevel.BEGINNER,
                      notes="When your data has relationships more complex than a soap opera."),
            TechEntry(id="react", name="React", category=TechCategory.LIBRARY,
                      tier=RecommendationTier.A_TIER, skill_level=SkillLevel.INTERMEDIATE,
                      notes="The library that became an ecosystem. Love it or hate it, you'll use it."),
            TechEntry(id="nodejs", name="Node.js", category=TechCategory.RUNTIME,
                      tier=RecommendationTier.A_TIER, skill_level=SkillLevel.INTERMEDIATE,
                      notes="JavaScript on the server. The prophecy was fulfilled."),
            TechEntry(id="sqlite", name="SQLite", category=TechCategory.DATABASE,
                      tier=RecommendationTier.A_TIER, skill_level=SkillLevel.INTERMEDIATE,
                      notes="A database in a single file. 35% of all software on earth uses it."),
            TechEntry(id="htmx", name="HTMX", category=TechCategory.LIBRARY,
                      tier=RecommendationTier.A_TIER, skill_level=SkillLevel.BEGINNER,
                      notes="What happens when someone reads the HTML spec and actually follows it."),
            # B-Tier — good but situational
            TechEntry(id="angular", name="Angular", category=TechCategory.FRAMEWORK,
                      tier=RecommendationTier.B_TIER, skill_level=SkillLevel.BEGINNER,
                      notes="Enterprise React. More boilerplate, more structure, more opinions."),
            TechEntry(id="vuejs", name="Vue.js", category=TechCategory.FRAMEWORK,
                      tier=RecommendationTier.B_TIER, skill_level=SkillLevel.BEGINNER,
                      notes="The approachable framework. Like React but with better docs."),
            TechEntry(id="django", name="Django", category=TechCategory.FRAMEWORK,
                      tier=RecommendationTier.B_TIER, skill_level=SkillLevel.INTERMEDIATE,
                      notes="Python's batteries-included web framework. Admin panel for free."),
            TechEntry(id="flask", name="Flask", category=TechCategory.FRAMEWORK,
                      tier=RecommendationTier.B_TIER, skill_level=SkillLevel.INTERMEDIATE,
                      notes="Microframework. When Django is too much but raw WSGI is too little."),
            TechEntry(id="mongodb", name="MongoDB", category=TechCategory.DATABASE,
                      tier=RecommendationTier.B_TIER, skill_level=SkillLevel.BEGINNER,
                      notes="The database for when your schema changes more than your socks."),
            TechEntry(id="kubernetes", name="Kubernetes", category=TechCategory.INFRASTRUCTURE,
                      tier=RecommendationTier.B_TIER, skill_level=SkillLevel.NOVICE,
                      notes="Docker's final boss. Necessary evil at scale."),
            # C-Tier — legacy or niche
            TechEntry(id="jquery", name="jQuery", category=TechCategory.LIBRARY,
                      tier=RecommendationTier.C_TIER, skill_level=SkillLevel.INTERMEDIATE,
                      notes="It's 2026. Let it rest in peace."),
            TechEntry(id="php", name="PHP", category=TechCategory.LANGUAGE,
                      tier=RecommendationTier.C_TIER, skill_level=SkillLevel.BEGINNER,
                      notes="Laravel made it bearable. Raw PHP is a war crime."),
            TechEntry(id="java", name="Java", category=TechCategory.LANGUAGE,
                      tier=RecommendationTier.C_TIER, skill_level=SkillLevel.BEGINNER,
                      notes="Still runs 3 billion devices. Also still verbose as a legal contract."),
        ]
        for t in techs:
            self._tech_registry[t.id] = t

    def _seed_fireship_wisdom(self) -> None:
        """Load curated developer tips in Jeff Delaney's voice."""
        self._fireship_wisdom = [
            "Every line of code you write is a liability. The best code is the code you never wrote.",
            "You don't need microservices. You need a monolith that's not garbage.",
            "Stop learning frameworks. Start learning patterns. Frameworks die, patterns don't.",
            "If your build takes longer than your coffee break, something is very wrong.",
            "TypeScript isn't optional. It's a requirement for code other humans can understand.",
            "The best framework is the one you actually ship with.",
            "Docker isn't complicated. Your deployment was already complicated — Docker made it visible.",
            "GraphQL is great until you realize you've reinvented SQL but worse.",
            "Ship first. Optimize later. Premature optimization is the root of all evil.",
            "Tests are documentation that actually stays up to date.",
            "If your PR is over 500 lines, it's not a PR, it's a hostage situation.",
            "Serverless means someone else's server with someone else's bill.",
            "AI won't replace developers. Developers who use AI will replace developers who don't.",
            "Your users don't care what framework you used. They care if it loads in under 3 seconds.",
            "Tailwind is just inline styles. It's also the best CSS workflow ever invented. Both true.",
            "The 10x developer isn't who writes 10x more code. They delete 10x more.",
            "Monorepos: because one node_modules folder wasn't enough.",
            "HTMX is what happens when someone reads the HTML spec and actually follows it.",
            "WebAssembly is the future. It's been the future for 8 years. Any day now.",
            "Your tech stack doesn't matter if your product doesn't solve a problem.",
            "Postgres can do 90% of what you're running Redis, Elasticsearch, and MongoDB for.",
            "Rust is C++ that went to therapy.",
            "The best database is the one your team can operate at 3 AM.",
            "SSR, SSG, ISR, PPR — just pick one and ship it.",
            "Every developer should read their own error messages before asking ChatGPT.",
            "You don't need a design system. You need consistency. Those are different things.",
            "The cloud is just someone else's computer. Make sure you trust them.",
            "Code reviews aren't about catching bugs. They're about spreading knowledge.",
            "If you can't explain your architecture in one diagram, it's too complex.",
            "npm install is-odd has 500k weekly downloads. This is why we can't have nice things.",
            "The best security is the code you didn't deploy to production.",
            "git push --force is the developer equivalent of 'hold my beer'.",
            "A senior developer is just a junior developer who has mass-produced more bugs.",
        ]

    def _discover_system(self) -> None:
        """Detect hardware and software on the current machine."""
        # OS
        self._system_components["os"] = SystemComponent(
            id="os", name=f"{platform.system()} {platform.release()}",
            component_type="os", hostname=platform.node(),
            specs={"platform": platform.platform(), "arch": platform.machine()},
            status="online",
        )
        # CPU
        cpu_count = os.cpu_count() or 0
        self._system_components["cpu"] = SystemComponent(
            id="cpu", name=platform.processor() or "Unknown CPU",
            component_type="cpu", specs={"cores": cpu_count},
            status="online",
        )
        # RAM
        ram_gb = self._detect_ram()
        if ram_gb:
            self._system_components["ram"] = SystemComponent(
                id="ram", name=f"{ram_gb:.1f} GB RAM",
                component_type="ram", specs={"total_gb": ram_gb},
                status="online",
            )
        # Disk
        try:
            usage = shutil.disk_usage("/")
            total_gb = usage.total / (1024 ** 3)
            free_gb = usage.free / (1024 ** 3)
            self._system_components["disk"] = SystemComponent(
                id="disk", name=f"{total_gb:.0f} GB Disk",
                component_type="disk",
                specs={"total_gb": round(total_gb, 1), "free_gb": round(free_gb, 1),
                       "used_pct": round((usage.used / usage.total) * 100, 1)},
                status="online",
            )
        except OSError:
            pass
        # GPU
        gpu_name = self._detect_gpu()
        if gpu_name:
            self._system_components["gpu"] = SystemComponent(
                id="gpu", name=gpu_name, component_type="gpu",
                specs={}, status="online",
            )
        # Python
        self._system_components["python"] = SystemComponent(
            id="python", name=f"Python {platform.python_version()}",
            component_type="runtime", specs={"version": platform.python_version()},
            status="online",
        )
        # Dev tools detection
        for tool, cmd in [("git", "git --version"), ("docker", "docker --version"),
                          ("node", "node --version"), ("npm", "npm --version")]:
            version = self._run_quiet(cmd)
            if version:
                self._system_components[tool] = SystemComponent(
                    id=tool, name=f"{tool} ({version.strip()})",
                    component_type="tool", specs={"version": version.strip()},
                    status="online",
                )

    def _detect_ram(self) -> float | None:
        """Detect total RAM in GB."""
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        kb = int(line.split()[1])
                        return kb / (1024 ** 2)
        except (OSError, ValueError):
            pass
        return None

    def _detect_gpu(self) -> str | None:
        """Try to detect GPU via nvidia-smi."""
        result = self._run_quiet(
            "nvidia-smi --query-gpu=name --format=csv,noheader,nounits",
            executable="nvidia-smi",
        )
        if result:
            return result.strip().split("\n")[0]
        return None

    @staticmethod
    def _run_quiet(cmd: str, executable: str | None = None, timeout: float = 1.0) -> str | None:
        """Run a command quietly, return stdout or None."""
        parts = cmd.split()
        if not parts:
            return None

        tool = executable or parts[0]
        if shutil.which(tool) is None:
            return None

        try:
            r = subprocess.run(parts, capture_output=True, text=True, timeout=timeout)
            return r.stdout.strip() if r.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None

    def _seed_projects(self) -> None:
        """Register known Guardian One projects."""
        self._projects["guardian_one"] = ProjectRecord(
            id="guardian_one", name="Guardian One",
            description="Multi-agent AI orchestration platform for personal life management",
            status=ProjectStatus.ACTIVE,
            tech_stack=["python", "git", "sqlite"],
            repo_url="https://github.com/CuriousCat777/jt",
            architecture="multi_agent", deploy_target="local",
        )
        self._projects["drjeremytabernero_org"] = ProjectRecord(
            id="drjeremytabernero_org", name="drjeremytabernero.org",
            description="Personal/professional site — CV, publications",
            status=ProjectStatus.PAUSED,
            tech_stack=["html", "css", "javascript"],
            domain="drjeremytabernero.org", deploy_target="cloud_vps",
        )
        self._projects["jtmdai_com"] = ProjectRecord(
            id="jtmdai_com", name="jtmdai.com",
            description="JTMD AI — AI solutions, services, case studies",
            status=ProjectStatus.ACTIVE,
            tech_stack=["html", "css", "javascript"],
            domain="jtmdai.com", deploy_target="cloud_vps",
        )

    # ------------------------------------------------------------------
    # Public API — Tech Registry
    # ------------------------------------------------------------------

    def add_tech(self, entry: TechEntry) -> None:
        self._tech_registry[entry.id] = entry
        self.log("tech_added", details={"id": entry.id, "tier": entry.tier.value})

    def rate_tech(self, tech_id: str, tier: RecommendationTier, notes: str = "") -> None:
        entry = self._tech_registry.get(tech_id)
        if entry:
            entry.tier = tier
            if notes:
                entry.notes = notes
            entry.updated_at = datetime.now(timezone.utc).isoformat()
            self.log("tech_rated", details={"id": tech_id, "tier": tier.value})

    def search_tech(
        self,
        query: str | None = None,
        category: TechCategory | None = None,
        tier: RecommendationTier | None = None,
    ) -> list[TechEntry]:
        results = list(self._tech_registry.values())
        if category:
            results = [t for t in results if t.category == category]
        if tier:
            results = [t for t in results if t.tier == tier]
        if query:
            q = query.lower()
            results = [t for t in results if q in t.name.lower() or q in t.id.lower()
                       or q in t.description.lower() or q in t.notes.lower()]
        return results

    def get_tier_list(self) -> dict[str, list[dict[str, Any]]]:
        tiers: dict[str, list[dict[str, Any]]] = {}
        for entry in self._tech_registry.values():
            tier_key = entry.tier.value
            if tier_key not in tiers:
                tiers[tier_key] = []
            tiers[tier_key].append({
                "id": entry.id, "name": entry.name,
                "category": entry.category.value, "notes": entry.notes,
                "skill_level": entry.skill_level.value,
            })
        return tiers

    # ------------------------------------------------------------------
    # Public API — Code Snippets
    # ------------------------------------------------------------------

    def add_snippet(self, snippet: CodeSnippet) -> None:
        self._snippets[snippet.id] = snippet
        self.log("snippet_added", details={"id": snippet.id, "lang": snippet.language})

    def search_snippets(
        self, query: str | None = None, language: str | None = None,
    ) -> list[CodeSnippet]:
        results = list(self._snippets.values())
        if language:
            results = [s for s in results if s.language.lower() == language.lower()]
        if query:
            q = query.lower()
            results = [s for s in results if q in s.title.lower() or q in s.description.lower()
                       or q in s.code.lower()]
        return results

    # ------------------------------------------------------------------
    # Public API — Projects
    # ------------------------------------------------------------------

    def add_project(self, project: ProjectRecord) -> None:
        self._projects[project.id] = project
        self.log("project_added", details={"id": project.id, "status": project.status.value})

    def get_project(self, project_id: str) -> ProjectRecord | None:
        return self._projects.get(project_id)

    # ------------------------------------------------------------------
    # Public API — Learning Paths
    # ------------------------------------------------------------------

    def add_learning_path(self, path: LearningPath) -> None:
        self._learning_paths[path.id] = path
        self.log("learning_path_added", details={"id": path.id, "title": path.title})

    def skill_assessment(self) -> dict[str, Any]:
        by_level: dict[str, list[str]] = {}
        for entry in self._tech_registry.values():
            level = entry.skill_level.value
            if level not in by_level:
                by_level[level] = []
            by_level[level].append(entry.name)
        return {
            "total_technologies": len(self._tech_registry),
            "by_skill_level": by_level,
            "learning_paths_active": len(self._learning_paths),
        }

    # ------------------------------------------------------------------
    # Public API — Stack Recommendations
    # ------------------------------------------------------------------

    def recommend_stack(self, project_type: str) -> dict[str, Any]:
        stacks = {
            "saas": {
                "summary": "Ship a SaaS in 2026? Next.js + Postgres. Done. Stop overthinking.",
                "stack": [
                    {"name": "Next.js", "reason": "SSR + API routes in one framework. Deploy to Vercel in 30 seconds."},
                    {"name": "TypeScript", "reason": "Type safety or type tragedy. Your call."},
                    {"name": "Tailwind CSS", "reason": "Ship UI fast without writing a single CSS file."},
                    {"name": "PostgreSQL", "reason": "ACID-compliant, battle-tested, handles 99% of use cases."},
                    {"name": "Redis", "reason": "Session store + cache. Sub-millisecond reads."},
                    {"name": "Docker", "reason": "Containerize everything. No 'works on my machine' excuses."},
                ],
            },
            "api": {
                "summary": "Building an API? FastAPI is Python's gift to the backend world.",
                "stack": [
                    {"name": "FastAPI", "reason": "Automatic OpenAPI docs, type validation, async by default."},
                    {"name": "Python", "reason": "The lingua franca of APIs, ML, and everything between."},
                    {"name": "PostgreSQL", "reason": "Relational data done right. Use SQLAlchemy for ORM."},
                    {"name": "Redis", "reason": "Rate limiting, caching, pub/sub. The Swiss Army knife."},
                    {"name": "Docker", "reason": "One Dockerfile, deploy anywhere. Cloud-agnostic."},
                ],
            },
            "static_site": {
                "summary": "Static site? SvelteKit compiles away the framework. Tiny bundles, huge performance.",
                "stack": [
                    {"name": "SvelteKit", "reason": "Compiled output, no virtual DOM overhead. Your Lighthouse score will thank you."},
                    {"name": "TypeScript", "reason": "Even static sites deserve type safety."},
                    {"name": "Tailwind CSS", "reason": "Utility-first CSS. Purge unused styles automatically."},
                    {"name": "Vercel/Cloudflare", "reason": "Edge deployment. Your site loads before the user blinks."},
                ],
            },
            "ai_app": {
                "summary": "AI app? Python + FastAPI + local Ollama. Keep your data sovereign.",
                "stack": [
                    {"name": "Python", "reason": "Every AI library speaks Python. No exceptions."},
                    {"name": "FastAPI", "reason": "Async endpoints for streaming LLM responses."},
                    {"name": "PostgreSQL + pgvector", "reason": "Vector search without a separate vector DB. Less infra, less pain."},
                    {"name": "Redis", "reason": "Cache LLM responses. Save tokens, save money."},
                    {"name": "Ollama", "reason": "Local inference. Data sovereignty. No API bills."},
                    {"name": "Docker", "reason": "GPU passthrough containers for reproducible ML environments."},
                ],
            },
            "mobile": {
                "summary": "Mobile in 2026? React Native + Expo. One codebase, both platforms.",
                "stack": [
                    {"name": "React Native", "reason": "Write once, deploy iOS + Android. The dream actually works now."},
                    {"name": "TypeScript", "reason": "Mobile bugs are 10x harder to debug. Types are your safety net."},
                    {"name": "Expo", "reason": "OTA updates, managed builds, push notifications. The cheat code."},
                    {"name": "Supabase", "reason": "Postgres + Auth + Realtime. Firebase but open source."},
                ],
            },
        }
        result = stacks.get(project_type)
        if result:
            return result
        return {
            "summary": f"'{project_type}'? Tell me what you're building and I'll tell you what to use. No stack is one-size-fits-all.",
            "stack": [],
        }

    # ------------------------------------------------------------------
    # Public API — Web Audit
    # ------------------------------------------------------------------

    def web_audit(self, domain: str) -> dict[str, dict[str, str]]:
        return {
            "performance": {"status": "needs_review", "note": "Lighthouse score should be 90+. Your users have the attention span of a goldfish."},
            "https": {"status": "needs_review", "note": "TLS or GTFO. It's 2026."},
            "headers": {"status": "needs_review", "note": "Security headers aren't optional. CSP, HSTS, X-Frame-Options."},
            "responsive": {"status": "needs_review", "note": "Mobile-first or mobile-worst. Your choice."},
            "accessibility": {"status": "needs_review", "note": "a11y isn't a nice-to-have. It's the law in many places."},
            "seo": {"status": "needs_review", "note": "If Google can't find you, do you even exist?"},
            "bundle_size": {"status": "needs_review", "note": "Every kilobyte is a user you lost. Ship less JavaScript."},
            "caching": {"status": "needs_review", "note": "Cache everything. Invalidate surgically."},
            "error_handling": {"status": "needs_review", "note": "Your 500 page shouldn't be a white screen of death."},
            "monitoring": {"status": "needs_review", "note": "If you're not measuring it, you're guessing."},
        }

    # ------------------------------------------------------------------
    # Public API — Wisdom & Misc
    # ------------------------------------------------------------------

    def get_wisdom(self) -> str:
        if not self._fireship_wisdom:
            return "Ship it."
        return random.choice(self._fireship_wisdom)

    def get_system_inventory(self) -> list[dict[str, Any]]:
        return [
            {"id": c.id, "name": c.name, "type": c.component_type,
             "status": c.status, "specs": c.specs}
            for c in self._system_components.values()
        ]

    def code_review_tips(self, language: str) -> list[str]:
        common = [
            "Check for hardcoded secrets. grep for API keys, passwords, tokens.",
            "Verify error handling covers edge cases, not just the happy path.",
            "Look for N+1 query patterns. Your database will thank you.",
            "Check that new dependencies are actually necessary. Every dep is a liability.",
            "Verify tests exist for new logic. No tests = no confidence.",
        ]
        lang_tips = {
            "python": [
                "Use type hints. mypy is your friend.",
                "Prefer pathlib over os.path. It's 2026.",
                "Check for bare except clauses. Catch specific exceptions.",
                "Use dataclasses or Pydantic for structured data, not raw dicts.",
                "Async where it matters, sync where it doesn't. Don't async everything.",
            ],
            "typescript": [
                "No 'any' types unless you have a VERY good reason.",
                "Use strict mode. Always. No exceptions.",
                "Prefer const over let. Use let only when reassignment is needed.",
                "Check for proper null handling. Optional chaining is your friend.",
                "Validate external data at the boundary with Zod or similar.",
            ],
            "javascript": [
                "Why aren't you using TypeScript? Seriously.",
                "Check for == vs ===. Always use strict equality.",
                "Verify Promise chains have proper error handling.",
                "Look for memory leaks in event listeners and intervals.",
                "Use modern syntax. No var, no callbacks when async/await works.",
            ],
        }
        return common + lang_tips.get(language.lower(), [
            f"General advice: follow {language}'s community style guide.",
            "Consistency matters more than any specific style.",
        ])

    def get_sql_schema(self) -> str:
        return SQL_SCHEMA

    def get_neo4j_schema(self) -> str:
        return NEO4J_SCHEMA

    def get_dgraph_schema(self) -> str:
        return DGRAPH_SCHEMA

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    def run(self) -> AgentReport:
        self._set_status(AgentStatus.RUNNING)
        alerts: list[str] = []
        recommendations: list[str] = []
        actions: list[str] = []

        # System inventory
        actions.append(f"Discovered {len(self._system_components)} system components.")

        # Tech health check
        outdated = [t for t in self._tech_registry.values()
                    if t.version_current and t.version_latest
                    and t.version_current != t.version_latest]
        if outdated:
            alerts.append(f"{len(outdated)} technologies have outdated versions.")

        # Project health
        paused = [p for p in self._projects.values() if p.status == ProjectStatus.PAUSED]
        if paused:
            names = ", ".join(p.name for p in paused)
            recommendations.append(f"Paused projects need attention: {names}")

        # Novice skills to level up
        novice = [t for t in self._tech_registry.values()
                  if t.skill_level == SkillLevel.NOVICE and t.tier in (
                      RecommendationTier.S_TIER, RecommendationTier.A_TIER)]
        if novice:
            names = ", ".join(t.name for t in novice[:5])
            recommendations.append(f"Level up these S/A-tier skills: {names}")

        # Wisdom of the day
        wisdom = self.get_wisdom()
        actions.append(f"Wisdom: {wisdom}")

        self._set_status(AgentStatus.IDLE)
        return AgentReport(
            agent_name=self.name,
            status=AgentStatus.IDLE.value,
            summary=(
                f"The Archivist tracking {len(self._tech_registry)} technologies, "
                f"{len(self._projects)} projects, {len(self._system_components)} system components. "
                f"// {wisdom}"
            ),
            actions_taken=actions,
            recommendations=recommendations,
            alerts=alerts,
            data={
                "technologies": len(self._tech_registry),
                "snippets": len(self._snippets),
                "projects": len(self._projects),
                "learning_paths": len(self._learning_paths),
                "system_components": len(self._system_components),
                "dev_sessions": len(self._dev_sessions),
                "tier_list": self.get_tier_list(),
            },
        )

    def report(self) -> AgentReport:
        return AgentReport(
            agent_name=self.name,
            status=self.status.value,
            summary=(
                f"The Archivist: {len(self._tech_registry)} technologies, "
                f"{len(self._projects)} projects, "
                f"{len(self._system_components)} system components, "
                f"{len(self._snippets)} code patterns."
            ),
            data={
                "technologies": len(self._tech_registry),
                "snippets": len(self._snippets),
                "projects": len(self._projects),
                "learning_paths": len(self._learning_paths),
                "system_components": list(self._system_components.keys()),
                "wisdom_count": len(self._fireship_wisdom),
            },
        )
