"""Ademco/SIA Contact ID protocol adapter.

Event code data (CID_EVENT_DESCRIPTIONS below) is transcribed directly from
the attached Ademco Contact ID Report Codes reference (Magellan Programming
Guide, Appendix 1); the 3-digit CID# column, not the hex "Programming Value"
column (that column is for Ademco panel keypad programming, not the digits
transmitted on the wire). CONTACT_ID_EVENT_CODES, the mapping actually used
to encode a canonical AlarmEvent, only uses codes that exist in that table --
every value in it is asserted (see test_alarm_contact_id.py) to be a real key
in CID_EVENT_DESCRIPTIONS, so nothing here is an invented code.

The 15-digit message layout (ACCT + message type + qualifier + event code +
group + zone/user) is the standard, widely-documented Contact ID wire format,
not something reconstructed from the attached table -- that part is
high-confidence, unlike the SIA DC-09 stub in sia.py. What IS a judgment call
rather than a verified fact:

- Which single CID code best represents each coarser canonical
  AlarmEventType (e.g. `supervision` -> 380 "Sensor trouble" is a reasonable
  fit, not the only defensible choice). See CONTACT_ID_EVENT_CODES comments.
- `AlarmEventType.camera_failure` has no video-specific code in this
  reference (it's a burglar-panel code set) and `AlarmEventType.restore` has
  no code of its own -- Contact ID expresses "restore" as a qualifier on the
  original event's code, not a separate code. Both are deliberately
  unmapped; encoding either raises UnmappedAlarmEventType.
- The checksum digit used for DTMF transmission is omitted, matching common
  Contact-ID-over-IP implementations that rely on TCP for integrity instead.
  Verify this assumption against your specific receiver.
- Group/zone-user numbers: Frigate zones are named, not numbered. Callers
  must supply a numeric zone/user code explicitly; this adapter does not
  invent a zone numbering scheme.
"""

import socket
from dataclasses import dataclass
from enum import Enum

from frigate.alarm.event import AlarmEvent, AlarmEventType

