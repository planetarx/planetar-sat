"""Land masking for SAR ship detections.

CFAR is a ship-vs-water detector. Run over land it floods with false
alarms — buildings, terrain relief and shoreline all return strongly in
SAR. A single 4096x4096 land window of a real Sentinel-1 scene produced
~1600 spurious detections in testing. Detections that geocode onto land
are therefore discarded before they reach the tracker / bus.

Backed by `global_land_mask`: a 1-arcmin (~1.8 km) global land/water grid.
That resolution is coarse for fine coastal work — a detection within ~1 km
of a complex shoreline can be mis-classified — so this is a baseline.
Production should swap in a full-resolution coastline (GSHHG full-res, or
OSM water polygons); see docs/DATA-SOURCES.md.
"""
from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)


def is_land(lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Vectorized land test for arrays of lat/lon.

    Returns a boolean array, True where the coordinate is on land. Non-finite
    coordinates are reported False (not-land) so a geocoding failure never
    silently drops a detection as if it were on shore.
    """
    from global_land_mask import globe

    lats = np.asarray(lats, dtype=np.float64)
    lons = np.asarray(lons, dtype=np.float64)
    out = np.zeros(lats.shape, dtype=bool)
    valid = np.isfinite(lats) & np.isfinite(lons)
    if valid.any():
        out[valid] = np.asarray(globe.is_land(lats[valid], lons[valid]), dtype=bool)
    return out
