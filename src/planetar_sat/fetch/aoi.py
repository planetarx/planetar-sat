"""Area-of-interest helpers.

Maritime AOIs as (min_lon, min_lat, max_lon, max_lat) bboxes. The Salish Sea
preset is the CH13 flagship-demo region; the others are convenient for
broader-coverage validation against xView3 ground truth.
"""
from __future__ import annotations

from dataclasses import dataclass

# (min_lon, min_lat, max_lon, max_lat)
BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class AOI:
    name: str
    bbox: BBox
    description: str = ""

    def to_wkt_polygon(self) -> str:
        lo_lon, lo_lat, hi_lon, hi_lat = self.bbox
        coords = [
            (lo_lon, lo_lat),
            (hi_lon, lo_lat),
            (hi_lon, hi_lat),
            (lo_lon, hi_lat),
            (lo_lon, lo_lat),
        ]
        return "POLYGON((" + ", ".join(f"{x} {y}" for x, y in coords) + "))"


PRESETS: dict[str, AOI] = {
    "salish-sea": AOI(
        name="salish-sea",
        bbox=(-125.0, 47.5, -122.0, 50.5),
        description="Salish Sea — CH13 flagship demo region (BC/WA inland waters)",
    ),
    "strait-of-juan-de-fuca": AOI(
        name="strait-of-juan-de-fuca",
        bbox=(-125.0, 48.0, -123.0, 48.6),
        description="Strait of Juan de Fuca — high vessel traffic corridor",
    ),
    "english-channel": AOI(
        name="english-channel",
        bbox=(-1.5, 49.5, 2.0, 51.2),
        description="English Channel — heavy traffic, common SAR test region",
    ),
    "gulf-of-aden": AOI(
        name="gulf-of-aden",
        bbox=(43.0, 11.0, 51.0, 14.0),
        description="Gulf of Aden — dark-vessel hotspot",
    ),
}


def resolve(name_or_bbox: str) -> AOI:
    """Look up a preset by name, or parse 'min_lon,min_lat,max_lon,max_lat'."""
    if name_or_bbox in PRESETS:
        return PRESETS[name_or_bbox]
    parts = name_or_bbox.split(",")
    if len(parts) == 4:
        bbox = tuple(float(p) for p in parts)
        return AOI(name="custom", bbox=bbox)  # type: ignore[arg-type]
    raise ValueError(
        f"unknown AOI '{name_or_bbox}'. Known: {sorted(PRESETS)}, or pass 'min_lon,min_lat,max_lon,max_lat'."
    )
