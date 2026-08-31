from typing import Any

from pydantic import BaseModel


class AlarmZoneStatusResponse(BaseModel):
    camera: str
    zone: str
    enabled: bool
    armed: bool
    bypassed: bool


class AlarmStatusResponse(BaseModel):
    state: str
    armed_mode: str | None
    is_alarm_active: bool
    is_alarm_memory: bool
    fault_reason: str | None
    last_transition: str
    reporting_healthy: bool | None
    whatsapp_healthy: bool | None
    zones: list[AlarmZoneStatusResponse]


class AlarmEventResponse(BaseModel):
    event_type: str
    camera_id: str
    timestamp: float
    zone_id: str | None
    object_type: str | None
    confidence: float | None
    source: str
    message: str | None
    object_id: str | None


class AlarmAuditLogResponse(BaseModel):
    timestamp: float
    action: str
    source: str
    actor: str | None
    camera: str | None
    zone: str | None
    details: dict[str, Any] | None


class AlarmEventLogResponse(BaseModel):
    id: int
    timestamp: float
    event_type: str
    camera: str
    zone: str | None
    object_type: str | None
    confidence: float | None
    false_alarm: bool


class AlarmEventLogDayResponse(BaseModel):
    date: str
    total: int
    false_alarm_count: int


class AlarmEventLogSummaryResponse(BaseModel):
    total: int
    false_alarm_count: int
    false_alarm_rate: float | None
    daily: list[AlarmEventLogDayResponse]


class AlarmTrailMatchResponse(BaseModel):
    camera: str
    event_id: str
    timestamp: float
    thumbnail: str
    match_type: str
    label: str | None
    score: float | None


class AlarmTrailResponse(BaseModel):
    matches: list[AlarmTrailMatchResponse]
