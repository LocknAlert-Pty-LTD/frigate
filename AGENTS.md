# Agent Instructions for Frigate NVR

> **Fork-specific features** (alarm engine, ParkPow LPR integration, TensorRT
> execution provider): see **[`rebuild.md`](rebuild.md)** for the structural map —
> what exists, where it lives, how it wires together, and how to rebuild it on a
> clean upstream checkout. This file remains the authority on *why* each decision
> was made and what is still unverified; `rebuild.md` is the condensed index into
> the sections below.

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
      # âŒ Don't process data inside try block
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

  # âœ… Process data outside try block
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

- **Linting**: ESLint (see `web/eslint.config.js`)
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
# endpoint or its auth dependency â€” outputs docs/static/frigate-api.yaml,
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

# Regenerate config translations from Pydantic models â€” outputs to
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

### âŒ Avoid These

```python
# Blocking operations in async functions
data = requests.get(url)  # âŒ Use async HTTP client
time.sleep(5)  # âŒ Use asyncio.sleep()

# Hardcoded strings in React components
<div>Camera not found</div>  # âŒ Use t("camera_not_found")

# Missing error handling
data = await api.get_data()  # âŒ No exception handling

# Bare exceptions in regular code
try:
    value = await sensor.read()
except Exception:  # âŒ Too broad
    logger.error("Failed")

# Returning exceptions in JSON responses
except ValueError as e:
    return JSONResponse(
        content={"success": False, "message": str(e)},
    )
```

### âœ… Use These Instead

```python
# Async operations
import aiohttp
async with aiohttp.ClientSession() as session:
    async with session.get(url) as response:
        data = await response.json()

await asyncio.sleep(5)  # âœ… Non-blocking

# Translatable strings in React
const { t } = useTranslation();
<div>{t("camera_not_found")}</div>  # âœ… Translatable

# Proper error handling
try:
    data = await api.get_data()
except ApiException as err:
    logger.error("API error: %s", err)
    raise

# Specific exceptions
try:
    value = await sensor.read()
except SensorException as err:  # âœ… Specific
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

**Goal**: extend Frigate into an AI-based alarm system â€” camera/zone-driven alarm
zones, arm/disarm (away/stay), entry/exit delay, alarm memory, fault/supervision,
persistence-based AI verification, SIA DC-09 and Contact ID reporting over IP.
Alarm engine core has zero MQTT dependency; MQTT is one optional output path.

**Phase tracker** (12 phases, commit + update this file after each):
1. Architectural analysis â€” **DONE, signed off by user**
2. Core alarm domain / state machine + unit tests â€” **DONE**. See
   `frigate/alarm/state.py` (`AlarmState`, `ArmedMode`, `ALLOWED_TRANSITIONS`
   table, `InvalidAlarmTransition`) and `frigate/alarm/engine.py`
   (`AlarmStateMachine`). 20 tests in `frigate/test/test_alarm_state_machine.py`,
   all passing; ruff/format/mypy clean. Key design choices: (a) entry/exit
   delay countdowns are NOT timed inside the state machine â€” callers own the
   timer and call `complete_exit_delay()`/`complete_entry_delay()` when it
   elapses, or `disarm()` to cancel; keeps the FSM pure and trivially unit
   testable. (b) `disarm()` during an active ALARM moves to ALARM_MEMORY, not
   DISARMED â€” `clear()` is the separate call that actually clears memory,
   matching the spec's distinct `alarm/disarm` vs `alarm/clear` API. (c) FAULT
   is enterable from any state and always restores whichever state was active
   before the fault, rather than having fixed predecessors/successors in the
   transition table â€” while faulted, no other transition is permitted (must
   `clear_fault()` first). This module has zero external dependencies
   (stdlib only), so it's a safe reuse target for the Phase 3 adapter and
   Phase 8 API layer.
3. Detection â†’ canonical event adapter + tests â€” **DONE**. See
   `frigate/alarm/event.py` (`AlarmEventType`, `AlarmEvent` â€” the canonical,
   protocol-agnostic event), `frigate/alarm/rules.py` (`ZoneAlarmRule`, a
   plain dataclass, NOT the Pydantic config), and `frigate/alarm/adapter.py`
   (`DetectionAlarmAdapter.evaluate()`). 18 tests in
   `frigate/test/test_alarm_adapter.py`, all passing; ruff/format/mypy clean.
   Design choices: (a) the adapter takes `armed_mode: ArmedMode | None` as an
   explicit parameter rather than holding a reference to `AlarmStateMachine`
   â€” one-way dependency (detections -> adapter -> engine), the adapter never
   imports `engine.py`, and it's unit-testable without constructing an engine.
   (b) "alarm enabled" (global) is NOT checked inside the adapter â€” the
   caller simply doesn't construct/use one when alarm is disabled; adding an
   internal flag would be redundant state. (c) persistence/verification is
   one numeric knob, `verification_seconds` (0 = instant-trigger, >0 = must
   dwell that long), tracked per (camera, zone, object_id) in
   `adapter._pending`; `clear_object()` lets the caller drop tracking when an
   object leaves a zone or its tracked-object lifecycle ends (future wiring
   phase must call this or trackers leak for objects that never
   re-qualify). (d) entry/exit delay is NOT applied by the adapter â€” it
   returns whether a detection qualifies; the caller reads
   `rule.entry_delay_seconds` via `adapter.get_rule(camera, zone)` and passes
   it to `engine.trigger()`. (e) a real bug was caught by the tests during
   this phase and fixed before commit: the object-whitelist check used
   `if rule.objects and label not in rule.objects`, which skipped the check
   entirely (allowing everything through) when the whitelist was empty,
   contradicting the "empty = nothing qualifies" design; fixed to
   `if label not in rule.objects`.
4. Config schema, validation, backwards-compat tests â€” **DONE, but NOT
   runtime-verified in this sandbox â€” see caveat below, run the tests in a
   full dev/CI env before trusting this phase.**
   - `frigate/config/alarm.py`: `AlarmConfig` (global) â€” `enabled`,
     `exit_delay_seconds`, `enabled_in_config` (snapshotted in
     `FrigateConfig.post_validation`, mirroring the existing
     `self.notifications.enabled_in_config = self.notifications.enabled`
     line right next to it).
   - `frigate/config/camera/alarm.py`: `AlarmZoneConfig` (per Frigate zone â€”
     `enabled`, `objects`, `event`, `object_event_overrides`,
     `min_confidence`, `verification_seconds`, `delay` [entry delay],
     `arm_modes`) and `CameraAlarmConfig` (`enabled`, `zones: dict[str,
     AlarmZoneConfig]`). `AlarmZoneConfig.to_rule(camera, zone)` builds a
     `frigate.alarm.rules.ZoneAlarmRule` directly (resolving the phase-3
     "decide how a rule gets built from config" question as a method on the
     config model itself, not a separate bridging module â€” one conversion
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
     section â€” `default_factory=AlarmConfig`/`default_factory=
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
     `frigate.config.*` â€” old or new â€” could be runtime-imported here, let
     alone executed. Verification for this phase was: `python3 -m py_compile`
     (syntax), `ruff check`/`ruff format --check` (clean), and manual
     line-by-line comparison against the exact precedent being mirrored
     (`verify_required_zones_exist`, `verify_lpr_and_face`,
     `NotificationConfig`). mypy was skipped deliberately, not just
     unavailable: `frigate/mypy.ini` has `[mypy-frigate.config.*]
     ignore_errors = true` project-wide, so it wouldn't have checked these
     files anyway. **Before relying on this phase, run
     `python3 -u -m unittest frigate.test.test_alarm_config` in a real
     dev/CI environment with full deps installed** â€” this has not been
     confirmed to actually pass, only to be free of syntax/lint errors and
     to structurally match working precedent.
