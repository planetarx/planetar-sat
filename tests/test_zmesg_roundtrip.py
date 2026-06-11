"""Roundtrip + wire-layout tests for the zmesg encoder.

These are the load-bearing tests: the encoded bytes must match the C reference
in ~/github/sness23/zmesg/zmesg.h exactly, or planetar-broker will reject them.
"""
from __future__ import annotations

import struct

from planetar_sat.bus.zmesg import FIXED_HDR, MAGIC, VERSION, Envelope, parse


def test_roundtrip_minimal():
    e = Envelope(topic="sar.chip", payload=b"hello")
    buf = e.serialize()
    e2 = parse(buf)
    assert e2.topic == "sar.chip"
    assert e2.payload == b"hello"
    assert e2.source == "planetar-sat"
    assert e2.id == e.id


def test_roundtrip_all_fields():
    e = Envelope(
        topic="track.update",
        payload=b'{"id":42}',
        source="planetar-sat:test",
        schema_name="planetar.track.update",
        schema_version=7,
        correlation_id="abc-123",
        causation_id="parent-uuid",
        flags=0,
    )
    e2 = parse(e.serialize())
    for attr in ("topic", "payload", "source", "schema_name", "schema_version",
                 "correlation_id", "causation_id", "flags", "id", "created_at_ns"):
        assert getattr(e, attr) == getattr(e2, attr), attr


def test_wire_layout_matches_c_reference():
    """Verify byte offsets match zmesg.h."""
    e = Envelope(topic="t", payload=b"", source="")  # empty source so header_len = FIXED_HDR + 1
    buf = e.serialize()
    assert len(buf) >= FIXED_HDR + 1
    (magic,) = struct.unpack("<I", buf[0:4])
    assert magic == MAGIC
    assert buf[4] == VERSION
    (header_len,) = struct.unpack("<H", buf[6:8])
    assert header_len == FIXED_HDR + 1
    (topic_len,) = struct.unpack("<H", buf[48:50])
    assert topic_len == 1
    assert buf[FIXED_HDR:FIXED_HDR + 1] == b"t"


def test_uuid7_version_and_variant():
    e = Envelope(topic="t", payload=b"")
    # version nibble (high 4 bits of byte 6) must be 0x7; variant (high 2 bits
    # of byte 8) must be 0b10. Per RFC 9562 / zmesg.h.
    assert (e.id[6] & 0xF0) == 0x70
    assert (e.id[8] & 0xC0) == 0x80
