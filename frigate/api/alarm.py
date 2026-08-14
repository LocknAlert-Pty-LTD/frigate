"""Alarm engine APIs."""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from frigate.alarm.state import ArmedMode, InvalidAlarmTransition
from frigate.api.auth import allow_any_authenticated, require_role
from frigate.api.defs.request.alarm_body import AlarmArmBody
from frigate.api.defs.response.alarm_response import (
    AlarmEventResponse,
    AlarmStatusResponse,
)
from frigate.api.defs.response.generic_response import GenericResponse
from frigate.api.defs.tags import Tags

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
        }
        for e in alarm_system.recent_events(limit)
    ]
    return JSONResponse(content=events, status_code=200)


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

    return JSONResponse(
        content={"success": True, "message": state.value}, status_code=200
    )