5. SIA DC-09 adapter + tests â€” **DONE, but explicitly UNVERIFIED â€” do not
   treat as spec-compliant.** No ANSI/SIA DC-09 spec text was ever provided
   (only the Ademco Contact ID PDF, used in phase 6). I stopped and asked;
   given three options (provide the spec / skip to Contact ID first / stub
   it flagged-unverified), the user chose **stub it, flagged unverified**,
   overriding the project's default "don't implement without the spec"
   instruction â€” that's a deliberate, explicit choice on record, not a
   lapse.
   - `frigate/alarm/protocols/sia.py`: `encode_sia_message`/
     `parse_sia_message` (envelope: `LF CRC LENGTH "SIA-DCS" SEQ R L
     #ACCOUNT [DATA] _TIMESTAMP CR`), `SiaClient` (bare TCP
     connect/send/close, no retry â€” retry is phase 7's job), `is_ack`
     (substring check).
   - What's confidently correct: general envelope shape, framing bytes,
     that it's length + CRC prefixed. What's explicitly NOT verified and
     likely wrong against a real receiver: the CRC variant (used CRC-16/ARC,
     poly 0xA001 â€” other SIA implementations may use a different one), the
     inner data-block subfield grammar (real DC-09 has structured
     event-qualifier tokens; this emits a simplified
     `[#account|code+zone]`), and ACK/NAK/DUH framing (real DC-09 responses
     are structured; this just substring-matches "ACK").
   - `SIA_EVENT_CODES` in that file only maps event types with reasonably
     common public citations (burglary->BA, panic->PA, tamper->TA, arm->CL,
     disarm->OP, test->RP). fault/restore/camera_failure/
     communication_failure/supervision are deliberately left unmapped â€”
     encoding one raises `UnmappedAlarmEventType` rather than emitting a
     fabricated code. Do not add codes for these without the real spec.
   - Encryption is NOT implemented. DC-09 has an AES-based encrypted
     variant; `encrypted=True` raises `NotImplementedError` rather than
     guessing at IV/padding for something security-relevant â€” that's a
     harder line than the rest of the stub, worth keeping even if the
     envelope guesses above ever get "good enough" treatment.
   - Tests: `frigate/test/test_alarm_sia.py`, 11 tests, all passing,
     ruff/format/mypy clean â€” but these only prove internal
     self-consistency (our encoder round-trips through our own parser,
     CRC/length invariants hold, a loopback-socket transport test) and
     prove NOTHING about interoperability with a real monitoring receiver.
     No cv2/pydantic-config dependency here (unlike phase 4), so this phase
     actually ran in this sandbox, not just syntax-checked.
   - **Before this touches a real receiver**: get the actual ANSI/SIA
     DC-09 spec and re-verify every point above, especially the CRC
     algorithm and the subfield grammar.
6. Contact ID adapter + tests â€” **DONE, and materially more trustworthy
   than phase 5** since the event code table came from an actual attached
   reference, not memory.
   - `frigate/alarm/protocols/contact_id.py`: `CID_EVENT_DESCRIPTIONS` is
     the full CID#->description table transcribed directly from the
     attached Ademco Contact ID Report Codes PDF (the plain 3-digit CID#
     column â€” the wire format code â€” not the hex "Programming Value"
     column, which is for Ademco keypad panel programming, a different
     thing). `CONTACT_ID_EVENT_CODES` maps canonical `AlarmEventType` to a
     code from that table; a test (`TestEventCodesAreFromReference`)
     asserts every mapped code is a real key in the reference table, so
     "don't invent codes" is enforced, not just claimed.
   - Mapping: burglary->130, panic->120, tamper->137, fault->300,
     communication_failure->354, supervision->380 (a judgment call among
     several plausible codes, not a guess at an undocumented one),
     test->602, arm/disarm->401 (both share "Open/Close by user"; which one
     you get is the qualifier digit, not the code â€” Contact ID's Q digit
     means Open/Close for code 401 specifically, New/Restore for
     alarm-type codes elsewhere, same 1/3 values, context-dependent
     meaning, handled via `ContactIDQualifier`).
   - Deliberately unmapped, same "raise rather than fabricate" posture as
     phase 5: `camera_failure` (no video-specific code in this
     burglar-panel reference) and `restore` (Contact ID expresses restore
     as a qualifier on the *original* event's code, not as its own code â€”
     callers should re-encode the original event_type with
     `qualifier=new_restore`, not use `AlarmEventType.restore` here).
   - The 15-digit message layout (ACCT+type+qualifier+code+group+zone) is
     the standard public Contact ID wire format â€” high confidence, unlike
     phase 5's envelope. What's still a real caveat: no checksum digit
     (DTMF-only concept, assumed unnecessary over TCP â€” verify against
     your receiver), and "Contact ID over IP" transport itself isn't
     standardized the way DC-09 is (Contact ID is natively DTMF-over-POTS),
     so `ContactIDClient` is a reasonable-but-generic TCP transport, not a
     verified wire protocol.
   - Tests: `frigate/test/test_alarm_contact_id.py`, 18 tests, all passing,
     ruff/format/mypy clean, no cv2/config dependency so it actually ran
     here.
7. Reporting queue (send/ACK/retry/failure) + tests â€” **DONE**.
   `frigate/alarm/queue.py`: `ReportingQueue`, modeled directly on
   `WebPushClient._process_notifications`
   (`frigate/comms/webpush.py`) â€” a `queue.Queue[AlarmEvent]` plus one
   background thread, no new dependency. Protocol-agnostic: constructed
   with a plain `send: Callable[[AlarmEvent], bool]`, so it never imports
   `sia.py`/`contact_id.py` â€” the wiring layer (phase 9) passes in
   something like `lambda event: sia_client.send(encode_sia_message(event,
   ...))`.
   - Events are delivered one at a time, in order, retries included (not
     fanned across worker threads) â€” deliberate: for a home alarm, ordering
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
     1 error â€” the pre-existing/expected `test_alarm_config` cv2-import
     gap from phase 4, nothing new broken.
8. API endpoints + auth + tests â€” **DONE, but like phase 4, NOT
   runtime-verified in this sandbox (no fastapi installed) â€” see caveat
   below.**
   - `frigate/alarm/system.py`: new `AlarmSystem` orchestrator, deliberately
     kept separate from `AlarmStateMachine`. Bundles `state_machine`,
     `adapter` (`DetectionAlarmAdapter`, built from the same `rules` dict
     phase 4's `CameraAlarmConfig.build_rules()` produces), a bounded
     `deque` event history, and an optional `ReportingQueue`. `arm()`/
     `disarm()`/`clear()` delegate straight to the state machine;
     `record_event()` only does history + reporting-queue bookkeeping â€” it
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
   - Wiring: `frigate/api/fastapi_app.py` â€” `alarm_system: AlarmSystem |
     None = None` added as a new trailing optional parameter to
     `create_fastapi_app()` (additive, matches the existing `dispatcher`/
     `profile_manager`/`config_holder` optional-trailing-param pattern, so
     no existing caller breaks), `app.include_router(alarm.router)`,
     `app.alarm_system = alarm_system`. Actually constructing and starting
     an `AlarmSystem` from real config in `frigate/app.py` is phase 9's
     job, not this one â€” phase 8 only builds the API surface and the class
     it talks to.
   - `generate_api_auth_spec.py` also updated (import + its own
     independent `routers` list in `build_app()`) â€” CLAUDE.md is explicit
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
     (required by this repo's own CLAUDE.md after any endpoint change â€”
     could not be run here for the same missing-fastapi reason) to
     regenerate `docs/static/frigate-api.yaml` before this could pass CI's
     `--check` gate.
9. MQTT integration (optional path) + test engine runs with MQTT off â€”
   **DONE**, including real `frigate/app.py` wiring (the highest-risk phase
   so far â€” touches the actual process startup sequence, not just new
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
     attempt) from `AlarmReportingConfig`. This is glue, not core â€” it's
     the one alarm module allowed to import `frigate.config` â€” so like
     phase 4/8 it could only be verified via `py_compile`/`ruff`/`mypy`
     here (mypy *did* run cleanly on it â€” it statically resolves
     `frigate.config` fine without cv2 actually being installed, since
     mypy doesn't execute code â€” a useful distinction from runtime tests
     discovered this phase).
   - `frigate/alarm/mqtt_bridge.py`: `AlarmMqttBridge`, publishes
     `alarm/state`/`alarm/fault` (retained) and `alarm/event` (not
     retained) plus, critically, `<camera>/alarm_zone/<zone>/state` per
     zone â€” NOT the spec's literal `alarm/zone/<zone>/state`, because that
     doesn't start with a camera name and would be silently dropped by
     `frigate/comms/ws.py`'s fail-closed classifier (see phase 1 analysis).
     Takes a plain `Callable[[str, str, bool], None]` for publish, not a
     `Dispatcher` import, so it stays testable without the comms stack â€”
     confirmed by 6 tests in `test_alarm_mqtt_bridge.py` that all actually
     run here, including a regression guard specifically asserting the
     zone topic is camera-prefixed.
   - `frigate/alarm/detection_thread.py`: `AlarmDetectionThread`, a
     `threading.Thread` (modeled on `EventProcessor`) that subscribes to
     `EventUpdateSubscriber` â€” the internal MQTT-independent ZMQ event bus,
     not MQTT â€” and drives `adapter.evaluate()` ->
     `state_machine.trigger()` -> `alarm_system.record_event()` ->
     `mqtt_bridge.publish_*()`. The exact dict field names read off each
     tracked-object update (`current_zones`, `entered_zones`, `id`,
     `label`, `top_score`/`score`, `false_positive`, `frame_time`) were
     read directly from `TrackedObject.to_dict()`
     (`frigate/track/tracked_object.py:387-430`) and
     `EventUpdateSubscriber`/`Subscriber.check_for_update()`
     (`frigate/comms/events_updater.py`, `frigate/comms/zmq_proxy.py`) â€”
     not guessed, unlike the SIA/Contact ID situation. `InvalidAlarmTransition`
     from `trigger()` (e.g. a second qualifying detection while already in
     ALARM) is caught and logged at debug, not treated as an error â€” the
     event still gets recorded/reported.
   - **A real design bug was caught while writing this phase's tests, not
     before**: `AlarmSystem.armed_mode_for_evaluation` (added this phase)
     originally excluded `AlarmState.alarm` from the states that permit
     evaluation, meaning a second zone triggering while an alarm was
     already sounding would silently never get recorded or reported. Fixed
     by including `alarm` in that set â€” a genuinely different question
     from "should this trigger a *new* alarm" (no, `state_machine.trigger()`
     correctly rejects that) vs. "should this qualifying detection still be
     logged and reported" (yes). `EXIT_DELAY` deliberately still excluded
     (motion while walking out during exit delay shouldn't trigger).
   - **Test: "engine runs correctly with MQTT off"** (explicitly required
     by the original spec) â€” `frigate/test/test_alarm_no_mqtt_dependency.py`,
     3 tests, all passing. Rather than spinning up a real FrigateApp with
     MQTT disabled (impossible here, needs the full dependency set), this
     statically parses every core module's imports via `ast` and asserts
     none reference `mqtt` or `dispatcher`, PLUS actually imports the 9
     core modules and confirms `frigate.comms` never lands in
     `sys.modules` as a side effect. `factory.py` and
     `detection_thread.py` are explicitly exempted (documented in the file)
     as the wiring/glue layer that's expected to depend on
     `frigate.config`/the internal ZMQ bus â€” everything else (`state.py`,
     `engine.py`, `event.py`, `rules.py`, `adapter.py`, `queue.py`,
     `system.py`, `protocols/*`) is asserted clean.
   - **`frigate/test/test_alarm_detection_thread.py` â€” 9 tests, and they
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
     (clean), and `mypy` (clean â€” zero errors in `frigate/app.py` or any
     file this project touched; the 105 errors mypy reported while
     following imports are 100% pre-existing, in numpy/opencv-heavy files
     never touched this session like `norfair_tracker.py` and
     `license_plate/mixin.py`, almost certainly a numpy/stub version
     mismatch between this sandbox and the real dev container â€” verified
     by grepping mypy's output for any file this session created/edited
     and finding none).
     - **UPDATE (see "Live verification" below, post phase-12 review):**
       the "boot a real instance" step this caveat called for has now
       actually been done, in the user's real devcontainer, not this
       sandbox. It found and this branch now fixes a real bug (exit/entry
       delay never completing â€” see that section). MQTT topic publishing
       itself still hasn't been observed (no MQTT broker was configured in
       that test), so that specific piece is still open.
10. Frontend components â€” **DONE, and this is the first phase with real
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
      `createSectionPage("lpr", "camera")` etc. â€” no new form code.
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
      `frigate/api/defs/response/alarm_response.py` by hand â€” there's no
      shared codegen between the two), `web/public/locales/en/views/
      alarm.json` (new i18n namespace, registered in `web/src/utils/
      i18n.ts`), `menu.alarm`/`menu.alarmStatus`/`menu.globalAlarm`/
      `menu.cameraAlarm` keys added to `web/public/locales/en/views/
      settings.json`.
    - Actually verified in this sandbox (all passed, not just
      syntax-checked): `npx tsc --noEmit` (caught and fixed a real bug â€”
      `Heading` only supports `h1`-`h4`, I'd used `h5`), `npx eslint`
      (clean after one auto-fix), `npx vite build --base=/BASE_PATH/`
      (production build succeeds, only pre-existing unrelated chunk-size
      warnings), `npx i18next-cli extract --ci` (exit 0 â€” every `t()` call
      in the new code has a real matching key, nothing missing or unused).
    - **Not verified, explicitly**: visual appearance and live
      interaction. No browser was opened, `npm run dev` was not started
      (CLAUDE.md: agents should never start the dev server unless asked),
      no screenshot taken, no e2e/Playwright spec added. This codebase has
      no component-level unit tests to mirror (`web/src/**/*.test.tsx`
      doesn't exist anywhere â€” e2e/Playwright is the only test layer), so
      "add a test" for this phase means an e2e spec, which needs a live
      built app + backend (mock data doesn't cover alarm endpoints yet)
      and was out of scope here. **Before trusting this phase**: run
      `npm run dev`, open Settings â†’ Alarm, and confirm arm/disarm/clear
      actually work end-to-end against a real backend with
      `alarm.enabled: true`.
11. Full test suite run, fix regressions â€” **DONE**.
    - `python3 -u -m unittest discover -s frigate/test`: 217 tests
      collected, 75 errors â€” confirmed by name that exactly 2 are
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
      aren't sufficient â€” this phase existed for exactly this reason.
    - `ruff check frigate/` and `ruff format --check frigate/`: clean
      across the whole backend (356 files), not just alarm files.
    - `python3 -u -m mypy --config-file frigate/mypy.ini frigate/`: 111
      errors in 28 files, all outside anything created/modified this
      project (confirmed by grepping the output for
      `frigate/alarm|frigate/api/alarm|frigate/app.py|frigate/config/alarm`
      â€” zero matches). Same pre-existing numpy/stub-version gap noted in
      phase 9, now confirmed against the *entire* codebase, not just the
      files this branch touches.
    - Frontend: `npx eslint --ext .jsx,.js,.tsx,.ts --ignore-path
      .gitignore .` across the whole `web/` tree â€” clean, no output.
    - **Still not done, carried forward as the real "phase 11" for
      whoever picks this up next**: none of the backend caveats from
      phases 4/8/9 (run the config/API/http_alarm tests, boot a real
      FrigateApp instance) have been resolved â€” this phase only confirms
      *this sandbox's* tests are internally consistent and regression-free,
      not that the untested-here code actually works. That full
      dev/CI-environment verification pass is still outstanding.
12. Final architecture review against phase 1 â€” **DONE**. All 12 phases
    complete; branch `feature/alarm-engine` has 17 commits from phase 1
    through this one.
    - **Drift from the phase 1 plan, and why**:
      1. **SIA DC-09 (phase 5)** â€” the single biggest deviation. The
         original instructions (both the project bootstrap and section
         5.5) say to stop rather than implement a protocol from memory.
         No spec was ever provided; the user was given three explicit
         options (provide the spec / do Contact ID first / stub it
         flagged-unverified) and chose the third, overriding the default
         rule on record. `frigate/alarm/protocols/sia.py` is real,
         tested code, but "tested" only means internally self-consistent
         â€” it has never been checked against the actual ANSI/SIA DC-09
         spec text and should not be trusted against a real receiver
         without that check.
      2. **Frontend config UI** â€” phase 1 proposed a fully custom view;
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
         built in phase 4 where it belongs conceptually â€” it was a real
         gap, caught only when phase 9 needed it to actually construct a
         `ReportingQueue`, and back-filled then. Noted honestly in the
         phase 9 entry rather than pretending it was planned.
      4. **The WS classifier registration** â€” phase 1's own analysis
         explicitly flagged `frigate/comms/ws.py`'s fail-closed classifier
         as a sharp edge new topics must be registered in, and proposed
         the exact fix (camera-prefixed zone topic to dodge it). Despite
         calling this out in the plan, phase 9 built `AlarmMqttBridge` and
         never actually touched `ws.py` â€” the three global/payload topics
         would have been silently dropped for every WebSocket client (MQTT
         delivery was unaffected, which is why none of phase 9's own tests
         caught it â€” none of them exercise `ws.py`). Found and fixed
         during this final review, before writing it up as done. This is
         the clearest example in the whole project of why phase 11 (full
         suite) and phase 12 (review against the original plan) are
         separate, real steps and not just a formality: isolated
         per-module tests all passed while a real integration gap sat
         unnoticed for three phases.
      5. **Process model** (thread vs. `mp.Process` for the alarm engine)
         â€” built exactly as flagged for confirmation in phase 1
         (`AlarmDetectionThread` as a `threading.Thread`, not a process)
         and signed off on at the time; no drift.
      6. **Zone MQTT topic naming** (`<camera>/alarm_zone/<zone>/state`
         instead of the spec's literal `alarm/zone/<zone>/state`) â€” also
         flagged and signed off in phase 1, implemented as planned in
         phase 9; no drift.
    - **What was never touched, and should be before this is real**:
      camera/comms supervision -> automatic `FAULT` entry (spec 5.8) was
      never wired up â€” `AlarmStateMachine.enter_fault()` exists and is
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
been started in that session â€” the s6-supervised "frigate" service in dev
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
  design, for testability â€” callers own the timer), but no caller was ever
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
  port 5000 too (the same path the user's 502s came from) â€” 200s across
  the board once the process was running.
- **Not yet observed live**: MQTT topic publishing (no broker configured in
  this test), a real camera/detection triggering the alarm end-to-end
  (`cameras: {}` in this test), the frontend in a browser (Vite wasn't
  started â€” intentionally not started by the agent, per the "never start
  the dev server unless asked" instruction).
- The test config used (`alarm: {enabled: true, exit_delay_seconds: 5}`,
  no cameras) is still in `/config/config.yaml` in that devcontainer, with
  the original backed up alongside it as `config.yaml.bak` â€” the user may
  want to restore or keep it depending on whether they want to keep poking
  at the feature.

This is the strongest evidence in the whole project that the phase 11/12
process (full suite + review) is not just a formality: it directly led to
finding this bug, and the fix would not exist without actually running the
software, which no amount of `ruff`/`mypy`/unit testing in this sandbox
could have caught, precisely because the unit tests all called the
timer-completion methods manually instead of waiting for a real timer.

## Post-phase-12 addition: Home Assistant integration

Requested after the original 12-phase plan was already complete: three-way
arm modes matching Home Assistant's own vocabulary, full MQTT auto-discovery
so the alarm panel and its zones appear in HA without any manual YAML, and a
friendlier zone setup UI (the generic schema-driven config form was
functional but not "simple," per the request). Not part of the original
spec's phase numbering, so tracked here as its own section rather than
shoehorned into phase 10/12.

**Three-way arm modes (away/home/night)**: `ArmedMode`/`AlarmState` renamed
`stay`/`armed_stay` -> `home`/`armed_home`, plus a new `night`/`armed_night`.
"night" is what's shown to users as "Sleep" (the user's own wording) --
same concept, Home Assistant's literal state name for it, used internally so
the MQTT bridge needs no translation table for these three. Rippled through
every layer: `frigate/alarm/state.py` (enum + transition table),
`engine.py` (`_complete_arming`'s mode->state dict), `rules.py`/
`frigate/config/camera/alarm.py` (`arm_modes` default is now all three,
was away+stay), `frigate/api/defs/request/alarm_body.py` (`Literal["away",
"home", "night"]`), `frigate/api/alarm.py` (`ArmedMode(body.mode)`, simpler
than the old two-way ternary), and every test file that constructed an
`ArmedMode`/`AlarmState`. `armed_mode_for_evaluation`/`zone_status()` in
`system.py` already enumerated states explicitly rather than using a
catch-all, so both needed the third state added by hand -- a case where the
original design's explicitness (rather than e.g. `state.value.startswith
("armed_")`) made the rename mechanical and safe to verify by reading, not
a place a state could be silently missed.

**A real architecture improvement fell out of the MQTT work, not just the
MQTT work itself**: wiring inbound `alarm/set` MQTT commands (so a Home
Assistant alarm card can arm/disarm, not just Frigate's own UI) surfaced
that arm/disarm via the HTTP API never actually pushed updated state out
over MQTT/WS either -- `frigate/api/alarm.py`'s handlers only ever called
`alarm_system.arm()`/`.disarm()` and returned; nothing published until the
*next* real detection happened to run `AlarmDetectionThread`, which was the
only caller that remembered to publish. Fixed at the root instead of adding
a third remember-to-publish call site: `AlarmSystem` now owns `on_change`/
`on_event` callbacks (`system.py`) invoked automatically by `arm()`/
`disarm()`/`clear()`/`trigger()`/the delay-timer completions/
`record_event()`. The wiring layer (`frigate/app.py`'s `init_alarm_system`)
assigns these once to the MQTT bridge's `publish_status`/`publish_event`,
and every mutator -- HTTP API, an inbound MQTT command, or a real detection
-- now publishes the same way with no risk of a caller forgetting. Net
effect: `AlarmDetectionThread` got *simpler* (no longer holds an
`AlarmMqttBridge` reference at all) while covering strictly more cases than
before.

**Home Assistant MQTT discovery** (`frigate/alarm/ha_discovery.py`,
`frigate/alarm/mqtt_bridge.py`'s `HA_*` topics/`translate_state_for_ha`):
unlike SIA DC-09, this is a stable, well-documented public protocol
(home-assistant.io/integrations/mqtt/#mqtt-discovery), so there's no
"unverified stub" caveat on the protocol shape itself -- only on whether
it's actually been observed working against a real HA instance (see live
verification below, it hasn't).
- One HA `device` ("Frigate Alarm") groups: an `alarm_control_panel`
  (state topic `alarm/ha/state`, command topic `alarm/set`, payloads
  `ARM_AWAY`/`ARM_HOME`/`ARM_NIGHT`/`DISARM`, no code required since access
  control is Frigate's own auth), a `binary_sensor` per enabled alarm zone
  (device_class `safety`), a fault `binary_sensor` (device_class
  `problem`), and a reporting-health `binary_sensor` (device_class
  `connectivity`).
- Deliberately new dedicated bare-value topics (`alarm/ha/state`,
  `alarm/ha/fault`, `alarm/ha/reporting`, `alarm/ha/zone/<camera>_<zone>`)
  rather than reusing the existing rich-JSON `alarm/state` topic with a
  Jinja2 `value_template` translation. A Python mapping function
  (`translate_state_for_ha`) is unit-testable exactly; a Jinja2
  dict-literal-lookup expression embedded in a discovery JSON payload is
  not verifiable from here and is exactly the kind of "looks right, can't
  confirm the fine syntax" guess this project has avoided all session
  (see the SIA DC-09 posture). The existing JSON topics are untouched, so
  nothing already working (the frontend, the API) was put at risk.
- **A real, non-obvious technical constraint discovered while building
  this**: `MqttClient.publish()` (`frigate/comms/mqtt.py`) unconditionally
  prefixes every topic with `mqtt.topic_prefix` (default `frigate`) --
  fine for Frigate's own topics, but HA discovery configs *must* be under
  the literal `homeassistant/` tree regardless of Frigate's prefix, or HA
  never sees them. Fixed with a small additive `publish_absolute()` method
  on both `MqttClient` and `Dispatcher` (mirrors the existing
  `web_push_client`-lookup pattern in `Dispatcher.__init__` --
  `self.mqtt_client = next((c for c in communicators if isinstance(c,
  MqttClient)), None)`) that bypasses the prefix. This is genuinely new
  capability, not a workaround; the regular `publish()` path was
  structurally incapable of reaching an unprefixed topic at all.
- `Dispatcher` gained an `alarm_system: AlarmSystem | None` attribute (same
  post-construction-assignment pattern as the existing `profile_manager`)
  and a `"alarm"` entry in `_global_settings_handlers`, so an inbound
  `<prefix>/alarm/set` MQTT message routes to `_on_alarm_command` exactly
  the way `profile/set` routes to `_on_profile_command`. This is the one
  place `frigate/comms/dispatcher.py` now imports from `frigate.alarm.*`
  (`AlarmSystem`, `ArmedMode`, `InvalidAlarmTransition`) -- a one-way
  dependency (comms depends on alarm, not the reverse) that does not
  violate the alarm engine's "zero MQTT dependency" constraint, which is
  about the alarm core never needing MQTT to function, not about MQTT
  code being disallowed from knowing about the alarm domain. Confirmed by
  rerunning `test_alarm_no_mqtt_dependency.py`, which only scans
  `frigate/alarm/*` and is unaffected by what `frigate/comms/dispatcher.py`
  imports.
- `frigate/alarm/detection_thread.py` lost its `AlarmMqttBridge` reference
  as a side effect of the `on_change`/`on_event` refactor above, which
  means it no longer needs the "wiring/glue, exempt from the no-MQTT-import
  scan" carve-out it had in phase 9 -- it now passes
  `test_alarm_no_mqtt_dependency.py`'s static import check on its own
  merits. `factory.py` and the new `ha_discovery.py` (both need
  `frigate.config`) remain the only exemptions.

**Friendly zone setup UI** (`web/src/views/settings/AlarmZoneSetup.tsx`,
embedded in `AlarmView.tsx`): replaces reliance on the generic
schema-driven config form for the one thing it renders awkwardly -- a
dict of zones, each with object/arm-mode lists and numeric delays. Lists
every camera's existing Frigate zones (from `config.zones`, not a
separate alarm-specific zone list -- alarm zones are just Frigate zones
with alarm behavior turned on) as a card with a single "Protect this
zone" switch; enabling one reveals object-type and arm-mode pickers
(`ToggleGroup type="multiple"`) and two number inputs (entry delay,
verification seconds). Saves every pending change in one `PUT config/set`
call using its `config_data` body form (discovered via `TriggerView.tsx`'s
precedent -- much simpler than building dotted-query-string params for
list-valued fields, which is what `MotionTunerView.tsx`'s scalar-only
pattern would have required). Saving implicitly sets both the per-camera
and global `alarm.enabled: true`, so turning on one zone is enough to
activate the whole feature -- no separate "enable alarm" step to forget.
- **A real first-run UX bug was caught before it shipped, not after**:
  the live status/control section's original design returned early with
  just a "not enabled" message whenever `alarm.enabled` was false --
  which is *always* true for a brand new install, since alarm defaults
  off. That would have made the zone setup UI (the only thing that can
  turn it on) unreachable from the same page for a first-time user.
  Restructured so zone setup always renders; only the live status/arm
  buttons are conditional on `isEnabled`.
- `web/src/types/frigateConfig.ts` (the hand-maintained TS mirror of the
  Pydantic config, no shared codegen between them) gained `alarm` on both
  `FrigateConfig` and `CameraConfig` -- this had been missed in phase 10,
  caught only now because this component actually reads
  `camera.alarm.zones` and `tsc` failed until the type existed.

**Tests**: every renamed/added Python surface has matching test coverage,
following exactly the same "actually runs here" vs. "needs cv2/zmq, written
correctly but unverified in this sandbox" split as the rest of this project.
New test files: `test_alarm_dispatcher_command.py` (needs `frigate.config`
via `frigate.comms.dispatcher`, blocked by the same cv2 gap as
`test_dispatcher_runtime_state.py`, its precedent), `test_alarm_ha_discovery.py`
(needs `frigate.config` via `factory.build_alarm_rules`, same gap --
its mock had to give `camera.alarm.build_rules` a real return value rather
than mocking the whole Pydantic chain, since `build_alarm_rules()` calls
that method for real). `test_alarm_mqtt_bridge.py`,
`test_alarm_system.py`, `test_alarm_detection_thread.py`,
`test_alarm_adapter.py`, `test_alarm_state_machine.py` all gained new
cases and **do** run here (pure `frigate.alarm.*`, no config/comms
dependency) -- 245 tests collected total now, 168 actually run and pass,
the other 77 are exactly the pre-existing 73-error baseline plus these 4
new config/comms-dependent files, confirmed by name, zero unexplained
regressions.

**Live verification status, read before trusting this**: mid-way through
verifying this in the user's real devcontainer (the same one from the
phase-9/502-error session), the container started stopping and restarting
outside of anything this session did -- strong signal the user was
actively working in it themselves (opened it and found a real camera,
zone, and alarm-zone config already set up, with `arm_modes: [away]`,
which validates fine against the rename). Confirmed before that started:
Frigate boots cleanly with all of this session's changes against that real
config, no new errors (the only errors present -- an ONNX/OpenVINO
model-format mismatch on the detector, and the camera's RTSP stream being
unreachable from this sandbox -- are pre-existing and unrelated to any of
this). **Not confirmed live**: the arm/disarm HTTP roundtrip with the new
three modes (was confirmed for the old two-mode version in the phase-9
session; the rename itself is only verified by the 168 passing unit tests
plus this clean boot, not by a fresh live HTTP round-trip), and HA
discovery / inbound MQTT commands over a real broker -- MQTT is disabled
(`mqtt.enabled: false`) in the config that's actually in that devcontainer,
and standing up a broker on the same docker network was judged more
infrastructure than this warranted without being asked. **Before trusting
the Home Assistant integration specifically**: point Frigate at a real
MQTT broker with `mqtt.enabled: true`, connect a real Home Assistant
instance to the same broker, and confirm the alarm panel and zone sensors
actually appear and that arming from the HA card actually works --
none of that has been observed, only that the discovery payloads are
correctly shaped per unit tests and the publish-side wiring compiles,
lints, and type-checks clean.

**Proposed architecture (pending sign-off, see phase 1 analysis in conversation)**:
- New package `frigate/alarm/` â€” protocol-agnostic engine (state machine, zone
  verification, alarm memory), zero MQTT/ZMQ imports inside the state machine
  itself. Runs as a thread started from `FrigateApp` (pattern: `EventProcessor`
  in `frigate/events/maintainer.py`), consuming `EventUpdateSubscriber` /
  `DetectionSubscriber` (`frigate/comms/events_updater.py`,
  `frigate/comms/detections_updater.py`) â€” the same MQTT-independent internal
  ZMQ bus every other subsystem (review, timeline, events) already uses.
- New `frigate/alarm/protocols/sia.py` and `frigate/alarm/protocols/contact_id.py`
  â€” isolated encoding/transport, consuming only the canonical `AlarmEvent`.
- Reporting queue: in-process `queue.Queue` + background thread, modeled on
  `WebPushClient._process_notifications` (`frigate/comms/webpush.py`) â€” no new
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
  classifier â€” unregistered topics are silently dropped). Per-zone topic
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

## Post-HA-integration session: live verification, and two real inbound/discovery bugs found and fixed

Requested: resume the specific live-verification items the HA integration
section above left open (3-mode arm/disarm HTTP roundtrip, HA discovery
against a real broker, inbound `alarm/set` commands). Found real bugs in the
process, not just confirmed things worked.

**Environment note, read first if picking this up again**: the
`frigate-devcontainer` (VS Code dev container, `docker compose --profile`
target `devcontainer`, s6 placeholder "fake Frigate" service +
`python3 -m frigate` started by hand) turned out to be unusable for
extended live testing -- not because of anything alarm-related, but because
of a **pre-existing, unrelated bug**: `config/config.yaml`'s
`detectors.ov.type` was set to `onnx` while `model.path` pointed at an
OpenVINO IR file (`ssdlite_mobilenet_v2.xml`). ONNX Runtime can't parse an
OpenVINO IR XML as a `.onnx` protobuf (`InvalidProtobuf` on every load), so
the detector subprocess died immediately, every time, and Frigate's own
watchdog (`frigate/watchdog.py` -> `frigate/util/services.py:restart_frigate`)
correctly treats "detector process is dead" as fatal and calls
`psutil.Process(1).terminate()` -- a deliberate, by-design SIGTERM to the
container's own PID 1 (s6-svscan) to force a clean restart, documented
in the source as `# if this is running via s6, sigterm pid 1`. In the
devcontainer this has no `restart:` policy, so the whole container just
died and stayed dead every ~20-100s (the ONNX load + watchdog timeout
window) whenever the real Frigate process was started manually. This
produced about an hour of misleading symptoms this session (nginx cache
noise, apparent GET/POST state desync, "the container keeps dying for no
reason") before the actual cause was traced with a 1s-resolution process
trace showing the s6-supervised placeholder process disappearing in lockstep
with the container's death. **Fixed** by changing `detectors.ov.type` from
`onnx` to `openvino` in `config/config.yaml` (Frigate has a dedicated
`frigate/detectors/plugins/openvino.py` plugin for IR-format models) --
this is a local dev config fix, not a code change, and only applies to this
one devcontainer's `config/config.yaml`.
- Given that instability, live verification for this session was done
  against a **new, separate path**: `docker-compose.yml`'s `frigate` +
  `mqtt` services (production image, `target: frigate`, no source
  bind-mount, `restart: unless-stopped`, real `eclipse-mosquitto:2.0`
  broker) rather than the devcontainer. That compose file already had an
  uncommitted, half-finished edit (not from this session, found as-is,
  intent stated in its own comments) replacing the old `devcontainer`-only
  service with this production `frigate` + `mqtt` pair; it was completed
  by actually bringing it up (`docker compose up -d --build frigate mqtt`),
  not further redesigned. `config/config.yaml` was backed up
  (`config.yaml.pre-mqtt-verify.bak`) before flipping `mqtt.enabled: true`
  / `mqtt.host: mqtt` for this test. An unrelated crash-looping container,
  `locknalert-mqtt` (a different project's mosquitto, exit code 13,
  `restart: unless-stopped`), was found squatting near port 1883 on this
  same host; it never actually held the port stably so it didn't conflict,
  but worth knowing about if MQTT setup ever seems flaky on this machine
  again -- it's unrelated to Frigate.
- The apparent "GET /alarm/status doesn't reflect what POST /alarm/arm just
  did" behavior seen early in this session, before the detector fix, was
  **not a bug**: it was nginx's existing, intentional `/api/` location
  cache (`docker/main/rootfs/usr/local/nginx/conf/nginx.conf`:
  `proxy_cache_valid 200 5s` on all JSON GETs, bypassed only when a real
  `$cookie_session` is present). Un-authenticated curl testing (no session
  cookie) hits this cache like any other anonymous `/api/*` GET; a real
  logged-in browser session bypasses it. Confirmed by re-running the same
  test with `curl -H "X-Cache-Bypass: 1"` (the existing
  `proxy_cache_bypass $http_x_cache_bypass` escape hatch) -- all 3 arm
  modes (away/home/night) and disarm behaved correctly on every call. No
  code change needed here; noted only so a future session doesn't re-chase
  this as a phantom bug.
- Exit-delay auto-completion (the `threading.Timer`-based fix from the
  phase-9 live-verification note above) reconfirmed live: `POST
  alarm/arm {"exit_delay_seconds": 3}` -> automatically -> `armed_away`
  after 3 real seconds, no manual `complete_exit_delay()` call.

**Two real, previously-undiscovered bugs found and fixed in the HA/MQTT
wiring** (both silent -- no exceptions, no log errors, just nothing
happening -- which is exactly why unit tests never caught either one: the
unit tests call the relevant methods directly rather than going through a
real connected MQTT client):

1. **HA discovery configs were never actually reaching Home Assistant's
   `homeassistant/` tree.** `frigate/app.py`'s `init_alarm_system()` called
   `publish_ha_discovery(self.config, self.dispatcher.publish)` -- the
   regular, topic-prefixing `publish`, not `publish_absolute`, despite
   `publish_ha_discovery`'s own parameter being named `publish_absolute`
   and its docstring explicitly saying discovery topics must bypass the
   prefix. Confirmed live: subscribing to `homeassistant/#` on a real
   broker returned nothing at all (not even under the wrong
   `frigate/homeassistant/#` prefix), which pointed at a second,
   independent problem: `init_alarm_system()` runs synchronously right
   after `init_dispatcher()`, before the async paho-mqtt connection
   completes, so `MqttClient.publish`/`publish_absolute` silently no-op
   (`if not self.connected: return`) every time -- a pure race, not
   something that would even work by luck. **Fixed** by moving the
   `publish_ha_discovery` call out of `app.py` entirely and into
   `MqttClient._on_connect` (`frigate/comms/mqtt.py`), right after the
   existing `_set_initial_topics()` call -- the exact same "must run after
   `self.connected = True`" precedent already established for Frigate's
   own default-state publishing, so this now also correctly re-publishes
   on every reconnect, not just first boot. `app.py` still calls
   `self.alarm_mqtt_bridge.publish_status()` once at startup (unchanged --
   benefits WS listeners too, and gets naturally refreshed by the first
   real `on_change`), but no longer imports or calls `publish_ha_discovery`
   itself. Live-reconfirmed after the fix: `homeassistant/alarm_control_panel/
   frigate_alarm/panel/config` plus 3 `binary_sensor` configs (fault,
   reporting, one per enabled alarm zone) all appear correctly on a real
   mosquitto broker with correct `state_topic`/`command_topic`/`device`
   grouping.
2. **Home Assistant's alarm card could never actually arm/disarm Frigate.**
   `Dispatcher._on_alarm_command` (the handler for inbound `alarm/set`,
   added in the HA-integration work above) was correctly implemented and
   correctly registered in `_global_settings_handlers`, but `MqttClient`
   never told paho-mqtt to route the `<prefix>/alarm/set` topic to
   `on_mqtt_command` in the first place -- every other global command topic
   (`profile/set`, `notifications/set`, `onConnect`, `restart`) gets an
   explicit `self.client.message_callback_add(...)` in `MqttClient._start()`
   (`frigate/comms/mqtt.py`), and `alarm/set` was simply missing from that
   list, so paho-mqtt silently dropped every message published to it before
   it ever reached the dispatcher. This is the same class of gap as the
   `ws.py` classifier registration miss the phase-12 review already found
   once for outbound topics -- this time on the inbound side, in a
   different file, and it slipped through because `test_alarm_dispatcher_
   command.py` tests `_on_alarm_command` directly rather than through a
   real subscribed MQTT client. **Fixed** with one added
   `message_callback_add(f"{prefix}/alarm/set", self.on_mqtt_command)` call,
   mirroring `profile/set`'s registration exactly. Live-reconfirmed:
   `mosquitto_pub -t frigate/alarm/set -m ARM_NIGHT` -> real `armed_mode:
   night` / `exit_delay` state change and matching `alarm/ha/state: arming`
   publish; `DISARM` -> back to `disarmed`. This is the first time in the
   whole project "arming from the HA card actually works" (flagged
   unconfirmed in the HA-integration section above) has actually been
   exercised end-to-end.

**Test suite note**: `frigate.test.test_alarm_dispatcher_command`'s 4
`test_arm_*_command` tests fail against current code
(`AssertionError: 'exit_delay' != 'armed_away'` etc.) -- confirmed
**pre-existing, not caused by this session's changes** (git-clean before
these edits; the test file itself was never touched). The tests construct
`AlarmSystem(...)` without passing `default_exit_delay_seconds`, which
defaults to 30, so `arm()` correctly lands on `exit_delay` first rather than
jumping straight to `armed_*` -- the test assertions are stale against the
by-design non-instant-arm behavior documented in phase 2. Not fixed this
session (out of scope for the HA/MQTT live-verification ask); a one-line
fix per test (assert `exit_delay` + `armed_mode`, or construct with
`default_exit_delay_seconds=0`) whenever someone picks it up. Full alarm
suite otherwise green: 76 collected in-container (real `cv2`/`zmq`/etc.),
72 pass, 4 pre-existing failures, 0 regressions from this session's 2 file
changes (`frigate/app.py`, `frigate/comms/mqtt.py` -- both `ruff`/`mypy`
clean, confirmed against the real in-container dependency set, not just
`py_compile`).

**Still open** (carried forward, nothing new): a real camera/detection
actually triggering the alarm end-to-end (this session's test config has
one camera whose RTSP source is unreachable from this host, pre-existing
and unrelated), and the frontend `AlarmView.tsx` in a real browser (Vite
was not started, per the "never start the dev server unless asked"
instruction).

## "Control room" session: camera auto-surface on alert + AI verification

Requested as a deliberate product-direction push, planned via EnterPlanMode
before any code (plan saved at the time to
`~/.claude/plans/typed-popping-pearl.md`), two ordered slices.

**Part 1 -- camera auto-surfaces on alert (frontend only, no backend
changes needed)**: `web/src/api/ws.ts` gained `useAlarmEvents()`/
`useAlarmState()`, mirroring the existing `useFrigateEvents()` pattern
exactly. New `web/src/components/alarm/AlarmAlertOverlay.tsx`: a global,
route-independent component (mounted once in `App.tsx`'s `DefaultAppView`,
gated on `config.alarm.enabled`) that watches those two topics and pops a
fixed bottom-right card with the triggering camera's live feed (reusing
`LivePlayer` + `useCameraLiveMode`, the exact hooks the grid dashboard
already uses) plus zone/object/confidence context. Surfaces as early as
`alarm/event` fires (entry-delay, not only full `alarm` state -- the point
is seeing the camera before the alarm finishes triggering), escalates
visually when `is_alarm_active`, and only clears on manual dismiss or the
alarm actually clearing/disarming -- no auto-timeout, matching how a real
panel behaves. `alarm/event` was already correctly scoped per-camera and
`alarm/state` global in `frigate/comms/ws.py`'s classifier (confirmed
working live in the previous session), so this needed zero backend work.

**Part 2 -- smarter AI verification (opt-in per zone, backend)**: adds one
more check after the existing confidence/persistence gates in
`DetectionAlarmAdapter.evaluate()`, using Frigate's *existing* GenAI
provider abstraction (`frigate/genai/`, already used for object/review
descriptions) -- not a new AI integration.
- `ZoneAlarmRule.ai_verification: bool = False` (`frigate/alarm/rules.py`)
  and the matching `AlarmZoneConfig.ai_verification` field
  (`frigate/config/camera/alarm.py`, threaded through `to_rule()`).
  Default off, backwards compatible like every other alarm knob.
- `GenAIClient.generate_alarm_verification()` (`frigate/genai/__init__.py`)
  is the new public entry point -- takes camera/zone/label/confidence/
  event_type/thumbnail, returns `(confirmed, reason) | None`. Uses new
  `build_alarm_verification_prompt()` / `_response_format()`
  (`frigate/genai/prompts.py`), the latter using GenAI structured-output
  JSON schema (same mechanism `build_review_description_response_format`
  already uses) rather than free-text parsing.
- New `frigate/alarm/ai_verification.py`: `AlarmAiVerifier` wraps
  `GenAIClientManager.description_client` with a background
  `threading.Thread` per verification call, mirroring
  `frigate/data_processing/post/object_descriptions.py`'s exact pattern
  for the same reason (network-bound GenAI calls must never run on a
  hot-path thread). **Fails open by design**: no provider configured, a
  request exception, or an unparseable response all resolve to
  `confirmed=True`. This was a deliberate security-domain call, not left
  for the user to decide -- an optional AI layer must never become a
  silent single point of failure that disables the alarm; it can only
  suppress false positives, never mask a real one.
- **Getting a live thumbnail required real tracing, not a guess**: the ZMQ
  tuple `AlarmDetectionThread.run()` unpacks already carried a `frame_name`
  that was being discarded. `frigate/embeddings/maintainer.py` was traced
  as the exact live precedent for turning that into pixels
  (`SharedMemoryFrameManager.get(frame_name, camera_config.frame_shape_yuv)`),
  and `frigate/util/image.py`'s existing `create_thumbnail(yuv_frame, box)`
  helper -- found by reading the file, not written from scratch -- does
  the crop/pad/resize/JPEG-encode in one call, better fit than the
  lower-level `yuv_region_2_bgr` the plan originally named.
- **Wiring** (`frigate/alarm/detection_thread.py`): when a rule has
  `ai_verification` set and a verifier is configured, the thumbnail is
  cropped *synchronously* (the shared-memory frame is only valid for this
  update's lifetime) before handing off to the background thread;
  `state_machine.trigger()`/`record_event()` are deferred to the
  verifier's callback via `functools.partial(self._on_verified,
  entry_delay=entry_delay)` (a plain lambda-with-default-arg mypy couldn't
  type -- caught by running mypy for real in-container, not guessed
  around). No frame available, no verifier configured, or the flag unset
  all fall through to the original immediate-trigger path unchanged --
  confirmed by dedicated regression tests, not just reasoning about it.
  `frigate/alarm/factory.py` gained `build_ai_verifier()`, only
  constructing a `GenAIClientManager` at all if at least one rule actually
  uses the flag. `frigate/app.py` wires it into
  `AlarmDetectionThread.__init__`, which now also takes the live
  `FrigateConfig` (needed for `camera_config.frame_shape_yuv`).
- **A real testability property was knowingly given up, not accidentally
  broken**: `test_alarm_detection_thread.py` used to import cleanly in the
  bare local sandbox (no cv2) because `detection_thread.py` didn't touch
  `frigate.config`. It now imports `FrigateConfig` and
  `frigate.util.image` (cv2), so that file needs the real container now --
  same tier as `test_alarm_config.py` already was. Documented in both
  files' docstrings rather than left to be rediscovered.
- **Tests, all actually run in-container against real cv2/genai deps, not
  just syntax-checked**: new `frigate/test/test_alarm_ai_verification.py`
  (7 tests -- confirmed/rejected/exception-fail-open/unparseable-fail-open/
  no-provider-fail-open, plus a real threading.Event-synchronized
  non-blocking-call test mirroring `test_alarm_queue.py`'s precedent for
  the same reason: proving the thread genuinely doesn't block, not just
  asserting a mock was called). `test_alarm_detection_thread.py` gained 5
  new cases for the deferred-trigger path. `test_alarm_config.py` gained 2
  for the new field. **Two of the new detection-thread tests failed on
  first real run** (asserted `"disarmed"` right after arming with
  `exit_delay_seconds=0`, which actually lands on `"armed_away"` -- a
  copy-paste mistake in the test, not the implementation) and were fixed
  before landing -- left in here as the concrete evidence that these ran
  for real rather than being assumed correct.
- 189 alarm tests collected in-container, 34 of the new/touched ones
  individually re-confirmed green after the fix; the only other failures
  are the 4 pre-existing `test_alarm_dispatcher_command.py` failures
  already documented above (untouched by this session). `ruff`/`mypy`
  clean on every touched file against the real dependency set -- mypy
  caught one genuine issue (`Cannot infer type of lambda`) which is why
  the deferred-trigger callback uses `functools.partial` instead.
- **Live-verified**: enabled `ai_verification: true` on the existing test
  zone in the real devcontainer's `config/config.yaml` (no GenAI provider
  configured there), restarted, confirmed a clean boot (`build_ai_verifier`
  / `GenAIClientManager` construction, `AlarmDetectionThread` taking the
  live config) and a normal `GET /alarm/status` response -- then reverted
  the config line since it was test-only and no real GenAI provider is
  set up in that environment. **Not verified live** (no path to a real
  detection in this environment, documented as an existing gap above):
  an actual AI judgment call, or the fail-open behavior specifically
  triggered by a real detection event rather than by unit test.
- Frontend: `npx tsc --noEmit`, `npx eslint`, `npx i18next-cli extract
  --ci`, `npx vite build` all clean. New `alert.view` i18n key added to
  `web/public/locales/en/views/alarm.json`. Not opened in a browser (dev
  server not started, per standing instruction).

## Easy alarm control UI: quick arm/disarm + zone bypass

Requested directly: arm/disarm existed but only inside Settings -> Alarm,
several clicks deep; zone bypass (temporarily exclude one zone from the
current arm cycle -- a window left open, contractors in one room) didn't
exist at all. Planned via EnterPlanMode; two design questions were asked
and answered up front since they genuinely changed the backend shape:
bypass is **per-arm-cycle** (auto-clears the instant the system actually
disarms, matching real alarm panel convention -- no risk of a forgotten
permanent bypass) and can be **toggled anytime, including while already
armed**, not only before arming.

**Backend** (`frigate/alarm/system.py`): `AlarmSystem` gained
`_bypassed_zones: set[tuple[str, str]]` plus `bypass_zone()`/
`unbypass_zone()`/`is_bypassed()`. Auto-clear is deliberately conditional,
not unconditional: `disarm()` only clears it when the state machine
actually lands on `disarmed` -- `disarm()` during an active alarm silences
into `alarm_memory` instead (existing behavior), and bypass has to survive
that until the operator genuinely stands the system down via a second
`disarm()` or `clear()` (both verified with dedicated tests, including the
alarm_memory case explicitly). `ZoneStatus`/`zone_status()` gained
`bypassed`, and `armed` was made additionally conditional on *not*
bypassed -- meaning `status()`'s existing per-zone dict (already fed
as-is into `AlarmMqttBridge.publish_status()` via `json.dumps(zone)`,
per the phase-9 design) needed no changes at all to get bypass onto the
`<camera>/alarm_zone/<zone>/state` MQTT/WS topic; confirmed live rather
than just reasoned about (see below). `AlarmDetectionThread._evaluate()`
skips a zone entirely (before it ever reaches `DetectionAlarmAdapter`) if
`alarm_system.is_bypassed(camera, zone)` -- the adapter itself stays
completely unaware bypass exists, consistent with its existing "static
rules + armed_mode, nothing else" boundary.

**API**: new `POST /alarm/zones/{camera}/{zone}/bypass` (body
`{"bypassed": bool}`), admin-gated like arm/disarm/clear, 404 (not the
generic 400 "not enabled" body) for an unknown camera/zone pair --
distinguishing "bad request" from "alarm disabled globally".
`AlarmZoneStatusResponse` gained `bypassed: bool`.

**A real, unrelated gap was found and fixed as a side effect of
regenerating the OpenAPI spec**: `docs/static/frigate-api.yaml` had never
actually contained the `/alarm/*` paths at all -- not because this
change broke it, but because this is the first time in the whole project
`generate_api_auth_spec.py` could actually be *run* (every earlier phase
noted "could not run here, no fastapi" and deferred it). Running it now
added all 6 alarm endpoints (the 5 pre-existing ones plus the new bypass
one) in one pass, confirmed by `git diff` showing pure insertions, zero
deletions, nothing outside `/alarm/*` touched. `--check` now passes
clean. Generated inside the running `frigate` container (script + prior
yaml copied in via `docker cp`, since the runtime image doesn't ship
repo-root dev scripts) and copied back out to the host.

**Frontend**: arm/disarm/clear mutation logic (previously inline in
`AlarmView.tsx`) extracted into `web/src/hooks/use-alarm-actions.ts`,
gaining `setZoneBypass` alongside it -- both `AlarmView.tsx` and the new
quick-control widget key off the same `"alarm/status"` SWR cache, so
mutating from either place refreshes both with no extra wiring. New
`web/src/components/menu/AlarmControl.tsx`, modeled directly on
`AccountSettings.tsx`'s `Container`/`Trigger`/`Content` polymorphic
pattern (`DropdownMenu` on desktop, `Drawer` on mobile via `isDesktop`
from `react-device-detect`) rather than built from scratch -- that
pattern already solves "reachable from every page, desktop and mobile"
exactly. Deliberately does *not* wrap its buttons/switches in
`DropdownMenuItem`/`DrawerClose` (unlike `GeneralSettings.tsx`'s nav-item
precedent) since those auto-close on click, which is wrong for a bypass
`Switch` you might flip several times in a row. Trigger shows a shield
icon with a small colored dot reflecting current state, reusing the same
`ALARM_STATE_BADGE_CLASSES` map now hoisted to `web/src/utils/alarmUtil.ts`
so `AlarmView.tsx` and `AlarmControl.tsx` can't drift apart. Mounted in
both `Sidebar.tsx` (desktop) and `Bottombar.tsx` (mobile) next to
`GeneralSettings`/`AccountSettings` -- confirmed those two are the
complete desktop+mobile mount set by grepping for every place they
render, not assumed. `AlarmView.tsx` itself also gained a bypass
`Switch` per zone in its existing zone list, next to the existing status
badge.

**Tests, all run in-container against real deps**: `test_alarm_system.py`
gained a `TestBypass` class (round-trip, settable-while-armed, disarm
clears it, disarm-during-active-alarm does *not* clear it, clear() does,
on_change fires) plus a zone_status case;
`test_alarm_detection_thread.py` gained bypassed/unbypassed-zone cases;
`test_http_alarm.py` gained a `TestAlarmZoneBypass` class (bypass,
unbypass, unknown zone -> 404, admin-gating, disabled -> 400, status
reflects it). 91 tests collected across the full touched set, all green,
zero regressions. `ruff`/mypy clean on every touched backend file.

**Live-verified end to end**, not just unit-tested: armed the real test
zone over HTTP, confirmed `armed: true, bypassed: false`; bypassed it,
confirmed `armed: false, bypassed: true` in the same `GET /alarm/status`
call; subscribed to the real MQTT broker and confirmed
`frigate/dehothouse/alarm_zone/driveway/state` carries the new
`bypassed` field with no code changes needed there; disarmed and
confirmed bypass cleared automatically on the next status check.

**Frontend**: `tsc`/`eslint`/`i18next-cli extract --ci`/`vite build` all
clean. Not opened in a browser (dev server not started, per standing
instruction) -- the quick-control widget's actual look/feel and the
Drawer-vs-DropdownMenu responsive switch have not been visually
confirmed, only that they compile and type-check against the real
component APIs.

---

## Security Command Centre roadmap

**STATUS: ALL 5 PARTS DONE.** Parts 1-5 below are all complete and
live-verified; the roadmap as originally scoped is finished. If the user
wants to extend this further, that's new scope -- treat it as a fresh
roadmap addition (its own EnterPlanMode + sign-off), not a continuation
of "part 6" implicitly.

**Goal, stated by the user**: turn the alarm engine (done, above) into "a
full security command centre type of program" -- not one feature, a
product direction. Explicitly requested to persist across sessions: this
section is that persistence. **Read this section first** if picking up
new work here with no memory of the conversation that produced it;
update it (status + one-line outcome note, following the style already
used for every phase above) immediately after finishing each part, the
same discipline the original 12-phase alarm-engine plan used.

Working agreement: **part for part** -- one part fully designed
(EnterPlanMode, written plan, user sign-off), built, tested against real
dependencies inside the running `frigate`+`mqtt` containers, and
live-verified before starting the next. Do not batch multiple parts in
one sitting. Order below is a recommendation made when the roadmap was
proposed, not a hard commitment -- confirm with the user before starting
a part if priorities may have shifted since this was written.

1. **Incident / operator-action audit log** -- STATUS: **done**, live-
   verified. New `AlarmAuditLog` table (`frigate/models.py`, migration
   `036`), written via `frigate/alarm/audit.py`'s `record_alarm_audit()`
   from the two call sites that mutate alarm state --
   `frigate/api/alarm.py` (arm/disarm/clear/bypass, `actor` = the
   `remote-user` header) and `frigate/comms/dispatcher.py`'s
   `_on_alarm_command` (MQTT-driven arm/disarm, `actor=None`). Only
   successful actions are recorded, not rejected attempts -- a deliberate
   scope line, not an oversight (failed attempts already go to the
   application log). New `GET /alarm/audit`, mirrors `/alarm/events`
   exactly. `AlarmView.tsx` gained an Audit Log table alongside the
   existing Recent Events table.
   - **Two real bugs, both caught only by live-testing against the real
     app, not by the 30 unit/HTTP tests that all passed first**:
     (1) `datetime.now(UTC)` stores with a `+00:00` suffix that peewee's
     `DateTimeField` can't parse back out of its own format list, so
     reads silently returned a raw `str` instead of a `datetime` --
     fixed with a naive-UTC timestamp plus an explicit
     `.replace(tzinfo=UTC)` on read before converting to epoch (the
     container's local tz is UTC+2, so the naive `.timestamp()` call
     alone would have silently shifted every audit timestamp by 2 hours).
     (2) `AlarmAuditLog` was never added to the real `models = [...]`
     list `frigate/app.py` binds to the production database at startup
     -- every write 500'd with `peewee.InterfaceError: Query must be
     bound to a database`. This is exactly why: `BaseTestHttp`'s test
     harness binds whatever model list you pass it directly in
     `setUp()`, completely bypassing `app.py`'s own binding logic, so no
     amount of HTTP-layer unit testing could ever have caught a model
     missing from that real list. Confirmed fixed by a full live
     sequence -- HTTP arm/bypass/disarm, MQTT arm/disarm (mirroring the
     HA-card path) -- then a container **restart**, re-querying, and
     confirming all 5 entries survived, which is the entire reason this
     is DB-backed instead of an in-memory deque like the event history.
2. **Multi-camera incident view** -- STATUS: **done**, verified to the
   extent this environment allows (see caveat below). Pure frontend
   change, one file: `AlarmAlertOverlay.tsx`'s state changed from a
   single `activeEvent` to `activeEvents: Map<camera_id, AlarmEvent>` --
   a new `alarm/event` upserts that camera's entry instead of replacing
   the whole panel, so two zones on two different cameras triggering as
   part of the same incident now both stay visible. Capped at
   `MAX_VISIBLE_CAMERAS = 4` with a "+N more" badge past that (real
   i18next pluralization gotcha caught here: a `{ count }` interpolation
   needs `_one`/`_other` suffixed keys, not one generic key -- the
   `i18next-cli extract --ci` gate correctly failed on the first attempt
   and named the exact fix). Single-camera case renders the same
   `AlarmCameraTile` as the multi-camera grid, just not wrapped in a
   grid container -- a deliberate DRY choice over preserving the exact
   prior DOM structure (footer button vs. inline button), since there
   was no way to visually verify pixel fidelity here anyway. No backend
   changes: `alarm/event` already carried everything needed, and
   `useCameraLiveMode` already accepted multiple cameras.
   - **Caveat, called out in the plan before building rather than
     discovered after**: this environment has exactly one configured
     camera (with an unreachable RTSP source), so an actual two-camera
     incident could not be produced to watch this live -- unlike every
     other part so far, verification here is `tsc`/`eslint`/
     `i18next-cli extract --ci`/`vite build` all clean plus manual
     read-through of the map-upsert logic, not an observed live
     multi-camera panel. Also does not reconstruct an in-progress
     incident's camera set on a fresh page load (only accumulates events
     received while mounted) -- a real, well-scoped follow-up that Part
     1's audit log (querying since the last "arm" action) would make
     clean to build, deliberately left out as extra scope beyond what
     was asked.
3. **Scheduling (auto arm/disarm)** -- STATUS: **done**, live-verified,
   including a real fire against the running container. E.g. "always
   armed away at 23:00, disarmed at 07:00" without a human doing it
   manually every time. Confirmed with the user up front that entries
   need per-weekday granularity (weeknight vs. weekend times differ),
   not just one flat daily time.
   - Researched first, not assumed: Frigate has no existing schedule/
     cron concept anywhere in the codebase (recording, motion,
     notifications, genai all lack one) and no scheduling dependency in
     `pyproject.toml`/requirements. A hand-rolled polling thread was the
     right fit, not a new dependency.
   - `frigate/alarm/schedule.py`: `ScheduleEntry`, a plain frozen
     dataclass (`time: str` "HH:MM", `mode: ArmedMode | None` -- `None`
     means disarm, `days: frozenset[int]` -- empty means every day),
     mirroring `rules.py`'s "core stays free of `frigate.config`"
     split.
   - `frigate/alarm/scheduler.py`: `AlarmScheduler(threading.Thread)`,
     modeled directly on `AlarmDetectionThread` -- `run()` is a thin
     `stop_event.wait(poll_interval)` loop (default 30s), with the
     actual decision logic split into a pure, directly-testable
     `_check_and_fire(now: datetime)` method (same reasoning as
     `AlarmDetectionThread._evaluate()`). Dedup via
     `_fired_today: dict[int, date]` keyed by entry index, since a 30s
     poll interval checks each matching minute roughly twice.
     `_fire()` calls `alarm_system.arm()`/`.disarm()` and
     `record_alarm_audit(..., "schedule", ...)`, wrapped in
     `try/except InvalidAlarmTransition` exactly like `dispatcher.py`'s
     `_on_alarm_command` (e.g. the schedule says "arm" but the system
     is already armed or faulted -- log at debug, move on). No new
     state-change plumbing needed: `arm()`/`disarm()` already call
     `AlarmSystem._notify()` internally, so MQTT/WS/frontend pick up a
     scheduled change exactly like a manual one, automatically.
   - Config: `AlarmScheduleEntryConfig`/`AlarmScheduleConfig` added to
     `frigate/config/alarm.py` alongside the existing
     `AlarmReportingConfig`, same title/description/validator
     conventions (`field_validator` for HH:MM format and 0-6 day
     range). `AlarmConfig.schedule` field added. `to_entry()`/
     `build_entries()` mirror `AlarmZoneConfig.to_rule()`/
     `CameraAlarmConfig.build_rules()` exactly.
   - Wiring: no new `factory.py` function needed -- `AlarmScheduler`,
     like `AlarmDetectionThread`, is constructed directly in
     `frigate/app.py`'s `start_alarm_system()` (a deliberate deviation
     from the original plan's proposed `build_alarm_scheduler()`
     factory wrapper, made during implementation once it was clear
     `config.alarm.schedule.build_entries()` already did the only real
     work a factory function would have done -- matches existing
     precedent better, not scope creep). Stopped in `stop()` alongside
     `alarm_detection_thread.stop()`, before `alarm_system.stop()`, so
     nothing can fire an `arm()`/`disarm()` into a system already being
     torn down.
   - Tests: `frigate/test/test_alarm_scheduler.py` (8 cases -- fires on
     exact minute match, disarm branch, outside-minute no-op, same-day
     dedup, fires again next day, `days` filter respected, empty `days`
     means every day, `InvalidAlarmTransition` swallowed cleanly), plus
     5 new cases in `test_alarm_config.py`. All pass in-container (same
     peewee-needing tier as `test_alarm_dispatcher_command.py`, not
     runnable on the bare host). Full in-container `unittest discover`:
     1139 tests (up from 1126), only the same 4 pre-existing
     `test_alarm_dispatcher_command.py` failures from the
     zone-normalization session, zero new regressions. `ruff`/mypy
     clean on every touched file.
   - **Live-verified with an actual scheduled fire, not just
     reasoning**: added a real near-term schedule entry
     (`{"time": "10:01", "mode": "away"}`) to the running container's
     `config/config.yaml`, restarted, and confirmed over real HTTP that
     the system transitioned `disarmed` -> `exit_delay` ->
     `armed_away` at exactly the scheduled time with zero manual
     intervention, and that `GET /alarm/audit` recorded
     `source: "schedule"`. Separately verified the mid-restart
     resilience the design relies on (no timer set up in advance, just
     a wall-clock comparison every poll): restarted the container 10
     seconds into a new target minute and confirmed the scheduled arm
     still fired within that same minute. Both test entries removed
     and the original `config.yaml` restored afterward.
   - **An unplanned but valuable side effect of this live test**: a
     real "person" detection on the real `dehothouse` camera actually
     triggered a genuine `ALARM` state during the verification window
     (confirmed via `GET /alarm/events`) -- meaning the camera's RTSP
     feed is reachable now, unlike every earlier session's repeated
     "RTSP unreachable" caveat. This is the first real end-to-end
     detection -> alarm-trigger confirmation in the whole project,
     previously an explicitly open item (see the "Control room" and
     "Easy alarm control UI" sections above). `clear()` was called
     afterward to reset state.
   - Frontend: `web/src/views/settings/AlarmScheduleSetup.tsx` (new),
     mirrors `AlarmZoneSetup.tsx`'s exact draft-state/`config/set`-PUT
     pattern -- one card, a list of entry rows (time input, an
     away/home/night/disarm `Select`, a 7-day `ToggleGroup`), add/
     remove buttons, one enable switch, and a client-side-only "next
     scheduled action" readout (pure function of the entries + current
     time, no backend endpoint needed). Mounted in `AlarmView.tsx`
     alongside `<AlarmZoneSetup />`. `frigateConfig.ts` gained the
     schedule shape (same hand-maintained-mirror gap as every earlier
     phase). `tsc`/`eslint`/`i18next-cli extract --ci`/`vite build` all
     clean. `generate_config_translations.py` was run in-container
     (repo-root dev script, not shipped in the runtime image --
     `docker cp`'d in, run, output copied back out) to pick up the new
     Pydantic field titles/descriptions into
     `web/public/locales/en/config/global.json`, per this repo's own
     CLAUDE.md instructions -- pure additions, nothing else touched.
     Not opened in a browser (dev server not started, per standing
     instruction) -- visual layout/responsiveness of the new schedule
     card has not been confirmed, only that it compiles and type-checks
     against the real component APIs.
4. **Notifications beyond MQTT** -- STATUS: **done**, live-verified to
   the extent possible without a real subscribed browser or a real
   WhatsApp send (see below). Push/WhatsApp when something fires, for
   when nobody is looking at a screen or connected to the MQTT broker.
   Email/SMS were explicitly descoped this part (see below).
   - Researched first, per this item's own instruction: confirmed
     Frigate already has a working push-notification system
     (`WebPushClient`, `frigate/comms/webpush.py` -- browser Push API +
     VAPID, already wired to review/trigger events via a topic fan-out
     on `Dispatcher.publish()`) and zero existing SMS/email/WhatsApp
     code anywhere.
   - Asked the user which channels to build. Answer: check
     `/home/raine/Documents/LockNAlert/source/locknalert-api` (a
     separate project of the user's) for how *it* sends WhatsApp
     messages, and add WhatsApp alongside push -- not email/SMS. That
     project sends via a **self-hosted OpenWA instance**
     (`app/openwa_client.py`: `POST {base_url}/sessions/{session_id}/
     messages/send-text`, `{"chatId": "<digits>@c.us", "text": ...}`,
     `X-API-Key` header), confirmed live on this host
     (`openwa-api`/`openwa-docker-proxy`/`openwa-postgres` containers).
     Mirrored the REST contract and the rate-limiting instinct from that
     project, not its code verbatim -- it's async (httpx) because that
     whole app is async; this uses synchronous `requests` (already a
     Frigate dependency) since every file in `frigate/alarm/` is
     thread-based, not async.
   - **Push**: `AlarmMqttBridge.publish_event()` already publishes a
     global `"alarm/event"` topic through `Dispatcher.publish()` on
     every qualifying detection, and `WebPushClient` already receives
     every dispatcher publish call -- it just didn't act on this topic
     before. Added one branch (`webpush.py`) plus a new
     `send_alarm_alert()` method mirroring the existing `send_alert()`
     almost exactly (same `_user_has_camera_access()`-filtered loop over
     `web_pushers`, same `send_push_notification()` call), reusing the
     existing per-camera `notifications.enabled` flag rather than adding
     a redundant alarm-specific toggle (same sharing already used by
     `triggers`/`camera_monitoring`). **Deliberately skips**
     `_within_cooldown()`/`is_camera_suspended()` -- both exist to
     reduce noise from routine review notifications, and an actual alarm
     trigger must never be silenced by settings meant for that, not
     this.
   - **WhatsApp**: new `AlarmWhatsAppConfig` (`frigate/config/alarm.py`,
     global only -- one sending session per instance, same shape as
     `AlarmReportingConfig`) with **no hardcoded default `api_base_url`**
     -- Frigate is a public repo; the user's OpenWA host/session/API key
     are their own private infrastructure and never get a default value,
     nor do they appear anywhere in this file, tests, or committed code,
     only in the user's own gitignored `config.yaml`.
     `frigate/alarm/notify_whatsapp.py`: `WhatsAppNotifyConfig` (plain
     dataclass, same core/config split as `rules.py`/`schedule.py`, kept
     free of `frigate.config` -- `AlarmWhatsAppConfig.to_notify_config()`
     does the conversion) and `AlarmWhatsAppNotifier` (stateful, unlike
     the bare-function SIA/Contact ID senders, since it needs
     per-(camera, zone) cooldown tracking across calls -- mirrors the
     LockNAlert precedent's own instinct to rate-limit WhatsApp
     specifically so a burst of qualifying detections during one
     incident can't spam a phone). `notifier.notify` matches
     `ReportingQueue`'s `send: Callable[[AlarmEvent], bool]` signature
     exactly, so it plugs directly into the **same `ReportingQueue`
     class from phase 7** (`build_alarm_whatsapp_queue` in
     `factory.py`) -- zero new queue/retry/thread code needed, just
     reuse.
   - **Wiring** (`frigate/app.py`, `init_alarm_system()`):
     `AlarmSystem.on_event` is a single-slot callback already occupied
     by the MQTT bridge -- rather than building a generic multi-listener
     event bus for exactly two consumers (over-engineering), a small
     composed closure fans out to both: `mqtt_bridge.publish_event(event)`
     then `alarm_whatsapp_queue.enqueue(event)` if configured. Push needed
     no equivalent change -- it already rides the dispatcher topic
     `publish_event` triggers, unconditionally. **A real mypy catch, not
     just reasoning**: the closure originally read
     `self.alarm_mqtt_bridge.publish_event(...)`, which mypy correctly
     flagged as `AlarmMqttBridge | None` since a deferred closure can't
     inherit the surrounding `if self.alarm_system is None: return`
     narrowing -- fixed by closing over a local `mqtt_bridge` variable
     bound once at construction instead of re-reading the optional
     attribute inside the closure. `alarm_whatsapp_queue` start/stop
     wired alongside the existing `reporting_queue` start/stop in
     `start_alarm_system()`/`stop()`.
   - **No frontend changes** -- `AlarmWhatsAppConfig`'s fields all have
     `title`/`description` like every other alarm config model, so the
     existing schema-driven config form (already live for `alarm`/
     `global` since phase 10) renders it automatically, exactly like
     `AlarmReportingConfig` itself never got a hand-built component.
     `generate_config_translations.py` run in-container afterward (same
     pattern as Part 3) -- picked up both the new `whatsapp` section and,
     as a harmless side effect, the camera-level `alarm`/`zones` section
     into `cameras.json` for the first time (a pre-existing gap from
     phase 4/10 that had just never been regenerated into that specific
     file until now; confirmed via `git diff --stat` as pure additions,
     unrelated to this session's own changes).
   - Tests: `frigate/test/test_alarm_notify_whatsapp.py` (11 cases --
     chat-id normalization, message formatting, successful/failed send,
     request-exception handling, cooldown skip and its
     per-camera/zone scoping, failed sends don't start a cooldown) runs
     on the **bare host sandbox**, no cv2/peewee needed (`requests` is
     already installed there) -- same tier as `test_alarm_sia.py`. Plus
     5 new `test_alarm_config.py` cases. 34 tests total for this part,
     all pass in-container too; full in-container `unittest discover`:
     1155 tests (up from 1139), same 4 pre-existing
     `test_alarm_dispatcher_command.py` failures, zero new regressions.
     `ruff`/mypy clean on every touched file.
   - **Live-verified against the real running container** (not just
     unit tests): rebuilt the image, confirmed a clean boot with
     notifications enabled (WebPushClient generated a fresh VAPID
     keypair on first boot with the new config, no errors). Directly
     exercised the real `WebPushClient.publish("alarm/event", ...)` path
     against the real bound database and real config (a standalone
     script binding to the same `frigate.db`, mirroring the technique
     used for the zone-normalization live verification) -- confirmed
     the new topic branch decodes the payload, checks
     `notifications.enabled`, and reaches `send_alarm_alert()` with zero
     exceptions. **Corrected a mistake made during this same
     verification pass, not swept under the rug**: an early attempt to
     toggle `notifications.enabled` in the live `config.yaml` used a
     naive string-replace that matched the wrong `dehothouse:` key
     (`go2rtc.streams.dehothouse`, not `cameras.dehothouse`) and produced
     structurally invalid YAML -- caught before it was ever applied to
     the running process, restored from the pre-edit backup, and redone
     with a proper `yaml.safe_load`/`yaml.dump` round-trip instead of
     string matching. Config restored to its original state and the
     container restarted clean afterward either way.
   - **Not verified live, and explicitly flagged, same posture as the
     SIA DC-09 stub**: an actual push notification landing on a real
     subscribed browser (no real Push API subscription exists in this
     environment -- `web_pushers` resolved to one user with zero
     subscriptions), and a real WhatsApp message via a real OpenWA
     instance (would send a real message to a real phone -- the plan
     explicitly calls this out as something to do only with the user's
     own credentials and explicit opt-in during a session, never
     autonomously; that opt-in was not given this session, so
     `notify_whatsapp.py`'s request-shape correctness rests on the unit
     tests against a mocked `requests.post`, not a real OpenWA
     response).
5. **Health / reporting dashboard** -- STATUS: **done**, live-verified,
   including a real detection persisting through the new table and
   surviving a real restart. Camera uptime, false-alarm rate, SIA/
   Contact ID (and now WhatsApp) reporting-link health, all in one
   place instead of scattered across `AlarmView.tsx`'s status badges
   and `reporting_healthy`. Last part of the roadmap -- all 5 done.
   - Researched first via two Explore agents: camera uptime
     (`connection_quality`/`reconnects_last_hour`/`stalls_last_hour`/
     `camera_fps`) is already fully tracked and exposed via `GET
     /stats`, just never surfaced on the alarm dashboard. The WhatsApp
     `ReportingQueue` (Part 4) was confirmed invisible anywhere --
     built and held only on `FrigateApp`, never passed into
     `AlarmSystem`. False-alarm rate had zero existing infrastructure
     at all: `AlarmEvent`s were never persisted (in-memory
     `deque(maxlen=100)`, lost on restart) and nothing links an
     `AlarmEvent` back to a Frigate `Event`/`ReviewSegment` row. Asked
     the user explicitly whether to build the full persisted-history +
     marking feature or a reduced version -- confirmed: build it all.
   - **New `AlarmEventLog` table** (`frigate/models.py`, migration
     `042_create_alarm_event_log_table.py`), mirroring `AlarmAuditLog`'s
     exact precedent from phase 1 -- `timestamp`/`event_type`/`camera`/
     `zone`/`object_type`/`confidence`/`source`/`message`, plus
     `false_alarm` (bool, default False). `frigate/alarm/event_log.py`'s
     `record_alarm_event_log()` mirrors `audit.py`'s
     `record_alarm_audit()` almost exactly, **including the naive-UTC
     timestamp fix already learned the hard way in phase 1** (a
     tz-aware `datetime.now(UTC)` stores with a `+00:00` suffix peewee
     can't parse back out) -- reused, not rediscovered. `AlarmEventLog`
     added to `frigate/app.py`'s real `models = [...]` binding list
     proactively, in the same edit that added the class, continuing
     every part's discipline since phase 1's live-500 mistake.
   - **New API**: `GET /alarm/event_log` (mirrors `GET /alarm/audit`
     exactly), `GET /alarm/event_log/summary?days=30` (total/false-alarm
     count/rate/daily breakdown, grouped in Python not SQL `GROUP BY` --
     a home alarm's volume doesn't justify the complexity), `POST
     /alarm/event_log/{id}/false_alarm` (admin-gated, mirrors the
     zone-bypass endpoint's shape, 404 for an unknown id, also calls
     `record_alarm_audit("false_alarm", ...)` since marking something
     false-alarm is an operator action same as bypass). `GET
     /alarm/events` (the existing in-memory, most-recent-100 endpoint)
     was deliberately left untouched -- different purpose (live/
     low-latency vs. historical/annotatable), same coexistence already
     established between `/alarm/events` and `/alarm/audit`.
   - **Architecture fix, not just a new field**: exposing
     `whatsapp_healthy` required giving the WhatsApp `ReportingQueue`
     the same first-class treatment `reporting_queue` already has.
     `AlarmSystem.__init__` gained a `whatsapp_queue` param (defaults
     `None`, fully backwards compatible with every existing call site/
     test), `record_event()` enqueues to it alongside `reporting_queue`,
     `status()` gained `"whatsapp_healthy"`. `build_alarm_system()`
     (`factory.py`) now builds and passes it in. `frigate/app.py` lost
     its standalone `self.alarm_whatsapp_queue` attribute entirely --
     the only reason it lived outside `AlarmSystem` in Part 4 was
     `on_event`'s single-slot-callback limit, which was never actually
     a constraint on the *queue*, only on the notification callback.
     The `_on_alarm_event` closure simplified as a result: WhatsApp
     enqueueing moved into `record_event()` itself, leaving the closure
     with just MQTT publishing and the new `record_alarm_event_log()`
     call.
   - Tests: `test_alarm_event_log.py` (7 cases, mirrors
     `test_alarm_audit.py` exactly including its own naive-UTC
     regression-guard test), extended `test_alarm_system.py` (6 new
     whatsapp-queue/status cases, all pass on the **bare host** -- pure
     `frigate.alarm.*`, no cv2/peewee needed), extended
     `test_http_alarm.py` (11 new cases: list/filter/summary/toggle/
     404/admin-gating/audit-trail). 1176 tests collected in-container
     (up from 1155), same 4 pre-existing `test_alarm_dispatcher_command.py`
     failures, zero new regressions. `ruff`/mypy clean on every touched
     file.
   - **Live-verified with real detections, not just seeded rows**:
     armed the real system, waited for the real `dehothouse` camera's
     RTSP feed to produce genuine person detections (it fired 10 times
     during this pass), confirmed each one landed in `GET
     /alarm/event_log` with real confidence values via real HTTP,
     toggled false-alarm on one and confirmed the summary/rate and
     audit trail updated correctly, confirmed 404/403 error handling.
   - **A real testing-harness gotcha caught and resolved during this
     same pass**: an early admin-gating check via nginx (port 5000)
     returned 200 for a viewer-role request against the new endpoint,
     which looked like a real authorization bug. Isolated by hitting
     the FastAPI backend directly on port 5001 (bypassing nginx)
     instead, which correctly returned 403 -- confirming this was
     nginx's own local-network auth convenience layer overriding the
     `Remote-Role` header for anonymous curl requests (the same class
     of nginx-layer testing quirk the phase-9 session already
     documented for its 5s response cache), not a gap in this session's
     code. Re-ran an *existing, already-shipped* admin-gated endpoint
     (`/alarm/disarm`) the same way to confirm the quirk wasn't
     specific to the new code, then re-verified the new endpoint
     directly against port 5001 for both roles before moving on.
   - **Restart-survival explicitly confirmed, the actual point of this
     table existing**: with real detection rows persisted, restarted
     the container and confirmed `GET /alarm/event_log/summary` still
     showed the same total, while `GET /alarm/events` (the in-memory
     endpoint) correctly reset to empty -- exactly the intended
     difference between the two endpoints, not just asserted.
   - `generate_api_auth_spec.py` run in-container (new endpoints,
     `docs/static/frigate-api.yaml` didn't exist in the runtime image so
     the directory had to be created before copying the file in) --
     pure additions, confirmed via `git diff --stat`. No config schema
     changed this part, so `generate_config_translations.py` was not
     needed.
   - Frontend: new `web/src/views/settings/AlarmHealthDashboard.tsx`
     (camera-uptime cards reusing `ConnectionQualityIndicator` from
     Frigate's own System page, a false-alarm summary + a modest
     ApexCharts stacked bar chart of daily real-vs-false counts --
     `react-apexcharts` was already a dependency, no new charting
     library -- and an event-log table with a false-alarm `Switch` per
     row mirroring the existing zone-bypass `Switch` pattern), mounted
     in `AlarmView.tsx` between the Zones and Events sections. The
     WhatsApp health badge is one small addition to the existing top
     badge row (which already had a symmetric `reporting_healthy`
     badge), not a new section. New `use-alarm-event-log.ts` hook
     following `use-alarm-actions.ts`'s exact pattern.
     `tsc`/`eslint`/`i18next-cli extract --ci`/`vite build` all clean.
     Not opened in a browser (dev server not started, per standing
     instruction) -- visual layout of the new dashboard section and the
     chart's light/dark theming have not been visually confirmed, only
     that they compile and type-check.

**Already done, load-bearing for everything above** (full detail in the
phase-by-phase sections earlier in this file, not repeated here): the
alarm state machine and zone rules (`frigate/alarm/`), MQTT/HA
integration including inbound `alarm/set` commands, opt-in AI
verification via the existing GenAI provider abstraction, the global
camera-auto-surface-on-alert overlay, and the quick arm/disarm/bypass
control reachable from every page.

### Post-roadmap addition: cross-camera person trail

Requested after the 5-part roadmap above was already complete -- picked by
the user from a shortlist of next-step ideas. During an active incident,
show that the same person was likely seen on another camera nearby in
time ("also seen on driveway at 14:32"), surfaced on the existing
camera-auto-surface overlay (`AlarmAlertOverlay.tsx`, Part 2 above).
Planned via EnterPlanMode with two Explore agents first, since it touches
the alarm pipeline, the DB, the API, and the frontend.

**Entirely glue, no new ML** -- research confirmed Frigate already
computes both signals this needs: face recognition (opt-in,
`FaceRecognitionConfig`) already writes a matched name to `Event.sub_label`,
and semantic/thumbnail search (opt-in, `semantic_search.enabled`) already
has a working cross-camera k-NN cosine-similarity query,
`EmbeddingsContext.search_thumbnail()` (`frigate/embeddings/__init__.py`),
already used by `GET /events/search?search_type=similarity`. Both stayed
opt-in/off-by-default here too -- the trail endpoint just returns an empty
list when neither is enabled, same "disabled feature returns empty/400"
posture used throughout `frigate/api/alarm.py`.

- **Carried the tracked-object id through the pipeline**, which nothing
  previously did: `AlarmEvent` (`frigate/alarm/event.py`) gained
  `object_id: str | None`, set by `DetectionAlarmAdapter.evaluate()`
  (`frigate/alarm/adapter.py`) from the `object_id` parameter it already
  received but only used for internal persistence tracking. This is
  exactly the Frigate tracked-object id, confirmed to equal `Event.id`
  once persisted by reading `frigate/events/maintainer.py:363`
  (`Event.id == event_data["id"]`), not guessed. Threaded through
  `AlarmMqttBridge.publish_event()` (one explicit dict key, since that
  method builds its payload field-by-field, not via `asdict`),
  `record_alarm_event_log()`, and `GET /alarm/events`'s response dict.
  `migrations/043_add_object_id_to_alarm_event_log.py` adds a nullable,
  indexed column to `AlarmEventLog` for historical lookups, following the
  exact additive-migration pattern used for 036-038.
- **New `frigate/alarm/trail.py`**: `find_trail(object_id, embeddings,
  window_seconds)`. Same "glue layer allowed to import frigate.models/
  frigate.embeddings" precedent as `event_log.py`/`ha_discovery.py` --
  `frigate/alarm/system.py` itself stays DB-free by design. Combines a
  cheap exact `Event.sub_label` match (free, no vector search, "named"
  match type) with `search_thumbnail()` scoped to a candidate id list
  built from a plain indexed `Event.start_time`/`Event.camera` query
  ("visual" match type, only when `embeddings` is not `None`). **A real
  bug in the existing `search_thumbnail()` was read directly from its own
  docstring, not discovered the hard way**: its `event_ids` filter is
  documented as broken on the currently pinned sqlite-vec version, so
  `find_trail()` re-checks candidate-set membership in Python rather than
  trusting the SQL filter -- covered by a dedicated regression test
  (`test_visual_match_ignores_ids_outside_candidate_set`) that fabricates
  exactly that broken-filter scenario. `VISUAL_MATCH_MAX_DISTANCE = 0.5`
  is an untuned heuristic cosine-distance cutoff -- flagged in-code as
  needing live tuning, same posture as every other "can't verify against
  real embeddings/photos in this sandbox" caveat in this file.
- **New `GET /alarm/trail/{object_id}`** (`frigate/api/alarm.py`),
  `allow_any_authenticated()` like the other GET endpoints. New response
  models `AlarmTrailMatchResponse`/`AlarmTrailResponse`. Regenerating
  `docs/static/frigate-api.yaml` via `generate_api_auth_spec.py` is
  **still outstanding** -- needs the real container (no fastapi here),
  not run this session.
- Frontend: `web/src/types/alarm.ts` gained `AlarmTrailMatch`/`AlarmTrail`
  and `object_id` on `AlarmEvent` (hand-maintained mirror, same gap as
  every earlier phase). New `web/src/hooks/use-alarm-trail.ts` (SWR,
  fetch skipped via a `null` key until an `object_id` exists -- standard
  SWR conditional-fetch, no precedent needed). `AlarmAlertOverlay.tsx`'s
  `AlarmCameraTile` gained an "Also seen on" badge row, purely additive to
  the multi-camera-incident layout from the "Control room" session.
- **Tests, and this phase had more of the sandbox's "actually runs here"
  tier than usual**: `frigate/alarm/event.py`/`adapter.py`/`mqtt_bridge.py`
  have zero DB dependency, so their new/extended tests
  (`test_alarm_adapter.py`, `test_alarm_mqtt_bridge.py`) ran for real in
  this bare sandbox, not just lint-checked -- confirmed green. New
  `frigate/test/test_alarm_trail.py` (13 cases) and the `test_alarm_event_log.py`/
  `test_http_alarm.py` extensions need `peewee`/`fastapi`, the usual gap,
  syntax/lint-only here. Full `test_alarm_*.py` discovery re-run after
  this session's changes: same 9 pre-existing import-gap files as before
  (now including the new `test_alarm_trail.py`, expected) plus one
  pre-existing flaky threading test in `test_alarm_queue.py` (passes in
  isolation, confirmed unrelated -- that file was never touched this
  session), zero new regressions.
- **Not yet live-verified** (no GPU, no `cv2`/`fastapi`/peewee in this
  sandbox, same posture as every other feature in this file that touches
  real ML): enable both `face_recognition` and `semantic_search` in a
  real container, enroll a named face, trigger an alarm on one camera,
  walk the same person past a second camera, and confirm
  `GET /alarm/trail/{object_id}` returns the named match; repeat
  unenrolled to confirm the visual-match fallback; confirm the overlay
  renders the badges live; and regenerate `docs/static/frigate-api.yaml`.

## Scalability: zone-filter query normalization (separate initiative)

**Not part of the numbered security-command-centre roadmap above** --
this is core Frigate data-layer work, prompted by "make the app scale to
plenty of cameras/zones and stay fast," not an alarm feature. **DONE**,
live-verified in the real `frigate` docker-compose container (not just
this sandbox), including a rebuild of the image.

- An initial audit (Explore agents) claimed `Event.start_time`,
  `ReviewSegment.start_time`, and `Recordings.start_time` were
  unindexed. Hand-verified against `migrations/*.py` and found all three
  already indexed (migrations 011, 020, 022) -- the agents only checked
  `models.py`'s inline `index=True` declarations and missed that most
  indexes in this codebase are added via separate raw-SQL migrations.
  No N+1 query patterns found either. The one real, confirmed,
  zone-count-scaling issue: zone filtering on `Event.zones` and
  `ReviewSegment.data["zones"]` did an unindexed `LIKE` scan over a JSON
  blob (`Event.zones.cast("text") % f'*"{zone}"*'`), architecturally
  unindexable as-is -- more zones directly meant a slower scan.
- Fix: new additive join tables `EventZone`/`ReviewSegmentZone`
  (`frigate/models.py`), a real index on `zone`, populated via
  `insert_many(...).on_conflict_ignore()` at every write site
  (`frigate/events/maintainer.py`, `frigate/comms/dispatcher.py`'s
  review-segment upsert handlers) and kept clean at every existing
  delete site (`frigate/events/cleanup.py`, `frigate/record/cleanup.py`,
  `frigate/api/review.py`, `frigate/util/camera_cleanup.py`) since this
  codebase does not enable SQLite's `foreign_keys` pragma, so `ON DELETE
  CASCADE` would be inert. `Event.zones`/`ReviewSegment.data["zones"]`
  are untouched -- still the display source, still what the join tables
  are populated from. `migrations/041_create_zone_join_tables.py` also
  backfills existing rows via SQLite's `json_each()` (verified working
  against this codebase's SQLite build before relying on it) and adds a
  `ReviewSegment.severity`+`start_time` compound index (every review-list
  query already sorts by that pair). Read paths
  (`frigate/api/event.py`, `frigate/api/review.py`) swapped from the LIKE
  scan to `Event.id.in_(EventZone.select(...).where(EventZone.zone <<
  filtered_zones))` and the review mirror, preserving OR-across-zones and
  "None" (zoneless) semantics.
- Learned from Part 1's mistake and avoided repeating it: `EventZone`/
  `ReviewSegmentZone` were added to `frigate/app.py`'s real `models = [...]`
  binding list proactively, in the same edit that added the classes to
  `models.py` -- not discovered missing later via a live 500.
- Tests: `frigate/test/test_zone_join_tables.py` (upsert-sync mechanics,
  the migration's exact backfill SQL against hand-built rows, cleanup
  orphan-check), plus new `TestEventZoneFilter`/`TestReviewZoneFilter`
  classes in the existing `test_http_event.py`/`test_http_review.py`.
  All pass in-container, plus a full `unittest discover` regression pass
  (1126 tests) showed zero new failures -- the only 4 failures found
  (`test_alarm_dispatcher_command.py`: `test_arm_home_command`,
  `test_arm_night_command`, `test_command_is_case_insensitive`) are
  pre-existing, deterministic, reproducible in isolation, and confirmed
  unrelated by diffing exactly what changed in `dispatcher.py` this
  session (only the zone-sync helper and its wiring into the two
  review-segment handlers) -- worth fixing separately, not folded into
  this initiative. The bug: `AlarmSystem`'s exit-delay timer only
  reliably completes for `away` in that test's synchronous assertion
  style, not `home`/`night`, in the still-uncommitted HA three-mode
  work.
- Rebuilt the image (`docker compose build frigate` + `up -d frigate`)
  and confirmed migration 037 runs cleanly against the real production
  DB on a real container restart (camera `dehothouse` configured, no
  historical event/review rows existed yet to exercise the backfill
  against, so the backfill's correctness rests on the unit tests running
  the exact migration SQL against hand-built rows instead).
- Live end-to-end verification against the real bound database (not
  in-memory): manually inserted rows through the exact same write path
  `maintainer.py`/`dispatcher.py` use, confirmed `EXPLAIN QUERY PLAN`
  shows `SEARCH eventzone USING INDEX eventzone_zone` (not a table
  scan), hit the real HTTP API through nginx (`GET /api/events?zones=`,
  `GET /api/review?zones=`) and confirmed correct OR-across-zones and
  "None" filtering, then deleted the rows through the same cleanup path
  and confirmed zero orphaned join-table rows. Cleaned up all test data
  afterward -- nothing left in the real database.
- **A pre-existing, unrelated bug found along the way, not fixed**:
  `frigate/api/review.py`'s `after = params.after or (now - 24h)` (and
  the equivalent for `before`) treats `after=0` as falsy and silently
  ignores it, falling back to the 24-hour-ago default instead of epoch
  0. Only surfaced because a live-verification test row happened to use
  an old timestamp; harmless for real usage (nobody passes `after=0` in
  practice) but worth a one-line `is None` fix if anyone hits it.

## TensorRT execution provider for x86_64 GPU inference (separate initiative)

**Not alarm-engine related** -- performance work on core GPU inference,
prompted by wanting the `-tensorrt` amd64 image to actually use TensorRT
instead of silently running plain CUDA. **Code changes done, NOT live-
verified** -- no NVIDIA GPU in this sandbox, same posture as the SIA DC-09
stub above: best-effort implementation, flagged unverified, needs a real
GPU build/boot before being trusted.

- Found that `frigate/util/model.py`'s `get_ort_providers()` already had a
  TensorRT-then-CUDA-fallback code path, but it was **dead on x86_64**: (1)
  it only activated on the literal, undocumented `device: Tensorrt` config
  value, and (2) `docker/tensorrt/requirements-amd64.txt` never installed
  the TensorRT runtime libs (`libnvinfer*`) ONNX Runtime needs to even
  detect `TensorrtExecutionProvider` as available, unlike
  `Dockerfile.arm64` which does for Jetson. So every existing x86_64
  `-tensorrt` GPU user was running plain CUDA-EP ONNX regardless of config.
- User confirmed (via AskUserQuestion): TensorRT should become the
  **automatic default** on that image, not a hidden opt-in, matching the
  "auto-detected" UX already given to CUDA/ROCm/OpenVINO.
- Changes: added `tensorrt-cu12-libs==10.9.*` to
  `docker/tensorrt/requirements-amd64.txt` (version is a best-available
  extrapolation from ONNX Runtime's published CUDA/TensorRT compatibility
  table, which doesn't list `onnxruntime-gpu==1.24` explicitly -- **must be
  confirmed against a real build**, adjust if `onnxruntime.get_available_providers()`
  shows a version-mismatch error). Removed the `device == "Tensorrt"` gate
  in `get_ort_providers()` (`frigate/util/model.py`) so
  `TensorrtExecutionProvider` is registered unconditionally whenever ONNX
  Runtime reports it available, exactly mirroring how `CUDAExecutionProvider`
  is already handled -- no new fallback logic needed, since ONNX Runtime's
  own per-node graph partitioning already falls back to whichever provider
  comes next in the list. Added `trt_max_workspace_size` (default 2048MB,
  overridable via `TRT_MAX_WORKSPACE_MB`), which resolves the stale
  in-code comment claiming TensorRT had "no options to control" its memory
  use -- that option existed in ONNX Runtime already, Frigate's code just
  never set it.
- `trt_fp16_enable` wiring was left untouched: the ONNX detector
  (`frigate/detectors/plugins/onnx.py`) never passes `requires_fp16=True`
  for detection models, so TensorRT runs at the same FP32 precision CUDA
  does today -- no accuracy tradeoff introduced by this change.
- `frigate/detectors/detection_runners.py`'s `get_optimized_runner()`
  needed no change: its `providers[0] == "CUDAExecutionProvider"` check
  (gating the CUDA-Graph-capture fast path) already correctly falls through
  to the generic `ONNXModelRunner` path when TensorRT is `providers[0]`
  instead, which is what should happen since CUDA Graph capture is CUDA-EP
  specific and wouldn't apply to TensorRT anyway.
- `frigate/detectors/plugins/tensorrt.py` (the dedicated Jetson `type:
  tensorrt` detector) was not touched -- separate, unrelated code path.
- Docs (`docs/docs/configuration/object_detectors.md`) updated to describe
  the new automatic TensorRT-then-CUDA behavior and its tradeoffs (larger
  image, slower first-boot engine compile, unchanged FP32 accuracy).
- Tests: new `frigate/test/test_util_model.py` (3 cases -- TRT registered
  automatically with CUDA fallback and a real `trt_max_workspace_size`,
  the `TRT_MAX_WORKSPACE_MB` env override, and the CUDA-only case when TRT
  isn't available). Like most of `frigate.util.model`'s dependents, this
  needs real `cv2`/`onnxruntime` (imported at module scope), neither
  installed in this sandbox -- confirmed via `ruff check`/`ruff format
  --check`/`mypy` only (all clean), **never actually run**.
- **Before trusting this**: rebuild the `-tensorrt` amd64 image on real
  GPU hardware and confirm `TensorrtExecutionProvider` loads without a
  version mismatch, the detector survives the slower first-boot engine
  compile (existing `_warmup()` in `onnx.py` should already cover this,
  unverified), inference speed actually improves over the prior CUDA-only
  baseline, and detection confidence scores are materially unchanged.
