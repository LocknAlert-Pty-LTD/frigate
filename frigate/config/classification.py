import re
from enum import Enum

from pydantic import ConfigDict, Field, field_validator

from .base import FrigateBaseModel

__all__ = [
    "AudioTranscriptionModelEnum",
    "CameraFaceRecognitionConfig",
    "CameraLicensePlateRecognitionConfig",
    "CameraAudioTranscriptionConfig",
    "FaceLivenessConfig",
    "FaceRecognitionConfig",
    "SemanticSearchConfig",
    "CameraSemanticSearchConfig",
    "LicensePlateRecognitionConfig",
    "ParkPowConfig",
]


class SemanticSearchModelEnum(str, Enum):
    jinav1 = "jinav1"
    jinav2 = "jinav2"


class AudioTranscriptionModelEnum(str, Enum):
    whisper = "whisper"


class EnrichmentsDeviceEnum(str, Enum):
    GPU = "GPU"
    CPU = "CPU"


class ModelSizeEnum(str, Enum):
    small = "small"
    large = "large"


class TriggerType(str, Enum):
    THUMBNAIL = "thumbnail"
    DESCRIPTION = "description"


class TriggerAction(str, Enum):
    NOTIFICATION = "notification"
    SUB_LABEL = "sub_label"
    ATTRIBUTE = "attribute"


class ObjectClassificationType(str, Enum):
    sub_label = "sub_label"
    attribute = "attribute"


class AudioTranscriptionConfig(FrigateBaseModel):
    enabled: bool = Field(
        default=False,
        title="Enable audio transcription",
        description="Enable or disable automatic audio transcription for all cameras; can be overridden per-camera.",
    )
    language: str = Field(
        default="auto",
        title="Transcription language",
        description="Language code used for transcription/translation (for example 'en' for English), or 'auto' to let the model detect it. See https://whisper-api.com/docs/languages/ for supported language codes.",
    )
    model: AudioTranscriptionModelEnum | str | None = Field(
        default=AudioTranscriptionModelEnum.whisper,
        title="Audio transcription model or GenAI provider name",
        description="The transcription backend: 'whisper' for Kestrel's built-in local models, or the name of a GenAI provider with the transcribe role.",
    )

    @field_validator("model", mode="before")
    @classmethod
    def coerce_model_enum(cls, v):
        # An absent value ("model:" with nothing after it, or an explicit null)
        # means unspecified, so fall back to the built-in backend. Left as None
        # it would pass the GenAI-provider validation, which only inspects
        # strings, and then be treated as a provider name that resolves to no
        # client, turning transcription into a silent no-op.
        if v is None or (isinstance(v, str) and not v.strip()):
            return AudioTranscriptionModelEnum.whisper

        if isinstance(v, str):
            try:
                return AudioTranscriptionModelEnum(v)
            except ValueError:
                return v

        return v

    device: EnrichmentsDeviceEnum = Field(
        default=EnrichmentsDeviceEnum.CPU,
        title="Transcription device",
        description="Device key (CPU/GPU) to run the transcription model on. Only NVIDIA CUDA GPUs are currently supported for transcription.",
    )
    model_size: ModelSizeEnum = Field(
        default=ModelSizeEnum.small,
        title="Model size",
        description="Model size to use for offline audio event transcription.",
    )
    live_enabled: bool | None = Field(
        default=False,
        title="Live transcription",
        description="Enable streaming live transcription for audio as it is received.",
    )


class BirdClassificationConfig(FrigateBaseModel):
    enabled: bool = Field(
        default=False,
        title="Bird classification",
        description="Enable or disable bird classification.",
    )
    threshold: float = Field(
        default=0.9,
        title="Minimum score",
        description="Minimum classification score required to accept a bird classification.",
        gt=0.0,
        le=1.0,
    )


class CustomClassificationStateCameraConfig(FrigateBaseModel):
    crop: list[float, float, float, float] = Field(
        title="Classification crop",
        description="Crop coordinates to use for running classification on this camera.",
    )


class CustomClassificationStateConfig(FrigateBaseModel):
    cameras: dict[str, CustomClassificationStateCameraConfig] = Field(
        title="Classification cameras",
        description="Per-camera crop and settings for running state classification.",
    )
    motion: bool = Field(
        default=False,
        title="Run on motion",
        description="If true, run classification when motion is detected within the specified crop.",
    )
    interval: int | None = Field(
        default=None,
        title="Classification interval",
        description="Interval (seconds) between periodic classification runs for state classification.",
        gt=0,
    )


