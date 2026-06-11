"""Map Sentinel-1 GRD pixel coordinates to geographic lon/lat.

A Sentinel-1 Level-1 GRD product is delivered in radar (range/azimuth)
geometry — the measurement GeoTIFF carries no CRS or affine geotransform.
Geolocation instead comes from the `geolocationGrid` in the product's
annotation XML: a coarse lattice of (line, pixel) -> (latitude, longitude)
ground-control points sampled across the scene.

This module parses that grid and interpolates it (Delaunay-based linear
interpolation over the scattered GCP lattice), so a CFAR detection at an
arbitrary (row, col) pixel can be assigned a real lon/lat.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.interpolate import LinearNDInterpolator

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GridPoint:
    line: int
    pixel: int
    lat: float
    lon: float
    height: float


class Geocoder:
    """Interpolates the S1 geolocation grid: (row, col) pixel -> (lon, lat).

    `height` (the terrain elevation the geolocation used) is also exposed —
    over open water it sits at the geoid (~0 m), so it doubles as a coarse
    land hint independent of any external coastline dataset.
    """

    def __init__(self, points: list[GridPoint]):
        if len(points) < 3:
            raise ValueError(f"need >=3 geolocation grid points, got {len(points)}")
        self.points = points
        rc = np.array([(p.line, p.pixel) for p in points], dtype=np.float64)
        self._lon = LinearNDInterpolator(rc, np.array([p.lon for p in points]))
        self._lat = LinearNDInterpolator(rc, np.array([p.lat for p in points]))
        self._height = LinearNDInterpolator(rc, np.array([p.height for p in points]))

    @classmethod
    def from_annotation(cls, xml_path: str | Path) -> Geocoder:
        """Build a Geocoder from a Sentinel-1 annotation XML file."""
        xml_path = Path(xml_path)
        root = ET.parse(str(xml_path)).getroot()
        plist = root.find(".//geolocationGrid/geolocationGridPointList")
        if plist is None:
            raise ValueError(f"no geolocationGrid in {xml_path.name}")
        pts: list[GridPoint] = []
        for p in plist.findall("geolocationGridPoint"):
            pts.append(
                GridPoint(
                    line=int(p.findtext("line", "0")),
                    pixel=int(p.findtext("pixel", "0")),
                    lat=float(p.findtext("latitude", "nan")),
                    lon=float(p.findtext("longitude", "nan")),
                    height=float(p.findtext("height", "nan")),
                )
            )
        log.info("loaded %d geolocation grid points from %s", len(pts), xml_path.name)
        return cls(pts)

    def lonlat(self, row: float, col: float) -> tuple[float, float]:
        """Geocode a single (row, col) pixel to (lon, lat)."""
        return float(self._lon(row, col)), float(self._lat(row, col))

    def lonlat_many(
        self, rows: np.ndarray, cols: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Geocode many pixels at once. Returns (lon[], lat[])."""
        rows = np.asarray(rows, dtype=np.float64)
        cols = np.asarray(cols, dtype=np.float64)
        return self._lon(rows, cols), self._lat(rows, cols)

    def height_many(self, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
        """Interpolated terrain height (m) at each pixel."""
        rows = np.asarray(rows, dtype=np.float64)
        cols = np.asarray(cols, dtype=np.float64)
        return self._height(rows, cols)


def find_annotation(tif_path: str | Path) -> Path | None:
    """Locate the annotation XML that pairs with a S1 measurement GeoTIFF.

    Inside an unpacked .SAFE the measurement tiff lives at
    `<SAFE>/measurement/<stem>.tiff` and its annotation at
    `<SAFE>/annotation/<stem>.xml`. Returns None if no sibling is found.
    """
    tif_path = Path(tif_path)
    stem = tif_path.stem
    candidates = [
        tif_path.parent.parent / "annotation" / f"{stem}.xml",
        tif_path.with_suffix(".xml"),
        tif_path.parent / f"{stem}.xml",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None
