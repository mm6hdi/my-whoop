"""Offline analysis of a gen5 capture JSONL (from gen5_probe.py / gen5_capture.py).

PURE functions — NO Bluetooth, runs anywhere, unit-tested in test_analyze_frames.py — to
help infer the unknown WHOOP 5.0 frame format from raw bytes:

  * length / first-byte histograms (per characteristic),
  * Shannon entropy (structured protocol vs encrypted/compressed),
  * a candidate little-endian length-prefixed reassembler — the 4.0 used
    [SOF=0xAA][len u16 LE][crc8]… (total = len + 4); this tests whether the 5.0 does too,
  * a per-characteristic summary + a heuristic verdict.

    python re/gen5/analyze_frames.py re/gen5/gen5_probe.jsonl
    python re/gen5/analyze_frames.py re/gen5/gen5_capture.jsonl --char <uuid>

If a channel looks 4.0-like (dominant SOF + matching LE length header), the 4.0 decoder
shape in ../../protocol/whoop_protocol.json is a strong starting point. If entropy is
near 8 bits/byte, the payload is likely encrypted/compressed.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter


def load(path):
    """Load notification records ({char, len, hex, …}) from a capture JSONL.
    Tolerates blank/garbled lines and control-write ({tx,…}) lines (skipped)."""
    recs = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(r, dict) and "hex" in r and "char" in r:
                recs.append(r)
    return recs


def by_char(records) -> dict[str, list[bytes]]:
    """Group records into {char_uuid: [frame_bytes, …]} in capture order."""
    out: dict[str, list[bytes]] = {}
    for r in records:
        try:
            out.setdefault(r["char"], []).append(bytes.fromhex(r["hex"]))
        except (KeyError, ValueError):
            continue
    return out


def length_histogram(frames) -> Counter:
    return Counter(len(f) for f in frames)


def first_byte_histogram(frames) -> Counter:
    return Counter(f[0] for f in frames if f)


def guess_sof(frames, dominance: float = 0.6):
    """Return the most common first byte if it accounts for >= ``dominance`` of frames
    (a strong start-of-frame marker like the 4.0's 0xAA), else None."""
    fb = first_byte_histogram(frames)
    if not fb:
        return None
    byte, count = fb.most_common(1)[0]
    total = sum(fb.values())
    return byte if total and count / total >= dominance else None


def entropy(data: bytes) -> float:
    """Shannon entropy in bits/byte. ~8.0 ⇒ random/encrypted/compressed; structured
    protocol bytes are typically well under ~6."""
    if not data:
        return 0.0
    counts = Counter(data)
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def le_length_matches(frame: bytes, len_off: int = 1, hdr_extra: int = 4) -> bool:
    """Does a little-endian u16 at ``len_off`` plausibly encode this frame's length?
    The 4.0 used total = u16le(frame[1:3]) + 4, so hdr_extra defaults to 4. Returns True
    iff len(frame) == u16le(frame[len_off:len_off+2]) + hdr_extra."""
    if len(frame) < len_off + 2:
        return False
    declared = int.from_bytes(frame[len_off:len_off + 2], "little")
    return declared + hdr_extra == len(frame)


def reassemble(fragments, sof: int, len_off: int = 1, hdr_extra: int = 4):
    """Recover frames from BLE fragments assuming a [SOF][u16 LE length]… header (the 4.0
    scheme, total = u16le + hdr_extra). For OFFLINE analysis we have the whole byte stream,
    so this concatenates the fragments and consumes frames length-first: at a ``sof``, read
    the declared length and take exactly that many bytes (the length prefix means a ``sof``
    byte inside a payload is never mistaken for a boundary). If the byte after a frame isn't
    a ``sof`` (desync / truncation), it resyncs by scanning to the next ``sof``. Handles
    frames split across fragments AND multiple frames packed back-to-back in one fragment."""
    stream = b"".join(fragments)
    sof_byte = bytes([sof])
    frames: list[bytes] = []
    i, n = 0, len(stream)
    while i < n:
        if stream[i] != sof:                       # desynced → resync to next SOF
            j = stream.find(sof_byte, i + 1)
            if j == -1:
                break
            i = j
            continue
        if i + len_off + 2 > n:                    # not enough bytes for the length field
            break
        total = int.from_bytes(stream[i + len_off:i + len_off + 2], "little") + hdr_extra
        if total <= len_off + 2 or i + total > n:  # implausible/incomplete → resync past it
            j = stream.find(sof_byte, i + 1)
            if j == -1:
                break
            i = j
            continue
        frames.append(stream[i:i + total])
        i += total
    return frames


def summarize(records) -> dict:
    """Per-characteristic summary dict suitable for json.dumps / a quick eyeball."""
    out = {}
    for char, frames in by_char(records).items():
        allbytes = b"".join(frames)
        sof = guess_sof(frames)
        matches = sum(le_length_matches(f) for f in frames)
        out[char] = {
            "packets": len(frames),
            "total_bytes": len(allbytes),
            "length_hist": dict(length_histogram(frames).most_common(10)),
            "first_byte_hist": {f"0x{b:02x}": n for b, n in first_byte_histogram(frames).most_common(8)},
            "candidate_sof": (f"0x{sof:02x}" if sof is not None else None),
            "entropy_bits_per_byte": round(entropy(allbytes), 2),
            "le_length_header_match_frac": round(matches / len(frames), 2) if frames else 0.0,
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Infer the WHOOP 5.0 frame format from a capture JSONL.")
    ap.add_argument("jsonl")
    ap.add_argument("--char", default=None, help="restrict to one characteristic UUID")
    args = ap.parse_args()

    recs = load(args.jsonl)
    if args.char:
        recs = [r for r in recs if r.get("char") == args.char]
    summary = summarize(recs)
    print(json.dumps(summary, indent=2))

    for char, s in summary.items():
        if s["candidate_sof"] and s["le_length_header_match_frac"] >= 0.8:
            print(f"\n[{char}] looks 4.0-like: SOF {s['candidate_sof']} + LE length header "
                  f"({int(s['le_length_header_match_frac'] * 100)}% match). The 4.0 decoder "
                  f"shape in protocol/whoop_protocol.json is a strong starting point.")
        elif s["entropy_bits_per_byte"] >= 7.5:
            print(f"\n[{char}] high entropy ({s['entropy_bits_per_byte']} bits/byte) — "
                  f"payload may be encrypted or compressed.")


if __name__ == "__main__":
    main()
