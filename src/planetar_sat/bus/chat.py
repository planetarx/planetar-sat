"""Helpers for publishing chat-style envelopes that surface in planetar-ui.

The UI's channels subscribe to topics of the form `chat.<serverId>.<channelName>`
(see `planetar-ui/src/lib/topic.ts`). To make SAR detections visible in the
running #sar-detections channel without any UI changes, this module emits
envelopes matching the format the bridge expects (schema `chat.v1.Message`,
payload `{text, author}`), bound to topic `chat.pac.sar-detections`.

We act as an autonomous bot operator. The persona id `agent-sat` slots into
the same naming scheme as the synthetic chatter's `agent-fuse` / `agent-asr`.
"""
from __future__ import annotations

import json

from planetar_sat.bus.zmesg import Envelope

CHAT_SCHEMA = "chat.v1.Message"
DEFAULT_SERVER = "pac"
DEFAULT_CHANNEL_SAR = "sar-detections"

AUTHOR = {"id": "agent-sat", "name": "sat", "role": "agent"}


def chat_envelope(
    text: str,
    channel: str = DEFAULT_CHANNEL_SAR,
    server: str = DEFAULT_SERVER,
    created_at_ns: int | None = None,
) -> Envelope:
    """Build a chat-channel envelope that planetar-ui will render as a message line.

    The `created_at_ns` override is what makes historical replay show up as
    historical: pass the scene's acquisition timestamp, not `now`.
    """
    topic = f"chat.{server}.{channel}"
    payload = {"text": text, "author": AUTHOR}
    env = Envelope(
        topic=topic,
        source=AUTHOR["id"],
        schema_name=CHAT_SCHEMA,
        schema_version=1,
        payload=json.dumps(payload).encode("utf-8"),
    )
    if created_at_ns is not None:
        env.created_at_ns = created_at_ns
    return env


def detection_line(scene_id: str, n_dets: int, n_unmatched: int | None = None) -> str:
    """Human-readable summary line for a scene's CFAR results."""
    base = f"Sentinel-1 GRD ⟦{scene_id}⟧ — {n_dets} CFAR detection{'s' if n_dets != 1 else ''}"
    if n_unmatched is not None:
        base += f", {n_unmatched} unmatched"
    return base


def track_line(track_id: str, lat: float, lon: float, speed_kn: float, n_hits: int) -> str:
    short = track_id[:8]
    return (
        f"track ⟦{short}⟧ updated — {lat:.4f}°N {abs(lon):.4f}°{'W' if lon < 0 else 'E'}"
        f", {speed_kn:.1f} kn, {n_hits} hit{'s' if n_hits != 1 else ''}"
    )
