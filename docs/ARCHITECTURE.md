# planetar-sat — architecture

```
                 ┌──────────────────────────┐
                 │ Copernicus Data Space    │
                 │ (Sentinel-1 GRD, free)   │
                 └────────────┬─────────────┘
                              │ OData query + auth'd download
                              ▼
   ┌────────────────────────────────────────────────────────┐
   │  fetch/copernicus.py                                   │
   │   • token refresh against CDSE Keycloak                │
   │   • OData $filter on AOI ∩ S1 GRD ∩ date window        │
   │   • streamed .SAFE.zip download with resume-safe rename│
   └────────────────────────────┬───────────────────────────┘
                                │
                                ▼
   ┌────────────────────────────────────────────────────────┐
   │  detect/cfar.py + detect/chip.py                       │
   │   • cell-averaging CFAR via summed-area table          │
   │   • connected-component blob extraction                │
   │   • pixel→lat/lon reprojection (rasterio)              │
   │   → list[GeoDetection]                                 │
   └────────────────────────────┬───────────────────────────┘
                                │
                                ▼
   ┌────────────────────────────────────────────────────────┐
   │  track/tracker.py                                      │
   │   • greedy nearest-neighbor in haversine metres        │
   │   • persistent UUIDv4 track IDs, age-out on stale      │
   │   • speed_kn + course_deg from last two fixes          │
   │   → list[Track]                                        │
   └────────────────────────────┬───────────────────────────┘
                                │
                                ▼
   ┌────────────────────────────────────────────────────────┐
   │  bus/zmesg.py + bus/publisher.py                       │
   │   • Envelope.serialize() — bit-exact mirror of zmesg.h │
   │   • TCP framing: [u32 LE length][envelope bytes]       │
   │   • Topics: sar.chip, track.update                     │
   └────────────────────────────┬───────────────────────────┘
                                │
                                ▼
                ┌──────────────────────────┐
                │  planetar-broker         │
                │  127.0.0.1:12001 (PUB)   │
                │  → WAL → 12002 (SUB) →   │
                │     planetar-ui, etc.    │
                └──────────────────────────┘
```

## Where it fits in the proposal architecture

This service implements the SAR ingress + `sar.chip` detector from the
5-layer reference architecture in
`~/github/planetarx/planetar/03-ARCHITECTURE.md`. The five layers:

1. **Envelope** — `zmesg` (this service ships its own pure-Python encoder)
2. **Bus** — `planetar-broker` (this service is a producer)
3. **Detectors** — the CFAR detector here is one of the five (others: `ais.gap`,
   `eo.chip`, `acoustic.event`, `rf.emit`)
4. **Entity graph** — downstream consumer (not in this service)
5. **Shell** — `planetar-ui` (not in this service)

The dark-vessel demo (proposal flagship) is the cross-modal correlation of
`sar.chip` from this service against `ais.gap` from another producer — both
emitted as envelopes on the same bus.

## Conservative claims

- **CFAR is a baseline.** The proposal's `sar.chip` detector is described as
  a "CFAR + chip-classifier baseline ported from the public xView3 reference
  implementations, not a frontier model." This service ships the CFAR half;
  the classifier head is a follow-on commit. Don't advertise frontier-model
  numbers from a CFAR-only run.
- **No fake outputs.** When extraction of a .SAFE archive isn't staged, the
  `run` subcommand logs a warning and skips the scene rather than emitting
  synthetic detections.

## Future work (out of scope for v0.1)

- `.SAFE/manifest.safe` parsing for true `acquired_at_ns` and orbit metadata
- chip-classifier head trained on xView3 (per `05-DATASETS.md`)
- AIS correlation: receive `ais.gap` on the SUB port and emit
  `track.update.with_ais` envelopes
- Sentinel-2 EO ingest (separate `eo.chip` topic; reuses bus + tracker)
