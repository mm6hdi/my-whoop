# WHOOP 5.0 (Gen-5) reverse-engineering toolkit

Scripts to **discover and decode the WHOOP 5.0's BLE protocol on your own Mac**, for
interoperability with your own device and your own data. The 5.0 is **not** supported by the
app yet — it speaks a different, undocumented BLE protocol than the 4.0 this repo decodes (see
[`../../FINDINGS.md`](../../FINDINGS.md) §6–7). These tools make **no** assumption that the 5.0
matches the 4.0; they help you find out.

> Independent reverse-engineering for interoperability (17 U.S.C. §1201(f)); **not** affiliated
> with WHOOP, Inc. Your own device, your own data, at your own risk. No proprietary WHOOP
> material is used or included. See [`../../DISCLAIMER.md`](../../DISCLAIMER.md).

## Prerequisites

- A Mac (or Linux box) with Bluetooth and Python 3.11+, `pip install bleak`.
- Copy `../device_local.example.py` → `../device_local.py` (gitignored) — you'll fill in
  `GEN5_ADDR` (and later the `GEN5_*_UUID`s) as you discover them.
- Run everything from the **repo root** so `device_config` resolves, e.g.
  `python re/gen5/gen5_scan.py`.

## The path (each step feeds the next)

| Step | Script | What it does |
|---|---|---|
| 1 | `gen5_scan.py` | Find the band, print its address → set `GEN5_ADDR`. |
| 2 | `gen5_gatt_dump.py` | Enumerate all services/characteristics → set the `GEN5_*_UUID`s. |
| 3 | `gen5_standard_ble.py` | **Early win:** standard HR `0x2A37` (HR + R-R) usually works unbonded — enough for HRV/recovery before the custom protocol is cracked. |
| 4 | `gen5_probe.py` | Bond (one confirmed write) + listen; log raw notifications losslessly. |
| 5 | `gen5_capture.py` | Sustained capture with a control file + phase labels (for IMU/optical decode). |
| — | `analyze_frames.py` | Offline: infer framing (SOF, LE length header, entropy) from a capture. Pure functions, unit-tested (`test_analyze_frames.py`). |

Captures (`gen5_*.jsonl`) and the `gen5_control.txt` / `gen5_phase.txt` driver files are
**gitignored** — they're personal data, kept local.

## Quick start

```bash
pip install bleak
cp re/device_local.example.py re/device_local.py     # then edit GEN5_ADDR after step 1

python re/gen5/gen5_scan.py                            # 1 → note the WHOOP address
# edit re/device_local.py: GEN5_ADDR = "…"
python re/gen5/gen5_gatt_dump.py                       # 2 → note the real UUIDs
python re/gen5/gen5_standard_ble.py                    # 3 → live HR + R-R, hopefully
python re/gen5/gen5_probe.py --bond-write              # 4 → bond + listen 30s
python re/gen5/analyze_frames.py re/gen5/gen5_probe.jsonl
```

The full method (including the labeled controlled-motion capture that decoded the 4.0 IMU, and a
known/unknown checklist) is in
[`../../docs/2026-05-30-whoop-5.0-re-method.md`](../../docs/2026-05-30-whoop-5.0-re-method.md).

When you've decoded something, record the layout in
[`../../protocol/whoop_protocol_gen5.json`](../../protocol/whoop_protocol_gen5.json) (a skeleton
that mirrors the 4.0 schema) and update `FINDINGS.md`.
