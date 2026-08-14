# Agent Instructions for Frigate NVR

This document provides coding guidelines and best practices for contributing to Frigate NVR, a complete and local NVR designed for Home Assistant with AI object detection.

## Project Overview

Frigate NVR is a realtime object detection system for IP cameras that uses:

- **Backend**: Python 3.13+ with FastAPI, OpenCV, TensorFlow/ONNX
- **Frontend**: React with TypeScript, Vite, TailwindCSS
- **Architecture**: Multiprocessing design with ZMQ and MQTT communication
- **Focus**: Minimal resource usage with maximum performance

## Code Review Guidelines

When reviewing code, do NOT comment on:

- Missing imports - Static analysis tooling catches these
- Code formatting - Ruff (Python) and Prettier (TypeScript/React) handle formatting
- Minor style inconsistencies already enforced by linters

## Python Backend Standards

### Python Requirements

- **Compatibility**: Python 3.13+
- **Language Features**: Use modern Python features:
  - Pattern matching
  - Type hints (comprehensive typing preferred)
  - f-strings (preferred over `%` or `.format()`)
  - Dataclasses
  - Async/await patterns

### Code Quality Standards

- **Formatting**: Ruff (configured in `pyproject.toml`)
- **Linting**: Ruff with rules defined in project config
- **Type Checking**: Use type hints consistently
- **Testing**: unittest framework - use `python3 -u -m unittest` to run tests
- **Language**: American English for all code, comments, and documentation
- **Punctuation**: Do not use em dashes in documentation, comments, or strings; reword with standard punctuation (commas, colons, parentheses, or separate sentences)

### Logging Standards

- **Logger Pattern**: Use module-level logger

  ```python
  import logging

  logger = logging.getLogger(__name__)
  ```

- **Format Guidelines**:
  - No periods at end of log messages
  - No sensitive data (keys, tokens, passwords)
  - Use lazy logging: `logger.debug("Message with %s", variable)`
- **Log Levels**:
  - `debug`: Development and troubleshooting information
  - `info`: Important runtime events (startup, shutdown, state changes)
  - `warning`: Recoverable issues that should be addressed
  - `error`: Errors that affect functionality but don't crash the app
  - `exception`: Use in except blocks to include traceback

### Error Handling

- **Exception Types**: Choose most specific exception available
- **Try/Catch Best Practices**:
  - Only wrap code that can throw exceptions
  - Keep try blocks minimal - process data after the try/except
  - Avoid bare exceptions except in background tasks

  Bad pattern:

  ```python
  try:
      data = await device.get_data()  # Can throw
      # ❌ Don't process data inside try block
      processed = data.get("value", 0) * 100
      result = processed
  except DeviceError:
      logger.error("Failed to get data")
  ```

  Good pattern:

  ```python
  try:
      data = await device.get_data()  # Can throw
  except DeviceError:
      logger.error("Failed to get data")
      return

  # ✅ Process data outside try block
  processed = data.get("value", 0) * 100
  result = processed
  ```

### Async Programming

- **External I/O**: All external I/O operations must be async
- **Best Practices**:
  - Avoid sleeping in loops - use `asyncio.sleep()` not `time.sleep()`
  - Avoid awaiting in loops - use `asyncio.gather()` instead
  - No blocking calls in async functions
  - Use `asyncio.create_task()` for background operations
- **Thread Safety**: Use proper synchronization for shared state

### Documentation Standards

- **Module Docstrings**: Concise descriptions at top of files
  ```python
  """Utilities for motion detection and analysis."""
  ```
- **Function Docstrings**: Required for public functions and methods

  ```python
  async def process_frame(frame: ndarray, config: Config) -> Detection:
      """Process a video frame for object detection.

      Args:
          frame: The video frame as numpy array
          config: Detection configuration

      Returns:
          Detection results with bounding boxes
      """
  ```

- **Comment Style**:
  - Explain the "why" not just the "what"
  - Keep lines under 88 characters when possible
  - Use clear, descriptive comments

### File Organization

- **API Endpoints**: `frigate/api/` - FastAPI route handlers
- **Configuration**: `frigate/config/` - Configuration parsing and validation
- **Detectors**: `frigate/detectors/` - Object detection backends
- **Events**: `frigate/events/` - Event management and storage
- **Utilities**: `frigate/util/` - Shared utility functions

## Frontend (React/TypeScript) Standards

### Internationalization (i18n)

- **CRITICAL**: Never write user-facing strings directly in components
- **Always use react-i18next**: Import and use the `t()` function

  ```tsx
  import { useTranslation } from "react-i18next";

  function MyComponent() {
    const { t } = useTranslation(["views/live"]);
    return <div>{t("camera_not_found")}</div>;
  }
  ```

- **Translation Files**: Add English strings to the appropriate json files in `web/public/locales/en`
- **Namespaces**: Organize translations by feature/view (e.g., `views/live`, `common`, `views/system`)

### Code Quality

- **Linting**: ESLint (see `web/.eslintrc.cjs`)
- **Formatting**: Prettier with Tailwind CSS plugin
- **Type Safety**: TypeScript strict mode enabled

### Component Patterns

- **UI Components**: Use Radix UI primitives (in `web/src/components/ui/`)
- **Styling**: TailwindCSS with `cn()` utility for class merging
- **State Management**: React hooks (useState, useEffect, useCallback, useMemo)
- **Data Fetching**: Custom hooks with proper loading and error states

### ESLint Rules

Key rules enforced:

- `react-hooks/rules-of-hooks`: error
- `react-hooks/exhaustive-deps`: error
- `no-console`: error (use proper logging or remove)
- `@typescript-eslint/no-explicit-any`: warn (always use proper types instead of `any`)
- Unused variables must be prefixed with `_`
- Comma dangles required for multiline objects/arrays

### File Organization

- **Pages**: `web/src/pages/` - Route components
- **Views**: `web/src/views/` - Complex view components
- **Components**: `web/src/components/` - Reusable components
- **Hooks**: `web/src/hooks/` - Custom React hooks
- **API**: `web/src/api/` - API client functions
- **Types**: `web/src/types/` - TypeScript type definitions

## Testing Requirements

### Backend Testing

- **Framework**: Python unittest
- **Run Command**: `python3 -u -m unittest`
- **Location**: `frigate/test/`
- **Coverage**: Aim for comprehensive test coverage of core functionality
- **Pattern**: Use `TestCase` classes with descriptive test method names
  ```python
  class TestMotionDetection(unittest.TestCase):
      def test_detects_motion_above_threshold(self):
          # Test implementation
  ```

### Test Best Practices

- Always have a way to test your work and confirm your changes
- Write tests for bug fixes to prevent regressions
- Test edge cases and error conditions
- Mock external dependencies (cameras, APIs, hardware)
- Use fixtures for test data

## Development Commands

### Python Backend