# Transcribed from the attached Ademco Contact ID Report Codes reference.
# CID# -> description. Not exhaustive of every Ademco panel variant, just
# what's in the attached table.
CID_EVENT_DESCRIPTIONS: dict[str, str] = {
    "100": "Medical alarm",
    "101": "Pendant transmitter",
    "102": "Fail to report in",
    "110": "Fire alarm",
    "111": "Smoke",
    "112": "Combustion",
    "113": "Water flow",
    "114": "Heat",
    "115": "Pull station",
    "116": "Duct",
    "117": "Flame",
    "118": "Near alarm",
    "120": "Panic alarm",
    "121": "Duress",
    "122": "Silent",
    "123": "Audible",
    "124": "Duress - Access granted",
    "125": "Duress - Egress granted",
    "130": "Burglary",
    "131": "Perimeter",
    "132": "Interior",
    "133": "24-hour",
    "134": "Entry/Exit",
    "135": "Day/Night",
    "136": "Outdoor",
    "137": "Tamper",
    "138": "Near alarm",
    "139": "Intrusion verified",
    "140": "General alarm",
    "141": "Polling loop open",
    "142": "Polling loop short",
    "143": "Expansion module failure",
    "144": "Sensor tamper",
    "145": "Expansion module tamper",
    "146": "Silent burglary",
    "147": "Sensor supervision failure",
    "150": "24-hour non-burglary",
    "151": "Gas detected",
    "152": "Refrigeration",
    "153": "Loss of heat",
    "154": "Water leakage",
    "155": "Foil break",
    "156": "Day trouble",
    "157": "Low bottled gas level",
    "158": "High temperature",
    "159": "Low temperature",
    "161": "Loss of air flow",
    "162": "Carbon monoxide detected",
    "163": "Tank level",
    "200": "Fire supervisory",
    "201": "Low water pressure",
    "202": "Low CO2",
    "203": "Gate valve sensor",
    "204": "Low water level",
    "205": "Pump activated",
    "206": "Pump failure",
    "300": "System trouble",
    "301": "AC loss",
    "302": "Low system battery",
    "303": "RAM checksum bad",
    "304": "ROM checksum",
    "305": "System reset",
    "306": "Panel program changed",
    "307": "Self-test failure",
    "308": "System shutdown",
    "309": "Battery test failure",
    "310": "Ground fault",
    "311": "Battery missing/dead",
    "312": "Power supply over current limit",
    "313": "Engineer reset",
    "320": "Sounder/relay",
    "321": "Bell 1",
    "322": "Bell 2",
    "323": "Alarm relay",
    "324": "Trouble relay",
    "325": "Reversing relay",
    "326": "Notification appliance chk. #3",
    "327": "Notification appliance chk. #4",
    "330": "System peripheral",
    "331": "Polling loop open",
    "332": "Polling loop short",
    "333": "Expansion module failure",
    "334": "Repeater failure",
    "335": "Local printer paper out",
    "336": "Local printer failure",
    "337": "Exp. module DC loss",
    "338": "Exp. module low battery",
    "339": "Exp. module reset",
    "341": "Exp. module tamper",
    "342": "Exp. module AC loss",
    "343": "Exp. module self-test fail",
    "344": "RF receiver jam detect",
    "350": "Communication",
    "351": "Telco 1 fault",
    "352": "Telco 2 fault",
    "353": "Long range radio",
    "354": "Fail to communicate",
    "355": "Loss of radio supervision",
    "356": "Loss of central polling",
    "357": "Long range radio VSWR prob.",
    "370": "Protection loop",
    "371": "Protection loop open",
    "372": "Protection loop short",
    "373": "Fire trouble",
    "374": "Exit error alarm",
    "375": "Panic zone trouble",
    "376": "Hold-up zone trouble",
    "377": "Swinger trouble",
    "378": "Cross-zone trouble",
    "380": "Sensor trouble",
    "381": "Loss of supervision - RF",
    "382": "Loss of supervision - RPM",
    "383": "Sensor tamper",
    "384": "RF transmitter low battery",
    "385": "Smoke detector Hi sensitivity",
    "386": "Smoke detector Low sensitivity",
    "387": "Intrusion detector Hi sensitivity",
    "388": "Intrusion detector Low sensitivity",
    "389": "Sensor self-test failure",
    "391": "Sensor watch trouble",
    "392": "Drift compensation error",
    "393": "Maintenance alert",
    "400": "Open/Close",
    "401": "Open/Close by user",
    "402": "Group open/close",
    "403": "Automatic open/close",
    "406": "Cancel",
    "407": "Remote arm/disarm",
    "408": "Quick arm",
    "409": "Keyswitch open/close",
    "411": "Call back request made",
    "412": "Success - download access",
    "413": "Unsuccessful access",
    "414": "System shutdown",
    "415": "Dialer shutdown",
    "416": "Successful upload",
    "421": "Access denied",
    "422": "Access report by user",
    "423": "Forced access",
    "424": "Egress denied",
    "425": "Egress granted",
    "426": "Access door propped open",
    "427": "Access point door status monitor trouble",
    "428": "Access point request to exit",
    "429": "Access program mode entry",
    "430": "Access program mode exit",
    "431": "Access threat level change",
    "432": "Access relay/trigger fail",
    "433": "Access RTE shunt",
    "434": "Access DSM shunt",
    "441": "Armed Stay",
    "442": "Keyswitch armed Stay",
    "450": "Exception open/close",
    "451": "Early open/close",
    "452": "Late open/close",
    "453": "Failed to open",
    "454": "Failed to close",
    "455": "Auto-arm failed",
    "456": "Partial arm",
    "457": "Exit error (user)",
    "458": "User on premises",
    "459": "Recent close",
    "461": "Wrong code entry",
    "462": "Legal code entry",
    "463": "Re-arm after alarm",
    "464": "Auto-arm time extended",
    "465": "Panic alarm reset",
    "466": "Service ON/OFF premises",
    "520": "Sounder/Relay disabled",
    "521": "Bell 1 disabled",
    "522": "Bell 2 disabled",
    "523": "Alarm relay disabled",
    "524": "Trouble relay disabled",
    "525": "Reversing relay disabled",
    "526": "Notification appliance chk. #3 disabled",
    "527": "Notification appliance chk. #4 disabled",
    "531": "Module added",
    "532": "Module removed",
    "551": "Dialer disabled",
    "552": "Radio transmitter disabled",
    "570": "Zone bypass",
    "571": "Fire bypass",
    "572": "24Hr. zone bypass",
    "573": "Burglary bypass",
    "574": "Group bypass",
    "575": "Swinger bypass",
    "576": "Access zone shunt",
    "577": "Access point bypass",
    "601": "Manual trigger test",
    "602": "Periodic test report",
    "603": "Periodic RF transmission",
    "604": "Fire test",
    "605": "Status report to follow",
    "606": "Listen-in to follow",
    "607": "Walk test mode",
    "608": "Periodic test - system trouble present",
    "609": "Video transmitter active",
    "611": "Point test OK",
    "612": "Point not tested",
    "613": "Intrusion zone walk tested",
    "614": "Fire zone walk tested",
    "615": "Panic zone walk tested",
    "616": "Service request",
    "621": "Event log reset",
    "622": "Event log 50% full",
    "623": "Event log 90% full",
    "624": "Event log overflow",
    "625": "Time/Date reset",
    "626": "Time/Date inaccurate",
    "627": "Program mode entry",
    "628": "Program mode exit",
    "629": "32-hour event log marker",
    "630": "Schedule change",
    "631": "Exception schedule change",
    "632": "Access schedule change",
    "654": "System inactivity",
}

