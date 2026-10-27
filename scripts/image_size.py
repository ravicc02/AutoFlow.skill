"""Resolve AutoFlow image batch presets to concrete upstream size values."""

from __future__ import annotations

from pathlib import Path


# Matrix supplied for the configured OpenAI-compatible image upstream.
SIZE_MATRIX = {
    "1K": {
        "1:1": "1024x1024", "3:2": "1536x1024", "2:3": "1024x1536",
        "16:9": "1280x720", "9:16": "720x1280", "4:3": "1024x768",
        "3:4": "768x1024", "21:9": "1280x544",
    },
    "2K": {
        "1:1": "2048x2048", "3:2": "2160x1440", "2:3": "1440x2160",
        "16:9": "2560x1440", "9:16": "1440x2560", "4:3": "2048x1536",
        "3:4": "1536x2048", "21:9": "2560x1088",
    },
    "4K": {
        "1:1": "2880x2880", "3:2": "3456x2304", "2:3": "2304x3456",
        "16:9": "3840x2160", "9:16": "2160x3840", "4:3": "3200x2400",
        "3:4": "2400x3200", "21:9": "3840x1600",
    },
}


def normalize_resolution(value: str) -> str:
    text = str(value).strip()
    alias = text.replace("_", " ").upper()
    parts = alias.split()
    if len(parts) == 3:
        alias = f"{parts[0]} {parts[1]}:{parts[2]}"
    for tier in SIZE_MATRIX:
        for ratio, size in SIZE_MATRIX[tier].items():
            if alias == f"{tier} {ratio}":
                return size
    return text


def nearest_aspect_ratio(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        raise ValueError("Reference image dimensions must be positive.")
    ratio = width / height

    def distance(aspect: str) -> float:
        numerator, denominator = (int(part) for part in aspect.split(":"))
        return abs(ratio - numerator / denominator)

    return min(SIZE_MATRIX["4K"], key=distance)


def resolve_batch_size(
    resolution: str,
    aspect_ratio: str = "auto",
    *,
    asset_type: str = "illustration",
    reference_image: str | None = None,
) -> tuple[str, str]:
    """Return (pixel size, chosen ratio); explicit pixel sizes remain compatible."""
    raw = normalize_resolution(resolution)
    tier = "4K" if raw.lower() == "auto" else raw.upper()
    ratio = str(aspect_ratio or "auto").strip().lower()
    if "x" in raw.lower():
        parts = raw.lower().split("x", 1)
        if len(parts) == 2 and all(part.isdigit() and int(part) > 0 for part in parts):
            width, height = (int(part) for part in parts)
            explicit_ratio = nearest_aspect_ratio(width, height)
            if ratio != "auto" and ratio != explicit_ratio:
                raise ValueError(f"Explicit size {raw} conflicts with aspect_ratio {aspect_ratio}.")
            return f"{width}x{height}", explicit_ratio
    if ratio == "auto":
        if reference_image:
            from PIL import Image

            with Image.open(Path(reference_image)) as image:
                ratio = nearest_aspect_ratio(*image.size)
        else:
            ratio = "16:9" if asset_type in {"screenshot", "ui_mockup"} else "1:1"
    if ratio not in SIZE_MATRIX["4K"]:
        raise ValueError(f"Unsupported aspect_ratio '{aspect_ratio}'; use auto or one of {', '.join(SIZE_MATRIX['4K'])}.")
    if tier in SIZE_MATRIX:
        return SIZE_MATRIX[tier][ratio], ratio
    raise ValueError(f"Unsupported resolution '{resolution}'; use 1K, 2K, 4K, auto, or WIDTHxHEIGHT.")
