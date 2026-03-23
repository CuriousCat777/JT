"""H.O.M.E. L.I.N.K. — Home Operations Management Engine: Linked Infrastructure & Network Kernel

The unified service layer for Guardian One's physical and digital infrastructure.
H.O.M.E. L.I.N.K. is two systems working as one:

**API Infrastructure** — secure plumbing for every external call Guardian One makes:
    gateway.py      Secure API gateway (TLS 1.3, rate limiting, circuit breakers, retry)
    vault.py        Encrypted credential storage (Fernet/PBKDF2, rotation tracking)
    registry.py     Integration catalog with per-service threat models & rollback plans
    monitor.py      API health monitoring, anomaly detection, weekly security briefs

**Smart Home Control** — device management and automation for Jeremy's home:
    devices.py      Device inventory, room model, network segmentation, Flipper Zero profiles
    automations.py  Rule-based automation engine (wake/sleep/leave/arrive routines, scenes)

The DeviceAgent (agents/device_agent.py) is the primary consumer of the smart home
side, while every agent routes external API calls through the Gateway.

All actions are audited. All credentials are encrypted. All devices are inventoried.
"""
