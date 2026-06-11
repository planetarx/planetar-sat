"""Simple multi-target tracker over geo-referenced detections.

Strategy: greedy nearest-neighbor matching in lat/lon space, with track-age
bookkeeping. Distance threshold is set in meters using a flat-earth
approximation (good enough up to ~100 km at maritime latitudes).

This is the v0 tracker — intentionally simple. The proposal's M3 milestone
(see ~/github/planetarx/planetar/07-TIMELINE.md) covers an upgraded tracker
that fuses AIS, hydrophone, and EO modalities through the entity-graph layer.
"""
from __future__ import annotations

import logging
import math
import time
import uuid
from dataclasses import dataclass, field

from planetar_sat.detect.chip import GeoDetection

log = logging.getLogger(__name__)


@dataclass
class Track:
    track_id: str
    lat: float
    lon: float
    last_seen_ns: int
    n_hits: int = 1
    speed_kn: float = 0.0
    course_deg: float = 0.0
    history: list[tuple[int, float, float]] = field(default_factory=list)


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in metres between (lat, lon) pairs."""
    R = 6_371_000.0
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _bearing_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


class Tracker:
    """Greedy nearest-neighbor tracker on geo-detections."""

    def __init__(self, max_match_m: float = 2000.0, max_age_s: float = 6 * 3600.0):
        self.max_match_m = max_match_m
        self.max_age_ns = int(max_age_s * 1e9)
        self.tracks: dict[str, Track] = {}

    def step(self, detections: list[GeoDetection]) -> list[Track]:
        """Match detections to existing tracks (or spawn new), prune stale. Returns updated tracks."""
        now_ns = max((d.acquired_at_ns for d in detections), default=time.time_ns())
        updated: list[Track] = []
        unmatched: list[GeoDetection] = []

        # Greedy: for each detection, find the closest unmatched track within threshold.
        available = dict(self.tracks)
        for d in detections:
            best_id, best_dist = None, math.inf
            for tid, t in available.items():
                dist = _haversine_m((t.lat, t.lon), (d.lat, d.lon))
                if dist < best_dist and dist <= self.max_match_m:
                    best_id, best_dist = tid, dist
            if best_id is None:
                unmatched.append(d)
                continue
            t = available.pop(best_id)
            updated.append(self._extend(t, d))

        # Unmatched detections become new tracks.
        for d in unmatched:
            tid = str(uuid.uuid4())
            t = Track(
                track_id=tid,
                lat=d.lat,
                lon=d.lon,
                last_seen_ns=d.acquired_at_ns,
                history=[(d.acquired_at_ns, d.lat, d.lon)],
            )
            self.tracks[tid] = t
            updated.append(t)

        # Age out tracks not seen recently.
        stale = [tid for tid, t in self.tracks.items() if now_ns - t.last_seen_ns > self.max_age_ns]
        for tid in stale:
            del self.tracks[tid]
        if stale:
            log.info("pruned %d stale tracks", len(stale))

        return updated

    def _extend(self, t: Track, d: GeoDetection) -> Track:
        dist_m = _haversine_m((t.lat, t.lon), (d.lat, d.lon))
        dt_s = max((d.acquired_at_ns - t.last_seen_ns) / 1e9, 1e-6)
        speed_ms = dist_m / dt_s
        t.speed_kn = speed_ms * 1.943844  # m/s → knots
        t.course_deg = _bearing_deg((t.lat, t.lon), (d.lat, d.lon))
        t.lat, t.lon = d.lat, d.lon
        t.last_seen_ns = d.acquired_at_ns
        t.n_hits += 1
        t.history.append((d.acquired_at_ns, d.lat, d.lon))
        return t
