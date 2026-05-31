"""Gen-5 step 4 — bond + listen, making NO frame-format assumptions.

Subscribes to EVERY notify/indicate characteristic the band exposes and logs all
notifications losslessly (raw hex + char + timestamp) to gen5_probe.jsonl. Optionally
forces a "just-works" bond by issuing one CONFIRMED write to the command char — on the
4.0 this single confirmed write is what unlocks the custom channels (see FINDINGS.md §1).

    python re/gen5/gen5_probe.py --seconds 30
    python re/gen5/gen5_probe.py --bond-write           # one confirmed 0x00 write to CMD_TX, then listen
    python re/gen5/gen5_probe.py --bond-write 01         # confirmed write 0x01 to CMD_TX, then listen
    python re/gen5/gen5_probe.py --raw-write aa0c00…      # send one arbitrary framed confirmed write

We deliberately do NOT auto-send guessed commands: the 5.0 command set and frame format
are unknown, so a wrong byte could do something you didn't intend. You drive writes
explicitly, once gen5_gatt_dump.py + analyze_frames.py tell you what's safe. Afterwards:
    python re/gen5/analyze_frames.py re/gen5/gen5_probe.jsonl

Independent reverse-engineering for interoperability with your OWN device; not
affiliated with WHOOP, Inc.
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bleak import BleakClient, BleakScanner  # noqa: E402
from device_config import GEN5_ADDR, GEN5_CMD_TX_UUID  # noqa: E402

OUT = Path(__file__).resolve().parent / "gen5_probe.jsonl"


async def main(args) -> None:
    if GEN5_ADDR.startswith("00000000"):
        print("GEN5_ADDR is the placeholder. Run gen5_scan.py and set it in re/device_local.py.")
        return
    dev = await BleakScanner.find_device_by_address(GEN5_ADDR, timeout=15.0)
    if dev is None:
        print("Device not found.")
        return

    logf = open(OUT, "a", buffering=1)
    stats: dict[str, dict] = {}

    def make_cb(uuid):
        def cb(_, data):
            raw = bytes(data)
            s = stats.setdefault(uuid, {"n": 0, "bytes": 0, "first_byte": {}})
            s["n"] += 1
            s["bytes"] += len(raw)
            if raw:
                fb = f"0x{raw[0]:02x}"
                s["first_byte"][fb] = s["first_byte"].get(fb, 0) + 1
            logf.write(json.dumps({"ts": time.time(), "char": uuid,
                                   "len": len(raw), "hex": raw.hex()}) + "\n")
        return cb

    async with BleakClient(dev) as client:
        print(f"Connected: {client.is_connected}", flush=True)
        # Subscribe to every notify/indicate char we find — not just the configured
        # ones — so we don't miss a channel we didn't know about.
        subscribed = []
        for service in client.services:
            for ch in service.characteristics:
                if {"notify", "indicate"} & set(ch.properties):
                    try:
                        await client.start_notify(ch.uuid, make_cb(ch.uuid))
                        subscribed.append(ch.uuid)
                    except Exception as e:
                        print(f"  subscribe {ch.uuid} failed: {e}")
        print(f"Subscribed to {len(subscribed)} notify/indicate chars.", flush=True)

        if args.raw_write:
            frame = bytes.fromhex(args.raw_write)
            await client.write_gatt_char(GEN5_CMD_TX_UUID, frame, response=True)
            print(f">>> raw confirmed write {frame.hex()} → {GEN5_CMD_TX_UUID}", flush=True)
        elif args.bond_write is not None:
            payload = bytes.fromhex(args.bond_write) if args.bond_write else b"\x00"
            try:
                await client.write_gatt_char(GEN5_CMD_TX_UUID, payload, response=True)
                print(f">>> bond write {payload.hex()} → {GEN5_CMD_TX_UUID} "
                      f"(confirmed write forces just-works bonding)", flush=True)
            except Exception as e:
                print(f"bond write failed: {e}", flush=True)

        print(f"Listening {args.seconds:.0f}s → {OUT.name}", flush=True)
        await asyncio.sleep(args.seconds)

    print("\n=== per-characteristic notification stats ===")
    for uuid, s in sorted(stats.items(), key=lambda kv: -kv[1]["n"]):
        print(f"  {uuid}: {s['n']} pkts, {s['bytes']} B, first-bytes={s['first_byte']}")
    if not stats:
        print("  (nothing emitted — try --bond-write to unlock custom channels, "
              "or re-check gen5_gatt_dump.py)")
    else:
        print(f"\nAnalyze it: python re/gen5/analyze_frames.py {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Bond + listen on a WHOOP 5.0, logging raw notifications.")
    ap.add_argument("--seconds", type=float, default=30.0, help="listen duration")
    ap.add_argument("--bond-write", nargs="?", const="", default=None,
                    help="issue one confirmed write to CMD_TX to force bonding (optional hex payload)")
    ap.add_argument("--raw-write", default=None,
                    help="send one arbitrary framed hex confirmed write to CMD_TX")
    asyncio.run(main(ap.parse_args()))
