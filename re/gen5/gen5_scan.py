"""Gen-5 step 1 — scan for the band and print its BLE address + advertised data.

No device identity is assumed here. Run this with the WHOOP 5.0 awake / on-wrist,
note the address (and advertised name) of the WHOOP entry, then put it in
re/device_local.py as GEN5_ADDR so the other gen5 scripts can find it.

    python re/gen5/gen5_scan.py                 # 12s scan, list everything (loudest first)
    python re/gen5/gen5_scan.py --name whoop     # filter by case-insensitive name substring
    python re/gen5/gen5_scan.py --seconds 20

macOS note: addresses are CoreBluetooth peripheral UUIDs, not MACs.

Independent reverse-engineering for interoperability with your OWN device and OWN
data; not affiliated with WHOOP, Inc. See ../README.md and ../../DISCLAIMER.md.
"""
import argparse
import asyncio
import sys
from pathlib import Path

# Make re/ importable (device_config) when run as re/gen5/gen5_scan.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bleak import BleakScanner  # noqa: E402


async def main(name_filter: str | None, seconds: float) -> None:
    print(f"Scanning {seconds:.0f}s … (have the band awake / on-wrist)\n", flush=True)
    found = await BleakScanner.discover(timeout=seconds, return_adv=True)
    rows = []
    for addr, (dev, adv) in found.items():
        name = (dev.name if dev else None) or (adv.local_name if adv else None) or ""
        if name_filter and name_filter.lower() not in name.lower():
            continue
        rssi = adv.rssi if adv and adv.rssi is not None else -999
        uuids = list(adv.service_uuids) if adv and adv.service_uuids else []
        rows.append((rssi, addr, name, uuids))

    rows.sort(reverse=True)  # strongest signal first
    if not rows:
        print("No matching devices. Is the band awake and in range?")
        return
    for rssi, addr, name, uuids in rows:
        print(f"  {rssi:>4} dBm  {addr}  {name!r}")
        for u in uuids:
            print(f"             svc {u}")
    print("\nPut the WHOOP entry's address into re/device_local.py as GEN5_ADDR,")
    print("then run: python re/gen5/gen5_gatt_dump.py")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Scan for a WHOOP 5.0 over BLE.")
    ap.add_argument("--name", default=None, help="case-insensitive name substring filter")
    ap.add_argument("--seconds", type=float, default=12.0, help="scan duration")
    args = ap.parse_args()
    asyncio.run(main(args.name, args.seconds))
