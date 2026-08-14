"""Proves the alarm engine core has zero MQTT dependency.

This is a hard architectural constraint (see AGENTS.md phase 1): the alarm
engine must run correctly with MQTT fully disabled. Rather than trying to
spin up a real FrigateApp with MQTT turned off (needs the full dependency
set, not available in this sandbox -- see the phase 4/8/9 caveats), this
statically proves the constraint by parsing each core module's imports and
asserting none of them reference mqtt or the Dispatcher.

frigate/alarm/factory.py (needs frigate.config) and
frigate/alarm/detection_thread.py (needs frigate.comms.events_updater, the
internal ZMQ bus, plus a reference to mqtt_bridge to publish through) are
exempt -- those are explicitly the wiring/integration glue that connects
the alarm engine to the rest of Frigate, and are expected to depend on it.
Note detection_thread.py depends on the ZMQ event bus, not MQTT the
protocol -- that's the intended architecture (see AGENTS.md phase 1: "the
alarm engine subsystem should instantiate an EventUpdateSubscriber
directly"), it's just that "mqtt_bridge" as an import name trips this
scan's substring check, hence the exemption rather than a smarter check.
Everything else in frigate/alarm/ is the protocol-agnostic core (the state
machine, the detection adapter, the protocol encoders, the reporting queue,
the orchestrator) and must stay free of both MQTT and the ZMQ bus.
"""

import ast
import importlib
import unittest
from pathlib import Path

ALARM_PACKAGE_DIR = Path(__file__).resolve().parent.parent / "alarm"

# The wiring/integration glue layer, exempt from this constraint by design.
EXEMPT_MODULES = {"factory", "detection_thread"}

_FORBIDDEN_SUBSTRINGS = ("mqtt", "dispatcher")


def _core_module_files() -> list[Path]:
    files = []
    for path in ALARM_PACKAGE_DIR.rglob("*.py"):
        relative = path.relative_to(ALARM_PACKAGE_DIR)
        if relative.stem in EXEMPT_MODULES:
            continue
        files.append(path)
    return files


def _imported_module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


class TestNoMqttImportsInCoreModules(unittest.TestCase):
    def test_no_core_module_imports_mqtt_or_dispatcher(self) -> None:
        violations = []
        for path in _core_module_files():
            for name in _imported_module_names(path):
                lowered = name.lower()
                if any(forbidden in lowered for forbidden in _FORBIDDEN_SUBSTRINGS):
                    violations.append(f"{path.name} imports {name!r}")

        self.assertEqual(
            violations,
            [],
            "Core alarm modules must not depend on MQTT/Dispatcher: "
            + "; ".join(violations),
        )

    def test_found_a_reasonable_number_of_core_modules(self) -> None:
        # Guards against the scan silently finding nothing (e.g. a bad path)
        # and the test above passing vacuously.
        self.assertGreaterEqual(len(_core_module_files()), 8)


class TestCoreModulesImportCleanlyWithoutFrigateComms(unittest.TestCase):
    """Belt-and-suspenders: actually import the core modules and confirm
    frigate.comms never ends up in sys.modules as a side effect."""

    CORE_MODULES = [
        "frigate.alarm.state",
        "frigate.alarm.engine",
        "frigate.alarm.event",
        "frigate.alarm.rules",
        "frigate.alarm.adapter",
        "frigate.alarm.queue",
        "frigate.alarm.system",
        "frigate.alarm.protocols.sia",
        "frigate.alarm.protocols.contact_id",
    ]

    def test_importing_core_modules_does_not_pull_in_frigate_comms(self) -> None:
        import sys

        # Compare before/after rather than asserting an absolute empty
        # state: under full test-suite discovery, unrelated test modules
        # (e.g. test_dispatcher_runtime_state.py) may have already
        # legitimately imported frigate.comms.* earlier in the same
        # process. What matters is that *importing the alarm core* doesn't
        # add any new ones, not that the process-wide sys.modules is
        # pristine.
        comms_before = {
            name for name in sys.modules if name.startswith("frigate.comms")
        }

        for module_name in self.CORE_MODULES:
            importlib.import_module(module_name)

        comms_after = {name for name in sys.modules if name.startswith("frigate.comms")}
        newly_imported = comms_after - comms_before

        self.assertEqual(
            newly_imported,
            set(),
            f"Importing the alarm core pulled in new frigate.comms modules: {newly_imported}",
        )


if __name__ == "__main__":
    unittest.main()
