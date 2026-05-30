"""Gen-5 step 2 — connect and enumerate the band's FULL GATT table.

This answers the decisive structural question: does the 5.0 expose the same custom
service as the 4.0 (61080001-…) or new UUIDs? Prints every service / characteristic
(with properties) / descriptor, tags the standard profiles (HR / battery / device-info),
and lists the write-capable characteristics that are candidate command channels.

    python re/gen5/gen5_gatt_dump.py

Then record the real UUIDs in re/device_local.py:
    GEN5_SERVICE_UUID / GEN5_CMD_TX_UUID / GEN5_CMD_RX_UUID / GEN5_EVENTS_UUID / GEN5_DATA_UUID

Independent reverse-engineering for interoperability with your OWN device; not
affiliated with WHOOP, Inc. See ../README.md and ../../DISCLAIMER.md.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bleak import BleakClient, BleakScanner  # noqa: E402
from device_config import GEN5_ADDR  # noqa: E402

# 16-bit SIG-assigned UUIDs (generation-independent) — match on the first 8 hex chars.
_STD = {
    "00002a37": "Heart Rate Measurement (HR + R-R)",
    "00002a38": "Body Sensor Location",
    "00002a19": "Battery Level",
    "00002a29": "Manufacturer Name",
    "00002a24": "Model Number",
    "00002a25": "Serial Number",
    "00002a26": "Firmware Revision",
    "0000180d": "Heart Rate Service",
    "0000180f": "Battery Service",
    "0000180a": "Device Information",
}


def _std(uuid: str) -> str:
    return _STD.get(uuid.lower()[:8], "")


async def main() -> None:
    if GEN5_ADDR.startswith("00000000"):
        print("GEN5_ADDR is the placeholder. Run gen5_scan.py and set it in re/device_local.py.")
        return
    print(f"Scanning for {GEN5_ADDR} …", flush=True)
    dev = await BleakScanner.find_device_by_address(GEN5_ADDR, timeout=15.0)
    if dev is None:
        print("Not found. Is the band awake / in range?")
        return
    print(f"Connecting to {dev.name} ({dev.address}) …\n", flush=True)
    async with BleakClient(dev) as client:
        print(f"Connected: {client.is_connected}\n")
        write_chars: list[str] = []
        notify_chars: list[str] = []
        for service in client.services:
            tag = _std(service.uuid)
            print(f"[Service] {service.uuid}{('  — ' + tag) if tag else ''}")
            for ch in service.characteristics:
                props = ",".join(ch.properties)
                ctag = _std(ch.uuid)
                print(f"  [Char] {ch.uuid}  ({props}){('  — ' + ctag) if ctag else ''}")
                for d in ch.descriptors:
                    print(f"    [Desc] {d.uuid}")
                if {"write", "write-without-response"} & set(ch.properties):
                    write_chars.append(ch.uuid)
                if {"notify", "indicate"} & set(ch.properties):
                    notify_chars.append(ch.uuid)

        print("\n--- candidate command (write) characteristics ---")
        for u in write_chars or ["(none — unusual; the band may require bonding first)"]:
            print(f"  {u}")
        print("\n--- notify/indicate characteristics (response / event / data channels) ---")
        for u in notify_chars or ["(none)"]:
            print(f"  {u}")
        print("\nNext: set GEN5_*_UUID in re/device_local.py, then run gen5_standard_ble.py "
              "(quick win) and gen5_probe.py.")


if __name__ == "__main__":
    asyncio.run(main())
