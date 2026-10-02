---
id: license_plate_recognition
title: License Plate Recognition (LPR)
---

import ConfigTabs from "@site/src/components/ConfigTabs";
import TabItem from "@theme/TabItem";
import NavPath from "@site/src/components/NavPath";
import FaqItem from "@site/src/components/FaqItem";

Kestrel can recognize license plates on vehicles and automatically add the detected characters to the `recognized_license_plate` field or a [known](#matching) name as a `sub_label` to tracked objects of type `car`, `motorcycle`, `bus`, `truck`, `school_bus`, or `garbage_truck`, depending on which of those labels your model detects. A common use case may be to read the license plates of cars pulling into a driveway or cars passing by on a street.

LPR works best when the license plate is clearly visible to the camera. For moving vehicles, Kestrel continuously refines the recognition process, keeping the most confident result. When a vehicle becomes stationary, LPR continues to run for a short time after to attempt recognition.

:::info

License plate recognition requires a one-time internet connection to download OCR and detection models from GitHub. Once cached, models work fully offline. See [Network Requirements](/frigate/network_requirements#one-time-model-downloads) for details.

:::

When a plate is recognized, the details are:

- Added as a `sub_label` (if [known](#matching)) or the `recognized_license_plate` field (if unknown) to a tracked object.
- Viewable in the Details pane in Review/History.
- Viewable in the Tracked Object Details pane in Explore (sub labels and recognized license plates).
- Filterable through the More Filters menu in Explore.
- Published via the `frigate/events` MQTT topic as a `sub_label` ([known](#matching)) or `recognized_license_plate` (unknown) for the vehicle tracked object.
- Published via the `frigate/tracked_object_update` MQTT topic with `name` (if [known](#matching)) and `plate`.

## Model Requirements

Users running a Frigate+ model (or any custom model that natively detects license plates) should ensure that `license_plate` is added to the [list of objects to track](https://docs.frigate.video/plus/#available-label-types) either globally or for a specific camera. This will improve the accuracy and performance of the LPR model.

Users without a model that detects license plates can still run LPR. Kestrel uses a lightweight YOLOv9 license plate detection model that can be configured to run on your CPU or GPU. In this case, you should _not_ define `license_plate` in your list of objects to track.

:::note

In the default mode, Kestrel's LPR needs to first detect a vehicle before it can recognize a license plate. If you're using a dedicated LPR camera and have a zoomed-in view where a vehicle will not be detected, you can still run LPR, but the configuration parameters will differ from the default mode. See the [Dedicated LPR Cameras](#dedicated-lpr-cameras) section below.

:::

## Minimum System Requirements

License plate recognition works by running AI models locally on your system. The YOLOv9 plate detector model and the OCR models ([PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)) are relatively lightweight and can run on your CPU or GPU, depending on your configuration. At least 4GB of RAM and a CPU with AVX + AVX2 instructions is required.

## Configuration

License plate recognition is disabled by default and must be enabled before it can be used.

<ConfigTabs>
<TabItem value="ui">

Navigate to <NavPath path="Settings > Enrichments > License plate recognition" />.

- Set **Enable LPR** to on

</TabItem>
<TabItem value="yaml">

```yaml
lpr:
  enabled: True
```

</TabItem>
</ConfigTabs>

Like other enrichments in Kestrel, LPR **must be enabled globally** to use the feature. Disable it for specific cameras at the camera level if you don't want to run LPR on cars on those cameras.

<ConfigTabs>
<TabItem value="ui">

Navigate to <NavPath path="Settings > Camera configuration > License plate recognition" /> for the desired camera and disable the **Enable LPR** toggle.

</TabItem>
<TabItem value="yaml">

```yaml {4,5}
cameras:
  garage:
    ...
    lpr:
      enabled: False
```

</TabItem>
</ConfigTabs>

For non-dedicated LPR cameras, ensure that your camera is configured to detect vehicle objects, and that a vehicle is actually being detected by Kestrel. Otherwise, LPR will not run. The object types that can carry a plate are defined by your model's `attributes_map`, so if your model detects other vehicle labels, you can add them there.

Like the other real-time processors in Kestrel, license plate recognition runs on the camera stream defined by the `detect` role in your config. To ensure optimal performance, select a suitable resolution for this stream in your camera's firmware that fits your specific scene and requirements.

## Advanced Configuration

Fine-tune the LPR feature using these optional parameters. The only optional parameters that can be set at the camera level are `enabled`, `min_area`, and `enhancement`.

### Detection

<ConfigTabs>
<TabItem value="ui">

Navigate to <NavPath path="Settings > Enrichments > License plate recognition" />.

- **Detection threshold**: License plate object detection confidence score required before recognition runs. This field only applies to the standalone license plate detection model; `threshold` and `min_score` object filters should be used for models like Frigate+ that have license plate detection built in.
  - Default: `0.7`
- **Minimum plate area**: Minimum area (in pixels) a license plate must be before recognition runs. This is an _area_ measurement (length x width). For reference, 1000 pixels represents a ~32x32 pixel square in your camera image. Depending on the resolution of your camera's `detect` stream, you can increase this value to ignore small or distant plates.
  - Default: `1000` pixels
- **Device**: Device to use to run license plate detection _and_ recognition models. Auto-selected by Kestrel and can be `CPU`, `GPU`, or the GPU's device number. For users without a model that detects license plates natively, using a GPU may increase performance of the YOLOv9 license plate detector model. See the [Hardware Accelerated Enrichments](/configuration/hardware_acceleration_enrichments.md) documentation.
  - Default: `None`
- **Model size**: The size of the model used to identify regions of text on plates. The `small` model is fast and identifies groups of Latin and Chinese characters. The `large` model identifies Latin characters only, and uses an enhanced text detector to find characters on multi-line plates. If your country or region does not use multi-line plates, you should use the `small` model.
  - Default: `small`

</TabItem>
<TabItem value="yaml">

```yaml
lpr:
  enabled: True
  detection_threshold: 0.7
  min_area: 1000
  device: CPU
  model_size: small
```

</TabItem>
</ConfigTabs>

### Recognition

<ConfigTabs>
<TabItem value="ui">

Navigate to <NavPath path="Settings > Enrichments > License plate recognition" />.

- **Recognition threshold**: Recognition confidence score required to add the plate to the object as a `recognized_license_plate` and/or `sub_label`.
  - Default: `0.9`
- **Min plate length**: Minimum number of characters a detected license plate must have to be added as a `recognized_license_plate` and/or `sub_label`. Use this to filter out short, incomplete, or incorrect detections.
- **Plate format regex**: A regular expression defining the expected format of detected plates. Plates that do not match this format will be discarded. Kestrel refuses to start if the pattern is not a valid regex, rather than logging per plate and letting every read through. Websites like https://regex101.com/ can help test regular expressions for your plates.

</TabItem>
<TabItem value="yaml">

```yaml
lpr:
  enabled: True
  recognition_threshold: 0.9
  min_plate_length: 4
  format: "^[A-Z]{2}[0-9]{2} [A-Z]{3}$"
```

</TabItem>
</ConfigTabs>

### Matching

<ConfigTabs>
<TabItem value="ui">

Navigate to <NavPath path="Settings > Enrichments > License plate recognition" />.

- **Known plates**: Assign custom `sub_label` values to vehicle objects when a recognized plate matches a known value. These labels appear in the UI, filters, and notifications. Unknown plates are still saved but are added to the `recognized_license_plate` field rather than the `sub_label`.
- **Match distance**: Allows for minor variations (missing/incorrect characters) when matching a detected plate to a known plate. For example, setting to `1` allows a plate `ABCDE` to match `ABCBE` or `ABCD`. This parameter will _not_ operate on known plates that are defined as regular expressions.

</TabItem>
<TabItem value="yaml">

```yaml
lpr:
  enabled: True
  match_distance: 1
  known_plates:
    Wife's Car:
      - "ABC-1234"
    Johnny:
      - "J*N-*234"
```

</TabItem>
</ConfigTabs>

### Image Enhancement

<ConfigTabs>
<TabItem value="ui">

Navigate to <NavPath path="Settings > Enrichments > License plate recognition" />.

- **Enhancement level**: A value between 0 and 10 that adjusts the level of image enhancement applied to captured license plates before they are processed for recognition. Higher values increase contrast, sharpen details, and reduce noise, but excessive enhancement can blur or distort characters. This setting is best adjusted at the camera level if running LPR on multiple cameras.
  - Default: `0` (no enhancement)

</TabItem>
<TabItem value="yaml">

```yaml
lpr:
  enabled: True
  enhancement: 1
```

</TabItem>
</ConfigTabs>

If Kestrel is already recognizing plates correctly, leave enhancement at the default of `0`. However, if you're experiencing frequent character issues or incomplete plates and you can already easily read the plates yourself, try increasing the value gradually, starting at 3 and adjusting as needed. Use the `debug_save_plates` configuration option (see below) to see how different enhancement levels affect your plates.

### Normalization Rules

<ConfigTabs>
<TabItem value="ui">

Navigate to <NavPath path="Settings > Enrichments > License plate recognition" />.

Under **Replacement rules**, add regex rules to normalize detected plate strings before matching. Rules fire in order. For example:

| Pattern          | Replacement | Description                                        |
| ---------------- | ----------- | -------------------------------------------------- |
| `[%#*?]`         | _(empty)_   | Remove noise symbols                               |
| `[= ]`           | `-`         | Normalize `=` or space to dash                     |
| `O`              | `0`         | Swap `O` to `0` (common OCR error)                 |
| `I`              | `1`         | Swap `I` to `1`                                    |
| `(\w{3})(\w{3})` | `\1-\2`     | Split 6 chars into groups (e.g., ABC123 → ABC-123) |

</TabItem>
<TabItem value="yaml">

```yaml
lpr:
  replace_rules:
    - pattern: "[%#*?]" # Remove noise symbols
      replacement: ""
    - pattern: "[= ]" # Normalize = or space to dash
      replacement: "-"
    - pattern: "O" # Swap 'O' to '0' (common OCR error)
      replacement: "0"
    - pattern: "I" # Swap 'I' to '1'
      replacement: "1"
    - pattern: '(\w{3})(\w{3})' # Split 6 chars into groups (e.g., ABC123 → ABC-123) - use single quotes to preserve backslashes
      replacement: '\1-\2'
```

</TabItem>
</ConfigTabs>

These rules must be defined at the global level of your `lpr` config.

- Rules fire in order: In the example above: clean noise first, then separators, then swaps, then splits.
- Backrefs (`\1`, `\2`) allow dynamic replacements (e.g., capture groups).
- Any changes made by the rules are printed to the LPR debug log.
- Tip: You can test patterns with tools like regex101.com.

### Debugging

<ConfigTabs>
<TabItem value="ui">

Navigate to <NavPath path="Settings > Enrichments > License plate recognition" />.

- **Save debug plates**: Set to on to save captured text on plates for debugging. These images are stored in `/media/frigate/clips/lpr`, organized into subdirectories by `<camera>/<event_id>`, and named based on the capture timestamp.

</TabItem>
<TabItem value="yaml">

```yaml
lpr:
  enabled: True
  debug_save_plates: True
```

</TabItem>
</ConfigTabs>

The saved images are not full plates but rather the specific areas of text detected on the plates. It is normal for the text detection model to sometimes find multiple areas of text on the plate. Use them to analyze what text Kestrel recognized and how image enhancement affects detection.

**Note:** Kestrel does **not** automatically delete these debug images. Once LPR is functioning correctly, you should disable this option and manually remove the saved files to free up storage.

### ParkPow integration

Kestrel can report recognized plates to [ParkPow](https://app.parkpow.com/documentation/), a hosted or self-hosted ALPR visit-management dashboard. Once a vehicle's tracked object finishes and a plate has been recognized for it, Kestrel sends the plate, confidence score, camera name, timestamp, and a snapshot image to your ParkPow instance.

```yaml
lpr:
  parkpow:
    enabled: True
    host: https://app.parkpow.com # use your on-premise host if self-hosting
    token: <your ParkPow API token>
    timeout: 10
```

Generate an API token at `https://app.parkpow.com/account/token/` (or the equivalent path on a self-hosted instance).

To report only specific cameras to ParkPow, leave `lpr.parkpow.enabled` off globally and turn it on per-camera:

```yaml
lpr:
  parkpow:
    enabled: False
    token: <your ParkPow API token>

cameras:
  driveway:
    lpr:
      parkpow_enabled: True
```

`cameras.<camera>.lpr.parkpow_enabled` overrides the global `lpr.parkpow.enabled` value for that camera; leave it unset to inherit the global setting.

## Using LPR for Gate Access

### When LPR runs on a vehicle

Reading starts on the **first frame** a vehicle is tracked and continues on every
frame until one of these:

- **A known plate matches.** The decision is made, so the plate is not read
  again for that vehicle. A car waiting at a barrier would otherwise be re-read
  on every frame for as long as it sat there.
- **The vehicle has been stationary too long.** Reading continues for 5 seconds
  after a car stops, then gives up rather than grinding on a parked car.

Earlier versions waited for the object tracker to confirm movement before
starting, which meant nothing happened until a couple of frames after
`detect.min_initialized`. For a gate those are the frames worth having: the plate
is square-on and growing as the car approaches, and by the time the tracker had
made up its mind the car could already be at the barrier waiting on a read that
had not begun. The symptom in the log was one of these per frame:

```
Skipping LPR for non-stationary car object ... with no position changes.
(Detected in 5 concurrent frames, threshold to run is 6 frames)
```

**This costs less than running on every frame sounds like it should.** Each frame
starts with the license plate detector, a fixed-shape model on TensorRT. While
the car is far away the plate it finds falls below `min_area` and the pass ends
there, so the expensive OCR pipeline only runs on frames where the plate is
actually big enough to read. `min_area` is therefore the dial that controls how
much work a distant vehicle costs: raise it to start reading later and closer,
lower it to start earlier at the cost of more passes that fail to resolve.

Watch **Plate Recognition** on <NavPath path="System > Enrichments" /> after
changing it. If inference time climbs with several vehicles in view, `min_area`
is too low for the camera.

### Where the time goes

The pipeline runs four models per vehicle: a license plate detector, then
PaddleOCR text detection, orientation classification and character recognition.
They run on a GPU when one is available, and no configuration is needed for that
(`lpr.device` is only an override).

The plate detector has a fixed `[1, 3, 256, 256]` input, so TensorRT compiles one
engine for it and keeps it. **The three PaddleOCR models do not**: all declare
dynamic input dimensions, and the recognition width is recomputed from the widest
text crop in each batch, taking dozens of distinct values in practice. The ONNX
Runtime TensorRT provider builds and caches a separate engine per input shape, so
those models paid a full engine build over and over -- the compile cost that is the
only reason to use TensorRT, with none of the benefit. Kestrel now runs them on
CUDA instead, which handles changing shapes with no build step. The plate detector
stays on TensorRT.

Nothing needs configuring for this. If you are watching the logs you will see
`Loaded paddleocr model on CUDA` rather than TensorRT, and that is correct.

### Reading the timings

<NavPath path="System > Enrichments" /> shows a card per stage, so a slow pipeline
can be read as the sum of its parts instead of one opaque number:

| Card | What it covers |
| ---- | -------------- |
| **YOLOv9 Plate Detection** | Finding the plate in the frame. One model, static input shape, on TensorRT. |
| **Plate Text Detection** | Finding the text regions inside the plate crop (PaddleOCR detection). |
| **Plate Orientation Check** | Deciding whether a crop is upside down. |
| **Plate Character Recognition** | Reading the characters (PaddleOCR recognition). Runs once per batch of text crops, so it scales with how many regions the detector found. |
| **Plate Image Processing (CPU)** | Everything that is not a model: resizing and normalising each crop, the optional CLAHE and bilateral filter, CTC decoding, box clustering and the polygon work. |
| **Plate Recognition** | The total of the four above. This is the number to watch; the others say where it went. |

**Plate Image Processing (CPU) is the one to look at first when the total is
high.** None of it runs on a GPU, so a faster card changes nothing — the answer
is to do less of it. Measured per call on a typical crop:

| Work | Cost |
| ---- | ---- |
| Recognition preprocessing, `enhancement: 0` | 0.39 ms per text crop |
| Recognition preprocessing, `enhancement: 1` (adds CLAHE) | 0.64 ms per text crop |
| Recognition preprocessing, `enhancement: 4` (adds a bilateral filter) | 1.43 ms per text crop |
| Recognition preprocessing, `enhancement: 8` | 1.81 ms per text crop |
| Plate crop extraction (perspective warp) | 0.67 ms per box |

`enhancement` above 3 turns on a bilateral filter, which is the most expensive
thing in the pipeline per crop. Raise it only while watching whether reads
actually improve, and drop it back if they do not.

If **Plate Character Recognition** dominates, the text detector is finding more
regions than it should — a tighter `min_area` or a better-framed camera reduces
the batch size it has to read.

For a deeper breakdown than the dashboard gives, turn on debug logging:

```yaml
logger:
  logs:
    frigate.data_processing.common.license_plate: debug
```

### Accuracy settings that matter for a gate

- `min_plate_length` rejects short reads. The most common OCR failure is part of a
  plate resolving into a plausible shorter string, so set this to the real length
  of the plates you expect.
- `format` is a regex the whole plate must match. For a gate this is a security
  control, not a convenience: it is what stops a misread of a passing vehicle from
  resembling a plate on your allow list. Kestrel refuses to start if the pattern
  does not compile, because a `format` that silently stopped filtering would admit
  every plate it could read.
- `recognition_threshold` is the confidence a read needs. Raise it for a gate.
- `known_plates` with `match_distance` allows fuzzy matching. **`match_distance`
  is a character budget for being wrong**: at the default of `1`, a plate one
  character different from a known plate still matches, which turns every entry on
  your allow list into a small family of accepted plates. For gate access consider
  `match_distance: 0` and enrol the exact plates, accepting that a misread means
  the gate does not open rather than that the wrong vehicle gets in.
- `enhancement` helps on soft or low-contrast plates and costs CPU per frame. Raise
  it only while watching whether reads actually improve; it is not free.

### What LPR cannot tell you

A plate is a flat printed object, so unlike a face there is nothing to distinguish
a real plate from a good picture of one. A printed plate held up to the camera, or
a cloned plate on another vehicle, reads exactly like the genuine article. LPR
identifies a *plate*, not a vehicle and not a person.

For a gate, treat a plate as one factor. Pair it with something else -- a fob, a
code, an intercom, or a second camera confirming the vehicle matches the plate --
and keep the event log so an unexpected entry can be reviewed afterwards.

## Configuration Examples

These configuration parameters are available at the global level. The only optional parameters that should be set at the camera level are `enabled`, `min_area`, and `enhancement`.

<ConfigTabs>
<TabItem value="ui">

Navigate to <NavPath path="Settings > Enrichments > License plate recognition" />.

| Field                          | Description                                                                                           |
| ------------------------------ | ----------------------------------------------------------------------------------------------------- |
| **Enable LPR**                 | Set to on                                                                                             |
| **Minimum plate area**         | Set to `1500` to ignore plates with an area (length x width) smaller than 1500 pixels                  |
| **Min plate length**           | Set to `4` to only recognize plates with 4 or more characters                                          |
| **Known plates > Wife's Car**  | `ABC-1234`, `ABC-I234` (accounts for potential confusion between the number one and capital letter I) |
| **Known plates > Johnny**      | `J*N-*234` (matches JHN-1234 and JMN-I234; `*` matches any number of characters)                      |
| **Known plates > Sally**       | `[S5]LL 1234` (matches both SLL 1234 and 5LL 1234)                                                    |
| **Known plates > Work Trucks** | `EMP-[0-9]{3}[A-Z]` (matches plates like EMP-123A, EMP-456Z)                                          |

</TabItem>
<TabItem value="yaml">

```yaml
lpr:
  enabled: True
  min_area: 1500 # Ignore plates with an area (length x width) smaller than 1500 pixels
  min_plate_length: 4 # Only recognize plates with 4 or more characters
  known_plates:
    Wife's Car:
      - "ABC-1234"
      - "ABC-I234" # Accounts for potential confusion between the number one (1) and capital letter I
    Johnny:
      - "J*N-*234" # Matches JHN-1234 and JMN-I234, but also note that "*" matches any number of characters
    Sally:
      - "[S5]LL 1234" # Matches both SLL 1234 and 5LL 1234
    Work Trucks:
      - "EMP-[0-9]{3}[A-Z]" # Matches plates like EMP-123A, EMP-456Z
```

</TabItem>
</ConfigTabs>

:::note

If a camera is configured to detect vehicles but you don't want Kestrel to run LPR for that camera, disable LPR at the camera level:

<ConfigTabs>
<TabItem value="ui">

Navigate to <NavPath path="Settings > Camera configuration > License plate recognition" /> for the desired camera and disable the **Enable LPR** toggle.

</TabItem>
<TabItem value="yaml">

```yaml
cameras:
  side_yard:
    lpr:
      enabled: False
    ...
```

</TabItem>
</ConfigTabs>

:::

## Dedicated LPR Cameras

Dedicated LPR cameras are single-purpose cameras with powerful optical zoom to capture license plates on distant vehicles, often with fine-tuned settings to capture plates at night.

To mark a camera as a dedicated LPR camera, set `type: "lpr"` in the camera configuration.

:::note

Kestrel's dedicated LPR mode is optimized for cameras with a narrow field of view, specifically positioned and zoomed to capture license plates exclusively. If your camera provides a general overview of a scene rather than a tightly focused view, this mode is not recommended.

:::

Users can configure Kestrel's dedicated LPR mode in two different ways depending on whether a Frigate+ (or native `license_plate` detecting) model is used:

### Using a Frigate+ (or Native `license_plate` Detecting) Model

Users running a Frigate+ model (or any model that natively detects `license_plate`) can take advantage of `license_plate` detection. This allows license plates to be treated as standard objects in dedicated LPR mode, meaning that alerts, detections, snapshots, and other Kestrel features work as usual, and plates are detected efficiently through your configured object detector.

An example configuration for a dedicated LPR camera using a `license_plate`-detecting model:

<ConfigTabs>
<TabItem value="ui">

Navigate to <NavPath path="Settings > Enrichments > License plate recognition" /> and set **Enable LPR** to on. Set **Device** to `CPU` (can also be `GPU` if available).

Navigate to <NavPath path="Settings > Camera configuration > Streams (FFmpeg)" /> and add your camera streams.

Navigate to <NavPath path="Settings > Camera configuration > Object detection" />.

| Field                             | Description                                                                                                                    |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **Enable object detection**       | Set to on                                                                                                                      |
| **Detect FPS**                    | Set to `5`. Increase to `10` if vehicles move quickly across your frame. Higher than 10 is unnecessary and is not recommended. |
| **Minimum initialization frames** | Set to `2`                                                                                                                     |
| **Detect width**                  | Set to `1920`                                                                                                                  |
| **Detect height**                 | Set to `1080`                                                                                                                  |

Navigate to <NavPath path="Settings > Camera configuration > Objects" />.

| Field                                          | Description         |
| ---------------------------------------------- | ------------------- |
| **Objects to track**                           | Add `license_plate` |
| **Object filters > License Plate > Threshold** | Set to `0.7`        |

Navigate to <NavPath path="Settings > Camera configuration > Motion detection" />.

| Field                | Description                                                           |
| -------------------- | --------------------------------------------------------------------- |
| **Motion threshold** | Set to `30`                                                           |
| **Contour area**     | Set to `60`. Use an increased value to tune out small motion changes. |
| **Improve contrast** | Set to off                                                            |

Also add a motion mask over your camera's timestamp so it is not incorrectly detected as a license plate.

Navigate to <NavPath path="Settings > Camera configuration > Recording" />.

| Field                | Description                                              |
| -------------------- | -------------------------------------------------------- |
| **Enable recording** | Set to on. Disable recording if you only want snapshots. |

Navigate to <NavPath path="Settings > Camera configuration > Snapshots" />.

| Field                | Description |
| -------------------- | ----------- |
| **Enable snapshots** | Set to on   |

</TabItem>
<TabItem value="yaml">

```yaml
# LPR global configuration
lpr:
  enabled: True
  device: CPU # can also be GPU if available

# Dedicated LPR camera configuration
cameras:
  dedicated_lpr_camera:
    type: "lpr" # required to use dedicated LPR camera mode
    ffmpeg: ... # add your streams
    detect:
      enabled: True
      fps: 5 # increase to 10 if vehicles move quickly across your frame. Higher than 10 is unnecessary and is not recommended.
      min_initialized: 2
      width: 1920
      height: 1080
    objects:
      track:
        - license_plate
      filters:
        license_plate:
          threshold: 0.7
    motion:
      threshold: 30
      contour_area: 60 # use an increased value to tune out small motion changes
      improve_contrast: false
      mask: 0.704,0.007,0.709,0.052,0.989,0.055,0.993,0.001 # ensure your camera's timestamp is masked
    record:
      enabled: True # disable recording if you only want snapshots
    snapshots:
      enabled: True
    review:
      detections:
        labels:
          - license_plate
```

</TabItem>
</ConfigTabs>

With this setup:

- License plates are treated as normal objects in Kestrel.
- Scores, alerts, detections, and snapshots work as expected.
- Snapshots will have license plate bounding boxes on them.
- The `frigate/events` MQTT topic will publish tracked object updates.
- Debug view will display `license_plate` bounding boxes.
- If you are using a Frigate+ model and want to submit images from your dedicated LPR camera for model training and fine-tuning, annotate both the vehicle and the `license_plate` in the snapshots on the Frigate+ website, even if the vehicle is barely visible.

### Using the Secondary LPR Pipeline (Without Frigate+)

If you are not running a Frigate+ model, you can use Kestrel's built-in secondary dedicated LPR pipeline. In this mode, Kestrel bypasses the standard object detection pipeline and runs a local license plate detector model on the full frame whenever motion activity occurs.

An example configuration for a dedicated LPR camera using the secondary pipeline:

<ConfigTabs>
<TabItem value="ui">

Navigate to <NavPath path="Settings > Enrichments > License plate recognition" /> and set **Enable LPR** to on. Set **Device** to `CPU` (can also be `GPU` if available and the correct Docker image is used). Set **Detection threshold** to `0.7` (change if necessary).

Navigate to <NavPath path="Settings > Camera configuration > License plate recognition" /> for your dedicated LPR camera.

| Field                 | Description                                                                      |
| --------------------- | -------------------------------------------------------------------------------- |
| **Enable LPR**        | Set to on                                                                        |
| **Enhancement level** | Set to `3` (optional, enhances the image before trying to recognize characters) |

Navigate to <NavPath path="Settings > Camera configuration > Streams (FFmpeg)" /> and add your camera streams.

Navigate to <NavPath path="Settings > Camera configuration > Object detection" />.

| Field                       | Description                                                                                                                  |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| **Enable object detection** | Set to off to disable Kestrel's standard object detection pipeline                                                           |
| **Detect FPS**              | Set to `5`. Increase if necessary, though high values may slow down Kestrel's enrichments pipeline and use considerable CPU. |
| **Detect width**            | Set to `1920` (recommended value, but depends on your camera)                                                                |
| **Detect height**           | Set to `1080` (recommended value, but depends on your camera)                                                                |

Navigate to <NavPath path="Settings > Camera configuration > Objects" />.

| Field                | Description                                                                            |
| -------------------- | -------------------------------------------------------------------------------------- |
| **Objects to track** | Set to an empty list, required when not using a Frigate+ model for dedicated LPR mode |

Navigate to <NavPath path="Settings > Camera configuration > Motion detection" />.

| Field                | Description                                                           |
| -------------------- | --------------------------------------------------------------------- |
| **Motion threshold** | Set to `30`                                                           |
| **Contour area**     | Set to `60`. Use an increased value to tune out small motion changes. |
| **Improve contrast** | Set to off                                                            |

Navigate to <NavPath path="Settings > Camera configuration > Masks / Zones" /> and add a motion mask over your camera's timestamp so it is not incorrectly detected as a license plate.

Navigate to <NavPath path="Settings > Camera configuration > Recording" />.

| Field                | Description                                              |
| -------------------- | -------------------------------------------------------- |
| **Enable recording** | Set to on. Disable recording if you only want snapshots. |

Navigate to <NavPath path="Settings > Camera configuration > Review" />.

| Field                                     | Description     |
| ----------------------------------------- | --------------- |
| **Detections config > Enable detections** | Set to on       |
| **Detections config > Retain > Default**  | Set to `7` days |

</TabItem>
<TabItem value="yaml">

```yaml
# LPR global configuration
lpr:
  enabled: True
  device: CPU # can also be GPU if available and correct Docker image is used
  detection_threshold: 0.7 # change if necessary

# Dedicated LPR camera configuration
cameras:
  dedicated_lpr_camera:
    type: "lpr" # required to use dedicated LPR camera mode
    lpr:
      enabled: True
      enhancement: 3 # optional, enhance the image before trying to recognize characters
    ffmpeg: ... # add your streams
    detect:
      enabled: False # disable Kestrel's standard object detection pipeline
      fps: 5 # increase if necessary, though high values may slow down Kestrel's enrichments pipeline and use considerable CPU
      width: 1920
      height: 1080
    objects:
      track: [] # required when not using a Frigate+ model for dedicated LPR mode
    motion:
      threshold: 30
      contour_area: 60 # use an increased value here to tune out small motion changes
      improve_contrast: false
      mask: 0.704,0.007,0.709,0.052,0.989,0.055,0.993,0.001 # ensure your camera's timestamp is masked
    record:
      enabled: True # disable recording if you only want snapshots
    review:
      detections:
        enabled: True
        retain:
          default: 7
```

</TabItem>
</ConfigTabs>

With this setup:

- The standard object detection pipeline is bypassed. Any detected license plates on dedicated LPR cameras are treated similarly to manual events in Kestrel. You must **not** specify `license_plate` as an object to track.
- The license plate detector runs on the full frame whenever motion is detected and processes frames according to your detect `fps` setting.
- Review items will always be classified as a `detection`.
- Snapshots will always be saved.
- Zones and object masks are **not** used.
- The `frigate/events` MQTT topic will **not** publish tracked object updates with the license plate bounding box and score, though `frigate/reviews` will publish if recordings are enabled. If a plate is recognized as a [known](#matching) plate, publishing will occur with an updated `sub_label` field. If characters are recognized, publishing will occur with an updated `recognized_license_plate` field.
- License plate snapshots are saved at the highest-scoring moment and appear in Explore.
- Debug view will not show `license_plate` bounding boxes.

### Summary

| Feature                 | Native `license_plate` detecting Model (like Frigate+) | Secondary Pipeline (without native model or Frigate+)           |
| ----------------------- | ------------------------------------------------------ | --------------------------------------------------------------- |
| License Plate Detection | Uses `license_plate` as a tracked object               | Runs a dedicated LPR pipeline                                   |
| FPS Setting             | 5 (increase for fast-moving cars)                      | 5 (increase for fast-moving cars, but it may use much more CPU) |
| Object Detection        | Standard Frigate+ detection applies                    | Bypasses standard object detection                              |
| Debug View              | May show `license_plate` bounding boxes                | May **not** show `license_plate` bounding boxes                 |
| MQTT `frigate/events`   | Publishes tracked object updates                       | Publishes limited updates                                       |
| Explore                 | Recognized plates available in More Filters            | Recognized plates available in More Filters                     |

By selecting the appropriate configuration, users can optimize their dedicated LPR cameras based on whether they are using a Frigate+ model or the secondary LPR pipeline.

### Best practices for using Dedicated LPR camera mode

- Tune your motion detection and increase the `contour_area` until you see only larger motion boxes being created as cars pass through the frame (likely somewhere between 50-90 for a 1920x1080 detect stream). Increasing the `contour_area` filters out small areas of motion and will prevent excessive resource use from looking for license plates in frames that don't even have a car passing through it.
- Disable the `improve_contrast` motion setting, especially if you are running LPR at night and the frame is mostly dark. This will prevent small pixel changes and smaller areas of motion from triggering license plate detection.
- Ensure your camera's timestamp is covered with a motion mask so that it's not incorrectly detected as a license plate.
- For non-Frigate+ users, you may need to change your camera settings for a clearer image or decrease your global `recognition_threshold` config if your plates are not being accurately recognized at night.
- The secondary pipeline mode runs a local AI model on your CPU or GPU (depending on how `device` is configured) to detect plates. Increasing detect `fps` will increase resource usage proportionally.

## FAQ

### Detection and Recognition

<FaqItem id="why-isnt-my-license-plate-being-detected-and-recognized" question="Why isn't my license plate being detected and recognized?">

Ensure that:

- Your camera has a clear, human-readable, well-lit view of the plate. If you can't read the plate's characters, Kestrel certainly won't be able to, even if the model is recognizing a `license_plate`. This may require changing video size, quality, or frame rate settings on your camera, depending on your scene and how fast the vehicles are traveling.
- The plate is large enough in the image (try adjusting `min_area`) or increasing the resolution of your camera's stream.
- Your `enhancement` level (if you've changed it from the default of `0`) is not too high. Too much enhancement will run too much denoising and cause the plate characters to become blurry and unreadable.

If you are using a Frigate+ model or a custom model that detects license plates, ensure that `license_plate` is added to your list of objects to track.
If you are using the free model that ships with Kestrel, you should _not_ add `license_plate` to the list of objects to track.

Recognized plates will show as object labels in the debug view and will appear in the "Recognized License Plates" select box in the More Filters popout in Explore.

If you are still having issues detecting plates, start with a basic configuration and see the debugging tips below.

</FaqItem>

<FaqItem id="can-i-run-lpr-without-detecting-car-or-motorcycle-objects" question={<>Can I run LPR without detecting vehicle objects?</>}>

In normal LPR mode, Kestrel requires a vehicle to be detected first before recognizing a license plate. If you have a dedicated LPR camera, you can change the camera `type` to `"lpr"` to use the Dedicated LPR Camera algorithm. This comes with important caveats, though. See the [Dedicated LPR Cameras](#dedicated-lpr-cameras) section above.

</FaqItem>

<FaqItem id="how-can-i-improve-detection-accuracy" question="How can I improve detection accuracy?">

- Use high-quality cameras with good resolution.
- Adjust `detection_threshold` and `recognition_threshold` values.
- Define a `format` regex to filter out invalid detections.

</FaqItem>

<FaqItem id="does-lpr-work-at-night" question="Does LPR work at night?">

Yes, but performance depends on camera quality, lighting, and infrared capabilities. Make sure your camera can capture clear images of plates at night.

</FaqItem>

<FaqItem id="can-i-limit-lpr-to-specific-zones" question="Can I limit LPR to specific zones?">

LPR, like other Kestrel enrichments, runs at the camera level rather than the zone level. While you can't restrict LPR to specific zones directly, you can control when recognition runs by setting a `min_area` value to filter out smaller detections.

</FaqItem>

<FaqItem id="how-can-i-match-known-plates-with-minor-variations" question="How can I match known plates with minor variations?">

Use `match_distance` to allow small character mismatches. Alternatively, define multiple variations in `known_plates`.

</FaqItem>

### Performance and Troubleshooting

<FaqItem id="how-do-i-debug-lpr-issues" question="How do I debug LPR issues?">

Start with ["Why isn't my license plate being detected and recognized?"](#why-isnt-my-license-plate-being-detected-and-recognized). If you are still having issues, work through these steps.

1. Start with a simplified LPR config.
   - Remove or comment out everything in your LPR config, including `min_area`, `min_plate_length`, `format`, `known_plates`, or `enhancement` values so that the only values left are `enabled` and `debug_save_plates`. This will run LPR with Kestrel's default values.

<ConfigTabs>
<TabItem value="ui">

Navigate to <NavPath path="Settings > Enrichments > License plate recognition" />.

- Set **Enable LPR** to on
- Set **Device** to `CPU`
- Set **Save debug plates** to on

</TabItem>
<TabItem value="yaml">

```yaml
lpr:
  enabled: true
  device: CPU
  debug_save_plates: true
```

</TabItem>
</ConfigTabs>

2. Enable debug logs to see exactly what Kestrel is doing.
   - Enable debug logs for LPR by adding `frigate.data_processing.common.license_plate: debug` to your `logger` configuration. These logs are _very_ verbose, so only keep this enabled when necessary. Restart Kestrel after this change.

     ```yaml
     logger:
       default: info
       logs:
         # highlight-next-line
         frigate.data_processing.common.license_plate: debug
     ```

3. Ensure your plates are being _detected_.

   If you are using a Frigate+ or `license_plate` detecting model:
   - Watch the [Debug view](/usage/live#the-single-camera-view) to ensure that `license_plate` is being detected.
   - View MQTT messages for `frigate/events` to verify detected plates.
   - You may need to adjust your `min_score` and/or `threshold` for the `license_plate` object if your plates are not being detected.

   If you are **not** using a Frigate+ or `license_plate` detecting model:
   - Watch the debug logs for messages from the YOLOv9 plate detector.
   - You may need to adjust your `detection_threshold` if your plates are not being detected.

4. Ensure the characters on detected plates are being _recognized_.
   - Check the **Plate recognition** inference time in Enrichment metrics (<NavPath path="Health and Metrics > Enrichments" />). High inference times (> 100ms) could lead to poor recognition results, especially for dedicated LPR cameras where the plate crosses the frame quickly.
   - Enable `debug_save_plates` to save images of detected text on plates to the clips directory (`/media/frigate/clips/lpr`). Ensure these images are readable and the text is clear.
   - Watch the debug view to see plates recognized in real-time. For non-dedicated LPR cameras, the vehicle's label will change to the recognized plate when LPR is enabled and working.
   - Adjust `recognition_threshold` settings per the suggestions [above](#advanced-configuration).

</FaqItem>

<FaqItem id="will-lpr-slow-down-my-system" question="Will LPR slow down my system?">

LPR's performance impact depends on your hardware. Ensure you have at least 4GB RAM and a capable CPU or GPU for optimal results. If you are running the Dedicated LPR Camera mode, resource usage will be higher compared to users who run a model that natively detects license plates. Tune your motion detection settings for your dedicated LPR camera so that the license plate detection model runs only when necessary.

</FaqItem>

<FaqItem id="i-am-seeing-a-yolov9-plate-detection-metric-in-enrichment-metrics-but-i-have-a-frigate-or-custom-model-that-detects-license_plate-why-is-the-yolov9-model-running" question={<>I am seeing a YOLOv9 plate detection metric in Enrichment Metrics, but I have a Frigate+ or custom model that detects <code>license_plate</code>. Why is the YOLOv9 model running?</>}>

The YOLOv9 license plate detector model will run (and the metric will appear) if you've enabled LPR but haven't defined `license_plate` as an object to track, either at the global or camera level.

If you are detecting vehicles on cameras where you don't want to run LPR, make sure you disable LPR it at the camera level. And if you do want to run LPR on those cameras, make sure you define `license_plate` as an object to track.

</FaqItem>

<FaqItem id="it-looks-like-frigate-picked-up-my-cameras-timestamp-or-overlay-text-as-the-license-plate-how-can-i-prevent-this" question="It looks like Kestrel picked up my camera's timestamp or overlay text as the license plate. How can I prevent this?">

This could happen if vehicles travel close to your camera's timestamp or overlay text. You could either move the text through your camera's firmware, or apply a mask to it in Kestrel.

If you are using a model that natively detects `license_plate`, add an _object mask_ of type `license_plate` and a _motion mask_ over your text.

If you are not using a model that natively detects `license_plate` or you are using dedicated LPR camera mode, only a _motion mask_ over your text is required.

</FaqItem>

<FaqItem id="i-see-error-running--model-in-my-logs-or-my-inference-time-is-very-high-how-can-i-fix-this" question={'I see "Error running ... model" in my logs, or my inference time is very high. How can I fix this?'}>

This usually happens when your GPU is unable to compile or use one of the LPR models. Set your `device` to `CPU` and try again. GPU acceleration only provides a slight performance increase, and the models are lightweight enough to run without issue on most CPUs.

</FaqItem>
