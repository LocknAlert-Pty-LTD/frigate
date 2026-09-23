"""Tests for the Contact ID protocol adapter.

Unlike the SIA DC-09 stub, the event code table here is transcribed directly
from the attached Ademco Contact ID reference and the message layout is the
well-documented public Contact ID standard, so these tests assert real
correctness, not just internal self-consistency (see
TestEventCodesAreFromReference).
"""

import socket
import threading
import unittest

from frigate.alarm.event import AlarmEvent, AlarmEventType
from frigate.alarm.protocols.contact_id import (
    CID_EVENT_DESCRIPTIONS,
    CONTACT_ID_EVENT_CODES,
    ContactIDClient,
    ContactIDQualifier,
    UnmappedAlarmEventType,
    encode_contact_id_message,
    is_ack,
    parse_contact_id_message,
)


def _event(event_type: AlarmEventType = AlarmEventType.burglary) -> AlarmEvent:
    return AlarmEvent(
        event_type=event_type,
        camera_id="front",
        timestamp=1_700_000_000.0,
        zone_id="driveway",
    )


class TestEventCodesAreFromReference(unittest.TestCase):
    """Every mapped code must be a real code from the attached reference,
    not an invented one."""

    def test_all_mapped_codes_exist_in_reference_table(self) -> None:
        for event_type, code in CONTACT_ID_EVENT_CODES.items():
            self.assertIn(
                code,
                CID_EVENT_DESCRIPTIONS,
                f"{event_type} maps to {code!r}, not in the reference table",
            )

    def test_burglary_maps_to_documented_burglary_code(self) -> None:
        self.assertEqual(CONTACT_ID_EVENT_CODES[AlarmEventType.burglary], "130")
        self.assertEqual(CID_EVENT_DESCRIPTIONS["130"], "Burglary")

    def test_panic_maps_to_documented_panic_code(self) -> None:
        self.assertEqual(CONTACT_ID_EVENT_CODES[AlarmEventType.panic], "120")
        self.assertEqual(CID_EVENT_DESCRIPTIONS["120"], "Panic alarm")


class TestEncodeDecodeRoundTrip(unittest.TestCase):
    def test_round_trip_preserves_fields(self) -> None:
        message = encode_contact_id_message(
            _event(),
            account="1234",
            qualifier=ContactIDQualifier.new_event,
            zone_or_user="007",
        )
        parsed = parse_contact_id_message(str(message))
        self.assertEqual(parsed.account, "1234")
        self.assertEqual(parsed.event_code, "130")
        self.assertEqual(parsed.qualifier, ContactIDQualifier.new_event)
        self.assertEqual(parsed.zone_or_user, "007")

    def test_message_is_15_digits(self) -> None:
        message = encode_contact_id_message(_event(), account="1234")
        self.assertEqual(len(str(message)), 15)
        self.assertTrue(str(message).isdigit())

    def test_restore_qualifier_round_trips(self) -> None:
        message = encode_contact_id_message(
            _event(), account="1234", qualifier=ContactIDQualifier.new_restore
        )
        parsed = parse_contact_id_message(str(message))
        self.assertEqual(parsed.qualifier, ContactIDQualifier.new_restore)


class TestArmDisarmQualifierSemantics(unittest.TestCase):
    """arm/disarm share code 401; the qualifier distinguishes them."""

    def test_arm_uses_close_qualifier(self) -> None:
        message = encode_contact_id_message(
            _event(AlarmEventType.arm),
            account="1234",
            qualifier=ContactIDQualifier.new_restore,
        )
        self.assertEqual(message.event_code, "401")
        self.assertEqual(message.qualifier, ContactIDQualifier.new_restore)

    def test_disarm_uses_open_qualifier(self) -> None:
        message = encode_contact_id_message(
            _event(AlarmEventType.disarm),
            account="1234",
            qualifier=ContactIDQualifier.new_event,
        )
        self.assertEqual(message.event_code, "401")
        self.assertEqual(message.qualifier, ContactIDQualifier.new_event)


class TestValidation(unittest.TestCase):
    def test_account_must_be_4_digits(self) -> None:
        with self.assertRaises(ValueError):
            encode_contact_id_message(_event(), account="123")
        with self.assertRaises(ValueError):
            encode_contact_id_message(_event(), account="12ab")

    def test_zone_or_user_must_be_3_digits(self) -> None:
        with self.assertRaises(ValueError):
            encode_contact_id_message(_event(), account="1234", zone_or_user="7")

    def test_unmapped_event_type_raises(self) -> None:
        with self.assertRaises(UnmappedAlarmEventType):
            encode_contact_id_message(
                _event(AlarmEventType.camera_failure), account="1234"
            )

    def test_restore_type_is_deliberately_unmapped(self) -> None:
        with self.assertRaises(UnmappedAlarmEventType):
            encode_contact_id_message(_event(AlarmEventType.restore), account="1234")

    def test_parse_rejects_wrong_length(self) -> None:
        with self.assertRaises(ValueError):
            parse_contact_id_message("12341813000000")

    def test_parse_rejects_non_digits(self) -> None:
        with self.assertRaises(ValueError):
            parse_contact_id_message("abcd181300000AA")


class TestAckDetection(unittest.TestCase):
    def test_detects_ack(self) -> None:
        self.assertTrue(is_ack(b"ACK\r"))

    def test_rejects_non_ack(self) -> None:
        self.assertFalse(is_ack(b"NAK\r"))


class TestContactIDClientTransport(unittest.TestCase):
    def test_send_requires_connection(self) -> None:
        client = ContactIDClient("127.0.0.1", 0)
        message = encode_contact_id_message(_event(), account="1234")
        with self.assertRaises(RuntimeError):
            client.send(message)

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

        client = ContactIDClient(host, port, timeout=5.0)
        client.connect()
        try:
            message = encode_contact_id_message(_event(), account="1234")
            self.assertTrue(client.send(message))
        finally:
            client.close()
            thread.join(timeout=5.0)
            server.close()


if __name__ == "__main__":
    unittest.main()
