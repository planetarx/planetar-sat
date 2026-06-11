"""Geolocation-grid geocoder tests."""
from __future__ import annotations

import pytest

from planetar_sat.detect.geocode import Geocoder, GridPoint, find_annotation


def _linear_grid() -> list[GridPoint]:
    """3x3 lattice with lat linear in line, lon linear in pixel.

    A linear field is reproduced exactly by linear interpolation, so geocoded
    values are predictable: lat = 48.0 + line*0.001, lon = -124.0 + pixel*0.001.
    """
    pts: list[GridPoint] = []
    for line in (0, 100, 200):
        for pixel in (0, 100, 200):
            pts.append(
                GridPoint(
                    line=line,
                    pixel=pixel,
                    lat=48.0 + line * 0.001,
                    lon=-124.0 + pixel * 0.001,
                    height=0.0,
                )
            )
    return pts


def test_geocoder_at_grid_points():
    g = Geocoder(_linear_grid())
    lon, lat = g.lonlat(100, 200)
    assert lat == pytest.approx(48.1)
    assert lon == pytest.approx(-123.8)


def test_geocoder_interpolates_interior():
    g = Geocoder(_linear_grid())
    lon, lat = g.lonlat(50, 50)
    assert lat == pytest.approx(48.05)
    assert lon == pytest.approx(-123.95)
    lon, lat = g.lonlat(150, 75)
    assert lat == pytest.approx(48.15)
    assert lon == pytest.approx(-123.925)


def test_geocoder_many_is_vectorized():
    g = Geocoder(_linear_grid())
    lons, lats = g.lonlat_many([0, 100, 200], [0, 100, 200])
    assert list(lats) == pytest.approx([48.0, 48.1, 48.2])
    assert list(lons) == pytest.approx([-124.0, -123.9, -123.8])


def test_geocoder_rejects_too_few_points():
    with pytest.raises(ValueError, match="grid points"):
        Geocoder([GridPoint(0, 0, 48.0, -124.0, 0.0)])


_SAMPLE_XML = """<product><geolocationGrid><geolocationGridPointList count="4">
<geolocationGridPoint><line>0</line><pixel>0</pixel>
<latitude>48.0</latitude><longitude>-124.0</longitude><height>0.1</height></geolocationGridPoint>
<geolocationGridPoint><line>0</line><pixel>100</pixel>
<latitude>48.0</latitude><longitude>-123.9</longitude><height>0.2</height></geolocationGridPoint>
<geolocationGridPoint><line>100</line><pixel>0</pixel>
<latitude>48.1</latitude><longitude>-124.0</longitude><height>5.0</height></geolocationGridPoint>
<geolocationGridPoint><line>100</line><pixel>100</pixel>
<latitude>48.1</latitude><longitude>-123.9</longitude><height>7.0</height></geolocationGridPoint>
</geolocationGridPointList></geolocationGrid></product>"""


def test_from_annotation_parses_grid(tmp_path):
    p = tmp_path / "annotation.xml"
    p.write_text(_SAMPLE_XML)
    g = Geocoder.from_annotation(p)
    assert len(g.points) == 4
    lon, lat = g.lonlat(50, 50)
    assert lat == pytest.approx(48.05)
    assert lon == pytest.approx(-123.95)


def test_from_annotation_rejects_missing_grid(tmp_path):
    p = tmp_path / "bad.xml"
    p.write_text("<product/>")
    with pytest.raises(ValueError, match="geolocationGrid"):
        Geocoder.from_annotation(p)


def test_find_annotation_in_safe_layout(tmp_path):
    safe = tmp_path / "S1C_X.SAFE"
    (safe / "measurement").mkdir(parents=True)
    (safe / "annotation").mkdir()
    tif = safe / "measurement" / "s1c-iw-grd-vv-cog.tiff"
    tif.write_bytes(b"")
    xml = safe / "annotation" / "s1c-iw-grd-vv-cog.xml"
    xml.write_text("<product/>")
    assert find_annotation(tif) == xml


def test_find_annotation_returns_none_when_absent(tmp_path):
    tif = tmp_path / "lonely.tiff"
    tif.write_bytes(b"")
    assert find_annotation(tif) is None
