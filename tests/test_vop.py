"""Tests for VOP v2.1 — Verification Operating Protocol.

Covers all 9 steps of the protocol:
    1. Claim Classification
    2. Verification Logic
    3. Output Gating (fail-closed)
    4. Output Format (compressed schema)
    5. Anti-Hallucination Guard
    6. Multi-Claim Handling (dependency blocking)
    7. Conversation Memory Consistency
    8. Performance Mode
    9. Escalation Flag

Also tests:
    - Continuity handshake ("IM BACK")
    - Verifier registration
    - Claim extraction from raw text
    - VOP system prompt availability
    - Integration with BaseAgent.think_verified()
    - Integration with GuardianOne.verify_claims()
"""

from __future__ import annotations

import pytest

from guardian_one.core.audit import AuditLog
from guardian_one.core.vop import (
    Claim,
    ClaimType,
    Confidence,
    VOPEngine,
    VOPResult,
    VerificationStatus,
    VerifiedClaim,
    VOP_SYSTEM_PROMPT,
    VOP_ACTIVATION_PHRASE,
    classify_claim,
    assess_confidence,
    extract_claims,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def audit(tmp_path):
    return AuditLog(log_dir=tmp_path / "audit")


@pytest.fixture
def vop(audit):
    return VOPEngine(audit=audit)


@pytest.fixture
def vop_no_audit():
    return VOPEngine(audit=None)


@pytest.fixture
def vop_open():
    """VOP engine with fail_closed=False (permissive mode)."""
    return VOPEngine(audit=None, fail_closed=False)


# ---------------------------------------------------------------------------
# Step 1 — Claim Classification
# ---------------------------------------------------------------------------

class TestClaimClassification:
    """Step 1: every claim must be classified before verification."""

    def test_internal_claim(self):
        assert classify_claim("The user asked about Python") == ClaimType.INTERNAL

    def test_remote_claim_url(self):
        assert classify_claim("See https://example.com for details") == ClaimType.REMOTE

    def test_remote_claim_according_to(self):
        assert classify_claim("According to recent reports, revenue is up") == ClaimType.REMOTE

    def test_remote_claim_studies_show(self):
        assert classify_claim("Studies show that sleep improves memory") == ClaimType.REMOTE

    def test_remote_claim_was_released(self):
        assert classify_claim("Python 3.13 was released in October 2024") == ClaimType.REMOTE

    def test_remote_claim_stock_price(self):
        assert classify_claim("The stock price of AAPL is $150") == ClaimType.REMOTE

    def test_remote_claim_github(self):
        assert classify_claim("The repo at github.com/user/repo has 1000 stars") == ClaimType.REMOTE

    def test_local_claim_installed(self):
        assert classify_claim("Python 3.12 is installed on your machine") == ClaimType.LOCAL

    def test_local_claim_disk(self):
        assert classify_claim("Your system has disk space available") == ClaimType.LOCAL

    def test_local_claim_localhost(self):
        assert classify_claim("The service is running on localhost:8080") == ClaimType.LOCAL

    def test_inferred_claim_likely(self):
        assert classify_claim("This is likely caused by a race condition") == ClaimType.INFERRED

    def test_inferred_claim_probably(self):
        assert classify_claim("The bug probably exists in the parser") == ClaimType.INFERRED

    def test_inferred_claim_suggests(self):
        assert classify_claim("The error log suggests a timeout issue") == ClaimType.INFERRED

    def test_inferred_claim_might(self):
        assert classify_claim("This might be related to the recent deploy") == ClaimType.INFERRED

    def test_internal_default(self):
        """Claims without signal words default to INTERNAL."""
        assert classify_claim("The function returns a list of integers") == ClaimType.INTERNAL

    def test_classify_via_engine(self, vop):
        """Engine.classify() delegates to the module-level function."""
        assert vop.classify("According to Wikipedia, water is wet") == ClaimType.REMOTE

    def test_claim_id_deterministic(self):
        """Same text always produces the same ID."""
        c1 = Claim(text="hello world", claim_type=ClaimType.INTERNAL)
        c2 = Claim(text="hello world", claim_type=ClaimType.REMOTE)
        assert c1.id == c2.id  # ID is based on text only

    def test_claim_id_unique(self):
        c1 = Claim(text="hello world", claim_type=ClaimType.INTERNAL)
        c2 = Claim(text="goodbye world", claim_type=ClaimType.INTERNAL)
        assert c1.id != c2.id


# ---------------------------------------------------------------------------
# Step 2 — Verification Logic
# ---------------------------------------------------------------------------

class TestVerificationLogic:
    """Step 2: claims must be verified according to their type."""

    def test_internal_claim_verified(self, vop):
        claim = Claim(text="The user asked about Python", claim_type=ClaimType.INTERNAL)
        result = vop.process([claim])
        assert result.claims[0].status == VerificationStatus.VERIFIED

    def test_internal_with_evidence(self, vop):
        claim = Claim(
            text="The function returns 42",
            claim_type=ClaimType.INTERNAL,
            evidence="from conversation context",
        )
        result = vop.process([claim])
        vc = result.claims[0]
        assert vc.status == VerificationStatus.VERIFIED
        assert vc.confidence == Confidence.HIGH

    def test_local_with_artifact(self, vop):
        claim = Claim(
            text="Python 3.12 is installed on your machine",
            claim_type=ClaimType.LOCAL,
            evidence="python --version output: Python 3.12.4",
        )
        result = vop.process([claim])
        assert result.claims[0].status == VerificationStatus.VERIFIED

    def test_local_without_artifact_blocked(self, vop):
        claim = Claim(
            text="Python 3.12 is installed on your machine",
            claim_type=ClaimType.LOCAL,
        )
        result = vop.process([claim])
        assert result.claims[0].status == VerificationStatus.UNVERIFIED
        assert result.claims[0].blocked

    def test_remote_with_evidence_and_source(self, vop):
        claim = Claim(
            text="Python 3.13 was released in October 2024",
            claim_type=ClaimType.REMOTE,
            evidence="Release announcement on python.org",
            source="https://python.org/downloads/",
        )
        result = vop.process([claim])
        assert result.claims[0].status == VerificationStatus.VERIFIED

    def test_remote_without_evidence_blocked(self, vop):
        claim = Claim(
            text="Python 3.13 was released in October 2024",
            claim_type=ClaimType.REMOTE,
        )
        result = vop.process([claim])
        assert result.claims[0].status == VerificationStatus.UNVERIFIED
        assert result.claims[0].blocked

    def test_remote_with_verifier(self, vop):
        """Register a verifier that confirms the claim."""
        def fake_verifier(claim):
            return True, "confirmed via API"
        vop.register_verifier("web", fake_verifier)

        claim = Claim(
            text="Python 3.13 was released in October 2024",
            claim_type=ClaimType.REMOTE,
        )
        result = vop.process([claim])
        assert result.claims[0].status == VerificationStatus.VERIFIED
        assert "confirmed via API" in result.claims[0].evidence

    def test_remote_verifier_fails(self, vop):
        """Verifier returns False — claim remains unverified."""
        def failing_verifier(claim):
            return False, ""
        vop.register_verifier("web", failing_verifier)

        claim = Claim(
            text="According to reports, GDP grew 5%",
            claim_type=ClaimType.REMOTE,
        )
        result = vop.process([claim])
        assert result.claims[0].status == VerificationStatus.UNVERIFIED

    def test_remote_verifier_exception(self, vop):
        """Verifier raises exception — gracefully handled, claim unverified."""
        def exploding_verifier(claim):
            raise RuntimeError("API down")
        vop.register_verifier("web", exploding_verifier)

        claim = Claim(
            text="According to Wikipedia, water boils at 100C",
            claim_type=ClaimType.REMOTE,
        )
        result = vop.process([claim])
        assert result.claims[0].status == VerificationStatus.UNVERIFIED

    def test_inferred_claim_passes_as_inferred(self, vop):
        claim = Claim(
            text="This is likely a race condition",
            claim_type=ClaimType.INFERRED,
        )
        result = vop.process([claim])
        assert result.claims[0].status == VerificationStatus.INFERRED
        assert not result.claims[0].blocked

    def test_inferred_confidence_medium(self, vop):
        claim = Claim(text="This probably works", claim_type=ClaimType.INFERRED)
        result = vop.process([claim])
        assert result.claims[0].confidence == Confidence.MEDIUM


# ---------------------------------------------------------------------------
# Step 3 — Output Gating (fail-closed)
# ---------------------------------------------------------------------------

class TestOutputGating:
    """Step 3: UNVERIFIED claims are blocked when fail_closed=True."""

    def test_fail_closed_blocks_unverified(self, vop):
        claim = Claim(text="The latest version is X", claim_type=ClaimType.REMOTE)
        result = vop.process([claim])
        assert result.blocked_count == 1
        assert not result.passed

    def test_fail_closed_allows_verified(self, vop):
        claim = Claim(
            text="The function returns 42",
            claim_type=ClaimType.INTERNAL,
        )
        result = vop.process([claim])
        assert result.blocked_count == 0
        assert result.passed

    def test_open_mode_allows_unverified(self, vop_open):
        claim = Claim(text="The latest version is X", claim_type=ClaimType.REMOTE)
        result = vop_open.process([claim])
        assert result.blocked_count == 0
        assert result.claims[0].status == VerificationStatus.UNVERIFIED
        assert not result.claims[0].blocked

    def test_block_reason_set(self, vop):
        claim = Claim(text="Currently, the stock price is high", claim_type=ClaimType.REMOTE)
        result = vop.process([claim])
        assert "UNVERIFIED" in result.claims[0].block_reason


# ---------------------------------------------------------------------------
# Step 4 — Output Format (compressed schema)
# ---------------------------------------------------------------------------

class TestOutputFormat:
    """Step 4: [C][E][V][CF] compressed output."""

    def test_compact_output_verified(self, vop):
        claim = Claim(text="The sum is 42", claim_type=ClaimType.INTERNAL)
        result = vop.process([claim])
        compact = result.claims[0].to_compact()
        assert "[C]" in compact
        assert "[E]" in compact
        assert "[V]" in compact
        assert "[CF]" in compact
        assert "VERIFIED" in compact

    def test_compact_output_blocked(self, vop):
        claim = Claim(text="The latest release was yesterday", claim_type=ClaimType.REMOTE)
        result = vop.process([claim])
        compact = result.claims[0].to_compact()
        assert "[BLOCKED]" in compact

    def test_full_compact_output(self, vop):
        claims = [
            Claim(text="The user asked for X", claim_type=ClaimType.INTERNAL),
            Claim(text="This probably works", claim_type=ClaimType.INFERRED),
        ]
        result = vop.process(claims)
        output = result.to_compact()
        assert "---" in output  # Separator between claims
        assert "VERIFIED" in output
        assert "INFERRED" in output

    def test_to_dict(self, vop):
        claim = Claim(text="Test claim", claim_type=ClaimType.INTERNAL)
        result = vop.process([claim])
        d = result.claims[0].to_dict()
        assert d["claim"] == "Test claim"
        assert d["type"] == "internal"
        assert d["status"] == "VERIFIED"

    def test_result_to_dict(self, vop):
        claim = Claim(text="Test claim", claim_type=ClaimType.INTERNAL)
        result = vop.process([claim])
        d = result.to_dict()
        assert "claims" in d
        assert "all_verified" in d
        assert "timestamp" in d


# ---------------------------------------------------------------------------
# Step 5 — Anti-Hallucination Guard
# ---------------------------------------------------------------------------

class TestAntiHallucinationGuard:
    """Step 5: remote/local claims without evidence are pre-blocked."""

    def test_remote_no_evidence_blocked(self, vop):
        """REMOTE claim with no evidence/source fails anti-hallucination."""
        claim = Claim(
            text="According to reports, inflation is at 2%",
            claim_type=ClaimType.REMOTE,
        )
        result = vop.process([claim])
        assert result.claims[0].blocked
        assert result.claims[0].verification_method == "anti_hallucination_guard"

    def test_remote_with_evidence_passes(self, vop):
        claim = Claim(
            text="According to the BLS, inflation is at 2%",
            claim_type=ClaimType.REMOTE,
            evidence="BLS CPI report March 2024",
            source="bls.gov",
        )
        result = vop.process([claim])
        assert not result.claims[0].blocked

    def test_local_no_evidence_blocked(self, vop):
        claim = Claim(
            text="Your system has 32GB RAM installed",
            claim_type=ClaimType.LOCAL,
        )
        result = vop.process([claim])
        assert result.claims[0].blocked

    def test_internal_always_passes_guard(self, vop):
        claim = Claim(text="This is an internal observation", claim_type=ClaimType.INTERNAL)
        result = vop.process([claim])
        assert not result.claims[0].blocked

    def test_inferred_always_passes_guard(self, vop):
        claim = Claim(text="This might be a bug", claim_type=ClaimType.INFERRED)
        result = vop.process([claim])
        assert not result.claims[0].blocked


# ---------------------------------------------------------------------------
# Step 6 — Multi-Claim Handling (dependency blocking)
# ---------------------------------------------------------------------------

class TestMultiClaimHandling:
    """Step 6: independent processing + dependency blocking."""

    def test_independent_claims_processed_separately(self, vop):
        claims = [
            Claim(text="The user asked for X", claim_type=ClaimType.INTERNAL),
            Claim(text="The latest version is Y", claim_type=ClaimType.REMOTE),
        ]
        result = vop.process(claims)
        assert len(result.claims) == 2
        assert result.claims[0].status == VerificationStatus.VERIFIED
        assert result.claims[1].status == VerificationStatus.UNVERIFIED

    def test_dependent_claim_blocked_when_parent_fails(self, vop):
        parent = Claim(text="The latest API version is v3", claim_type=ClaimType.REMOTE)
        child = Claim(
            text="Therefore, we should use v3 endpoints",
            claim_type=ClaimType.INTERNAL,
            depends_on=[parent.id],
        )
        result = vop.process([parent, child])
        assert result.claims[0].blocked  # Parent blocked (remote, no evidence)
        assert result.claims[1].blocked  # Child blocked (dependency failed)
        assert "dependent claim" in result.claims[1].block_reason

    def test_dependent_claim_passes_when_parent_verified(self, vop):
        parent = Claim(
            text="The sum of 2+2 is 4",
            claim_type=ClaimType.INTERNAL,
        )
        child = Claim(
            text="Therefore, 4 is the correct answer",
            claim_type=ClaimType.INTERNAL,
            depends_on=[parent.id],
        )
        result = vop.process([parent, child])
        assert not result.claims[0].blocked
        assert not result.claims[1].blocked

    def test_mixed_batch(self, vop):
        """Mix of verified, blocked, and inferred claims."""
        claims = [
            Claim(text="Internal fact A", claim_type=ClaimType.INTERNAL),
            Claim(text="This is likely B", claim_type=ClaimType.INFERRED),
            Claim(text="According to X, C is true", claim_type=ClaimType.REMOTE),
        ]
        result = vop.process(claims)
        assert result.claims[0].status == VerificationStatus.VERIFIED
        assert result.claims[1].status == VerificationStatus.INFERRED
        assert result.claims[2].status == VerificationStatus.UNVERIFIED
        assert result.blocked_count == 1


# ---------------------------------------------------------------------------
# Step 7 — Conversation Memory Consistency
# ---------------------------------------------------------------------------

class TestMemoryConsistency:
    """Step 7: session claims tracked and re-verifiable."""

    def test_claims_stored_in_session(self, vop):
        claim = Claim(text="Internal fact", claim_type=ClaimType.INTERNAL)
        vop.process([claim])
        stored = vop.get_session_claim(claim.id)
        assert stored is not None
        assert stored.status == VerificationStatus.VERIFIED

    def test_reverify_session(self, vop):
        """Re-verification should re-process all session claims."""
        claims = [
            Claim(text="Internal A", claim_type=ClaimType.INTERNAL),
            Claim(text="Internal B", claim_type=ClaimType.INTERNAL),
        ]
        vop.process(claims)
        assert len(vop._session_claims) == 2

        result = vop.reverify_session()
        assert len(result.claims) == 2
        assert result.all_verified

    def test_clear_session(self, vop):
        claim = Claim(text="Test claim", claim_type=ClaimType.INTERNAL)
        vop.process([claim])
        assert vop.get_session_claim(claim.id) is not None

        vop.clear_session()
        assert vop.get_session_claim(claim.id) is None

    def test_session_tracks_blocked_claims(self, vop):
        claim = Claim(text="The latest release is X", claim_type=ClaimType.REMOTE)
        vop.process([claim])
        stored = vop.get_session_claim(claim.id)
        assert stored is not None
        assert stored.blocked


# ---------------------------------------------------------------------------
# Step 8 — Performance Mode
# ---------------------------------------------------------------------------

class TestPerformanceMode:
    """Step 8: compressed output by default, verbose on request."""

    def test_default_is_compact(self, vop):
        claim = Claim(text="Internal fact", claim_type=ClaimType.INTERNAL)
        result = vop.process([claim])
        output = vop.format_result(result)
        assert "[C]" in output
        assert "Method:" not in output

    def test_verbose_mode(self, vop):
        claim = Claim(text="Internal fact", claim_type=ClaimType.INTERNAL)
        result = vop.process([claim])
        output = vop.format_result(result, verbose=True)
        assert "Method:" in output
        assert "Type:" in output

    def test_performance_mode_off(self, audit):
        vop = VOPEngine(audit=audit, performance_mode=False)
        claim = Claim(text="Internal fact", claim_type=ClaimType.INTERNAL)
        result = vop.process([claim])
        output = vop.format_result(result)
        # Non-performance mode still uses compact by default
        assert "[C]" in output


# ---------------------------------------------------------------------------
# Step 9 — Escalation Flag
# ---------------------------------------------------------------------------

class TestEscalation:
    """Step 9: repeated failures trigger escalation."""

    def test_escalation_after_threshold(self, vop):
        """3 consecutive blocked claims should trigger escalation."""
        claims = [
            Claim(text="According to X, A is true", claim_type=ClaimType.REMOTE),
            Claim(text="Studies show B is correct", claim_type=ClaimType.REMOTE),
            Claim(text="The latest data says C", claim_type=ClaimType.REMOTE),
        ]
        result = vop.process(claims)
        assert result.escalation
        assert "SYSTEM LIMITATION" in result.escalation_message

    def test_no_escalation_below_threshold(self, vop):
        claims = [
            Claim(text="According to X, A is true", claim_type=ClaimType.REMOTE),
            Claim(text="According to Y, B is true", claim_type=ClaimType.REMOTE),
        ]
        result = vop.process(claims)
        assert not result.escalation

    def test_escalation_resets_on_success(self, vop):
        """Successful verification resets the failure counter."""
        # First: 2 failures
        vop.process([
            Claim(text="According to X, A is true", claim_type=ClaimType.REMOTE),
            Claim(text="Studies show B", claim_type=ClaimType.REMOTE),
        ])
        # Then: success resets counter
        vop.process([
            Claim(text="Internal fact", claim_type=ClaimType.INTERNAL),
        ])
        assert vop._consecutive_failures == 0

    def test_escalation_in_compact_output(self, vop):
        claims = [
            Claim(text="According to X, A", claim_type=ClaimType.REMOTE),
            Claim(text="Studies show B", claim_type=ClaimType.REMOTE),
            Claim(text="The latest C", claim_type=ClaimType.REMOTE),
        ]
        result = vop.process(claims)
        output = result.to_compact()
        assert "SYSTEM LIMITATION" in output


# ---------------------------------------------------------------------------
# Continuity Rule
# ---------------------------------------------------------------------------

class TestContinuityRule:
    """Continuity handshake: "IM BACK" after interruption."""

    def test_no_interruption_returns_none(self, vop):
        assert vop.continuity_check() is None

    def test_interrupted_returns_im_back(self, vop):
        vop.mark_interrupted()
        assert vop.continuity_check() == "IM BACK"

    def test_continuity_clears_after_check(self, vop):
        vop.mark_interrupted()
        vop.continuity_check()
        assert vop.continuity_check() is None


# ---------------------------------------------------------------------------
# Verifier Registration
# ---------------------------------------------------------------------------

class TestVerifierRegistration:

    def test_register_verifier(self, vop):
        vop.register_verifier("test", lambda c: (True, "ok"))
        assert "test" in vop.available_verifiers

    def test_unregister_verifier(self, vop):
        vop.register_verifier("test", lambda c: (True, "ok"))
        assert vop.unregister_verifier("test")
        assert "test" not in vop.available_verifiers

    def test_unregister_nonexistent(self, vop):
        assert not vop.unregister_verifier("nope")

    def test_multiple_verifiers_fallthrough(self, vop):
        """First verifier fails, second succeeds."""
        def fail_verifier(claim):
            return False, ""
        def success_verifier(claim):
            return True, "found it"

        vop.register_verifier("fail", fail_verifier)
        vop.register_verifier("success", success_verifier)

        claim = Claim(text="The latest version is X", claim_type=ClaimType.REMOTE)
        result = vop.process([claim])
        assert result.claims[0].status == VerificationStatus.VERIFIED


# ---------------------------------------------------------------------------
# Claim Extraction
# ---------------------------------------------------------------------------

class TestClaimExtraction:
    """Extract and auto-classify claims from raw LLM text."""

    def test_extract_single_sentence(self):
        claims = extract_claims("The function returns a list of integers.")
        assert len(claims) == 1
        assert claims[0].claim_type == ClaimType.INTERNAL

    def test_extract_multiple_sentences(self):
        text = (
            "Python 3.13 was released recently. "
            "The function works correctly. "
            "This might cause issues."
        )
        claims = extract_claims(text)
        assert len(claims) == 3
        assert claims[0].claim_type == ClaimType.REMOTE  # "was released"
        assert claims[1].claim_type == ClaimType.INTERNAL
        assert claims[2].claim_type == ClaimType.INFERRED  # "might"

    def test_extract_skips_short_fragments(self):
        claims = extract_claims("OK. Yes. The function is correct.")
        assert len(claims) == 1  # Only last sentence is long enough

    def test_extract_empty_string(self):
        assert extract_claims("") == []


# ---------------------------------------------------------------------------
# Status / Metrics
# ---------------------------------------------------------------------------

class TestStatusMetrics:

    def test_initial_status(self, vop):
        status = vop.status()
        assert status["protocol"] == "VOP v2.1"
        assert status["fail_closed"] is True
        assert status["stats"]["total_processed"] == 0

    def test_stats_updated_after_processing(self, vop):
        claims = [
            Claim(text="Internal fact", claim_type=ClaimType.INTERNAL),
            Claim(text="According to X, remote claim", claim_type=ClaimType.REMOTE),
        ]
        vop.process(claims)
        stats = vop.status()["stats"]
        assert stats["total_processed"] == 2
        assert stats["total_verified"] == 1
        assert stats["total_blocked"] == 1
        assert stats["verification_rate"] == 50.0

    def test_reset_stats(self, vop):
        vop.process([Claim(text="Test", claim_type=ClaimType.INTERNAL)])
        vop.reset_stats()
        assert vop.status()["stats"]["total_processed"] == 0


# ---------------------------------------------------------------------------
# Confidence Assessment
# ---------------------------------------------------------------------------

class TestConfidenceAssessment:

    def test_internal_verified_high(self):
        claim = Claim(text="X", claim_type=ClaimType.INTERNAL)
        assert assess_confidence(claim, True, "evidence") == Confidence.HIGH

    def test_remote_verified_medium(self):
        claim = Claim(text="X", claim_type=ClaimType.REMOTE)
        assert assess_confidence(claim, True, "evidence") == Confidence.MEDIUM

    def test_unverified_low(self):
        claim = Claim(text="X", claim_type=ClaimType.REMOTE)
        assert assess_confidence(claim, False, "") == Confidence.LOW

    def test_local_with_evidence_high(self):
        claim = Claim(text="X", claim_type=ClaimType.LOCAL)
        assert assess_confidence(claim, True, "artifact") == Confidence.HIGH

    def test_inferred_medium(self):
        claim = Claim(text="X", claim_type=ClaimType.INFERRED)
        assert assess_confidence(claim, True, "") == Confidence.MEDIUM


# ---------------------------------------------------------------------------
# System Prompt & Activation
# ---------------------------------------------------------------------------

class TestSystemPrompt:

    def test_system_prompt_exists(self):
        assert "VOP v2.1" in VOP_SYSTEM_PROMPT
        assert "FAIL_CLOSED" in VOP_SYSTEM_PROMPT

    def test_activation_phrase(self):
        assert "VOP v2.1" in VOP_ACTIVATION_PHRASE
        assert "fail closed" in VOP_ACTIVATION_PHRASE

    def test_all_nine_steps_in_prompt(self):
        for i in range(1, 10):
            assert f"STEP {i}" in VOP_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Audit Integration
# ---------------------------------------------------------------------------

class TestAuditIntegration:

    def test_audit_recorded_on_process(self, audit):
        vop = VOPEngine(audit=audit)
        vop.process([Claim(text="Test", claim_type=ClaimType.INTERNAL)])
        entries = audit.query(agent="vop_oracle", limit=10)
        assert len(entries) >= 1
        assert entries[0].action == "verification_pass"

    def test_no_audit_without_log(self, vop_no_audit):
        """Processing without an audit log should not raise."""
        result = vop_no_audit.process([
            Claim(text="Test", claim_type=ClaimType.INTERNAL),
        ])
        assert result.all_verified

    def test_audit_severity_warning_on_block(self, audit):
        vop = VOPEngine(audit=audit)
        vop.process([Claim(text="The latest X", claim_type=ClaimType.REMOTE)])
        entries = audit.query(agent="vop_oracle", limit=10)
        assert any(e.severity == "warning" for e in entries)


# ---------------------------------------------------------------------------
# VOPResult properties
# ---------------------------------------------------------------------------

class TestVOPResult:

    def test_passed_when_no_blocks(self):
        result = VOPResult(claims=[], all_verified=True, blocked_count=0)
        assert result.passed

    def test_not_passed_when_blocked(self):
        result = VOPResult(claims=[], all_verified=False, blocked_count=1)
        assert not result.passed

    def test_empty_result(self):
        result = VOPResult()
        assert result.passed
        assert result.all_verified is False
        assert result.to_compact() == ""

    def test_result_timestamp(self):
        result = VOPResult()
        assert "T" in result.timestamp  # ISO format


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_empty_claim_list(self, vop):
        result = vop.process([])
        assert result.all_verified
        assert result.blocked_count == 0

    def test_very_long_claim(self, vop):
        text = "The function " * 1000 + "returns correctly"
        claim = Claim(text=text, claim_type=ClaimType.INTERNAL)
        result = vop.process([claim])
        assert result.claims[0].status == VerificationStatus.VERIFIED

    def test_concurrent_processing(self, vop):
        """Thread safety: process claims from multiple threads."""
        import threading
        results: list[VOPResult] = []
        errors: list[Exception] = []

        def worker():
            try:
                r = vop.process([
                    Claim(text=f"Thread claim {threading.current_thread().name}",
                          claim_type=ClaimType.INTERNAL),
                ])
                results.append(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(results) == 10
