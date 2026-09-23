# Fork Rebuild Reference — TensorRT, ParkPow, Alarm System

Reference for rebuilding the three LocknAlert-specific feature sets in this
Frigate fork onto a clean upstream checkout. Written to be read cold, with no
memory of the sessions that produced the code.

**Relationship to `AGENTS.md`**: `AGENTS.md` is the chronological session log —
why each decision was made, what was tried and rejected, which bugs were found
live. It is the authority on *intent* and *caveats*. This file is the structural
map: what exists, where it lives, how the pieces connect, and what order to
rebuild them in. When the two disagree, trust the code, then `AGENTS.md`.

**Fork base**: upstream commit `d37dff1b4` ("Docs update (#24131)"). Everything
described here is in the diff:

```bash
git diff d37dff1b4 HEAD --stat -- frigate/ migrations/ docker/ docs/ web/src/
```

### History note (2026-09-23)

All of this work was once wiped from `dev` by a `git reset --hard origin/dev`,
then restored on branch `restore/fork-features`. The restore was a real 3-way
merge of the recovered commit `8afc101fd` against the fork base — *not* a
re-type from this document. If the work is ever lost again, look for the real
commit first (`git reflog`, `git fsck --lost-found`) and merge it; rebuilding
by hand from prose is strictly worse. Upstream had moved on in the meantime,
and the reconciliations that needed are marked **upstream drift** below.

---

## 1. TensorRT — making the `-tensorrt` image actually use TensorRT

### The problem

On x86_64, the `-tensorrt` image was silently running plain CUDA, not TensorRT.
Two independent causes:

