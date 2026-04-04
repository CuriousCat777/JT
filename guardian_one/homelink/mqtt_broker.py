"""H.O.M.E. L.I.N.K. MQTT Broker Integration — Mosquitto message bus.

Sovereign MQTT broker for local IoT device communication:
- Device state publishes (device -> mqtt)
- Automation triggers (mqtt -> automation engine)
- Health monitoring via $SYS topics
- TLS-encrypted connections (optional, recommended)
- Topic-level ACL enforcement

Data flow: device -> mqtt -> automation -> action -> ui
All messages stay on the LAN. No cloud relay.
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from guardian_one.core.audit import AuditLog, Severity


class MqttQos(Enum):
    AT_MOST_ONCE = 0
    AT_LEAST_ONCE = 1
    EXACTLY_ONCE = 2


@dataclass
class MqttMessage:
    """An MQTT message received or published."""
    topic: str
    payload: str
    qos: int = 0
    retain: bool = False
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def payload_json(self) -> dict[str, Any] | None:
        """Try to parse payload as JSON, return None on failure."""
        try:
            return json.loads(self.payload)
        except (json.JSONDecodeError, TypeError):
            return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "payload": self.payload,
            "qos": self.qos,
            "retain": self.retain,
            "timestamp": self.timestamp,
        }


@dataclass
class MqttBrokerConfig:
    """Configuration for the MQTT broker connection."""
    host: str = "localhost"
    port: int = 1883
    tls_port: int = 8883
    use_tls: bool = False
    username: str = ""
    password: str = ""
    client_id: str = "guardian-one"
    keepalive: int = 60
    # Topic prefixes
    device_topic_prefix: str = "homelink/devices"
    event_topic_prefix: str = "homelink/events"
    command_topic_prefix: str = "homelink/commands"
    status_topic: str = "homelink/status"


# Standard topic structure:
# homelink/devices/{device_id}/state     — device publishes state
# homelink/devices/{device_id}/command   — guardian publishes commands
# homelink/events/{event_type}           — system events
# homelink/status                        — broker health


class MqttBrokerClient:
    """MQTT broker client for Guardian One.

    Wraps paho-mqtt (if available) with structured topic handling,
    message history, and subscription management. Falls back to
    an in-memory message bus if paho-mqtt is not installed.
    """

    def __init__(
        self,
        config: MqttBrokerConfig | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self._config = config or MqttBrokerConfig()
        self._audit = audit
        self._connected = False
        self._client: Any = None
        self._subscriptions: dict[str, list[Callable[[MqttMessage], None]]] = {}
        self._message_history: deque[MqttMessage] = deque(maxlen=1000)
        self._lock = threading.Lock()
        self._stats = {
            "messages_received": 0,
            "messages_published": 0,
            "connect_attempts": 0,
            "errors": 0,
        }

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def config(self) -> MqttBrokerConfig:
        return self._config

    def connect(self) -> bool:
        """Connect to the MQTT broker.

        Tries paho-mqtt first. If not available, operates in
        local-only mode (in-memory message bus).
        """
        self._stats["connect_attempts"] += 1

        try:
            import paho.mqtt.client as mqtt_client

            client = mqtt_client.Client(
                client_id=self._config.client_id,
                protocol=mqtt_client.MQTTv5,
            )

            if self._config.username:
                client.username_pw_set(
                    self._config.username, self._config.password,
                )

            if self._config.use_tls:
                client.tls_set()

            client.on_connect = self._on_connect
            client.on_message = self._on_message
            client.on_disconnect = self._on_disconnect

            port = self._config.tls_port if self._config.use_tls else self._config.port
            client.connect(
                self._config.host, port, self._config.keepalive,
            )
            client.loop_start()
            self._client = client
            self._connected = True

            self._log("mqtt_connected", Severity.INFO, {
                "host": self._config.host,
                "port": port,
                "tls": self._config.use_tls,
            })
            return True

        except ImportError:
            # paho-mqtt not installed — local-only mode
            self._connected = True
            self._log("mqtt_local_mode", Severity.INFO, {
                "reason": "paho-mqtt not installed, using in-memory bus",
            })
            return True

        except Exception as exc:
            self._stats["errors"] += 1
            self._log("mqtt_connect_error", Severity.ERROR, {
                "error": str(exc),
            })
            return False

    def disconnect(self) -> None:
        """Disconnect from the MQTT broker."""
        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
        self._connected = False
        self._log("mqtt_disconnected", Severity.INFO, {})

    def publish(
        self,
        topic: str,
        payload: str | dict[str, Any],
        qos: int = 0,
        retain: bool = False,
    ) -> bool:
        """Publish a message to a topic."""
        if isinstance(payload, dict):
            payload = json.dumps(payload)

        msg = MqttMessage(
            topic=topic, payload=payload, qos=qos, retain=retain,
        )

        with self._lock:
            self._message_history.append(msg)
            self._stats["messages_published"] += 1

        if self._client:
            try:
                result = self._client.publish(topic, payload, qos, retain)
                return result.rc == 0
            except Exception as exc:
                self._stats["errors"] += 1
                self._log("mqtt_publish_error", Severity.WARNING, {
                    "topic": topic, "error": str(exc),
                })
                return False

        # Local-only mode: dispatch to subscribers directly
        self._dispatch(msg)
        return True

    def subscribe(
        self,
        topic: str,
        callback: Callable[[MqttMessage], None],
        qos: int = 0,
    ) -> None:
        """Subscribe to a topic with a callback."""
        with self._lock:
            if topic not in self._subscriptions:
                self._subscriptions[topic] = []
            self._subscriptions[topic].append(callback)

        if self._client:
            try:
                self._client.subscribe(topic, qos)
            except Exception as exc:
                self._stats["errors"] += 1
                self._log("mqtt_subscribe_error", Severity.WARNING, {
                    "topic": topic, "error": str(exc),
                })

    def unsubscribe(self, topic: str) -> None:
        """Unsubscribe from a topic."""
        with self._lock:
            self._subscriptions.pop(topic, None)

        if self._client:
            try:
                self._client.unsubscribe(topic)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Device-specific topic helpers
    # ------------------------------------------------------------------

    def publish_device_state(
        self, device_id: str, state: dict[str, Any],
    ) -> bool:
        """Publish device state to homelink/devices/{device_id}/state."""
        topic = f"{self._config.device_topic_prefix}/{device_id}/state"
        state["timestamp"] = datetime.now(timezone.utc).isoformat()
        return self.publish(topic, state, qos=1, retain=True)

    def publish_device_command(
        self, device_id: str, command: dict[str, Any],
    ) -> bool:
        """Publish command to homelink/devices/{device_id}/command."""
        topic = f"{self._config.device_topic_prefix}/{device_id}/command"
        command["timestamp"] = datetime.now(timezone.utc).isoformat()
        return self.publish(topic, command, qos=1)

    def publish_event(
        self, event_type: str, data: dict[str, Any],
    ) -> bool:
        """Publish a system event to homelink/events/{event_type}."""
        topic = f"{self._config.event_topic_prefix}/{event_type}"
        data["timestamp"] = datetime.now(timezone.utc).isoformat()
        return self.publish(topic, data, qos=1)

    def subscribe_device_state(
        self,
        device_id: str,
        callback: Callable[[MqttMessage], None],
    ) -> None:
        """Subscribe to a specific device's state updates."""
        topic = f"{self._config.device_topic_prefix}/{device_id}/state"
        self.subscribe(topic, callback)

    def subscribe_all_device_states(
        self, callback: Callable[[MqttMessage], None],
    ) -> None:
        """Subscribe to all device state updates (wildcard)."""
        topic = f"{self._config.device_topic_prefix}/+/state"
        self.subscribe(topic, callback)

    def subscribe_events(
        self,
        event_type: str,
        callback: Callable[[MqttMessage], None],
    ) -> None:
        """Subscribe to system events of a given type."""
        topic = f"{self._config.event_topic_prefix}/{event_type}"
        self.subscribe(topic, callback)

    # ------------------------------------------------------------------
    # paho-mqtt callbacks
    # ------------------------------------------------------------------

    def _on_connect(self, client: Any, userdata: Any, flags: Any,
                    rc: Any, properties: Any = None) -> None:
        """Called when connected to broker — resubscribe to all topics."""
        self._connected = True
        for topic in self._subscriptions:
            client.subscribe(topic)

    def _on_message(self, client: Any, userdata: Any, msg: Any) -> None:
        """Called when a message is received."""
        mqtt_msg = MqttMessage(
            topic=msg.topic,
            payload=msg.payload.decode("utf-8", errors="replace"),
            qos=msg.qos,
            retain=msg.retain,
        )
        with self._lock:
            self._message_history.append(mqtt_msg)
            self._stats["messages_received"] += 1
        self._dispatch(mqtt_msg)

    def _on_disconnect(self, client: Any, userdata: Any,
                       rc: Any, properties: Any = None) -> None:
        self._connected = False
        if rc != 0:
            self._log("mqtt_unexpected_disconnect", Severity.WARNING, {
                "rc": rc,
            })

    def _dispatch(self, msg: MqttMessage) -> None:
        """Dispatch a message to matching subscribers."""
        with self._lock:
            subs = dict(self._subscriptions)

        for pattern, callbacks in subs.items():
            if self._topic_matches(pattern, msg.topic):
                for cb in callbacks:
                    try:
                        cb(msg)
                    except Exception as exc:
                        self._stats["errors"] += 1
                        self._log("mqtt_callback_error", Severity.WARNING, {
                            "topic": msg.topic, "error": str(exc),
                        })

    @staticmethod
    def _topic_matches(pattern: str, topic: str) -> bool:
        """Check if a topic matches an MQTT subscription pattern.

        Supports + (single-level wildcard) and # (multi-level wildcard).
        """
        pattern_parts = pattern.split("/")
        topic_parts = topic.split("/")

        for i, p in enumerate(pattern_parts):
            if p == "#":
                return True
            if i >= len(topic_parts):
                return False
            if p != "+" and p != topic_parts[i]:
                return False

        return len(pattern_parts) == len(topic_parts)

    # ------------------------------------------------------------------
    # Status & history
    # ------------------------------------------------------------------

    def message_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent messages."""
        with self._lock:
            msgs = list(self._message_history)
        return [m.to_dict() for m in msgs[-limit:]]

    def stats(self) -> dict[str, Any]:
        return {
            "connected": self._connected,
            "host": self._config.host,
            "port": self._config.tls_port if self._config.use_tls else self._config.port,
            "tls": self._config.use_tls,
            "subscriptions": list(self._subscriptions.keys()),
            "message_history_size": len(self._message_history),
            **self._stats,
        }

    def _log(self, action: str, severity: Severity, details: dict[str, Any]) -> None:
        if self._audit:
            self._audit.record(
                agent="mqtt_broker",
                action=action,
                severity=severity,
                details=details,
            )
