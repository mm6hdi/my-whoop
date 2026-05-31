"""Ingest service configuration from environment."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    api_key: str
    db_dsn: str
    raw_root: str
    # Optional: Claude-powered insights/chat (/v1/insights, /v1/chat). When the key is
    # unset the server still boots; those two endpoints return 503. Model is overridable.
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-4-8"


def load_config() -> Config:
    api_key = os.environ.get("WHOOP_API_KEY")
    db_dsn = os.environ.get("WHOOP_DB_DSN")
    raw_root = os.environ.get("WHOOP_RAW_ROOT", "/data/raw")
    if not api_key:
        raise RuntimeError("WHOOP_API_KEY is required")
    if not db_dsn:
        raise RuntimeError("WHOOP_DB_DSN is required")
    return Config(
        api_key=api_key,
        db_dsn=db_dsn,
        raw_root=raw_root,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        anthropic_model=os.environ.get("ANTHROPIC_MODEL") or "claude-opus-4-8",
    )
