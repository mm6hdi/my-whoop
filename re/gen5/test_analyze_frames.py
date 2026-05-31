"""Offline unit tests for analyze_frames (no Bluetooth — runs anywhere).

Validates the frame-inference helpers against synthetic 4.0-style frames so the
analysis is trustworthy before it's ever pointed at a real WHOOP 5.0 capture.

    python -m pytest re/gen5/test_analyze_frames.py -q
"""
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze_frames as af  # noqa: E402


def make_frame(body: bytes, sof: int = 0xAA, crc8: int = 0x00) -> bytes:
    """Build a 4.0-style frame: [SOF][len u16 LE][crc8][body…] where the declared length
    equals len(body) and the total frame length is len(body) + 4."""
    return bytes([sof]) + struct.pack("<H", len(body)) + bytes([crc8]) + body


def test_entropy_bounds():
    assert af.entropy(b"") == 0.0
    assert af.entropy(b"\x00" * 100) == 0.0          # single symbol → 0 bits/byte
    assert abs(af.entropy(bytes(range(256))) - 8.0) < 1e-9  # uniform → exactly 8 bits/byte


def test_first_byte_and_length_histograms():
    frames = [make_frame(b"\x28\x0a\x03zzz"), make_frame(b"\x28\x0a\x03zz"), b"\xbb\x01"]
    fb = af.first_byte_histogram(frames)
    assert fb[0xAA] == 2 and fb[0xBB] == 1
    lengths = af.length_histogram(frames)
    assert lengths[len(frames[0])] == 1 and lengths[2] == 1


def test_guess_sof_dominant_vs_mixed():
    dominant = [make_frame(b"abc") for _ in range(8)] + [b"\x01x", b"\x02y"]
    assert af.guess_sof(dominant) == 0xAA
    mixed = [b"\x01a", b"\x02b", b"\x03c", b"\x04d"]
    assert af.guess_sof(mixed) is None
    assert af.guess_sof([]) is None


def test_le_length_matches():
    assert af.le_length_matches(make_frame(b"hello")) is True
    # Corrupt the declared length → no longer matches the real frame length.
    f = bytearray(make_frame(b"hello"))
    f[1] = (f[1] + 1) & 0xFF
    assert af.le_length_matches(bytes(f)) is False
    assert af.le_length_matches(b"\xaa") is False  # too short to hold a length field


def test_reassemble_fragmented_and_whole():
    frame = make_frame(bytes(range(60)))  # 64-byte frame, bigger than one 20-byte BLE chunk
    fragments = [frame[i:i + 20] for i in range(0, len(frame), 20)]
    assert len(fragments) > 1
    assert af.reassemble(fragments, sof=0xAA) == [frame]
    # A frame that fits in a single fragment passes straight through.
    whole = make_frame(b"xy")
    assert af.reassemble([whole], sof=0xAA) == [whole]


def test_reassemble_multiple_frames_back_to_back():
    f1, f2 = make_frame(b"AAAA"), make_frame(bytes(range(30)))
    stream = f1 + f2
    fragments = [stream[i:i + 16] for i in range(0, len(stream), 16)]
    assert af.reassemble(fragments, sof=0xAA) == [f1, f2]


def test_summarize_flags_4_0_like_channel(tmp_path):
    cap = tmp_path / "cap.jsonl"
    frames = [make_frame(bytes([0x28, 0x0a, i]) + b"payload") for i in range(20)]
    with cap.open("w") as fh:
        for fr in frames:
            fh.write(json.dumps({"ts": 1.0, "char": "uuid-A", "len": len(fr), "hex": fr.hex()}) + "\n")
        fh.write("\n")                          # blank line tolerated
        fh.write(json.dumps({"ts": 2.0, "tx": "aa00", "resp": True}) + "\n")  # control write skipped
    recs = af.load(str(cap))
    summary = af.summarize(recs)
    assert set(summary) == {"uuid-A"}
    s = summary["uuid-A"]
    assert s["packets"] == 20
    assert s["candidate_sof"] == "0xaa"
    assert s["le_length_header_match_frac"] == 1.0
