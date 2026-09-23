"""WhatsApp alarm notifications via a self-hosted OpenWA instance.

Mirrors the REST contract of a working OpenWA integration the user already
runs for a different project (send-text endpoint, digits+"@c.us" chat IDs,
X-API-Key header) -- not copied verbatim, since that project is async
(httpx) and this one is thread-based like every other file in
frigate/alarm/, so this uses `requests` (already a Frigate dependency,
docker/main/requirements-wheels.txt) synchronously instead.

WhatsAppNotifyConfig is a plain dataclass, not the Pydantic
AlarmWhatsAppConfig -- same core/config split as rules.py and schedule.py,
so this module stays free of frigate.config (AlarmWhatsAppConfig.
to_notify_config() does the conversion).

Stateful (per-camera/zone cooldown), unlike the SIA/Contact ID senders in
protocols/, which are bare functions -- hence a class here rather than a
closure in factory.py.
"""

import logging
import time
from dataclasses import dataclass

import requests

from frigate.alarm.event import AlarmEvent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WhatsAppNotifyConfig:
    api_base_url: str
    session_id: str
    api_key: str
    to_numbers: tuple[str, ...]
    cooldown_seconds: float = 300.0
    timeout_seconds: float = 30.0


def _chat_id(number: str) -> str:
    """OpenWA addresses chats as '<digits>@c.us'; accept E.164 or a bare number."""
    digits = "".join(ch for ch in number if ch.isdigit())
    return f"{digits}@c.us"


def _format_message(event: AlarmEvent) -> str:
    parts = [f"Frigate alarm: {event.event_type.value}"]
    if event.zone_id:
        parts.append(f"in {event.zone_id}")
    parts.append(f"on {event.camera_id}")
    if event.confidence is not None:
        parts.append(f"({round(event.confidence * 100)}% confidence)")
    return " ".join(parts)


class AlarmWhatsAppNotifier:
    def __init__(self, config: WhatsAppNotifyConfig) -> None:
        self.config = config
        # Keyed by (camera_id, zone_id) so a burst of qualifying detections
        # during one incident doesn't spam every configured number.
        self._last_sent: dict[tuple[str, str | None], float] = {}

    def _within_cooldown(self, event: AlarmEvent) -> bool:
        key = (event.camera_id, event.zone_id)
        last = self._last_sent.get(key)
        return last is not None and time.time() - last < self.config.cooldown_seconds

    def notify(self, event: AlarmEvent) -> bool:
        if self._within_cooldown(event):
            logger.debug(
                "Skipping WhatsApp notification for %s/%s -- in cooldown",
                event.camera_id,
                event.zone_id,
            )
            return True

        body = _format_message(event)
        headers = {"X-API-Key": self.config.api_key}
        url = (
            f"{self.config.api_base_url}/sessions/{self.config.session_id}"
            "/messages/send-text"
        )

        success = True
        for number in self.config.to_numbers:
            try:
                response = requests.post(
                    url,
                    json={"chatId": _chat_id(number), "text": body},
                    headers=headers,
                    timeout=self.config.timeout_seconds,
                )
                if response.status_code >= 400:
                    logger.warning(
                        "WhatsApp notification to %s failed with status %s",
                        number,
                        response.status_code,
                    )
                    success = False
            except requests.RequestException as e:
                logger.warning("WhatsApp notification to %s failed: %s", number, e)
                success = False

        if success:
            self._last_sent[(event.camera_id, event.zone_id)] = time.time()
        return success
