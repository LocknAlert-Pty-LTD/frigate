"""Tests for the alarm reporting queue."""

import threading
import unittest

from frigate.alarm.event import AlarmEvent, AlarmEventType
from frigate.alarm.queue import DeliveryStatus, ReportingQueue


def _event() -> AlarmEvent:
    return AlarmEvent(
        event_type=AlarmEventType.burglary,
        camera_id="front",
        timestamp=1_700_000_000.0,
        zone_id="driveway",
    )


class TestDeliverWithRetry(unittest.TestCase):
    """Exercises the delivery/retry logic directly and synchronously,
    without depending on the background thread's timing."""

    def test_delivers_on_first_success(self) -> None:
        rq = ReportingQueue(send=lambda event: True, retry_delay_seconds=0)
        report = rq._deliver_with_retry(_event())
        self.assertEqual(report.status, DeliveryStatus.delivered)
        self.assertEqual(report.attempts, 1)
        self.assertEqual(rq.delivered_count, 1)
        self.assertTrue(rq.healthy)

    def test_retries_until_success(self) -> None:
        attempts = {"count": 0}

        def send(event: AlarmEvent) -> bool:
            attempts["count"] += 1
            return attempts["count"] >= 3

        rq = ReportingQueue(send=send, max_attempts=5, retry_delay_seconds=0)
        report = rq._deliver_with_retry(_event())
        self.assertEqual(report.status, DeliveryStatus.delivered)
        self.assertEqual(report.attempts, 3)

    def test_gives_up_after_max_attempts(self) -> None:
        rq = ReportingQueue(
            send=lambda event: False, max_attempts=3, retry_delay_seconds=0
        )
        report = rq._deliver_with_retry(_event())
        self.assertEqual(report.status, DeliveryStatus.failed)
        self.assertEqual(report.attempts, 3)
        self.assertEqual(rq.failed_count, 1)
        self.assertFalse(rq.healthy)

    def test_exception_in_send_is_treated_as_a_failed_attempt(self) -> None:
        def send(event: AlarmEvent) -> bool:
            raise ConnectionError("receiver unreachable")

        rq = ReportingQueue(send=send, max_attempts=2, retry_delay_seconds=0)
        report = rq._deliver_with_retry(_event())
        self.assertEqual(report.status, DeliveryStatus.failed)
        self.assertEqual(report.attempts, 2)
        self.assertIn("receiver unreachable", report.last_error)


class TestHealthChangeCallback(unittest.TestCase):
    def test_fires_once_on_transition_to_unhealthy(self) -> None:
        calls = []
        rq = ReportingQueue(
            send=lambda event: False,
            max_attempts=1,
            retry_delay_seconds=0,
            on_health_change=calls.append,
        )
        rq._deliver_with_retry(_event())
        rq._deliver_with_retry(_event())
        self.assertEqual(calls, [False])

    def test_fires_on_recovery(self) -> None:
        calls = []
        results = iter([False, True])
        rq = ReportingQueue(
            send=lambda event: next(results),
            max_attempts=1,
            retry_delay_seconds=0,
            on_health_change=calls.append,
        )
        rq._deliver_with_retry(_event())
        rq._deliver_with_retry(_event())
        self.assertEqual(calls, [False, True])

    def test_no_callback_when_already_healthy(self) -> None:
        calls = []
        rq = ReportingQueue(
            send=lambda event: True,
            retry_delay_seconds=0,
            on_health_change=calls.append,
        )
        rq._deliver_with_retry(_event())
        self.assertEqual(calls, [])


class TestThreadedQueue(unittest.TestCase):
    def test_enqueue_delivers_via_background_thread(self) -> None:
        delivered = threading.Event()

        def send(event: AlarmEvent) -> bool:
            delivered.set()
            return True

        rq = ReportingQueue(send=send, retry_delay_seconds=0)
        rq.start()
        try:
            rq.enqueue(_event())
            self.assertTrue(delivered.wait(timeout=5.0))
            self.assertEqual(rq.delivered_count, 1)
        finally:
            rq.stop()

    def test_stop_joins_the_thread(self) -> None:
        rq = ReportingQueue(send=lambda event: True, retry_delay_seconds=0)
        rq.start()
        rq.stop()
        self.assertFalse(rq._thread.is_alive())


if __name__ == "__main__":
    unittest.main()
