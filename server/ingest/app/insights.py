"""Claude-powered insights + chat over the user's OWN computed metrics.

Reads the deterministic analysis outputs already produced by the pipeline (daily
metrics, workouts, profile) and asks the Anthropic API to (a) write a daily
natural-language summary + recommendations and (b) answer free-form questions. Claude
is a READ-ONLY consumer on top of the existing metrics — it computes nothing
physiological itself, so this layer is generation-agnostic (works on WHOOP 4.0 data
today, 5.0 data later).

Design notes:
  * `render_context` is PURE (no DB, no network) so it's unit-testable and easy to
    review — it's also the cacheable prefix sent to Claude.
  * `daily_insight` / `chat` take an injected ``client`` so tests pass a fake (no real
    API calls, no cost). `make_client` builds the real Anthropic client lazily, so the
    server boots without the SDK installed or the key set.
  * Per the claude-api skill: official SDK, default model claude-opus-4-8 (overridable),
    adaptive thinking, prompt caching on the stable system/context prefix.

The metrics sent are the user's own data, dispatched to the Anthropic API under the
operator's own ANTHROPIC_API_KEY. Outputs are explicitly non-medical / non-diagnostic.
"""
from __future__ import annotations

import datetime as _dt
import json

DEFAULT_MODEL = "claude-opus-4-8"

# Carried into every Claude call — mirrors the non-medical notice in README/DISCLAIMER.md.
_DISCLAIMER = (
    "IMPORTANT: These metrics come from an independent, unofficial reimplementation of "
    "WHOOP-like analytics. They are approximations, NOT a medical device, and NOT "
    "clinically validated. Never give medical advice, diagnoses, or treatment guidance. "
    "Frame everything as general wellness observations about the user's own data, and "
    "suggest consulting a clinician for any health concern."
)

_COACH_SYSTEM = (
    "You are a concise, encouraging recovery & training assistant embedded in a personal, "
    "self-hosted WHOOP-style app. You analyze ONLY the metrics provided for the device "
    "owner — their own body, their own data. Be specific and reference the numbers you "
    "were given; never invent data you weren't shown. Prefer plain language over jargon. "
    + _DISCLAIMER
)

_INSIGHT_INSTRUCTION = (
    "Based on the metrics above, write today's recovery/training insight. Respond with "
    "ONLY a JSON object (no preamble, no code fences) with exactly these keys:\n"
    '  "summary": a 2-4 sentence plain-language read on how the user is doing,\n'
    '  "observations": an array of short strings noting concrete patterns/trends in the data,\n'
    '  "recommendations": an array of short, actionable, non-medical suggestions.\n'
    "Reference the actual numbers (recovery, strain, sleep, HRV, RHR, trends)."
)


def make_client(api_key: str):
    """Build the real Anthropic client. Imported lazily so the server boots (and the
    test suite runs with a fake client) without the `anthropic` package installed."""
    import anthropic

    return anthropic.Anthropic(api_key=api_key)


# ── Context rendering (PURE — unit-tested, no DB/network) ─────────────────────

def _fmt(v, nd: int = 0, suffix: str = "") -> str:
    """Format a metric value, rendering None as an em dash."""
    if v is None:
        return "—"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return (f"{round(f)}{suffix}" if nd == 0 else f"{f:.{nd}f}{suffix}")


def _daily_line(d: dict) -> str:
    """One compact line summarizing a daily_metrics row. ``recovery`` is a 0-100 score;
    ``efficiency`` is a 0-1 fraction (rendered as %)."""
    eff = d.get("efficiency")
    eff_pct = eff * 100 if isinstance(eff, (int, float)) else None
    return (
        f"  {d.get('day')}: "
        f"recovery {_fmt(d.get('recovery'), 0, '%')}, "
        f"strain {_fmt(d.get('strain'), 1)}/21, "
        f"sleep {_fmt(d.get('total_sleep_min'), 0)} min "
        f"(eff {_fmt(eff_pct, 0, '%')}; "
        f"deep {_fmt(d.get('deep_min'), 0)}/rem {_fmt(d.get('rem_min'), 0)}/light {_fmt(d.get('light_min'), 0)} min), "
        f"RHR {_fmt(d.get('resting_hr'), 0)} bpm, "
        f"HRV {_fmt(d.get('avg_hrv'), 0)} ms, "
        f"SpO2 {_fmt(d.get('spo2_pct'), 0, '%')}, "
        f"resp {_fmt(d.get('resp_rate_bpm'), 1)}/min, "
        f"skin-temp dev {_fmt(d.get('skin_temp_dev_c'), 1, '°C')}, "
        f"workouts {d.get('exercise_count') if d.get('exercise_count') is not None else 0}"
    )


