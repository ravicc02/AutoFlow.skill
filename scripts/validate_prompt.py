"""
Prompt JSON Validator for AutoFlow.

Three-layer validation:
  Layer 0 — STRUCTURAL: local-only, checks all required fields exist (no API needed)
  Layer 1 — REQUIREMENT: checks each image matches WORK_PLAN scoring items (needs API + vision)
  Layer 2 — CONSISTENCY: checks prompt semantics, forbidden terms, cross-image consistency (needs API)

Usage:
    # Layer 0 only (fast, local, no API)
    python validate_prompt.py --config prompt_config.json --mode structure

    # Full three-layer validation (needs API)
    python validate_prompt.py --config prompt_config.json --mode full

    # With requirement-gating (Layer 1)
    python validate_prompt.py --config prompt_config.json --mode full --requirements WORK_PLAN.md

    # Auto-fix + output
    python validate_prompt.py --config prompt_config.json --fix --output report.json
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict

import requests

from env_config import load_skill_env
from image_size import SIZE_MATRIX, resolve_batch_size

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_env_file() -> dict:
    """Load the shared, client-neutral .env format."""
    return load_skill_env(skill_root())


# ── Layer 0: Structure validation (local, no API) ──────────────────────────

REQUIRED_TOP_KEYS = [
    "task_name", "total_count", "resolution", "output_dir",
    "max_workers", "max_retries", "retry_delay", "timeout",
    "global_constraints", "scene_anchor",
    "image_policy", "global_prompt", "images"
]

REQUIRED_IMAGE_KEYS = ["name", "asset_type", "mode", "resolution", "consistency_group", "prompt"]

REQUIRED_IMAGE_POLICY_KEYS = [
    "schema_version", "default_asset_type", "default_mode",
    "fail_on_prompt_risk", "allow_negative_forbidden_terms",
    "probe_retries", "probe_timeout", "batch_timeout", "skip_existing_files",
    "screenshot_forbidden_terms", "diagram_forbidden_terms",
    "ui_density", "crop_browser_chrome",
    "quality_constraints",
    "required_image_fields", "required_global_fields"
]

REQUIRED_QUALITY_KEYS = ["consistency", "pixel_sharpness", "no_blur_or_mosaic", "time_consistency"]
ALLOWED_ASSET_TYPES = {"screenshot", "diagram", "ui_mockup", "photo", "illustration"}
ASSET_MODE_MAP = {
    "screenshot": {"screenshot_strict"},
    "diagram": {"diagram_strict", "generic"},
    "ui_mockup": {"generic"},
    "photo": {"generic"},
    "illustration": {"generic"},
}
SCREENSHOT_RESOLUTIONS = {"2560x1440", "2048x1152", "1920x1080", "1280x720", "3840x2160"}
DIAGRAM_RESOLUTIONS = {"1600x1000", "1920x1080", "2048x1152"}
SQUARE_RESOLUTIONS = {"1024x1024"}


def parse_resolution(value: str) -> tuple[int, int] | None:
    parts = str(value).lower().split("x", 1)
    if len(parts) != 2:
        return None
    try:
        width = int(parts[0].strip())
        height = int(parts[1].strip())
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def is_16_9_pair(width: int, height: int) -> bool:
    return abs((width / height) - (16 / 9)) < 0.03


def normalize_layer_check(check: dict) -> dict:
    normalized = dict(check)
    if "result" not in normalized and "status" in normalized:
        normalized["result"] = normalized.get("status")
    if "issue" not in normalized and "message" in normalized:
        normalized["issue"] = normalized.get("message")
    if "affected_field" not in normalized and "target" in normalized:
        normalized["affected_field"] = normalized.get("target")
    return normalized


def validate_structure(config: dict, config_dir: Path) -> dict:
    """Layer 0: check all required fields exist, values are plausible, reference_image paths valid."""
    checks: List[Dict] = []
    all_pass = True

    # ── top-level keys ──
    for key in REQUIRED_TOP_KEYS:
        if key not in config:
            checks.append({
                "rule": f"Layer 0 — missing top-level key: {key}",
                "result": "fail",
                "issue": f"Required key '{key}' is missing from prompt_config.json",
                "fix_suggestion": f"Add '{key}' field (see TEMPLATE.json for expected format)",
                "affected_field": key
            })
            all_pass = False
        elif key == "total_count" and not isinstance(config[key], int):
            checks.append({
                "rule": f"Layer 0 — invalid type: {key}",
                "result": "fail",
                "issue": f"total_count must be an integer, got {type(config[key]).__name__}",
                "fix_suggestion": "Set total_count to the number of images[] entries",
                "affected_field": "total_count"
            })
            all_pass = False

    for key in REQUIRED_TOP_KEYS:
        if key in config and key not in [c["affected_field"] for c in checks]:
            checks.append({
                "rule": f"Layer 0 — top-level key present: {key}",
                "result": "pass",
                "issue": "",
                "fix_suggestion": "",
                "affected_field": ""
            })

    # ── total_count vs images array length ──
    if "total_count" in config and "images" in config and isinstance(config["total_count"], int):
        actual = len(config["images"])
        expected = config["total_count"]
        if actual != expected:
            checks.append({
                "rule": "Layer 0 — total_count mismatch",
                "result": "fail",
                "issue": f"total_count={expected} but images[] has {actual} entries",
                "fix_suggestion": f"Set total_count to {actual} or add/remove images[] entries to match",
                "affected_field": "total_count"
            })
            all_pass = False
        else:
            checks.append({
                "rule": "Layer 0 — total_count matches images[]",
                "result": "pass",
                "issue": "",
                "fix_suggestion": "",
                "affected_field": ""
            })

    # ── image_policy keys ──
    if "image_policy" in config and isinstance(config["image_policy"], dict):
        policy = config["image_policy"]
        for key in REQUIRED_IMAGE_POLICY_KEYS:
            if key not in policy:
                checks.append({
                    "rule": f"Layer 0 — missing image_policy key: {key}",
                    "result": "fail",
                    "issue": f"Required image_policy key '{key}' is missing",
                    "fix_suggestion": f"Add '{key}' to image_policy (see TEMPLATE.json)",
                    "affected_field": f"image_policy.{key}"
                })
                all_pass = False

        # quality_constraints sub-keys
        if "quality_constraints" in policy and isinstance(policy["quality_constraints"], dict):
            for qk in REQUIRED_QUALITY_KEYS:
                if qk not in policy["quality_constraints"]:
                    checks.append({
                        "rule": f"Layer 0 — missing quality_constraints key: {qk}",
                        "result": "fail",
                        "issue": f"Required quality_constraints key '{qk}' is missing",
                        "fix_suggestion": f"Add '{qk}': true to image_policy.quality_constraints",
                        "affected_field": f"image_policy.quality_constraints.{qk}"
                    })
                    all_pass = False

    # ── per-image keys ──
    if "images" in config and isinstance(config["images"], list):
        for idx, img in enumerate(config["images"]):
            prefix = f"images[{idx}]"
            for key in REQUIRED_IMAGE_KEYS:
                if key not in img:
                    checks.append({
                        "rule": f"Layer 0 — missing image key: {prefix}.{key}",
                        "result": "fail",
                        "issue": f"Required image key '{key}' is missing in {prefix}",
                        "fix_suggestion": f"Add '{key}' to {prefix}",
                        "affected_field": f"{prefix}.{key}"
                    })
                    all_pass = False

            # reference_image is optional, but if present, must be a valid path
            if "reference_image" in img and img["reference_image"]:
                ref_path = Path(img["reference_image"])
                if not ref_path.is_absolute():
                    ref_path = config_dir / ref_path
                if not ref_path.exists():
                    checks.append({
                        "rule": f"Layer 0 — reference_image not found: {prefix}",
                        "result": "fail",
                        "issue": f"reference_image '{img['reference_image']}' does not exist on disk (resolved to {ref_path})",
                        "fix_suggestion": "Verify the reference_image path is correct, or remove the field for txt2img mode",
                        "affected_field": f"{prefix}.reference_image"
                    })
                    all_pass = False
                else:
                    checks.append({
                        "rule": f"Layer 0 — reference_image valid: {prefix}",
                        "result": "pass",
                        "issue": f"reference_image found: {ref_path.name}",
                        "fix_suggestion": "",
                        "affected_field": ""
                    })

            # mode values
            if "mode" in img and img["mode"] not in ("screenshot_strict", "diagram_strict", "generic"):
                checks.append({
                    "rule": f"Layer 0 — invalid mode: {prefix}",
                    "result": "fail",
                    "issue": f"mode must be 'screenshot_strict', 'diagram_strict', or 'generic', got '{img['mode']}'",
                    "fix_suggestion": "Set mode to 'screenshot_strict' (screenshots), 'diagram_strict' (diagrams), or 'generic' (other)",
                    "affected_field": f"{prefix}.mode"
                })
                all_pass = False

            if "asset_type" in img and img["asset_type"] not in ALLOWED_ASSET_TYPES:
                checks.append({
                    "rule": f"Layer 0 �� invalid asset_type: {prefix}",
                    "result": "fail",
                    "issue": f"asset_type must be one of {sorted(ALLOWED_ASSET_TYPES)}, got '{img['asset_type']}'",
                    "fix_suggestion": "Set asset_type to screenshot, diagram, ui_mockup, photo, or illustration",
                    "affected_field": f"{prefix}.asset_type"
                })
                all_pass = False

            if "asset_type" in img and "mode" in img and img["asset_type"] in ASSET_MODE_MAP:
                allowed_modes = ASSET_MODE_MAP[img["asset_type"]]
                if img["mode"] not in allowed_modes:
                    checks.append({
                        "rule": f"Layer 0 �� asset_type/mode mismatch: {prefix}",
                        "result": "fail",
                        "issue": f"asset_type '{img['asset_type']}' is not compatible with mode '{img['mode']}'",
                        "fix_suggestion": f"Use one of {sorted(allowed_modes)} for asset_type '{img['asset_type']}'",
                        "affected_field": f"{prefix}.mode"
                    })
                    all_pass = False

            if "resolution" in img:
                requested = img["resolution"]
                if str(requested).strip().lower() == "auto":
                    requested = config.get("resolution", "4K")
                raw_reference = img.get("reference_image")
                ref_path = (config_dir / raw_reference).resolve() if raw_reference else None
                try:
                    resolved, _ = resolve_batch_size(
                        requested,
                        img.get("aspect_ratio", config.get("aspect_ratio", "auto")),
                        asset_type=img.get("asset_type", "screenshot"),
                        reference_image=str(ref_path) if ref_path and ref_path.is_file() else None,
                    )
                except (OSError, ValueError) as exc:
                    checks.append({
                        "rule": f"Layer 0 �� invalid image resolution format: {prefix}",
                        "result": "fail",
                        "issue": str(exc),
                        "fix_suggestion": "Use 1K, 2K, 4K with aspect_ratio auto or one of the eight matrix ratios; legacy WIDTHxHEIGHT is also accepted",
                        "affected_field": f"{prefix}.resolution"
                    })
                    all_pass = False
                else:
                    asset_type = img.get("asset_type")
                    matrix_sizes = {size for tier in SIZE_MATRIX.values() for size in tier.values()}
                    if asset_type == "diagram":
                        if resolved not in DIAGRAM_RESOLUTIONS | matrix_sizes:
                            checks.append({
                                "rule": f"Layer 0 �� diagram resolution warning: {prefix}",
                                "result": "warn",
                                "issue": f"Diagram resolution '{resolved}' is outside the matrix and legacy diagram presets",
                                "fix_suggestion": "Prefer a matrix preset or an existing diagram size",
                                "affected_field": f"{prefix}.resolution"
                            })
                    elif resolved not in matrix_sizes | SCREENSHOT_RESOLUTIONS | DIAGRAM_RESOLUTIONS | SQUARE_RESOLUTIONS:
                        checks.append({
                            "rule": f"Layer 0 �� uncommon resolution warning: {prefix}",
                            "result": "warn",
                            "issue": f"Resolution '{resolved}' is outside the matrix and legacy presets for asset_type '{asset_type}'",
                            "fix_suggestion": "Prefer a matrix preset unless the task needs a legacy pixel size",
                            "affected_field": f"{prefix}.resolution"
                        })

            # name format
            if "name" in img:
                import re
                if not re.match(r'^img_\d{2,}$', img["name"]):
                    checks.append({
                        "rule": f"Layer 0 — invalid name format: {prefix}",
                        "result": "fail",
                        "issue": f"name must follow 'img_NNN' format (e.g. img_001), got '{img['name']}'",
                        "fix_suggestion": "Rename to img_001, img_002, ... with continuous numbers",
                        "affected_field": f"{prefix}.name"
                    })
                    all_pass = False

    # ── mark all remaining keys as pass ──
    unmarked = _find_unmarked_structural_checks(config)
    if any(item["result"] == "fail" for item in unmarked):
        all_pass = False
    for um in unmarked:
        checks.append(um)

    return {
        "layer": 0,
        "layer_name": "structural",
        "overall_result": "pass" if all_pass else "fail",
        "summary": f"Structure validation: {'all fields present' if all_pass else 'missing or invalid fields found'}",
        "checks": checks,
        "required_changes": [],
        "auto_fix_applied": False,
        "auto_fix_count": 0
    }


def _find_unmarked_structural_checks(config: dict) -> List[Dict]:
    """Generate pass entries for structural items not yet covered by explicit checks."""
    results = []
    if "images" in config and isinstance(config["images"], list):
        names = [img.get("name", "") for img in config["images"]]
        expected = [f"img_{i+1:03d}" for i in range(len(names))]
        if names != expected:
            results.append({
                "rule": "Layer 0 - naming continuity",
                "result": "fail",
                "issue": f"Image names are not continuous: got {names}, expected {expected}",
                "fix_suggestion": "Rename images to img_001, img_002, ... in order",
                "affected_field": "images[].name"
            })
        else:
            results.append({
                "rule": "Layer 0 - naming continuity",
                "result": "pass",
                "issue": "",
                "fix_suggestion": "",
                "affected_field": ""
            })

    res = config.get("resolution", "")
    parsed_top = parse_resolution(res)
    if str(res).upper() in SIZE_MATRIX or str(res).lower() == "auto":
        try:
            resolve_batch_size(res, config.get("aspect_ratio", "auto"))
        except ValueError as exc:
            results.append({"rule": "Layer 0 - resolution validity", "result": "fail", "issue": str(exc), "fix_suggestion": "Use auto or one of the eight matrix ratios", "affected_field": "aspect_ratio"})
        else:
            results.append({"rule": "Layer 0 - resolution validity", "result": "pass", "issue": "", "fix_suggestion": "", "affected_field": ""})
    elif not parsed_top:
        results.append({
            "rule": "Layer 0 - resolution validity",
            "result": "fail",
            "issue": f"Invalid resolution format: '{res}'. Expected 1K, 2K, 4K, auto, or WIDTHxHEIGHT",
            "fix_suggestion": "Use 4K with aspect_ratio auto, or a legacy pixel size",
            "affected_field": "resolution"
        })
    else:
        try:
            resolve_batch_size(res, config.get("aspect_ratio", "auto"))
        except ValueError as exc:
            results.append({"rule": "Layer 0 - resolution validity", "result": "fail", "issue": str(exc), "fix_suggestion": "Make the pixel size and aspect_ratio consistent", "affected_field": "aspect_ratio"})
            return results
        results.append({
            "rule": "Layer 0 - resolution validity",
            "result": "pass" if res in SCREENSHOT_RESOLUTIONS | DIAGRAM_RESOLUTIONS | SQUARE_RESOLUTIONS else "warn",
            "issue": "" if res in SCREENSHOT_RESOLUTIONS | DIAGRAM_RESOLUTIONS | SQUARE_RESOLUTIONS else f"Legacy pixel size '{res}' is outside the matrix presets.",
            "fix_suggestion": "" if res in SCREENSHOT_RESOLUTIONS | DIAGRAM_RESOLUTIONS | SQUARE_RESOLUTIONS else "Prefer a 1K/2K/4K matrix tier for new batches",
            "affected_field": ""
        })

    return results


def build_validation_prompt(config_json: str, requirements_text: str = "") -> str:
    """Build a validation prompt for the configured validator API."""
    req_section = """
