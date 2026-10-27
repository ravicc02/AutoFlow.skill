"""Validated local settings shared by the web UI and runtime."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from env_config import parse_env_file
from image_size import normalize_resolution


DEFAULTS = {
    "IMAGE_MODEL": "gpt-image-2.5",
    "IMAGE_DEFAULT_RESOLUTION": "4K",
    "IMAGE_MAX_RETRIES": "2",
    "IMAGE_PROBE_RETRIES": "1",
    "VALIDATOR_MAX_RETRIES": "1",
    "IMAGE_EDIT_MODEL": "",
    "IMAGE_EDIT_DEFAULT_RESOLUTION": "4K",
    "IMAGE_EDIT_FALLBACK_MODEL": "",
    "IMAGE_EDIT_MAX_RETRIES": "2",
    "WORD_AUTHORING_SKILL": "auto",
}
FIELDS = (
    "BASEURL", "APIKEY", "IMAGE_MODEL", "IMAGE_DEFAULT_RESOLUTION",
    "IMAGE_MAX_RETRIES", "IMAGE_PROBE_RETRIES", "VALIDATOR_BASEURL",
    "VALIDATOR_APIKEY", "VALIDATOR_MODEL", "VALIDATOR_MAX_RETRIES",
    "VALIDATOR_RESPONSE_FORMAT", "VALIDATOR_REASONING_EFFORT",
    "IMAGE_EDIT_MODEL", "IMAGE_EDIT_DEFAULT_RESOLUTION",
    "IMAGE_EDIT_FALLBACK_MODEL", "IMAGE_EDIT_MAX_RETRIES", "WORD_AUTHORING_SKILL",
)
SECRETS = {"APIKEY", "VALIDATOR_APIKEY"}
URLS = {"BASEURL", "VALIDATOR_BASEURL"}
COUNTS = {"IMAGE_MAX_RETRIES", "IMAGE_PROBE_RETRIES", "IMAGE_EDIT_MAX_RETRIES", "VALIDATOR_MAX_RETRIES"}
MODELS = {"IMAGE_MODEL", "VALIDATOR_MODEL", "IMAGE_EDIT_MODEL", "IMAGE_EDIT_FALLBACK_MODEL"}
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


def public_settings(root: Path) -> dict:
    values = parse_env_file(root / ".env")
    return {
        "values": {key: values.get(key, DEFAULTS.get(key, "")) for key in FIELDS if key not in SECRETS},
        "secrets": {key: bool(values.get(key)) for key in SECRETS},
    }


def _validate(key: str, value: str) -> None:
    if "\r" in value or "\n" in value or "\0" in value:
        raise ValueError(f"{key} must be a single line")
    if len(value) > 2048:
        raise ValueError(f"{key} is too long")
    if key in URLS and value:
        parsed = urlparse(value)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError(f"{key} must be an HTTP(S) URL without embedded credentials")
    if key in COUNTS and (not value.isascii() or not value.isdigit() or not 1 <= int(value) <= 10):
        raise ValueError(f"{key} must be an integer from 1 to 10")
    if key in MODELS and value and not NAME_RE.fullmatch(value):
        raise ValueError(f"{key} contains invalid characters")
    if key in {"IMAGE_DEFAULT_RESOLUTION", "IMAGE_EDIT_DEFAULT_RESOLUTION"} and value:
        normalize_resolution(value)
    if key == "WORD_AUTHORING_SKILL" and value not in {"auto", "minimaxdocx", "officecli"} and not re.fullmatch(r"github:[a-z0-9-]{1,100}", value):
        raise ValueError("Invalid Word authoring skill")
    if key == "VALIDATOR_RESPONSE_FORMAT" and value not in {"", "json_object"}:
        raise ValueError("Unsupported response format")
    if key == "VALIDATOR_REASONING_EFFORT" and value not in {"", "low", "medium", "high", "max"}:
        raise ValueError("Unsupported reasoning effort")


def update_settings(root: Path, updates: dict) -> None:
    if not isinstance(updates, dict) or not updates or set(updates) - set(FIELDS):
        raise ValueError("Unknown or empty settings update")
    for key, value in updates.items():
        if not isinstance(value, str):
            raise ValueError(f"{key} must be a string")
        _validate(key, value)
    path = root / ".env"
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    lines = existing.splitlines()
    seen = set()
    updated = []
    for line in lines:
        match = re.match(r"^\s*([A-Z][A-Z0-9_]*)\s*[:=]", line)
        if match and match.group(1) in updates:
            key = match.group(1)
            if key in seen:
                continue
            seen.add(key)
            if key in SECRETS and not updates[key]:
                updated.append(line)
            else:
                updated.append(f"{key}={updates[key]}")
        else:
            updated.append(line)
    for key, value in updates.items():
        if key not in seen and (value or key not in SECRETS):
            updated.append(f"{key}={value}")
    root.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".env-", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(updated) + "\n")
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
