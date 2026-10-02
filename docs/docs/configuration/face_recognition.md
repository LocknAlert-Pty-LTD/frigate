---
id: face_recognition
title: Face Recognition
---

import ConfigTabs from "@site/src/components/ConfigTabs";
import TabItem from "@theme/TabItem";
import NavPath from "@site/src/components/NavPath";
import FaqItem from "@site/src/components/FaqItem";

Face recognition identifies known individuals by matching detected faces with previously learned facial data. When a known `person` is recognized, their name will be added as a `sub_label`. This information is included in the UI, filters, as well as in notifications.

:::info

Face recognition requires a one-time internet connection to download detection and embedding models from GitHub. Once cached, models work fully offline. See [Network Requirements](/frigate/network_requirements#one-time-model-downloads) for details.

:::

## Using Face Recognition for Access Control

Kestrel checks that a recognised face belongs to someone actually present, rather
than to a photograph of them, and withholds the name when it cannot establish
that. Liveness is on by default (`face_recognition.liveness`).

:::warning

**A face match still should not be the only thing that opens a gate.** Liveness
here stops a photograph. It does not stop video replayed on a good screen, and it
is not certified presentation-attack detection (ISO/IEC 30107-3). Pair it with
something the person carries -- a fob, a PIN, a phone -- or with an intercom
confirmation, and treat the recognised name as strong evidence of *who* is there
rather than as the decision itself.

:::

### What it checks

Nothing about how a face *looks* separates a person from a good photo of them.
What separates them is what they are:

- **A photo is flat.** Any flat surface, seen from any angle, maps between two
  views by a single projective transform. A real face does not: as the head
  turns, the nose and the ears shift by different amounts. What no flat transform
  can explain is parallax, and parallax is depth.
- **A photo does not blink.** Eyes and mouths open and close. A printed face holds
  its shape however the paper is waved. This check needs no head movement at all,
  so it is what lets someone standing still be recognised.
- **A photo has been through a printer or a screen**, which can leave a halftone
  pattern or a pixel grid beating against the sensor. The weakest of the three: a
  high-resolution screen at the right distance leaves no trace.

The first two are measured from the 68 facial landmarks across several frames of
the same tracked person, so a verdict needs a few frames and firms up as someone
approaches.

### What defeats it

Stated plainly, because an access control decision deserves it:

- **Video replayed on a screen.** A recording of a real face turning already
  contains genuine parallax, and displaying it reproduces that parallax. This is
  the attack liveness here does not stop.
- **A curved or bent photo**, which is not flat and will show some depth. A mask,
  or a photo wrapped around something head-shaped, is out of scope entirely.
- **A face too small, dim or blurred for precise landmarks.** Rather than guess,
  Kestrel refuses to judge and withholds the name (`max_noise_floor`).

### Holding still does not defeat it

These checks look for evidence of presence rather than for signs of fakery, so
absent evidence is not a pass. A photo held perfectly still produces no parallax
and no blink, and so is never recognised. The cost of that design is symmetric: a
real person who stands motionless, face-on, and does not blink is not recognised
either. Walking toward a camera normally supplies plenty of both.

### Tuning it

The defaults come from measurements on projected face geometry, in the units the
analyzer logs. Yours are the numbers that matter. Turn on debug logging:

```yaml
logger:
  logs:
    frigate.data_processing.common.face.liveness: debug
```

Then hold a photo of an enrolled person up to the camera, walk past it yourself,
and compare. Every frame logs every signal:

```
liveness 1712345678.1-abc123: face has depth (depth_growth=0.0241
  parallax=0.0318 noise_floor=0.0077 viewpoint=0.0562 deformation=0.043
  appearance=1.000 frames=4)
```

- `depth_growth` is the main signal: how much a flat surface fails to explain the
  motion, over and above this face's own landmark noise. A real face turning
  about 20 degrees measures 0.014 to 0.029; a photo measures 0.000 to 0.003.
- `noise_floor` is how imprecise this face's landmarks are, measured from two
  nearly identical views where anything left unexplained must be jitter. Above
  `max_noise_floor` (0.05, roughly 2.5px) a real face and a photo become
  indistinguishable, and Kestrel declines to judge. **Raising this does not
  improve detection; it only permits guesses.**
- `deformation` is how much the eyes and mouth opened or closed, relative to the
  distance between the eyes. A real blink or a spoken word measures 0.12 to 0.15.
- `viewpoint` is how much the view changed at all. It only decides which reason
  is logged when a face is refused.
- `appearance` is 1.0 for a direct-looking view, falling toward 0.0 for something
  that looks reproduced.

If real people are being refused, the usual cause is `noise_floor` sitting near
the cap, which means the faces are too small: raise the camera resolution, move
the camera closer, or lower `min_area` last. Loosening
`depth_growth_threshold` is the wrong first move, because it also lets photos
through.

<ConfigTabs>
<TabItem value="ui">

Navigate to <NavPath path="Settings > Enrichments > Face recognition" />.

- **Require liveness**: withhold a recognised name unless the face is shown to
  belong to someone present. Turning this off means a printed photo or a phone
  screen is recognised exactly like a real face.
  - Default: `true`
- **Minimum frames**: frames of one person needed before liveness can be decided.
  Three is the minimum that can measure anything: two establish the landmark
  noise floor and the third is measured against it.
  - Default: `3`
- **Depth threshold**: how much a flat surface must fail to explain the motion
  before the face counts as solid.
  - Default: `0.008`
- **Blink threshold**: how much the eyes or mouth must open or close to count as a
  working face.
  - Default: `0.11`
- **Maximum landmark noise**: refuse to judge once landmark jitter reaches this.
  - Default: `0.05`
- **Minimum viewpoint change**: how much the view must change before a failure to
  show depth is treated as proof of flatness rather than as too little
  information.
  - Default: `0.04`
- **Appearance threshold**: below this score for looking like a direct view,
  reject outright.
  - Default: `0.5`

</TabItem>
<TabItem value="yaml">

```yaml
face_recognition:
  enabled: true
  liveness:
    enabled: true
    min_frames: 3
    depth_growth_threshold: 0.008
    deformation_threshold: 0.11
    max_noise_floor: 0.05
    min_viewpoint: 0.04
    appearance_threshold: 0.5
```

</TabItem>
</ConfigTabs>

### Stronger anti-spoofing

To resist video replay, add a trained presentation-attack model. MiniFASNetV2
from the Silent-Face-Anti-Spoofing project is Apache-2.0 licensed, around 600KB,
and runs on CPU; `LivenessAnalyzer.observe` already accepts a `model_score` that
replaces the frequency check when supplied. Wiring a third-party model download
into the path that opens your gate is a decision worth making deliberately, so it
is not enabled here. For an unattended entrance, dedicated access-control
hardware with certified presentation-attack detection remains the right answer.

### Settings that matter alongside it

- `recognition_threshold` and `unknown_score` decide how confident a match must
  be. Raising them trades recognising people less often for mislabelling them
  less often, which is the right trade here.
- `recognition_margin` guards the failure that matters most for access:
  confusing one enrolled person with another. Raise it if you have enrolled
  people who look alike.
- `min_faces` requires the same person to be recognised across several frames
  before the name is applied.
- `min_blur_variance` declines faces too soft to carry identity.

None of these detect spoofing; they reduce the chance of the wrong *enrolled*
person being named.

## Model Requirements

### Face Detection

When running a Frigate+ model (or any custom model that natively detects faces) should ensure that `face` is added to the [list of objects to track](../plus/index.md#available-label-types) either globally or for a specific camera. This will allow face detection to run at the same time as object detection and be more efficient.

When running a default COCO model or another model that does not include `face` as a detectable label, face detection will run via CV2 using a lightweight DNN model that runs on the CPU. In this case, you should _not_ define `face` in your list of objects to track.

:::note

Kestrel needs to first detect a `person` before it can detect and recognize a face.

:::

### Face Recognition

Kestrel has support for two face recognition model types:

- **small**: Kestrel will run a FaceNet embedding model to recognize faces, which runs locally on the CPU. This model is optimized for efficiency and is not as accurate.
- **large**: Kestrel will run a large ArcFace embedding model that is optimized for accuracy. It is only recommended to be run when an integrated or dedicated GPU / NPU is available.

In both cases, a lightweight face landmark detection model is also used to align faces before running recognition.

All of these features run locally on your system.

## Minimum System Requirements

A CPU with AVX + AVX2 instructions is required to run Face Recognition.

The `small` model is optimized for efficiency and runs on the CPU, most CPUs should run the model efficiently.

The `large` model is optimized for accuracy, an integrated or discrete GPU / NPU is required. See the [Hardware Accelerated Enrichments](/configuration/hardware_acceleration_enrichments.md) documentation.

## Configuration

Face recognition is disabled by default and must be enabled before it can be used. Face recognition is a global configuration setting.

<ConfigTabs>
<TabItem value="ui">

Navigate to <NavPath path="Settings > Enrichments > Face recognition" />.

- Set **Enable face recognition** to on

</TabItem>
<TabItem value="yaml">

```yaml
face_recognition:
  enabled: true
```

</TabItem>
</ConfigTabs>

Like the other real-time processors in Kestrel, face recognition runs on the camera stream defined by the `detect` role in your config. To ensure optimal performance, select a suitable resolution for this stream in your camera's firmware that fits your specific scene and requirements.

## Advanced Configuration

Fine-tune face recognition with these optional parameters. The only optional parameters that can be set at the camera level are `enabled` and `min_area`.

### Detection

<ConfigTabs>
<TabItem value="ui">

Navigate to <NavPath path="Settings > Enrichments > Face recognition" />.

- **Detection threshold**: Face detection confidence score required before recognition runs. This field only applies to the standalone face detection model; `min_score` should be used to filter for models that have face detection built in.
  - Default: `0.7`
- **Minimum face area**: Minimum size (in pixels) a face must be before recognition runs. Depending on the resolution of your camera's `detect` stream, you can increase this value to ignore small or distant faces.
  - Default: `750` pixels

</TabItem>
<TabItem value="yaml">

```yaml
face_recognition:
  enabled: true
  detection_threshold: 0.7
  min_area: 750
```

</TabItem>
</ConfigTabs>

### Recognition

<ConfigTabs>
<TabItem value="ui">

Navigate to <NavPath path="Settings > Enrichments > Face recognition" />.

- **Model size**: Which model size to use, options are `small` (FaceNet) or `large` (ArcFace). ArcFace separates faces considerably better and is the default. Changing this re-embeds your whole face library on the next restart; the source images are kept, so there is nothing to re-upload.
  - Default: `large`
- **Unknown score threshold**: Min score to mark a person as a potential match; matches at or below this will be marked as unknown.
  - Default: `0.8`
- **Recognition threshold**: Recognition confidence score required to add the face to the object as a sub label.
  - Default: `0.9`
- **Minimum faces**: Min face recognitions for the sub label to be applied to the person object.
  - Default: `1`
- **Save attempts**: Number of recent recognition attempts kept for review in the Face Library. Each is a small JPEG crop, so raising this costs little disk.
  - Default: `400`
- **Blur confidence filter**: Enables a filter that calculates how blurry the face is and adjusts the confidence based on this.
  - Default: `True`
- **Minimum sharpness**: Rejects a face outright when its Laplacian variance falls below this, rather than only lowering its score the way the blur confidence filter does. A motion-blurred face carries little identity information, so it is declined instead of guessed at. Set to `0` to disable. Raise it to demand sharper faces; lower it if faces are being dropped in low light.
  - Default: `120`
- **Recognition margin**: How far ahead the best-matching person must be of the runner-up, in cosine similarity, before the match is accepted. A face scoring 0.91 against one person and 0.90 against another is not a confident identification however high those numbers look, and this is what stops look-alikes -- siblings especially -- being confidently mislabelled. Set to `0` to disable. Raise it if similar-looking people are being confused.
  - Default: `0.05`
- **Neighbours per person**: Each enrolled person is scored by the average of their this-many most similar training images. Earlier versions averaged every image of a person into a single face, which could represent nobody well: the average of someone with and without glasses matches neither. Raise it if you enrol many varied photos per person.
  - Default: `3`
- **Device**: Target a specific device to run the face recognition model on (multi-GPU installation). This setting is only applicable when using the `large` model. See [onnxruntime's provider options](https://onnxruntime.ai/docs/execution-providers/).
  - Default: `None`

</TabItem>
<TabItem value="yaml">

```yaml
face_recognition:
  enabled: true
  model_size: large
  unknown_score: 0.8
  recognition_threshold: 0.9
  min_faces: 1
  save_attempts: 400
  blur_confidence_filter: true
  min_blur_variance: 120
  recognition_margin: 0.05
  knn_top_k: 3
  device: None
```

</TabItem>
</ConfigTabs>

### People you do not want recognized

`ignored_faces` names people who are never reported, even when Kestrel recognizes
them. For anyone who lives or works somewhere and would rather the cameras did
not keep a record of them.

<ConfigTabs>
<TabItem value="ui">

Navigate to <NavPath path="Settings > Enrichments > Face recognition" />.

- **Do not recognize**: names that are never reported. The face stays enrolled
  and is still matched internally, but the name reaches nothing and no attempt
  image is kept.
  - Default: empty

</TabItem>
<TabItem value="yaml">

```yaml
face_recognition:
  enabled: true
  ignored_faces:
    - Jane Doe
    - jane_doe_2
```

</TabItem>
</ConfigTabs>

**They have to stay enrolled.** A name must be matched before it can be
suppressed, so deleting someone from the face library does the opposite of what
you want: they become an unrecognized person and get reported as `unknown` on
every camera that sees them. Keep the training images and list the name here.

**What stops:**

- No `sub_label` on the tracked object, so no event, MQTT message or notification
  carries the name.
- No attempt image is written, so the Face Library does not fill up with crops of
  someone who asked not to be recorded.

**What does not stop:** the person is still detected as a `person` object and
still appears in recordings and review items like anyone else. This suppresses
*identification*, not detection. It is also not a privacy control against anyone
with access to the recordings.

Names are matched without regard to case, spaces, underscores or hyphens, so
`Jane Doe`, `jane_doe` and `jane-doe` are the same person. Matching is on the
whole name: listing `Jane` does not silence `Jane Doe`.

Kestrel refuses to start on a blank entry in the list, which otherwise matches
nobody and leaves someone you believed was ignored still being reported.

:::warning

Listing `unknown` is accepted and means "do not tell me about strangers". On a
camera that gates access that is almost certainly a mistake -- it suppresses
exactly the faces worth knowing about.

:::

## Usage

Follow these steps to begin:

1. **Enable face recognition** in your configuration and restart Kestrel.
2. **Upload one face** using the **Add Face** button's wizard in the Face Library section of the Kestrel UI. Read below for the best practices on expanding your training set.
3. When Kestrel detects and attempts to recognize a face, it will appear in the **Train** tab of the Face Library, along with its associated recognition confidence.
4. From the **Train** tab, you can **assign the face** to a new or existing person to improve recognition accuracy for the future.

## Creating a Robust Training Set

:::tip

**The short version:** Start with a few clear, front-facing photos of each person. As faces are detected in the Recent Recognitions tab, train clear images that scored lower, adding variety (different angles, lighting, and expressions) slowly. Diversity matters far more than volume, and low-quality images hurt recognition more than they help.

For a step-by-step narrative of these best practices (and the same principles applied to state and object classification), see the [Kestrel Tips: Best Practices for Training](https://github.com/blakeblackshear/frigate/discussions/21374) discussion.

:::

The number of images needed for a sufficient training set for face recognition varies depending on several factors:

- Diversity of the dataset: A dataset with diverse images, including variations in lighting, pose, and facial expressions, will require fewer images per person than a less diverse dataset.
- Desired accuracy: The higher the desired accuracy, the more images are typically needed.

However, here are some general guidelines:

- Minimum: For basic face recognition tasks, a minimum of 5-10 images per person is often recommended.
- Recommended: For more robust and accurate systems, 20-30 images per person is a good starting point.
- Ideal: For optimal performance, especially in challenging conditions, 50-100 images per person can be beneficial.

The accuracy of face recognition is heavily dependent on the quality of data given to it for training. It is recommended to build the face training library in phases.

:::tip

When choosing images to include in the face training set it is recommended to always follow these recommendations:

- If it is difficult to make out details in a persons face it will not be helpful in training.
- Avoid images with extreme under/over-exposure.
- Avoid blurry / pixelated images.
- Avoid training on infrared (gray-scale). The models are trained on color images and will not be able to extract features from gray-scale images.
- Using images of people wearing hats / sunglasses may confuse the model.
- Do not upload too many similar images at the same time, it is recommended to train no more than 4-6 similar images for each person to avoid over-fitting.

:::

### Understanding the Recent Recognitions Tab

The Recent Recognitions tab in the face library displays recent face recognition attempts. Detected face images are grouped according to the person they were identified as potentially matching.

Each face image is labeled with a name (or `Unknown`) along with the confidence score of that recognition attempt. Images are grouped by the person they were matched against, not by who they actually are, so a group labeled with a person's name can contain a crop that is really someone else but happened to score as a partial match. The name and score shown on each individual crop describe that single attempt.

While each image can be used to train the system for a specific person, not all images are suitable for training. Refer to the guidelines below for best practices on selecting images for training.

### How Kestrel Decides Who a Person Is

Recognition does not happen one frame at a time. While a `person` is in view, Kestrel runs face recognition on many frames, not just a single frame. The final `sub_label` is decided from all of those attempts together, weighted by the area of each face (larger, closer faces count more), not from any single frame.

This has a few practical consequences:

- A handful of wrong guesses on blurry or distant frames usually do not change the result. If Kestrel sees a person as "Tom, Tom, Sam, Tom, Tom," it will still conclude the person was Tom.
- The goal is not for every individual face crop to be correct. The goal is for each person to be recognized correctly overall, across all the faces captured while they were present.
- A single very high confidence match will not by itself assign a sub label. Recognition must be consistent. See [I see scores above the threshold in the Recent Recognitions tab, but a sub label wasn't assigned?](#i-see-scores-above-the-threshold-in-the-recent-recognitions-tab-but-a-sub-label-wasnt-assigned) below.

### Which Faces Are Worth Training?

Whether a face is worth training has little to do with what it was recognized as. A crop is a good training candidate when all of these are true:

- It did not already score high and correctly. Faces that are already recognized confidently add little and increase the risk of over-fitting.
- It is clear enough to be useful: not blurry, not heavily off-axis, not infrared (gray-scale). If it is hard for you to make out the face, it will not help the model.
- It adds something new: a different angle, lighting, expression, or distance than what you already have.

### Step 1 - Building a Strong Foundation

When first enabling face recognition it is important to build a foundation of strong images. It is recommended to start by uploading 1-5 photos containing just this person's face. It is important that the person's face in the photo is front-facing and not turned, this will ensure a good starting point.

Then it is recommended to use the `Face Library` tab in Kestrel to select and train images for each person as they are detected. When building a strong foundation it is strongly recommended to only train on images that are front-facing. Ignore images from cameras that recognize faces from an angle. Aim to strike a balance between the quality of images while also having a range of conditions (day / night, different weather conditions, different times of day, etc.) in order to have diversity in the images used for each person and not have over-fitting.

You do not want to train images that are 90%+ as these are already being confidently recognized. In this step the goal is to train on clear, lower scoring front-facing images until the majority of front-facing images for a given person are consistently recognized correctly. Then it is time to move on to step 2.

### Step 2 - Expanding The Dataset

Once front-facing images are performing well, start choosing slightly off-angle images to include for training. It is important to still choose images where enough face detail is visible to recognize someone, and you still only want to train on images that score lower.

## FAQ

### Getting Recognition Working

<FaqItem id="how-do-i-debug-face-recognition-issues" question="How do I debug Face Recognition issues?">

Start with the [Usage](#usage) section and re-read the [Model Requirements](#model-requirements) above.

1. Enable debug logs to see exactly what Kestrel is doing.
   - Enable debug logs for face recognition by adding `frigate.data_processing.real_time.face: debug` to your `logger` configuration. Restart Kestrel after this change.

     ```yaml
     logger:
       default: info
       logs:
         # highlight-next-line
         frigate.data_processing.real_time.face: debug
     ```

   - These logs report where the pipeline stopped for each `person` object, such as no face being found within the person's bounding box, the detected face being smaller than `min_area`, or a face being recognized but scoring too low.
   - If you see no face-related messages at all, also add `frigate.embeddings.maintainer: debug` to confirm that the face processor was created at startup and that `person` updates are reaching it.

2. Ensure `person` is being _detected_. A `person` will automatically be scanned by Kestrel for a face. Any detected faces will appear in the Recent Recognitions tab in the Kestrel UI's Face Library.

   If you are using a Frigate+ or `face` detecting model:
   - Watch the [debug view](/usage/live#the-single-camera-view) to ensure that `face` is being detected along with `person`.
   - You may need to adjust the `min_score` for the `face` object if faces are not being detected.

   If you are **not** using a Frigate+ or `face` detecting model:
   - Check your `detect` stream resolution and ensure it is sufficiently high enough to capture face details on `person` objects.
   - You may need to lower your `detection_threshold` if faces are not being detected.

3. Any detected faces will then be _recognized_.
   - Make sure you have trained at least one face per the recommendations above.
   - Adjust `recognition_threshold` settings per the suggestions [above](#advanced-configuration).

</FaqItem>

<FaqItem id="does-face-recognition-run-on-the-recording-stream" question="Does face recognition run on the recording stream?">

Face recognition does not run on the recording stream, this would be suboptimal for many reasons:

1. The latency of accessing the recordings means the notifications would not include the names of recognized people because recognition would not complete until after.
2. The embedding models used run on a set image size, so larger images will be scaled down to match this anyway.
3. Motion clarity is much more important than extra pixels, over-compression and motion blur are much more detrimental to results than resolution.

</FaqItem>

### Improving Accuracy and Training

<FaqItem id="detection-does-not-work-well-with-blurry-images" question="Detection does not work well with blurry images?">

Accuracy is definitely going to be improved with higher quality cameras / streams. It is important to look at the DORI (Detection Observation Recognition Identification) range of your camera, if that specification is posted. This specification explains the distance from the camera that a person can be detected, observed, recognized, and identified. The identification range is the most relevant here, and the distance listed by the camera is the furthest that face recognition will realistically work.

Some users have also noted that setting the stream in camera firmware to a constant bit rate (CBR) leads to better image clarity than with a variable bit rate (VBR).

</FaqItem>

<FaqItem id="can-i-train-faces-for-people-who-only-appear-at-night" question="Can I train faces for people who only appear at night?">

The embedding models are trained on color images, so gray-scale and infrared (IR) faces sit in a different feature distribution and are more easily confused with other people. Prefer color images, and avoid mixing gray-scale samples in early while you are building a foundation. If someone only ever appears at night, gray-scale training is acceptable, but keep those samples limited and as clear as possible, and add them only once color recognition is stable for your other people.

</FaqItem>

<FaqItem id="why-cant-i-bulk-upload-photos" question="Why can't I bulk upload photos?">

It is important to methodically add photos to the library, bulk importing photos (especially from a general photo library) will lead to over-fitting in that particular scenario and hurt recognition performance.

</FaqItem>

<FaqItem id="why-cant-i-bulk-reprocess-faces" question="Why can't I bulk reprocess faces?">

Face embedding models work by breaking apart faces into different features. This means that when reprocessing an image, only images from a similar angle will have its score affected.

</FaqItem>

<FaqItem id="why-do-unknown-people-score-similarly-to-known-people" question="Why do unknown people score similarly to known people?">

This can happen for a few different reasons, but this is usually an indicator that the training set needs to be improved. This is often related to over-fitting:

- If you train with only a few images per person, especially if those images are very similar, the recognition model becomes overly specialized to those specific images.
- When you provide images with different poses, lighting, and expressions, the algorithm extracts features that are consistent across those variations.
- By training on a diverse set of images, the algorithm becomes less sensitive to minor variations and noise in the input image.

Review your face collections and remove most of the unclear or low-quality images. Then, use the **Reprocess** button on each face in the **Train** tab to evaluate how the changes affect recognition scores.

Avoid training on images that already score highly, as this can lead to over-fitting. Instead, focus on relatively clear images that score lower (ideally with different lighting, angles, and conditions) to help the model generalize more effectively.

</FaqItem>

<FaqItem id="should-i-correct-a-face-that-was-recognized-as-the-wrong-person" question="Should I correct a face that was recognized as the wrong person?">

Only if it is a good image. Reassigning a face does add it to that person's training set, but two things are true at once:

- Reassigning a single misclassified frame has a small effect. The image is weighted against every other sample for that person, so correcting 1 frame out of 20 will not move recognition much. Occasional wrong guesses on poor frames are normal and do not need to be fixed.
- Reassigning a poor image (blurry, off-angle, low-resolution, gray-scale) can hurt more than the misidentification did, because low-quality samples degrade recognition for that whole person.

So the decision is about image quality, not about the wrong label. If the crop is clear, well-lit, and reasonably front-facing, and it scored low or was wrong, assigning it to the correct person is useful. If you can barely make out the face yourself, ignore it; do not train it just to correct the label.

If a person is repeatedly misidentified, do not keep reassigning the same frame. Instead, remove low-quality or misleading images and add a few high-quality samples to the correct person. See [Why do unknown people score similarly to known people?](#why-do-unknown-people-score-similarly-to-known-people) above.

</FaqItem>

<FaqItem id="frigate-misidentified-a-face-can-i-tell-it-that-a-face-is-not-a-specific-person" question={'Kestrel misidentified a face. Can I tell it that a face is "not" a specific person?'}>

No, face recognition does not support negative training (i.e., explicitly telling it who someone is _not_). Instead, the best approach is to improve the training data by using a more diverse and representative set of images for each person.
For more guidance, refer to the section above on improving recognition accuracy.

This also applies to a stranger who is repeatedly matched to a known person (for example, a delivery driver recognized as you). Do not create a profile for them and do not reassign their faces to yourself, as this pollutes your training set and makes recognition worse. Leave the detection as unknown and improve the known person's training set instead. Face recognition learns who someone is, not who they are not.

</FaqItem>

<FaqItem id="i-see-scores-above-the-threshold-in-the-recent-recognitions-tab-but-a-sub-label-wasnt-assigned" question="I see scores above the threshold in the Recent Recognitions tab, but a sub label wasn't assigned?">

Kestrel considers the recognition scores across all recognition attempts for each person object. The scores are continually weighted based on the area of the face, and a sub label will only be assigned to person if a person is confidently recognized consistently. This avoids cases where a single high confidence recognition would throw off the results.

</FaqItem>

### Compatibility and Maintenance

<FaqItem id="can-i-use-other-face-recognition-software-like-doubletake-at-the-same-time-as-the-built-in-face-recognition" question="Can I use other face recognition software like DoubleTake at the same time as the built in face recognition?">

No, using another face recognition service will interfere with Kestrel's built in face recognition. When using double-take the sub_label feature must be disabled if the built in face recognition is also desired.

</FaqItem>

<FaqItem id="i-get-an-unknown-error-when-taking-a-photo-directly-with-my-iphone" question="I get an unknown error when taking a photo directly with my iPhone">

By default iOS devices will use HEIC (High Efficiency Image Container) for images, but this format is not supported for uploads. Choosing `large` as the format instead of `original` will use JPG which will work correctly.

</FaqItem>

<FaqItem id="how-can-i-delete-the-face-database-and-start-over" question="How can I delete the face database and start over?">

Kestrel does not store anything in its database related to face recognition. You can simply delete all of your faces through the Kestrel UI or remove the contents of the `/media/frigate/clips/faces` directory.

</FaqItem>