## Requirement / WORK_PLAN excerpt

No WORK_PLAN was provided. Skip requirement-only checks when evidence is insufficient.
"""
    if requirements_text:
        req_section = f"""
## Requirement / WORK_PLAN excerpt

Use the following requirement context when judging route choice, image intent, and scoring alignment.

```
{requirements_text[:4000]}
```
"""

    return f"""You are validating an AutoFlow image prompt configuration before generation.

{req_section}

Evaluate the config in two layers.

Layer 1: requirement alignment
- R1: each image should map to a plausible scoring or evidence need from the requirement or WORK_PLAN.
- R2: txt2img vs img2img usage should be appropriate. If reference_image is present, the prompt should describe the desired change rather than restating the whole scene.

Layer 2: internal consistency
- C1: global_constraints must be structurally compatible with each image prompt.
- C2: forbidden-term strategy must match each image asset_type.
- C3: asset_type and mode must be compatible.
- C4: prompts inside the same consistency_group must keep one coherent environment anchored by scene_anchor.
- C5: resolution, aspect ratio, and asset_type must be compatible.
- C6: image_policy schema v2.0 fields must be complete and internally consistent.

Return ONLY valid JSON using this schema:
{{
  "stage": "pre_generation_static_check",
  "overall_result": "pass|fail|warn",
  "risk_level": "low|medium|high",
  "summary": "one-sentence summary",
  "layers": [
    {{
      "name": "requirement",
      "enabled": true,
      "checks": [
        {{
          "rule": "R1|R2",
          "status": "pass|fail|warn|skipped",
          "severity": "none|low|medium|high",
          "target": "json.path",
          "message": "what is wrong or why it passed",
          "fix_suggestion": "specific fix"
        }}
      ]
    }},
    {{
      "name": "consistency",
      "enabled": true,
      "checks": [
        {{
          "rule": "C1|C2|C3|C4|C5|C6",
          "status": "pass|fail|warn|risk",
          "severity": "none|low|medium|high",
          "target": "json.path",
          "message": "what is wrong or why it passed",
          "fix_suggestion": "specific fix"
        }}
      ]
    }}
  ],
  "failed_rules": ["C2"],
  "risk_rules": ["C5"],
  "can_generate_images": true,
  "required_changes": [
    {{
      "path": "json.path",
      "current": "current value summary",
      "suggested": "suggested value",
      "reason": "why it should change"
    }}
  ]
}}

