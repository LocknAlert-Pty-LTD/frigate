"""Tests for frigate.data_processing.common.license_plate.parkpow."""

import json
import threading
import unittest
from unittest.mock import MagicMock, patch

from frigate.config.classification import ParkPowConfig
from frigate.data_processing.common.license_plate.parkpow import (
    _post_to_parkpow,
    send_to_parkpow,
)


class _SyncThread:
    """Stand-in for threading.Thread that runs the target immediately."""

    def __init__(self, target=None, args=(), daemon=None) -> None:
        self._target = target
        self._args = args

    def start(self) -> None:
        self._target(*self._args)


def _config(**overrides) -> ParkPowConfig:
    defaults = dict(
        enabled=True,
        host="https://app.parkpow.com",
        token="secret-token",
        timeout=10.0,
    )
    defaults.update(overrides)
    return ParkPowConfig(**defaults)


class TestPostToParkPow(unittest.TestCase):
    @patch("frigate.data_processing.common.license_plate.parkpow.requests.post")
    def test_posts_expected_payload(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=200)

        _post_to_parkpow(
            _config(), "driveway", "ABC123", 0.95, 1_700_000_000.0, b"fake-jpeg"
        )

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://app.parkpow.com/api/v1/webhook-receiver/")
        self.assertEqual(kwargs["headers"], {"Authorization": "Token secret-token"})
        payload = json.loads(kwargs["data"]["json"])
        self.assertEqual(payload["data"]["results"], [{"plate": "ABC123", "score": 0.95}])
        self.assertEqual(payload["data"]["camera_id"], "driveway")
        self.assertEqual(kwargs["files"]["upload"][1], b"fake-jpeg")
        self.assertEqual(kwargs["timeout"], 10.0)

    @patch("frigate.data_processing.common.license_plate.parkpow.requests.post")
    def test_strips_trailing_slash_from_host(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=200)

        _post_to_parkpow(
            _config(host="https://app.parkpow.com/"),
            "driveway",
            "ABC123",
            0.95,
            1_700_000_000.0,
            None,
        )

        called_url = mock_post.call_args[0][0]
        self.assertEqual(called_url, "https://app.parkpow.com/api/v1/webhook-receiver/")
        self.assertIsNone(mock_post.call_args[1]["files"])

    @patch("frigate.data_processing.common.license_plate.parkpow.requests.post")
    def test_non_2xx_response_logs_and_does_not_raise(
        self, mock_post: MagicMock
    ) -> None:
        mock_post.return_value = MagicMock(status_code=500)

        _post_to_parkpow(_config(), "driveway", "ABC123", 0.95, 1_700_000_000.0, None)

    @patch("frigate.data_processing.common.license_plate.parkpow.requests.post")
    def test_request_exception_does_not_raise(self, mock_post: MagicMock) -> None:
        import requests

        mock_post.side_effect = requests.ConnectionError("unreachable")

        _post_to_parkpow(_config(), "driveway", "ABC123", 0.95, 1_700_000_000.0, None)


class TestSendToParkPow(unittest.TestCase):
    @patch(
        "frigate.data_processing.common.license_plate.parkpow.threading.Thread",
        _SyncThread,
    )
    @patch("frigate.data_processing.common.license_plate.parkpow.requests.post")
    def test_dispatches_when_enabled(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=200)

        send_to_parkpow(
            _config(), "driveway", "ABC123", 0.95, 1_700_000_000.0, None
        )

        mock_post.assert_called_once()

    @patch("frigate.data_processing.common.license_plate.parkpow.requests.post")
    def test_skips_when_disabled(self, mock_post: MagicMock) -> None:
        send_to_parkpow(
            _config(enabled=False), "driveway", "ABC123", 0.95, 1_700_000_000.0, None
        )

        mock_post.assert_not_called()

    @patch("frigate.data_processing.common.license_plate.parkpow.requests.post")
    def test_skips_when_no_token(self, mock_post: MagicMock) -> None:
        send_to_parkpow(
            _config(token=None), "driveway", "ABC123", 0.95, 1_700_000_000.0, None
        )

        mock_post.assert_not_called()

    @patch(
        "frigate.data_processing.common.license_plate.parkpow.threading.Thread",
        _SyncThread,
    )
    @patch("frigate.data_processing.common.license_plate.parkpow.requests.post")
    def test_uses_thumbnail_fallback_bytes(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=200)

        send_to_parkpow(
            _config(), "driveway", "ABC123", 0.95, 1_700_000_000.0, b"thumb-bytes"
        )

        files = mock_post.call_args[1]["files"]
        self.assertEqual(files["upload"][1], b"thumb-bytes")


if __name__ == "__main__":
    unittest.main()