1. `docker/tensorrt/requirements-amd64.txt` never installed the TensorRT runtime
   libs (`libnvinfer*`), so ONNX Runtime could not even detect
   `TensorrtExecutionProvider` as available. (`Dockerfile.arm64` *did* install
   them for Jetson — which is why Jetson worked and amd64 didn't.)
2. `frigate/util/model.py::get_ort_providers()` only registered the TensorRT EP
   when the config had the literal, undocumented value `device: Tensorrt`;
   otherwise it hit a `continue` and skipped it entirely.

### The changes (2 files, plus docs + test)

| File | Change |
| --- | --- |
| `docker/tensorrt/requirements-amd64.txt` | `+ tensorrt-cu12-libs==10.9.*; platform_machine == 'x86_64'` |
| `frigate/util/model.py` | `get_ort_providers()`: removed the `device == "Tensorrt"` gate so TRT registers unconditionally when ORT reports it available; added `trt_max_workspace_size` (default 2048 MB, env `TRT_MAX_WORKSPACE_MB`); hardened `device_id` parse against empty string |
| `docs/docs/configuration/object_detectors.md` | Documents automatic TRT→CUDA behavior, first-boot engine compile, larger image |
| `frigate/test/test_util_model.py` | 3 cases: TRT auto-registered with CUDA fallback, env override, CUDA-only when TRT absent |

### Why no fallback logic was needed

ONNX Runtime partitions the graph per-node and falls back to the next provider in
the list. Registering `TensorrtExecutionProvider` immediately before
`CUDAExecutionProvider` is therefore a strict upgrade — anything TRT can't compile
runs on CUDA automatically. `frigate/detectors/detection_runners.py` also needed
no change: its `providers[0] == "CUDAExecutionProvider"` check (gating CUDA-Graph
capture) correctly falls through to the generic runner when TRT is first.

### Things deliberately left alone

- `trt_fp16_enable` — the ONNX detector never passes `requires_fp16=True` for
  detection models, so TRT runs FP32, same precision as CUDA. **No accuracy
  tradeoff was introduced.** Don't "fix" this without measuring.
- `frigate/detectors/plugins/tensorrt.py` — the dedicated Jetson `type: tensorrt`
  detector is a separate, unrelated code path.

### ⚠️ Verification status: NOT live-verified

Written without NVIDIA GPU access. The `tensorrt-cu12-libs==10.9.*` pin is an
extrapolation from ONNX Runtime's compatibility table, which does not list
`onnxruntime-gpu==1.24` explicitly. **Before trusting it:**

1. Build the amd64 `-tensorrt` image on real GPU hardware.
2. `python3 -c "import onnxruntime; print(onnxruntime.get_available_providers())"`
   inside the container — `TensorrtExecutionProvider` must be present with no
   version-mismatch error. If mismatched, adjust the pin to whatever TRT release
   `onnxruntime-gpu` was built against.
3. Confirm the detector survives the slower first-boot engine compile (engines are
   cached to `/config/model_cache/tensorrt/ort/trt-engines`).
4. Confirm inference speed improves over the CUDA-only baseline and detection
   confidence scores are materially unchanged.

### Build + push

There are two build paths, and they must produce the same amd64 image:

| Path | Use for | Entry point |
| --- | --- | --- |
| `docker buildx bake` | all three variants, incl. both Jetsons | `docker/tensorrt/trt.hcl` + `trt.mk` |
| plain `docker build` / `docker compose` | amd64 only, self-building | `docker/main/Dockerfile --target frigate-tensorrt` |

Bake exists because `docker/tensorrt/Dockerfile.amd64` takes `wheels`, `deps` and
`rootfs` in as **named build contexts**, which only bake can supply. Compose has
`additional_contexts` but no equivalent of bake's `target:` stage references, so
that file is unreachable from `docker compose build`. To keep compose
self-building, `docker/main/Dockerfile` repeats the same two stages
(`trt-wheels`, `frigate-tensorrt`) where those names are ordinary local stages.

**The two copies must stay identical** — otherwise the image differs depending on
which path built it. `frigate/test/test_tensorrt_dockerfile_parity.py` compares
the stage bodies (comments stripped) and fails on drift. It has no frigate
imports, so it runs on a bare host.

Adding those stages does not affect the default image: BuildKit only builds
stages the requested target depends on, so `--target frigate` never touches them.

#### Build on one machine, run on another (the usual workflow here)

`docker-compose.yml` carries both `image:` and `build:`, so compose builds the
TensorRT image and can push it straight to a registry. `FRIGATE_IMAGE` selects
the tag; `build.platforms` is pinned to `linux/amd64` so a build never inherits
the builder's architecture.

```bash
# on the build machine
export FRIGATE_IMAGE=docker.io/<user>/frigate:tensorrt
docker compose build
docker login
docker compose push

# on the Ubuntu server, same FRIGATE_IMAGE (a .env file beside the compose file
# is easiest), plus the NVIDIA Container Toolkit installed
docker compose pull
docker compose up -d
```

`docker compose build` ignores the `deploy.resources` GPU reservation, so the
build machine does not need an NVIDIA GPU or the container toolkit — only the
host that actually runs the image does.

#### Bake path (all three variants)

TensorRT is enabled identically on **all three** variants — `get_ort_providers()`
has no architecture gating, so registering the EP applies to amd64, JP5 and JP6
alike. What differs is only where the TRT runtime comes from: the
`tensorrt-cu12-libs` wheel on amd64, and the NVIDIA L4T / TensorRT base image on
the two Jetson variants (which is why Jetson worked before the amd64 fix).

```bash
docker login -u <dockerhub-username>
docker buildx create --use          # needs the docker-container driver to push
make version                        # writes frigate/version.py + web/.env

# all three variants (amd64 dGPU + Jetson JP5 + JP6), tagged <TRT_TAG>-tensorrt,
# -tensorrt-jp5 and -tensorrt-jp6:
make push-trt IMAGE_REPO=docker.io/<user>/frigate TRT_TAG=0.19.0

# x86 dGPU only:
ARCH=amd64 docker buildx bake --file=docker/tensorrt/trt.hcl tensorrt \
  --set tensorrt.tags=docker.io/<user>/frigate:latest-tensorrt \
  --push
```

`TRT_TAG` defaults to the CI scheme `<branch>-<commit>`; override it for a
friendlier Docker Hub tag.

**`COMPUTE_LEVEL` does nothing for the amd64 build.** It is only read by
`docker/tensorrt/detector/tensorrt_libyolo.sh` (the `tensorrt_demos` YOLO
plugins), and only `Dockerfile.arm64` declares the ARG — `Dockerfile.amd64` never
references it. The ONNX Runtime TensorRT EP compiles engines at runtime for
whichever GPU is present, so there is no compute-capability list to narrow and no
x86 build time to save by trying. (An earlier revision of this file claimed
otherwise; that was wrong.)

Jetson (arm64) variants built from an amd64 host need QEMU:
`docker run --privileged --rm tonistiigi/binfmt --install all`.

Local build without pushing: `make local-trt` (or `local-trt-jp5` / `local-trt-jp6`)
→ tags `frigate:latest-tensorrt`. `docker compose build` with no `FRIGATE_IMAGE`
set produces that same tag, so the two local paths are interchangeable.

### Unrelated build fix that rode along

`docker/main/Dockerfile` gained an `APT_NETWORK_TUNING` ARG applied to the `base`,
`base_host`, and `slim-base` stages: forces apt to IPv4 with retries/timeouts,
because some networks have flaky IPv6 routes to `deb.debian.org` that manifest as
slow connect timeouts failing the whole build. Keep it — it is not TensorRT-specific
but it is why builds stopped failing intermittently.

### FFmpeg NVIDIA hardware decoding — already upstream, do not reimplement

TensorRT accelerates *inference*. Video *decoding* is a separate, unrelated path,
and it already works upstream with no fork changes. This is written down because
the question keeps coming up.

`hwaccel_args: preset-nvidia` expands to `-hwaccel cuda -hwaccel_output_format
cuda` (`frigate/ffmpeg_presets.py`), which is codec-agnostic: FFmpeg selects the
matching NVDEC decoder from the bitstream, covering H.264, H.265/HEVC and MJPEG
in one setting. The supporting pieces are all present:

- `NVIDIA_VISIBLE_DEVICES` / `NVIDIA_DRIVER_CAPABILITIES="compute,video,utility"`
  are set in the `deps` stage of `docker/main/Dockerfile`, which both `frigate`
  and `frigate-tensorrt` build `FROM`, so the `video` capability NVDEC needs is
  in the TensorRT image too.
- The bundled FFmpeg builds have NVDEC compiled in and dlopen the driver at
  runtime.
- `FAMILY_NVIDIA` in `frigate/util/hwaccel.py` is registered with `ANY_CODEC`, so
  the hwaccel recommender never drops it for a codec.
- `auto_detect_hwaccel()` (`frigate/util/services.py`) probes go2rtc's
  `/api/ffmpeg/hardware` and returns `preset-nvidia` on its own when CUDA is up.

**H.264+ / H.265+ need nothing extra.** They are Hikvision/Dahua encoder-side
optimizations, not codecs — longer dynamic GOPs, long-term reference frames,
per-region bitrate shaping — and the output is still a standards-compliant
H.264/HEVC bitstream. No "H.265+ decoder" exists in FFmpeg or in any GPU, and
`ffprobe` reports these streams as plain `h264` / `hevc`. Their one real
side effect is wider keyframe spacing, which slows first-frame latency and
coarsens recording segment cuts; the fix is a fixed I-frame interval in the
camera's own UI, not a Frigate setting.

Do **not** add `h264_cuvid` / `hevc_cuvid` presets as a "better" path. NVIDIA's
own guidance is to prefer the `-hwaccel cuda`/`nvdec` route and to use the
`_cuvid` decoders only for a specific reason, so such presets would be a
downgrade dressed up as a feature.

---

## 2. ParkPow integration (LPR → ParkPow visits)

Sends each recognized license plate to [ParkPow](https://app.parkpow.com/documentation/),
a hosted/self-hosted ALPR visit-management dashboard (same company as Plate
Recognizer). Frigate keeps doing its own on-device OCR; this only forwards results.

### Wire contract

```
POST {host}/api/v1/webhook-receiver/
Authorization: Token <token>
multipart/form-data:
  json   = {"data": {"results": [{"plate": "...", "score": 0.95}],
                     "camera_id": "<frigate camera name>",
                     "timestamp": "<ISO-8601 UTC>"}}
  upload = <snapshot.jpg>            # optional image part
```

Same contract Plate Recognizer Stream uses. Token comes from
`https://app.parkpow.com/account/token/` (or the equivalent path on a self-hosted
instance).

### Files

| File | Role |
| --- | --- |
| `frigate/data_processing/common/license_plate/parkpow.py` | **New.** `send_to_parkpow()` (gate + dispatch) and `_post_to_parkpow()` (the actual request). Fire-and-forget via a daemon `threading.Thread`, log-and-drop on failure — modeled on `frigate/alarm/notify_whatsapp.py`. |
| `frigate/config/classification.py` | `ParkPowConfig` (`enabled`, `host`, `token`, `timeout`) under `lpr.parkpow`; `parkpow_enabled: bool \| None` on `CameraLicensePlateRecognitionConfig` |
| `frigate/embeddings/maintainer.py` | The hook — see below |
| `docs/docs/configuration/license_plate_recognition.md` | "ParkPow integration" section |
| `frigate/test/test_parkpow.py` | Payload construction, host-slash normalization, non-2xx + exception handling, enabled/token gating |
| `frigate/test/test_config.py` | `test_default_lpr_parkpow`, `test_lpr_parkpow_camera_override` |

### The hook point (this is the important design decision)

Fires **once per finished vehicle event**, in
`EmbeddingMaintainer._process_finalized()` (`frigate/embeddings/maintainer.py`),
inside the existing `if updated_db:` block right after
`thumbnail = get_event_thumbnail_bytes(event)`.

Why not in the LPR pipeline itself: `lpr_process()` in
`frigate/data_processing/common/license_plate/mixin.py` runs many times per
vehicle while it's tracked/stationary. Hooking there would spam ParkPow with
duplicate "visits". `_process_finalized()` runs exactly once, when the event ends,
and by that point the DB row already carries the final
`event.data["recognized_license_plate"]` / `["recognized_license_plate_score"]`
(written in `frigate/events/maintainer.py`). The thumbnail is already being
fetched there for embeddings, so no extra I/O is introduced for the common path.

Enablement resolution, read fresh from `self.config` each call so runtime config
reloads are picked up with no `update_config` plumbing:

```python
camera_override = self.config.cameras[camera].lpr.parkpow_enabled
parkpow_enabled = (parkpow_config.enabled if camera_override is None
                   else camera_override)
```

Image: full-resolution snapshot via `get_event_snapshot(event)`
(`frigate/util/file.py`), JPEG-encoded; falls back to the already-fetched
thumbnail bytes when no snapshot exists.

### Config

```yaml
lpr:
  parkpow:
    enabled: True
    host: https://app.parkpow.com   # or your on-prem host
    token: <api token>
    timeout: 10

cameras:
  driveway:
    lpr:
      parkpow_enabled: True         # overrides the global flag; unset = inherit
```

### Deliberately out of scope

No retry queue, no dedup beyond once-per-event, no ParkPow `box` coordinates in
the payload (snapshot geometry doesn't map cleanly to their expected pixel box
without extra plumbing; `plate` + `score` + image is enough for ParkPow to create
the visit and run its own enrichment).

### ⚠️ Known debt

**`web/public/locales/en/config/{global,cameras}.json` were hand-edited** for
the ParkPow fields. `AGENTS.md` says never to do that — they are generated from
the Pydantic field `title`/`description` by `python3 generate_config_translations.py`.
That script cannot run on native Windows (`frigate/util/services.py` imports the
POSIX-only `resource` module), so this is still outstanding. Re-run it in the
container and confirm the diff is empty or sensible.

`frigate/test/test_parkpow.py` **has now been run** — all 8 cases pass against
the real `ParkPowConfig` and `parkpow.py`. On Windows it needs the package
`__init__` chain bypassed (`frigate/config/__init__.py` transitively pulls
`psutil`/`py3nvml`/`resource`, none of which `parkpow.py` itself uses); in the
container just run it normally. Still never fired against a live ParkPow
instance.

### Upstream drift already reconciled

`_process_finalized()` gained a removed-camera guard upstream that runs *after*
the ParkPow hook, so the hook now resolves the camera with
`self.config.cameras.get(camera)` and skips when it is gone. Don't switch that
back to `[camera]`.

---

## 3. Alarm system (backend)

A full intrusion-alarm engine layered on Frigate's existing detection stream.
`AGENTS.md` §"Alarm Engine Project" documents its 12-phase build and every design
argument; this is the structural summary.

### Core principle: no MQTT dependency

`AlarmSystem` and everything under it have zero MQTT/Dispatcher knowledge —
enforced by `frigate/test/test_alarm_no_mqtt_dependency.py`. The MQTT bridge is
the *only* piece that publishes, and it takes a plain callable. Detections arrive
over `EventUpdateSubscriber` (the internal ZMQ bus every other subsystem uses),
not MQTT. **Preserve this boundary when rebuilding.**

### Layers

```
config (frigate/config/alarm.py, frigate/config/camera/alarm.py)
  └─ factory.py            builds everything from a validated FrigateConfig
       └─ AlarmSystem (system.py)          orchestrator; owns delay timers,
            ├─ AlarmStateMachine (engine.py)   states + transitions only
            ├─ DetectionAlarmAdapter (adapter.py)  detection → AlarmEvent | None
            ├─ ReportingQueue ×2 (queue.py)    central-station + WhatsApp
            └─ on_change / on_event callbacks  ← the only outward coupling
```

`AlarmDetectionThread` (`detection_thread.py`) feeds it; `AlarmMqttBridge`
(`mqtt_bridge.py`) publishes from it; `frigate/api/alarm.py` and
`frigate/comms/dispatcher.py` mutate it.

### State machine (`state.py`, `engine.py`)

States: `disarmed → arming → exit_delay → armed_{away,home,night} → entry_delay →
alarm → alarm_memory`, plus `fault` (enterable from anywhere, returns to the prior
state). `ALLOWED_TRANSITIONS` in `state.py` is the authority; illegal moves raise
`InvalidAlarmTransition`.

`ArmedMode` is `away` / `home` / `night` — named to match Home Assistant's
`alarm_control_panel` 1:1 so the MQTT bridge needs no translation table. The UI
labels `night` as "Sleep".

**The state machine deliberately does not time its own delay states.**
`AlarmSystem` owns the `threading.Timer`s for exit/entry delay. A bug where the
delay never completed (no timer ever called it) was fixed in `58759df8f` — don't
reintroduce it by moving timers back into the engine.

### Per-arm-cycle zone bypass

`AlarmSystem._bypassed_zones` + `bypass_zone()`/`unbypass_zone()`/`is_bypassed()`.
Auto-clears **conditionally**: only when `disarm()` actually lands on `disarmed`.
Disarm during an active alarm silences into `alarm_memory`, and bypass must survive
that until a genuine stand-down (`disarm()` again, or `clear()`). Matches real panel
convention. `AlarmDetectionThread._evaluate()` skips bypassed zones *before* the
adapter sees them — the adapter stays unaware bypass exists.

### Config

```yaml
alarm:
  enabled: True
  exit_delay_seconds: 30
  reporting:                # sia_dc09 | contact_id | none
    protocol: contact_id
    host: 1.2.3.4
    port: 9000
    account: "1234"
    max_attempts: 5
    retry_delay_seconds: 5
  schedule:
    enabled: True
    entries:
      - time: "22:00"       # HH:MM 24h
        mode: night         # omit mode to disarm instead
        days: [0,1,2,3,4]   # 0=Mon..6=Sun; empty = every day
  whatsapp:
    enabled: True
    api_base_url: https://your-openwa-host/api
    session_id: session1
    api_key: <key>
    to_numbers: ["+27..."]
    cooldown_seconds: 300

cameras:
  driveway:
    alarm:
      enabled: True
      zones:
        front_gate:         # must match a Frigate zone name on this camera
          objects: [person]
          event: burglary
          min_confidence: 0.7
          verification_seconds: 2
          delay: 30         # entry delay
          arm_modes: [away, home, night]
          ai_verification: False
```

Validators enforce coherence: reporting requires host+port+account when protocol
≠ none; WhatsApp requires base URL + session + key + at least one number when
enabled.

### Module map (`frigate/alarm/`)

| File | Role |
| --- | --- |
| `state.py` | `AlarmState`, `ArmedMode`, `ALLOWED_TRANSITIONS`, `InvalidAlarmTransition` |
| `engine.py` | `AlarmStateMachine` — transitions only, no timers, no I/O |
| `system.py` | `AlarmSystem` orchestrator: timers, bypass, event history, `status()`, `on_change`/`on_event` |
| `rules.py` | `ZoneAlarmRule` plain dataclass (the config→core boundary) |
| `adapter.py` | `DetectionAlarmAdapter.evaluate()` — confidence/persistence/arm-mode gates → `AlarmEvent \| None` |
| `event.py` | `AlarmEvent`, `AlarmEventType` (canonical event vocabulary) |
| `detection_thread.py` | Subscribes `EventUpdateSubscriber`, evaluates, triggers, records. Crops the AI-verification thumbnail synchronously. |
| `factory.py` | Config → `AlarmSystem` / reporting queue / AI verifier / WhatsApp queue |
| `queue.py` | `ReportingQueue` — retrying background delivery + `healthy` flag |
| `protocols/sia.py` | SIA DC-09 encoder/client. ⚠️ **Unverified stub** — no spec was available. |
| `protocols/contact_id.py` | Contact ID encoder/client. Event codes verified against a real reference. |
| `mqtt_bridge.py` | `publish_status()` / `publish_event()` via a plain callable |
| `ha_discovery.py` | Home Assistant MQTT discovery for `alarm_control_panel` |
| `scheduler.py` / `schedule.py` | Auto arm/disarm thread + `ScheduleEntry` dataclass |
| `ai_verification.py` | `AlarmAiVerifier` — background GenAI confirm. **Fails open by design.** |
| `audit.py` | `record_alarm_audit()` — operator actions (successful ones only) |
| `event_log.py` | `record_alarm_event_log()` — historical alarm events |
| `trail.py` | Cross-camera person trail |
| `notify_whatsapp.py` | `AlarmWhatsAppNotifier` via self-hosted OpenWA, per camera/zone cooldown |

### Database

| Migration | Adds |
| --- | --- |
| `040_create_alarm_audit_log_table.py` | `AlarmAuditLog` |
| `041_create_zone_join_tables.py` | `EventZone`, `ReviewSegmentZone` (zone-filter query normalization — separate initiative, see `AGENTS.md`) |
| `042_create_alarm_event_log_table.py` | `AlarmEventLog` |
| `043_add_object_id_to_alarm_event_log.py` | `object_id` column (for the trail feature) |

**Upstream drift**: these were originally `036`–`039`. Upstream has since taken
`036`–`039` for recordings stream metadata/index, notices and perf indexes, so
they were renumbered to `040`–`043`. If you rebuild onto a newer upstream,
check the highest existing migration number first — peewee_migrate orders by
filename, so a duplicate prefix makes the order ambiguous.

Models live in `frigate/models.py`; all four must also be registered in the
`models = [...]` list in `frigate/app.py`.

**Peewee timestamp gotcha (cost real debugging time):** `datetime.now(UTC)` stores
a `+00:00` suffix that peewee's `DateTimeField` cannot parse back, silently
returning `str` instead of `datetime`. Store naive UTC, then
`.replace(tzinfo=UTC)` on read before converting to epoch.

### Wiring in `frigate/app.py`

- `init_alarm_system()` — builds the system, AI verifier, and MQTT bridge; assigns
  `alarm_system.on_change = bridge.publish_status` and an `on_event` closure that
  does `bridge.publish_event(event)` + `record_alarm_event_log(event)`; sets
  `dispatcher.alarm_system` so inbound MQTT `alarm/set` commands route through.
- `start_alarm_system()` — starts reporting/WhatsApp queues, `AlarmDetectionThread`,
  and (only if entries exist) `AlarmScheduler`.
- HA discovery is published from `MqttClient`'s **on-connect** callback
  (`frigate/comms/mqtt.py`), *not* synchronously at init — doing it at init races
  the async connect and the publish is silently dropped.

WhatsApp enqueueing lives inside `AlarmSystem.record_event()`, not in the app
closure, so every mutation path gets it.

### HTTP API (`frigate/api/alarm.py`, all admin-gated for mutations)

```
GET  /alarm/status                               state, armed_mode, faults, queue health, per-zone status
GET  /alarm/events                               recent in-memory events
GET  /alarm/audit                                operator action log
GET  /alarm/event_log                            persisted alarm events
GET  /alarm/event_log/summary
GET  /alarm/trail/{object_id}                    cross-camera person trail
POST /alarm/event_log/{event_id}/false_alarm
POST /alarm/arm                                  {mode, exit_delay_seconds?}
POST /alarm/disarm
POST /alarm/clear
POST /alarm/zones/{camera}/{zone}/bypass         {bypassed: bool}; 404 for unknown zone
```

After touching any endpoint, regenerate the OpenAPI spec —
`docs/static/frigate-api.yaml` is generated by `generate_api_auth_spec.py`, CI
runs the `--check` variant, and it must **never** be hand-edited.

### MQTT / WebSocket topics

Registered in `frigate/comms/ws.py`'s outbound classifier:

| Topic | Scope |
| --- | --- |
| `alarm/state` | global |
| `alarm/fault` | global |
| `alarm/event` | per-camera (keyed on payload field `camera_id`) |
| `<camera>/alarm_zone/<zone>/state` | per-zone status incl. `armed` / `bypassed` |

Inbound `alarm/set` commands are routed by `frigate/comms/dispatcher.py`'s
`_on_alarm_command` (also writes the audit record, `actor=None` for MQTT-driven
actions vs. the `remote-user` header for HTTP).

**Upstream drift**: `MqttClient` used to need an explicit
`message_callback_add(".../alarm/set", ...)`. It no longer does — upstream
replaced per-topic registration with a wildcard `{prefix}/#` subscribe filtered
by `_is_supported_command_topic()`, which delegates to
`Dispatcher.is_command_topic()`. That already returns True for `alarm/set`
because `"alarm"` is in `_global_settings_handlers`. Re-adding the explicit
callback is harmless but redundant; what is load-bearing is keeping `"alarm"`
in `_global_settings_handlers`.

Push notifications ride along automatically: `WebPushClient`
(`frigate/comms/webpush.py`) subscribes to the `alarm/event` dispatcher topic —
no extra wiring needed at the call site.

### AI verification (opt-in per zone)

Uses Frigate's **existing** GenAI abstraction, not a new integration:
`GenAIClient.generate_alarm_verification()` (`frigate/genai/__init__.py`) with
`build_alarm_verification_prompt()` / structured-output `_response_format()`
(`frigate/genai/prompts.py`). `AlarmAiVerifier` runs each call on a background
thread (network-bound work must never touch a hot path).

**Fails open, deliberately**: no provider configured, a request exception, or an
unparseable response all resolve to `confirmed=True`. An optional AI layer must
never become a silent single point of failure that disables the alarm — it can
suppress false positives, never mask a real intrusion. Do not "harden" this into
fail-closed without an explicit product decision.

The live thumbnail comes from the `frame_name` in the ZMQ tuple →
`SharedMemoryFrameManager.get(frame_name, camera_config.frame_shape_yuv)` →
`create_thumbnail(yuv_frame, box)` (`frigate/util/image.py`). It **must** be
cropped synchronously — the shared-memory frame is only valid for that update's
lifetime.

### Tests (`frigate/test/`)

`test_alarm_{state_machine,system,adapter,detection_thread,queue,sia,contact_id,
mqtt_bridge,ha_discovery,scheduler,audit,event_log,trail,ai_verification,config,
dispatcher_command,no_mqtt_dependency,notify_whatsapp}.py` plus
`http_api/test_http_alarm.py` (~190 tests).

Two tiers, and it matters: some import cleanly without cv2/pyzmq (bare host),
others need the real container. `test_alarm_detection_thread.py` moved into the
container-only tier when AI verification added `FrigateConfig` + `frigate.util.image`
imports — noted in its docstring. `test_alarm_dispatcher_command.py` has 4
pre-existing known failures.

---

## 4. Alarm UI — management + camera auto-surface popup

### The popup (what the user calls "camera that has an object detected shown")

`web/src/components/alarm/AlarmAlertOverlay.tsx` — **frontend only, needed zero
backend changes.**

- Mounted once in `App.tsx`'s `DefaultAppView`, gated on `config.alarm.enabled`,
  so it is global and route-independent. **Upstream drift**: chrome components
  there are now wrapped in `<ChromeErrorBoundary>`; the overlay is mounted
  inside one too, so a render error in it can't take the whole app down.
- Watches `useAlarmEvents()` / `useAlarmState()` in `web/src/api/ws.ts` (added
  mirroring the existing `useFrigateEvents()` pattern).
- Pops a fixed bottom-right card with the **triggering camera's live feed** —
  reuses `LivePlayer` + `useCameraLiveMode`, the same hooks the grid dashboard
  uses — plus zone / object / confidence context.
- Surfaces as early as `alarm/event` fires (i.e. during entry delay, not only on
  full `alarm` state — the whole point is seeing the camera *before* the alarm
  finishes triggering), escalates visually when `is_alarm_active`.
- **No auto-timeout.** Clears only on manual dismiss or the alarm actually
  clearing/disarming — matching how a real panel behaves.

### Quick control widget

`web/src/components/menu/AlarmControl.tsx` — arm/disarm/clear + per-zone bypass
reachable from every page. Modeled on `AccountSettings.tsx`'s polymorphic
`Container`/`Trigger`/`Content` pattern (`DropdownMenu` on desktop, `Drawer` on
mobile via `isDesktop`). Mounted in **both** `Sidebar.tsx` (desktop) and
`Bottombar.tsx` (mobile) — that pair is the complete mount set.

Deliberately does **not** wrap its controls in `DropdownMenuItem`/`DrawerClose`
(unlike `GeneralSettings.tsx`'s nav-item precedent): those auto-close on click,
which is wrong for a bypass `Switch` you may flip several times in a row.

### Settings page registration

**Upstream drift**: the Settings section index moved out of `pages/Settings.tsx`
into `web/src/types/settings.ts` (`settingsViewGroups`, from which `SettingsType`
is derived). The alarm group is registered there as
`{ label: "alarm", views: ["alarmStatus", "globalAlarm", "cameraAlarm"] }`, and
`pages/Settings.tsx` maps those three keys to components in `SECTION_VIEWS`.
Adding a view to only one of the two places will not compile.

### Full UI surface

| File | Role |
| --- | --- |
| `components/alarm/AlarmAlertOverlay.tsx` | The auto-surface camera popup |
| `components/menu/AlarmControl.tsx` | Global quick arm/disarm/bypass widget |
| `views/settings/AlarmView.tsx` | Main panel: status, zone list + bypass switches, recent events, audit log |
| `views/settings/AlarmZoneSetup.tsx` | Per-camera zone rule editor |
| `views/settings/AlarmScheduleSetup.tsx` | Schedule entry editor |
| `views/settings/AlarmHealthDashboard.tsx` | Reporting/queue health |
| `hooks/use-alarm-actions.ts` | arm/disarm/clear/`setZoneBypass` mutations |
| `hooks/use-alarm-event-log.ts`, `hooks/use-alarm-trail.ts` | History + trail fetching |
| `types/alarm.ts` | Shared response types |
| `utils/alarmUtil.ts` | `ALARM_STATE_BADGE_CLASSES` — shared so `AlarmView` and `AlarmControl` can't drift |
| `api/ws.ts` | `useAlarmEvents()`, `useAlarmState()` |
| `types/settings.ts` | The `alarm` settings group (`alarmStatus`, `globalAlarm`, `cameraAlarm`) |
| `public/locales/en/views/alarm.json` | i18n keys |

All mutation paths key off the same `"alarm/status"` SWR cache, so mutating from
the quick widget refreshes the settings view and vice versa with no extra wiring.

---

## Rebuild order

1. **TensorRT** — independent of everything else; 2 files. Do it first, it's the
   cheapest to verify (build + `get_available_providers()`).
2. **Alarm backend core** — `state.py` → `engine.py` → `rules.py` → `adapter.py` →
   `system.py` → `factory.py`, with tests at each step. These are pure and
   testable on a bare host.
3. **Alarm persistence** — models + migrations 040–043, registered in `app.py`.
4. **Alarm integration** — `detection_thread.py`, `mqtt_bridge.py`,
   `ha_discovery.py`, `scheduler.py`, dispatcher/webpush/ws wiring, `app.py`
   `init_alarm_system()`/`start_alarm_system()`.
5. **Alarm API** — `frigate/api/alarm.py`, then regenerate `frigate-api.yaml`.
6. **Alarm UI** — ws hooks → `AlarmView` → `AlarmControl` → `AlarmAlertOverlay`.
7. **ParkPow** — fully independent; config → client module → `maintainer.py` hook.

## Commands

```bash
# Backend tests (in container — cannot run on native Windows)
python3 -m pytest frigate/test/ -k alarm
python3 -m pytest frigate/test/test_parkpow.py frigate/test/test_util_model.py
python3 -m ruff check frigate && python3 -m mypy --config-file frigate/mypy.ini frigate

# Regenerate — NEVER hand-edit the outputs of these
python3 generate_config_translations.py     # web/public/locales/en/config/*.json
python3 generate_api_auth_spec.py           # docs/static/frigate-api.yaml (--check in CI)

# Frontend (from web/)
npx tsc --noEmit && npx eslint . && npx i18next-cli extract --ci && npx vite build
```

## Open risks

| Item | Status |
| --- | --- |
| TensorRT `tensorrt-cu12-libs` version pin | Never run on real GPU hardware — verify before trusting |
| SIA DC-09 protocol (`protocols/sia.py`) | Best-effort, no spec available — flagged unverified. Contact ID *is* verified. |
| ParkPow end-to-end | Unit tests now pass (8/8); no live POST confirmed against a real ParkPow instance |
| ParkPow locale JSON | Hand-edited; still needs `generate_config_translations.py` re-run in the container |
| `docs/static/frigate-api.yaml` | Carried through the restore merge; not regenerated since (`generate_api_auth_spec.py` needs the container). Run the `--check` variant before pushing. |
| `test_alarm_queue.py::test_stop_joins_the_thread` | Flaky, ~1 run in 5. `ReportingQueue.stop()` joins with `retry_delay_seconds + 1`s while `_run` blocks on `queue.get(timeout=1.0)`; with `retry_delay_seconds=0` those are equal, so the join can time out with the thread still alive. Pre-existing, in the engine not just the test. |
| `test_alarm_dispatcher_command.py` | 4 pre-existing failures, unrelated to recent work |
| Alarm UI visual QA | Never opened in a browser, and **not type-checked since the restore** — no Node toolchain on the Windows host. Run `npx tsc --noEmit` in `web/`. |
