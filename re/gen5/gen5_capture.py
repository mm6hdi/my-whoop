"""Gen-5 step 5 — sustained capture with a control file (no frame assumptions).

Holds the BLE link (auto-reconnect), subscribes to every notify/indicate characteristic,
logs ALL notifications losslessly to gen5_capture.jsonl, and lets you drive writes via a
control file WITHOUT dropping the link. Each notification is tagged with the current label
in gen5_phase.txt — the same mechanism ../capture_motion.py used for the proven 4.0
controlled-motion IMU decode (see FINDINGS.md §6 and the method doc).

    python re/gen5/gen5_capture.py

In another shell, drive it:
    echo bondwrite:01    >> re/gen5/gen5_control.txt   # confirmed write 0x01 to CMD_TX (force bond)
    echo write:aa0c…      >> re/gen5/gen5_control.txt   # arbitrary framed confirmed write
    echo writenr:aa0c…    >> re/gen5/gen5_control.txt   # write-without-response
    echo quit              >> re/gen5/gen5_control.txt

Label a capture (e.g. for IMU axis isolation):
    echo flat_table       >> re/gen5/gen5_phase.txt
    echo rotate_x         >> re/gen5/gen5_phase.txt

Independent reverse-engineering for interoperability with your OWN device; not
affiliated with WHOOP, Inc.
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bleak import BleakClient, BleakScanner  # noqa: E402
from device_config import GEN5_ADDR, GEN5_CMD_TX_UUID  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "gen5_capture.jsonl"
CONTROL = HERE / "gen5_control.txt"
PHASE = HERE / "gen5_phase.txt"
running = True


def cur_phase() -> str:
    try:
        return PHASE.read_text().strip() or "none"
    except OSError:
        return "none"


async def control_loop(client, logf) -> None:
    global running
    CONTROL.touch()
    while running:
        try:
            lines = [ln.strip() for ln in CONTROL.read_text().splitlines() if ln.strip()]
            if lines:
                CONTROL.write_text("")  # consume
            for cmd in lines:
                if cmd == "quit":
                    running = False
                elif cmd.partition(":")[0] in ("write", "writenr", "bondwrite"):
                    kind, _, hexstr = cmd.partition(":")
                    resp = kind != "writenr"
                    frame = bytes.fromhex(hexstr) if hexstr else b"\x00"
                    await client.write_gatt_char(GEN5_CMD_TX_UUID, frame, response=resp)
                    logf.write(json.dumps({"ts": time.time(), "tx": frame.hex(),
                                           "resp": resp}) + "\n")
                    print(f">>> {kind} {frame.hex()} (response={resp})", flush=True)
                else:
                    print(f"### unknown control: {cmd}", flush=True)
        except Exception as e:
            print(f"control error: {e}", flush=True)
        await asyncio.sleep(0.4)


async def hold() -> None:
    global running
    logf = open(OUT, "a", buffering=1)

    def make_cb(uuid):
        def cb(_, data):
            raw = bytes(data)
            logf.write(json.dumps({"ts": time.time(), "phase": cur_phase(),
                                   "char": uuid, "len": len(raw), "hex": raw.hex()}) + "\n")
        return cb

    while running:
        dev = await BleakScanner.find_device_by_address(GEN5_ADDR, timeout=15.0)
        if dev is None:
            print("device not found, retry 5s…", flush=True)
            await asyncio.sleep(5)
            continue
        disconnected = asyncio.Event()
        try:
            async with BleakClient(dev, disconnected_callback=lambda _: disconnected.set()) as client:
                print(f"=== connected {dev.name} at {time.strftime('%H:%M:%S')} ===", flush=True)
                for service in client.services:
                    for ch in service.characteristics:
                        if {"notify", "indicate"} & set(ch.properties):
                            try:
                                await client.start_notify(ch.uuid, make_cb(ch.uuid))
                            except Exception as e:
                                print(f"  subscribe {ch.uuid} failed: {e}", flush=True)
                ctrl = asyncio.create_task(control_loop(client, logf))
                while running and not disconnected.is_set():
                    await asyncio.sleep(1)
                ctrl.cancel()
        except Exception as e:
            print(f"connection error: {e}", flush=True)
        if running:
            print("reconnecting in 3s…", flush=True)
            await asyncio.sleep(3)
    print("capture stopped.", flush=True)


if __name__ == "__main__":
    if GEN5_ADDR.startswith("00000000"):
        print("GEN5_ADDR is the placeholder. Run gen5_scan.py and set it in re/device_local.py.")
        sys.exit(1)
    try:
        asyncio.run(hold())
    except KeyboardInterrupt:
        running = False
        print("interrupted", flush=True)
