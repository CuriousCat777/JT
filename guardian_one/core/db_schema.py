"""Database Schema Module — ACID-compliant relational + graph database models.

Provides schema definitions for:
- SQLite/PostgreSQL relational tables (ACID-compliant)
- Neo4j Cypher graph models (nodes + relationships)
- Dgraph GraphQL schema (edges + predicates)

These schemas power the Archivist's knowledge graph — connecting
technologies, recommendations, projects, learning paths, and system state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ============================================================
# Enums
# ============================================================

class TechCategory(Enum):
    LANGUAGE = "language"
    FRAMEWORK = "framework"
    RUNTIME = "runtime"
    DATABASE = "database"
    TOOL = "tool"
    PLATFORM = "platform"
    LIBRARY = "library"
    PROTOCOL = "protocol"
    PARADIGM = "paradigm"
    INFRASTRUCTURE = "infrastructure"


class RecommendationTier(Enum):
    """Fireship-style opinionated tier list."""
    S_TIER = "S"       # Ship it yesterday — industry standard, battle-tested
    A_TIER = "A"       # Solid choice — use with confidence
    B_TIER = "B"       # Good but situational — know the trade-offs
    C_TIER = "C"       # Legacy or niche — migrate when possible
    D_TIER = "D"       # Avoid — better alternatives exist
    F_TIER = "F"       # Mass extinction event — run


class ProjectStatus(Enum):
    PLANNING = "planning"
    ACTIVE = "active"
    PAUSED = "paused"
    SHIPPED = "shipped"
    ARCHIVED = "archived"


class SkillLevel(Enum):
    NOVICE = "novice"           # Just heard of it
    BEGINNER = "beginner"       # Hello world
    INTERMEDIATE = "intermediate"  # Can build things
    ADVANCED = "advanced"       # Deep understanding
    EXPERT = "expert"           # Could teach it


# ============================================================
# Relational Models (ACID-compliant SQL)
# ============================================================

@dataclass
class TechEntry:
    """A technology tracked by the Archivist."""
    id: str                               # e.g. "typescript", "nextjs"
    name: str                             # Human-readable name
    category: TechCategory = TechCategory.TOOL
    tier: RecommendationTier = RecommendationTier.B_TIER
    description: str = ""
    website: str = ""
    github_url: str = ""
    version_current: str = ""
    version_latest: str = ""
    skill_level: SkillLevel = SkillLevel.NOVICE
    last_used: str | None = None
    notes: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class CodeSnippet:
    """Reusable code patterns indexed by the Archivist."""
    id: str
    title: str
    language: str
    code: str
    description: str = ""
    tech_ids: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    source: str = ""                       # Where it came from
    use_this: str = ""                     # "Code THIS"
    not_that: str = ""                     # "NOT THAT" — antipattern
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ProjectRecord:
    """A project tracked by the Archivist."""
    id: str
    name: str
    description: str = ""
    status: ProjectStatus = ProjectStatus.PLANNING
    tech_stack: list[str] = field(default_factory=list)   # tech entry IDs
    repo_url: str = ""
    domain: str = ""
    architecture: str = ""                 # e.g. "monolith", "microservices", "serverless"
    deploy_target: str = ""                # e.g. "vercel", "cloud_vps", "docker"
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class LearningPath:
    """A structured learning path recommended by the Archivist."""
    id: str
    title: str
    description: str = ""
    tech_ids: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    estimated_hours: int = 0
    priority: int = 0                      # 1 = highest
    completed_steps: list[int] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SystemComponent:
    """A hardware/software component on the connected system."""
    id: str
    name: str
    component_type: str                    # "cpu", "gpu", "ram", "disk", "os", "service"
    specs: dict[str, Any] = field(default_factory=dict)
    hostname: str = ""
    status: str = "unknown"                # "online", "offline", "degraded", "unknown"
    last_seen: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class DevSession:
    """A tracked development session for analytics."""
    id: str
    project_id: str | None
    start_time: str
    end_time: str | None = None
    tech_used: list[str] = field(default_factory=list)
    files_changed: int = 0
    commits: int = 0
    notes: str = ""
    productivity_score: float = 0.0        # 0-10


# ============================================================
# SQL DDL — ACID-compliant relational schema
# ============================================================

SQL_SCHEMA = """
-- Archivist Dev Coach — Relational Schema
-- ACID-compliant, foreign key enforced, indexed for performance
-- SQLite 3.35+ schema
-- NOTE: SQLite connection PRAGMAs such as `journal_mode=WAL` and
-- `foreign_keys=ON` must be applied during SQLite connection setup,
-- not embedded in shared DDL.
-- Core technology registry
CREATE TABLE IF NOT EXISTS tech_entries (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL CHECK(category IN (
                        'language','framework','runtime','database',
                        'tool','platform','library','protocol',
                        'paradigm','infrastructure'
                    )),
    tier            TEXT NOT NULL DEFAULT 'B' CHECK(tier IN ('S','A','B','C','D','F')),
    description     TEXT DEFAULT '',
    website         TEXT DEFAULT '',
    github_url      TEXT DEFAULT '',
    version_current TEXT DEFAULT '',
    version_latest  TEXT DEFAULT '',
    skill_level     TEXT DEFAULT 'novice' CHECK(skill_level IN (
                        'novice','beginner','intermediate','advanced','expert'
                    )),
    last_used       TEXT,
    notes           TEXT DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_tech_category ON tech_entries(category);
CREATE INDEX IF NOT EXISTS idx_tech_tier ON tech_entries(tier);

-- Tech tags (many-to-many)
CREATE TABLE IF NOT EXISTS tech_tags (
    tech_id TEXT NOT NULL REFERENCES tech_entries(id) ON DELETE CASCADE,
    tag     TEXT NOT NULL,
    PRIMARY KEY (tech_id, tag)
);

-- Technology relationships (depends_on, alternative_to, works_with)
CREATE TABLE IF NOT EXISTS tech_relations (
    source_id     TEXT NOT NULL REFERENCES tech_entries(id) ON DELETE CASCADE,
    target_id     TEXT NOT NULL REFERENCES tech_entries(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL CHECK(relation_type IN (
                      'depends_on','alternative_to','works_with',
                      'replaced_by','extends','competes_with'
                  )),
    weight        REAL DEFAULT 1.0,
    notes         TEXT DEFAULT '',
    PRIMARY KEY (source_id, target_id, relation_type)
);

-- Code snippets (the "Code This Not That" vault)
CREATE TABLE IF NOT EXISTS code_snippets (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    language    TEXT NOT NULL,
    code        TEXT NOT NULL,
    description TEXT DEFAULT '',
    source      TEXT DEFAULT '',
    use_this    TEXT DEFAULT '',
    not_that    TEXT DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS snippet_techs (
    snippet_id TEXT NOT NULL REFERENCES code_snippets(id) ON DELETE CASCADE,
    tech_id    TEXT NOT NULL REFERENCES tech_entries(id) ON DELETE CASCADE,
    PRIMARY KEY (snippet_id, tech_id)
);

-- Projects
CREATE TABLE IF NOT EXISTS projects (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'planning' CHECK(status IN (
                      'planning','active','paused','shipped','archived'
                  )),
    repo_url      TEXT DEFAULT '',
    domain        TEXT DEFAULT '',
    architecture  TEXT DEFAULT '',
    deploy_target TEXT DEFAULT '',
    notes         TEXT DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS project_tech_stack (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    tech_id    TEXT NOT NULL REFERENCES tech_entries(id) ON DELETE CASCADE,
    role       TEXT DEFAULT 'core',  -- 'core', 'dev', 'testing', 'deploy'
    PRIMARY KEY (project_id, tech_id)
);

-- Learning paths
CREATE TABLE IF NOT EXISTS learning_paths (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    description     TEXT DEFAULT '',
    estimated_hours INTEGER DEFAULT 0,
    priority        INTEGER DEFAULT 5,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS learning_steps (
    path_id   TEXT NOT NULL REFERENCES learning_paths(id) ON DELETE CASCADE,
    step_num  INTEGER NOT NULL,
    title     TEXT NOT NULL,
    completed INTEGER DEFAULT 0,
    PRIMARY KEY (path_id, step_num)
);

CREATE TABLE IF NOT EXISTS learning_path_techs (
    path_id TEXT NOT NULL REFERENCES learning_paths(id) ON DELETE CASCADE,
    tech_id TEXT NOT NULL REFERENCES tech_entries(id) ON DELETE CASCADE,
    PRIMARY KEY (path_id, tech_id)
);

-- System components (hardware/software inventory)
CREATE TABLE IF NOT EXISTS system_components (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    component_type  TEXT NOT NULL,
    hostname        TEXT DEFAULT '',
    specs           TEXT DEFAULT '{}',  -- JSON blob
    status          TEXT DEFAULT 'unknown',
    last_seen       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- Dev sessions (productivity tracking)
CREATE TABLE IF NOT EXISTS dev_sessions (
    id                TEXT PRIMARY KEY,
    project_id        TEXT REFERENCES projects(id) ON DELETE SET NULL,
    start_time        TEXT NOT NULL,
    end_time          TEXT,
    files_changed     INTEGER DEFAULT 0,
    commits           INTEGER DEFAULT 0,
    notes             TEXT DEFAULT '',
    productivity_score REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS session_techs (
    session_id TEXT NOT NULL REFERENCES dev_sessions(id) ON DELETE CASCADE,
    tech_id    TEXT NOT NULL REFERENCES tech_entries(id) ON DELETE CASCADE,
    PRIMARY KEY (session_id, tech_id)
);

-- Audit trail for all Archivist actions
CREATE TABLE IF NOT EXISTS archivist_audit (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    action    TEXT NOT NULL,
    details   TEXT DEFAULT '{}',
    severity  TEXT DEFAULT 'info',
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- Recommendations log (AI-generated advice history)
CREATE TABLE IF NOT EXISTS recommendations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT NOT NULL,  -- 'tech_choice', 'architecture', 'performance', 'security'
    summary     TEXT NOT NULL,
    details     TEXT DEFAULT '',
    confidence  REAL DEFAULT 0.8,
    acted_on    INTEGER DEFAULT 0,
    timestamp   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
"""


# ============================================================
# Neo4j Cypher Schema — Knowledge Graph
# ============================================================

NEO4J_SCHEMA = """
// Archivist Dev Coach — Neo4j Knowledge Graph
// Nodes represent entities, relationships capture how they connect.
// This is the "developer brain" that maps everything Jeremy knows and uses.

// ---- Constraints (ACID equivalent in Neo4j) ----
CREATE CONSTRAINT tech_id_unique IF NOT EXISTS
  FOR (t:Technology) REQUIRE t.id IS UNIQUE;

CREATE CONSTRAINT project_id_unique IF NOT EXISTS
  FOR (p:Project) REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT snippet_id_unique IF NOT EXISTS
  FOR (s:Snippet) REQUIRE s.id IS UNIQUE;

CREATE CONSTRAINT path_id_unique IF NOT EXISTS
  FOR (lp:LearningPath) REQUIRE lp.id IS UNIQUE;

CREATE CONSTRAINT component_id_unique IF NOT EXISTS
  FOR (c:SystemComponent) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT session_id_unique IF NOT EXISTS
  FOR (ds:DevSession) REQUIRE ds.id IS UNIQUE;

// ---- Indexes ----
CREATE INDEX tech_category_idx IF NOT EXISTS FOR (t:Technology) ON (t.category);
CREATE INDEX tech_tier_idx IF NOT EXISTS FOR (t:Technology) ON (t.tier);
CREATE INDEX project_status_idx IF NOT EXISTS FOR (p:Project) ON (p.status);

// ---- Node Labels ----
// :Technology  — languages, frameworks, tools, databases
// :Project     — codebases, websites, services
// :Snippet     — reusable code patterns
// :LearningPath — structured learning tracks
// :SystemComponent — hardware/software on connected machines
// :DevSession  — tracked coding sessions
// :Owner       — Jeremy (single node, center of the graph)
// :Tag         — taxonomy tags

// ---- Relationship Types (Edges) ----
// (:Technology)-[:DEPENDS_ON]->(:Technology)
// (:Technology)-[:ALTERNATIVE_TO]->(:Technology)
// (:Technology)-[:WORKS_WITH]->(:Technology)
// (:Technology)-[:REPLACED_BY]->(:Technology)
// (:Technology)-[:EXTENDS]->(:Technology)
// (:Technology)-[:COMPETES_WITH]->(:Technology)
//
// (:Project)-[:USES {role: 'core'|'dev'|'testing'|'deploy'}]->(:Technology)
// (:Project)-[:DEPLOYED_ON]->(:SystemComponent)
//
// (:Snippet)-[:DEMONSTRATES]->(:Technology)
// (:Snippet)-[:TAGGED_WITH]->(:Tag)
//
// (:LearningPath)-[:COVERS]->(:Technology)
// (:LearningPath)-[:PREREQUISITE]->(:LearningPath)
//
// (:Owner)-[:KNOWS {level: 'novice'..'expert'}]->(:Technology)
// (:Owner)-[:OWNS]->(:Project)
// (:Owner)-[:STUDYING]->(:LearningPath)
// (:Owner)-[:RUNS]->(:SystemComponent)
//
// (:DevSession)-[:SESSION_FOR]->(:Project)
// (:DevSession)-[:USED]->(:Technology)

// ---- Sample seed data ----
MERGE (owner:Owner {name: 'Jeremy Paulo Salvino Tabernero'})

// S-Tier technologies
MERGE (python:Technology {id: 'python', name: 'Python', category: 'language', tier: 'S'})
MERGE (typescript:Technology {id: 'typescript', name: 'TypeScript', category: 'language', tier: 'S'})
MERGE (git:Technology {id: 'git', name: 'Git', category: 'tool', tier: 'S'})
MERGE (linux:Technology {id: 'linux', name: 'Linux', category: 'platform', tier: 'S'})
MERGE (docker:Technology {id: 'docker', name: 'Docker', category: 'infrastructure', tier: 'S'})
MERGE (postgres:Technology {id: 'postgresql', name: 'PostgreSQL', category: 'database', tier: 'S'})

// A-Tier
MERGE (nextjs:Technology {id: 'nextjs', name: 'Next.js', category: 'framework', tier: 'A'})
MERGE (svelte:Technology {id: 'sveltekit', name: 'SvelteKit', category: 'framework', tier: 'A'})
MERGE (tailwind:Technology {id: 'tailwind', name: 'Tailwind CSS', category: 'library', tier: 'A'})
MERGE (neo4j:Technology {id: 'neo4j', name: 'Neo4j', category: 'database', tier: 'A'})
MERGE (rust:Technology {id: 'rust', name: 'Rust', category: 'language', tier: 'A'})
MERGE (go:Technology {id: 'golang', name: 'Go', category: 'language', tier: 'A'})
MERGE (redis:Technology {id: 'redis', name: 'Redis', category: 'database', tier: 'A'})
MERGE (fastapi:Technology {id: 'fastapi', name: 'FastAPI', category: 'framework', tier: 'A'})

// Relationships
MERGE (typescript)-[:WORKS_WITH]->(nextjs)
MERGE (typescript)-[:WORKS_WITH]->(svelte)
MERGE (nextjs)-[:COMPETES_WITH]->(svelte)
MERGE (tailwind)-[:WORKS_WITH]->(nextjs)
MERGE (tailwind)-[:WORKS_WITH]->(svelte)
MERGE (python)-[:WORKS_WITH]->(fastapi)
MERGE (docker)-[:WORKS_WITH]->(postgres)
MERGE (docker)-[:WORKS_WITH]->(neo4j)
MERGE (docker)-[:WORKS_WITH]->(redis)

// Owner knowledge graph
MERGE (owner)-[:KNOWS {level: 'advanced'}]->(python)
MERGE (owner)-[:KNOWS {level: 'intermediate'}]->(typescript)
MERGE (owner)-[:KNOWS {level: 'advanced'}]->(git)
MERGE (owner)-[:KNOWS {level: 'intermediate'}]->(linux)
MERGE (owner)-[:KNOWS {level: 'intermediate'}]->(docker)
"""


# ============================================================
# Dgraph GraphQL Schema
# ============================================================

DGRAPH_SCHEMA = """
# Archivist Dev Coach — Dgraph GraphQL Schema
# Distributed graph database with ACID transactions
# Edges are first-class citizens in Dgraph

type Technology {
    id: ID!
    techId: String! @id @search(by: [hash, term])
    name: String! @search(by: [fulltext, term])
    category: TechCategory! @search(by: [hash])
    tier: String! @search(by: [hash])
    description: String @search(by: [fulltext])
    website: String
    githubUrl: String
    versionCurrent: String
    versionLatest: String
    skillLevel: String @search(by: [hash])
    lastUsed: DateTime
    notes: String
    tags: [String] @search(by: [hash])
    createdAt: DateTime!
    updatedAt: DateTime!

    # Edges — relationships to other technologies
    dependsOn: [Technology] @hasInverse(field: dependedOnBy)
    dependedOnBy: [Technology]
    alternativeTo: [Technology]
    worksWith: [Technology]
    replacedBy: [Technology]
    extends: [Technology]
    competesWith: [Technology]

    # Reverse edges — which projects/snippets use this tech
    usedByProjects: [Project] @hasInverse(field: techStack)
    demonstratedBy: [Snippet] @hasInverse(field: demonstrates)
    coveredBy: [LearningPath] @hasInverse(field: covers)
}

enum TechCategory {
    LANGUAGE
    FRAMEWORK
    RUNTIME
    DATABASE
    TOOL
    PLATFORM
    LIBRARY
    PROTOCOL
    PARADIGM
    INFRASTRUCTURE
}

type Project {
    id: ID!
    projectId: String! @id @search(by: [hash])
    name: String! @search(by: [fulltext, term])
    description: String @search(by: [fulltext])
    status: ProjectStatus! @search(by: [hash])
    repoUrl: String
    domain: String @search(by: [term])
    architecture: String
    deployTarget: String
    notes: String
    createdAt: DateTime!
    updatedAt: DateTime!

    techStack: [Technology]
    deployedOn: [SystemComponent]
    sessions: [DevSession] @hasInverse(field: project)
    owner: Owner! @hasInverse(field: projects)
}

enum ProjectStatus {
    PLANNING
    ACTIVE
    PAUSED
    SHIPPED
    ARCHIVED
}

type Snippet {
    id: ID!
    snippetId: String! @id
    title: String! @search(by: [fulltext, term])
    language: String! @search(by: [hash])
    code: String!
    description: String @search(by: [fulltext])
    source: String
    useThis: String
    notThat: String
    createdAt: DateTime!

    demonstrates: [Technology]
    tags: [String] @search(by: [hash])
}

type LearningPath {
    id: ID!
    pathId: String! @id
    title: String! @search(by: [fulltext])
    description: String
    estimatedHours: Int
    priority: Int @search(by: [int])
    createdAt: DateTime!

    covers: [Technology]
    steps: [LearningStep]
    prerequisites: [LearningPath]
    student: Owner @hasInverse(field: studying)
}

type LearningStep {
    id: ID!
    stepNum: Int!
    title: String!
    completed: Boolean!
    path: LearningPath! @hasInverse(field: steps)
}

type SystemComponent {
    id: ID!
    componentId: String! @id @search(by: [hash])
    name: String! @search(by: [term])
    componentType: String! @search(by: [hash])
    hostname: String @search(by: [term])
    specs: String  # JSON blob
    status: String! @search(by: [hash])
    lastSeen: DateTime!

    runsOn: Owner @hasInverse(field: systems)
    hosts: [Project] @hasInverse(field: deployedOn)
}

type DevSession {
    id: ID!
    sessionId: String! @id
    startTime: DateTime! @search(by: [hour])
    endTime: DateTime
    filesChanged: Int
    commits: Int
    notes: String
    productivityScore: Float

    project: Project
    techUsed: [Technology]
}

type Owner {
    id: ID!
    name: String! @search(by: [fulltext])
    timezone: String
    createdAt: DateTime!

    # The center of the graph — everything connects to the owner
    knows: [Technology]
    projects: [Project]
    studying: [LearningPath]
    systems: [SystemComponent]
}

# ---- Dgraph DQL Predicates (for raw RDF queries) ----
# <techId>: string @index(hash, term) .
# <name>: string @index(fulltext, term) .
# <category>: string @index(hash) .
# <tier>: string @index(hash) .
# <depends_on>: [uid] @reverse .
# <works_with>: [uid] .
# <alternative_to>: [uid] .
# <replaced_by>: [uid] .
# <uses_tech>: [uid] @reverse .
# <deployed_on>: [uid] @reverse .
# <knows>: [uid] @reverse .
# <owns>: [uid] @reverse .
"""
