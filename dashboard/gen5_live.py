"""Ares live server for the WHOOP MG / gen-5 over the OPEN standard BLE profiles.

The MG's custom service (fd4b0001-…) is encryption/authentication-gated — it's paired
and provisioned by the official app (an access control). This project does NOT circumvent
access controls (see ../DISCLAIMER.md), so this server uses ONLY the open, unprotected,
SIG-standard profiles that the band broadcasts to any central:

    Heart Rate 0x2A37  -> HR + R-R intervals     Battery 0x2A19 -> %
    Device Information 0x180A -> model / firmware

From R-R it computes a live HRV (RMSSD) and drives the same /live dashboard the 4.0 uses.
No bonding, no commands, nothing proprietary — just the standard heart-rate broadcast.

Setup (once):  set GEN5_ADDR in re/device_local.py   (python re/gen5/gen5_scan.py)
Run:           pip install aiohttp bleak && python dashboard/gen5_live.py
Open:          http://127.0.0.1:8765/live
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "re"))
from device_config import GEN5_ADDR  # noqa: E402
from bleak import BleakClient, BleakScanner  # noqa: E402
from aiohttp import web  # noqa: E402

STATIC = Path(__file__).parent / "static"
HR_MEAS = "00002a37-0000-1000-8000-00805f9b34fb"
BATTERY = "00002a19-0000-1000-8000-00805f9b34fb"
MODEL = "00002a24-0000-1000-8000-00805f9b34fb"
FW_REV = "00002a26-0000-1000-8000-00805f9b34fb"

clients: set = set()
state = {"connected": False, "device": None, "battery": None, "bonded": False, "fw": None}
outq: asyncio.Queue = asyncio.Queue()


def parse_hr(data: bytes):
    """Standard Heart Rate Measurement (0x2A37): flags, HR (8/16-bit), optional R-R (ms)."""
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


def emit(obj):
    try:
        outq.put_nowait(obj)
    except Exception:
        pass


def hr_cb(_, data):
    hr, rrs = parse_hr(bytes(data))
    emit({"kind": "packet",
          "packet": {"type_name": "REALTIME_DATA", "char": "hr_std", "ts": time.time(),
                     "len_bytes": len(bytes(data)),
                     "parsed": {"heart_rate": hr, "rr_intervals": rrs}},
          "state": state})


def batt_cb(_, data):
    state["battery"] = int(bytes(data)[0])
    emit({"kind": "state", "state": state})


async def ble_loop():
    while True:
        try:
            dev = await BleakScanner.find_device_by_address(GEN5_ADDR, timeout=15.0)
            if dev is None:
                state["connected"] = False
                emit({"kind": "log", "msg": "band not found, retry 5s"})
                emit({"kind": "state", "state": state})
                await asyncio.sleep(5)
                continue
            async with BleakClient(dev) as c:
                state.update(connected=True, device=dev.name)
                for uuid, key, conv in ((MODEL, "model", bytes.decode), (FW_REV, "fw", bytes.decode)):
                    try:
                        state[key] = conv(await c.read_gatt_char(uuid)).strip("\x00")
                    except Exception:
                        pass
                try:
                    state["battery"] = int((await c.read_gatt_char(BATTERY))[0])
                except Exception:
                    pass
                emit({"kind": "log", "msg": f"connected {dev.name} ({state.get('fw') or 'fw ?'})"})
                emit({"kind": "state", "state": state})
                await c.start_notify(HR_MEAS, hr_cb)
                try:
                    await c.start_notify(BATTERY, batt_cb)
                except Exception:
                    pass
                while c.is_connected:
                    await asyncio.sleep(5)
        except Exception as e:
            emit({"kind": "log", "msg": f"ble error: {e}"})
        state["connected"] = False
        emit({"kind": "state", "state": state})
        await asyncio.sleep(3)


async def broadcaster():
    while True:
        obj = await outq.get()
        for ws in list(clients):
            try:
                await ws.send_json(obj)
            except Exception:
                clients.discard(ws)


async def ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    clients.add(ws)
    await ws.send_json({"kind": "hello", "state": state})
    try:
        async for _ in ws:
            pass  # standard HR streams on subscribe; control actions from the page are no-ops
    finally:
        clients.discard(ws)
    return ws


async def live(request):
    return web.FileResponse(STATIC / "live.html")


def make_app():
    app = web.Application()
    app.router.add_get("/", live)
    app.router.add_get("/live", live)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/static", STATIC)
    return app


async def main():
    if GEN5_ADDR.startswith("00000000"):
        print("Set GEN5_ADDR in re/device_local.py first (run: python re/gen5/gen5_scan.py).")
        return
    runner = web.AppRunner(make_app())
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 8765).start()
    print("Ares live (standard HR) → http://127.0.0.1:8765/live", flush=True)
    asyncio.create_task(broadcaster())
    asyncio.create_task(ble_loop())
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