Validate this prompt_config.json:

```json
{config_json}
```
"""


VALIDATOR_SYSTEM_PROMPT = """You are a strict JSON prompt-config validator.

Rules:
1. Return JSON only. No markdown fences.
2. The JSON must be directly parseable.
3. Do not include explanatory prose outside the JSON object.
4. Every check must have a concrete status and fix suggestion when applicable.
5. Prefer precise field-level findings over vague feedback.
"""


def call_validator_api(
    prompt: str,
    base_url: str,
    api_key: str,
    model: str,
    timeout: int = 120,
    response_format: str = "",
    reasoning_effort: str = "",
) -> Optional[dict]:
    """Call the configured validator API (OpenAI-compatible chat endpoint)."""
    url = f"{base_url.rstrip('/')}/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": VALIDATOR_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0,
        "max_tokens": 4096
    }
    if response_format == "json_object":
        payload["response_format"] = {"type": "json_object"}
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort

    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    result = response.json()

    if "choices" not in result or not result["choices"]:
        return None

    content = result["choices"][0].get("message", {}).get("content", "")
    if not content:
        return None

    # Try to parse the JSON response
    content = content.strip()
    # Remove markdown code block markers if present
    if content.startswith("```"):
        lines = content.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"Warning: Validator returned non-JSON response: {e}")
        print(f"Raw response: {content[:500]}")
        return {"error": "JSON parse failed", "raw": content[:1000]}


def validate_config(
    config_path: Path,
    output_path: Optional[Path] = None,
    auto_fix: bool = False,
    mode: str = "full",
    requirements_path: Optional[Path] = None
) -> dict:
    """Validate prompt_config.json."""
    if not config_path.exists():
        raise SystemExit(f"Config file not found: {config_path}")

    config = json.loads(config_path.read_text(encoding="utf-8"))
    config_dir = config_path.parent
    config_json = json.dumps(config, ensure_ascii=False, indent=2)

    print(f"=== Prompt JSON Validation ===")
    print(f"Config: {config_path}")
    print(f"Mode: {mode}")
    print(f"Images: {config.get('total_count', 0)} entries")
    if requirements_path:
        print(f"Requirements: {requirements_path}")
    print("-" * 50)

    # ── Layer 0: always run structure validation first ──
    print("\n[Layer 0] Structure validation (local)...")
    struct_result = validate_structure(config, config_dir)
    struct_checks = struct_result["checks"]
    struct_fails = [c for c in struct_checks if c["result"] == "fail"]
    struct_warns = [c for c in struct_checks if c["result"] == "warn"]

    print(f"  Results: {len([c for c in struct_checks if c['result']=='pass'])} pass, "
          f"{len(struct_fails)} fail, {len(struct_warns)} warn")

    for check in struct_checks:
        status = check["result"]
        if status == "pass":
            continue
        icon = {"fail": "[FAIL]", "warn": "[WARN]"}.get(status, "[????]")
        print(f"  {icon} {check['rule']}: {check.get('issue', '')}")

    # ── If structure-only mode, return early ──
    if mode == "structure":
        result = struct_result
        result["mode"] = "structure"
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\nReport saved: {output_path}")
        return result

    # ── Layer 1+2: need API ──
    env = load_env_file()
    base_url = env.get("VALIDATOR_BASEURL", "").strip()
    api_key = env.get("VALIDATOR_APIKEY", "").strip()
    model = env.get("VALIDATOR_MODEL", "").strip()
    response_format = env.get("VALIDATOR_RESPONSE_FORMAT", "").strip().lower()
    reasoning_effort = env.get("VALIDATOR_REASONING_EFFORT", "").strip().lower()

    missing = [
        name for name, value in (
            ("VALIDATOR_BASEURL", base_url),
            ("VALIDATOR_APIKEY", api_key),
            ("VALIDATOR_MODEL", model),
        ) if not value
    ]
    if missing:
        raise SystemExit(
            "[ERROR] Prompt validator API not configured (missing: "
            + ", ".join(missing) + ").\n"
            "Any OpenAI-compatible chat endpoint works. Add these to .env:\n"
            "  VALIDATOR_BASEURL=https://your-validator-api.example.com\n"
            "  VALIDATOR_APIKEY=sk-xxx...\n"
            "  VALIDATOR_MODEL=your-validator-model"
        )

    print(f"\nValidator: {model} @ {base_url}")
    print(f"Mode: {'auto-fix' if auto_fix else 'report-only'}")

    # Load requirements if provided
    requirements_text = ""
    if requirements_path and requirements_path.exists():
        requirements_text = requirements_path.read_text(encoding="utf-8")
        print(f"\n[Layer 1] Requirement-gated validation (WORK_PLAN loaded: {len(requirements_text)} chars)")
    else:
        print(f"\n[Layer 1] No requirements provided — skipping requirement-gated checks")

    print(f"\n[Layer 2] Consistency validation...")

    validation_prompt = build_validation_prompt(config_json, requirements_text)

    print("Calling validation agent...")
    start_time = time.time()

    try:
        max_retries = max(1, int(env.get("VALIDATOR_MAX_RETRIES", "1")))
    except ValueError:
        max_retries = 1
    result = None
    last_error = None

    for attempt in range(max_retries):
        try:
            result = call_validator_api(
                validation_prompt,
                base_url,
                api_key,
                model,
                response_format=response_format,
                reasoning_effort=reasoning_effort,
            )
            if result and "error" not in result:
                break
            last_error = result.get("error") if result else "empty response"
        except Exception as exc:
            last_error = str(exc)
            print(f"  Attempt {attempt + 1} failed: {last_error}")
            if attempt < max_retries - 1:
                time.sleep(3)

    elapsed = time.time() - start_time

    if not result or "error" in result:
        raise SystemExit(
            f"[FAIL] Prompt validation failed after {max_retries} attempts.\n"
            f"Last error: {last_error}\n"
            f"Time: {elapsed:.1f}s\n"
            f"Check VALIDATOR_BASEURL/VALIDATOR_APIKEY/VALIDATOR_MODEL in .env"
        )

    normalized_layers = []
    for layer in result.get("layers", []):
        normalized_checks = [normalize_layer_check(check) for check in layer.get("checks", [])]
        normalized_layer = dict(layer)
        normalized_layer["checks"] = normalized_checks
        normalized_layers.append(normalized_layer)

    result["layers"] = normalized_layers
    result["layers"].insert(0, {
        "name": "structural",
        "checks": struct_checks
    })

    layer_fails = len(struct_fails) > 0
    layer_warns = len(struct_warns) > 0
    for layer in result.get("layers", []):
        if layer["name"] == "structural":
            continue
        for c in layer.get("checks", []):
            status = c.get("result")
            if status == "fail":
                layer_fails = True
            elif status in {"warn", "risk"}:
                layer_warns = True

    result["mode"] = "full"
    if layer_fails:
        result["overall_result"] = "fail"
    elif layer_warns and result.get("overall_result") != "pass":
        result["overall_result"] = "warn"
    else:
        result["overall_result"] = result.get("overall_result", "pass")

    print(f"\nValidation completed in {elapsed:.1f}s")
    print(f"Overall result: {result.get('overall_result', 'unknown')}")
    print(f"Summary: {result.get('summary', 'N/A')}")

    total_pass = total_fail = total_warn = 0
    for layer in result.get("layers", []):
        for check in layer.get("checks", []):
            status = check.get("result", "?")
            icon = {"pass": "[PASS]", "fail": "[FAIL]", "warn": "[WARN]", "risk": "[RISK]", "skipped": "[SKIP]"}.get(status, "[????]")
            rule = check.get("rule", "Unknown")
            issue = check.get("issue", "")
            if status == "pass":
                total_pass += 1
            elif status == "fail":
                total_fail += 1
                print(f"  {icon} [{layer['name']}] {rule}: {issue}")
            elif status in {"warn", "risk"}:
                total_warn += 1
                print(f"  {icon} [{layer['name']}] {rule}: {issue}")

    print(f"\nResults across all layers: {total_pass} pass, {total_fail} fail, {total_warn} warn")
    print("-" * 50)

    # Required changes
    required_changes = result.get("required_changes", [])
    if required_changes:
        print(f"\n=== Required Changes ({len(required_changes)}) ===")
        for i, change in enumerate(required_changes, 1):
            print(f"\n  #{i}: {change.get('path', 'unknown')}")
            print(f"      Reason: {change.get('reason', 'N/A')}")
            current = change.get("current", "")
            suggested = change.get("suggested", "")
            if current:
                print(f"      Current:  {current[:120]}")
            if suggested:
                print(f"      Suggest:  {suggested[:120]}")

    # Auto-fix
    if auto_fix and required_changes:
        print(f"\n=== Auto-fixing prompt_config.json ===")
        fixed_count = 0
        for change in required_changes:
            path_str = change.get("path", "")
            suggested = change.get("suggested", "")
            if not path_str or not suggested:
                continue
            try:
                apply_change(config, path_str, suggested)
                fixed_count += 1
                print(f"  Fixed: {path_str}")
            except Exception as exc:
                print(f"  Failed to fix {path_str}: {exc}")

        if fixed_count > 0:
            backup_path = config_path.with_suffix(".json.bak")
            config_path.rename(backup_path)
            print(f"  Backup: {backup_path}")
            config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  Written: {config_path} ({fixed_count} changes)")
            print(f"\n  Agent: review the changes and verify before proceeding.")
            result["auto_fix_applied"] = True
            result["auto_fix_count"] = fixed_count
    elif auto_fix:
        print(f"\nNo changes needed — config is clean.")

    # Save report
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nReport saved: {output_path}")

    return result


def apply_change(config: dict, path_str: str, suggested: str) -> None:
    """Apply a single change to the config dict using dot/bracket notation path."""
    parts = []
    current = ""
    i = 0
    while i < len(path_str):
        ch = path_str[i]
        if ch == ".":
            if current:
                parts.append(current)
                current = ""
        elif ch == "[":
            if current:
                parts.append(current)
                current = ""
            j = path_str.index("]", i)
            idx = int(path_str[i+1:j])
            parts.append(idx)
            i = j
        else:
            current += ch
        i += 1
    if current:
        parts.append(current)

    target = config
    for part in parts[:-1]:
        if isinstance(part, int):
            target = target[part]
        else:
            target = target[part]

    last = parts[-1]
    if isinstance(last, int):
        target[last] = suggested
    elif last == "prompt" or last == "global_prompt":
        target[last] = suggested
    elif last == "total_count":
        target[last] = int(suggested)
    elif last == "mode":
        target[last] = str(suggested)
    elif last == "resolution":
        target[last] = str(suggested)
    else:
        try:
            target[last] = json.loads(suggested)
        except (json.JSONDecodeError, TypeError):
            target[last] = suggested


def parse_args():
    parser = argparse.ArgumentParser(
        description="Validate prompt_config.json — three-layer architecture (structure / requirement / consistency).",
        epilog=(
            "Examples:\n"
            "  # Structure only (fast, no API)\n"
            "  python validate_prompt.py --config prompt_config.json --mode structure\n\n"
            "  # Full validation with requirement-gating\n"
            "  python validate_prompt.py --config prompt_config.json --mode full --requirements WORK_PLAN.md\n\n"
            "  # Full validation + auto-fix + report\n"
            "  python validate_prompt.py --config prompt_config.json --mode full --fix --output report.json"
        )
    )
    parser.add_argument("--config", "-c", required=True, help="Path to prompt_config.json")
    parser.add_argument("--mode", "-m", choices=["structure", "full"], default="full",
                        help="Validation mode: 'structure' (local Layer 0 only) or 'full' (all three layers, needs API)")
    parser.add_argument("--requirements", "-r", help="Path to WORK_PLAN.md or requirements file for Layer 1 requirement-gated checks")
    parser.add_argument("--output", "-o", help="Path to save validation report JSON")
    parser.add_argument("--fix", action="store_true", help="Auto-apply suggested fixes to prompt_config.json (full mode only)")
    parser.add_argument("--timeout", "-t", type=int, default=120, help="API timeout in seconds")
    return parser.parse_args()


def main():
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve() if args.output else None
    requirements_path = Path(args.requirements).expanduser().resolve() if args.requirements else None

    try:
        result = validate_config(
            config_path=config_path,
            output_path=output_path,
            auto_fix=args.fix,
            mode=args.mode,
            requirements_path=requirements_path
        )

        overall = result.get("overall_result", "fail")
        if overall == "fail":
            if args.mode == "structure":
                print("\n[FAIL] Structure validation found missing or invalid fields.")
                print("Fix the above issues in prompt_config.json before proceeding.")
            else:
                print("\n[FAIL] Prompt validation found critical issues.")
                print("Fix the above issues in prompt_config.json before generating images.")
            sys.exit(1)
        elif overall == "warn":
            print("\n[WARN] Prompt validation found warnings. Review before proceeding.")
            sys.exit(0)
        else:
            print("\n[PASS] Prompt validation passed. Ready for image generation.")
            sys.exit(0)

    except SystemExit:
        raise
    except Exception as exc:
        print(f"\n[ERROR] Validation failed: {exc}")
        sys.exit(2)


if __name__ == "__main__":
    main()
