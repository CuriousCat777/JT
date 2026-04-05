"""Tests for InputCortex agent + InputStreamProcessor.

Covers the security-critical paths:
- Credential entry is blocked (returns None, never stored)
- PHI/PII patterns are redacted in processed text
- Session flushing writes index entries and session JSON
- Query filters work on the index
- Stale session detection via monotonic timeout
- Auth token enforcement on HTTP listener
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from guardian_one.agents.input_cortex import InputCortex
from guardian_one.core.audit import AuditLog
from guardian_one.core.config import AgentConfig
from guardian_one.integrations.input_stream import (
    BatchResult,
    InputCategory,
    InputStreamProcessor,
    RawKeystrokeBatch,
)


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "cortex"


@pytest.fixture
def processor(tmp_output):
    return InputStreamProcessor(
        tmp_output,
        min_words_to_store=1,
        session_timeout_seconds=1,
    )


def _batch(**overrides) -> RawKeystrokeBatch:
    defaults = dict(
        device_id="test-phone",
        app_package="com.google.android.gm",
        app_label="Gmail",
        timestamp_start="2026-04-05T10:00:00Z",
        timestamp_end="2026-04-05T10:00:30Z",
        text="hello world this is a test message",
        field_hint="Compose email",
        input_type="text",
        word_count=7,
        session_id="sess-1",
    )
    defaults.update(overrides)
    return RawKeystrokeBatch(**defaults)


# ── Credential detection ──────────────────────────────────────────────────

def test_credential_entry_blocked_via_field_hint(processor):
    batch = _batch(
        field_hint="Password",
        input_type="textPassword",
        text="mys3cret!",
        word_count=1,
    )
    block, result = processor.process_batch(batch)
    assert block is None, "password field input must not return a block"
    assert result == BatchResult.CREDENTIAL_REDACTED


def test_credential_entry_blocked_via_input_type(processor):
    batch = _batch(
        field_hint="",
        input_type="textPassword",
        text="token123",
        word_count=1,
    )
    block, result = processor.process_batch(batch)
    assert block is None
    assert result == BatchResult.CREDENTIAL_REDACTED


def test_credential_entry_blocked_via_signal_keywords(processor):
    batch = _batch(
        field_hint="",
        input_type="text",
        text="my pin",
        word_count=2,
    )
    block, result = processor.process_batch(batch)
    assert block is None
    assert result == BatchResult.CREDENTIAL_REDACTED


def test_credential_redaction_logged(processor, tmp_output):
    batch = _batch(field_hint="Password", input_type="textPassword", text="x", word_count=1)
    processor.process_batch(batch)
    redaction_log = tmp_output / "redactions.jsonl"
    assert redaction_log.exists()
    lines = redaction_log.read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["reason"] == "credential_detected"
    # The log must NOT contain the actual password text
    assert "x" not in entry or entry.get("text") is None
    assert "text" not in entry


# ── PHI/PII scrubbing ─────────────────────────────────────────────────────

def test_phi_scrubbing_ssn_and_dob_and_phone(processor):
    batch = _batch(
        text="Patient SSN 123-45-6789 DOB: 01/15/1980 phone 602-810-0527",
        app_package="com.android.chrome",
        app_label="Chrome",
        field_hint="Search",
        word_count=9,
    )
    block, _ = processor.process_batch(batch)
    assert block is not None
    assert "[SSN-REDACTED]" in block.processed_text
    assert "[DOB-REDACTED]" in block.processed_text
    assert "[PHONE-REDACTED]" in block.processed_text
    assert "123-45-6789" not in block.processed_text
    assert "01/15/1980" not in block.processed_text
    assert "602-810-0527" not in block.processed_text
    assert block.redactions_applied >= 3


def test_phi_scrubbing_email_and_card(processor):
    batch = _batch(
        text="Contact jeremy@example.com card 4111 1111 1111 1111 please",
        app_package="com.app.notes",
        app_label="Notes",
        field_hint="",
        word_count=7,
    )
    block, _ = processor.process_batch(batch)
    assert block is not None
    assert "[EMAIL-REDACTED]" in block.processed_text
    assert "[CARD-REDACTED]" in block.processed_text
    assert "jeremy@example.com" not in block.processed_text
    assert "4111" not in block.processed_text


def test_non_sensitive_text_is_unchanged(processor):
    batch = _batch(text="Schedule morning rounds for tomorrow at 7am", word_count=7)
    block, _ = processor.process_batch(batch)
    assert block is not None
    assert block.redactions_applied == 0
    assert "Schedule morning rounds" in block.processed_text


# ── Classification ────────────────────────────────────────────────────────

def test_gmail_classified_as_message(processor):
    batch = _batch(app_package="com.google.android.gm", app_label="Gmail")
    block, _ = processor.process_batch(batch)
    assert block is not None
    assert block.category == InputCategory.MESSAGE.value
    assert block.confidence == "high"
    assert "#app-gmail" in block.tags


def test_chrome_classified_as_search(processor):
    batch = _batch(
        app_package="com.android.chrome",
        app_label="Chrome",
        field_hint="Search",
    )
    block, _ = processor.process_batch(batch)
    assert block is not None
    assert block.category == InputCategory.SEARCH.value


def test_intent_signals_extracted(processor):
    batch = _batch(text="schedule a meeting tomorrow at 3pm", word_count=6)
    block, _ = processor.process_batch(batch)
    assert block is not None
    assert "scheduling_intent" in block.intent_signals
    assert "meeting_intent" in block.intent_signals


def test_urgency_signal_extracted(processor):
    batch = _batch(text="urgent need this STAT please respond", word_count=6)
    block, _ = processor.process_batch(batch)
    assert block is not None
    assert "urgency_high" in block.intent_signals


# ── Session flushing + index ──────────────────────────────────────────────

def test_flush_session_writes_file_and_index(processor, tmp_output):
    processor.process_batch(_batch(session_id="s-flush"))
    path = processor.flush_session("s-flush")
    assert path is not None
    assert path.exists()

    # Session JSON has the right shape
    with open(path) as f:
        data = json.load(f)
    assert data["session_id"] == "s-flush"
    assert data["block_count"] >= 1
    assert data["total_words"] >= 1
    assert data["dominant_category"] == InputCategory.MESSAGE.value

    # Index has an entry
    index_file = tmp_output / "cortex_index.jsonl"
    assert index_file.exists()
    entries = [json.loads(line) for line in index_file.read_text().splitlines() if line]
    assert any(e["session_id"] == "s-flush" for e in entries)


def test_flush_session_clears_from_memory(processor):
    processor.process_batch(_batch(session_id="s-clear"))
    assert any(s["session_id"] == "s-clear" for s in processor.get_open_sessions())
    processor.flush_session("s-clear")
    assert not any(s["session_id"] == "s-clear" for s in processor.get_open_sessions())


def test_flush_stale_sessions_honors_timeout(processor):
    # session_timeout_seconds=1 from fixture
    processor.process_batch(_batch(session_id="s-stale"))
    # Immediately-flushing stale should yield nothing
    assert processor.flush_stale_sessions() == []
    # After waiting past the timeout, session becomes stale
    time.sleep(1.2)
    paths = processor.flush_stale_sessions()
    assert len(paths) == 1
    assert not processor.get_open_sessions()


def test_flush_empty_session_returns_none(processor):
    assert processor.flush_session("nonexistent") is None


# ── Query interface ───────────────────────────────────────────────────────

def test_query_index_filters_by_category(processor):
    processor.process_batch(_batch(session_id="q-1"))  # Gmail → message
    processor.flush_session("q-1")
    processor.process_batch(_batch(
        session_id="q-2",
        app_package="com.android.chrome",
        app_label="Chrome",
        field_hint="Search",
    ))
    processor.flush_session("q-2")

    messages = processor.query_index(category=InputCategory.MESSAGE.value)
    searches = processor.query_index(category=InputCategory.SEARCH.value)
    assert len(messages) == 1
    assert len(searches) == 1
    assert messages[0]["session_id"] == "q-1"
    assert searches[0]["session_id"] == "q-2"


def test_query_index_filters_by_app(processor):
    processor.process_batch(_batch(session_id="app-q"))
    processor.flush_session("app-q")
    results = processor.query_index(app="Gmail")
    assert len(results) == 1
    assert results[0]["session_id"] == "app-q"
    assert processor.query_index(app="NonexistentApp") == []


def test_query_index_limit_respected(processor):
    for i in range(5):
        processor.process_batch(_batch(session_id=f"lim-{i}"))
        processor.flush_session(f"lim-{i}")
    assert len(processor.query_index(limit=3)) == 3


# ── Thread-safe block ID generation ──────────────────────────────────────

def test_block_ids_are_unique_under_concurrency(processor):
    import threading
    ids: list[str] = []
    lock = threading.Lock()

    def worker():
        for _ in range(25):
            bid = processor._next_block_id()
            with lock:
                ids.append(bid)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(ids) == 100
    assert len(set(ids)) == 100, "block IDs must be unique under concurrency"


# ── InputCortex agent wrapper ─────────────────────────────────────────────

@pytest.fixture
def cortex_agent(tmp_path):
    audit = AuditLog(log_dir=tmp_path / "logs")
    cfg = AgentConfig(
        name="input_cortex",
        custom={"session_timeout_seconds": 1, "min_words_to_store": 1},
    )
    agent = InputCortex(config=cfg, audit=audit, data_dir=str(tmp_path))
    agent.initialize()
    return agent


def test_cortex_initialize_idempotent(cortex_agent):
    """Second initialize() call must not reset counters or state."""
    cortex_agent.ingest_payload({
        "device_id": "d",
        "app_package": "com.google.android.gm",
        "app_label": "Gmail",
        "text": "schedule meeting please tomorrow",
        "session_id": "idem-1",
    })
    first_count = cortex_agent._batches_processed
    first_token = cortex_agent.auth_token
    assert first_count == 1
    assert first_token  # non-empty

    cortex_agent.initialize()

    assert cortex_agent._batches_processed == first_count
    assert cortex_agent.auth_token == first_token


def test_cortex_auth_token_generated(cortex_agent):
    assert cortex_agent.auth_token
    assert len(cortex_agent.auth_token) >= 20


def test_cortex_public_properties(cortex_agent):
    assert cortex_agent.drop_dir.exists()
    assert cortex_agent.data_dir.exists()
    assert isinstance(cortex_agent.auth_token, str)


def test_cortex_ingest_payload_returns_block(cortex_agent):
    block = cortex_agent.ingest_payload({
        "device_id": "d",
        "app_package": "com.google.android.gm",
        "app_label": "Gmail",
        "text": "test message for ingestion",
        "session_id": "ing-1",
    })
    assert block is not None
    assert block.category == InputCategory.MESSAGE.value
    assert cortex_agent._batches_processed == 1


def test_cortex_ingest_blocks_credential(cortex_agent):
    block = cortex_agent.ingest_payload({
        "device_id": "d",
        "app_package": "com.app.bank",
        "app_label": "Bank",
        "text": "hunter2",
        "field_hint": "Password",
        "input_type": "textPassword",
        "session_id": "cred-1",
    })
    assert block is None
    assert cortex_agent._batches_redacted == 1
    assert cortex_agent._batches_processed == 0


def test_session_summary_for_open_session(cortex_agent):
    cortex_agent.ingest_payload({
        "device_id": "d",
        "app_package": "com.google.android.gm",
        "app_label": "Gmail",
        "text": "open session test message",
        "session_id": "sum-open",
    })
    summary = cortex_agent.session_summary("sum-open")
    assert summary is not None
    assert summary["status"] == "open"
    assert summary["session_id"] == "sum-open"


def test_session_summary_for_flushed_session(cortex_agent):
    cortex_agent.ingest_payload({
        "device_id": "d",
        "app_package": "com.google.android.gm",
        "app_label": "Gmail",
        "text": "flushed session test message",
        "session_id": "sum-flushed",
    })
    assert cortex_agent._processor is not None
    cortex_agent._processor.flush_session("sum-flushed")
    summary = cortex_agent.session_summary("sum-flushed")
    assert summary is not None
    assert summary["status"] == "flushed"
    assert summary["session_id"] == "sum-flushed"


def test_session_summary_missing_returns_none(cortex_agent):
    assert cortex_agent.session_summary("does-not-exist") is None


def test_cortex_skill_manifest_advertises_loopback_and_auth():
    manifest = InputCortex.skill_manifest()
    assert manifest["default_bind"] == "127.0.0.1"
    assert "X-Cortex-Token" in manifest["auth"]
    assert manifest["privacy"]["raw_text_stored"] is False
    # session_summary advertised AND implemented
    skill_names = {s["name"] for s in manifest["skills"]}
    assert "session_summary" in skill_names


# ── HTTP listener auth integration test ───────────────────────────────────

def test_http_listener_rejects_without_token_and_accepts_with(tmp_path):
    """Integration test: start the listener on an ephemeral port,
    verify that requests without a valid X-Cortex-Token get 401,
    and requests with the correct token get 200."""
    import http.client
    import threading

    audit = AuditLog(log_dir=tmp_path / "logs")
    cfg = AgentConfig(
        name="input_cortex",
        custom={"session_timeout_seconds": 1, "min_words_to_store": 1},
    )
    agent = InputCortex(config=cfg, audit=audit, data_dir=str(tmp_path))
    agent.initialize()

    # Probe for a free port to avoid flake on shared CI runners.
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    # Start daemon listener in background
    agent.start_daemon(mode="listener", port=port, bind="127.0.0.1")

    # Poll until the listener is ready (replaces flaky time.sleep)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            probe = http.client.HTTPConnection("127.0.0.1", port, timeout=0.5)
            probe.request("GET", "/status", headers={"X-Cortex-Token": agent.auth_token})
            resp = probe.getresponse()
            resp.read()
            probe.close()
            if resp.status == 200:
                break
        except OSError:
            pass
        time.sleep(0.1)
    else:
        pytest.fail("HTTP listener did not become ready within 5s")

    try:
        # Request WITHOUT token → should get 401
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/status")
        resp = conn.getresponse()
        assert resp.status == 401, f"Expected 401, got {resp.status}"
        resp.read()
        conn.close()

        # Request WITH valid token → should get 200
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "GET", "/status",
            headers={"X-Cortex-Token": agent.auth_token},
        )
        resp = conn.getresponse()
        assert resp.status == 200, f"Expected 200, got {resp.status}"
        body = json.loads(resp.read())
        assert "batches_processed" in body
        conn.close()

        # POST with valid token → should get 200
        payload = json.dumps({
            "device_id": "test",
            "app_package": "com.google.android.gm",
            "app_label": "Gmail",
            "text": "test auth message for listener",
            "session_id": "auth-test",
        }).encode()
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "POST", "/input",
            body=payload,
            headers={
                "X-Cortex-Token": agent.auth_token,
                "Content-Type": "application/json",
                "Content-Length": str(len(payload)),
            },
        )
        resp = conn.getresponse()
        assert resp.status == 200, f"Expected 200, got {resp.status}"
        result = json.loads(resp.read())
        assert result["status"] == "ok"
        assert result["block_id"] is not None
        conn.close()

        # POST with WRONG token → 401
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "POST", "/input",
            body=payload,
            headers={
                "X-Cortex-Token": "wrong-token",
                "Content-Type": "application/json",
                "Content-Length": str(len(payload)),
            },
        )
        resp = conn.getresponse()
        assert resp.status == 401
        conn.close()

    finally:
        agent.stop_daemon()
