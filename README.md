# planetar-sat

Satellite imagery → AI boat detection → tracking microservice.

Fetches Sentinel-1 SAR scenes from Copernicus Data Space, runs a CFAR-based ship
detector over them, tracks detections across passes, and publishes results to
`planetar-broker` as native `zmesg` envelopes.

Built for the CH13 v2 proposal flagship demo (dark-vessel detection over the
Salish Sea) and for the `zdefence` v1 project.

## Layout

```
planetar-sat/
├── src/planetar_sat/
│   ├── fetch/        # Copernicus Data Space (CDSE) Sentinel-1 GRD fetcher
│   ├── detect/       # CFAR detector + geolocation-grid geocoder + land mask
│   ├── track/        # IoU multi-target tracker (persistent IDs)
│   ├── bus/          # zmesg encoder + TCP publisher to planetar-broker
│   ├── cli.py        # `planetar-sat fetch|detect|run|replay`
│   └── config.py
├── tests/
└── docs/
```

## Quickstart

```bash
make install                            # pip install -e .[dev] into .venv
export CDSE_USERNAME=…                  # Copernicus Data Space credentials
export CDSE_PASSWORD=…

# live (last N days)
.venv/bin/planetar-sat run --aoi salish-sea --days 3

# historical date range
.venv/bin/planetar-sat run --aoi salish-sea --start 2024-08-15 --end 2024-08-22

# pure replay from cached scenes (no CDSE auth needed — great for demos)
.venv/bin/planetar-sat replay data/scenes/*.tif --acquired-at 2024-08-15T14:02:00Z
```

The `run` and `replay` subcommands chain fetch → detect → track → publish,
emitting THREE envelope types:

- `sar.chip` — per-detection machine envelope
- `track.update` — per-tracked-vessel machine envelope
- `chat.pac.sar-detections` — human-readable chat line, picked up by the
  `#sar-detections` channel in the running planetar-ui (which subscribes
  via `chatTopic()` → `chat.<server>.<channel>`)

Historical-replay mode stamps `created_at_ns` to the scene's acquisition
time so the UI renders messages at the right wall-clock — not as "now."

## Bus topics

| Topic         | Schema                                                                | Emitted by         |
|---------------|-----------------------------------------------------------------------|--------------------|
| `sar.chip`    | JSON: `{scene_id, lat, lon, snr, bbox_px, acquired_at_ns}`            | `detect/cfar.py`   |
| `track.update`| JSON: `{track_id, lat, lon, speed_kn, course_deg, last_seen_ns, ...}` | `track/tracker.py` |

Wire framing matches the broker: 4-byte **big-endian** (network byte order)
length prefix, then a `zmesg` envelope (see `src/planetar_sat/bus/zmesg.py` —
pure-Python mirror of `~/github/sness23/zmesg/zmesg.h`).

## Geo-referencing & land masking

A Sentinel-1 GRD measurement GeoTIFF is delivered in radar (range/azimuth)
geometry — it carries **no CRS**. `detect/geocode.py` recovers real
coordinates by interpolating the geolocation grid in the product's
annotation XML (a lattice of line/pixel → lat/lon ground-control points).
For a loose tiff, pass `--annotation <s1-annotation>.xml`.

CFAR is a ship-vs-water detector and floods with false alarms over land, so
detections that geocode onto land are dropped (`detect/landmask.py`, backed
by `global_land_mask`). Pass `--no-land-mask` to keep them — useful for
synthetic test scenes and debugging.

## Datasets in scope (CH13 1a)

- **Sentinel-1 GRD** (live ingress, free via CDSE) — **implemented**
- **xView3** — labeled-evaluation backbone (dark-vessel ground truth, Sentinel-1 + co-located AIS)
- **MarineCadastre AIS / Danish DMA / Global Fishing Watch** — historical AIS for `ais.gap` correlation
- **Alaska Satellite Facility** — US Sentinel-1 mirror + pre-Sentinel SAR archive (ERS-1/2, ALOS PALSAR)

See [`docs/DATA-SOURCES.md`](docs/DATA-SOURCES.md) for concrete URLs, auth
patterns, archive depth, and how each one lands on the bus.

See `~/github/planetarx/planetar/05-DATASETS.md` for the full modality list
across all five sensor lanes.

## Status

v0.2 — working detector pipeline (no fake numbers).

- **CFAR** cell-averaging detector (summed-area-table) with a scipy-vectorized
  connected-component labeller — a 16-Mpx window runs in seconds.
- **Geo-referencing** via the Sentinel-1 geolocation grid (radar-geometry
  products have no CRS).
- **Land masking** drops CFAR's land false alarms. Validated on a real
  Sentinel-1C scene: a land window collapsed 1582 → 28 detections; an
  open-water window kept all 19.

Honest limitations: `detect_scene` reads the whole band, so a full 433-Mpx
GRD scene exceeds memory — tiled reads are the next step. The 1-arcmin land
mask is coarse near complex shorelines; a full-resolution coastline (GSHHG)
is the production upgrade. The chip-classifier head (xView3 port) is still a
follow-on.

## Licensing

Licensed under **AGPL-3.0** (see [`LICENSE`](LICENSE)). **Commercial licenses**
(for use without AGPL obligations) are available — contact `sness@sness.net`.
