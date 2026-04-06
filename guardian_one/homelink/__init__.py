"""H.O.M.E. L.I.N.K. — Secure API Integration & Orchestration Layer.

All external API connections for Guardian One agents are routed through
this module.  It enforces zero-trust, encrypted-by-default, and
observability-first principles.

Components:
    vault          — Encrypted secret storage (API keys, tokens)
    gateway        — Central API gateway with TLS enforcement & rate limiting
    registry       — Integration catalog with threat/failure models
    monitor        — Latency tracking, anomaly detection, weekly brief
    lan_security   — DNS blocking, VLAN policy, telemetry audit
    email_commands — Email-based device control (HOMELINK: prefix)
    iot_controller — Sovereign IoT local control (Docker Compose stack lifecycle)
    iot_stack      — n8n workflow & Node-RED flow templates for IoT AI agents
"""
