# Data sources for planetar-sat

Every source listed here is **free, programmatic, and has a public archive**
deep enough to do historical replay. No commercial-only feeds, no ITAR-
restricted data, no GFP-only material — matches CH13 CFP §3.5.4.

Each source has:

- **Auth** — what credentials you need (most are free registration).
- **Archive depth** — how far back the historical data goes.
- **Access** — concrete API or bulk-download path.
- **Bus topic** — where it lands when ingested into planetar.

---

## Tier 1 — already wired (Sentinel-1 SAR)

### Copernicus Data Space Ecosystem (CDSE)

The European Space Agency's portal for all Sentinel missions. This is what
`fetch/copernicus.py` already uses.

| Attribute | Value |
|---|---|
| **Auth** | Free registration at https://dataspace.copernicus.eu/ — sets `CDSE_USERNAME` / `CDSE_PASSWORD`. OAuth2 password grant against Keycloak. |
| **Archive depth** | Sentinel-1A from **2014-10-03** onward; Sentinel-1B 2016-09-25 to 2021-12-23 (mission ended). Continuous global coverage at ~6-day revisit per platform. |
| **Access** | OData catalogue at `https://catalogue.dataspace.copernicus.eu/odata/v1`. Download at `https://download.dataspace.copernicus.eu/odata/v1/Products({id})/$value` with Bearer token. |
| **Bus topic** | `sar.chip` (per detection) + `chat.pac.sar-detections` (human-readable). |
| **Status** | **Implemented.** `planetar-sat fetch --aoi … --start … --end …` works against arbitrary date ranges back to 2014. |

### Alaska Satellite Facility (ASF)

US mirror of Sentinel-1 with the same archive, plus Sentinel-1 Burst products
and analysis-ready RTC. Useful as a CDSE fallback if European servers are
slow or rate-limit on a busy day.

| Attribute | Value |
|---|---|
| **Auth** | Free Earthdata Login at https://urs.earthdata.nasa.gov/. Then download via `asf_search` Python library or direct HTTPS. |
| **Archive depth** | Same as CDSE — 2014 onward, plus pre-Sentinel ERS-1/2 (1991-2011) and ALOS PALSAR (2006-2011) historical SAR if we ever need pre-Sentinel comparison data. |
| **Access** | `pip install asf-search`; `asf_search.geo_search(platform="S1", intersectsWith=wkt, start=date, end=date)`. |
| **Bus topic** | Same as CDSE (`sar.chip`). |
| **Status** | Documented; not wired. One file would suffice (`fetch/asf.py`) — same interface as `copernicus.py`. |

---

## Tier 2 — high-value labeled / curated datasets

### xView3 dark-vessel dataset (DIU)

**This is the proposal's labeled-evaluation backbone.** Sentinel-1 scenes
with co-located AIS, and per-pixel labels for "this detection is a vessel
that was/wasn't broadcasting AIS at acquisition time" — the literal
ground truth for dark-vessel detection.

| Attribute | Value |
|---|---|
| **Auth** | Free registration at https://iuu.xview.us/. |
| **Archive depth** | ~1,000 Sentinel-1 GRD scenes drawn from 2017-2020 over five high-traffic regions (Indonesia, Southeast Asia, southern Africa, Pacific, North Atlantic). ~250k labeled vessel detections. |
| **Access** | S3 bucket (presigned URL after login). Annotations as CSV; SAR chips as compressed GeoTIFF stacks. |
| **Bus topic** | `sar.chip` (with extra `xview3_label` field for ground truth) + `chat.pac.sar-detections`. The labeled scenes also let us emit a `sar.chip.eval` evaluation envelope when running benchmark passes. |
| **Status** | Documented. Loader belongs in `fetch/xview3.py` — different shape (zipped chip stack, CSV labels) so it's its own module. |

### SAR-Ship-Dataset, HRSID, SSDD, FUSAR-Ship

Smaller chip-level datasets useful for training the chip classifier (the
follow-on to v0.1 CFAR baseline). All freely downloadable, all hosted on
GitHub or institutional pages.

| Attribute | Value |
|---|---|
| **Auth** | None. |
| **Access** | GitHub releases / dataset pages: see `~/github/planetarx/planetar/05-DATASETS.md` for canonical URLs. |
| **Bus topic** | Training-time only — these don't ingest live; they back the classifier weights that `detect/chip.py` will load. |

---

## Tier 3 — AIS (correlation, not detection)

