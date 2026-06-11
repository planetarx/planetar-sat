"""Land-mask filtering tests."""
from __future__ import annotations

import numpy as np

from planetar_sat.detect.landmask import is_land


def test_open_ocean_is_water():
    # Mid-Pacific and mid-Atlantic — unambiguously open water.
    res = is_land(np.array([0.0, 30.0]), np.array([-140.0, -40.0]))
    assert res.tolist() == [False, False]


def test_continental_interior_is_land():
    # Central Australia and central Asia — unambiguously land.
    res = is_land(np.array([-25.0, 45.0]), np.array([133.0, 90.0]))
    assert res.tolist() == [True, True]


def test_mixed_batch():
    lats = np.array([0.0, -25.0])
    lons = np.array([-140.0, 133.0])
    assert is_land(lats, lons).tolist() == [False, True]


def test_nonfinite_coords_reported_not_land():
    # A geocoding failure must not silently drop a detection as "on shore".
    res = is_land(np.array([np.nan, 1.0]), np.array([2.0, np.nan]))
    assert res.tolist() == [False, False]


def test_returns_bool_array_of_matching_shape():
    res = is_land(np.zeros(5), np.full(5, -150.0))
    assert res.shape == (5,)
    assert res.dtype == bool
