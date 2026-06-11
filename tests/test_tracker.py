"""Tracker behaviour tests."""
from __future__ import annotations

from planetar_sat.detect.chip import GeoDetection
from planetar_sat.track.tracker import Tracker


def _det(lat: float, lon: float, t_ns: int) -> GeoDetection:
    return GeoDetection(
        scene_id="test",
        lat=lat,
        lon=lon,
        snr=10.0,
        bbox_px=(0, 0, 1, 1),
        acquired_at_ns=t_ns,
    )


def test_new_detection_creates_track():
    tr = Tracker(max_match_m=2000.0)
    out = tr.step([_det(48.5, -123.5, 1_000_000_000)])
    assert len(out) == 1
    assert out[0].n_hits == 1
    assert len(tr.tracks) == 1


def test_close_detections_extend_same_track():
    tr = Tracker(max_match_m=2000.0)
    tr.step([_det(48.5, -123.5, 1_000_000_000)])
    out = tr.step([_det(48.501, -123.499, 2_000_000_000)])  # ~120 m away
    assert len(out) == 1
    assert out[0].n_hits == 2
    assert out[0].speed_kn > 0


def test_far_detection_creates_new_track():
    tr = Tracker(max_match_m=500.0)
    tr.step([_det(48.5, -123.5, 1_000_000_000)])
    out = tr.step([_det(48.6, -123.6, 2_000_000_000)])  # ~13 km away
    assert len(out) == 1
    assert len(tr.tracks) == 2  # original + new


def test_stale_tracks_pruned():
    tr = Tracker(max_match_m=2000.0, max_age_s=1.0)
    tr.step([_det(48.5, -123.5, 1_000_000_000)])
    # Detection far in the future to age out the first track.
    tr.step([_det(48.7, -123.7, 10_000_000_000)])
    assert all(t.last_seen_ns >= 10_000_000_000 for t in tr.tracks.values())
