"""Diagnostics for HAWake Satellite."""

from __future__ import annotations

from typing import Any

SECRET_KEYS = {"token", "access_token", "long_lived_access_token"}


def redact_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    """Return diagnostics payload with secrets removed."""
    return _redact(payload)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "REDACTED" if key in SECRET_KEYS else _redact(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