class CustomClassificationObjectConfig(FrigateBaseModel):
    objects: list[str] = Field(
        default_factory=list,
        title="Classify objects",
        description="List of object types to run object classification on.",
    )
    classification_type: ObjectClassificationType = Field(
        default=ObjectClassificationType.sub_label,
        title="Classification type",
        description="Classification type applied: 'sub_label' (adds sub_label) or other supported types.",
    )


class CustomClassificationConfig(FrigateBaseModel):
    enabled: bool = Field(
        default=True,
        title="Enable model",
        description="Enable or disable the custom classification model.",
    )
    name: str | None = Field(
        default=None,
        title="Model name",
        description="Identifier for the custom classification model to use.",
    )
    threshold: float = Field(
        default=0.8,
        title="Score threshold",
        description="Score threshold used to change the classification state.",
    )
    save_attempts: int | None = Field(
        default=None,
        title="Save attempts",
        description="How many classification attempts to save for recent classifications UI.",
        ge=0,
    )
    object_config: CustomClassificationObjectConfig | None = Field(default=None)
    state_config: CustomClassificationStateConfig | None = Field(default=None)


class ClassificationConfig(FrigateBaseModel):
    bird: BirdClassificationConfig = Field(
        default_factory=BirdClassificationConfig,
        title="Bird classification config",
        description="Settings specific to bird classification models.",
    )
    custom: dict[str, CustomClassificationConfig] = Field(
        default={},
        title="Custom Classification Models",
        description="Configuration for custom classification models used for objects or state detection.",
    )


class SemanticSearchConfig(FrigateBaseModel):
    enabled: bool = Field(
        default=False,
        title="Enable semantic search",
        description="Enable or disable the semantic search feature.",
    )
    reindex: bool | None = Field(
        default=False,
        title="Reindex on startup",
        description="Trigger a full reindex of historical tracked objects into the embeddings database.",
    )
    model: SemanticSearchModelEnum | str | None = Field(
        default=SemanticSearchModelEnum.jinav1,
        title="Semantic search model or GenAI provider name",
        description="The embeddings model to use for semantic search (for example 'jinav1'), or the name of a GenAI provider with the embeddings role.",
    )

    @field_validator("model", mode="before")
    @classmethod
    def coerce_model_enum(cls, v):
        if isinstance(v, str):
            try:
                return SemanticSearchModelEnum(v)
            except ValueError:
                return v
        return v

    model_size: ModelSizeEnum = Field(
        default=ModelSizeEnum.small,
        title="Model size",
        description="Select model size; 'small' runs on CPU and 'large' typically requires GPU.",
    )
    device: str | None = Field(
        default=None,
        title="Device",
        description="This is an override, to target a specific device. See https://onnxruntime.ai/docs/execution-providers/ for more information",
    )


class TriggerConfig(FrigateBaseModel):
    friendly_name: str | None = Field(
        None,
        title="Friendly name",
        description="Optional friendly name displayed in the UI for this trigger.",
    )
    enabled: bool = Field(
        default=True,
        title="Enable this trigger",
        description="Enable or disable this semantic search trigger.",
    )
    type: TriggerType = Field(
        default=TriggerType.DESCRIPTION,
        title="Trigger type",
        description="Type of trigger: 'thumbnail' (match against image) or 'description' (match against text).",
    )
    data: str = Field(
        title="Trigger content",
        description="Text phrase or thumbnail ID to match against tracked objects.",
    )
    threshold: float = Field(
        title="Trigger threshold",
        description="Minimum similarity score (0-1) required to activate this trigger.",
        default=0.8,
        gt=0.0,
        le=1.0,
    )
    actions: list[TriggerAction] = Field(
        default=[],
        title="Trigger actions",
        description="List of actions to execute when trigger matches (notification, sub_label, attribute).",
    )

    model_config = ConfigDict(extra="forbid", protected_namespaces=())


class CameraSemanticSearchConfig(FrigateBaseModel):
    triggers: dict[str, TriggerConfig] = Field(
        default={},
        title="Triggers",
        description="Actions and matching criteria for camera-specific semantic search triggers.",
    )

    model_config = ConfigDict(extra="forbid", protected_namespaces=())


def _normalize_face_name(name: str) -> str:
    """Fold the spellings of one person onto a single key."""
    return name.strip().casefold().replace("_", " ").replace("-", " ")


