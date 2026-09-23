"""Optional AI confirmation step for qualifying alarm detections.

Wraps GenAIClientManager.description_client -- the same provider Frigate
already uses for object/review descriptions, not a new AI integration --
with a background-thread call, mirroring the exact pattern
frigate/data_processing/post/object_descriptions.py uses for its own GenAI
calls: network-bound work never runs on the calling thread.

Fail-open by design: a missing provider, a network error, or an
unparseable response all count as "confirmed". This step exists only to
suppress false positives; it must never become a way for an AI outage (or
simply not having GenAI configured) to silently disable the alarm.
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

from frigate.alarm.event import AlarmEvent
from frigate.genai.manager import GenAIClientManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlarmVerificationResult:
    confirmed: bool
    reason: str | None = None


class AlarmAiVerifier:
    def __init__(self, genai_manager: GenAIClientManager) -> None:
        self._genai_manager = genai_manager

    def verify_async(
        self,
        event: AlarmEvent,
        thumbnail: bytes,
        on_result: Callable[[AlarmEvent, AlarmVerificationResult], None],
    ) -> None:
        """Kick off verification in a background thread. Never blocks the
        caller -- on_result is invoked from that thread once a result (or
        a fail-open default) is available."""
        threading.Thread(
            target=self._verify,
            name=f"alarm_ai_verify_{event.camera_id}_{event.zone_id}",
            daemon=True,
            args=(event, thumbnail, on_result),
        ).start()

    def _verify(
        self,
        event: AlarmEvent,
        thumbnail: bytes,
        on_result: Callable[[AlarmEvent, AlarmVerificationResult], None],
    ) -> None:
        client = self._genai_manager.description_client
        if client is None:
            logger.debug(
                "No GenAI description provider configured; skipping AI "
                "verification and triggering normally for %s/%s",
                event.camera_id,
                event.zone_id,
            )
            on_result(event, AlarmVerificationResult(confirmed=True))
            return

        try:
            result = client.generate_alarm_verification(
                camera=event.camera_id,
                zone=event.zone_id or "",
                label=event.object_type or "object",
                confidence=event.confidence or 0.0,
                event_type=event.event_type.value,
                thumbnail=thumbnail,
            )
        except Exception:
            logger.exception(
                "AI alarm verification failed for %s/%s; failing open",
                event.camera_id,
                event.zone_id,
            )
            on_result(event, AlarmVerificationResult(confirmed=True))
            return

        if result is None:
            logger.warning(
                "AI alarm verification returned no usable response for "
                "%s/%s; failing open",
                event.camera_id,
                event.zone_id,
            )
            on_result(event, AlarmVerificationResult(confirmed=True))
            return

        confirmed, reason = result
        if not confirmed:
            logger.info(
                "AI verification rejected alarm trigger for %s/%s: %s",
                event.camera_id,
                event.zone_id,
                reason,
            )
        on_result(event, AlarmVerificationResult(confirmed=confirmed, reason=reason))
