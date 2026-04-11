"""Verification Operating Protocol (VOP v2.1) — evidence-gated output engine.

Converts all LLM responses into evidence-gated outputs, prevents unverified
external claims, and enforces conversation continuity ("IM BACK" handshake).

Architecture mapping (dual-agent enforcement):
    Generator  → AI Engine (LLM)         — produces claims
    Verifier   → VARYS (Archivist)       — checks via APIs/tools
    Arbiter    → ORaCLE (this module)     — blocks unverified output

Nine-step protocol:
    1. Claim Classification   (INTERNAL | LOCAL | REMOTE | INFERRED)
    2. Verification Logic     (tool-based, artifact-based, memory-based)
    3. Output Gating          (fail-closed — UNVERIFIED = blocked)
    4. Output Format          (compressed [C][E][V][CF] schema)
    5. Anti-Hallucination     (pre-output external-validation check)
    6. Multi-Claim Handling   (independent processing, dependency blocking)
    7. Memory Consistency     (session re-verification of prior claims)
    8. Performance Mode       (compressed schema, no narrative)
    9. Escalation Flag        (repeated failures → system limitation)
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from guardian_one.core.audit import AuditLog, Severity


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ClaimType(Enum):
    """Step 1 — how the claim was derived."""
    INTERNAL = "internal"    # Derived from current conversation only
    LOCAL = "local"          # Requires user device/system access
    REMOTE = "remote"        # Requires external source (web/API/database)
    INFERRED = "inferred"    # Logical synthesis without direct evidence


class VerificationStatus(Enum):
    """Step 2/3 — outcome of verification."""
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    INFERRED = "INFERRED"


class Confidence(Enum):
    """Confidence level attached to each claim."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Claim:
    """A single factual assertion extracted from an LLM response."""
    text: str
    claim_type: ClaimType
    evidence: str = ""
    source: str = ""
    depends_on: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        """Short stable identifier (first 8 chars of hash)."""
        import hashlib
        return hashlib.sha256(self.text.encode()).hexdigest()[:8]


@dataclass
class VerifiedClaim:
    """A claim after passing through the verification pipeline."""
    claim: Claim
    status: VerificationStatus
    confidence: Confidence
    evidence: str = ""
    verification_method: str = ""
    blocked: bool = False
    block_reason: str = ""

    def to_compact(self) -> str:
        """Step 4 — compressed [C][E][V][CF] output."""
        lines = [
            f"[C]\n{self.claim.text}",
            f"\n[E]\n{self.evidence or 'none'}",
            f"\n[V]\n{self.status.value}",
            f"\n[CF]\n{self.confidence.value}",
        ]
        if self.blocked:
            lines.append(f"\n[BLOCKED]\n{self.block_reason}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim.text,
            "type": self.claim.claim_type.value,
            "status": self.status.value,
            "confidence": self.confidence.value,
            "evidence": self.evidence,
            "verification_method": self.verification_method,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
        }


@dataclass
class VOPResult:
    """Complete result of a VOP verification pass."""
    claims: list[VerifiedClaim] = field(default_factory=list)
    all_verified: bool = False
    blocked_count: int = 0
    escalation: bool = False
    escalation_message: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_compact(self) -> str:
        """Full compressed output for all claims."""
        parts: list[str] = []
        for vc in self.claims:
            if vc.blocked:
                parts.append(f"[C]\n{vc.claim.text}\n\n[V]\nUNVERIFIED — NO EVIDENCE")
            else:
                parts.append(vc.to_compact())
        if self.escalation:
            parts.append(
                f"\n{self.escalation_message}"
            )
        return "\n\n---\n\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claims": [c.to_dict() for c in self.claims],
            "all_verified": self.all_verified,
            "blocked_count": self.blocked_count,
            "escalation": self.escalation,
            "escalation_message": self.escalation_message,
            "timestamp": self.timestamp,
        }

    @property
    def passed(self) -> bool:
        """True if all claims passed gating (none blocked)."""
        return self.blocked_count == 0


# ---------------------------------------------------------------------------
# Verification tools — pluggable verifiers
# ---------------------------------------------------------------------------

VerifierFn = Callable[[Claim], tuple[bool, str]]
"""Signature: (claim) -> (verified: bool, evidence: str)"""