class FaceLivenessConfig(FrigateBaseModel):
    """Whether a recognised face belongs to someone actually present.

    Recognition alone cannot tell a person from a photograph of them, so these
    checks look for what a photograph cannot supply: parallax as the head turns,
    and blinking. See docs/docs/configuration/face_recognition.md for the
    measurements behind the defaults, and for what this does and does not stop.

    The thresholds are in the units the analyzer logs, so enable debug logging
    for frigate.data_processing.common.face.liveness, hold a photo up to the
    camera, then walk past it yourself, and set them from what you see.
    """

    enabled: bool = Field(
        default=True,
        title="Require liveness",
        description="Withhold a recognised name unless the face is shown to belong to someone present. Disabling this means a printed photo or a phone screen will be recognised exactly like a real face.",
    )
    min_frames: int = Field(
        default=3,
        ge=2,
        le=30,
        title="Minimum frames",
        description="Frames of one person needed before liveness can be decided. Three is the minimum that can measure anything: two give the landmark noise floor and the third is measured against it.",
    )
    depth_growth_threshold: float = Field(
        default=0.008,
        ge=0.0,
        le=1.0,
        title="Depth threshold",
        description="How much a flat surface must fail to explain the face's motion, above the track's own noise floor, before the face counts as solid. A real face turning 20 degrees measures 0.014 to 0.029; a photo measures 0.000 to 0.003. Raise it to demand clearer proof at the cost of more refusals.",
    )
    deformation_threshold: float = Field(
        default=0.11,
        ge=0.0,
        le=1.0,
        title="Blink threshold",
        description="How much the eyes or mouth must open or close, relative to the distance between the eyes, to count as a working face. A real blink or spoken word measures 0.12 to 0.15. Accepts a motionless person without needing them to turn.",
    )
    min_viewpoint: float = Field(
        default=0.04,
        ge=0.0,
        le=1.0,
        title="Minimum viewpoint change",
        description="How much the view must change before a failure to show depth is treated as proof of a flat surface rather than as too little information. Only affects which reason is logged; both withhold the name.",
    )
    max_noise_floor: float = Field(
        default=0.05,
        gt=0.0,
        le=1.0,
        title="Maximum landmark noise",
        description="Refuse to judge at all once a face's own landmark jitter reaches this, because a real face and a photo stop being distinguishable. Small, dim or motion-blurred faces are what exceed it. Raising it does not improve detection; it only allows guesses.",
    )
    appearance_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        title="Appearance threshold",
        description="Below this score for looking like a direct view rather than a reproduction, a face is rejected outright. Detects a screen's pixel grid or a printer's halftone; a high-resolution screen at the right distance leaves no trace, so this is a backstop rather than the main defence.",
    )
    model_config = ConfigDict(extra="forbid", protected_namespaces=())


