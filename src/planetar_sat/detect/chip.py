"""SAR scene → detection batch.

Wraps the CFAR detector with rasterio I/O: opens a Sentinel-1 GRD GeoTIFF,
runs CFAR over the VV pol, geo-references each detection to lon/lat, and
drops any that land on shore.

Geo-referencing has two paths:
  - the raster carries a CRS + affine transform — use it directly;
  - the raster is in radar geometry with no CRS (the usual case for a
    Sentinel-1 GRD measurement tiff) — fall back to the geolocation grid in
    the sibling annotation XML (see `geocode.py`).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from planetar_sat.detect.cfar import cfar_ca
from planetar_sat.detect.geocode import Geocoder, find_annotation
from planetar_sat.detect.landmask import is_land

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeoDetection:
    scene_id: str
    lat: float
    lon: float
    snr: float
    bbox_px: tuple[int, int, int, int]
    acquired_at_ns: int


def detect_scene(
    tif_path: Path,
    scene_id: str,
    acquired_at_ns: int,
    cfar_kwargs: dict | None = None,
    annotation_path: Path | None = None,
    mask_land: bool = True,
) -> list[GeoDetection]:
    """Run CFAR on a single VV GRD GeoTIFF and return geo-referenced detections.

    Args:
        tif_path:        VV-polarization Sentinel-1 GRD GeoTIFF.
        scene_id:        stable scene identifier, stamped on every detection.
        acquired_at_ns:  scene acquisition time (ns), stamped on every detection.
        cfar_kwargs:     extra args forwarded to `cfar_ca`.
        annotation_path: S1 annotation XML for the geolocation grid. If omitted
                         and the raster has no CRS, a sibling XML is looked up.
        mask_land:       drop detections that geocode onto land (default True).
    """
    import rasterio
    from rasterio.transform import xy

    with rasterio.open(tif_path) as ds:
        band = ds.read(1).astype(np.float32)
        transform = ds.transform
        crs = ds.crs

    dets = cfar_ca(band, **(cfar_kwargs or {}))
    if not dets:
        log.info("scene %s: 0 detections", scene_id)
        return []

    rows = np.array([d.row for d in dets], dtype=np.float64)
    cols = np.array([d.col for d in dets], dtype=np.float64)

    # --- geo-referencing ---
    if crs is not None:
        xs, ys = xy(transform, rows, cols)
        xs, ys = np.asarray(xs, dtype=np.float64), np.asarray(ys, dtype=np.float64)
        if crs.to_epsg() != 4326:
            from rasterio.warp import transform as warp_transform

            xs, ys = warp_transform(crs, "EPSG:4326", xs.tolist(), ys.tolist())
            xs, ys = np.asarray(xs), np.asarray(ys)
        lons, lats = xs, ys
    else:
        ann = annotation_path or find_annotation(tif_path)
        if ann is None:
            raise RuntimeError(
                f"{Path(tif_path).name} has no CRS and no sibling annotation "
                "XML — cannot geo-reference detections. Pass annotation_path "
                "with the Sentinel-1 geolocation-grid XML."
            )
        geocoder = Geocoder.from_annotation(ann)
        lons, lats = geocoder.lonlat_many(rows, cols)

    # --- land masking ---
    on_land = is_land(lats, lons) if mask_land else np.zeros(len(dets), dtype=bool)

    geo_dets: list[GeoDetection] = []
    for d, lat, lon, land in zip(dets, lats, lons, on_land, strict=True):
        if land:
            continue
        geo_dets.append(
            GeoDetection(
                scene_id=scene_id,
                lat=float(lat),
                lon=float(lon),
                snr=d.snr,
                bbox_px=d.bbox,
                acquired_at_ns=acquired_at_ns,
            )
        )
    n_land = int(on_land.sum())
    if n_land:
        log.info("scene %s: dropped %d land detections", scene_id, n_land)
    log.info("scene %s: %d geo-detections", scene_id, len(geo_dets))
    return geo_dets
