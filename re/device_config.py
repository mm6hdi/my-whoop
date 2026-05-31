"""Local device identity for the RE scripts.

The real values (your strap's macOS BLE UUID / Bluetooth MAC / serial) are
personal and must never be committed. They are resolved, in order, from:

  1. re/device_local.py   (gitignored; create it from device_local.example.py)
  2. the WHOOP_DEVICE_UUID / WHOOP_DEVICE_MAC / WHOOP_DEVICE_SERIAL env vars
  3. inert placeholders    (so the published tree carries no personal identifiers)

Scripts use `from device_config import DEVICE_UUID as ADDR`.
"""
import os

_PLACEHOLDER_UUID = "00000000-0000-0000-0000-000000000000"
_PLACEHOLDER_MAC = "00:00:00:00:00:00"
_PLACEHOLDER_SERIAL = "0000000000"

try:
    # gitignored; holds the real personal values for local runs
    from device_local import (  # type: ignore
        DEVICE_UUID,
        DEVICE_MAC,
        DEVICE_SERIAL,
    )
except ImportError:
    DEVICE_UUID = os.environ.get("WHOOP_DEVICE_UUID", _PLACEHOLDER_UUID)
    DEVICE_MAC = os.environ.get("WHOOP_DEVICE_MAC", _PLACEHOLDER_MAC)
    DEVICE_SERIAL = os.environ.get("WHOOP_DEVICE_SERIAL", _PLACEHOLDER_SERIAL)


# ── WHOOP 5.0 (Gen-5) reverse-engineering config (optional) ───────────────────
# The 5.0 advertises under its own BLE address and MAY use different GATT
# service/characteristic UUIDs and a different frame format than the 4.0 above —
# none of this is known yet (see docs/2026-05-30-whoop-5.0-re-method.md). These are
# starting guesses (defaulting to the 4.0 custom-service UUIDs) that
# re/gen5/gen5_gatt_dump.py will confirm or replace. Resolution is INDEPENDENT of
# the 4.0 block above (its own try/except), so an existing device_local.py without
# any GEN5_* keys keeps working unchanged. Used only by the re/gen5/ scripts.

# 4.0 custom-service UUIDs, reused as the initial guess for the 5.0.
_GEN4_SERVICE = "61080001-8d6d-82b8-614a-1c8cb0f8dcc6"
_GEN4_CMD_TX = "61080002-8d6d-82b8-614a-1c8cb0f8dcc6"
_GEN4_CMD_RX = "61080003-8d6d-82b8-614a-1c8cb0f8dcc6"
_GEN4_EVENTS = "61080004-8d6d-82b8-614a-1c8cb0f8dcc6"
_GEN4_DATA = "61080005-8d6d-82b8-614a-1c8cb0f8dcc6"


def _gen5(name: str, default: str) -> str:
    """Resolve a Gen-5 setting from device_local.py, then the env, then ``default``."""
    try:
        import device_local  # type: ignore

        v = getattr(device_local, name, None)
        if v:
            return v
    except ImportError:
        pass
    return os.environ.get(name, default)


GEN5_ADDR = _gen5("GEN5_ADDR", _PLACEHOLDER_UUID)
GEN5_SERVICE_UUID = _gen5("GEN5_SERVICE_UUID", _GEN4_SERVICE)
GEN5_CMD_TX_UUID = _gen5("GEN5_CMD_TX_UUID", _GEN4_CMD_TX)
GEN5_CMD_RX_UUID = _gen5("GEN5_CMD_RX_UUID", _GEN4_CMD_RX)
GEN5_EVENTS_UUID = _gen5("GEN5_EVENTS_UUID", _GEN4_EVENTS)
GEN5_DATA_UUID = _gen5("GEN5_DATA_UUID", _GEN4_DATA)