class FaceRecognitionConfig(FrigateBaseModel):
    enabled: bool = Field(
        default=False,
        title="Enable face recognition",
        description="Enable or disable face recognition for all cameras; can be overridden per-camera.",
    )
    model_size: ModelSizeEnum = Field(
        default=ModelSizeEnum.large,
        title="Model size",
        description="Model size to use for face embeddings. 'large' is ArcFace, 'small' is FaceNet. ArcFace separates faces considerably better and is the default because recognition here can gate access; drop to 'small' only if inference cost forces it.",
    )
    unknown_score: float = Field(
        title="Unknown score threshold",
        description="Distance threshold below which a face is considered a potential match (higher = stricter).",
        default=0.8,
        gt=0.0,
        le=1.0,
    )
    detection_threshold: float = Field(
        default=0.7,
        title="Detection threshold",
        description="Minimum detection confidence required to consider a face detection valid.",
        gt=0.0,
        le=1.0,
    )
    recognition_threshold: float = Field(
        default=0.9,
        title="Recognition threshold",
        description="Face embedding distance threshold to consider two faces a match.",
        gt=0.0,
        le=1.0,
    )
    min_area: int = Field(
        default=750,
        title="Minimum face area",
        description="Minimum area (pixels) of a detected face box required to attempt recognition.",
    )
    min_faces: int = Field(
        default=1,
        gt=0,
        le=6,
        title="Minimum faces",
        description="Minimum number of face recognitions required before applying a recognized sub-label to a person.",
    )
    save_attempts: int = Field(
        default=400,
        ge=0,
        title="Save attempts",
        description="Number of recent face recognition attempts to retain for review in the UI. Each is a small JPEG crop, so raising this costs little disk.",
    )
    blur_confidence_filter: bool = Field(
        default=True,
        title="Blur confidence filter",
        description="Adjust confidence scores based on image blur to reduce false positives for poor quality faces.",
    )
    min_blur_variance: int = Field(
        default=120,
        ge=0,
        title="Minimum sharpness",
        description="Reject faces whose Laplacian variance is below this, instead of only lowering their score. 0 disables the check. Raise it to demand sharper faces, lower it if faces are being dropped.",
    )
    recognition_margin: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        title="Recognition margin",
        description="How far ahead the best matching person must be of the runner-up, in cosine similarity, before a match is accepted. Guards against confusing similar-looking people. 0 disables the check.",
    )
    knn_top_k: int = Field(
        default=3,
        ge=1,
        le=25,
        title="Neighbours per person",
        description="Score each enrolled person by the average of their this-many most similar training images, rather than against a single averaged face. Higher tolerates more varied enrolment photos.",
    )
    ignored_faces: list[str] = Field(
        default_factory=list,
        title="Do not recognize",
        description="Names that are never reported, even when recognized. The face stays enrolled and is still matched internally, but no name reaches events, MQTT or notifications and no attempt image is kept. For people who live or work somewhere and do not want to be tracked by it. Matched without regard to case, spaces, underscores or hyphens.",
    )

    @field_validator("ignored_faces")
    @classmethod
    def reject_blank_names(cls, value: list[str]) -> list[str]:
        """A blank entry would silently match nothing.

        Easy to leave behind when editing the list in YAML, and the only symptom
        would be that someone the operator believed was ignored is still being
        reported.
        """
        for name in value:
            if not name or not name.strip():
                raise ValueError(
                    "face_recognition.ignored_faces contains a blank name"
                )

        return value

    def is_ignored(self, name: str | None) -> bool:
        """Whether a recognized name must not be reported.

        Compared on a normalized form so the list matches what people type.
        Enrolled names come from directory names under the face library, where
        "Jane Doe", "jane_doe" and "jane-doe" are three different folders but one
        person to whoever writes the config.
        """
        if not name:
            return False

        return _normalize_face_name(name) in {
            _normalize_face_name(ignored) for ignored in self.ignored_faces
        }

    liveness: FaceLivenessConfig = Field(
        default_factory=FaceLivenessConfig,
        title="Liveness",
        description="Checks that a recognised face belongs to someone actually present rather than to a photo of them.",
    )
    device: str | None = Field(
        default=None,
        title="Device",
        description="This is an override, to target a specific device. See https://onnxruntime.ai/docs/execution-providers/ for more information",
    )


class CameraFaceRecognitionConfig(FrigateBaseModel):
    enabled: bool = Field(
        default=False,
        title="Enable face recognition",
        description="Enable or disable face recognition.",
    )
    min_area: int = Field(
        default=750,
        title="Minimum face area",
        description="Minimum area (pixels) of a detected face box required to attempt recognition.",
    )

    model_config = ConfigDict(extra="forbid", protected_namespaces=())


class ReplaceRule(FrigateBaseModel):
    pattern: str = Field(..., title="Regex pattern")
    replacement: str = Field(..., title="Replacement string")


class ParkPowConfig(FrigateBaseModel):
    enabled: bool = Field(
        default=False,
        title="Enable ParkPow integration",
        description="Send recognized license plates to a ParkPow instance.",
    )
    host: str = Field(
        default="https://app.parkpow.com",
        title="ParkPow host",
        description="Base URL of the ParkPow instance (cloud or on-premise) to send recognized plates to.",
    )
    token: str | None = Field(
        default=None,
        title="ParkPow API token",
        description="API token used to authenticate with ParkPow, available at https://app.parkpow.com/account/token/.",
    )
    timeout: float = Field(
        default=10.0,
        title="Request timeout",
        description="Timeout in seconds for requests sent to ParkPow.",
        gt=0.0,
    )


