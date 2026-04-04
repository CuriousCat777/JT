"""Teleprompter — Telehospitalist Patient Interaction Agent.

Responsibilities:
- Generate and manage clinical communication scripts
- AI advisory on patient interaction best practices
- Track practice sessions with scoring and feedback
- Provide real-time prompts during telehealth encounters
- Maintain a script library organized by clinical scenario
- Record and analyze practice test performance over time

Designed for Dr. Jeremy Tabernero's telehospitalist workflow.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.base_agent import AgentReport, AgentStatus, BaseAgent
from guardian_one.core.config import AgentConfig

from guardian_one.agents.teleprompter_db import TeleprompterDB


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Script:
    """A teleprompter script for a clinical scenario."""
    script_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str = ""
    category: str = "general"  # admission, discharge, consult, code, handoff, family, general
    scenario: str = ""         # description of the clinical situation
    content: str = ""          # the actual script text
    tags: list[str] = field(default_factory=list)
    scroll_speed: int = 3      # 1-5 scale (1=slow, 5=fast)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ai_generated: bool = False
    notes: str = ""


@dataclass
class PracticeSession:
    """Records a single practice test session."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    script_id: str = ""
    script_title: str = ""
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str = ""
    duration_seconds: int = 0
    self_rating: int = 0             # 1-5 self-assessment
    ai_feedback: str = ""            # AI advisory feedback
    areas_of_strength: list[str] = field(default_factory=list)
    areas_to_improve: list[str] = field(default_factory=list)
    notes: str = ""
    completed: bool = False


@dataclass
class AdvisoryTip:
    """An AI-generated advisory tip for patient interaction."""
    tip_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    category: str = ""       # empathy, clarity, pacing, cultural, legal, rapport
    content: str = ""
    scenario: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Script categories with telehospitalist-specific templates
# ---------------------------------------------------------------------------

SCRIPT_CATEGORIES = {
    "admission": "New patient admission / initial encounter",
    "discharge": "Discharge instructions and follow-up planning",
    "consult": "Specialist consultation requests",
    "code": "Code blue / rapid response communication",
    "handoff": "Shift handoff and SBAR communication",
    "family": "Family meetings and goals-of-care discussions",
    "bad_news": "Delivering difficult news (SPIKES protocol)",
    "informed_consent": "Procedure consent and risk discussion",
    "cross_cover": "Cross-cover and overnight call scenarios",
    "general": "General patient interaction",
}

