"""Reporting queue: reliable delivery of AlarmEvents to a protocol sender.

Protocol-agnostic: wraps any `Callable[[AlarmEvent], bool]` (e.g. a SIA or
Contact ID client's encode+send), so this module knows nothing about SIA or
Contact ID specifically. Modeled on WebPushClient._process_notifications
(frigate/comms/webpush.py): a queue.Queue plus a single background thread,
no new dependency.

Events are processed one at a time, in order, including their retries, not
fanned out across multiple worker threads. For a home alarm system,
delivering events in order matters more than throughput.
"""

import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from frigate.alarm.event import AlarmEvent

logger = logging.getLogger(__name__)


class DeliveryStatus(str, Enum):
    pending = "pending"
    delivered = "delivered"
    failed = "failed"


@dataclass
class QueuedReport:
    event: AlarmEvent
    attempts: int = 0
    status: DeliveryStatus = DeliveryStatus.pending
    last_error: str | None = None


class ReportingQueue:
    """Queues AlarmEvents and delivers them via `send`, retrying failed
    attempts up to `max_attempts` with a linear backoff before giving up.

    `on_health_change`, if given, fires only on healthy<->unhealthy
    transitions (not on every event), so callers can drive a fault state
    without being spammed on every retried delivery.
    """

    def __init__(
        self,
        send: Callable[[AlarmEvent], bool],
        *,
        max_attempts: int = 5,
        retry_delay_seconds: float = 5.0,
        on_health_change: Callable[[bool], None] | None = None,
    ) -> None:
        self._send = send
        self._max_attempts = max_attempts
        self._retry_delay_seconds = retry_delay_seconds
        self._on_health_change = on_health_change

        self._queue: queue.Queue[AlarmEvent] = queue.Queue()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        self._healthy = True
        self._delivered_count = 0
        self._failed_count = 0

    @property
    def healthy(self) -> bool:
        return self._healthy

    @property
    def delivered_count(self) -> int:
        return self._delivered_count

    @property
    def failed_count(self) -> int:
        return self._failed_count

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name="alarm_reporting_queue", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._retry_delay_seconds + 1)

    def enqueue(self, event: AlarmEvent) -> None:
        self._queue.put(event)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                event = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            self._deliver_with_retry(event)

    def _deliver_with_retry(self, event: AlarmEvent) -> QueuedReport:
        """Attempt delivery, retrying on failure."""
        report = QueuedReport(event=event)

        while report.attempts < self._max_attempts and not self._stop_event.is_set():
            report.attempts += 1
            try:
                success = self._send(event)
            except Exception as e:
                success = False
                report.last_error = str(e)
                logger.warning(
                    "alarm report delivery attempt %s/%s failed: %s",
                    report.attempts,
                    self._max_attempts,
                    e,
                )

            if success:
                report.status = DeliveryStatus.delivered
                self._delivered_count += 1
                self._set_healthy(True)
                return report

            if report.attempts < self._max_attempts:
                time.sleep(self._retry_delay_seconds * report.attempts)

        report.status = DeliveryStatus.failed
        self._failed_count += 1
        self._set_healthy(False)
        logger.error(
            "alarm report delivery failed after %s attempts: %s",
            report.attempts,
            event,
        )
        return report

    def _set_healthy(self, healthy: bool) -> None:
        if healthy == self._healthy:
            return
        self._healthy = healthy
        if self._on_health_change is not None:
            self._on_health_change(healthy)
