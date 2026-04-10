"""Fleet Management — Multi-device orchestration for Guardian One.

Manages Jeremy's compute fleet:
    A = ASUS ROG Flow Z13 (Windows, 64GB RAM) — Primary / heavy lifts
    B = MacBook Pro 2024 — Secondary workstation
    C = Mac Mini — Always-on homelink services

Components:
    nodes      — Compute node registry (specs, roles, health)
    orchestrator — Fleet control (SSH dispatch, task routing, health checks)
    resources  — Resource optimizer (RAM/CPU balancing, backup, subscriptions)
    displays   — Display topology (monitors, TVs, layout)
"""
