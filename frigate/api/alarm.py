"""Alarm engine APIs."""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from peewee import DoesNotExist

from frigate.alarm.audit import record_alarm_audit
from frigate.alarm.state import ArmedMode, InvalidAlarmTransition
from frigate.alarm.trail import find_trail
from frigate.api.auth import allow_any_authenticated, require_role
from frigate.api.defs.request.alarm_body import (
    AlarmArmBody,
    AlarmEventFalseAlarmBody,
    AlarmZoneBypassBody,
)
from frigate.api.defs.response.alarm_response import (
    AlarmAuditLogResponse,
    AlarmEventLogResponse,
    AlarmEventLogSummaryResponse,
    AlarmEventResponse,
    AlarmStatusResponse,
    AlarmTrailResponse,
)
from frigate.api.defs.response.generic_response import GenericResponse
from frigate.api.defs.tags import Tags
from frigate.models import AlarmAuditLog, AlarmEventLog

logger = logging.getLogger(__name__)

router = APIRouter(tags=[Tags.alarm])


def _not_enabled_response() -> JSONResponse:
    return JSONResponse(
        content={"success": False, "message": "Alarm is not enabled."},
        status_code=400,
    )


@router.get(
    "/alarm/status",
    response_model=AlarmStatusResponse,
    dependencies=[Depends(allow_any_authenticated())],
    summary="Get alarm status",
    description="Current alarm state, armed mode, faults, zone status, and reporting health.",
)
def get_status(request: Request):
    alarm_system = request.app.alarm_system
    if alarm_system is None:
        return _not_enabled_response()

    return JSONResponse(content=alarm_system.status(), status_code=200)


@router.get(
    "/alarm/events",
    response_model=list[AlarmEventResponse],
    dependencies=[Depends(allow_any_authenticated())],
    summary="Get recent alarm events",
    description="Most recent alarm events, newest first.",
)
def get_events(request: Request, limit: int = 50):
    alarm_system = request.app.alarm_system
    if alarm_system is None:
        return _not_enabled_response()

    events = [
        {
            "event_type": e.event_type.value,
            "camera_id": e.camera_id,
            "timestamp": e.timestamp,
            "zone_id": e.zone_id,
            "object_type": e.object_type,
            "confidence": e.confidence,
            "source": e.source,
            "message": e.message,
            "object_id": e.object_id,
        }
        for e in alarm_system.recent_events(limit)
    ]
    return JSONResponse(content=events, status_code=200)


@router.get(
    "/alarm/audit",
    response_model=list[AlarmAuditLogResponse],
    dependencies=[Depends(allow_any_authenticated())],
    summary="Get the operator-action audit log",
    description="Recent arm/disarm/clear/bypass actions, newest first, with who performed each one and from where.",
)
def get_audit_log(request: Request, limit: int = 50):
    alarm_system = request.app.alarm_system
    if alarm_system is None:
        return _not_enabled_response()

    entries = [
        {
            # e.timestamp is naive (see audit.py on why), representing UTC
            # wall-clock time -- .timestamp() alone would interpret it as
            # local time and shift it by the container's UTC offset.
            "timestamp": e.timestamp.replace(tzinfo=UTC).timestamp(),
            "action": e.action,
            "source": e.source,
            "actor": e.actor,
            "camera": e.camera,
            "zone": e.zone,
            "details": e.details,
        }
        for e in AlarmAuditLog.select()
        .order_by(AlarmAuditLog.timestamp.desc())
        .limit(limit)
    ]
    return JSONResponse(content=entries, status_code=200)