```bash
# Run all tests
python3 -u -m unittest

# Run specific test file
python3 -u -m unittest frigate.test.test_ffmpeg_presets

# Check formatting (Ruff)
ruff format --check frigate/

# Apply formatting
ruff format frigate/

# Run linter
ruff check frigate/

# Type check
python3 -u -m mypy --config-file frigate/mypy.ini frigate

# Regenerate the OpenAPI spec after adding, changing, or removing an API
# endpoint or its auth dependency — outputs docs/static/frigate-api.yaml,
# annotated with each endpoint's auth requirement (admin / any / camera /
# public). NEVER edit that file by hand. CI runs the --check variant and fails
# if it is out of date. (from repo root)
python3 generate_api_auth_spec.py
python3 generate_api_auth_spec.py --check
```

### Frontend (from web/ directory)

```bash
# Start dev server (AI agents should never run this directly unless asked)
npm run dev

# Build for production
npm run build

# Run linter
npm run lint

# Fix linting issues
npm run lint:fix

# Format code
npm run prettier:write

# E2E: first-time setup
npm install
npx playwright install chromium

# E2E: build the app and run all tests
npm run e2e:build && npm run e2e

# E2E: interactive UI for debugging
npm run e2e:ui

# E2E: run a specific spec
npx playwright test --config e2e/playwright.config.ts e2e/specs/live.spec.ts

# E2E: filter by name, or run only desktop/mobile
npx playwright test --config e2e/playwright.config.ts --grep="severity tab"
npx playwright test --config e2e/playwright.config.ts --project=desktop

# E2E: regenerate mock data after backend model changes (from repo root)
PYTHONPATH=. python3 web/e2e/fixtures/mock-data/generate-mock-data.py

# Regenerate config translations from Pydantic models — outputs to
# web/public/locales/en/config/{global,cameras}.json. NEVER edit those
# JSON files by hand; change the Pydantic field title/description and
# re-run this script. (from repo root)
python3 generate_config_translations.py

# Extract i18n keys from source into the locale files after adding
# new t() calls. Use the :ci variant to verify the locale files are
# in sync with source (fails if extraction would change anything).
npm run i18n:extract
npm run i18n:extract:ci
```

### Docker Development

AI agents should never run these commands directly unless instructed.

```bash
# Build local image
make local

# Build debug image
make debug
```

## Common Patterns

### API Endpoint Pattern

```python
from fastapi import APIRouter, Request
from frigate.api.defs.tags import Tags

router = APIRouter(tags=[Tags.Events])

@router.get("/events")
async def get_events(request: Request, limit: int = 100):
    """Retrieve events from the database."""
    # Implementation
```

After adding, changing, or removing an endpoint (or its auth dependency), regenerate the OpenAPI spec with `python3 generate_api_auth_spec.py` so `docs/static/frigate-api.yaml` stays in sync and the endpoint's auth requirement is documented. CI enforces this via the `--check` variant; never edit that file by hand.

### Configuration Access

```python
# Access Frigate configuration
config: FrigateConfig = request.app.frigate_config
camera_config = config.cameras["front_door"]
```

### Database Queries

```python
from frigate.models import Event

# Use Peewee ORM for database access
events = (
    Event.select()
    .where(Event.camera == camera_name)
    .order_by(Event.start_time.desc())
    .limit(limit)
)
```

## Common Anti-Patterns to Avoid

### ❌ Avoid These

```python
# Blocking operations in async functions
data = requests.get(url)  # ❌ Use async HTTP client
time.sleep(5)  # ❌ Use asyncio.sleep()

# Hardcoded strings in React components
<div>Camera not found</div>  # ❌ Use t("camera_not_found")

# Missing error handling
data = await api.get_data()  # ❌ No exception handling

# Bare exceptions in regular code
try:
    value = await sensor.read()
except Exception:  # ❌ Too broad
    logger.error("Failed")

# Returning exceptions in JSON responses
except ValueError as e:
    return JSONResponse(
        content={"success": False, "message": str(e)},
    )
```

### ✅ Use These Instead

```python
# Async operations
import aiohttp
async with aiohttp.ClientSession() as session:
    async with session.get(url) as response:
        data = await response.json()

await asyncio.sleep(5)  # ✅ Non-blocking

# Translatable strings in React
const { t } = useTranslation();
<div>{t("camera_not_found")}</div>  # ✅ Translatable

# Proper error handling
try:
    data = await api.get_data()
except ApiException as err:
    logger.error("API error: %s", err)
    raise

# Specific exceptions
try:
    value = await sensor.read()
except SensorException as err:  # ✅ Specific
    logger.exception("Failed to read sensor")

# Safe error responses
except ValueError:
    logger.exception("Invalid parameters for API request")
    return JSONResponse(
        content={
            "success": False,
            "message": "Invalid request parameters",
        },
    )
```

## WebSocket Broadcasts

Outbound WebSocket broadcasts go through a per-recipient classifier in `frigate/comms/ws.py` that enforces camera-level access. **The classifier is fail-closed: any topic it doesn't recognize is dropped for every client.** New outbound topics must be classified there or they'll silently disappear.

## Project-Specific Conventions

### Configuration Files

- Main config: `config/config.yml`

### Directory Structure

- Backend code: `frigate/`
- Frontend code: `web/`
- Docker files: `docker/`
- Documentation: `docs/`
- Database migrations: `migrations/`

### Code Style Conformance

Always conform new and refactored code to the existing coding style in the project:

- Follow established patterns in similar files
- Match indentation and formatting of surrounding code
- Use consistent naming conventions (snake_case for Python, camelCase for TypeScript)
- Maintain the same level of verbosity in comments and docstrings

## Additional Resources

- Documentation: https://docs.frigate.video
- Main Repository: https://github.com/blakeblackshear/frigate
- Home Assistant Integration: https://github.com/blakeblackshear/frigate-hass-integration

---

## Alarm Engine Project (branch: feature/alarm-engine)

**Goal**: extend Frigate into an AI-based alarm system — camera/zone-driven alarm
zones, arm/disarm (away/stay), entry/exit delay, alarm memory, fault/supervision,
persistence-based AI verification, SIA DC-09 and Contact ID reporting over IP.
Alarm engine core has zero MQTT dependency; MQTT is one optional output path.

