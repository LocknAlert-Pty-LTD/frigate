"""Tests for the (unverified, best-effort) SIA DC-09 protocol adapter.

These only prove internal self-consistency (our own encoder round-trips
through our own parser, framing/CRC/length invariants hold) and basic
transport plumbing over a loopback socket. They do NOT prove interoperability
with a real SIA DC-09 receiver -- see frigate/alarm/protocols/sia.py's module
docstring.
"""

import socket
import threading
import unittest

from frigate.alarm.event import AlarmEvent, AlarmEventType
from frigate.alarm.protocols.sia import (
    SiaClient,
    UnmappedAlarmEventType,
    encode_sia_message,
    is_ack,
    parse_sia_message,
)


def _event(event_type: AlarmEventType = AlarmEventType.burglary) -> AlarmEvent:
    return AlarmEvent(
        event_type=event_type,
        camera_id="front",
        timestamp=1_700_000_000.0,
        zone_id="driveway",
        object_type="person",
        confidence=0.9,
    )


class TestEncodeDecodeRoundTrip(unittest.TestCase):
    def test_round_trip_preserves_fields(self) -> None:
        message = encode_sia_message(_event(), account="1234", sequence=7)
        fields = parse_sia_message(message)
        self.assertEqual(fields.sequence, 7)
        self.assertEqual(fields.account, "1234")
        self.assertEqual(fields.data, "#1234|BAdriveway")

    def test_message_is_framed_with_lf_and_cr(self) -> None:
        message = encode_sia_message(_event(), account="1234", sequence=1)
        self.assertEqual(message[:1], b"\x0a")
        self.assertEqual(message[-1:], b"\x0d")

    def test_tampered_message_fails_crc_check(self) -> None:
        message = encode_sia_message(_event(), account="1234", sequence=1)
        tampered = message[:-2] + b"9" + message[-1:]
        with self.assertRaises(ValueError):
            parse_sia_message(tampered)

    def test_falls_back_to_camera_id_when_no_zone(self) -> None:
        event = AlarmEvent(
            event_type=AlarmEventType.panic,
            camera_id="front",
            timestamp=1_700_000_000.0,
        )
        message = encode_sia_message(event, account="1234", sequence=1)
        fields = parse_sia_message(message)
        self.assertEqual(fields.data, "#1234|PAfront")


class TestValidation(unittest.TestCase):
    def test_sequence_must_be_in_range(self) -> None:
        with self.assertRaises(ValueError):
            encode_sia_message(_event(), account="1234", sequence=0)
        with self.assertRaises(ValueError):
            encode_sia_message(_event(), account="1234", sequence=10000)

    def test_unmapped_event_type_raises(self) -> None:
        with self.assertRaises(UnmappedAlarmEventType):
            encode_sia_message(_event(AlarmEventType.fault), account="1234", sequence=1)

    def test_encrypted_raises_not_implemented(self) -> None:
        with self.assertRaises(NotImplementedError):
            encode_sia_message(_event(), account="1234", sequence=1, encrypted=True)


class TestAckDetection(unittest.TestCase):
    def test_detects_ack(self) -> None:
        self.assertTrue(is_ack(b"\x06ACK0001R0L0#1234[]\r"))

    def test_rejects_non_ack(self) -> None:
        self.assertFalse(is_ack(b"\x15NAK0001R0L0#1234[]\r"))


class TestSiaClientTransport(unittest.TestCase):
    def test_send_requires_connection(self) -> None:
        client = SiaClient("127.0.0.1", 0)
        with self.assertRaises(RuntimeError):
            client.send(b"anything")

    def test_send_over_loopback_socket(self) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        host, port = server.getsockname()

        def _serve() -> None:
            conn, _ = server.accept()
            with conn:
                conn.recv(1024)
                conn.sendall(b"ACK")

        thread = threading.Thread(target=_serve, daemon=True)
        thread.start()

        client = SiaClient(host, port, timeout=5.0)
        client.connect()
        try:
            message = encode_sia_message(_event(), account="1234", sequence=1)
            self.assertTrue(client.send(message))
        finally:
            client.close()
            thread.join(timeout=5.0)
            server.close()


if __name__ == "__main__":
    unittest.main()
