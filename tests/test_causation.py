"""Distributed-tracing wiring through _publish_scene_results.

Every track.update must carry `causation_id` = the envelope id (dashed-UUID
string) of the sar.chip that extended that track, while `correlation_id`
stays the track id. The per-track chat line announces that same chip.
"""
from __future__ import annotations

import json

from planetar_sat.bus.zmesg import Envelope, parse, uuid_str
from planetar_sat.cli import _publish_scene_results
from planetar_sat.detect.chip import GeoDetection
from planetar_sat.track.tracker import Tracker


class FakePublisher:
    """Captures envelopes instead of shipping them to the broker."""

    def __init__(self) -> None:
        self.published: list[Envelope] = []

    def publish(self, env: Envelope) -> int:
        self.published.append(env)
        return len(env.serialize()) + 4

    def by_topic(self, topic: str) -> list[Envelope]:
        return [e for e in self.published if e.topic == topic]


def _det(lat: float, lon: float, t_ns: int) -> GeoDetection:
    return GeoDetection(
        scene_id="test",
        lat=lat,
        lon=lon,
        snr=12.0,
        bbox_px=(0, 0, 4, 4),
        acquired_at_ns=t_ns,
    )


def test_track_update_causation_is_chip_envelope_id():
    pub = FakePublisher()
    _publish_scene_results(pub, "scene-a", [_det(48.5, -123.5, 1_000_000_000)],
                           Tracker(), "sar-detections")

    (chip,) = pub.by_topic("sar.chip")
    (track,) = pub.by_topic("track.update")
    assert track.causation_id == uuid_str(chip.id)
    assert track.correlation_id == json.loads(track.payload)["track_id"]
    # chips are roots of the SAR chain — no causation
    assert chip.causation_id == ""
    # and the wiring survives serialization
    assert parse(track.serialize()).causation_id == uuid_str(chip.id)


def test_new_track_chat_line_announces_the_chip():
    pub = FakePublisher()
    _publish_scene_results(pub, "scene-a", [_det(48.5, -123.5, 1_000_000_000)],
                           Tracker(), "sar-detections")

    (chip,) = pub.by_topic("sar.chip")
    chats = pub.by_topic("chat.pac.sar-detections")
    # scene summary line stays causation-free (announces N chips, not one)
    summary, track_chat = chats
    assert summary.causation_id == ""
    assert track_chat.causation_id == uuid_str(chip.id)


def test_extended_track_points_at_newest_chip():
    tracker = Tracker()
    first = FakePublisher()
    _publish_scene_results(first, "scene-a", [_det(48.5, -123.5, 1_000_000_000)],
                           tracker, "sar-detections")
    second = FakePublisher()
    _publish_scene_results(second, "scene-b", [_det(48.501, -123.499, 2_000_000_000)],
                           tracker, "sar-detections")

    (chip2,) = second.by_topic("sar.chip")
    (track2,) = second.by_topic("track.update")
    assert json.loads(track2.payload)["n_hits"] == 2
    assert track2.causation_id == uuid_str(chip2.id)
    # not the first scene's chip
    (chip1,) = first.by_topic("sar.chip")
    assert track2.causation_id != uuid_str(chip1.id)