**Phase tracker** (12 phases, commit + update this file after each):
1. Architectural analysis — **DONE, signed off by user**
2. Core alarm domain / state machine + unit tests — **DONE**. See
   `frigate/alarm/state.py` (`AlarmState`, `ArmedMode`, `ALLOWED_TRANSITIONS`
   table, `InvalidAlarmTransition`) and `frigate/alarm/engine.py`
   (`AlarmStateMachine`). 20 tests in `frigate/test/test_alarm_state_machine.py`,
   all passing; ruff/format/mypy clean. Key design choices: (a) entry/exit
   delay countdowns are NOT timed inside the state machine — callers own the
   timer and call `complete_exit_delay()`/`complete_entry_delay()` when it
   elapses, or `disarm()` to cancel; keeps the FSM pure and trivially unit
   testable. (b) `disarm()` during an active ALARM moves to ALARM_MEMORY, not
   DISARMED — `clear()` is the separate call that actually clears memory,
   matching the spec's distinct `alarm/disarm` vs `alarm/clear` API. (c) FAULT
   is enterable from any state and always restores whichever state was active
   before the fault, rather than having fixed predecessors/successors in the
   transition table — while faulted, no other transition is permitted (must
   `clear_fault()` first). This module has zero external dependencies
   (stdlib only), so it's a safe reuse target for the Phase 3 adapter and
   Phase 8 API layer.
3. Detection → canonical event adapter + tests — **DONE**. See
   `frigate/alarm/event.py` (`AlarmEventType`, `AlarmEvent` — the canonical,
   protocol-agnostic event), `frigate/alarm/rules.py` (`ZoneAlarmRule`, a
   plain dataclass, NOT the Pydantic config), and `frigate/alarm/adapter.py`
   (`DetectionAlarmAdapter.evaluate()`). 18 tests in
   `frigate/test/test_alarm_adapter.py`, all passing; ruff/format/mypy clean.
   Design choices: (a) the adapter takes `armed_mode: ArmedMode | None` as an
   explicit parameter rather than holding a reference to `AlarmStateMachine`
   — one-way dependency (detections -> adapter -> engine), the adapter never
   imports `engine.py`, and it's unit-testable without constructing an engine.
   (b) "alarm enabled" (global) is NOT checked inside the adapter — the
   caller simply doesn't construct/use one when alarm is disabled; adding an
   internal flag would be redundant state. (c) persistence/verification is
   one numeric knob, `verification_seconds` (0 = instant-trigger, >0 = must
   dwell that long), tracked per (camera, zone, object_id) in
   `adapter._pending`; `clear_object()` lets the caller drop tracking when an
   object leaves a zone or its tracked-object lifecycle ends (future wiring
   phase must call this or trackers leak for objects that never
   re-qualify). (d) entry/exit delay is NOT applied by the adapter — it
   returns whether a detection qualifies; the caller reads
   `rule.entry_delay_seconds` via `adapter.get_rule(camera, zone)` and passes
   it to `engine.trigger()`. (e) a real bug was caught by the tests during
   this phase and fixed before commit: the object-whitelist check used
   `if rule.objects and label not in rule.objects`, which skipped the check
   entirely (allowing everything through) when the whitelist was empty,
   contradicting the "empty = nothing qualifies" design; fixed to
   `if label not in rule.objects`.