DEFAULT_SCRIPTS: list[dict[str, Any]] = [
    {
        "title": "Admission — Initial Telehealth Encounter",
        "category": "admission",
        "scenario": "First contact with a newly admitted patient via video",
        "content": (
            "Good [morning/afternoon/evening], I'm Dr. Tabernero. "
            "I'll be your hospitalist taking care of you today.\n\n"
            "I know being in the hospital can be stressful, and I want you to know "
            "that even though we're connecting by video, I'm fully here for you.\n\n"
            "Before we begin, can you confirm your full name and date of birth for me?\n\n"
            "[PAUSE — verify identity]\n\n"
            "Thank you. I've reviewed your chart and I'd like to go over a few things with you.\n\n"
            "First, can you tell me in your own words what brought you to the hospital today?\n\n"
            "[PAUSE — active listening, 30-60 seconds]\n\n"
            "Thank you for sharing that. Let me summarize what I understand, and please "
            "correct me if I get anything wrong.\n\n"
            "[SUMMARIZE — reflect back key points]\n\n"
            "Here's what I'd like us to focus on today:\n"
            "1. [Primary concern]\n"
            "2. [Secondary items]\n"
            "3. [Any pending workup]\n\n"
            "Do you have any questions so far?\n\n"
            "[PAUSE — address questions]\n\n"
            "I'll be checking in on you [frequency]. If you need anything before then, "
            "please let your nurse know and they can reach me.\n\n"
            "Is there anything else on your mind before we wrap up?"
        ),
        "tags": ["admission", "introduction", "rapport"],
    },
    {
        "title": "SBAR Handoff Communication",
        "category": "handoff",
        "scenario": "Shift handoff using SBAR framework",
        "content": (
            "SITUATION:\n"
            "I'm calling about [Patient Name] in [Room/Unit].\n"
            "They are a [age]-year-old [gender] admitted for [diagnosis].\n"
            "Current status: [stable/unstable/improving/declining]\n\n"
            "BACKGROUND:\n"
            "Admitted on [date] with [chief complaint].\n"
            "Key history: [relevant PMH, allergies, code status]\n"
            "Hospital course: [major events, procedures, changes]\n\n"
            "ASSESSMENT:\n"
            "Current vitals: [latest set]\n"
            "Key labs: [pertinent results]\n"
            "Active issues:\n"
            "  1. [Issue] — [current plan]\n"
            "  2. [Issue] — [current plan]\n"
            "  3. [Issue] — [current plan]\n\n"
            "RECOMMENDATION:\n"
            "Overnight, please watch for: [specific concerns]\n"
            "Pending: [labs, imaging, consults]\n"
            "If [condition], then [action].\n"
            "Anticipated disposition: [expected LOS, discharge criteria]\n\n"
            "Any questions?"
        ),
        "tags": ["handoff", "SBAR", "communication"],
    },
    {
        "title": "Delivering Difficult News (SPIKES)",
        "category": "bad_news",
        "scenario": "Breaking bad news to patient or family via telehealth",
        "content": (
            "SETTING UP:\n"
            "Thank you for taking the time to speak with me. "
            "Is now a good time? Is there anyone else you'd like to have on this call?\n\n"
            "[PAUSE — ensure privacy and readiness]\n\n"
            "PERCEPTION:\n"
            "Before I share the results, can you tell me what your understanding is "
            "of what's been going on?\n\n"
            "[PAUSE — listen carefully to their understanding]\n\n"
            "INVITATION:\n"
            "I have the results from [test/imaging/biopsy]. "
            "Would you like me to go over all the details, or would you prefer "
            "I give you the big picture first?\n\n"
            "[PAUSE — respect their preference]\n\n"
            "KNOWLEDGE:\n"
            "I'm sorry to tell you that [deliver news clearly and compassionately].\n\n"
            "[WARNING SHOT: 'Unfortunately...' or 'I wish I had better news...']\n\n"
            "[PAUSE — allow silence, at least 5-10 seconds]\n\n"
            "EMOTION:\n"
            "I can see this is very difficult to hear. That's completely understandable.\n"
            "Take all the time you need.\n\n"
            "[PAUSE — acknowledge emotion, do NOT rush]\n\n"
            "STRATEGY & SUMMARY:\n"
            "When you're ready, I'd like to talk about what we can do from here.\n"
            "The next steps I'd recommend are:\n"
            "1. [Immediate plan]\n"
            "2. [Follow-up]\n"
            "3. [Support resources]\n\n"
            "I want you to know that I'm here for you through this process. "
            "What questions do you have?"
        ),
        "tags": ["bad_news", "SPIKES", "empathy", "family"],
    },
    {
        "title": "Discharge Instructions",
        "category": "discharge",
        "scenario": "Reviewing discharge plan with patient via video",
        "content": (
            "Hi [Patient Name], I'm glad to let you know we're getting you ready "
            "to go home today.\n\n"
            "Before you leave, I want to make sure we go over everything together "
            "so you feel confident about your care at home.\n\n"
            "MEDICATIONS:\n"
            "Here are the medications you'll be taking:\n"
            "  - [Med 1]: [dose, frequency, purpose]\n"
            "  - [Med 2]: [dose, frequency, purpose]\n"
            "  - STOPPED: [any discontinued meds and why]\n\n"
            "Do you have any questions about your medications?\n\n"
            "[PAUSE]\n\n"
            "FOLLOW-UP:\n"
            "You have the following appointments scheduled:\n"
            "  - [Provider] on [date/time]\n"
            "  - [Labs/imaging] on [date]\n\n"
            "WHEN TO COME BACK:\n"
            "Please come to the ER or call 911 if you experience:\n"
            "  - [Red flag 1]\n"
            "  - [Red flag 2]\n"
            "  - [Red flag 3]\n\n"
            "ACTIVITY & DIET:\n"
            "  - [Activity restrictions]\n"
            "  - [Dietary guidance]\n\n"
            "Can you tell me back in your own words what you'll do "
            "when you get home? This helps me make sure I explained things clearly.\n\n"
            "[PAUSE — teach-back method]\n\n"
            "You did great. Do you have any other questions for me?"
        ),
        "tags": ["discharge", "teach-back", "medications"],
    },
]