# ---------------------------------------------------------------------------
# Classification heuristics
# ---------------------------------------------------------------------------

# Keywords that signal a claim needs external verification
_REMOTE_SIGNALS = frozenset({
    "according to", "reports say", "studies show", "research indicates",
    "the latest", "currently", "as of", "was released", "is available",
    "announced", "published", "launched", "updated to version",
    "stock price", "market cap", "revenue", "net worth",
    "github.com", "arxiv.org", "wikipedia", "http://", "https://",
})

_LOCAL_SIGNALS = frozenset({
    "on your machine", "local file", "your system", "installed",
    "disk space", "running process", "your device", "your network",
    "localhost", "your browser", "your terminal",
})

_INFERRED_SIGNALS = frozenset({
    "likely", "probably", "suggests", "implies", "appears to",
    "might", "could", "may", "seems", "possibly",
    "in theory", "hypothetically", "based on patterns",
})


def classify_claim(text: str) -> ClaimType:
    """Step 1 — heuristic claim classification.

    Scans the claim text for signal words/phrases to determine whether
    the claim is INTERNAL, LOCAL, REMOTE, or INFERRED.
    """
    lower = text.lower()

    # Check REMOTE first (strongest verification requirement)
    for signal in _REMOTE_SIGNALS:
        if signal in lower:
            return ClaimType.REMOTE

    # Check LOCAL
    for signal in _LOCAL_SIGNALS:
        if signal in lower:
            return ClaimType.LOCAL

    # Check INFERRED
    for signal in _INFERRED_SIGNALS:
        if signal in lower:
            return ClaimType.INFERRED

    # Default: derived from conversation context
    return ClaimType.INTERNAL


def assess_confidence(claim: Claim, verified: bool, evidence: str) -> Confidence:
    """Determine confidence level based on claim type and verification outcome."""
    if not verified:
        return Confidence.LOW

    if claim.claim_type == ClaimType.INTERNAL:
        return Confidence.HIGH
    if claim.claim_type == ClaimType.LOCAL and evidence:
        return Confidence.HIGH
    if claim.claim_type == ClaimType.REMOTE and evidence:
        return Confidence.MEDIUM  # External sources can change
    if claim.claim_type == ClaimType.INFERRED:
        return Confidence.MEDIUM

    return Confidence.MEDIUM


# ---------------------------------------------------------------------------
# VOP Engine — the ORaCLE arbiter
# ---------------------------------------------------------------------------

# Escalation threshold: if this many consecutive claims fail verification,
# the engine flags a system limitation.
_ESCALATION_THRESHOLD = 3

_ESCALATION_MESSAGE = (
    "SYSTEM LIMITATION: VERIFICATION NOT POSSIBLE WITH CURRENT ACCESS"
)

_CONTINUITY_RESPONSE = "IM BACK"


