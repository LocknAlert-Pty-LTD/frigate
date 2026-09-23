"""Send recognized license plates to a ParkPow instance.

ParkPow's webhook-receiver endpoint accepts the same contract used by Plate
Recognizer Stream: a multipart POST with a `json` field describing the
detection and optional image file fields. See
https://app.parkpow.com/documentation/ and
https://guides.platerecognizer.com/docs/stream/results/ for the payload format.

Fire-and-forget like frigate/alarm/notify_whatsapp.py -- this runs on the
embeddings maintainer thread once per finished vehicle event, so a slow or
unreachable ParkPow host must never block it.
"""

import datetime
import json
import logging
import threading

import requests

from frigate.config.classification import ParkPowConfig

logger = logging.getLogger(__name__)


def send_to_parkpow(
    config: ParkPowConfig,
    camera: str,
    plate: str,
    score: float,
    timestamp: float,
    image_bytes: bytes | None,
) -> None:
    """Dispatch a recognized plate to ParkPow in a background thread."""
    if not config.enabled or not config.token:
        return

    threading.Thread(
        target=_post_to_parkpow,
        args=(config, camera, plate, score, timestamp, image_bytes),
        daemon=True,
    ).start()


def _post_to_parkpow(
    config: ParkPowConfig,
    camera: str,
    plate: str,
    score: float,
    timestamp: float,
    image_bytes: bytes | None,
) -> None:
    url = f"{config.host.rstrip('/')}/api/v1/webhook-receiver/"
    headers = {"Authorization": f"Token {config.token}"}
    payload = {
        "data": {
            "results": [{"plate": plate, "score": score}],
            "camera_id": camera,
            "timestamp": datetime.datetime.fromtimestamp(
                timestamp, tz=datetime.timezone.utc
            ).isoformat(),
        }
    }
    files = {"upload": ("snapshot.jpg", image_bytes, "image/jpeg")} if image_bytes else None

    try:
        response = requests.post(
            url,
            headers=headers,
            data={"json": json.dumps(payload)},
            files=files,
            timeout=config.timeout,
        )
        if response.status_code >= 400:
            logger.warning(
                "ParkPow webhook for %s plate '%s' failed with status %s",
                camera,
                plate,
                response.status_code,
            )
    except requests.RequestException as e:
        logger.warning("ParkPow webhook for %s plate '%s' failed: %s", camera, plate, e)