4. Config schema, validation, backwards-compat tests — **DONE, but NOT
   runtime-verified in this sandbox — see caveat below, run the tests in a
   full dev/CI env before trusting this phase.**
   - `frigate/config/alarm.py`: `AlarmConfig` (global) — `enabled`,
     `exit_delay_seconds`, `enabled_in_config` (snapshotted in
     `FrigateConfig.post_validation`, mirroring the existing
     `self.notifications.enabled_in_config = self.notifications.enabled`
     line right next to it).
   - `frigate/config/camera/alarm.py`: `AlarmZoneConfig` (per Frigate zone —
     `enabled`, `objects`, `event`, `object_event_overrides`,
     `min_confidence`, `verification_seconds`, `delay` [entry delay],
     `arm_modes`) and `CameraAlarmConfig` (`enabled`, `zones: dict[str,
     AlarmZoneConfig]`). `AlarmZoneConfig.to_rule(camera, zone)` builds a
     `frigate.alarm.rules.ZoneAlarmRule` directly (resolving the phase-3
     "decide how a rule gets built from config" question as a method on the
     config model itself, not a separate bridging module — one conversion
     didn't justify a new layer). `CameraAlarmConfig.build_rules(camera)`
     maps all enabled zones to rules, empty dict if the camera's alarm is
     disabled.
   - `CameraConfig.alarm` field added to `frigate/config/camera/camera.py`
     ("Options with global fallback" section, alphabetically first).
     `FrigateConfig.alarm` field added to `frigate/config/config.py`
     ("Global config" section).
   - Three new validators in `frigate/config/config.py`, called from the
     existing per-camera loop in `post_validation` right after
     `verify_lpr_and_face`: `verify_alarm_zones_exist` (mirrors
     `verify_required_zones_exist`: an alarm zone key must exist in
     `camera.zones`), `verify_alarm_zone_objects_are_tracked` (mirrors
     `verify_zone_objects_are_tracked`: alarm zone `objects` must be a
     subset of `camera.objects.track`), `verify_alarm_requires_global_enabled`
     (mirrors `verify_lpr_and_face`: camera-level `alarm.enabled` requires
     global `alarm.enabled`).
   - Backwards compat: no migration needed, same as every other optional
     section — `default_factory=AlarmConfig`/`default_factory=
     CameraAlarmConfig` means an old config.yml with no `alarm:` key at all
     parses to `enabled=False` everywhere, zero behavior change.
   - Tests: `frigate/test/test_alarm_config.py` (backwards-compat defaults,
     zone-existence validation, object-tracked validation, global/camera
     enabled-gating, `to_rule()`/`build_rules()` correctness).
   - **Caveat, read before trusting this phase**: `frigate/config/__init__.py`
     unconditionally does `from .camera import *` etc., which pulls in
     `frigate.detectors` -> `frigate.plus` -> `import cv2`. This dev sandbox
     has no `cv2`/`fastapi`/`peewee`/etc. installed (same gap phases 1-3
     already hit for the other 73 pre-existing tests), so NOTHING under
     `frigate.config.*` — old or new — could be runtime-imported here, let
     alone executed. Verification for this phase was: `python3 -m py_compile`
     (syntax), `ruff check`/`ruff format --check` (clean), and manual
     line-by-line comparison against the exact precedent being mirrored
     (`verify_required_zones_exist`, `verify_lpr_and_face`,
     `NotificationConfig`). mypy was skipped deliberately, not just
     unavailable: `frigate/mypy.ini` has `[mypy-frigate.config.*]
     ignore_errors = true` project-wide, so it wouldn't have checked these
     files anyway. **Before relying on this phase, run
     `python3 -u -m unittest frigate.test.test_alarm_config` in a real
     dev/CI environment with full deps installed** — this has not been
     confirmed to actually pass, only to be free of syntax/lint errors and
     to structurally match working precedent.
5. SIA DC-09 adapter + tests — **DONE, but explicitly UNVERIFIED — do not
   treat as spec-compliant.** No ANSI/SIA DC-09 spec text was ever provided
   (only the Ademco Contact ID PDF, used in phase 6). I stopped and asked;
   given three options (provide the spec / skip to Contact ID first / stub
   it flagged-unverified), the user chose **stub it, flagged unverified**,
   overriding the project's default "don't implement without the spec"
   instruction — that's a deliberate, explicit choice on record, not a
   lapse.
   - `frigate/alarm/protocols/sia.py`: `encode_sia_message`/
     `parse_sia_message` (envelope: `LF CRC LENGTH "SIA-DCS" SEQ R L
     #ACCOUNT [DATA] _TIMESTAMP CR`), `SiaClient` (bare TCP
     connect/send/close, no retry — retry is phase 7's job), `is_ack`
     (substring check).
   - What's confidently correct: general envelope shape, framing bytes,
     that it's length + CRC prefixed. What's explicitly NOT verified and
     likely wrong against a real receiver: the CRC variant (used CRC-16/ARC,
     poly 0xA001 — other SIA implementations may use a different one), the
     inner data-block subfield grammar (real DC-09 has structured
     event-qualifier tokens; this emits a simplified
     `[#account|code+zone]`), and ACK/NAK/DUH framing (real DC-09 responses
     are structured; this just substring-matches "ACK").
   - `SIA_EVENT_CODES` in that file only maps event types with reasonably
     common public citations (burglary->BA, panic->PA, tamper->TA, arm->CL,
     disarm->OP, test->RP). fault/restore/camera_failure/
     communication_failure/supervision are deliberately left unmapped —
     encoding one raises `UnmappedAlarmEventType` rather than emitting a
     fabricated code. Do not add codes for these without the real spec.
   - Encryption is NOT implemented. DC-09 has an AES-based encrypted
     variant; `encrypted=True` raises `NotImplementedError` rather than
     guessing at IV/padding for something security-relevant — that's a
     harder line than the rest of the stub, worth keeping even if the
     envelope guesses above ever get "good enough" treatment.
   - Tests: `frigate/test/test_alarm_sia.py`, 11 tests, all passing,
     ruff/format/mypy clean — but these only prove internal
     self-consistency (our encoder round-trips through our own parser,
     CRC/length invariants hold, a loopback-socket transport test) and
     prove NOTHING about interoperability with a real monitoring receiver.
     No cv2/pydantic-config dependency here (unlike phase 4), so this phase
     actually ran in this sandbox, not just syntax-checked.
   - **Before this touches a real receiver**: get the actual ANSI/SIA
     DC-09 spec and re-verify every point above, especially the CRC
     algorithm and the subfield grammar.
6. Contact ID adapter + tests — **DONE, and materially more trustworthy
   than phase 5** since the event code table came from an actual attached
   reference, not memory.
   - `frigate/alarm/protocols/contact_id.py`: `CID_EVENT_DESCRIPTIONS` is
     the full CID#->description table transcribed directly from the
     attached Ademco Contact ID Report Codes PDF (the plain 3-digit CID#
     column — the wire format code — not the hex "Programming Value"
     column, which is for Ademco keypad panel programming, a different
     thing). `CONTACT_ID_EVENT_CODES` maps canonical `AlarmEventType` to a
     code from that table; a test (`TestEventCodesAreFromReference`)
     asserts every mapped code is a real key in the reference table, so
     "don't invent codes" is enforced, not just claimed.
   - Mapping: burglary->130, panic->120, tamper->137, fault->300,
     communication_failure->354, supervision->380 (a judgment call among
     several plausible codes, not a guess at an undocumented one),
     test->602, arm/disarm->401 (both share "Open/Close by user"; which one
     you get is the qualifier digit, not the code — Contact ID's Q digit
     means Open/Close for code 401 specifically, New/Restore for
     alarm-type codes elsewhere, same 1/3 values, context-dependent
     meaning, handled via `ContactIDQualifier`).
   - Deliberately unmapped, same "raise rather than fabricate" posture as
     phase 5: `camera_failure` (no video-specific code in this
     burglar-panel reference) and `restore` (Contact ID expresses restore
     as a qualifier on the *original* event's code, not as its own code —
     callers should re-encode the original event_type with
     `qualifier=new_restore`, not use `AlarmEventType.restore` here).
   - The 15-digit message layout (ACCT+type+qualifier+code+group+zone) is
     the standard public Contact ID wire format — high confidence, unlike
     phase 5's envelope. What's still a real caveat: no checksum digit
     (DTMF-only concept, assumed unnecessary over TCP — verify against
     your receiver), and "Contact ID over IP" transport itself isn't
     standardized the way DC-09 is (Contact ID is natively DTMF-over-POTS),
     so `ContactIDClient` is a reasonable-but-generic TCP transport, not a
     verified wire protocol.
   - Tests: `frigate/test/test_alarm_contact_id.py`, 18 tests, all passing,
     ruff/format/mypy clean, no cv2/config dependency so it actually ran
     here.
7. Reporting queue (send/ACK/retry/failure) + tests — **DONE**.
   `frigate/alarm/queue.py`: `ReportingQueue`, modeled directly on
   `WebPushClient._process_notifications`
   (`frigate/comms/webpush.py`) — a `queue.Queue[AlarmEvent]` plus one
   background thread, no new dependency. Protocol-agnostic: constructed
   with a plain `send: Callable[[AlarmEvent], bool]`, so it never imports
   `sia.py`/`contact_id.py` — the wiring layer (phase 9) passes in
   something like `lambda event: sia_client.send(encode_sia_message(event,
   ...))`.
   - Events are delivered one at a time, in order, retries included (not
     fanned across worker threads) — deliberate: for a home alarm, ordering
     matters more than throughput, and it mirrors the webpush precedent.
   - Retry is linear backoff (`retry_delay_seconds * attempt_number`) up to
     `max_attempts`, then the report is marked `failed`.
   - `on_health_change(bool)` fires only on healthy<->unhealthy
     transitions, not on every event, so it's usable as a fault-state
     trigger later (phase 8/9 camera/comms supervision) without being
     spammed on every retry.
   - Tests: `frigate/test/test_alarm_queue.py`, 9 tests, all passing,
     ruff/format/mypy clean. Most tests call the private
     `_deliver_with_retry` directly (deterministic, no thread timing to
     race) rather than only going through the real background thread,
     following the `test_maintainer.py` precedent of exercising internal
     methods directly; two tests do exercise the real
     `start()`/`enqueue()`/`stop()` thread path using a
     `threading.Event` to synchronize instead of sleep-polling.
   - Full alarm test suite re-run after this phase: 77 collected, 76 pass,
     1 error — the pre-existing/expected `test_alarm_config` cv2-import
     gap from phase 4, nothing new broken.
8. API endpoints + auth + tests — **DONE, but like phase 4, NOT
   runtime-verified in this sandbox (no fastapi installed) — see caveat
   below.**
   - `frigate/alarm/system.py`: new `AlarmSystem` orchestrator, deliberately
     kept separate from `AlarmStateMachine`. Bundles `state_machine`,
     `adapter` (`DetectionAlarmAdapter`, built from the same `rules` dict
     phase 4's `CameraAlarmConfig.build_rules()` produces), a bounded
     `deque` event history, and an optional `ReportingQueue`. `arm()`/
     `disarm()`/`clear()` delegate straight to the state machine;
     `record_event()` only does history + reporting-queue bookkeeping — it
     does NOT call `state_machine.trigger()` itself, since the caller (the
     phase-9 wiring layer) already has the qualifying `ZoneAlarmRule` via
     `adapter.get_rule()` and needs to decide the entry delay. `status()`
     and `zone_status()` back the GET endpoints. Tests:
     `frigate/test/test_alarm_system.py`, 15 tests, all passing (no
     fastapi/config dependency, pure `frigate.alarm.*`, so this part
     actually ran here).
   - `frigate/api/alarm.py`: the 5 endpoints from the spec (`GET
     alarm/status`, `GET alarm/events`, `POST alarm/arm`, `POST
     alarm/disarm`, `POST alarm/clear`). GET routes use
     `allow_any_authenticated()`; the 3 POST actions use
     `require_role(["admin"])`, following the exact pattern of
     `review.py`'s admin-gated POSTs. All 5 read `request.app.alarm_system`
     and return a 400 `GenericResponse`-shaped body (not a 500) when it's
     `None` (alarm disabled), mirroring `notification.py`'s
     `get_vapid_pub_key` 400-when-not-enabled precedent.
     `InvalidAlarmTransition` from a bad arm/clear request is caught and
     turned into a 400, not a 500.
   - `frigate/api/defs/request/alarm_body.py` (`AlarmArmBody`),
     `frigate/api/defs/response/alarm_response.py`
     (`AlarmStatusResponse`/`AlarmZoneStatusResponse`/`AlarmEventResponse`),
     `Tags.alarm` added to `frigate/api/defs/tags.py`.
   - Wiring: `frigate/api/fastapi_app.py` — `alarm_system: AlarmSystem |
     None = None` added as a new trailing optional parameter to
     `create_fastapi_app()` (additive, matches the existing `dispatcher`/
     `profile_manager`/`config_holder` optional-trailing-param pattern, so
     no existing caller breaks), `app.include_router(alarm.router)`,
     `app.alarm_system = alarm_system`. Actually constructing and starting
     an `AlarmSystem` from real config in `frigate/app.py` is phase 9's
     job, not this one — phase 8 only builds the API surface and the class
     it talks to.
   - `generate_api_auth_spec.py` also updated (import + its own
     independent `routers` list in `build_app()`) — CLAUDE.md is explicit
     that this file keeps its own router list separate from
     `fastapi_app.py` and both need updating for a new router to be
     classified correctly.
   - Tests: `frigate/test/http_api/test_http_alarm.py`, follows
     `BaseTestHttp`/`AuthTestClient` exactly, including the observed
     precedent of assigning `self.app.alarm_system = ...` directly after
     `create_app()` (mirrors `self.app.detected_frames_processor =
     MagicMock()` in `test_http_latest_frame.py`, since `create_app()`
     doesn't expose every optional app attribute as a parameter).
   - **Caveat, read before trusting this phase**: no `fastapi`/`peewee`/etc.
     installed in this sandbox (same gap as phase 4), so
     `frigate/api/alarm.py`, the `fastapi_app.py`/`generate_api_auth_spec.py`
     edits, and `test_http_alarm.py` could only be verified with
     `python3 -m py_compile` + `ruff check`/`ruff format --check` (all
     clean) plus careful manual comparison against `review.py`/
     `notification.py`/`base_http_test.py`, not by running them. **Before
     relying on this phase**: run
     `python3 -u -m unittest frigate.test.http_api.test_http_alarm` in a
     real dev/CI environment, AND run `python3 generate_api_auth_spec.py`
     (required by this repo's own CLAUDE.md after any endpoint change —
     could not be run here for the same missing-fastapi reason) to
     regenerate `docs/static/frigate-api.yaml` before this could pass CI's
     `--check` gate.
9. MQTT integration (optional path) + test engine runs with MQTT off —
   **DONE**, including real `frigate/app.py` wiring (the highest-risk phase
   so far — touches the actual process startup sequence, not just new
   isolated files). Read this whole entry before trusting it.
   - **Config gap-fill (belongs to phase 4, added now because phase 9
     needed it)**: `frigate/config/alarm.py` gained `AlarmReportingConfig`
     (`protocol`: none/sia_dc09/contact_id, `host`, `port`, `account`,
     `timeout_seconds`, `max_attempts`, `retry_delay_seconds`) and
     `AlarmConfig.reporting`. A `model_validator` requires host/port/account
     when protocol isn't `none`. Tests added to `test_alarm_config.py`
     (same cv2-import caveat as the rest of that file).
   - `frigate/alarm/factory.py`: `build_alarm_system(config) -> AlarmSystem
     | None`, `build_alarm_rules()`, `build_reporting_queue()`. Builds the
     SIA/Contact ID `send` callable (connect -> encode -> send -> close per
     attempt) from `AlarmReportingConfig`. This is glue, not core — it's
     the one alarm module allowed to import `frigate.config` — so like
     phase 4/8 it could only be verified via `py_compile`/`ruff`/`mypy`
     here (mypy *did* run cleanly on it — it statically resolves
     `frigate.config` fine without cv2 actually being installed, since
     mypy doesn't execute code — a useful distinction from runtime tests
     discovered this phase).
   - `frigate/alarm/mqtt_bridge.py`: `AlarmMqttBridge`, publishes
     `alarm/state`/`alarm/fault` (retained) and `alarm/event` (not
     retained) plus, critically, `<camera>/alarm_zone/<zone>/state` per
     zone — NOT the spec's literal `alarm/zone/<zone>/state`, because that
     doesn't start with a camera name and would be silently dropped by
     `frigate/comms/ws.py`'s fail-closed classifier (see phase 1 analysis).
     Takes a plain `Callable[[str, str, bool], None]` for publish, not a
     `Dispatcher` import, so it stays testable without the comms stack —
     confirmed by 6 tests in `test_alarm_mqtt_bridge.py` that all actually
     run here, including a regression guard specifically asserting the
     zone topic is camera-prefixed.
   - `frigate/alarm/detection_thread.py`: `AlarmDetectionThread`, a
     `threading.Thread` (modeled on `EventProcessor`) that subscribes to
     `EventUpdateSubscriber` — the internal MQTT-independent ZMQ event bus,
     not MQTT — and drives `adapter.evaluate()` ->
     `state_machine.trigger()` -> `alarm_system.record_event()` ->
     `mqtt_bridge.publish_*()`. The exact dict field names read off each
     tracked-object update (`current_zones`, `entered_zones`, `id`,
     `label`, `top_score`/`score`, `false_positive`, `frame_time`) were
     read directly from `TrackedObject.to_dict()`
     (`frigate/track/tracked_object.py:387-430`) and
     `EventUpdateSubscriber`/`Subscriber.check_for_update()`
     (`frigate/comms/events_updater.py`, `frigate/comms/zmq_proxy.py`) —
     not guessed, unlike the SIA/Contact ID situation. `InvalidAlarmTransition`
     from `trigger()` (e.g. a second qualifying detection while already in
     ALARM) is caught and logged at debug, not treated as an error — the
     event still gets recorded/reported.
   - **A real design bug was caught while writing this phase's tests, not
     before**: `AlarmSystem.armed_mode_for_evaluation` (added this phase)
     originally excluded `AlarmState.alarm` from the states that permit
     evaluation, meaning a second zone triggering while an alarm was
     already sounding would silently never get recorded or reported. Fixed
     by including `alarm` in that set — a genuinely different question
     from "should this trigger a *new* alarm" (no, `state_machine.trigger()`
     correctly rejects that) vs. "should this qualifying detection still be
     logged and reported" (yes). `EXIT_DELAY` deliberately still excluded
     (motion while walking out during exit delay shouldn't trigger).
   - **Test: "engine runs correctly with MQTT off"** (explicitly required
     by the original spec) — `frigate/test/test_alarm_no_mqtt_dependency.py`,
     3 tests, all passing. Rather than spinning up a real FrigateApp with
     MQTT disabled (impossible here, needs the full dependency set), this
     statically parses every core module's imports via `ast` and asserts
     none reference `mqtt` or `dispatcher`, PLUS actually imports the 9
     core modules and confirms `frigate.comms` never lands in
     `sys.modules` as a side effect. `factory.py` and
     `detection_thread.py` are explicitly exempted (documented in the file)
     as the wiring/glue layer that's expected to depend on
     `frigate.config`/the internal ZMQ bus — everything else (`state.py`,
     `engine.py`, `event.py`, `rules.py`, `adapter.py`, `queue.py`,
     `system.py`, `protocols/*`) is asserted clean.
   - **`frigate/test/test_alarm_detection_thread.py` — 9 tests, and they
     genuinely run here**, unlike everything else touching `frigate.app`/
     `frigate.config` this phase. `frigate.comms.events_updater` (which
     needs `pyzmq`, not installed here) is mocked out of `sys.modules`
     before importing `AlarmDetectionThread`, following the exact pattern
     already established in `frigate/test/test_maintainer.py`. Because
     `AlarmDetectionThread` doesn't import `frigate.config` at all (unlike
     `test_maintainer.py`'s target), this sidesteps the cv2 chain entirely
     and actually exercises `_evaluate()` and `run()`'s logic end to end.
   - `frigate/app.py` wiring (read `init_dispatcher`/`start_event_processor`/
     `start()`/`stop()` from source before editing, not from memory of the
     phase-1 research summary): `init_alarm_system()` (builds
     `self.alarm_system`/`self.alarm_mqtt_bridge`/
     `self.alarm_detection_thread`, called right after `init_dispatcher()`
     since the bridge needs `self.dispatcher.publish`) and
     `start_alarm_system()` (starts the reporting queue and detection
     thread, no-ops cleanly if alarm is disabled) added to the `start()`
     sequence; `alarm_system=self.alarm_system` added to the
     `create_fastapi_app(...)` call; `stop()` stops the detection thread
     and reporting queue before `self.dispatcher.stop()`.
   - **Caveat, the most important one in this file**: `frigate/app.py` is
     ~750 lines and could not be executed or imported at all in this
     sandbox (pulls in cv2, zmq, peewee, fastapi, everything). Verification
     here was `python3 -m py_compile` (passes), `ruff check`/`ruff format`
     (clean), and `mypy` (clean — zero errors in `frigate/app.py` or any
     file this project touched; the 105 errors mypy reported while
     following imports are 100% pre-existing, in numpy/opencv-heavy files
     never touched this session like `norfair_tracker.py` and
     `license_plate/mixin.py`, almost certainly a numpy/stub version
     mismatch between this sandbox and the real dev container — verified
     by grepping mypy's output for any file this session created/edited
     and finding none).
     - **UPDATE (see "Live verification" below, post phase-12 review):**
       the "boot a real instance" step this caveat called for has now
       actually been done, in the user's real devcontainer, not this
       sandbox. It found and this branch now fixes a real bug (exit/entry
       delay never completing — see that section). MQTT topic publishing
       itself still hasn't been observed (no MQTT broker was configured in
       that test), so that specific piece is still open.
10. Frontend components — **DONE, and this is the first phase with real
    tooling verification** (`node_modules` wasn't installed; ran
    `npm install` in this sandbox specifically to unlock `tsc`/`eslint`/
    `vite build`/`i18next-cli extract`, unlike every backend phase that
    depended on `cv2`/`fastapi`/etc.).
    - Deliberately did NOT hand-build a settings form for `AlarmConfig`/
      `CameraAlarmConfig`/`AlarmZoneConfig`: every field in those Pydantic
      models already has `title`/`description` (from phases 4 and 9), so
      the existing schema-driven `ConfigSectionTemplate` machinery
      generates one automatically once `python3
      generate_config_translations.py` is run in a full environment (could
      not run it here, same cv2 gap as everything backend). Registered via
      `createSectionPage("alarm", "global")` and `createSectionPage("alarm",
      "camera")` in `web/src/pages/Settings.tsx`, exactly mirroring
      `createSectionPage("lpr", "camera")` etc. — no new form code.
    - What genuinely needed hand-building: `web/src/views/settings/
      AlarmView.tsx`, a live operational view (current state, armed mode,
      arm-away/arm-stay/disarm/clear buttons, zone status, fault banner,
      reporting health, recent-events table), modeled on
      `MotionTunerView.tsx`. Registered as its own new `settingsGroups`
      entry (`label: "alarm"`), not folded into an existing group, since
      it's a distinct subsystem the same way "cameras" and "system" are.
    - Data fetching is `useSWR` polling (`refreshInterval: 5000`) against
      `GET alarm/status`/`GET alarm/events`, not the WS pub/sub layer
      (`web/src/api/ws.ts`). This is a deliberate scope cut, not an
      oversight: wiring real-time topics into `ws.ts`'s
      `processWsMessage`/`applyCameraActivity` would need to be blind-coded
      against source I can't execute, unlike the backend where `tsc`
      exists as a safety net for API/type mistakes but not for runtime WS
      message-shape mistakes. Upgrading to WS-driven live updates (mirroring
      `useAutoFrigateStats`'s SWR-snapshot + WS-override pattern) is the
      natural next step once this can be verified in a browser.
    - New files: `web/src/types/alarm.ts` (response types matching
      `frigate/api/defs/response/alarm_response.py` by hand — there's no
      shared codegen between the two), `web/public/locales/en/views/
      alarm.json` (new i18n namespace, registered in `web/src/utils/
      i18n.ts`), `menu.alarm`/`menu.alarmStatus`/`menu.globalAlarm`/
      `menu.cameraAlarm` keys added to `web/public/locales/en/views/
      settings.json`.
    - Actually verified in this sandbox (all passed, not just
      syntax-checked): `npx tsc --noEmit` (caught and fixed a real bug —
      `Heading` only supports `h1`-`h4`, I'd used `h5`), `npx eslint`
      (clean after one auto-fix), `npx vite build --base=/BASE_PATH/`
      (production build succeeds, only pre-existing unrelated chunk-size
      warnings), `npx i18next-cli extract --ci` (exit 0 — every `t()` call
      in the new code has a real matching key, nothing missing or unused).
    - **Not verified, explicitly**: visual appearance and live
      interaction. No browser was opened, `npm run dev` was not started
      (CLAUDE.md: agents should never start the dev server unless asked),
      no screenshot taken, no e2e/Playwright spec added. This codebase has
      no component-level unit tests to mirror (`web/src/**/*.test.tsx`
      doesn't exist anywhere — e2e/Playwright is the only test layer), so
      "add a test" for this phase means an e2e spec, which needs a live
      built app + backend (mock data doesn't cover alarm endpoints yet)
      and was out of scope here. **Before trusting this phase**: run
      `npm run dev`, open Settings → Alarm, and confirm arm/disarm/clear
      actually work end-to-end against a real backend with
      `alarm.enabled: true`.
11. Full test suite run, fix regressions — **DONE**.
    - `python3 -u -m unittest discover -s frigate/test`: 217 tests
      collected, 75 errors — confirmed by name that exactly 2 are
      alarm-related (`test_alarm_config`, `test_http_alarm`, both the
      already-documented cv2/fastapi-missing gaps from phases 4/8) and the
      remaining 73 are the pre-existing baseline unrelated to this branch
      (same count as before phase 1 started). Zero new backend regressions.
    - **A real regression was caught by this run, not before**:
      `test_alarm_no_mqtt_dependency.py`'s
      `TestCoreModulesImportCleanlyWithoutFrigateComms` passed in isolation
      but failed under full-suite `discover`, because other unrelated test
      files (e.g. `test_dispatcher_runtime_state.py`) legitimately import
      `frigate.comms.*` earlier in the same test process, and the test was
      asserting an absolute-empty `sys.modules` state rather than "did
      *importing the alarm core* add anything new." Fixed to snapshot
      `sys.modules` before/after and diff, which is what the test actually
      meant to assert. Good illustration of why isolated per-file test runs
      aren't sufficient — this phase existed for exactly this reason.
    - `ruff check frigate/` and `ruff format --check frigate/`: clean
      across the whole backend (356 files), not just alarm files.
    - `python3 -u -m mypy --config-file frigate/mypy.ini frigate/`: 111
      errors in 28 files, all outside anything created/modified this
      project (confirmed by grepping the output for
      `frigate/alarm|frigate/api/alarm|frigate/app.py|frigate/config/alarm`
      — zero matches). Same pre-existing numpy/stub-version gap noted in
      phase 9, now confirmed against the *entire* codebase, not just the
      files this branch touches.
    - Frontend: `npx eslint --ext .jsx,.js,.tsx,.ts --ignore-path
      .gitignore .` across the whole `web/` tree — clean, no output.
    - **Still not done, carried forward as the real "phase 11" for
      whoever picks this up next**: none of the backend caveats from
      phases 4/8/9 (run the config/API/http_alarm tests, boot a real
      FrigateApp instance) have been resolved — this phase only confirms
      *this sandbox's* tests are internally consistent and regression-free,
      not that the untested-here code actually works. That full
      dev/CI-environment verification pass is still outstanding.
12. Final architecture review against phase 1 — **DONE**. All 12 phases
    complete; branch `feature/alarm-engine` has 17 commits from phase 1
    through this one.
    - **Drift from the phase 1 plan, and why**:
      1. **SIA DC-09 (phase 5)** — the single biggest deviation. The
         original instructions (both the project bootstrap and section
         5.5) say to stop rather than implement a protocol from memory.
         No spec was ever provided; the user was given three explicit
         options (provide the spec / do Contact ID first / stub it
         flagged-unverified) and chose the third, overriding the default
         rule on record. `frigate/alarm/protocols/sia.py` is real,
         tested code, but "tested" only means internally self-consistent
         — it has never been checked against the actual ANSI/SIA DC-09
         spec text and should not be trusted against a real receiver
         without that check.
      2. **Frontend config UI** — phase 1 proposed a fully custom view;
         what got built instead reuses the existing schema-driven
         `ConfigSectionTemplate` form for all of `AlarmConfig`/
         `CameraAlarmConfig`/`AlarmZoneConfig` (via `createSectionPage`),
         and reserves the hand-built `AlarmView.tsx` for only the parts
         that form genuinely can't do (arm/disarm buttons, live status,
         event log). This is a scope reduction, not a shortfall: every
         config field already had `title`/`description` from phases 4/9,
         so a second hand-built form would have been duplicate work for
         no benefit.
      3. **`AlarmReportingConfig` (SIA/Contact ID receiver host/port/
         account) wasn't planned as its own line item** in phase 1 or
         built in phase 4 where it belongs conceptually — it was a real
         gap, caught only when phase 9 needed it to actually construct a
         `ReportingQueue`, and back-filled then. Noted honestly in the
         phase 9 entry rather than pretending it was planned.
      4. **The WS classifier registration** — phase 1's own analysis
         explicitly flagged `frigate/comms/ws.py`'s fail-closed classifier
         as a sharp edge new topics must be registered in, and proposed
         the exact fix (camera-prefixed zone topic to dodge it). Despite
         calling this out in the plan, phase 9 built `AlarmMqttBridge` and
         never actually touched `ws.py` — the three global/payload topics
         would have been silently dropped for every WebSocket client (MQTT
         delivery was unaffected, which is why none of phase 9's own tests
         caught it — none of them exercise `ws.py`). Found and fixed
         during this final review, before writing it up as done. This is
         the clearest example in the whole project of why phase 11 (full
         suite) and phase 12 (review against the original plan) are
         separate, real steps and not just a formality: isolated
         per-module tests all passed while a real integration gap sat
         unnoticed for three phases.
      5. **Process model** (thread vs. `mp.Process` for the alarm engine)
         — built exactly as flagged for confirmation in phase 1
         (`AlarmDetectionThread` as a `threading.Thread`, not a process)
         and signed off on at the time; no drift.
      6. **Zone MQTT topic naming** (`<camera>/alarm_zone/<zone>/state`
         instead of the spec's literal `alarm/zone/<zone>/state`) — also
         flagged and signed off in phase 1, implemented as planned in
         phase 9; no drift.
    - **What was never touched, and should be before this is real**:
      camera/comms supervision -> automatic `FAULT` entry (spec 5.8) was
      never wired up — `AlarmStateMachine.enter_fault()` exists and is
      tested, but nothing calls it automatically on camera offline /
      detection subsystem down / reporting-connection-down conditions.
      `ReportingQueue.on_health_change` exists specifically so this could
      be wired (unhealthy reporting -> fault) but that wiring itself
      was never done. This is a real functional gap, not just an
      unverified-in-this-sandbox one.
    - See the git log on this branch (18 commits, phase 1 through this
      one) for the full history; this file is the durable summary if that
      conversation is gone.

**Live verification (post-review, in the user's real devcontainer, not this
sandbox)**: after writing up phase 12 as done, the user's own devcontainer
(`frigate-devcontainer`, docker) turned out to be running with nginx (port
5000) getting 502s because the actual `python3 -m frigate` process had never
been started in that session — the s6-supervised "frigate" service in dev
images is a placeholder sleep loop by design (`docker/main/fake_frigate_run`),
the real process is meant to be started manually (`.vscode/launch.json`'s
"Python: Launch Frigate", or `python3 -m frigate` in a terminal). Started it
directly (`docker start` + `docker exec`, real `cv2`/`fastapi`/`zmq`/`peewee`
all present) and ran real end-to-end checks that this sandbox could never do:

- Confirmed all 5 alarm routes are live in the real `/openapi.json`.
- Confirmed `allow_any_authenticated()` actually rejects unauthenticated
  requests (403) and `require_role(["admin"])` gates POST correctly.
- Confirmed the "alarm disabled" 400 response shape matches
  `_not_enabled_response()` exactly, against a real default config.
- Set `alarm: {enabled: true, exit_delay_seconds: 5}` in the real
  `/config/config.yaml`, restarted, and drove a full `POST /alarm/arm` ->
  `GET /alarm/status` (`exit_delay`) -> ... cycle over real HTTP.
- **This caught a real bug the entire unit-test suite missed**: after the
  configured exit delay, the state never advanced past `exit_delay`.
  `AlarmStateMachine` deliberately doesn't time its own delay states (by
  design, for testability — callers own the timer), but no caller was ever
  actually built to own it; `AlarmDetectionThread` only handles detection
  events, not delay completion. Every unit test that touched exit/entry
  delay called `complete_exit_delay()`/`complete_entry_delay()` manually,
  so this was invisible to 100% of the test suite. Fixed in the commit
  right after this one (`AlarmSystem` now owns a `threading.Timer` per
  delay; see that commit message for the full explanation) and
  **re-verified live after the fix**: arm -> exit_delay -> (5 real seconds
  later, automatically, no manual intervention) -> armed_away -> disarm ->
  disarmed, confirmed by polling `GET /alarm/status` over real HTTP.
- Confirmed `disarm()`/`clear()`/other existing endpoints (`/config`,
  `/version`) still work, and confirmed through the actual nginx proxy on
  port 5000 too (the same path the user's 502s came from) — 200s across
  the board once the process was running.
- **Not yet observed live**: MQTT topic publishing (no broker configured in
  this test), a real camera/detection triggering the alarm end-to-end
  (`cameras: {}` in this test), the frontend in a browser (Vite wasn't
  started — intentionally not started by the agent, per the "never start
  the dev server unless asked" instruction).
- The test config used (`alarm: {enabled: true, exit_delay_seconds: 5}`,
  no cameras) is still in `/config/config.yaml` in that devcontainer, with
  the original backed up alongside it as `config.yaml.bak` — the user may
  want to restore or keep it depending on whether they want to keep poking
  at the feature.

This is the strongest evidence in the whole project that the phase 11/12
process (full suite + review) is not just a formality: it directly led to
finding this bug, and the fix would not exist without actually running the
software, which no amount of `ruff`/`mypy`/unit testing in this sandbox
could have caught, precisely because the unit tests all called the
timer-completion methods manually instead of waiting for a real timer.

**Proposed architecture (pending sign-off, see phase 1 analysis in conversation)**:
- New package `frigate/alarm/` — protocol-agnostic engine (state machine, zone
  verification, alarm memory), zero MQTT/ZMQ imports inside the state machine
  itself. Runs as a thread started from `FrigateApp` (pattern: `EventProcessor`
  in `frigate/events/maintainer.py`), consuming `EventUpdateSubscriber` /
  `DetectionSubscriber` (`frigate/comms/events_updater.py`,
  `frigate/comms/detections_updater.py`) — the same MQTT-independent internal
  ZMQ bus every other subsystem (review, timeline, events) already uses.
- New `frigate/alarm/protocols/sia.py` and `frigate/alarm/protocols/contact_id.py`
  — isolated encoding/transport, consuming only the canonical `AlarmEvent`.
- Reporting queue: in-process `queue.Queue` + background thread, modeled on
  `WebPushClient._process_notifications` (`frigate/comms/webpush.py`) — no new
  dependency needed.
- Config: `frigate/config/alarm.py` (`AlarmConfig`, global) + per-camera
  `alarm` field on `CameraConfig`, following the `NotificationConfig` /
  `FaceRecognitionConfig` dual-level `enabled` pattern
  (`frigate/config/camera/notification.py`, `frigate/config/classification.py`).
  Cross-field validation added as `verify_alarm_*` functions called from
  `FrigateConfig.post_validation` (`frigate/config/config.py:629`), mirroring
  `verify_required_zones_exist` / `verify_lpr_and_face`.
- API: new `frigate/api/alarm.py` router, registered in
  `frigate/api/fastapi_app.py` and in `generate_api_auth_spec.py`'s router list.
- MQTT/WS: alarm state published via the existing `Dispatcher.publish()`
  (`frigate/comms/dispatcher.py:396`) so MQTT + WebSocket get it in one call.
  New global topics (`alarm/state`, `alarm/fault`) need explicit registration
  in `frigate/comms/ws.py`'s `_WS_GLOBAL_OUTBOUND_TOPICS` (fail-closed
  classifier — unregistered topics are silently dropped). Per-zone topic
  should be `<camera>/alarm_zone/<zone>/state` (not `alarm/zone/<zone>/state`)
  to piggyback on the existing camera-prefix auto-scoping in `ws.py`, avoiding
  bespoke zone-fanout classifier code.
- Frontend: custom view (not the generic schema-driven config form) under
  `web/src/views/settings/AlarmSettingsView.tsx`, modeled on
  `MotionTunerView.tsx` / `TriggerView.tsx`; live status via the existing
  `useWs` pub/sub layer (`web/src/api/ws.ts`), SWR snapshot + WS override
  pattern from `useAutoFrigateStats` (`web/src/hooks/use-stats.ts`).

Full phase-1 analysis with file:line citations lives in the conversation that
produced this file; re-derive from the codebase if that conversation is gone
and this summary is insufficient.