class VOPEngine:
    """Verification Operating Protocol v2.1 — deterministic, fail-closed.

    This is the ORaCLE arbiter.  Every claim produced by the Generator (LLM)
    passes through classify → verify → gate before reaching the user.

    Usage:
        vop = VOPEngine(audit=audit_log)
        vop.register_verifier("web", my_web_checker)
        result = vop.process([
            Claim(text="Python 3.13 was released", claim_type=ClaimType.REMOTE),
        ])
        print(result.to_compact())
    """

    def __init__(
        self,
        audit: AuditLog | None = None,
        fail_closed: bool = True,
        performance_mode: bool = True,
    ) -> None:
        self._audit = audit
        self._fail_closed = fail_closed
        self._performance_mode = performance_mode
        self._verifiers: dict[str, VerifierFn] = {}
        self._session_claims: dict[str, VerifiedClaim] = {}
        self._consecutive_failures: int = 0
        self._total_processed: int = 0
        self._total_blocked: int = 0
        self._total_verified: int = 0
        self._lock = threading.Lock()
        self._interrupted: bool = False

    # ------------------------------------------------------------------
    # Verifier registration
    # ------------------------------------------------------------------

    def register_verifier(self, name: str, fn: VerifierFn) -> None:
        """Register a verification function (e.g., web lookup, file check)."""
        self._verifiers[name] = fn

    def unregister_verifier(self, name: str) -> bool:
        return self._verifiers.pop(name, None) is not None

    @property
    def available_verifiers(self) -> list[str]:
        return list(self._verifiers.keys())

    # ------------------------------------------------------------------
    # Continuity rule
    # ------------------------------------------------------------------

    def mark_interrupted(self) -> None:
        """Mark the session as interrupted (for continuity handshake)."""
        self._interrupted = True

    def continuity_check(self) -> str | None:
        """If interrupted, return the IM BACK handshake and clear the flag."""
        if self._interrupted:
            self._interrupted = False
            return _CONTINUITY_RESPONSE
        return None

    # ------------------------------------------------------------------
    # Step 1 — Claim classification (delegate to module-level function)
    # ------------------------------------------------------------------

    @staticmethod
    def classify(text: str) -> ClaimType:
        return classify_claim(text)

    # ------------------------------------------------------------------
    # Step 2 — Verification logic
    # ------------------------------------------------------------------

    def _verify_claim(self, claim: Claim) -> tuple[bool, str, str]:
        """Attempt to verify a single claim.

        Returns:
            (verified, evidence, method)
        """
        if claim.claim_type == ClaimType.INTERNAL:
            # Verify against conversation memory (session claims)
            if claim.evidence:
                return True, claim.evidence, "internal_evidence"
            # Internal claims from the conversation are accepted if coherent
            return True, "derived from conversation context", "internal_memory"

        if claim.claim_type == ClaimType.LOCAL:
            # Requires user-provided artifact
            if claim.evidence:
                return True, claim.evidence, "local_artifact"
            # No artifact → unverified
            return False, "", "local_no_artifact"

        if claim.claim_type == ClaimType.REMOTE:
            # Must verify via tool
            if claim.evidence and claim.source:
                return True, f"{claim.evidence} (source: {claim.source})", "remote_provided"
            # Try registered verifiers
            for name, verifier in self._verifiers.items():
                try:
                    verified, evidence = verifier(claim)
                    if verified:
                        return True, evidence, f"verifier:{name}"
                except Exception:
                    continue
            # No tool used or all failed
            return False, "", "remote_no_tool"

        if claim.claim_type == ClaimType.INFERRED:
            # Mark as INFERRED (not FACT) — always passes but with INFERRED status
            return True, claim.evidence or "logical inference", "inference"

        return False, "", "unknown_type"

    # ------------------------------------------------------------------
    # Step 3 — Output gating (hard rule)
    # ------------------------------------------------------------------

    def _gate_claim(self, claim: Claim, verified: bool, evidence: str) -> VerifiedClaim:
        """Apply fail-closed gating to a verified/unverified claim."""
        if claim.claim_type == ClaimType.INFERRED:
            status = VerificationStatus.INFERRED
            confidence = Confidence.MEDIUM
            blocked = False
            block_reason = ""
        elif verified:
            status = VerificationStatus.VERIFIED
            confidence = assess_confidence(claim, verified, evidence)
            blocked = False
            block_reason = ""
        else:
            status = VerificationStatus.UNVERIFIED
            confidence = Confidence.LOW
            if self._fail_closed:
                blocked = True
                block_reason = "UNVERIFIED — NO EVIDENCE"
            else:
                blocked = False
                block_reason = ""

        return VerifiedClaim(
            claim=claim,
            status=status,
            confidence=confidence,
            evidence=evidence,
            blocked=blocked,
            block_reason=block_reason,
        )

    # ------------------------------------------------------------------
    # Step 5 — Anti-hallucination guard
    # ------------------------------------------------------------------

    def _anti_hallucination_check(self, claim: Claim) -> bool:
        """Pre-output check: does this claim require external validation?

        Returns True if the claim passes (no external validation needed,
        or external validation was provided).  If verifiers are registered
        for REMOTE claims, the check defers to the verification step.
        """
        if claim.claim_type == ClaimType.REMOTE:
            # If verifiers are registered, defer to Step 2 verification
            if self._verifiers:
                return True
            # Otherwise, require the same remote-provided fields as Step 2
            return bool(claim.evidence and claim.source)
        if claim.claim_type == ClaimType.LOCAL:
            return bool(claim.evidence)
        return True

    # ------------------------------------------------------------------
    # Step 6 — Multi-claim handling
    # ------------------------------------------------------------------

    def process(self, claims: list[Claim]) -> VOPResult:
        """Process a batch of claims through the full VOP pipeline.

        Each claim is classified, verified, and gated independently.
        If a critical claim fails, dependent conclusions are blocked.
        """
        verified_claims: list[VerifiedClaim] = []
        blocked_count = 0
        failed_ids: set[str] = set()

        for claim in claims:
            # Step 5: anti-hallucination pre-check
            if not self._anti_hallucination_check(claim) and self._fail_closed:
                vc = VerifiedClaim(
                    claim=claim,
                    status=VerificationStatus.UNVERIFIED,
                    confidence=Confidence.LOW,
                    blocked=True,
                    block_reason="UNVERIFIED — NO EVIDENCE",
                    verification_method="anti_hallucination_guard",
                )
                verified_claims.append(vc)
                blocked_count += 1
                failed_ids.add(claim.id)
                continue

            # Step 6: check dependencies — block if any dependency failed
            if claim.depends_on:
                dep_failed = any(dep in failed_ids for dep in claim.depends_on)
                if dep_failed:
                    vc = VerifiedClaim(
                        claim=claim,
                        status=VerificationStatus.UNVERIFIED,
                        confidence=Confidence.LOW,
                        blocked=True,
                        block_reason="BLOCKED — dependent claim failed verification",
                        verification_method="dependency_block",
                    )
                    verified_claims.append(vc)
                    blocked_count += 1
                    failed_ids.add(claim.id)
                    continue

            # Step 2: verify
            verified, evidence, method = self._verify_claim(claim)

            # Step 3: gate
            vc = self._gate_claim(claim, verified, evidence)
            vc.verification_method = method
            verified_claims.append(vc)

            if vc.blocked:
                blocked_count += 1
                failed_ids.add(claim.id)

        # Step 7: update session memory
        with self._lock:
            for vc in verified_claims:
                self._session_claims[vc.claim.id] = vc

            # Track stats
            self._total_processed += len(claims)
            self._total_blocked += blocked_count
            self._total_verified += len(claims) - blocked_count

            # Step 9: escalation check
            if blocked_count > 0:
                self._consecutive_failures += blocked_count
            else:
                self._consecutive_failures = 0

        escalation = self._consecutive_failures >= _ESCALATION_THRESHOLD
        escalation_msg = _ESCALATION_MESSAGE if escalation else ""

        result = VOPResult(
            claims=verified_claims,
            all_verified=(blocked_count == 0),
            blocked_count=blocked_count,
            escalation=escalation,
            escalation_message=escalation_msg,
        )

        # Audit
        if self._audit:
            from guardian_one.core.audit import Severity
            self._audit.record(
                agent="vop_oracle",
                action="verification_pass",
                severity=Severity.INFO if result.passed else Severity.WARNING,
                details={
                    "total_claims": len(claims),
                    "blocked": blocked_count,
                    "verified": len(claims) - blocked_count,
                    "escalation": escalation,
                    "fail_closed": self._fail_closed,
                },
            )

        return result

    # ------------------------------------------------------------------
    # Step 7 — Conversation memory consistency
    # ------------------------------------------------------------------

    def reverify_session(self) -> VOPResult:
        """Re-verify all claims in the current session.

        Prior claims are treated as UNVERIFIED unless evidence is
        still present or they are re-verified.
        """
        claims = [vc.claim for vc in self._session_claims.values()]
        # Clear session so re-processing starts fresh
        with self._lock:
            self._session_claims.clear()
        return self.process(claims)

    def get_session_claim(self, claim_id: str) -> VerifiedClaim | None:
        """Look up a previously verified claim by ID."""
        return self._session_claims.get(claim_id)

    def clear_session(self) -> None:
        """Clear all session memory (e.g., on new conversation)."""
        with self._lock:
            self._session_claims.clear()
            self._consecutive_failures = 0

    # ------------------------------------------------------------------
    # Step 8 — Performance mode helpers
    # ------------------------------------------------------------------

    def format_result(self, result: VOPResult, verbose: bool = False) -> str:
        """Format a VOPResult for output.

        In performance mode (default), uses compressed schema only.
        In verbose mode, adds narrative explanations.
        """
        if self._performance_mode and not verbose:
            return result.to_compact()

        # Verbose output
        lines: list[str] = []
        for vc in result.claims:
            lines.append(vc.to_compact())
            if verbose:
                lines.append(f"  Method: {vc.verification_method}")
                lines.append(f"  Type: {vc.claim.claim_type.value}")
            lines.append("")

        if result.escalation:
            lines.append(result.escalation_message)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Status / metrics
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Engine status for monitoring."""
        return {
            "protocol": "VOP v2.1",
            "fail_closed": self._fail_closed,
            "performance_mode": self._performance_mode,
            "verifiers": list(self._verifiers.keys()),
            "session_claims": len(self._session_claims),
            "consecutive_failures": self._consecutive_failures,
            "escalation_threshold": _ESCALATION_THRESHOLD,
            "stats": {
                "total_processed": self._total_processed,
                "total_verified": self._total_verified,
                "total_blocked": self._total_blocked,
                "verification_rate": (
                    round(self._total_verified / self._total_processed * 100, 1)
                    if self._total_processed > 0 else 0.0
                ),
            },
        }

    def reset_stats(self) -> None:
        """Reset all counters (for testing or new session)."""
        with self._lock:
            self._total_processed = 0
            self._total_verified = 0
            self._total_blocked = 0
            self._consecutive_failures = 0


# ---------------------------------------------------------------------------
# Convenience: extract claims from raw LLM text
# ---------------------------------------------------------------------------

def extract_claims(text: str) -> list[Claim]:
    """Extract individual factual claims from LLM output text.

    Simple sentence-level splitter.  Each non-trivial sentence is treated
    as a potential claim and auto-classified.
    """
    import re
    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    claims: list[Claim] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 10:
            continue
        claim_type = classify_claim(sentence)
        claims.append(Claim(text=sentence, claim_type=claim_type))
    return claims


# ---------------------------------------------------------------------------
# VOP system prompt — injectable into any LLM session
# ---------------------------------------------------------------------------

VOP_SYSTEM_PROMPT = """[ VOP v2.1 — VERIFICATION OPERATING PROTOCOL ]

