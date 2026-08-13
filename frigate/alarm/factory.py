"""Builds an AlarmSystem from a validated FrigateConfig.

This is the one place that knows how to turn config into a running
AlarmSystem: aggregating per-camera zone rules, and (if reporting is
configured) wiring a ReportingQueue to a SIA or Contact ID sender. Kept
separate from AlarmSystem itself so frigate/alarm/system.py stays free of
any dependency on frigate.config or the protocol adapters.
"""

import logging
from collections.abc import Callable

from frigate.alarm.event import AlarmEvent
from frigate.alarm.protocols.contact_id import (
    ContactIDClient,
    encode_contact_id_message,
)
from frigate.alarm.protocols.sia import SiaClient, encode_sia_message
from frigate.alarm.queue import ReportingQueue
from frigate.alarm.rules import ZoneAlarmRule
from frigate.alarm.system import AlarmSystem
from frigate.config.alarm import AlarmReportingConfig, AlarmReportingProtocol
from frigate.config.config import FrigateConfig

logger = logging.getLogger(__name__)


def _build_sia_sender(
    reporting: AlarmReportingConfig,
) -> Callable[[AlarmEvent], bool]:
    # Enforced by AlarmReportingConfig.require_receiver_details_when_enabled.
    assert reporting.host and reporting.port and reporting.account
    client = SiaClient(
        reporting.host, reporting.port, timeout=reporting.timeout_seconds
    )
    account = reporting.account
    sequence = {"n": 0}

    def send(event: AlarmEvent) -> bool:
        sequence["n"] = sequence["n"] % 9999 + 1
        message = encode_sia_message(event, account=account, sequence=sequence["n"])
        client.connect()
        try:
            return client.send(message)
        finally:
            client.close()

    return send


def _build_contact_id_sender(
    reporting: AlarmReportingConfig,
) -> Callable[[AlarmEvent], bool]:
    # Enforced by AlarmReportingConfig.require_receiver_details_when_enabled.
    assert reporting.host and reporting.port and reporting.account
    client = ContactIDClient(
        reporting.host, reporting.port, timeout=reporting.timeout_seconds
    )
    account = reporting.account

    def send(event: AlarmEvent) -> bool:
        message = encode_contact_id_message(event, account=account)
        client.connect()
        try:
            return client.send(message)
        finally:
            client.close()

    return send


def build_reporting_queue(reporting: AlarmReportingConfig) -> ReportingQueue | None:
    """Build a ReportingQueue for the configured protocol, or None if
    reporting is disabled (protocol == none)."""
    if reporting.protocol == AlarmReportingProtocol.none:
        return None

    if reporting.protocol == AlarmReportingProtocol.sia_dc09:
        send = _build_sia_sender(reporting)
    elif reporting.protocol == AlarmReportingProtocol.contact_id:
        send = _build_contact_id_sender(reporting)
    else:
        raise ValueError(f"unsupported reporting protocol: {reporting.protocol}")

    return ReportingQueue(
        send=send,
        max_attempts=reporting.max_attempts,
        retry_delay_seconds=reporting.retry_delay_seconds,
    )


def build_alarm_rules(config: FrigateConfig) -> dict[tuple[str, str], ZoneAlarmRule]:
    rules: dict[tuple[str, str], ZoneAlarmRule] = {}
    for camera_name, camera_config in config.cameras.items():
        rules.update(camera_config.alarm.build_rules(camera_name))
    return rules


def build_alarm_system(config: FrigateConfig) -> AlarmSystem | None:
    """Build a (not yet started) AlarmSystem from config, or None if the
    alarm engine is disabled. Starting it (and its reporting queue, if any)
    is the caller's responsibility."""
    if not config.alarm.enabled:
        return None

    rules = build_alarm_rules(config)
    reporting_queue = build_reporting_queue(config.alarm.reporting)

    return AlarmSystem(
        rules,
        default_exit_delay_seconds=config.alarm.exit_delay_seconds,
        reporting_queue=reporting_queue,
    )