# Which CID code represents each canonical AlarmEventType. Every value here
# must be a real key in CID_EVENT_DESCRIPTIONS (asserted in tests). Choosing
# among several plausible codes for a coarser canonical type is a judgment
# call, not a guess at an undocumented value -- see module docstring.
CONTACT_ID_EVENT_CODES: dict[AlarmEventType, str] = {
    AlarmEventType.burglary: "130",  # Burglary
    AlarmEventType.panic: "120",  # Panic alarm
    AlarmEventType.tamper: "137",  # Tamper
    AlarmEventType.fault: "300",  # System trouble
    AlarmEventType.communication_failure: "354",  # Fail to communicate
    AlarmEventType.supervision: "380",  # Sensor trouble
    AlarmEventType.test: "602",  # Periodic test report
    # arm/disarm both use 401 "Open/Close by user"; which one you get is the
    # qualifier (see ContactIDQualifier), not a different code.
    AlarmEventType.arm: "401",
    AlarmEventType.disarm: "401",
}


class ContactIDQualifier(str, Enum):
    """The Q digit. For alarm-type codes this means new/restore/status; for
    Open/Close codes (401 etc.) the same digits mean opening/closing instead
    -- same values, context-dependent meaning, per the Contact ID standard.
    """

    new_event = "1"
    new_restore = "3"
    status = "6"


class UnmappedAlarmEventType(ValueError):
    """Raised when there's no Contact ID code for an event type in this table."""

    def __init__(self, event_type: AlarmEventType) -> None:
        super().__init__(f"no Contact ID event code mapping for {event_type.value}")
        self.event_type = event_type


@dataclass(frozen=True)
class ContactIDMessage:
    account: str
    message_type: str
    qualifier: ContactIDQualifier
    event_code: str
    group: str
    zone_or_user: str

    def __str__(self) -> str:
        return (
            f"{self.account}{self.message_type}{self.qualifier.value}"
            f"{self.event_code}{self.group}{self.zone_or_user}"
        )


def encode_contact_id_message(
    event: AlarmEvent,
    *,
    account: str,
    qualifier: ContactIDQualifier = ContactIDQualifier.new_event,
    group: str = "00",
    zone_or_user: str = "000",
    message_type: str = "18",
) -> ContactIDMessage:
    """Encode a canonical AlarmEvent as a Contact ID message.

    Frigate zones are named, not numbered; the caller is responsible for
    supplying `zone_or_user` (3 digits) if the receiver needs one, this
    adapter does not invent a numbering scheme.
    """
    if not (account.isdigit() and len(account) == 4):
        raise ValueError("account must be exactly 4 digits")
    if not (group.isdigit() and len(group) == 2):
        raise ValueError("group must be exactly 2 digits")
    if not (zone_or_user.isdigit() and len(zone_or_user) == 3):
        raise ValueError("zone_or_user must be exactly 3 digits")

    try:
        event_code = CONTACT_ID_EVENT_CODES[event.event_type]
    except KeyError:
        raise UnmappedAlarmEventType(event.event_type) from None

    return ContactIDMessage(
        account=account,
        message_type=message_type,
        qualifier=qualifier,
        event_code=event_code,
        group=group,
        zone_or_user=zone_or_user,
    )


def parse_contact_id_message(raw: str) -> ContactIDMessage:
    """Parse a 15-digit Contact ID message string (no checksum digit)."""
    if len(raw) != 15 or not raw.isdigit():
        raise ValueError(f"Contact ID message must be exactly 15 digits, got {raw!r}")

    account = raw[0:4]
    message_type = raw[4:6]
    qualifier = ContactIDQualifier(raw[6])
    event_code = raw[7:10]
    group = raw[10:12]
    zone_or_user = raw[12:15]

    return ContactIDMessage(
        account=account,
        message_type=message_type,
        qualifier=qualifier,
        event_code=event_code,
        group=group,
        zone_or_user=zone_or_user,
    )


def is_ack(response: bytes) -> bool:
    """Best-effort ACK detection over an IP transport. Contact ID's native
    ACK is a DTMF handshake tone; there's no single standard for what an
    IP-based receiver sends back, so this just substring-matches "ACK"."""
    return b"ACK" in response.upper()


class ContactIDClient:
    """Minimal TCP transport for Contact ID messages sent over IP.

    Contact ID is natively a DTMF-over-POTS protocol; "over IP" wrapping is
    receiver-specific and not standardized the way SIA DC-09 is. This sends
    the message string, CR-terminated, over a bare TCP socket and waits for
    a response. Verify framing/ACK behavior against your specific receiver
    before relying on this. A single connect/send/close cycle; retry and
    backoff belong to the reporting queue, not this transport.
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

    def send(self, message: ContactIDMessage) -> bool:
        """Send an already-encoded message and report whether the response
        looks like an ACK."""
        if self._sock is None:
            raise RuntimeError("not connected")
        self._sock.sendall((str(message) + "\r").encode("ascii"))
        response = self._sock.recv(1024)
        return is_ack(response)
