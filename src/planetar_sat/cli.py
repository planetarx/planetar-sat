"""planetar-sat command-line entry point."""
from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import click

from planetar_sat.bus.chat import chat_envelope, detection_line, track_line
from planetar_sat.bus.publisher import Publisher
from planetar_sat.bus.zmesg import Envelope
from planetar_sat.config import DEFAULT_BROKER, DEFAULT_CACHE_DIR, CDSECredentials
from planetar_sat.detect.chip import GeoDetection, detect_scene
from planetar_sat.fetch.aoi import resolve
from planetar_sat.fetch.copernicus import CDSEClient
from planetar_sat.track.tracker import Tracker


def _parse_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    # Accept YYYY-MM-DD or full ISO; pin missing tz to UTC.
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _publish_scene_results(
    pub: Publisher,
    scene_id: str,
    dets: list[GeoDetection],
    tracker: Tracker,
    chat_chan: str,
    historical_ns: int | None = None,
) -> int:
    """Emit sar.chip + track.update machine envelopes AND chat.* human envelopes.

    If `historical_ns` is given, that timestamp is stamped on the chat
    envelope's `created_at_ns` so the UI renders the message at the scene's
    acquisition time rather than wall-clock now.
    """
    n = 0
    for d in dets:
        env = Envelope(
            topic="sar.chip",
            schema_name="planetar.sar.chip",
            schema_version=1,
            payload=json.dumps(asdict(d), default=str).encode("utf-8"),
        )
        if historical_ns is not None:
            env.created_at_ns = historical_ns
        pub.publish(env)
        n += 1

    summary = detection_line(scene_id, len(dets))
    pub.publish(chat_envelope(summary, channel=chat_chan, created_at_ns=historical_ns))
    n += 1

    updated = tracker.step(dets)
    for t in updated:
        payload = {
            "track_id": t.track_id,
            "lat": t.lat,
            "lon": t.lon,
            "speed_kn": t.speed_kn,
            "course_deg": t.course_deg,
            "last_seen_ns": t.last_seen_ns,
            "n_hits": t.n_hits,
        }
        env = Envelope(
            topic="track.update",
            schema_name="planetar.track.update",
            schema_version=1,
            correlation_id=t.track_id,
            payload=json.dumps(payload).encode("utf-8"),
        )
        if historical_ns is not None:
            env.created_at_ns = historical_ns
        pub.publish(env)
        n += 1
        # One chat line per *new* track (n_hits == 1) and one for every 5th
        # extension — avoid spamming the channel on every-pass updates.
        if t.n_hits == 1 or t.n_hits % 5 == 0:
            pub.publish(
                chat_envelope(
                    track_line(t.track_id, t.lat, t.lon, t.speed_kn, t.n_hits),
                    channel=chat_chan,
                    created_at_ns=historical_ns,
                )
            )
            n += 1
    return n

log = logging.getLogger("planetar_sat")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.option("-v", "--verbose", is_flag=True)
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """planetar-sat — satellite → AI → bus."""
    _setup_logging(verbose)
    ctx.ensure_object(dict)


@main.command()
@click.option("--aoi", default="salish-sea", help="preset name or 'min_lon,min_lat,max_lon,max_lat'")
@click.option("--days", default=3, type=int, help="window size if --start/--end not given")
@click.option("--start", default=None, help="ISO date or datetime (UTC) — historical window start")
@click.option("--end", default=None, help="ISO date or datetime (UTC) — historical window end")
@click.option("--max-results", default=5, type=int)
@click.option("--cache-dir", default=str(DEFAULT_CACHE_DIR), type=click.Path())
@click.option("--list-only", is_flag=True, help="only list products, do not download")
def fetch(
    aoi: str, days: int, start: str | None, end: str | None,
    max_results: int, cache_dir: str, list_only: bool,
) -> None:
    """Fetch Sentinel-1 GRD scenes for an AOI over the last N days or a date range."""
    aoi_obj = resolve(aoi)
    creds = CDSECredentials.from_env()
    client = CDSEClient(creds)
    products = client.search_grd(
        aoi_obj, days=days, max_results=max_results,
        start=_parse_iso_date(start), end=_parse_iso_date(end),
    )
    if not products:
        click.echo("no products matched")
        return
    for p in products:
        click.echo(f"{p.scene_id}  {p.sensing_start.isoformat()}  {p.content_length:>12} B")
    if list_only:
        return
    out = Path(cache_dir)
    for p in products:
        client.download(p, out)


@main.command()
@click.argument("inputs", nargs=-1, type=click.Path(exists=True))
@click.option("--guard", default=4, type=int)
@click.option("--train", default=12, type=int)
@click.option("--pfa-factor", default=3.0, type=float)
@click.option("--annotation", default=None, type=click.Path(exists=True),
              help="Sentinel-1 annotation XML for the geolocation grid — needed "
                   "when the GeoTIFF carries no CRS (radar-geometry GRD products)")
@click.option("--no-land-mask", is_flag=True,
              help="keep detections that fall on land (skip the land filter)")
def detect(inputs: tuple[str, ...], guard: int, train: int, pfa_factor: float,
           annotation: str | None, no_land_mask: bool) -> None:
    """Run CFAR over one or more SAR GeoTIFFs. Prints JSON-lines detections."""
    if not inputs:
        raise click.UsageError("provide one or more .tif paths")
    cfar_kwargs = {"guard": guard, "train": train, "pfa_factor": pfa_factor}
    for tif in inputs:
        path = Path(tif)
        # acquired_at_ns: prefer file mtime; real pipeline parses .SAFE/manifest.safe.
        acquired_ns = int(path.stat().st_mtime * 1e9)
        dets = detect_scene(
            path, scene_id=path.stem, acquired_at_ns=acquired_ns,
            cfar_kwargs=cfar_kwargs,
            annotation_path=Path(annotation) if annotation else None,
            mask_land=not no_land_mask,
        )
        for d in dets:
            click.echo(json.dumps(asdict(d), default=str))