class LicensePlateRecognitionConfig(FrigateBaseModel):
    enabled: bool = Field(
        default=False,
        title="Enable LPR",
        description="Enable or disable license plate recognition for all cameras; can be overridden per-camera.",
    )
    model_size: ModelSizeEnum = Field(
        default=ModelSizeEnum.small,
        title="Model size",
        description="Model size used for text detection/recognition. Most users should use 'small'.",
    )
    detection_threshold: float = Field(
        default=0.7,
        title="Detection threshold",
        description="Detection confidence threshold to begin running OCR on a suspected plate.",
        gt=0.0,
        le=1.0,
    )
    min_area: int = Field(
        default=1000,
        title="Minimum plate area",
        description="Minimum plate area (pixels) required to attempt recognition.",
    )
    recognition_threshold: float = Field(
        default=0.9,
        title="Recognition threshold",
        description="Confidence threshold required for recognized plate text to be attached as a sub-label.",
        gt=0.0,
        le=1.0,
    )
    min_plate_length: int = Field(
        default=4,
        title="Min plate length",
        description="Minimum number of characters a recognized plate must contain to be considered valid.",
    )
    format: str | None = Field(
        default=None,
        title="Plate format regex",
        description="Optional regex to validate recognized plate strings against an expected format. Rejected at startup if it is not a valid regex, since a pattern that fails to compile would otherwise disable the filter.",
    )

    @field_validator("format")
    @classmethod
    def validate_format_regex(cls, value: str | None) -> str | None:
        """Refuse a pattern that will not compile.

        Without this the error surfaced once per plate, at which point the filter
        is not doing anything -- and where LPR opens a gate, a filter that
        silently stopped filtering is the failure that matters. Better to refuse
        to start.
        """
        if value is None:
            return value

        try:
            re.compile(value)
        except re.error as err:
            raise ValueError(
                f"lpr.format is not a valid regular expression: {err}"
            ) from err

        return value

    match_distance: int = Field(
        default=1,
        title="Match distance",
        description="Number of character mismatches allowed when comparing detected plates to known plates.",
        ge=0,
    )
    known_plates: dict[str, list[str]] | None = Field(
        default={},
        title="Known plates",
        description="List of plates or regexes to specially track or alert on.",
    )
    enhancement: int = Field(
        default=0,
        title="Enhancement level",
        description="Enhancement level (0-10) to apply to plate crops prior to OCR; higher values may not always improve results, levels above 5 may only work with night time plates and should be used with caution.",
        ge=0,
        le=10,
    )
    debug_save_plates: bool = Field(
        default=False,
        title="Save debug plates",
        description="Save plate crop images for debugging LPR performance.",
    )
    device: str | None = Field(
        default=None,
        title="Device",
        description="This is an override, to target a specific device. See https://onnxruntime.ai/docs/execution-providers/ for more information",
    )
    replace_rules: list[ReplaceRule] = Field(
        default_factory=list,
        title="Replacement rules",
        description="Regex replacement rules used to normalize detected plate strings before matching.",
    )
    parkpow: ParkPowConfig = Field(
        default_factory=ParkPowConfig,
        title="ParkPow integration",
        description="Settings for sending recognized license plates to ParkPow.",
    )


class CameraLicensePlateRecognitionConfig(FrigateBaseModel):
    enabled: bool = Field(
        default=False,
        title="Enable LPR",
        description="Enable or disable LPR on this camera.",
    )
    parkpow_enabled: bool | None = Field(
        default=None,
        title="Override ParkPow reporting",
        description="Override the global ParkPow enabled setting for this camera. Unset inherits the global lpr.parkpow.enabled value.",
    )
    expire_time: int = Field(
        default=3,
        title="Expire seconds",
        description="Time in seconds after which an unseen plate is expired from the tracker (for dedicated LPR cameras only).",
        gt=0,
    )
    min_area: int = Field(
        default=1000,
        title="Minimum plate area",
        description="Minimum plate area (pixels) required to attempt recognition.",
    )
    enhancement: int = Field(
        default=0,
        title="Enhancement level",
        description="Enhancement level (0-10) to apply to plate crops prior to OCR; higher values may not always improve results, levels above 5 may only work with night time plates and should be used with caution.",
        ge=0,
        le=10,
    )

    model_config = ConfigDict(extra="forbid", protected_namespaces=())


class CameraAudioTranscriptionConfig(FrigateBaseModel):
    enabled: bool = Field(
        default=False,
        title="Enable transcription",
        description="Enable or disable manually triggered audio event transcription.",
    )
    enabled_in_config: bool | None = Field(
        default=None, title="Original transcription state"
    )
    live_enabled: bool | None = Field(
        default=False,
        title="Live transcription",
        description="Enable streaming live transcription for audio as it is received.",
    )

    model_config = ConfigDict(extra="forbid", protected_namespaces=())
