# Copy to re/device_local.py (gitignored) and fill in your strap's real values.
# These are personal identifiers — device_local.py must never be committed.
DEVICE_UUID = "00000000-0000-0000-0000-000000000000"  # macOS CoreBluetooth peripheral UUID
DEVICE_MAC = "00:00:00:00:00:00"                       # Bluetooth MAC
DEVICE_SERIAL = "0000000000"                            # strap serial

# ── WHOOP 5.0 (Gen-5) reverse-engineering (optional) ──────────────────────────
# Only needed if you're decoding a 5.0 band with the re/gen5/ toolkit. Leaving these
# commented out uses the defaults in device_config.py (which guess the 4.0 UUIDs).
#   1. Fill GEN5_ADDR from:  python re/gen5/gen5_scan.py
#   2. Fill the GEN5_*_UUIDs from:  python re/gen5/gen5_gatt_dump.py
# GEN5_ADDR = "00000000-0000-0000-0000-000000000000"  # the 5.0's BLE address/UUID
# GEN5_SERVICE_UUID = "..."   # custom command/data service (if not the 4.0 one)
# GEN5_CMD_TX_UUID  = "..."   # write here   (commands → strap)
# GEN5_CMD_RX_UUID  = "..."   # notify       (command responses ←)
# GEN5_EVENTS_UUID  = "..."   # notify       (events ←)
# GEN5_DATA_UUID    = "..."   # notify       (realtime / raw / historical ←)