@main.command()
@click.option("--aoi", default="salish-sea")
@click.option("--days", default=3, type=int)
@click.option("--start", default=None, help="ISO date — historical window start (UTC)")
@click.option("--end", default=None, help="ISO date — historical window end (UTC)")
@click.option("--max-results", default=3, type=int)
@click.option("--cache-dir", default=str(DEFAULT_CACHE_DIR), type=click.Path())
@click.option("--broker", default=DEFAULT_BROKER, help="host:port for planetar-broker publish port")
@click.option("--chat-channel", default="sar-detections", help="planetar-ui channel name to mirror chat lines to")
@click.option("--no-land-mask", is_flag=True,
              help="keep detections that fall on land (skip the land filter)")
def run(
    aoi: str, days: int, start: str | None, end: str | None,
    max_results: int, cache_dir: str, broker: str, chat_channel: str,
    no_land_mask: bool,
) -> None:
    """End-to-end: fetch → detect → track → publish to planetar-broker.

    Emits machine envelopes (`sar.chip`, `track.update`) AND human-readable
    chat envelopes (`chat.pac.<chat-channel>`) so detections surface in the
    running planetar-ui without any UI changes.
    """
    aoi_obj = resolve(aoi)
    creds = CDSECredentials.from_env()
    client = CDSEClient(creds)
    products = client.search_grd(
        aoi_obj, days=days, max_results=max_results,
        start=_parse_iso_date(start), end=_parse_iso_date(end),
    )
    if not products:
        click.echo("no Sentinel-1 GRD scenes returned for AOI", err=True)
        sys.exit(1)

    tracker = Tracker()
    out = Path(cache_dir)
    with Publisher.from_endpoint(broker) as pub:
        for p in products:
            client.download(p, out)
            # Real pipeline extracts the .SAFE archive and reads the VV
            # measurement GeoTIFF. Extraction lives in a separate worker so
            # bus-publish loop doesn't block on hundreds of MB of disk I/O.
            tif_candidates = sorted(out.glob(f"{p.scene_id}*vv*.tif"))
            if not tif_candidates:
                log.warning("no VV GeoTIFF staged for %s — extraction not run", p.scene_id)
                continue
            tif = tif_candidates[0]
            acquired_ns = int(p.sensing_start.timestamp() * 1e9)
            dets = detect_scene(tif, scene_id=p.scene_id, acquired_at_ns=acquired_ns,
                                mask_land=not no_land_mask)
            n_pub = _publish_scene_results(pub, p.scene_id, dets, tracker, chat_channel,
                                           historical_ns=acquired_ns)
            click.echo(f"scene {p.scene_id}: {len(dets)} dets, {n_pub} envelopes published")


@main.command()
@click.argument("scenes", nargs=-1, type=click.Path(exists=True))
@click.option("--broker", default=DEFAULT_BROKER, help="host:port for planetar-broker publish port")
@click.option("--chat-channel", default="sar-detections")
@click.option("--rate", default=0.0, type=float,
              help="seconds to sleep between scenes (0 = ship as fast as possible)")
@click.option("--acquired-at",
              help="ISO timestamp to stamp on chat.created_at_ns (overrides file mtime). "
                   "Apply to all scenes — useful for narrating a specific historical event.")
@click.option("--annotation", default=None, type=click.Path(exists=True),
              help="Sentinel-1 annotation XML for the geolocation grid — needed "
                   "when the GeoTIFF carries no CRS (radar-geometry GRD products)")
@click.option("--no-land-mask", is_flag=True,
              help="keep detections that fall on land (skip the land filter)")
def replay(scenes: tuple[str, ...], broker: str, chat_channel: str,
           rate: float, acquired_at: str | None,
           annotation: str | None, no_land_mask: bool) -> None:
    """Replay already-downloaded scenes through the bus.

    No CDSE auth needed — operates on local GeoTIFFs. Chat envelopes carry the
    scene's acquisition timestamp (from --acquired-at or file mtime) in
    `created_at_ns`, so planetar-ui renders them as historical events.

    Useful for demos, deterministic test runs, and replaying captured events
    against a fresh planetar-ui instance.
    """
    if not scenes:
        raise click.UsageError("provide one or more GeoTIFF scenes to replay")

    override_ns = (
        int(_parse_iso_date(acquired_at).timestamp() * 1e9)
        if acquired_at else None
    )
    tracker = Tracker()
    with Publisher.from_endpoint(broker) as pub:
        for tif in scenes:
            path = Path(tif)
            acquired_ns = override_ns if override_ns is not None else int(path.stat().st_mtime * 1e9)
            dets = detect_scene(path, scene_id=path.stem, acquired_at_ns=acquired_ns,
                                annotation_path=Path(annotation) if annotation else None,
                                mask_land=not no_land_mask)
            n_pub = _publish_scene_results(pub, path.stem, dets, tracker, chat_channel,
                                           historical_ns=acquired_ns)
            click.echo(f"replay {path.stem}: {len(dets)} dets, {n_pub} envelopes")
            if rate > 0:
                time.sleep(rate)


if __name__ == "__main__":
    main()
