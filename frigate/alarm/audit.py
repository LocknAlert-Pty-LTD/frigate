"""Operator-action audit log for the alarm engine.

Distinct from AlarmEvent/AlarmSystem.record_event(), which is for
qualifying *detections*. This is for deliberate operator actions --
arm/disarm/clear/bypass/unbypass -- who did it, from where, when. Needs
frigate.models, but unlike factory.py/ha_discovery.py that alone doesn't
pull in frigate.config's cv2 chain (frigate/models.py only imports
peewee/playhouse), so this module needs no exemption in
test_alarm_no_mqtt_dependency.py -- confirmed by that test passing
without one, not assumed. AlarmSystem itself still stays free of any DB
dependency by design; this lives entirely in the wiring layer (API/
dispatcher call sites), not in frigate/alarm/system.py.

Only successful actions are recorded, not rejected attempts (e.g. arming
an already-armed system) -- those already go to the application log via
logger.warning at each call site. A record of every attempt, including
failures, would be a different (larger) feature than what was asked for.
"""

from datetime import UTC, datetime
from typing import Any

from frigate.models import AlarmAuditLog


def record_alarm_audit(
    action: str,
    source: str,
    *,
    actor: str | None = None,
    camera: str | None = None,
    zone: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    AlarmAuditLog.create(
        # Naive UTC, not datetime.now(UTC) -- peewee's DateTimeField only
        # parses a handful of naive formats back out of sqlite ('%Y-%m-%d
        # %H:%M:%S(.%f)'); a tz-aware value stores with a "+00:00" suffix
        # none of those formats match, so reads silently come back as a
        # raw str instead of a datetime. Caught by actually running the
        # new GET /alarm/audit endpoint, not by reasoning about it.
        timestamp=datetime.now(UTC).replace(tzinfo=None),
        action=action,
        source=source,
        actor=actor,
        camera=camera,
        zone=zone,
        details=details,
    )