def _workout_line(w: dict) -> str:
    dur = w.get("duration_s")
    mins = (dur / 60) if isinstance(dur, (int, float)) else None
    return (
        f"  {w.get('kind') or 'workout'}: {_fmt(mins, 0)} min, "
        f"avg HR {_fmt(w.get('avg_hr'), 0)}, peak {_fmt(w.get('peak_hr'), 0)}, "
        f"strain {_fmt(w.get('strain'), 1)}, {_fmt(w.get('calories_kcal'), 0)} kcal"
    )


def render_context(*, daily: list[dict], workouts: list[dict],
                   profile: dict | None, target_day: str) -> str:
    """Pure: format the user's recent metrics into a compact text block for Claude.

    ``daily`` rows use the daily_metrics columns (recovery is 0-100, efficiency 0-1);
    ``workouts`` use the exercise_sessions columns; ``profile`` is the profile row or
    None. No DB and no network — this is the cacheable context prefix."""
    lines: list[str] = []
    if profile:
        bits = []
        if profile.get("age") is not None:
            bits.append(f"age {profile['age']}")
        if profile.get("sex"):
            bits.append(str(profile["sex"]))
        if profile.get("height_cm") is not None:
            bits.append(f"{_fmt(profile['height_cm'], 0)} cm")
        if profile.get("weight_kg") is not None:
            bits.append(f"{_fmt(profile['weight_kg'], 1)} kg")
        if bits:
            lines.append("User profile: " + ", ".join(bits))

    lines.append(f"Target day: {target_day}")
    lines.append("")
    lines.append("Daily metrics (oldest → newest):")
    if daily:
        lines.extend(_daily_line(d) for d in daily)
    else:
        lines.append("  (no daily metrics in this range)")

    if workouts:
        lines.append("")
        lines.append("Workouts in range:")
        lines.extend(_workout_line(w) for w in workouts)

    return "\n".join(lines)


# ── Context building (DB) ─────────────────────────────────────────────────────

def build_context(conn, device: str, target_day: _dt.date, lookback_days: int = 7) -> str:
    """Assemble the metrics context for ``device`` over [target_day - lookback, target_day]
    by reusing the read-layer queries, then render it. ``target_day`` is a datetime.date.

    ``read`` is imported lazily so the pure helpers above (render_context, daily_insight,
    chat) stay importable without the DB / whoop_protocol import chain."""
    from . import read

    start = target_day - _dt.timedelta(days=max(0, lookback_days))
    daily = read.query_daily(conn, device, start, target_day)
    workouts = read.query_workouts(conn, device, start, target_day)
    profile = read.query_profile(conn, device)
    return render_context(daily=daily, workouts=workouts, profile=profile,
                          target_day=target_day.isoformat())


# ── Anthropic calls ───────────────────────────────────────────────────────────

def _text_from(resp) -> str:
    """Concatenate the text blocks of an Anthropic response (skips thinking blocks)."""
    parts = []
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
    return "".join(parts).strip()


def _parse_json(text: str) -> dict:
    """Parse a JSON object from Claude's text, tolerating stray prose / code fences."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


def daily_insight(context: str, *, client, model: str = DEFAULT_MODEL) -> dict:
    """Ask Claude for a structured {summary, observations, recommendations} insight.
    ``client`` is an Anthropic client (injected so tests can fake it)."""
    resp = client.messages.create(
        model=model,
        max_tokens=4000,
        thinking={"type": "adaptive"},
        system=[{"type": "text", "text": _COACH_SYSTEM,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user",
                   "content": context + "\n\n" + _INSIGHT_INSTRUCTION}],
    )
    result = _parse_json(_text_from(resp))
    # Normalize shape so callers/DB always get the three keys.
    return {
        "summary": result.get("summary"),
        "observations": result.get("observations") or [],
        "recommendations": result.get("recommendations") or [],
    }


def chat(messages: list[dict], context: str, *, client, model: str = DEFAULT_MODEL) -> str:
    """Answer a multi-turn conversation grounded in the user's metrics. ``messages`` is
    the stateless history ([{role, content}, ...], roles user/assistant). The persona +
    metrics context are sent as a cached system prefix so repeated turns hit the cache."""
    system = [
        {"type": "text", "text": _COACH_SYSTEM, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": "The user's recent metrics:\n\n" + context,
         "cache_control": {"type": "ephemeral"}},
    ]
    resp = client.messages.create(
        model=model,
        max_tokens=3000,
        thinking={"type": "adaptive"},
        system=system,
        messages=messages,
    )
    return _text_from(resp)
