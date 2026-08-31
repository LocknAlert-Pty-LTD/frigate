"""Tests for AlarmAiVerifier.

Pure frigate.alarm.* plus frigate.genai.manager (which needs frigate.config
-> cv2), so this needs the real container, same as test_alarm_config.py.

genai_manager is duck-typed (a MagicMock exposing .description_client)
rather than a real GenAIClientManager -- AlarmAiVerifier only ever touches
that one property, matching how the class itself is documented.
"""

import threading
import time
import unittest
from unittest.mock import MagicMock

from frigate.alarm.ai_verification import AlarmAiVerifier, AlarmVerificationResult
from frigate.alarm.event import AlarmEvent, AlarmEventType

_TIMEOUT = 5.0


def _event(**overrides) -> AlarmEvent:
    base = {
        "event_type": AlarmEventType.burglary,
        "camera_id": "front",
        "timestamp": 1_700_000_000.0,
        "zone_id": "driveway",
        "object_type": "person",
        "confidence": 0.9,
    }
    base.update(overrides)
    return AlarmEvent(**base)


def _await_result(manager: MagicMock) -> tuple[AlarmEvent, AlarmVerificationResult]:
    """Run AlarmAiVerifier.verify_async and block for its callback,
    mirroring test_alarm_queue.py's threading.Event synchronization
    pattern rather than sleep-polling."""
    verifier = AlarmAiVerifier(manager)
    done = threading.Event()
    captured: dict = {}

    def on_result(event: AlarmEvent, result: AlarmVerificationResult) -> None:
        captured["event"] = event
        captured["result"] = result
        done.set()

    verifier.verify_async(_event(), b"fake-jpeg", on_result)

    if not done.wait(timeout=_TIMEOUT):
        raise AssertionError("verify_async callback never fired")

    return captured["event"], captured["result"]


class TestAlarmAiVerifier(unittest.TestCase):
    def test_no_provider_configured_fails_open(self) -> None:
        manager = MagicMock()
        manager.description_client = None

        _event_out, result = _await_result(manager)

        self.assertTrue(result.confirmed)

    def test_confirmed_response_is_passed_through(self) -> None:
        manager = MagicMock()
        manager.description_client.generate_alarm_verification.return_value = (
            True,
            "clearly a person",
        )

        _event_out, result = _await_result(manager)

        self.assertTrue(result.confirmed)
        self.assertEqual(result.reason, "clearly a person")

    def test_rejected_response_is_passed_through(self) -> None:
        manager = MagicMock()
        manager.description_client.generate_alarm_verification.return_value = (
            False,
            "just a cat",
        )

        _event_out, result = _await_result(manager)

        self.assertFalse(result.confirmed)
        self.assertEqual(result.reason, "just a cat")

    def test_unparseable_response_fails_open(self) -> None:
        manager = MagicMock()
        manager.description_client.generate_alarm_verification.return_value = None

        _event_out, result = _await_result(manager)

        self.assertTrue(result.confirmed)

    def test_provider_exception_fails_open(self) -> None:
        manager = MagicMock()
        manager.description_client.generate_alarm_verification.side_effect = (
            RuntimeError("network error")
        )

        _event_out, result = _await_result(manager)

        self.assertTrue(result.confirmed)

    def test_callback_receives_the_original_event(self) -> None:
        manager = MagicMock()
        manager.description_client = None
        event = _event(camera_id="back", zone_id="yard")

        verifier = AlarmAiVerifier(manager)
        done = threading.Event()
        captured: dict = {}

        def on_result(ev: AlarmEvent, result: AlarmVerificationResult) -> None:
            captured["event"] = ev
            done.set()

        verifier.verify_async(event, b"fake-jpeg", on_result)
        done.wait(timeout=_TIMEOUT)

        self.assertIs(captured["event"], event)

    def test_verify_async_does_not_block_the_caller(self) -> None:
        """The whole point is that a slow/blocking provider call never
        stalls the caller (AlarmDetectionThread's evaluation loop)."""
        manager = MagicMock()
        release = threading.Event()

        def slow_call(**_kwargs):
            release.wait(timeout=_TIMEOUT)
            return (True, "ok")

        manager.description_client.generate_alarm_verification.side_effect = slow_call

        verifier = AlarmAiVerifier(manager)
        start = time.monotonic()
        verifier.verify_async(_event(), b"fake-jpeg", lambda e, r: None)
        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 1.0)
        release.set()


if __name__ == "__main__":
    unittest.main()