class Teleprompter(BaseAgent):
    """Teleprompter agent for telehospitalist patient interaction support."""

    def __init__(
        self,
        config: AgentConfig,
        audit: AuditLog,
        data_dir: str = "data",
    ) -> None:
        super().__init__(config, audit)
        self._data_dir = Path(data_dir)
        self._db_path = self._data_dir / "teleprompter_db.json"  # legacy JSON path
        self._sqlite_path = self._data_dir / "teleprompter.db"
        self._db = TeleprompterDB(self._sqlite_path)
        self._scripts: list[Script] = []
        self._sessions: list[PracticeSession] = []
        self._tips: list[AdvisoryTip] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        self._set_status(AgentStatus.IDLE)
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # Connect SQLite database
        self._db.connect()

        # Migrate from legacy JSON if it exists
        if self._db_path.exists():
            migrated = self._db.migrate_from_json(self._db_path)
            if migrated:
                self.log("db_migrated_from_json", details={"records": migrated})

        # Load into in-memory lists (keeps existing API compatible)
        self._load_db()

        # Seed default scripts if empty
        if not self._scripts:
            self._seed_defaults()

        # Sync in-memory to SQLite (covers fresh seed + legacy load)
        self._sync_to_sqlite()

        self.log("initialized", details={
            "scripts": len(self._scripts),
            "sessions": len(self._sessions),
            "tips": len(self._tips),
            "database": str(self._sqlite_path),
        })

    def run(self) -> AgentReport:
        self._set_status(AgentStatus.RUNNING)
        actions: list[str] = []
        recommendations: list[str] = []
        alerts: list[str] = []

        # Analyze practice history
        stats = self.practice_stats()
        actions.append(f"Analyzed {stats['total_sessions']} practice sessions")

        if stats["total_sessions"] > 0:
            avg = stats["average_rating"]
            if avg < 3.0:
                recommendations.append(
                    f"Average self-rating is {avg:.1f}/5 — consider more practice "
                    "with the SPIKES and SBAR scripts"
                )
            if stats["sessions_this_week"] == 0:
                recommendations.append(
                    "No practice sessions this week — try to practice at least "
                    "2-3 times per week for best results"
                )

        # Generate a fresh advisory tip if AI is available
        if self.ai_enabled:
            tip = self._generate_daily_tip()
            if tip:
                actions.append(f"Generated advisory tip: {tip.category}")

        # Check for uncovered categories
        practiced = {s.script_title for s in self._sessions if s.completed}
        all_titles = {s.title for s in self._scripts}
        unpracticed = all_titles - practiced
        if unpracticed:
            recommendations.append(
                f"{len(unpracticed)} scripts never practiced: "
                + ", ".join(list(unpracticed)[:3])
            )

        self._set_status(AgentStatus.IDLE)

        return AgentReport(
            agent_name=self.name,
            status=self.status.value,
            summary=f"Teleprompter: {len(self._scripts)} scripts, "
                    f"{stats['total_sessions']} practice sessions",
            actions_taken=actions,
            recommendations=recommendations,
            alerts=alerts,
            data={
                "scripts_count": len(self._scripts),
                "sessions_count": stats["total_sessions"],
                "average_rating": stats["average_rating"],
                "categories": list(SCRIPT_CATEGORIES.keys()),
            },
        )

    def report(self) -> AgentReport:
        stats = self.practice_stats()
        return AgentReport(
            agent_name=self.name,
            status=self.status.value,
            summary=f"Teleprompter: {len(self._scripts)} scripts, "
                    f"{stats['total_sessions']} sessions, "
                    f"avg rating {stats['average_rating']:.1f}/5",
            data={
                "scripts": len(self._scripts),
                "sessions": stats["total_sessions"],
                "average_rating": stats["average_rating"],
                "categories_practiced": stats["categories_practiced"],
            },
        )

    # ------------------------------------------------------------------
    # Script management
    # ------------------------------------------------------------------

    def list_scripts(self, category: str | None = None) -> list[dict[str, Any]]:
        """Return all scripts, optionally filtered by category."""
        scripts = self._scripts
        if category:
            scripts = [s for s in scripts if s.category == category]
        return [asdict(s) for s in scripts]

    def get_script(self, script_id: str) -> dict[str, Any] | None:
        for s in self._scripts:
            if s.script_id == script_id:
                return asdict(s)
        return None

    def create_script(
        self,
        title: str,
        category: str,
        scenario: str,
        content: str,
        tags: list[str] | None = None,
        scroll_speed: int = 3,
    ) -> dict[str, Any]:
        """Create a new script manually."""
        script = Script(
            title=title,
            category=category,
            scenario=scenario,
            content=content,
            tags=tags or [],
            scroll_speed=scroll_speed,
        )
        self._scripts.append(script)
        self._save_db()
        self.log("script_created", details={"title": title, "category": category})
        self._log_to_guardian("script_created", event_data={
            "script_id": script.script_id, "title": title, "category": category,
        })
        return asdict(script)

    def update_script(self, script_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        """Update an existing script's fields."""
        for s in self._scripts:
            if s.script_id == script_id:
                for key, val in updates.items():
                    if hasattr(s, key) and key not in ("script_id", "created_at"):
                        setattr(s, key, val)
                s.updated_at = datetime.now(timezone.utc).isoformat()
                self._save_db()
                self.log("script_updated", details={"script_id": script_id})
                self._log_to_guardian("script_updated", event_data={
                    "script_id": script_id, "fields_updated": list(updates.keys()),
                })
                return asdict(s)
        return None

    def delete_script(self, script_id: str) -> bool:
        before = len(self._scripts)
        self._scripts = [s for s in self._scripts if s.script_id != script_id]
        if len(self._scripts) < before:
            self._save_db()
            self.log("script_deleted", details={"script_id": script_id})
            self._log_to_guardian("script_deleted", event_data={
                "script_id": script_id,
            })
            return True
        return False

    def generate_script(self, scenario: str, category: str = "general") -> dict[str, Any]:
        """Use AI to generate a script for a given clinical scenario."""
        prompt = (
            f"Generate a detailed teleprompter script for a telehospitalist doctor "
            f"in the following scenario:\n\n"
            f"Category: {category} ({SCRIPT_CATEGORIES.get(category, '')})\n"
            f"Scenario: {scenario}\n\n"
            f"Requirements:\n"
            f"- Write it as a natural, empathetic telehealth conversation guide\n"
            f"- Include [PAUSE] markers where the doctor should stop and listen\n"
            f"- Include [placeholder] markers for patient-specific details\n"
            f"- Use teach-back methodology where appropriate\n"
            f"- Follow evidence-based communication frameworks (SPIKES, SBAR, etc.)\n"
            f"- Be culturally sensitive and trauma-informed\n"
            f"- Format for easy reading on a scrolling teleprompter\n\n"
            f"Return ONLY the script text, no commentary."
        )

        response = self.think(prompt, context={"category": category, "scenario": scenario})

        script = Script(
            title=f"{category.title()}: {scenario[:60]}",
            category=category,
            scenario=scenario,
            content=response.content if response.success else f"[AI unavailable — draft for: {scenario}]",
            tags=[category, "ai-generated"],
            ai_generated=True,
        )
        self._scripts.append(script)
        self._save_db()
        self.log("script_generated", details={
            "title": script.title,
            "category": category,
            "ai_provider": response.provider,
        })
        self._log_to_guardian("script_generated", event_data={
            "script_id": script.script_id, "title": script.title,
            "category": category, "ai_generated": True,
        })
        return asdict(script)

    # ------------------------------------------------------------------
    # Practice sessions
    # ------------------------------------------------------------------

    def start_practice(self, script_id: str) -> dict[str, Any] | None:
        """Start a new practice session for a script."""
        script = self.get_script(script_id)
        if not script:
            return None

        session = PracticeSession(
            script_id=script_id,
            script_title=script["title"],
        )
        self._sessions.append(session)
        self._save_db()
        self.log("practice_started", details={
            "session_id": session.session_id,
            "script": script["title"],
        })
        self._log_to_guardian("practice_started", event_data={
            "script_id": script_id, "script_title": script["title"],
        }, session_context={"session_id": session.session_id})
        return asdict(session)

    def complete_practice(
        self,
        session_id: str,
        duration_seconds: int,
        self_rating: int,
        notes: str = "",
    ) -> dict[str, Any] | None:
        """Complete a practice session with self-assessment."""
        for session in self._sessions:
            if session.session_id == session_id:
                session.completed = True
                session.completed_at = datetime.now(timezone.utc).isoformat()
                session.duration_seconds = duration_seconds
                session.self_rating = max(1, min(5, self_rating))
                session.notes = notes

                # Get AI feedback if available
                if self.ai_enabled:
                    script = self.get_script(session.script_id)
                    feedback = self._get_practice_feedback(session, script)
                    session.ai_feedback = feedback.get("feedback", "")
                    session.areas_of_strength = feedback.get("strengths", [])
                    session.areas_to_improve = feedback.get("improvements", [])

                self._save_db()
                self.log("practice_completed", details={
                    "session_id": session_id,
                    "rating": session.self_rating,
                    "duration": duration_seconds,
                })
                self._log_to_guardian("practice_completed", event_data={
                    "script_id": session.script_id,
                    "duration_seconds": duration_seconds,
                    "self_rating": session.self_rating,
                }, session_context={"session_id": session_id})
                return asdict(session)
        return None

    def get_sessions(
        self,
        script_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get practice sessions, optionally filtered by script."""
        sessions = self._sessions
        if script_id:
            sessions = [s for s in sessions if s.script_id == script_id]
        # Most recent first
        sessions = sorted(sessions, key=lambda s: s.started_at, reverse=True)
        return [asdict(s) for s in sessions[:limit]]

    def practice_stats(self) -> dict[str, Any]:
        """Compute practice statistics."""
        completed = [s for s in self._sessions if s.completed]
        ratings = [s.self_rating for s in completed if s.self_rating > 0]

        # Sessions this week
        now = datetime.now(timezone.utc)
        week_ago = now.timestamp() - 7 * 86400
        this_week = [
            s for s in completed
            if s.completed_at and datetime.fromisoformat(s.completed_at).timestamp() > week_ago
        ]

        # Category breakdown
        category_counts: dict[str, int] = {}
        for s in completed:
            script = self.get_script(s.script_id)
            if script:
                cat = script.get("category", "general")
                category_counts[cat] = category_counts.get(cat, 0) + 1

        return {
            "total_sessions": len(completed),
            "average_rating": sum(ratings) / len(ratings) if ratings else 0.0,
            "best_rating": max(ratings) if ratings else 0,
            "total_practice_minutes": sum(s.duration_seconds for s in completed) / 60,
            "sessions_this_week": len(this_week),
            "categories_practiced": category_counts,
        }

    # ------------------------------------------------------------------
    # AI Advisory
    # ------------------------------------------------------------------

    def get_advisory(self, scenario: str, context: str = "") -> dict[str, Any]:
        """Get AI advisory on how to better interact with a patient."""
        prompt = (
            f"As a patient communication advisor for a telehospitalist, provide specific, "
            f"actionable advice for the following scenario:\n\n"
            f"Scenario: {scenario}\n"
        )
        if context:
            prompt += f"Additional context: {context}\n"

        prompt += (
            f"\nProvide:\n"
            f"1. Key communication strategies (3-5 bullet points)\n"
            f"2. Common pitfalls to avoid\n"
            f"3. Specific phrases or language to use\n"
            f"4. Cultural sensitivity considerations\n"
            f"5. Telehealth-specific tips (camera positioning, pace, etc.)\n\n"
            f"Be practical and evidence-based. Reference frameworks like SPIKES, "
            f"NURSE (Name, Understand, Respect, Support, Explore), or motivational "
            f"interviewing where relevant."
        )

        response = self.think(prompt, context={"scenario": scenario})

        tip = AdvisoryTip(
            category="advisory",
            content=response.content if response.success else "[AI unavailable]",
            scenario=scenario,
        )
        self._tips.append(tip)
        self._save_db()
        self._log_to_guardian("advisory_requested", event_data={
            "tip_id": tip.tip_id, "scenario": scenario,
        })

        return {
            "tip_id": tip.tip_id,
            "advice": tip.content,
            "scenario": scenario,
            "ai_provider": response.provider,
        }

    def get_tips(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent advisory tips."""
        tips = sorted(self._tips, key=lambda t: t.created_at, reverse=True)
        return [asdict(t) for t in tips[:limit]]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_daily_tip(self) -> AdvisoryTip | None:
        """Generate a daily advisory tip using AI."""
        prompt = (
            "Generate a single, practical communication tip for a telehospitalist doctor. "
            "Focus on one of these areas: empathy, clarity, pacing, cultural sensitivity, "
            "telehealth presence, or building rapport over video. "
            "Keep it to 2-3 sentences. Be specific and actionable."
        )
        response = self.think(prompt)
        if not response.success:
            return None

        tip = AdvisoryTip(
            category="daily_tip",
            content=response.content,
            scenario="Daily practice tip",
        )
        self._tips.append(tip)
        self._save_db()
        return tip

    def _get_practice_feedback(
        self,
        session: PracticeSession,
        script: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Generate AI feedback for a completed practice session."""
        prompt = (
            f"A telehospitalist doctor just completed a practice session:\n\n"
            f"Script: {session.script_title}\n"
            f"Duration: {session.duration_seconds} seconds\n"
            f"Self-rating: {session.self_rating}/5\n"
            f"Notes: {session.notes or 'None'}\n\n"
        )
        if script:
            prompt += f"Script category: {script.get('category', 'general')}\n"

        prompt += (
            "\nBased on this, provide:\n"
            "1. Brief encouraging feedback (2-3 sentences)\n"
            "2. 2-3 areas of likely strength\n"
            "3. 2-3 areas to improve\n\n"
            "Format as JSON: {\"feedback\": \"...\", \"strengths\": [...], \"improvements\": [...]}"
        )

        response = self.think(prompt)
        if not response.success:
            return {
                "feedback": "Great effort! Keep practicing regularly.",
                "strengths": ["Commitment to practice"],
                "improvements": ["Continue building confidence"],
            }

        try:
            # Try to parse JSON from response
            text = response.content.strip()
            # Find JSON in the response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except (json.JSONDecodeError, ValueError):
            pass

        return {
            "feedback": response.content[:300],
            "strengths": ["Active practice engagement"],
            "improvements": ["Continue refining communication skills"],
        }

    def _seed_defaults(self) -> None:
        """Seed the database with default clinical scripts."""
        for data in DEFAULT_SCRIPTS:
            script = Script(
                title=data["title"],
                category=data["category"],
                scenario=data["scenario"],
                content=data["content"],
                tags=data.get("tags", []),
            )
            self._scripts.append(script)
        self._save_db()
        self.log("defaults_seeded", details={"count": len(DEFAULT_SCRIPTS)})

    # ------------------------------------------------------------------
    # Guardian One activity logging (now backed by SQLite)
    # ------------------------------------------------------------------

    def _log_to_guardian(
        self,
        event_type: str,
        event_data: dict[str, Any] | None = None,
        session_context: dict[str, Any] | None = None,
    ) -> None:
        """Write a detailed activity log entry to the SQLite database.

        Also appends to data/teleprompter_activity.log for backward compat.
        """
        # Write to SQLite
        try:
            self._db.log_activity(event_type, event_data, session_context)
        except Exception:
            pass

        # Backward-compat: also append to JSONL file
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "event_data": event_data or {},
        }
        if session_context:
            entry["session_context"] = session_context

        log_path = self._data_dir / "teleprompter_activity.log"
        try:
            with open(log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass

    def get_activity_log(self, limit: int = 100) -> list[dict[str, Any]]:
        """Read recent activity log entries from SQLite (most recent first)."""
        try:
            return self._db.get_activity_log(limit=limit)
        except Exception:
            pass

        # Fallback: read from JSONL file
        log_path = self._data_dir / "teleprompter_activity.log"
        if not log_path.exists():
            return []

        entries: list[dict[str, Any]] = []
        try:
            with open(log_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []

        return list(reversed(entries[-limit:]))

    # ------------------------------------------------------------------
    # Persistence (SQLite primary, JSON backup for backward compat)
    # ------------------------------------------------------------------

    def _load_db(self) -> None:
        """Load teleprompter data.

        Priority: SQLite first, then fall back to legacy JSON.
        """
        # Try loading from SQLite first
        if self._sqlite_path.exists() and self._db.script_count() > 0:
            self._load_from_sqlite()
            return

        # Fall back to legacy JSON
        if not self._db_path.exists():
            return

        try:
            raw = json.loads(self._db_path.read_text())
            self._scripts = [Script(**s) for s in raw.get("scripts", [])]
            self._sessions = [PracticeSession(**s) for s in raw.get("sessions", [])]
            self._tips = [AdvisoryTip(**t) for t in raw.get("tips", [])]
            self.log("db_loaded_from_json", details={
                "scripts": len(self._scripts),
                "sessions": len(self._sessions),
            })
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            self.log("db_load_error", severity=Severity.WARNING,
                     details={"error": str(exc)})

    def _load_from_sqlite(self) -> None:
        """Load in-memory lists from SQLite."""
        scripts = self._db.list_scripts()
        self._scripts = [Script(**s) for s in scripts]

        sessions = self._db.list_sessions(limit=10000)
        self._sessions = [PracticeSession(**s) for s in sessions]

        tips = self._db.list_tips(limit=10000)
        self._tips = [AdvisoryTip(**t) for t in tips]

        self.log("db_loaded_from_sqlite", details={
            "scripts": len(self._scripts),
            "sessions": len(self._sessions),
            "tips": len(self._tips),
        })

    def _sync_to_sqlite(self) -> None:
        """Sync in-memory data to SQLite (used after seed or JSON load)."""
        try:
            for s in self._scripts:
                self._db.insert_script(asdict(s))
            for s in self._sessions:
                self._db.insert_session(asdict(s))
            for t in self._tips:
                self._db.insert_tip(asdict(t))
        except Exception as exc:
            self.log("sqlite_sync_error", severity=Severity.WARNING,
                     details={"error": str(exc)})

    def _save_db(self) -> None:
        """Persist teleprompter data to both SQLite and JSON."""
        # Write to SQLite (primary)
        self._sync_to_sqlite()

        # Write JSON backup (backward compat with other Guardian One tools)
        data = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "scripts": [asdict(s) for s in self._scripts],
            "sessions": [asdict(s) for s in self._sessions],
            "tips": [asdict(t) for t in self._tips],
        }
        self._db_path.write_text(json.dumps(data, indent=2))
        self._write_summary()

    def _write_summary(self) -> None:
        """Write a summary file readable by other Guardian One agents."""
        try:
            summary = self._db.export_summary()
        except Exception:
            # Fallback: compute from in-memory
            completed = [s for s in self._sessions if s.completed]
            ratings = [s.self_rating for s in completed if s.self_rating > 0]
            summary = {
                "total_scripts": len(self._scripts),
                "total_sessions": len(completed),
                "total_practice_minutes": round(
                    sum(s.duration_seconds for s in completed) / 60, 2
                ),
                "average_rating": round(
                    sum(ratings) / len(ratings), 2
                ) if ratings else 0.0,
                "last_activity": "",
                "categories_breakdown": {},
            }

        summary_path = self._data_dir / "teleprompter_summary.json"
        try:
            summary_path.write_text(json.dumps(summary, indent=2))
        except OSError:
            pass
