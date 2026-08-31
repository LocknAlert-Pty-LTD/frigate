"""Tests for AlarmWhatsAppNotifier -- pure frigate.alarm.notify_whatsapp,
no frigate.config/cv2/peewee dependency, so this runs on the bare host."""

import unittest
from unittest.mock import MagicMock, patch

from frigate.alarm.event import AlarmEvent, AlarmEventType
from frigate.alarm.notify_whatsapp import (
    AlarmWhatsAppNotifier,
    WhatsAppNotifyConfig,
    _chat_id,
    _format_message,
)


def _config(**overrides) -> WhatsAppNotifyConfig:
    defaults = dict(
        api_base_url="https://openwa.example.com/api",
        session_id="session1",
        api_key="secret",
        to_numbers=("+15551234567",),
        cooldown_seconds=300.0,
        timeout_seconds=30.0,
    )
    defaults.update(overrides)
    return WhatsAppNotifyConfig(**defaults)


def _event(**overrides) -> AlarmEvent:
    defaults = dict(
        event_type=AlarmEventType.burglary,
        camera_id="front",
        timestamp=1_700_000_000.0,
        zone_id="driveway",
        object_type="person",
        confidence=0.87,
    )
    defaults.update(overrides)
    return AlarmEvent(**defaults)


class TestChatId(unittest.TestCase):
    def test_strips_non_digits(self) -> None:
        self.assertEqual(_chat_id("+1 (555) 123-4567"), "15551234567@c.us")

    def test_bare_number(self) -> None:
        self.assertEqual(_chat_id("15551234567"), "15551234567@c.us")


class TestFormatMessage(unittest.TestCase):
    def test_includes_zone_camera_and_confidence(self) -> None:
        message = _format_message(_event())
        self.assertIn("burglary", message)
        self.assertIn("driveway", message)
        self.assertIn("front", message)
        self.assertIn("87%", message)

    def test_handles_missing_zone_and_confidence(self) -> None:
        message = _format_message(
            _event(zone_id=None, object_type=None, confidence=None)
        )
        self.assertNotIn("None", message)


class TestAlarmWhatsAppNotifier(unittest.TestCase):
    @patch("frigate.alarm.notify_whatsapp.requests.post")
    def test_successful_send(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=200)
        notifier = AlarmWhatsAppNotifier(_config())

        result = notifier.notify(_event())

        self.assertTrue(result)
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["headers"], {"X-API-Key": "secret"})
        self.assertEqual(kwargs["json"]["chatId"], "15551234567@c.us")

    @patch("frigate.alarm.notify_whatsapp.requests.post")
    def test_sends_to_every_configured_number(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=200)
        notifier = AlarmWhatsAppNotifier(
            _config(to_numbers=("+15551234567", "+15557654321"))
        )

        notifier.notify(_event())

        self.assertEqual(mock_post.call_count, 2)

    @patch("frigate.alarm.notify_whatsapp.requests.post")
    def test_non_2xx_response_returns_false(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=500)
        notifier = AlarmWhatsAppNotifier(_config())

        self.assertFalse(notifier.notify(_event()))

    @patch("frigate.alarm.notify_whatsapp.requests.post")
    def test_request_exception_returns_false(self, mock_post: MagicMock) -> None:
        import requests

        mock_post.side_effect = requests.ConnectionError("unreachable")
        notifier = AlarmWhatsAppNotifier(_config())

        self.assertFalse(notifier.notify(_event()))

    @patch("frigate.alarm.notify_whatsapp.requests.post")
    def test_cooldown_skips_second_send(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=200)
        notifier = AlarmWhatsAppNotifier(_config(cooldown_seconds=300.0))

        first = notifier.notify(_event())
        second = notifier.notify(_event())

        self.assertTrue(first)
        self.assertTrue(second)
        mock_post.assert_called_once()

    @patch("frigate.alarm.notify_whatsapp.requests.post")
    def test_cooldown_is_per_camera_and_zone(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=200)
        notifier = AlarmWhatsAppNotifier(_config(cooldown_seconds=300.0))

        notifier.notify(_event(camera_id="front", zone_id="driveway"))
        notifier.notify(_event(camera_id="back", zone_id="yard"))

        self.assertEqual(mock_post.call_count, 2)

    @patch("frigate.alarm.notify_whatsapp.requests.post")
    def test_failed_send_does_not_start_cooldown(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=500)
        notifier = AlarmWhatsAppNotifier(_config())

        notifier.notify(_event())
        notifier.notify(_event())

        self.assertEqual(mock_post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