@router.get(
    "/alarm/event_log",
    response_model=list[AlarmEventLogResponse],
    dependencies=[Depends(allow_any_authenticated())],
    summary="Get the persisted alarm event history",
    description="Historical, restart-surviving alarm events, newest first. Distinct from GET /alarm/events (live, most-recent-100, lost on restart).",
)
def get_event_log(request: Request, limit: int = 50, camera: str | None = None):
    alarm_system = request.app.alarm_system
    if alarm_system is None:
        return _not_enabled_response()

    query = AlarmEventLog.select().order_by(AlarmEventLog.timestamp.desc())
    if camera:
        query = query.where(AlarmEventLog.camera == camera)

    entries = [
        {
            "id": e.id,
            # e.timestamp is naive (see event_log.py on why), representing
            # UTC wall-clock time -- see get_audit_log above for the same
            # .replace(tzinfo=UTC) reasoning.
            "timestamp": e.timestamp.replace(tzinfo=UTC).timestamp(),
            "event_type": e.event_type,
            "camera": e.camera,
            "zone": e.zone,
            "object_type": e.object_type,
            "confidence": e.confidence,
            "false_alarm": e.false_alarm,
        }
        for e in query.limit(limit)
    ]
    return JSONResponse(content=entries, status_code=200)


@router.get(
    "/alarm/event_log/summary",
    response_model=AlarmEventLogSummaryResponse,
    dependencies=[Depends(allow_any_authenticated())],
    summary="Get alarm event/false-alarm rate summary",
    description="Total events, false-alarm count/rate, and a daily breakdown over the given window.",
)
def get_event_log_summary(request: Request, days: int = 30):
    alarm_system = request.app.alarm_system
    if alarm_system is None:
        return _not_enabled_response()

    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
    entries = list(AlarmEventLog.select().where(AlarmEventLog.timestamp >= since))

    total = len(entries)
    false_alarm_count = sum(1 for e in entries if e.false_alarm)

    # Grouped in Python, not SQL GROUP BY -- a home/small-business alarm's
    # event volume over a 30-day window doesn't justify the extra query
    # complexity.
    daily: dict[str, dict[str, int]] = {}
    for e in entries:
        day = e.timestamp.date().isoformat()
        bucket = daily.setdefault(day, {"total": 0, "false_alarm_count": 0})
        bucket["total"] += 1
        if e.false_alarm:
            bucket["false_alarm_count"] += 1

    return JSONResponse(
        content={
            "total": total,
            "false_alarm_count": false_alarm_count,
            "false_alarm_rate": (false_alarm_count / total) if total else None,
            "daily": [{"date": day, **counts} for day, counts in sorted(daily.items())],
        },
        status_code=200,
    )


@router.get(
    "/alarm/trail/{object_id}",
    response_model=AlarmTrailResponse,
    dependencies=[Depends(allow_any_authenticated())],
    summary="Get the cross-camera trail for a detection",
    description="Other cameras that likely saw the same person around the same time, using face recognition (named matches) and/or semantic search (visual matches) if enabled. Empty if neither is enabled, or the detection isn't found.",
)
def get_trail(request: Request, object_id: str, window_seconds: int = 120):
    alarm_system = request.app.alarm_system
    if alarm_system is None:
        return _not_enabled_response()

    matches = [
        {
            "camera": m.camera,
            "event_id": m.event_id,
            "timestamp": m.timestamp,
            "thumbnail": m.thumbnail,
            "match_type": m.match_type,
            "label": m.label,
            "score": m.score,
        }
        for m in find_trail(
            object_id, request.app.embeddings, window_seconds=window_seconds
        )
    ]
    return JSONResponse(content={"matches": matches}, status_code=200)


@router.post(
    "/alarm/event_log/{event_id}/false_alarm",
    response_model=GenericResponse,
    dependencies=[Depends(require_role(["admin"]))],
    summary="Mark or unmark a persisted alarm event as a false alarm",
    description="Used to compute the false-alarm rate on the health dashboard.",
)
def set_event_false_alarm(
    request: Request, event_id: int, body: AlarmEventFalseAlarmBody
):
    alarm_system = request.app.alarm_system
    if alarm_system is None:
        return _not_enabled_response()

    try:
        entry = AlarmEventLog.get_by_id(event_id)
    except DoesNotExist:
        return JSONResponse(
            content={
                "success": False,
                "message": f"Unknown alarm event: {event_id}",
            },
            status_code=404,
        )

    entry.false_alarm = body.false_alarm
    entry.save()

    record_alarm_audit(
        "false_alarm",
        "api",
        actor=request.headers.get("remote-user"),
        details={"event_log_id": event_id, "false_alarm": body.false_alarm},
    )
    return JSONResponse(
        content={"success": True, "message": "updated"}, status_code=200
    )