Every dark-vessel demo needs AIS data alongside the SAR detections, so the
detector can say "this radar return has no AIS broadcast." AIS lives on the
`ais.update` / `ais.gap` bus topics — owned by a sibling service
(`planetar-ais`, already exists at `~/github/planetarx/planetar-ais/`), so
this list documents the feeds but the ingest code is not in `planetar-sat`.

### MarineCadastre.gov (NOAA)

| Attribute | Value |
|---|---|
| **Auth** | None. |
| **Archive depth** | US coastal AIS, 2009 onward, by year and UTM zone. |
| **Access** | Bulk ZIP downloads — `https://coast.noaa.gov/htdata/CMSP/AISDataHandler/<year>/AIS_<year>_<month>_Zone<zone>.zip`. CSV format. |
| **Bus topic** | `ais.update` (per position), `ais.gap` (gap-detected). |

### Danish Maritime Authority (DMA)

| Attribute | Value |
|---|---|
| **Auth** | None. |
| **Archive depth** | European waters, 2006 onward, daily CSVs. |
| **Access** | `https://web.ais.dk/aisdata/aisdk-<YYYY>-<MM>-<DD>.zip`. |
| **Bus topic** | Same as MarineCadastre. |

### Global Fishing Watch (GFW)

| Attribute | Value |
|---|---|
| **Auth** | Free API key after research-use registration at https://globalfishingwatch.org/. |
| **Archive depth** | 2012 onward, but the ML-classified fishing-behavior + dark-event annotations are the value-add — not raw AIS. |
| **Access** | REST API at `https://gateway.api.globalfishingwatch.org/v2/`. |
| **Bus topic** | `ais.gap` (curated dark events with ground truth). |

### AISStream.io (live, free)

| Attribute | Value |
|---|---|
| **Auth** | Free registration → API key. |
| **Archive depth** | **Live only**, no archive. |
| **Access** | WebSocket at `wss://stream.aisstream.io/v0/stream` with JSON filter. |
| **Bus topic** | `ais.update`. |

---

## Tier 4 — optical EO (Sentinel-2, future)

When clouds permit, EO confirms SAR detections visually. Same CDSE
infrastructure as Sentinel-1 — only the collection name and product type
differ. Mentioned here for the broader `planetar-eo` sibling; not in this
service's scope.

| Attribute | Value |
|---|---|
| **Auth** | Same CDSE creds. |
| **Archive depth** | 2015-06 onward, ~5-day revisit. |
| **Access** | `Collection/Name eq 'SENTINEL-2'`, `productType` in `S2MSI1C`/`S2MSI2A`. |
| **Bus topic** | `eo.chip` (separate sibling service). |

---

## Historical replay strategy

The proposal's flagship demo is a **dark-vessel scenario over the Salish
Sea**. Two replay modes are useful for that:

**Mode 1 — recent live (last N days):**
```bash
planetar-sat run --aoi salish-sea --days 7
```
Picks up whatever Sentinel-1 has acquired in the last week. Good for
"is the pipeline alive" sanity, not for guaranteed-interesting events.

**Mode 2 — specific historical date range (with known busy traffic):**
```bash
planetar-sat run --aoi salish-sea --start 2024-08-15 --end 2024-08-22
```
Locks the AOI to a date window known to contain heavy shipping. Good for
deterministic demo runs and for comparison against AIS archives from
MarineCadastre / GFW for the same window.

**Mode 3 — pure replay from cache:**
```bash
planetar-sat replay --scenes data/scenes/*.tif --rate 2
```
Loads already-downloaded scenes, re-runs detect + track, and republishes
to the bus with **the scene's original acquisition timestamp** in the
envelope's `created_at_ns`. The UI will see them as historical events,
not as "now" — important for the dark-vessel demo where the SAR pass
predates the AIS gap by minutes.

Mode 3 is what we run for the planetar-ui demo: no CDSE auth needed, no
network calls, just the bus + the cached scenes. See `planetar-sat replay
--help` (added in this commit).

---

## Concrete demo data we can stage today

Two known-busy Salish Sea Sentinel-1 acquisition windows that are good for
the v2 demo:

| Window | Approx. footprint | Why it's interesting |
|---|---|---|
| 2024-08-15 to 2024-08-22 | Strait of Juan de Fuca + Haro Strait | Cruise-ship season peak; commercial traffic dense; AIS coverage well-archived in MarineCadastre Zone 10. |
| 2023-12-01 to 2023-12-15 | Same | Winter storm window — useful adversarial case for CFAR (high sea state → high clutter → false alarm tradeoffs). |

Both windows are available right now from CDSE (no special access). The
download budget is ~5-8 scenes × ~1 GB each = ~5-8 GB per window; cache
locally and you never need to re-download.
