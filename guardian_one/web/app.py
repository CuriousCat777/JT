"""Guardian One — Web-based Dev Panel.

Usage:
    python -m guardian_one.web.app          # Start on port 5100
    python main.py --devpanel               # Via CLI
    python main.py --devpanel --port 8080   # Custom port
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

from guardian_one.core.config import AgentConfig, load_config
from guardian_one.core.guardian import GuardianOne
from guardian_one.core.audit import Severity
from guardian_one.core.base_agent import AgentStatus

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

_guardian: GuardianOne | None = None
_lock = threading.Lock()


def _get_guardian() -> GuardianOne:
    global _guardian
    if _guardian is None:
        with _lock:
            if _guardian is None:
                config = load_config()
                _guardian = GuardianOne(config=config)
                _build_agents(_guardian)
    return _guardian


def _build_agents(guardian: GuardianOne) -> None:
    """Register all agents (mirrors main.py)."""
    from guardian_one.agents.chronos import Chronos
    from guardian_one.agents.archivist import Archivist
    from guardian_one.agents.cfo import CFO
    from guardian_one.agents.doordash import DoorDashAgent
    from guardian_one.agents.gmail_agent import GmailAgent
    from guardian_one.agents.web_architect import WebArchitect
    from guardian_one.agents.device_agent import DeviceAgent

    config = guardian.config
    for name, cls, kwargs in [
        ("chronos", Chronos, {}),
        ("archivist", Archivist, {}),
        ("cfo", CFO, {"data_dir": config.data_dir}),
        ("doordash", DoorDashAgent, {}),
        ("gmail", GmailAgent, {"data_dir": config.data_dir}),
        ("web_architect", WebArchitect, {}),
        ("device_agent", DeviceAgent, {}),
    ]:
        cfg = config.agents.get(name, AgentConfig(name=name))
        guardian.register_agent(cls(config=cfg, audit=guardian.audit, **kwargs))


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------

    @app.route("/")
    def index():
        return render_template("panel.html")

    # ------------------------------------------------------------------
    # API — System
    # ------------------------------------------------------------------

    @app.route("/api/status")
    def api_status():
        g = _get_guardian()
        agents = []
        for name in g.list_agents():
            agent = g.get_agent(name)
            if agent is None:
                continue
            agents.append({
                "name": name,
                "status": agent.status.value,
                "enabled": agent.config.enabled,
                "interval_min": agent.config.schedule_interval_minutes,
                "allowed_resources": agent.config.allowed_resources,
            })
        return jsonify({
            "owner": g.config.owner,
            "timezone": g.config.timezone,
            "agents": agents,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # ------------------------------------------------------------------
    # API — Agents
    # ------------------------------------------------------------------

    @app.route("/api/agents")
    def api_agents():
        g = _get_guardian()
        result = []
        for name in g.list_agents():
            agent = g.get_agent(name)
            if agent is None:
                continue
            try:
                report = agent.report()
                report_data = {
                    "agent_name": report.agent_name,
                    "status": report.status,
                    "summary": report.summary,
                    "alerts": report.alerts,
                    "recommendations": report.recommendations,
                    "timestamp": report.timestamp,
                }
            except Exception as exc:
                report_data = {"error": str(exc)}
            result.append({
                "name": name,
                "status": agent.status.value,
                "enabled": agent.config.enabled,
                "interval_min": agent.config.schedule_interval_minutes,
                "allowed_resources": agent.config.allowed_resources,
                "report": report_data,
            })
        return jsonify(result)

    @app.route("/api/agents/<name>/run", methods=["POST"])
    def api_run_agent(name: str):
        g = _get_guardian()
        try:
            report = g.run_agent(name)
            return jsonify({
                "agent_name": report.agent_name,
                "status": report.status,
                "summary": report.summary,
                "alerts": report.alerts,
                "recommendations": report.recommendations,
                "actions_taken": report.actions_taken,
                "timestamp": report.timestamp,
            })
        except KeyError:
            return jsonify({"error": f"Unknown agent: {name}"}), 404

    @app.route("/api/agents/run-all", methods=["POST"])
    def api_run_all():
        g = _get_guardian()
        reports = g.run_all()
        return jsonify([
            {
                "agent_name": r.agent_name,
                "status": r.status,
                "summary": r.summary,
                "alerts": r.alerts,
            }
            for r in reports
        ])

    # ------------------------------------------------------------------
    # API — Audit Log
    # ------------------------------------------------------------------

    @app.route("/api/audit")
    def api_audit():
        g = _get_guardian()
        agent_filter = request.args.get("agent")
        severity_filter = request.args.get("severity")
        limit = min(int(request.args.get("limit", 100)), 500)

        sev = None
        if severity_filter:
            try:
                sev = Severity(severity_filter)
            except ValueError:
                pass

        entries = g.audit.query(agent=agent_filter, severity=sev, limit=limit)
        return jsonify([e.to_dict() for e in entries])

    @app.route("/api/audit/pending")
    def api_audit_pending():
        g = _get_guardian()
        entries = g.audit.pending_reviews()
        return jsonify([e.to_dict() for e in entries])

    @app.route("/api/audit/summary")
    def api_audit_summary():
        g = _get_guardian()
        return jsonify({"summary": g.audit.summary(last_n=30)})

    # ------------------------------------------------------------------
    # API — H.O.M.E. L.I.N.K.
    # ------------------------------------------------------------------

    @app.route("/api/homelink/services")
    def api_services():
        g = _get_guardian()
        return jsonify(g.gateway.all_services_status())

    @app.route("/api/homelink/health")
    def api_health():
        g = _get_guardian()
        snapshots = g.monitor.all_health()
        return jsonify([
            {
                "service": s.service,
                "circuit_state": s.circuit_state,
                "success_rate": s.success_rate,
                "avg_latency_ms": s.avg_latency_ms,
                "rate_limit_remaining": s.rate_limit_remaining,
                "risk_score": s.risk_score,
            }
            for s in snapshots
        ])

    @app.route("/api/homelink/anomalies")
    def api_anomalies():
        g = _get_guardian()
        anomalies = g.monitor.detect_anomalies()
        return jsonify([
            {
                "service": a.service,
                "type": a.anomaly_type,
                "description": a.description,
                "severity": a.severity,
                "detected_at": a.detected_at,
            }
            for a in anomalies
        ])

    # ------------------------------------------------------------------
    # API — Vault (metadata only, NO secrets)
    # ------------------------------------------------------------------

    @app.route("/api/vault")
    def api_vault():
        g = _get_guardian()
        health = g.vault.health_report()
        keys = g.vault.list_keys()
        meta = []
        for k in keys:
            m = g.vault.get_meta(k)
            if m:
                meta.append({
                    "key_name": m.key_name,
                    "service": m.service,
                    "scope": m.scope,
                    "created_at": m.created_at,
                    "rotated_at": m.rotated_at,
                    "expires_at": m.expires_at,
                    "rotation_days": m.rotation_days,
                })
        return jsonify({
            "health": health,
            "credentials": meta,
        })

    # ------------------------------------------------------------------
    # API — Registry
    # ------------------------------------------------------------------

    @app.route("/api/registry")
    def api_registry():
        g = _get_guardian()
        integrations = []
        for name in g.registry.list_all():
            record = g.registry.get(name)
            if record is None:
                continue
            integrations.append({
                "name": record.name,
                "description": record.description,
                "base_url": record.base_url,
                "auth_method": record.auth_method,
                "owner_agent": record.owner_agent,
                "status": record.status,
                "threat_count": len(record.threat_model),
                "vault_keys": record.vault_keys,
            })
        return jsonify(integrations)

    @app.route("/api/registry/<name>/threats")
    def api_registry_threats(name: str):
        g = _get_guardian()
        record = g.registry.get(name)
        if record is None:
            return jsonify({"error": f"Unknown integration: {name}"}), 404
        return jsonify({
            "name": record.name,
            "threats": [
                {"risk": t.risk, "severity": t.severity, "mitigation": t.mitigation}
                for t in record.threat_model
            ],
            "failure_impact": record.failure_impact,
            "rollback_procedure": record.rollback_procedure,
        })

    # ------------------------------------------------------------------
    # API — H.O.M.E. L.I.N.K. Device Control
    # ------------------------------------------------------------------

    @app.route("/api/homelink/devices")
    def api_homelink_devices():
        g = _get_guardian()
        agent = g.get_agent("device_agent")
        if agent is None:
            return jsonify({"error": "DeviceAgent not registered"}), 500
        devices = agent.list_devices()
        return jsonify([
            {
                "device_id": d.device_id,
                "name": d.name,
                "category": d.category.value,
                "manufacturer": d.manufacturer,
                "model": d.model,
                "location": d.location,
                "status": d.status.value,
                "local_api_only": d.local_api_only,
                "integration": d.integration_name,
                "ip_address": d.ip_address,
                "network_segment": d.network_segment.value,
                "tags": d.tags,
            }
            for d in devices
        ])

    @app.route("/api/homelink/rooms")
    def api_homelink_rooms():
        g = _get_guardian()
        agent = g.get_agent("device_agent")
        if agent is None:
            return jsonify({"error": "DeviceAgent not registered"}), 500
        return jsonify(agent.device_registry.room_summary())

    @app.route("/api/homelink/scenes")
    def api_homelink_scenes():
        g = _get_guardian()
        agent = g.get_agent("device_agent")
        if agent is None:
            return jsonify({"error": "DeviceAgent not registered"}), 500
        scenes = agent.automation.all_scenes()
        return jsonify([
            {
                "scene_id": s.scene_id,
                "name": s.name,
                "description": s.description,
                "action_count": len(s.actions),
                "room_id": s.room_id,
                "tags": s.tags,
            }
            for s in scenes
        ])

    @app.route("/api/homelink/scenes/<scene_id>/activate", methods=["POST"])
    def api_activate_scene(scene_id: str):
        g = _get_guardian()
        agent = g.get_agent("device_agent")
        if agent is None:
            return jsonify({"error": "DeviceAgent not registered"}), 500
        results = agent.activate_scene(scene_id)
        return jsonify({
            "scene_id": scene_id,
            "actions_executed": len(results),
            "results": results,
        })

    @app.route("/api/homelink/devices/<device_id>/on", methods=["POST"])
    def api_device_on(device_id: str):
        g = _get_guardian()
        agent = g.get_agent("device_agent")
        if agent is None:
            return jsonify({"error": "DeviceAgent not registered"}), 500
        device = agent.get_device(device_id)
        if device is None:
            return jsonify({"error": f"Device not found: {device_id}"}), 404
        driver = agent.drivers.for_device(device)
        if driver is None:
            return jsonify({
                "error": f"No driver for {device_id} (integration={device.integration_name}, ip={device.ip_address})",
                "hint": "Set the device IP address first via LAN scan or manual config",
            }), 400
        from guardian_one.homelink.drivers import KasaDriver, HueDriver, GoveeLanDriver, GoveeCloudDriver
        if isinstance(driver, KasaDriver):
            result = driver.turn_on()
        elif isinstance(driver, HueDriver):
            result = driver.turn_on(brightness=254)
        elif isinstance(driver, (GoveeLanDriver, GoveeCloudDriver)):
            result = driver.turn_on()
        else:
            result = {"success": False, "error": "Unknown driver type"}
        return jsonify(result)

    @app.route("/api/homelink/devices/<device_id>/off", methods=["POST"])
    def api_device_off(device_id: str):
        g = _get_guardian()
        agent = g.get_agent("device_agent")
        if agent is None:
            return jsonify({"error": "DeviceAgent not registered"}), 500
        device = agent.get_device(device_id)
        if device is None:
            return jsonify({"error": f"Device not found: {device_id}"}), 404
        driver = agent.drivers.for_device(device)
        if driver is None:
            return jsonify({
                "error": f"No driver for {device_id}",
                "hint": "Set the device IP address first",
            }), 400
        from guardian_one.homelink.drivers import KasaDriver, HueDriver, GoveeLanDriver, GoveeCloudDriver
        if isinstance(driver, KasaDriver):
            result = driver.turn_off()
        elif isinstance(driver, HueDriver):
            result = driver.turn_off()
        elif isinstance(driver, (GoveeLanDriver, GoveeCloudDriver)):
            result = driver.turn_off()
        else:
            result = {"success": False, "error": "Unknown driver type"}
        return jsonify(result)

    @app.route("/api/homelink/devices/<device_id>/brightness", methods=["POST"])
    def api_device_brightness(device_id: str):
        g = _get_guardian()
        agent = g.get_agent("device_agent")
        if agent is None:
            return jsonify({"error": "DeviceAgent not registered"}), 500
        device = agent.get_device(device_id)
        if device is None:
            return jsonify({"error": f"Device not found: {device_id}"}), 404
        body = request.get_json(silent=True) or {}
        pct = max(0, min(100, int(body.get("brightness", 50))))
        driver = agent.drivers.for_device(device)
        if driver is None:
            return jsonify({"error": f"No driver for {device_id}"}), 400
        from guardian_one.homelink.drivers import HueDriver, GoveeLanDriver, GoveeCloudDriver
        if isinstance(driver, HueDriver):
            result = driver.set_brightness(pct)
        elif isinstance(driver, (GoveeLanDriver, GoveeCloudDriver)):
            result = driver.set_brightness(pct)
        else:
            result = {"success": False, "error": "Brightness not supported for this device"}
        return jsonify(result)

    @app.route("/api/homelink/events/<event>", methods=["POST"])
    def api_schedule_event(event: str):
        """Trigger a schedule event: wake, sleep, leave, arrive."""
        if event not in ("wake", "sleep", "leave", "arrive"):
            return jsonify({"error": f"Unknown event: {event}"}), 400
        g = _get_guardian()
        agent = g.get_agent("device_agent")
        if agent is None:
            return jsonify({"error": "DeviceAgent not registered"}), 500
        results = agent.handle_schedule_event(event)
        return jsonify({
            "event": event,
            "actions_executed": len(results),
            "results": results,
        })

    @app.route("/api/homelink/energy")
    def api_energy():
        """Energy monitoring — Kasa KP125 power data + light state summary."""
        g = _get_guardian()
        agent = g.get_agent("device_agent")
        if agent is None:
            return jsonify({"error": "DeviceAgent not registered"}), 500
        registry = agent.device_registry
        devices = registry.all_devices()

        energy_data = {"plugs": [], "lights_on": [], "lights_off": [],
                       "total_watts": 0.0, "plug_count": 0, "light_count": 0,
                       "lights_on_count": 0}

        for d in devices:
            if d.category.value == "smart_plug":
                plug_info = {
                    "device_id": d.device_id, "name": d.name,
                    "location": d.location, "ip_address": d.ip_address or "",
                    "watts": 0.0, "voltage": 0.0, "current": 0.0,
                    "status": "unknown",
                }
                if d.ip_address:
                    try:
                        import asyncio
                        from kasa import SmartPlug
                        async def _get_emeter(ip):
                            p = SmartPlug(ip)
                            await p.update()
                            em = p.emeter_realtime if hasattr(p, 'emeter_realtime') else {}
                            return {
                                "watts": getattr(em, 'power', em.get('power', 0)),
                                "voltage": getattr(em, 'voltage', em.get('voltage', 0)),
                                "current": getattr(em, 'current', em.get('current', 0)),
                                "is_on": p.is_on,
                            }
                        data = asyncio.run(_get_emeter(d.ip_address))
                        plug_info.update(data)
                        plug_info["status"] = "on" if data["is_on"] else "off"
                        energy_data["total_watts"] += data["watts"]
                    except Exception:
                        plug_info["status"] = "unreachable"
                energy_data["plugs"].append(plug_info)
                energy_data["plug_count"] += 1

            elif d.category.value == "smart_light":
                light_info = {
                    "device_id": d.device_id, "name": d.name,
                    "location": d.location, "ip_address": d.ip_address or "",
                    "integration": d.integration_name or "",
                    "status": "unknown",
                }
                energy_data["light_count"] += 1
                energy_data["lights_off"].append(light_info)

        return jsonify(energy_data)

    @app.route("/api/homelink/weather")
    def api_weather():
        """Local weather for drone flight assessment."""
        try:
            import urllib.request
            import json as _json
            url = ("https://api.open-meteo.com/v1/forecast?"
                   "latitude=46.7833&longitude=-92.1066"
                   "&current=temperature_2m,wind_speed_10m,wind_gusts_10m,"
                   "precipitation,cloud_cover,visibility"
                   "&temperature_unit=fahrenheit&wind_speed_unit=mph")
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = _json.loads(resp.read().decode())
            current = data.get("current", {})
            wind = current.get("wind_speed_10m", 0)
            gusts = current.get("wind_gusts_10m", 0)
            precip = current.get("precipitation", 0)
            visibility = current.get("visibility", 10000)
            cloud = current.get("cloud_cover", 0)
            temp = current.get("temperature_2m", 0)

            # DJI flight assessment
            issues = []
            if wind > 20:
                issues.append(f"Wind too high: {wind} mph")
            if gusts > 25:
                issues.append(f"Gusts dangerous: {gusts} mph")
            if precip > 0:
                issues.append(f"Precipitation: {precip} mm")
            if visibility < 3000:
                issues.append(f"Low visibility: {visibility}m")
            if temp < 32:
                issues.append(f"Battery risk: {temp}\u00b0F (cold)")

            fly_ok = len(issues) == 0
            return jsonify({
                "temperature_f": temp,
                "wind_mph": wind,
                "wind_gusts_mph": gusts,
                "precipitation_mm": precip,
                "cloud_cover_pct": cloud,
                "visibility_m": visibility,
                "drone_flight_ok": fly_ok,
                "drone_issues": issues,
                "assessment": "CLEAR TO FLY" if fly_ok else "DO NOT FLY",
                "location": "Duluth, MN",
            })
        except Exception as e:
            return jsonify({"error": str(e), "drone_flight_ok": False,
                            "assessment": "WEATHER UNAVAILABLE"})

    # ------------------------------------------------------------------
    # API — Noise / Volume Control
    # ------------------------------------------------------------------

    @app.route("/api/homelink/noise")
    def api_noise_status():
        """Get volume/noise status for all audio devices."""
        g = _get_guardian()
        agent = g.get_agent("device_agent")
        if agent is None:
            return jsonify({"error": "DeviceAgent not registered"}), 500
        registry = agent.device_registry
        devices = registry.all_devices()

        audio_devices = []
        # LG TV
        for d in devices:
            if d.category.value == "smart_tv" and d.ip_address:
                audio_devices.append({
                    "device_id": d.device_id, "name": d.name,
                    "type": "tv", "ip": d.ip_address,
                    "has_volume": True, "has_mute": True,
                    "can_kill_power": False,
                })
            elif d.category.value == "media_player":
                audio_devices.append({
                    "device_id": d.device_id, "name": d.name,
                    "type": "echo", "ip": d.ip_address or "",
                    "has_volume": False, "has_mute": False,
                    "can_kill_power": True,
                    "note": "Kill power via Kasa plug to silence",
                })
            elif "music_sync" in (d.device_id or "").lower():
                audio_devices.append({
                    "device_id": d.device_id, "name": d.name,
                    "type": "speaker", "ip": d.ip_address or "",
                    "has_volume": False, "has_mute": False,
                    "can_kill_power": True,
                })
        return jsonify({"audio_devices": audio_devices,
                        "count": len(audio_devices)})

    @app.route("/api/homelink/volume/<device_id>", methods=["POST"])
    def api_set_volume(device_id: str):
        """Set volume on a device (TV only for now)."""
        g = _get_guardian()
        agent = g.get_agent("device_agent")
        if agent is None:
            return jsonify({"error": "DeviceAgent not registered"}), 500
        registry = agent.device_registry
        device = registry.get_device(device_id)
        if not device:
            return jsonify({"error": f"Unknown device: {device_id}"}), 404

        body = request.get_json(silent=True) or {}
        level = body.get("volume", 20)

        from guardian_one.homelink.drivers import LgWebOsDriver, DriverFactory
        factory = DriverFactory(vault_retrieve=g.vault.retrieve)

        if device.category.value == "smart_tv" and device.ip_address:
            driver = factory.get_lg_driver(device.ip_address)
            result = driver.set_volume(int(level))
            return jsonify({"success": result.get("success", False),
                            "device": device_id, "volume": level})

        return jsonify({"error": "Volume control not supported for this device"}), 400

    @app.route("/api/homelink/mute/<device_id>", methods=["POST"])
    def api_mute_device(device_id: str):
        """Mute a specific device."""
        g = _get_guardian()
        agent = g.get_agent("device_agent")
        if agent is None:
            return jsonify({"error": "DeviceAgent not registered"}), 500
        registry = agent.device_registry
        device = registry.get_device(device_id)
        if not device:
            return jsonify({"error": f"Unknown device: {device_id}"}), 404

        from guardian_one.homelink.drivers import DriverFactory
        factory = DriverFactory(vault_retrieve=g.vault.retrieve)

        if device.category.value == "smart_tv" and device.ip_address:
            driver = factory.get_lg_driver(device.ip_address)
            result = driver.mute(True)
            return jsonify({"success": result.get("success", False),
                            "device": device_id, "action": "muted"})

        return jsonify({"error": "Mute not supported for this device"}), 400

    @app.route("/api/homelink/silence-all", methods=["POST"])
    def api_silence_all():
        """EMERGENCY: Mute TV, kill power to all audio devices via Kasa plugs."""
        g = _get_guardian()
        agent = g.get_agent("device_agent")
        if agent is None:
            return jsonify({"error": "DeviceAgent not registered"}), 500
        registry = agent.device_registry
        devices = registry.all_devices()

        from guardian_one.homelink.drivers import DriverFactory
        factory = DriverFactory(vault_retrieve=g.vault.retrieve)

        results = []
        for d in devices:
            # Mute TV
            if d.category.value == "smart_tv" and d.ip_address:
                try:
                    driver = factory.get_lg_driver(d.ip_address)
                    r = driver.mute(True)
                    results.append({"device": d.device_id, "action": "muted",
                                    "success": r.get("success", False)})
                except Exception as e:
                    results.append({"device": d.device_id, "action": "mute_failed",
                                    "error": str(e)})

            # Kill power to Echo Dots via Kasa if they have IPs
            if d.category.value == "media_player" and d.ip_address:
                try:
                    driver = factory.get_kasa_driver(d.ip_address)
                    r = driver.turn_off()
                    results.append({"device": d.device_id, "action": "power_killed",
                                    "success": r.get("success", False)})
                except Exception as e:
                    results.append({"device": d.device_id, "action": "kill_failed",
                                    "error": str(e)})

        g.audit.record(
            agent="homelink", action="SILENCE_ALL",
            severity=Severity.WARNING,
            details={"results": results, "devices_affected": len(results)},
        )
        return jsonify({"silenced": True, "results": results,
                        "devices_affected": len(results)})

    @app.route("/api/homelink/schedule")
    def api_schedule():
        """Automation schedule — what runs when."""
        g = _get_guardian()
        agent = g.get_agent("device_agent")
        if agent is None:
            return jsonify({"error": "DeviceAgent not registered"}), 500

        # Build schedule from device scenes + Chronos schedules
        automations = [
            {"time": "06:30", "description": "Blinds open to 50% (sunrise prep)",
             "device": "blind-ryse-01", "days": "weekdays", "enabled": True},
            {"time": "07:00", "description": "Wake scene — lights warm 30%, blinds full open",
             "device": "scene-wake", "days": "daily", "enabled": True},
            {"time": "09:00", "description": "Blinds fully open",
             "device": "blind-ryse-01", "days": "daily", "enabled": True},
            {"time": "09:00", "description": "Roborock vacuum — full clean cycle",
             "device": "vacuum-roborock", "days": "MWF", "enabled": True},
            {"time": "sunset", "description": "Living room lights on 60%, warm white",
             "device": "light-govee-lr-main", "days": "daily", "enabled": True},
            {"time": "sunset", "description": "Balcony strip on (ambient)",
             "device": "light-govee-balcony", "days": "daily", "enabled": True},
            {"time": "21:00", "description": "Lights dim to 30%, warm",
             "device": "scene-relax", "days": "daily", "enabled": True},
            {"time": "22:30", "description": "Goodnight scene — all lights off, blinds close, TV off",
             "device": "scene-goodnight", "days": "daily", "enabled": True},
            {"time": "23:00", "description": "Ring monitor — check Manteca events",
             "device": "ring-doorbell-manteca", "days": "daily", "enabled": True},
            {"time": "03:00", "description": "Security audit — scan for anomalies",
             "device": "system", "days": "daily", "enabled": True},
        ]
        return jsonify({"automations": automations, "count": len(automations)})

    @app.route("/api/homelink/security-audit")
    def api_security_audit():
        g = _get_guardian()
        agent = g.get_agent("device_agent")
        if agent is None:
            return jsonify({"error": "DeviceAgent not registered"}), 500
        return jsonify(agent.device_registry.security_audit())

    @app.route("/api/homelink/lan-security")
    def api_lan_security():
        g = _get_guardian()
        agent = g.get_agent("device_agent")
        if agent is None:
            return jsonify({"error": "DeviceAgent not registered"}), 500
        from guardian_one.homelink.lan_security import LanSecurityAuditor
        auditor = LanSecurityAuditor(agent.device_registry)
        return jsonify(auditor.full_audit())

    # ------------------------------------------------------------------
    # API — Email Commands (HOMELINK: prefix)
    # ------------------------------------------------------------------

    _email_processor = None

    @app.route("/api/homelink/email-commands")
    def api_email_commands():
        """List supported email commands."""
        commands = [
            {"command": "HOMELINK: silence all", "description": "Mute TV + kill power to speakers"},
            {"command": "HOMELINK: lights off", "description": "Turn off all lights"},
            {"command": "HOMELINK: lights on", "description": "Turn on all lights"},
            {"command": "HOMELINK: wake", "description": "Fire morning routine"},
            {"command": "HOMELINK: goodnight", "description": "Fire bedtime routine"},
            {"command": "HOMELINK: leave", "description": "Fire leave-home routine"},
            {"command": "HOMELINK: arrive", "description": "Fire arrive-home routine"},
            {"command": "HOMELINK: vacuum start", "description": "Start Roborock clean cycle"},
            {"command": "HOMELINK: vacuum stop", "description": "Dock Roborock"},
            {"command": "HOMELINK: tv mute", "description": "Mute LG TV"},
            {"command": "HOMELINK: tv volume 30", "description": "Set TV volume (0-100)"},
            {"command": "HOMELINK: scene movie", "description": "Activate scene (movie/work/gaming/relax)"},
            {"command": "HOMELINK: <device> on", "description": "Turn specific device on"},
            {"command": "HOMELINK: <device> off", "description": "Turn specific device off"},
            {"command": "HOMELINK: <device> brightness 50", "description": "Set brightness (0-100)"},
            {"command": "HOMELINK: status", "description": "Get system status summary"},
        ]
        aliases = {
            "tv": "lg-tv-65-living",
            "vacuum": "vacuum-roborock",
            "govee lr": "light-govee-lr-main",
            "govee desk": "light-govee-desk",
            "balcony": "light-govee-balcony",
            "blinds": "blind-ryse-01",
            "hue 1": "light-hue-bedroom-01",
        }
        return jsonify({"commands": commands, "aliases": aliases})

    @app.route("/api/homelink/email-commands/process", methods=["POST"])
    def api_process_email_command():
        """Process a single email command (manual trigger or from Gmail agent)."""
        nonlocal _email_processor
        g = _get_guardian()
        agent = g.get_agent("device_agent")
        if agent is None:
            return jsonify({"error": "DeviceAgent not registered"}), 500

        if _email_processor is None:
            from guardian_one.homelink.email_commands import EmailCommandProcessor
            _email_processor = EmailCommandProcessor(
                device_agent=agent, audit=g.audit)

        body = request.get_json(silent=True) or {}
        subject = body.get("subject", "")
        sender = body.get("sender", "")
        message_id = body.get("message_id", "")

        from guardian_one.homelink.email_commands import parse_email_command
        cmd = parse_email_command(subject, sender=sender,
                                  message_id=message_id)
        if cmd is None:
            return jsonify({"error": "Not a HOMELINK command",
                            "subject": subject}), 400

        result = _email_processor.execute(cmd)
        return jsonify({
            "success": result.success,
            "message": result.message,
            "command": result.command.command,
            "action": result.command.action,
            "target": result.command.target,
            "details": result.details,
        })

    @app.route("/api/homelink/email-commands/scan", methods=["POST"])
    def api_scan_email_commands():
        """Scan Gmail inbox for unread HOMELINK: commands and execute them."""
        nonlocal _email_processor
        g = _get_guardian()
        agent = g.get_agent("device_agent")
        gmail_agent = g.get_agent("gmail")
        if agent is None:
            return jsonify({"error": "DeviceAgent not registered"}), 500
        if gmail_agent is None:
            return jsonify({"error": "GmailAgent not registered"}), 500

        if _email_processor is None:
            from guardian_one.homelink.email_commands import EmailCommandProcessor
            _email_processor = EmailCommandProcessor(
                device_agent=agent, audit=g.audit)

        # Search for unread HOMELINK emails
        gmail = gmail_agent.gmail
        if not gmail.is_authenticated:
            return jsonify({
                "error": "Gmail not authenticated",
                "hint": "Complete OAuth2 setup first",
            }), 400

        messages = gmail.list_messages(
            query="subject:HOMELINK is:unread", max_results=10)
        results = []
        from guardian_one.homelink.email_commands import parse_email_command
        for ref in messages:
            msg = gmail.get_message(ref["id"], format="metadata")
            if not msg:
                continue
            cmd = parse_email_command(
                msg.subject, sender=msg.sender, message_id=ref["id"])
            if cmd:
                r = _email_processor.execute(cmd)
                results.append({
                    "subject": msg.subject,
                    "sender": msg.sender,
                    "success": r.success,
                    "message": r.message,
                })

        return jsonify({
            "scanned": len(messages),
            "executed": len(results),
            "results": results,
        })

    @app.route("/homelink")
    def homelink_dashboard():
        return render_template("homelink.html")

    # ------------------------------------------------------------------
    # API — Ring Monitor (Manteca priority)
    # ------------------------------------------------------------------

    _ring_monitor = None

    @app.route("/api/homelink/ring/status")
    def api_ring_status():
        nonlocal _ring_monitor
        if _ring_monitor is None:
            g = _get_guardian()
            from guardian_one.integrations.ring_monitor import RingMonitor
            _ring_monitor = RingMonitor(
                audit=g.audit, vault=g.vault, poll_interval=60)
        return jsonify(_ring_monitor.status())

    @app.route("/api/homelink/ring/start", methods=["POST"])
    def api_ring_start():
        nonlocal _ring_monitor
        g = _get_guardian()
        if _ring_monitor is None:
            from guardian_one.integrations.ring_monitor import RingMonitor
            _ring_monitor = RingMonitor(
                audit=g.audit, vault=g.vault, poll_interval=60)
        _ring_monitor.start_polling()
        return jsonify({"status": "polling_started",
                        "interval": _ring_monitor._poll_interval})

    @app.route("/api/homelink/ring/stop", methods=["POST"])
    def api_ring_stop():
        if _ring_monitor:
            _ring_monitor.stop_polling()
        return jsonify({"status": "polling_stopped"})

    @app.route("/api/homelink/ring/check", methods=["POST"])
    def api_ring_check():
        nonlocal _ring_monitor
        g = _get_guardian()
        if _ring_monitor is None:
            from guardian_one.integrations.ring_monitor import RingMonitor
            _ring_monitor = RingMonitor(
                audit=g.audit, vault=g.vault, poll_interval=60)
        events = _ring_monitor.check_events()
        return jsonify({"new_events": [e.to_dict() for e in events]})

    @app.route("/api/homelink/ring/manteca")
    def api_ring_manteca():
        if _ring_monitor is None:
            return jsonify({"events": [], "note": "Ring monitor not started"})
        return jsonify({"events": _ring_monitor.manteca_events()})

    # ------------------------------------------------------------------
    # API — Config (read-only view)
    # ------------------------------------------------------------------

    @app.route("/api/config")
    def api_config():
        g = _get_guardian()
        return jsonify({
            "owner": g.config.owner,
            "timezone": g.config.timezone,
            "daily_summary_hour": g.config.daily_summary_hour,
            "data_dir": g.config.data_dir,
            "log_dir": g.config.log_dir,
            "agents": {
                name: {
                    "enabled": cfg.enabled,
                    "schedule_interval_minutes": cfg.schedule_interval_minutes,
                    "allowed_resources": cfg.allowed_resources,
                }
                for name, cfg in g.config.agents.items()
            },
        })

    # ------------------------------------------------------------------
    # API — Daily Summary
    # ------------------------------------------------------------------

    @app.route("/api/summary")
    def api_summary():
        g = _get_guardian()
        return jsonify({"summary": g.daily_summary()})

    # ------------------------------------------------------------------
    # API — OpenAI-compatible chat completions (Chatbot UI bridge)
    # ------------------------------------------------------------------

    @app.route("/v1/models", methods=["GET"])
    def oai_models():
        """List available models in OpenAI format."""
        g = _get_guardian()
        ai_status = g.ai_engine.status()
        models = []
        if ai_status["ollama"]["available"]:
            models.append({
                "id": f"ollama/{ai_status['ollama']['model']}",
                "object": "model",
                "owned_by": "ollama",
            })
        if ai_status["anthropic"]["available"]:
            models.append({
                "id": f"anthropic/{ai_status['anthropic']['model']}",
                "object": "model",
                "owned_by": "anthropic",
            })
        if ai_status["cloudflare"]["available"]:
            models.append({
                "id": f"cloudflare/{ai_status['cloudflare']['model']}",
                "object": "model",
                "owned_by": "cloudflare",
            })
        # Always expose the auto-select model
        models.insert(0, {
            "id": "guardian-one",
            "object": "model",
            "owned_by": "guardian-one",
        })
        return jsonify({"object": "list", "data": models})

    @app.route("/v1/chat/completions", methods=["POST"])
    def oai_chat_completions():
        """OpenAI-compatible chat completions endpoint.

        Translates OpenAI format to Guardian One's AI engine, which
        routes to the best available backend (Ollama, Anthropic, or
        Cloudflare Workers AI).

        Chatbot UI and any OpenAI-compatible client can use this.
        """
        import time
        import uuid

        g = _get_guardian()
        body = request.get_json(silent=True) or {}

        messages = body.get("messages", [])
        temperature = body.get("temperature", 0.7)
        max_tokens = body.get("max_tokens", 4096)
        stream = body.get("stream", False)

        if not messages:
            return jsonify({
                "error": {
                    "message": "messages is required",
                    "type": "invalid_request_error",
                }
            }), 400

        # Validate and extract messages
        from guardian_one.core.ai_engine import AIMessage
        valid_roles = {"system", "user", "assistant"}
        ai_messages = []
        for m in messages:
            if not isinstance(m, dict) or "role" not in m:
                return jsonify({
                    "error": {
                        "message": "Each message must be an object with a 'role' field",
                        "type": "invalid_request_error",
                    }
                }), 400
            if m["role"] not in valid_roles:
                return jsonify({
                    "error": {
                        "message": f"Invalid role '{m['role']}'. Must be one of: {', '.join(valid_roles)}",
                        "type": "invalid_request_error",
                    }
                }), 400
            ai_messages.append(AIMessage(role=m["role"], content=str(m.get("content", ""))))

        # Find the right backend based on requested model
        requested_model = body.get("model", "guardian-one")
        backend = None
        if requested_model.startswith("ollama/"):
            backend = g.ai_engine._ollama
        elif requested_model.startswith("anthropic/"):
            backend = g.ai_engine._anthropic
        elif requested_model.startswith("cloudflare/"):
            backend = g.ai_engine._cloudflare
        else:
            backend = g.ai_engine._select_backend()

        if backend is None or not backend.is_available():
            return jsonify({
                "error": {
                    "message": "No AI backend available",
                    "type": "server_error",
                }
            }), 503

        response = backend.generate(
            messages=ai_messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        # Track usage
        g.ai_engine._total_requests += 1
        g.ai_engine._total_tokens += response.tokens_used

        completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())

        if stream:
            # Server-Sent Events streaming
            def generate_sse():
                # Send the full content as a single chunk
                chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": response.model,
                    "choices": [{
                        "index": 0,
                        "delta": {"role": "assistant", "content": response.content},
                        "finish_reason": None,
                    }],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                # Send done signal
                done_chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": response.model,
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                    }],
                }
                yield f"data: {json.dumps(done_chunk)}\n\n"
                yield "data: [DONE]\n\n"

            return app.response_class(
                generate_sse(),
                mimetype="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        # Non-streaming response
        return jsonify({
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": response.model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response.content,
                },
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": response.tokens_used,
                "total_tokens": response.tokens_used,
            },
        })

    return app


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

def run_devpanel(guardian: GuardianOne | None = None, port: int = 5100, debug: bool = False) -> None:
    """Start the dev panel server."""
    global _guardian
    if guardian is not None:
        _guardian = guardian
    app = create_app()
    print(f"\n  Guardian One — Command Center")
    print(f"  http://localhost:{port}")
    print(f"  Press Ctrl+C to stop.\n")
    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    run_devpanel(debug=True)
