"""Gen-5 step 3 (the early win) — read the STANDARD BLE profiles.

These are SIG-standard, not WHOOP-proprietary, and work across generations without
bonding. If the 5.0 supports the standard Heart Rate Measurement (0x2A37) you get live
HR + R-R intervals IMMEDIATELY — enough for HRV / resting-HR / your own recovery score
— long before the custom protocol is decoded. This is the same approach that already
works on the 4.0 (see ../standard_ble.py and FINDINGS.md §5).

    python re/gen5/gen5_standard_ble.py
    python re/gen5/gen5_standard_ble.py --seconds 30

Independent reverse-engineering for interoperability with your OWN device; not
affiliated with WHOOP, Inc.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bleak import BleakClient, BleakScanner  # noqa: E402
from device_config import GEN5_ADDR  # noqa: E402

BATTERY = "00002a19-0000-1000-8000-00805f9b34fb"
MANUF = "00002a29-0000-1000-8000-00805f9b34fb"
MODEL = "00002a24-0000-1000-8000-00805f9b34fb"
FW_REV = "00002a26-0000-1000-8000-00805f9b34fb"
HR_MEAS = "00002a37-0000-1000-8000-00805f9b34fb"


def parse_hr(data: bytearray):
    """Parse standard Heart Rate Measurement (0x2A37): flags, HR (8/16-bit), optional
    R-R intervals (1/1024 s units → ms). Returns (hr, [rr_ms, ...])."""
    flags = data[0]
    idx = 1
    if flags & 0x01:
        hr = int.from_bytes(data[idx:idx + 2], "little"); idx += 2
    else:
        hr = data[idx]; idx += 1
    rrs = []
    if (flags >> 4) & 0x01:
        while idx + 2 <= len(data):
            rrs.append(round(int.from_bytes(data[idx:idx + 2], "little") / 1024 * 1000, 1))
            idx += 2
    return hr, rrs


async def _try_read(client, uuid, label, decode=lambda v: v.decode(errors="replace")):
    try:
        v = await client.read_gatt_char(uuid)
        print(f"{label}: {decode(v)}")
    except Exception as e:
        print(f"{label}: not available ({e})")


async def main(seconds: float) -> None:
    if GEN5_ADDR.startswith("00000000"):
        print("GEN5_ADDR is the placeholder. Run gen5_scan.py and set it in re/device_local.py.")
        return
    dev = await BleakScanner.find_device_by_address(GEN5_ADDR, timeout=15.0)
    if dev is None:
        print("Device not found.")
        return
    async with BleakClient(dev) as client:
        print(f"Connected: {client.is_connected}\n")
        await _try_read(client, BATTERY, "Battery", lambda v: f"{int(v[0])}%")
        await _try_read(client, MANUF, "Manufacturer")
        await _try_read(client, MODEL, "Model")
        await _try_read(client, FW_REV, "Firmware")

        print(f"\nSubscribing to Heart Rate Measurement for {seconds:.0f}s …")
        print("(HR reads 0 / no-contact while off-wrist — that's expected.)")
        n = 0

        def cb(_, data: bytearray):
            nonlocal n
            n += 1
            hr, rrs = parse_hr(bytearray(data))
            print(f"  HR={hr} bpm  RR={rrs}")

        try:
            await client.start_notify(HR_MEAS, cb)
        except Exception as e:
            print(f"\nHR subscribe failed: {e}")
            print("→ The 5.0 may not expose the standard HR profile unbonded; "
                  "fall back to the custom channel (gen5_probe.py).")
            return
        await asyncio.sleep(seconds)
        await client.stop_notify(HR_MEAS)
        print(f"\nReceived {n} HR notifications.")
        if n:
            print("✓ Standard HR works on the 5.0 — you can collect HR + R-R now, "
                  "no bonding and no decoded custom protocol required.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Read standard BLE profiles from a WHOOP 5.0.")
    ap.add_argument("--seconds", type=float, default=20.0, help="HR subscription duration")
    asyncio.run(main(ap.parse_args().seconds))
