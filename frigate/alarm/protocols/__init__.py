"""Protocol adapters that encode canonical AlarmEvents for transmission to a
central monitoring station. Each adapter is isolated encoding/transport code;
none of them import frigate.alarm.engine or any Frigate detection type.
"""
