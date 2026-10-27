"""Shared, client-neutral configuration parsing for AutoFlow integrations."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
IMAGE_REQUIRED_KEYS = ("BASEURL", "APIKEY")
VALIDATOR_KEYS = ("VALIDATOR_BASEURL", "VALIDATOR_APIKEY", "VALIDATOR_MODEL")
OPTIONAL_KEYS = (
    "IMAGE_MODEL",
    "IMAGE_DEFAULT_RESOLUTION",
    "IMAGE_MAX_RETRIES",
    "IMAGE_PROBE_RETRIES",
    "VALIDATOR_RESPONSE_FORMAT",
    "VALIDATOR_REASONING_EFFORT",
    "VALIDATOR_MAX_RETRIES",
)


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse canonical KEY=value lines and legacy KEY:value lines."""
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        delimiter = "=" if "=" in line else ":" if ":" in line else None
        if delimiter is None:
            continue
        key, value = line.split(delimiter, 1)
        key = key.strip()
        if not ENV_KEY_RE.fullmatch(key):
            continue
        values[key] = value.strip().strip('"').strip("'")
    return values


def load_skill_env(root: Path) -> dict[str, str]:
    return parse_env_file(root / ".env")


def env_report(root: Path) -> dict[str, Any]:
    values = load_skill_env(root)
    image_missing = [key for key in IMAGE_REQUIRED_KEYS if not values.get(key)]
    validator_missing = [key for key in VALIDATOR_KEYS if not values.get(key)]
    return {
        "env_file": str((root / ".env").resolve()),
        "configured_fields": sorted(key for key, value in values.items() if value),
        "image": {
            "missing": image_missing,
            "configured": not image_missing,
            "model": values.get("IMAGE_MODEL") or "gpt-image-2.5",
            "default_resolution": values.get("IMAGE_DEFAULT_RESOLUTION") or "4K",
            "max_retries": _int_value(values.get("IMAGE_MAX_RETRIES"), 2),
            "probe_retries": _int_value(values.get("IMAGE_PROBE_RETRIES"), 1),
        },
        "validator": {
            "missing": validator_missing,
            "configured": not validator_missing,
            "model": values.get("VALIDATOR_MODEL", ""),
            "response_format": values.get("VALIDATOR_RESPONSE_FORMAT", ""),
            "reasoning_effort": values.get("VALIDATOR_REASONING_EFFORT", ""),
            "max_retries": _int_value(values.get("VALIDATOR_MAX_RETRIES"), 1),
        },
        "secrets_exposed": False,
    }


def _int_value(value: str | None, default: int) -> int:
    try:
        parsed = int(value or "")
    except ValueError:
        return default
    return parsed if parsed >= 1 else default
