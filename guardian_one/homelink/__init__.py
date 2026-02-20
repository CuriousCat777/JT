"""H.O.M.E. L.I.N.K. — Secure API Integration & Orchestration Layer.

All external API connections for Guardian One agents are routed through
this module.  It enforces zero-trust, encrypted-by-default, and
observability-first principles.

Components:
    vault       — Encrypted secret storage (API keys, tokens)
    gateway     — Central API gateway with TLS enforcement & rate limiting
    registry    — Integration catalog with threat/failure models
    monitor     — Latency tracking, anomaly detection, weekly brief
"""
