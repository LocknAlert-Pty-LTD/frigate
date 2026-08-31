"""SIA DC-09 protocol adapter.

************************************************************************
* UNVERIFIED / BEST-EFFORT STUB. Do not treat as SIA DC-09 compliant.  *
************************************************************************

No ANSI/SIA DC-09 specification text was available when this was written,
only general public knowledge of the protocol's shape (envelope framing,
that it wraps event data in brackets, that it's length- and CRC-prefixed).
Per explicit instruction this was built and flagged anyway rather than
skipped, but the following are NOT verified against the real spec and are
likely wrong in ways that would fail against a real monitoring receiver:

- CRC algorithm: implemented as CRC-16/ARC (poly 0xA001, init 0x0000).
  Some SIA implementations use a different table/polynomial; unconfirmed.
- Inner data block grammar: real DC-09 has a structured subfield token
  grammar (event qualifiers, ri/id/ti tokens, etc.). This only emits a
  simplified "[#account|code+zone]" block, not the full grammar.
- SIA_EVENT_CODES below only covers event types with reasonably common
  public citations (BA/PA/TA/OP/CL/RP). Event types with no confident
  mapping (fault, restore, camera_failure, communication_failure,
  supervision) are deliberately left unmapped rather than guessed;
  encoding one of those raises UnmappedAlarmEventType.
- Encryption is NOT implemented at all. DC-09 supports an AES-based
  encrypted variant; guessing at IV derivation/padding for a
  security-relevant feature is worse than refusing, so `encrypted=True`
  raises NotImplementedError.
- ACK/NAK/DUH handling: real DC-09 responses are structured; this only
  does a substring check for "ACK" in the raw response.

Before this touches a real receiver: get the actual ANSI/SIA DC-09 spec
and verify every point above.
"""

import re
import socket
from dataclasses import dataclass
from datetime import UTC, datetime

from frigate.alarm.event import AlarmEvent, AlarmEventType

LF = b"\x0a"
CR = b"\x0d"

# See module docstring: only mapped where there's reasonable public
# confidence. Deliberately incomplete.
SIA_EVENT_CODES: dict[AlarmEventType, str] = {
    AlarmEventType.burglary: "BA",
    AlarmEventType.panic: "PA",
    AlarmEventType.tamper: "TA",
    AlarmEventType.arm: "CL",
    AlarmEventType.disarm: "OP",
    AlarmEventType.test: "RP",
}

_MESSAGE_RE = re.compile(
    r'^(?P<crc>[0-9A-F]{4})(?P<length>\d{4})"SIA-DCS"'
    r"(?P<sequence>\d{4})R(?P<receiver>\w+)L(?P<prefix>\w+)#(?P<account>\w+)"
    r"\[(?P<data>[^\]]*)\]_(?P<timestamp>\d{2}:\d{2}:\d{2},\d{2}-\d{2}-\d{4})$"
)


class UnmappedAlarmEventType(ValueError):
    """Raised when there's no (even best-effort) SIA code for an event type."""

    def __init__(self, event_type: AlarmEventType) -> None:
        super().__init__(f"no SIA DC-09 event code mapping for {event_type.value}")
        self.event_type = event_type


@dataclass(frozen=True)
class SiaMessageFields:
    sequence: int
    receiver: str
    prefix: str
    account: str
    data: str
    timestamp: str


def _crc16(data: bytes) -> int:
    crc = 0x0000
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def encode_sia_message(
    event: AlarmEvent,
    *,
    account: str,
    sequence: int,
    receiver: str = "0",
    prefix: str = "0",
    encrypted: bool = False,
) -> bytes:
    """Encode a canonical AlarmEvent as a (best-effort) SIA DC-09 message."""
    if encrypted:
        raise NotImplementedError(
            "SIA DC-09 encryption is not implemented; see module docstring"
        )
    if not (1 <= sequence <= 9999):
        raise ValueError("sequence must be between 1 and 9999")

    try:
        code = SIA_EVENT_CODES[event.event_type]
    except KeyError:
        raise UnmappedAlarmEventType(event.event_type) from None

    zone_or_camera = event.zone_id or event.camera_id
    data_block = f"[#{account}|{code}{zone_or_camera}]"
    timestamp = datetime.fromtimestamp(event.timestamp, tz=UTC).strftime(
        "%H:%M:%S,%m-%d-%Y"
    )
    body = (
        f'"SIA-DCS"{sequence:04d}R{receiver}L{prefix}#{account}{data_block}_{timestamp}'
    )
    length_field = f"{len(body):04d}"
    crc = _crc16(f"{length_field}{body}".encode("ascii"))
    message = f"{crc:04X}{length_field}{body}"
    return LF + message.encode("ascii") + CR


def parse_sia_message(raw: bytes) -> SiaMessageFields:
    """Parse a message produced by encode_sia_message and verify its CRC.

    Only understands this module's own simplified framing; not a general
    DC-09 parser.
    """
    if not raw.startswith(LF) or not raw.endswith(CR):
        raise ValueError("message must be framed with LF...CR")

    text = raw[1:-1].decode("ascii")
    match = _MESSAGE_RE.match(text)
    if not match:
        raise ValueError(f"could not parse SIA message: {text!r}")

    fields = match.groupdict()
    expected_crc = _crc16(text[4:].encode("ascii"))
    if int(fields["crc"], 16) != expected_crc:
        raise ValueError("CRC mismatch")

    body_after_length = text[8:]
    if len(body_after_length) != int(fields["length"]):
        raise ValueError("length field does not match body length")

    return SiaMessageFields(
        sequence=int(fields["sequence"]),
        receiver=fields["receiver"],
        prefix=fields["prefix"],
        account=fields["account"],
        data=fields["data"],
        timestamp=fields["timestamp"],
    )


def is_ack(response: bytes) -> bool:
    """Best-effort ACK detection: treat any response containing "ACK" as
    success. Real DC-09 ACK/NAK/DUH framing is structured; unverified."""
    return b"ACK" in response.upper()


class SiaClient:
    """Minimal TCP transport for SIA DC-09 messages.

    A single connect/send/close cycle; retry and backoff belong to the
    reporting queue, not this transport.
    """

    def __init__(self, host: str, port: int, *, timeout: float = 10.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: socket.socket | None = None

    def connect(self) -> None:
        self._sock = socket.create_connection(
            (self.host, self.port), timeout=self.timeout
        )

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def send(self, message: bytes) -> bool:
        """Send an already-encoded message and report whether the response
        looks like an ACK."""
        if self._sock is None:
            raise RuntimeError("not connected")
        self._sock.sendall(message)
        response = self._sock.recv(1024)
        return is_ack(response)