GLOBAL STATE:
VERIFICATION_MODE = ON
DEFAULT_OUTPUT = STRUCTURED
FAIL_CLOSED = TRUE

CONTINUITY RULE:
If response interrupted or delayed:
    OUTPUT EXACTLY: "IM BACK"
    THEN resume from last completed section

STEP 1 — CLAIM CLASSIFICATION (MANDATORY)
For each claim, classify:
- INTERNAL = derived only from current conversation
- LOCAL = requires user device/system access
- REMOTE = requires external source (web/API/database)
- INFERRED = logical synthesis without direct evidence

STEP 2 — VERIFICATION LOGIC
IF claim == REMOTE: MUST verify via tool, MUST include source or evidence
IF claim == LOCAL: REQUIRE user-provided artifact
IF claim == INTERNAL: VERIFY against conversation memory
IF claim == INFERRED: MARK as INFERRED (NOT FACT)

STEP 3 — OUTPUT GATING (HARD RULE)
IF STATUS == UNVERIFIED: OUTPUT "UNVERIFIED — NO EVIDENCE" and STOP

STEP 4 — OUTPUT FORMAT
[C] <claim> [E] <evidence or "none"> [V] VERIFIED|UNVERIFIED|INFERRED [CF] HIGH|MEDIUM|LOW

STEP 5 — ANTI-HALLUCINATION GUARD
Before final output: if external validation required and not verified → FAIL_CLOSED

STEP 6 — MULTI-CLAIM HANDLING
Process claims independently. If any critical claim fails: block dependent conclusions.

STEP 7 — CONVERSATION MEMORY CONSISTENCY
All prior claims treated as UNVERIFIED unless evidence present OR re-verified.

STEP 8 — PERFORMANCE MODE
Compressed schema only. No narrative unless requested.

STEP 9 — ESCALATION FLAG
If repeated UNVERIFIED failures:
"SYSTEM LIMITATION: VERIFICATION NOT POSSIBLE WITH CURRENT ACCESS"

END PROTOCOL"""


# ---------------------------------------------------------------------------
# Activation trigger phrase
# ---------------------------------------------------------------------------

VOP_ACTIVATION_PHRASE = (
    "Activate VOP v2.1 — strict verification, fail closed, compressed output"
)