@router.post(
    "/alarm/arm",
    response_model=GenericResponse,
    dependencies=[Depends(require_role(["admin"]))],
    summary="Arm the alarm",
    description="Arm away or stay, with an optional exit delay override.",
)
def arm(request: Request, body: AlarmArmBody):
    alarm_system = request.app.alarm_system
    if alarm_system is None:
        return _not_enabled_response()

    mode = ArmedMode(body.mode)
    try:
        state = alarm_system.arm(mode, exit_delay_seconds=body.exit_delay_seconds)
    except InvalidAlarmTransition as e:
        logger.warning("rejected alarm arm request: %s", e)
        return JSONResponse(
            content={"success": False, "message": str(e)}, status_code=400
        )

    record_alarm_audit(
        "arm",
        "api",
        actor=request.headers.get("remote-user"),
        details={"mode": mode.value},
    )
    return JSONResponse(
        content={"success": True, "message": state.value}, status_code=200
    )


@router.post(
    "/alarm/disarm",
    response_model=GenericResponse,
    dependencies=[Depends(require_role(["admin"]))],
    summary="Disarm the alarm",
    description="Disarm the system. If an alarm is currently active, this silences it into alarm memory rather than clearing it (see /alarm/clear).",
)
def disarm(request: Request):
    alarm_system = request.app.alarm_system
    if alarm_system is None:
        return _not_enabled_response()

    state = alarm_system.disarm()
    record_alarm_audit("disarm", "api", actor=request.headers.get("remote-user"))
    return JSONResponse(
        content={"success": True, "message": state.value}, status_code=200
    )


@router.post(
    "/alarm/clear",
    response_model=GenericResponse,
    dependencies=[Depends(require_role(["admin"]))],
    summary="Clear alarm memory",
    description="Acknowledge and clear alarm memory after an alarm has been disarmed.",
)
def clear(request: Request):
    alarm_system = request.app.alarm_system
    if alarm_system is None:
        return _not_enabled_response()

    try:
        state = alarm_system.clear()
    except InvalidAlarmTransition as e:
        logger.warning("rejected alarm clear request: %s", e)
        return JSONResponse(
            content={"success": False, "message": str(e)}, status_code=400
        )

    record_alarm_audit("clear", "api", actor=request.headers.get("remote-user"))
    return JSONResponse(
        content={"success": True, "message": state.value}, status_code=200
    )


@router.post(
    "/alarm/zones/{camera}/{zone}/bypass",
    response_model=GenericResponse,
    dependencies=[Depends(require_role(["admin"]))],
    summary="Bypass or un-bypass an alarm zone",
    description="Temporarily exclude a zone from alarm evaluation. Bypass is per arm-cycle and clears automatically when the system disarms.",
)
def set_zone_bypass(
    request: Request, camera: str, zone: str, body: AlarmZoneBypassBody
):
    alarm_system = request.app.alarm_system
    if alarm_system is None:
        return _not_enabled_response()

    if alarm_system.adapter.get_rule(camera, zone) is None:
        return JSONResponse(
            content={
                "success": False,
                "message": f"Unknown alarm zone: {camera}/{zone}",
            },
            status_code=404,
        )

    if body.bypassed:
        alarm_system.bypass_zone(camera, zone)
    else:
        alarm_system.unbypass_zone(camera, zone)

    record_alarm_audit(
        "bypass" if body.bypassed else "unbypass",
        "api",
        actor=request.headers.get("remote-user"),
        camera=camera,
        zone=zone,
    )
    return JSONResponse(
        content={
            "success": True,
            "message": "bypassed" if body.bypassed else "unbypassed",
        },
        status_code=200,
    )
