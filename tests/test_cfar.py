"""CFAR detector sanity tests on synthetic SAR-like imagery."""
from __future__ import annotations

import numpy as np

from planetar_sat.detect.cfar import cfar_ca


def _synthetic_scene(h: int = 80, w: int = 80, seed: int = 0) -> np.ndarray:
    """Background speckle + a few bright 'ship' blobs."""
    rng = np.random.default_rng(seed)
    img = rng.exponential(scale=0.1, size=(h, w)).astype(np.float32)
    # Inject three "ships": small bright patches.
    for r, c in [(20, 20), (50, 50), (60, 15)]:
        img[r - 1 : r + 2, c - 1 : c + 2] += 5.0
    return img


def test_cfar_finds_injected_targets():
    img = _synthetic_scene()
    dets = cfar_ca(img, guard=2, train=8, pfa_factor=3.0, min_pixels=1)
    assert len(dets) >= 3
    rows = {d.row for d in dets}
    cols = {d.col for d in dets}
    # Each injected target's center should match one of the detection peaks
    # within a couple of pixels (CFAR picks the brightest cell, not necessarily
    # the geometric centre).
    for r, c in [(20, 20), (50, 50), (60, 15)]:
        assert any(abs(d.row - r) <= 1 and abs(d.col - c) <= 1 for d in dets), (r, c)


def test_cfar_empty_on_flat_image():
    img = np.full((40, 40), 0.05, dtype=np.float32)
    dets = cfar_ca(img, guard=2, train=6, pfa_factor=3.0, min_pixels=1)
    assert dets == []


def test_cfar_snr_is_positive_and_finite():
    img = _synthetic_scene()
    dets = cfar_ca(img, guard=2, train=8, pfa_factor=3.0, min_pixels=1)
    for d in dets:
        assert d.snr > 1.0
        assert np.isfinite(d.snr)
