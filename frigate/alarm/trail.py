"""Cross-camera "also seen" lookup for an alarm-triggering detection.

Glue layer (like event_log.py / ha_discovery.py) allowed to import
frigate.models and frigate.embeddings directly; frigate/alarm/system.py
stays DB-free by design, so this correlation logic lives here instead.

Combines two signals Frigate already computes elsewhere, nothing new:
- an exact Event.sub_label match ("named" match) -- free once
  face_recognition is enabled and a face was matched to a known person, no
  vector search involved.
- EmbeddingsContext.search_thumbnail's existing cross-camera k-NN cosine
  similarity search ("visual" match) -- the fallback for unidentified
  people, only available when semantic_search is enabled (embeddings is
  not None).
"""

from dataclasses import dataclass
from typing import Literal

from frigate.embeddings import EmbeddingsContext
from frigate.models import Event

DEFAULT_WINDOW_SECONDS = 120
MAX_RESULTS = 10
# search_thumbnail returns cosine distance (0 = identical, 2 = opposite).
# Untuned heuristic cutoff -- no way to validate against real embeddings/
# photos in this sandbox; adjust once live-verified.
VISUAL_MATCH_MAX_DISTANCE = 0.5


@dataclass
class TrailMatch:
    camera: str
    event_id: str
    timestamp: float
    thumbnail: str
    match_type: Literal["named", "visual"]
    label: str | None = None
    score: float | None = None


def find_trail(
    object_id: str,
    embeddings: EmbeddingsContext | None,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
) -> list[TrailMatch]:
    """Find other cameras that likely saw the same person around the same
    time as the given (already-persisted) tracked-object/event id."""
    trigger = Event.get_or_none(Event.id == object_id)
    if trigger is None:
        return []

    window_start = trigger.start_time - window_seconds
    window_end = trigger.start_time + window_seconds

    matches: dict[str, TrailMatch] = {}

    if trigger.sub_label and trigger.sub_label != "unknown":
        named = Event.select().where(
            Event.sub_label == trigger.sub_label,
            Event.camera != trigger.camera,
            Event.start_time.between(window_start, window_end),
        )
        for event in named:
            matches[event.id] = TrailMatch(
                camera=event.camera,
                event_id=event.id,
                timestamp=event.start_time,
                thumbnail=event.thumbnail,
                match_type="named",
                label=event.sub_label,
            )

    if embeddings is not None:
        candidate_ids = [
            row[0]
            for row in Event.select(Event.id)
            .where(
                Event.camera != trigger.camera,
                Event.start_time.between(window_start, window_end),
            )
            .tuples()
            if row[0] not in matches
        ]

        if candidate_ids:
            candidate_id_set = set(candidate_ids)
            for event_id, distance in embeddings.search_thumbnail(
                trigger, event_ids=candidate_ids
            ):
                # search_thumbnail's event_ids filter is documented (see
                # frigate/embeddings/__init__.py) as unreliable on the
                # currently pinned sqlite-vec version -- re-check
                # membership here rather than trusting the SQL filter.
                if (
                    event_id not in candidate_id_set
                    or event_id in matches
                    or distance > VISUAL_MATCH_MAX_DISTANCE
                ):
                    continue

                event = Event.get_or_none(Event.id == event_id)
                if event is None:
                    continue

                matches[event_id] = TrailMatch(
                    camera=event.camera,
                    event_id=event.id,
                    timestamp=event.start_time,
                    thumbnail=event.thumbnail,
                    match_type="visual",
                    score=distance,
                )

    return sorted(matches.values(), key=lambda m: m.timestamp)[:MAX_RESULTS]
