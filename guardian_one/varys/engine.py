"""VARYS Engine — the main orchestrator that ties all layers together.

Pipeline: Ingest → Detect → Triage → Score → Respond

Usage:
    engine = VarysEngine()
    engine.add_collector(AuthLogCollector())
    engine.start()  # runs continuous monitoring loop
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from guardian_one.varys.detection.anomaly import AnomalyDetector
from guardian_one.varys.detection.sigma_engine import SigmaEngine
from guardian_one.varys.brain.llm_triage import LLMTriage
from guardian_one.varys.brain.risk_scoring import RiskScorer
from guardian_one.varys.ingestion.collector import BaseCollector
from guardian_one.varys.models import Alert, SecurityEvent
from guardian_one.varys.response.actions import ResponseEngine

if TYPE_CHECKING:
    from guardian_one.core.ai_engine import AIEngine

logger = logging.getLogger(__name__)


class VarysEngine:
    """Central VARYS orchestrator — ingestion → detection → response pipeline.

    Attributes:
        sigma: Rule-based detection engine with built-in + custom rules.
        anomaly: Statistical anomaly detector with behavioral profiling.
        triage: LLM-powered alert triage (optional, degrades gracefully).
        scorer: Composite risk scoring engine.
        response: Automated response / SOAR-lite engine.
    """

    def __init__(
        self,
        ai_engine: AIEngine | None = None,
        dry_run: bool = True,
        z_threshold: float = 3.0,
    ) -> None:
        # Detection
        self.sigma = SigmaEngine()
        self.sigma.load_builtin_rules()
        self.anomaly = AnomalyDetector(z_threshold=z_threshold)

        # Brain
        self.triage = LLMTriage(ai_engine=ai_engine)
        self.scorer = RiskScorer()

        # Response
        self.response = ResponseEngine(dry_run=dry_run)

        # Ingestion
        self._collectors: list[BaseCollector] = []

        # State
        self._running = False
        self._total_events: int = 0
        self._total_alerts: int = 0
        self._start_time: str = ""
        self._last_cycle: str = ""

    def add_collector(self, collector: BaseCollector) -> None:
        """Register an ingestion collector."""
        self._collectors.append(collector)
        logger.info("VARYS: Registered collector '%s'", collector.name)

    def set_ai_engine(self, engine: AIEngine) -> None:
        """Inject AI engine for LLM triage."""
        self.triage.set_ai_engine(engine)

    def cycle(self) -> list[Alert]:
        """Run one ingestion → detection → response cycle.

        Returns all alerts generated in this cycle.
        """
        self._last_cycle = datetime.now(timezone.utc).isoformat()
        all_alerts: list[Alert] = []

        # 1. Ingest
        events = self._ingest()
        self._total_events += len(events)

        if not events:
            return all_alerts

        # 2. Detect (rule-based)
        rule_alerts = self.sigma.evaluate_batch(events)

        # 3. Detect (anomaly)
        anomaly_alerts = self.anomaly.detect_batch(events)

        all_alerts = rule_alerts + anomaly_alerts

        # 4. Triage (LLM or deterministic)
        for alert in all_alerts:
            self.triage.triage(alert)

        # 5. Score
        self.scorer.score_batch(all_alerts)

        # 6. Respond
        for alert in all_alerts:
            self.response.respond(alert)

        self._total_alerts += len(all_alerts)

        if all_alerts:
            logger.info(
                "VARYS cycle: %d events → %d alerts (rules=%d, anomaly=%d)",
                len(events), len(all_alerts), len(rule_alerts), len(anomaly_alerts),
            )

        return all_alerts

    def _ingest(self) -> list[SecurityEvent]:
        """Collect events from all registered collectors."""
        events: list[SecurityEvent] = []
        for collector in self._collectors:
            try:
                batch = collector.collect()
                events.extend(batch)
            except Exception as exc:
                logger.error("Collector '%s' failed: %s", collector.name, exc)
        return events

    def ingest_events(self, events: list[SecurityEvent]) -> list[Alert]:
        """Process externally-provided events through the pipeline.

        Useful for webhook/API-driven event ingestion without collectors.
        """
        self._total_events += len(events)

        rule_alerts = self.sigma.evaluate_batch(events)
        anomaly_alerts = self.anomaly.detect_batch(events)
        all_alerts = rule_alerts + anomaly_alerts

        for alert in all_alerts:
            self.triage.triage(alert)
        self.scorer.score_batch(all_alerts)
        for alert in all_alerts:
            self.response.respond(alert)

        self._total_alerts += len(all_alerts)
        return all_alerts

    def start(self, interval_seconds: int = 30) -> None:
        """Start the continuous monitoring loop.

        Blocks the calling thread. Use in daemon mode or a dedicated thread.
        """
        self._running = True
        self._start_time = datetime.now(timezone.utc).isoformat()
        logger.info("VARYS engine started (interval=%ds)", interval_seconds)

        try:
            while self._running:
                self.cycle()
                # Flush anomaly window periodically
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            logger.info("VARYS engine stopped by keyboard interrupt")
        finally:
            self._running = False

    def stop(self) -> None:
        """Signal the engine to stop."""
        self._running = False

    def status(self) -> dict[str, Any]:
        """Get comprehensive VARYS status."""
        return {
            "running": self._running,
            "start_time": self._start_time,
            "last_cycle": self._last_cycle,
            "total_events": self._total_events,
            "total_alerts": self._total_alerts,
            "collectors": [
                {"name": c.name, "events_collected": c.events_collected}
                for c in self._collectors
            ],
            "detection": {
                "rules_loaded": len(self.sigma.rules),
                "rule_matches": self.sigma.total_matches,
                "anomaly": self.anomaly.status(),
            },
            "brain": {
                "llm_available": self.triage.is_available,
                "total_triaged": self.triage.total_triaged,
                "risk_scoring": self.scorer.status(),
            },
            "response": self.response.status(),
        }
