"""Input Stream Processor — transforms raw keystroke data into contextual blocks.

Receives batched keystroke payloads from phone (Android IME / iOS keyboard extension),
processes them into structured context blocks, classifies by app/intent, strips PHI/PII,
and prepares them for encrypted vault storage.

Data flow:
    Phone (custom keyboard) → encrypted payload → InputStreamProcessor
        → session segmentation → app classification → PHI/PII gate
        → context enrichment → Vault storage → queryable index

Privacy guarantees:
    - All processing is local (no external API calls)
    - PHI/PII patterns are scrubbed before any AI analysis
    - Raw keystrokes are NEVER stored — only processed context blocks
    - Passwords/tokens detected in input are redacted immediately

Storage note:
    Current implementation writes processed session JSON to the output
    directory on local disk (plaintext at the filesystem layer — rely on
    OS/disk encryption). Vault-backed encryption for these session files
    is planned but not yet wired; see InputCortex agent for roadmap.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


# ─── Classification ──────────────────────────────────────────────────────────

class BatchResult(Enum):
    """Why process_batch returned None (or a block)."""
    STORED = "stored"               # block created and added to session
    CREDENTIAL_REDACTED = "credential_redacted"  # entire batch blocked
    TOO_SHORT = "too_short"         # below min_words_to_store after scrub


class InputCategory(Enum):
    """What type of activity the keystroke block represents."""
    SEARCH = "search"                # Search queries (Google, app search bars)
    MESSAGE = "message"              # Chat / SMS / email composition
    NOTE = "note"                    # Notes, journaling, document editing
    COMMAND = "command"              # Terminal / CLI / assistant commands
    CREDENTIAL = "credential"        # Password / token entry (REDACT, never store)
    NAVIGATION = "navigation"        # URLs, app switching
    CODE = "code"                    # Code editing
    FORM = "form"                    # Form filling (sign-ups, medical forms)
    UNKNOWN = "unknown"


class ConfidenceLevel(Enum):
    HIGH = "high"          # ≥85% sure about classification
    MODERATE = "moderate"  # 60-84%
    LOW = "low"            # 40-59%
    UNCERTAIN = "uncertain"  # <40%


# ─── PHI/PII Patterns ────────────────────────────────────────────────────────

# Patterns that MUST be redacted before storage
_PHI_PATTERNS = [
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN-REDACTED]"),
    (re.compile(r"\b\d{9}\b"), "[SSN-REDACTED]"),
    (re.compile(r"\b(?:\d[ -]*?){13,19}\b"), "[CARD-REDACTED]"),
    (re.compile(r"\b[A-Z]{1,2}\d{6,10}\b", re.I), "[MRN-REDACTED]"),
    (re.compile(
        r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"
    ), "[CARD-REDACTED]"),
    (re.compile(r"\b\d{3}[\s.-]?\d{3}[\s.-]?\d{4}\b"), "[PHONE-REDACTED]"),
    (re.compile(
        r"(?i)(?:password|passwd|pwd|token|secret|api.?key|bearer)\s*[:=]\s*\S+"
    ), "[CREDENTIAL-REDACTED]"),
    (re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    ), "[EMAIL-REDACTED]"),
    (re.compile(
        r"\b(?:DOB|date of birth|born)\s*[:=]?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        re.I,
    ), "[DOB-REDACTED]"),
]

# Patterns that indicate credential entry (redact entire block)
_CREDENTIAL_SIGNALS = re.compile(
    r"(?i)(?:password|passwd|pwd|pin|passcode|unlock|2fa|otp|verification.code"
    r"|sign.?in|log.?in|authenticate)",
)


# ─── Data Structures ─────────────────────────────────────────────────────────

@dataclass
class RawKeystrokeBatch:
    """A batch of keystrokes from the phone keyboard.

    The phone sends these in encrypted payloads at configurable intervals.
    """
    device_id: str                   # Hashed device identifier
    app_package: str                 # e.g. "com.google.android.gm"
    app_label: str                   # e.g. "Gmail"
    timestamp_start: str             # ISO-8601 of first keystroke
    timestamp_end: str               # ISO-8601 of last keystroke
    text: str                        # The composed text (NOT individual keys)
    field_hint: str = ""             # Input field hint text (e.g. "Search...")
    input_type: str = ""             # Android InputType or iOS keyboard type
    word_count: int = 0
    session_id: str = ""             # Groups batches in the same typing session


@dataclass
class ContextBlock:
    """A processed, classified, PHI-scrubbed context unit ready for vault."""
    block_id: str
    timestamp: str
    device_id: str
    app_label: str
    app_package: str
    category: str                    # InputCategory value
    confidence: str                  # ConfidenceLevel value
    summary: str                     # One-line summary of what was typed
    processed_text: str              # PHI-scrubbed text
    word_count: int
    session_id: str
    tags: list[str] = field(default_factory=list)
    intent_signals: list[str] = field(default_factory=list)
    redactions_applied: int = 0
    ai_context: str = ""             # AI-enriched context (from local model)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InputSession:
    """Groups multiple context blocks from the same typing session."""
    session_id: str
    device_id: str
    started: str
    ended: str
    blocks: list[ContextBlock] = field(default_factory=list)
    total_words: int = 0
    dominant_category: str = ""
    app_sequence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["block_count"] = len(self.blocks)
        return d


# ─── App Classification Map ──────────────────────────────────────────────────

# Maps app packages to likely input categories
_APP_CATEGORY_MAP: dict[str, InputCategory] = {
    # Messaging
    "com.google.android.apps.messaging": InputCategory.MESSAGE,
    "com.whatsapp": InputCategory.MESSAGE,
    "com.facebook.orca": InputCategory.MESSAGE,
    "org.telegram.messenger": InputCategory.MESSAGE,
    "com.discord": InputCategory.MESSAGE,
    "com.slack": InputCategory.MESSAGE,
    "com.apple.MobileSMS": InputCategory.MESSAGE,
    # Email
    "com.google.android.gm": InputCategory.MESSAGE,
    "com.microsoft.office.outlook": InputCategory.MESSAGE,
    "com.apple.mobilemail": InputCategory.MESSAGE,
    # Search / Browser
    "com.android.chrome": InputCategory.SEARCH,
    "com.google.android.googlequicksearchbox": InputCategory.SEARCH,
    "org.mozilla.firefox": InputCategory.SEARCH,
    "com.apple.mobilesafari": InputCategory.SEARCH,
    "com.brave.browser": InputCategory.SEARCH,
    # Notes
    "com.google.android.keep": InputCategory.NOTE,
    "com.microsoft.office.onenote": InputCategory.NOTE,
    "com.apple.mobilenotes": InputCategory.NOTE,
    "md.obsidian": InputCategory.NOTE,
    "com.notion.id": InputCategory.NOTE,
    # Code
    "com.termux": InputCategory.CODE,
    "com.foxdebug.acodefree": InputCategory.CODE,
    # Navigation
    "com.google.android.apps.maps": InputCategory.NAVIGATION,
    "com.waze": InputCategory.NAVIGATION,
}


# ─── Processor ────────────────────────────────────────────────────────────────

class InputStreamProcessor:
    """Processes raw keystroke batches into classified, PHI-scrubbed context blocks.

    This is the core engine. It does NOT handle network transport or encryption
    — those are handled by the InputCortex agent and phone-side keyboard.

    Usage:
        processor = InputStreamProcessor(output_dir=Path("data/input_cortex"))
        blocks = processor.process_batch(raw_batch)
        processor.flush_session(session_id)  # write to disk
    """

    def __init__(
        self,
        output_dir: Path,
        *,
        min_words_to_store: int = 3,
        session_timeout_seconds: int = 300,
    ) -> None:
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._min_words = min_words_to_store
        self._session_timeout = session_timeout_seconds
        self._sessions: dict[str, InputSession] = {}
        # Tracks monotonic last-update time per session for staleness checks
        self._session_last_update: dict[str, float] = {}
        self._lock = threading.Lock()
        self._block_counter = 0

        # Index file for fast lookups
        self._index_path = output_dir / "cortex_index.jsonl"

    # ── Public API ────────────────────────────────────────────────────────

    def process_batch(
        self, batch: RawKeystrokeBatch
    ) -> tuple[ContextBlock | None, BatchResult]:
        """Process a single keystroke batch into a context block.

        Returns a (block, result) tuple so callers can distinguish
        credential redactions from benign skips (too-short text).
        """
        # Step 1: Detect credential entry — redact entire block
        if self._is_credential_entry(batch):
            self._log_redaction(batch, "credential_detected")
            return None, BatchResult.CREDENTIAL_REDACTED

        # Step 2: Classify the input
        category, confidence = self._classify(batch)

        # Step 3: Scrub PHI/PII
        clean_text, redaction_count = self._scrub_phi(batch.text)

        # Step 4: Skip if too short after scrubbing
        word_count = len(clean_text.split())
        if word_count < self._min_words:
            return None, BatchResult.TOO_SHORT

        # Step 5: Generate summary
        summary = self._summarize(clean_text, category, batch.app_label)

        # Step 6: Extract intent signals
        signals = self._extract_signals(clean_text, category)

        # Step 7: Build tags
        tags = self._build_tags(category, batch.app_label, confidence)

        # Normalize session_id once so the block and session index agree.
        sid = batch.session_id or "default"

        # Step 8: Create context block
        block = ContextBlock(
            block_id=self._next_block_id(),
            timestamp=batch.timestamp_start,
            device_id=batch.device_id,
            app_label=batch.app_label,
            app_package=batch.app_package,
            category=category.value,
            confidence=confidence.value,
            summary=summary,
            processed_text=clean_text,
            word_count=word_count,
            session_id=sid,
            tags=tags,
            intent_signals=signals,
            redactions_applied=redaction_count,
        )

        # Step 9: Add to session
        with self._lock:
            self._add_to_session(block, batch)

        return block, BatchResult.STORED

    def flush_session(self, session_id: str) -> Path | None:
        """Write a completed session to disk and remove from memory."""
        with self._lock:
            session = self._sessions.pop(session_id, None)
            self._session_last_update.pop(session_id, None)

        if session is None or not session.blocks:
            return None

        return self._write_session(session_id, session)

    def _write_session(self, session_id: str, session: InputSession) -> Path | None:
        """Finalize and write a session to disk + index (no lock needed)."""
        # Determine dominant category
        cat_counts: dict[str, int] = {}
        for b in session.blocks:
            cat_counts[b.category] = cat_counts.get(b.category, 0) + 1
        session.dominant_category = max(cat_counts, key=cat_counts.get)  # type: ignore[arg-type]
        session.total_words = sum(b.word_count for b in session.blocks)
        session.app_sequence = [b.app_label for b in session.blocks]

        # Sanitize session_id to prevent path traversal.
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        safe_sid = re.sub(r"[^A-Za-z0-9_-]", "_", session_id[:8]) or "session"
        sid_hash = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12]
        filename = f"session_{ts}_{safe_sid}_{sid_hash}.json"
        path = self._output_dir / filename

        with open(path, "w") as f:
            json.dump(session.to_dict(), f, indent=2)

        # Append to index
        index_entry = {
            "session_id": session_id,
            "file": filename,
            "started": session.started,
            "ended": session.ended,
            "blocks": len(session.blocks),
            "words": session.total_words,
            "category": session.dominant_category,
            "apps": list(dict.fromkeys(session.app_sequence)),
        }
        with open(self._index_path, "a") as f:
            f.write(json.dumps(index_entry) + "\n")

        return path

    def flush_stale_sessions(self) -> list[Path]:
        """Flush sessions idle longer than the configured timeout."""
        now = time.monotonic()
        cutoff = self._session_timeout
        # Pop stale sessions under lock so a concurrent update can't
        # revive a session between the staleness check and the flush.
        stale: dict[str, InputSession] = {}
        with self._lock:
            stale_ids = [
                sid for sid, last in self._session_last_update.items()
                if now - last >= cutoff
            ]
            for sid in stale_ids:
                session = self._sessions.pop(sid, None)
                self._session_last_update.pop(sid, None)
                if session and session.blocks:
                    stale[sid] = session
        # Write to disk outside the lock. On I/O failure, re-insert
        # the session so transient errors don't permanently lose data.
        paths = []
        for sid, session in stale.items():
            try:
                path = self._write_session(sid, session)
                if path:
                    paths.append(path)
            except OSError:
                with self._lock:
                    self._sessions[sid] = session
                    self._session_last_update[sid] = time.monotonic()
        return paths

    def flush_all(self) -> list[Path]:
        """Flush all open sessions to disk."""
        with self._lock:
            session_ids = list(self._sessions.keys())
        paths = []
        for sid in session_ids:
            p = self.flush_session(sid)
            if p:
                paths.append(p)
        return paths

    def get_open_sessions(self) -> list[dict[str, Any]]:
        """Return summary of all open (in-memory) sessions."""
        with self._lock:
            return [
                {
                    "session_id": s.session_id,
                    "blocks": len(s.blocks),
                    "words": s.total_words,
                    "started": s.started,
                    "apps": list(dict.fromkeys(s.app_sequence)),
                }
                for s in self._sessions.values()
            ]

    def query_index(
        self,
        *,
        category: str | None = None,
        app: str | None = None,
        since: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query the session index for matching entries."""
        if not self._index_path.exists():
            return []

        results = []
        with open(self._index_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue  # skip corrupt lines
                if category and entry.get("category") != category:
                    continue
                if app and app.lower() not in [a.lower() for a in entry.get("apps", [])]:
                    continue
                if since and entry.get("started", "") < since:
                    continue
                results.append(entry)
                if len(results) >= limit:
                    break
        return results

    # ── Classification ────────────────────────────────────────────────────

    def _classify(
        self, batch: RawKeystrokeBatch
    ) -> tuple[InputCategory, ConfidenceLevel]:
        """Classify a keystroke batch by app + content heuristics."""
        # App-based classification (high confidence)
        app_cat = _APP_CATEGORY_MAP.get(batch.app_package)
        if app_cat:
            return app_cat, ConfidenceLevel.HIGH

        # Field hint classification
        hint = batch.field_hint.lower()
        if any(w in hint for w in ("search", "find", "query", "look up")):
            return InputCategory.SEARCH, ConfidenceLevel.HIGH
        if any(w in hint for w in ("message", "reply", "type a message", "compose")):
            return InputCategory.MESSAGE, ConfidenceLevel.HIGH
        if any(w in hint for w in ("password", "passcode", "pin")):
            return InputCategory.CREDENTIAL, ConfidenceLevel.HIGH
        if any(w in hint for w in ("url", "address", "website", "http")):
            return InputCategory.NAVIGATION, ConfidenceLevel.MODERATE

        # Content-based heuristics (lower confidence)
        text = batch.text.lower()
        if text.startswith(("http://", "https://", "www.")):
            return InputCategory.NAVIGATION, ConfidenceLevel.MODERATE
        if any(kw in text for kw in ("def ", "class ", "import ", "function ", "const ", "var ")):
            return InputCategory.CODE, ConfidenceLevel.MODERATE
        if len(batch.text) > 100 and "\n" in batch.text:
            return InputCategory.NOTE, ConfidenceLevel.LOW

        # Short text in unknown app — likely search or command
        if batch.word_count <= 5:
            return InputCategory.SEARCH, ConfidenceLevel.LOW

        return InputCategory.UNKNOWN, ConfidenceLevel.UNCERTAIN

    def _is_credential_entry(self, batch: RawKeystrokeBatch) -> bool:
        """Detect if this batch is a password/credential entry."""
        # Field hint says password
        hint = batch.field_hint.lower()
        if any(w in hint for w in ("password", "passcode", "pin", "secret")):
            return True
        # Android textPassword / textVisiblePassword input type
        if any(t in batch.input_type.lower() for t in ("password", "pin")):
            return True
        # Content contains credential patterns
        if _CREDENTIAL_SIGNALS.search(batch.text):
            # Only if the text is short (actual password entry, not discussion)
            if batch.word_count <= 3:
                return True
        return False

    # ── PHI/PII Scrubbing ─────────────────────────────────────────────────

    def _scrub_phi(self, text: str) -> tuple[str, int]:
        """Remove PHI/PII patterns from text. Returns (clean_text, redaction_count)."""
        count = 0
        for pattern, replacement in _PHI_PATTERNS:
            text, n = pattern.subn(replacement, text)
            count += n
        return text, count

    # ── Summarization ─────────────────────────────────────────────────────

    def _summarize(self, text: str, category: InputCategory, app: str) -> str:
        """Generate a one-line summary of the context block."""
        words = text.split()
        preview = " ".join(words[:12])
        if len(words) > 12:
            preview += "..."

        prefix_map = {
            InputCategory.SEARCH: "Searched",
            InputCategory.MESSAGE: "Composed message",
            InputCategory.NOTE: "Wrote note",
            InputCategory.COMMAND: "Ran command",
            InputCategory.NAVIGATION: "Navigated to",
            InputCategory.CODE: "Edited code",
            InputCategory.FORM: "Filled form",
        }
        prefix = prefix_map.get(category, "Typed")
        return f"{prefix} in {app}: {preview}"

    # ── Signal Extraction ─────────────────────────────────────────────────

    def _extract_signals(
        self, text: str, category: InputCategory
    ) -> list[str]:
        """Extract intent signals from processed text."""
        signals = []
        lower = text.lower()

        # Question detection
        if "?" in text:
            signals.append("question")

        # Action language
        if any(w in lower for w in ("schedule", "remind", "set alarm", "calendar")):
            signals.append("scheduling_intent")
        if any(w in lower for w in ("buy", "order", "purchase", "pay", "venmo")):
            signals.append("financial_intent")
        if any(w in lower for w in ("diagnosis", "treatment", "patient", "dosage", "mg")):
            signals.append("clinical_context")
        if any(w in lower for w in ("deploy", "git", "push", "merge", "build")):
            signals.append("devops_intent")
        if any(w in lower for w in ("meeting", "call", "zoom", "teams")):
            signals.append("meeting_intent")
        if any(w in lower for w in ("todo", "task", "need to", "don't forget")):
            signals.append("task_intent")

        # Urgency
        if any(w in lower for w in ("urgent", "asap", "emergency", "critical", "stat")):
            signals.append("urgency_high")

        return signals

    # ── Tagging ───────────────────────────────────────────────────────────

    def _build_tags(
        self,
        category: InputCategory,
        app_label: str,
        confidence: ConfidenceLevel,
    ) -> list[str]:
        """Build tags per the Guardian One tagging taxonomy."""
        tags = [
            f"#input-{category.value}",
            f"#app-{app_label.lower().replace(' ', '-')}",
            f"#confidence-{confidence.value}",
            "#query-system",
        ]
        return tags

    # ── Session Management ────────────────────────────────────────────────

    def _add_to_session(
        self, block: ContextBlock, batch: RawKeystrokeBatch
    ) -> None:
        """Add a block to its session, creating the session if needed.

        Uses block.session_id (already normalized by process_batch).
        """
        sid = block.session_id
        if sid not in self._sessions:
            self._sessions[sid] = InputSession(
                session_id=sid,
                device_id=batch.device_id,
                started=batch.timestamp_start,
                ended=batch.timestamp_end,
            )
        session = self._sessions[sid]
        session.blocks.append(block)
        session.ended = batch.timestamp_end
        session.total_words += block.word_count
        session.app_sequence.append(block.app_label)
        self._session_last_update[sid] = time.monotonic()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _next_block_id(self) -> str:
        with self._lock:
            self._block_counter += 1
            counter = self._block_counter
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"ICX-{ts}-{counter:04d}"

    def _log_redaction(self, batch: RawKeystrokeBatch, reason: str) -> None:
        """Log that a batch was fully redacted (no content stored)."""
        redaction_log = self._output_dir / "redactions.jsonl"
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "device_id": batch.device_id,
            "app": batch.app_label,
            "reason": reason,
            "word_count": batch.word_count,
            # NO text content stored — just metadata
        }
        with open(redaction_log, "a") as f:
            f.write(json.dumps(entry) + "\n")
