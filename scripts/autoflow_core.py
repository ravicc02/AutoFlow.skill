from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from env_config import env_report, load_skill_env
from skill_packages import installed_skills


SCHEMA_ID = "autoflow/1.0"
SCHEMA_VERSION = "1.0"
RUN_LAYOUT_SCHEMA = "autoflow/run-layout/1.0"
REQUIREMENT_MAP_SCHEMA = "autoflow/requirement-map/1.0"
DELIVERY_REVIEW_SCHEMA = "autoflow/delivery-review/1.0"
OFFICE_VALIDATION_SCHEMA = "autoflow/office-validation/1.0"
VIDEO_VALIDATION_SCHEMA = "autoflow/video-validation/1.0"
PACKAGE_MANIFEST_SCHEMA = "autoflow/package-manifest/1.0"
ENVIRONMENT_REPORT_SCHEMA = "autoflow/environment-report/1.0"
STEP_STATUSES = {"pending", "ready", "running", "blocked", "completed", "failed", "skipped"}
GATE_STATUSES = {"pending", "approved", "rejected", "not_applicable"}
GATE_NAMES = ("plan", "source", "visual", "delivery")
VALIDATORS = {
    "artifacts_exist",
    "source_plan",
    "office_acceptance",
    "video_acceptance",
    "package_acceptance",
}
MODULE_ACTIONS = {
    "task": {"research", "build", "compute", "execute"},
    "image": {"capture", "ai", "diagram", "chart"},
    "office": {"create", "edit", "fill"},
    "video": {"analyze", "record", "create", "process"},
    "package": {"assemble"},
}
OFFICE_FORMATS = {"word", "ppt", "excel"}
VISUAL_MODULES = {"image", "office", "video"}
HASH_EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "target",
}
PLAN_REQUIRED_SECTIONS = (
    "## 目标",
    "## 需求与证据",
    "## 工作流",
    "## 产物",
    "## 信息替换",
    "## 范围与约束",
    "## 验收策略",
)


class AutoFlowError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _elapsed_seconds(started_at: str, ended_at: str | None = None) -> int:
    if not started_at:
        return 0
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(ended_at or utc_now())
    except ValueError:
        return 0
    return max(0, int((end - start).total_seconds()))


def _new_step_state(status: str = "pending") -> dict[str, Any]:
    return {
        "status": status,
        "attempts": 0,
        "revision_attempts": 0,
        "revision": 0,
        "note": "",
        "started_at": "",
        "completed_at": "",
        "active_seconds": 0,
        "history": [],
        "updated_at": utc_now(),
    }


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AutoFlowError(f"Required file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AutoFlowError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise AutoFlowError(f"Expected a JSON object in {path}")
    return data


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


INTEGRATION_MANIFEST_SCHEMA = "autoflow/integration-manifest/2.0"


def _integration_manifest_root() -> Path:
    return Path(__file__).resolve().parent.parent / "integrations"


def _run_integration_check(directory: Path, check: dict[str, Any]) -> dict[str, Any]:
    """Run a package check entry; returns {"status", "version", "message"}."""
    script = directory / check["entry"]
    runtime = str(check.get("runtime", "python")).lower()
    if not script.is_file():
        return {"status": "blocked", "version": None, "message": f"check entry not found: {check['entry']}"}
    runner = {
        "python": [sys.executable],
        "node": [shutil.which("node") or "node"],
    }.get(runtime)
    if runtime not in ("python", "node"):
        return {"status": "blocked", "version": None, "message": f"unsupported check runtime: {runtime}"}
    if runtime == "node" and not shutil.which("node"):
        return {"status": "blocked", "version": None, "message": "Node.js not found in PATH"}
    try:
        result = subprocess.run([*runner, str(script)], capture_output=True, text=True, timeout=30)
    except Exception as exc:  # pragma: no cover - subprocess failure path
        return {"status": "blocked", "version": None, "message": str(exc)}
    output = (result.stdout or "").strip()
    if not output:
        return {"status": "blocked", "version": None, "message": "check script produced no output"}
    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        return {"status": "blocked", "version": None, "message": f"check script did not emit valid JSON: {exc}"}
    status = data.get("status")
    if status not in ("available", "missing", "blocked"):
        return {"status": "blocked", "version": None, "message": f"invalid check status: {status!r}"}
    return {"status": status, "version": data.get("version"), "message": data.get("error") or ""}


def integration_catalog() -> list[dict[str, Any]]:
    """Discover and verify every checked-in integration package.

    Package contract: integrations/<name>/manifest.json ($schema
    autoflow/integration-manifest/2.0). Discovery is filesystem-only; the
    catalog tells the Agent which external capabilities are present, whether
    the local run conditions hold (via the package's own check script), and
    where the package's SKILL.md lives. Usage knowledge stays in the package;
    AutoFlow never re-writes it.
    """
    integration_root = _integration_manifest_root()
    entries: list[dict[str, Any]] = []
    for directory in sorted(
        (path for path in integration_root.iterdir() if path.is_dir()),
        key=lambda p: p.name,
    ):
        manifest_path = directory / "manifest.json"
        entry: dict[str, Any] = {
            "name": directory.name,
            "root": str(directory.resolve()),
            "manifest_file": str(manifest_path.resolve()) if manifest_path.is_file() else "",
        }
        if not manifest_path.is_file():
            entries.append({**entry, "status": "missing_manifest", "message": "Add a manifest.json before routing this package."})
            continue
        try:
            manifest = load_json(manifest_path)
        except AutoFlowError as exc:
            entries.append({**entry, "status": "invalid_manifest", "message": str(exc)})
            continue

        errors: list[str] = []
        if manifest.get("$schema") != INTEGRATION_MANIFEST_SCHEMA:
            errors.append(f"unsupported manifest schema (expected {INTEGRATION_MANIFEST_SCHEMA})")
        if manifest.get("name") != directory.name:
            errors.append("manifest name does not match directory")
        pkg_type = manifest.get("type", "")
        if pkg_type not in ("tool", "knowledge-only"):
            errors.append("type must be 'tool' or 'knowledge-only'")
        capabilities = manifest.get("capabilities", {})
        if not isinstance(capabilities, dict) or not capabilities:
            errors.append("capabilities must be a non-empty object")
        check = manifest.get("check")
        if pkg_type == "tool" and not (isinstance(check, dict) and check.get("entry") and check.get("runtime")):
            errors.append("tool packages must declare a check entry with runtime")
        if pkg_type == "knowledge-only" and check is not None:
            errors.append("knowledge-only packages must not declare a check entry")
        for field in ("upstream", "revision", "license"):
            if not str(manifest.get(field, "")).strip():
                errors.append(f"missing {field}")
        if manifest.get("self_contained") is not True:
            errors.append("self_contained must be true")
        if manifest.get("external_user_skill_required") is not False:
            errors.append("external_user_skill_required must be false")
        if manifest.get("source_checkout_required") is not False:
            errors.append("source_checkout_required must be false")

        check_status = "available"
        version = None
        check_message = ""
        if pkg_type == "tool":
            if not errors:
                check_result = _run_integration_check(directory, check)
                check_status, version, check_message = (
                    check_result["status"],
                    check_result["version"],
                    check_result["message"],
                )
        else:
            if not (directory / "SKILL.md").is_file():
                check_status, check_message = "missing", "SKILL.md not found in package"

        manifest_errors = bool(errors)
        entries.append(
            {
                **entry,
                "status": "available" if not manifest_errors and check_status == "available" else ("incomplete" if manifest_errors else check_status),
                "type": pkg_type,
                "role": manifest.get("role", "capability"),
                "capabilities": sorted(capabilities.keys()),
                "version": version,
                "check_status": check_status,
                "check_message": check_message,
                "upstream": manifest.get("upstream", ""),
                "revision": manifest.get("revision", ""),
                "license": manifest.get("license", ""),
                "errors": errors,
            }
        )
    return entries


def _run_layout_paths(output_dir: Path) -> dict[str, Path]:
    output_dir = output_dir.expanduser().resolve()
    internal = output_dir / ".autoflow"
    config = internal / "config"
    intermediate = internal / "intermediate"
    return {
        "root": output_dir,
        "internal": internal,
        "scripts": internal / "scripts",
        "runtime": internal / "runtime",
        "intermediate": intermediate,
        "verification": intermediate / "verification",
        "config": config,
        "plans": intermediate / "plans",
        "artifacts": intermediate / "artifacts",
        "submit": output_dir / "submit",
        "workflow": config / "workflow.json",
        "state": config / "run_state.json",
        "manifest": config / "artifact_manifest.json",
        "work_plan": config / "WORK_PLAN.md",
        "requirement_map": config / "requirement_map.json",
        "delivery_review": config / "delivery_review.json",
        "source_plan": intermediate / "plans" / "source_candidates.json",
    }


def workflow_paths(workflow_path: Path) -> dict[str, Path]:
    config = workflow_path.resolve().parent
    internal = config.parent
    root = internal.parent
    return {
        "root": root,
        "workflow": workflow_path.resolve(),
        "internal": internal,
        "scripts": internal / "scripts",
        "runtime": internal / "runtime",
        "intermediate": internal / "intermediate",
        "verification": internal / "intermediate" / "verification",
        "config": config,
        "plans": internal / "intermediate" / "plans",
        "artifacts": internal / "intermediate" / "artifacts",
        "submit": root / "submit",
        "state": config / "run_state.json",
        "manifest": config / "artifact_manifest.json",
        "work_plan": config / "WORK_PLAN.md",
        "requirement_map": config / "requirement_map.json",
        "delivery_review": config / "delivery_review.json",
        "source_plan": internal / "intermediate" / "plans" / "source_candidates.json",
    }


def _recipe_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "recipes"


def detect_office_backend() -> dict[str, Any]:
    """Detect officecli and the agent-selectable Word authoring backends."""
    root = Path(__file__).resolve().parent.parent
    engine_script = root / "scripts" / "office_engine.py"
    validator_script = root / "scripts" / "validate_office.py"
    if not engine_script.is_file() or not validator_script.is_file():
        return {
            "status": "missing",
            "backend": "officecli",
            "integration_root": str(root.resolve()),
            "engine_script": str(engine_script.resolve()) if engine_script.is_file() else "",
            "validator_script": str(validator_script.resolve()) if validator_script.is_file() else "",
            "external_skill_required": False,
            "message": "AutoFlow's office engine scripts are incomplete. Repair scripts/office_engine.py and scripts/validate_office.py.",
        }
    try:
        import office_engine

        report = office_engine.capability()
    except Exception as exc:  # pragma: no cover - defensive; capability() is deterministic
        return {
            "status": "blocked",
            "backend": "officecli",
            "integration_root": str(root.resolve()),
            "engine_script": str(engine_script.resolve()),
            "validator_script": str(validator_script.resolve()),
            "external_skill_required": False,
            "message": f"officecli backend probe failed: {exc}",
        }
    minimax_package = root / "integrations" / "minimax-docx"
    if not (minimax_package / "SKILL.md").is_file() or not (
        minimax_package / "scripts" / "dotnet" / "MiniMaxAIDocx.Cli"
    ).is_dir():
        minimax_status = {
            "status": "missing",
            "version": None,
            "message": "minimax-docx package is incomplete under integrations/minimax-docx.",
        }
    else:
        minimax_status = _run_integration_check(
            minimax_package, {"entry": "scripts/check.py", "runtime": "python"}
        )
        minimax_status["message"] = minimax_status.get("message") or (
            "The checked-in minimax-docx package and dotnet runtime are available."
            if minimax_status["status"] == "available"
            else minimax_status.get("message", "")
        )
    minimax_backend = {
        "backend": "minimaxdocx",
        "status": minimax_status["status"],
        "root": str(minimax_package.resolve()) if minimax_package.is_dir() else "",
        "message": minimax_status.get("message", ""),
    }
    officecli_backend = {
        "backend": "officecli",
        "status": report.get("status", "missing"),
        "root": str((root / "integrations" / "officecli").resolve()),
        "message": "Simple Word edits and the common validation/render backend." if report.get("status") == "available" else report.get("message", ""),
    }
    installed_options = [
        {"backend": item["id"], "status": item["status"], "root": str(Path(item["skill_files"][0]).parent) if item["skill_files"] else "",
         "skill_file": item["skill_files"][0] if item["skill_files"] else "", "message": "Installed GitHub Skill"}
        for item in installed_skills(root)
    ]
    requested = load_skill_env(root).get("WORD_AUTHORING_SKILL", "auto") or "auto"
    selected_word_backend = ("minimaxdocx" if minimax_backend["status"] == "available" else "officecli") if requested == "auto" else requested
    options = [minimax_backend, officecli_backend, *installed_options]
    selected_option = next((item for item in options if item["backend"] == selected_word_backend), None)
    if selected_option is None:
        selected_option = {"backend": selected_word_backend, "status": "missing", "root": "", "message": "Selected Word Skill is not installed."}
    skill_file = selected_option.get("skill_file", "")
    if not skill_file and selected_word_backend in {"minimaxdocx", "officecli"}:
        package = "minimax-docx" if selected_word_backend == "minimaxdocx" else "officecli"
        skill_file = str((root / "integrations" / package / "SKILL.md").resolve())
    word_backend = {
        "default": requested,
        "selected": selected_word_backend,
        "backend": selected_word_backend,
        "status": selected_option["status"],
        "message": selected_option["message"],
        "root": selected_option.get("root", ""),
        "skill_file": skill_file,
    }
    base = {
        **report,
        "integration_root": str((root / "integrations" / "officecli").resolve()),
        "engine_script": str(engine_script.resolve()),
        "validator_script": str(validator_script.resolve()),
        "word_backend": word_backend,
        "word_backend_options": options,
        "ppt_backend": "officecli",
        "excel_backend": "officecli",
        "officecli_status": report.get("status", "missing"),
    }
    if word_backend["status"] != "available" or officecli_backend["status"] != "available":
        base["message"] = word_backend["message"] if word_backend["status"] != "available" else officecli_backend["message"]
        base["status"] = "blocked"
    return base


def _find_video_tool(name: str) -> str:
    local_root = Path.home() / "Tools" / "ffmpeg" / "bin"
    for candidate in (local_root / f"{name}.exe", local_root / name):
        if candidate.is_file():
            return str(candidate.resolve())
    return shutil.which(name) or ""


def detect_video_backend() -> dict[str, Any]:
    root = Path(__file__).resolve().parent.parent
    script = root / "scripts" / "video_process.py"
    ffmpeg = _find_video_tool("ffmpeg")
    ffprobe = _find_video_tool("ffprobe")
    missing_files = [] if script.is_file() else ["scripts/video_process.py"]
    missing_runtime = []
    if not ffmpeg:
        missing_runtime.append("ffmpeg")
    if not ffprobe:
        missing_runtime.append("ffprobe")
    missing = missing_files + missing_runtime
    return {
        "status": "available" if not missing else ("blocked" if not missing_files else "missing"),
        "backend": "integrated-video-process",
        "integration_root": str(root.resolve()),
        "script": str(script.resolve()) if script.is_file() else "",
        "ffmpeg": ffmpeg,
        "ffprobe": ffprobe,
        "runtime": {"ffmpeg": ffmpeg, "ffprobe": ffprobe},
        "missing": missing,
        "external_skill_required": False,
        "network_access_required": False,
        "message": "ready" if not missing else "Missing runtime: " + ", ".join(missing),
    }


def _image_env_status(root: Path) -> tuple[bool, str]:
    report = env_report(root)
    image = report["image"]
    return (bool(image["configured"]), "configured" if image["configured"] else "Missing " + ", ".join(image["missing"]))


def _image_action_report(action: str, root: Path) -> dict[str, Any]:
    files = {
        "ai": [
            root / "scripts" / "generate_images.py",
            root / "scripts" / "validate_prompt.py",
            root / "scripts" / "generate_scientific_schematic.py",
            root / "scripts" / "validate_scientific_figure.py",
        ],
        "capture": [root / "scripts" / "capture_frontend_screenshots.py"],
        "diagram": [root / "scripts" / "generate_diagram_assets.py"],
        "chart": [
            root / "integrations" / "nature-figure" / "SKILL.md",
            root / "integrations" / "nature-figure" / "figure-types.json",
            root / "integrations" / "nature-figure" / "scripts" / "plot_templates.py",
        ],
    }
    missing = [str(path.relative_to(root)) for path in files.get(action, []) if not path.is_file()]
    report: dict[str, Any] = {
        "action": action,
        "backend": f"integrated-image-{action}",
        "status": "missing" if missing else "available",
        "files": [str(path.resolve()) for path in files.get(action, []) if path.is_file()],
        "missing": missing,
        "external_skill_required": False,
        "network_access_required": action == "ai",
    }
    if missing:
        report["message"] = "Image action files are incomplete."
        return report
    if action == "ai":
        configured, detail = _image_env_status(root)
        report["env"] = env_report(root)
        report["env_configured"] = configured
        report["status"] = "available" if configured else "blocked"
        report["missing"] = [] if configured else report["env"]["image"]["missing"]
        report["message"] = detail
    elif action == "capture":
        playwright_available = importlib.util.find_spec("playwright") is not None
        report["playwright_available"] = playwright_available
        report["status"] = "available" if playwright_available else "blocked"
        report["missing"] = [] if playwright_available else ["playwright"]
        report["message"] = (
            "ready" if playwright_available else "Browser capture requires Playwright (pip install playwright)."
        )
    elif action == "diagram":
        renderers = {
            "mermaid": shutil.which("mmdc") or shutil.which("mmdc.cmd"),
            "d2": shutil.which("d2") or shutil.which("d2.exe"),
            "plantuml": shutil.which("plantuml") or shutil.which("plantuml.cmd") or shutil.which("plantuml.bat"),
        }
        missing_renderers = [name for name, path in renderers.items() if not path]
        report["renderers"] = renderers
        report["status"] = "available" if not missing_renderers else "blocked"
        report["missing"] = missing_renderers
        report["message"] = "ready" if not missing_renderers else "Missing renderers: " + ", ".join(missing_renderers)
    elif action == "chart":
        missing_packages = [
            package for package in ("numpy", "matplotlib")
            if importlib.util.find_spec(package) is None
        ]
        report["status"] = "available" if not missing_packages else "blocked"
        report["missing"] = missing_packages
        report["message"] = (
            "Charts consume approved task.compute data; publication templates use the integrated Nature Figure backend."
            if not missing_packages
            else "Missing publication chart runtime: " + ", ".join(missing_packages)
        )
    else:
        report["message"] = "Image action backend is ready."
    return report


def detect_image_backend(actions: list[str] | None = None) -> dict[str, Any]:
    root = Path(__file__).resolve().parent.parent
    selected = actions or ["ai", "capture", "diagram", "chart"]
    reports = {action: _image_action_report(action, root) for action in dict.fromkeys(selected)}
    statuses = [item["status"] for item in reports.values()]
    available_count = sum(value == "available" for value in statuses)
    if available_count == len(statuses):
        status = "available"
    elif available_count:
        status = "partial"
    elif any(value == "missing" for value in statuses):
        status = "missing"
    else:
        status = "blocked"
    status_details = ", ".join(f"{action}={report['status']}" for action, report in reports.items())
    return {
        "status": status,
        "backend": "integrated-image-assets",
        "integration_root": str(root.resolve()),
        "actions": reports,
        "external_skill_required": False,
        "network_access_required": any(action == "ai" for action in reports),
        "message": "ready" if status == "available" else status_details,
    }


def image_capability_for_action(image: dict[str, Any], action: str) -> dict[str, Any]:
    """Return an action-scoped image capability without sibling-action leakage."""
    report = (image.get("actions") or {}).get(action)
    if not report:
        report = _image_action_report(action, Path(__file__).resolve().parent.parent)
    return {
        **image,
        "status": report.get("status", "missing"),
        "actions": {action: report},
        "network_access_required": bool(report.get("network_access_required", False)),
        "message": report.get("message", f"Image action {action} is unavailable."),
    }


def detect_impeccable_backend() -> dict[str, Any]:
    integration_root = _integration_manifest_root()
    integration = integration_root / "impeccable"
    skill_file = integration / "SKILL.md"
    common = {
        "backend": "integrated-impeccable",
        "integration_root": str(integration.resolve()),
        "skill_file": str(skill_file.resolve()) if skill_file.is_file() else "",
        "runtime": shutil.which("node") or "",
        "network_update_check": False,
        "external_skill_required": False,
    }
    entry = next((item for item in integration_catalog() if item["name"] == "impeccable"), None)
    if entry is None:
        return {**common, "status": "missing", "message": "integrations/impeccable is not present."}
    status = entry.get("status", "missing")
    if status == "available":
        return {**common, "status": "available"}
    if status == "incomplete":
        return {
            **common,
            "status": "missing",
            "errors": entry.get("errors", []),
            "message": "integrations/impeccable manifest is invalid. Repair integrations/impeccable.",
        }
    message = entry.get("check_message") or entry.get("message", "integrations/impeccable is unavailable.")
    return {**common, "status": status, "message": message}


def workflow_capabilities(steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        **(
            {"impeccable": detect_impeccable_backend()}
            if any(step.get("design_backend") == "integrated-impeccable" for step in steps)
            else {}
        ),
        **({"office": detect_office_backend()} if any(step.get("module") == "office" for step in steps) else {}),
        **({"video": detect_video_backend()} if any(step.get("module") == "video" for step in steps) else {}),
        **(
            {"image": detect_image_backend([step.get("action", "") for step in steps if step.get("module") == "image"])}
            if any(step.get("module") == "image" for step in steps)
            else {}
        ),
    }


def validate_capabilities(workflow: dict[str, Any]) -> None:
    if any(step.get("design_backend") == "integrated-impeccable" for step in workflow.get("steps", [])):
        impeccable = (workflow.get("capabilities") or {}).get("impeccable") or detect_impeccable_backend()
        if impeccable.get("status") != "available":
            raise AutoFlowError(
                "Frontend design workflow requires AutoFlow's integrated Impeccable backend and Node.js. "
                "Repair integrations/impeccable or install Node before PLAN_STOP approval."
            )
    if any(step.get("module") == "video" for step in workflow.get("steps", [])):
        video = (workflow.get("capabilities") or {}).get("video") or detect_video_backend()
        script = Path(str(video.get("script", "")))
        if video.get("status") != "available" or not script.is_file():
            raise AutoFlowError(
                "Video workflow requires AutoFlow's integrated video_process.py and ffmpeg/ffprobe. "
                "Install or expose the declared local runtime before PLAN_STOP approval."
            )
    if any(step.get("module") == "image" for step in workflow.get("steps", [])):
        image = (workflow.get("capabilities") or {}).get("image") or detect_image_backend()
        for step in workflow.get("steps", []):
            if step.get("module") != "image":
                continue
            action_report = (image.get("actions") or {}).get(step.get("action", ""), {})
            if action_report.get("status") != "available":
                raise AutoFlowError(
                    f"Image action {step.get('id')} requires its local backend and runtime. "
                    "Repair the reported capability before PLAN_STOP approval."
                )
    if any(step.get("module") == "office" for step in workflow.get("steps", [])):
        office = (workflow.get("capabilities") or {}).get("office") or detect_office_backend()
        office_steps = [step for step in workflow.get("steps", []) if step.get("module") == "office"]
        word_required = any(step.get("format") == "word" for step in office_steps)
        officecli_required = bool(office_steps)  # All formats share officecli validation/rendering.
        backend_unavailable = (
            (word_required and (office.get("word_backend") or {}).get("status") != "available")
            or (officecli_required and office.get("officecli_status", office.get("status")) != "available")
        )
        if backend_unavailable:
            raise AutoFlowError(
                "Office workflow requires the selected backend. "
                "Install officecli or the configured Word backend before PLAN_STOP approval; "
                "AutoFlow will not silently substitute another backend."
            )


def load_recipe(name: str) -> dict[str, Any]:
    selected = "custom" if name == "auto" else name
    path = _recipe_dir() / f"{selected}.json"
    if not path.exists():
        available = ", ".join(sorted(p.stem for p in _recipe_dir().glob("*.json")))
        raise AutoFlowError(f"Unknown recipe '{name}'. Available recipes: auto, {available}")
    recipe = load_json(path)
    if recipe.get("name") != selected or not isinstance(recipe.get("steps"), list):
        raise AutoFlowError(f"Invalid recipe definition: {path}")
    return recipe


def recommend_recipe(request_text: str) -> dict[str, Any]:
    """Choose a transparent starting recipe from request language.

    This is a recommendation, not approval. The Agent may edit a custom DAG
    before PLAN_STOP, while the recorded signals make the initial choice
    auditable and reproducible.
    """
    text = request_text.casefold()
    signal_groups = {
        "project": (
            "源码",
            "源代码",
            "项目",
            "系统",
            "网站",
            "应用",
            "app",
            "web",
            "runnable",
            "database",
            "数据库",
        ),
        "document": (
            "论文",
            "实验报告",
            "课程报告",
            "报告",
            "word",
            "docx",
            "thesis",
            "paper",
        ),
        "slides": ("答辩", "ppt", "幻灯片", "演示文稿", "presentation", "slides"),
        "video": ("视频", "录屏", "video", "screen recording"),
    }
    signals = {
        group: [term for term in terms if term in text]
        for group, terms in signal_groups.items()
    }
    matched = [group for group, terms in signals.items() if terms]

    if "project" in matched and "document" in matched and "slides" in matched:
        return {
            "requested": "auto",
            "selected": "project-report-and-slides",
            "mode": "deterministic_recommendation",
            "signals": signals,
            "reason": "项目交付同时要求源码、文档报告和演示文稿，因此组合 GitHub discovery、build、image、word、ppt、package。",
        }
    if "project" in matched and "document" in matched:
        return {
            "requested": "auto",
            "selected": "project-and-report",
            "mode": "deterministic_recommendation",
            "signals": signals,
            "reason": "项目交付同时要求源码和文档报告，因此组合 GitHub discovery、build、image、word、package。",
        }
    if "project" in matched:
        return {
            "requested": "auto",
            "selected": "project-delivery",
            "mode": "deterministic_recommendation",
            "signals": signals,
            "reason": "请求包含可运行项目或源码交付，优先启用 GitHub-first discovery、build、evidence、package。",
        }
    if "document" in matched and "slides" in matched:
        return {
            "requested": "auto",
            "selected": "report-and-slides",
            "mode": "deterministic_recommendation",
            "signals": signals,
            "reason": "请求同时要求报告和演示文稿，复用共享 task/image 证据后并行生成 Word/PPT。",
        }
    if "slides" in matched:
        return {
            "requested": "auto",
            "selected": "presentation",
            "mode": "deterministic_recommendation",
            "signals": signals,
            "reason": "请求以演示文稿为主要交付物，启用 research/image/ppt 路径。",
        }
    if "document" in matched:
        return {
            "requested": "auto",
            "selected": "document",
            "mode": "deterministic_recommendation",
            "signals": signals,
            "reason": "请求以文档为主要交付物，启用 research/image/word 路径。",
        }
    if "video" in matched:
        return {
            "requested": "auto",
            "selected": "video-delivery",
            "mode": "deterministic_recommendation",
            "signals": signals,
            "reason": "请求包含视频交付，启用 video 验收、VISUAL_STOP 和 package 路径。",
        }
    return {
        "requested": "auto",
        "selected": "custom",
        "mode": "deterministic_recommendation",
        "signals": signals,
        "reason": "未命中明确的交付类型，保留 custom DAG 供 Agent 根据需求规划。",
    }


def _new_gate(required: bool, active: bool, status: str) -> dict[str, Any]:
    return {
        "required": required,
        "active": active,
        "status": status,
        "note": "",
        "updated_at": utc_now(),
        "activated_at": utc_now() if active and status == "pending" else "",
        "wait_seconds": 0,
        "history": [],
    }


def initialize_run(request_file: Path, output_dir: Path | None, recipe_name: str) -> Path:
    request_file = request_file.expanduser().resolve()
    # The run root is anchored to the task directory, not the session workspace.
    # Default: the request file's own directory — request files live in the task
    # project root, so the run is created there instead of the workspace root.
    if output_dir is None:
        output_dir = request_file.parent
    output_dir = output_dir.expanduser().resolve()
    if not request_file.is_file():
        raise AutoFlowError(f"Request file does not exist: {request_file}")
    layout = _run_layout_paths(output_dir)
    workflow_path = layout["workflow"]
    if workflow_path.exists():
        raise AutoFlowError(f"Run already initialized: {workflow_path}")
    legacy_workflow = output_dir / "workflow.json"
    if legacy_workflow.exists():
        raise AutoFlowError(
            "Legacy AutoFlow run layout detected at the output root; "
            "create a new run with 'python scripts/autoflow.py init'."
        )

    request_text = request_file.read_text(encoding="utf-8")
    if recipe_name == "auto":
        recipe_selection = recommend_recipe(request_text)
        recipe = load_recipe(recipe_selection["selected"])
    else:
        recipe_selection = {
            "requested": recipe_name,
            "selected": recipe_name,
            "mode": "explicit",
            "signals": {},
            "reason": "用户显式指定 recipe。",
        }
        recipe = load_recipe(recipe_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    for directory in (
        layout["scripts"], layout["runtime"], layout["intermediate"], layout["verification"],
        layout["config"], layout["plans"], layout["artifacts"], layout["submit"],
    ):
        directory.mkdir(parents=True, exist_ok=True)
    request_copy = layout["config"] / "request.md"
    shutil.copyfile(request_file, request_copy)

    workflow_id = f"af-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    workflow = {
        "$schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "workflow_id": workflow_id,
        "name": output_dir.name,
        "request_file": str(request_copy),
        "request_source_file": str(request_file),
        "output_dir": str(output_dir),
        "run_layout": RUN_LAYOUT_SCHEMA,
        "directories": {
            key: str(layout[key])
            for key in ("root", "internal", "scripts", "runtime", "intermediate", "verification", "config", "plans", "artifacts", "submit")
        },
        "recipe": recipe["name"],
        "recipe_description": recipe.get("description", ""),
        "recipe_selection": recipe_selection,
        "created_at": utc_now(),
        "steps": recipe["steps"],
        "capabilities": workflow_capabilities(recipe["steps"]),
    }
    validate_workflow_definition(workflow)

    state = {
        "schema_version": SCHEMA_VERSION,
        "workflow_id": workflow_id,
        "status": "planning",
        "updated_at": utc_now(),
        "steps": {step["id"]: _new_step_state() for step in workflow["steps"]},
        "revision": 0,
        "revision_history": [],
        "gates": {
            "plan": _new_gate(True, True, "pending"),
            "source": _new_gate(False, False, "not_applicable"),
            "visual": _new_gate(False, False, "not_applicable"),
            "delivery": _new_gate(True, False, "pending"),
        },
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "workflow_id": workflow_id,
        "updated_at": utc_now(),
        "artifacts": [],
        "artifact_history": [],
    }
    requirement_map = {
        "$schema": REQUIREMENT_MAP_SCHEMA,
        "workflow_id": workflow_id,
        "status": "planning",
        "target_tier": "requirements-complete",
        "source_files": [str(request_copy)],
        "requirements": [],
        "planned_figures": [],
        "updated_at": utc_now(),
    }
    delivery_review = {
        "$schema": DELIVERY_REVIEW_SCHEMA,
        "workflow_id": workflow_id,
        "review_completed": False,
        "requirement_results": [],
        "artifact_results": [],
        "issues_found": [],
        "overall_pass": False,
        "reviewer_notes": "",
        "updated_at": utc_now(),
    }
    work_plan = f"""# AutoFlow Work Plan — {output_dir.name}

> Recipe: `{recipe['name']}`
> Workflow: `{workflow_id}`

## 目标

待填写：说明用户最终要得到什么，以及成功标准。

## 需求与证据

待填写：逐项映射需求、评分项、验收条件、证据产物和计划图表，并同步到 `requirement_map.json`。

## 工作流

待填写：说明采用的模块、执行顺序、STOP 和每步验证方式。

## 产物

待填写：列出最终产物及其预期路径或类型。

## 信息替换

待填写：记录模板占位符、身份信息、主题、数据和其他待替换内容的真实值；没有替换项时明确写“无”。

## 范围与约束

待填写：说明模板、技术栈、禁止项、外部依赖和不在范围内的事项。

## 验收策略

待填写：说明每类产物的结构检查、视觉检查、运行验证、打包检查和最终签收方法。
"""

    save_json(workflow_path, workflow)
    save_json(layout["state"], state)
    save_json(layout["manifest"], manifest)
    save_json(layout["requirement_map"], requirement_map)
    save_json(layout["delivery_review"], delivery_review)
    layout["work_plan"].write_text(work_plan, encoding="utf-8")
    return workflow_path


def load_run(workflow_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Path]]:
    workflow_path = workflow_path.expanduser().resolve()
    workflow = load_json(workflow_path)
    if workflow.get("$schema") != SCHEMA_ID or workflow.get("schema_version") != SCHEMA_VERSION:
        if any(key in workflow for key in ("template_path", "output_docx", "requirement_checklist_path")):
            raise AutoFlowError(
                "Legacy workflow detected. AutoFlow does not support AutoLab workflow.json files; "
                "create a new run with 'python scripts/autoflow.py init'."
            )
        raise AutoFlowError(
            f"Unsupported workflow schema. Expected {SCHEMA_ID} version {SCHEMA_VERSION}."
        )
    if workflow_path.parent.name != "config" or workflow_path.parent.parent.name != ".autoflow":
        raise AutoFlowError(
            "Invalid AutoFlow run layout. Expected <output>/.autoflow/config/workflow.json; "
            "create a new run with 'python scripts/autoflow.py init'."
        )
    paths = workflow_paths(workflow_path)
    state = load_json(paths["state"])
    manifest = load_json(paths["manifest"])
    return workflow, state, manifest, paths


def validate_workflow_definition(workflow: dict[str, Any]) -> None:
    if workflow.get("$schema") != SCHEMA_ID or workflow.get("schema_version") != SCHEMA_VERSION:
        raise AutoFlowError(f"Workflow must use {SCHEMA_ID} schema version {SCHEMA_VERSION}")
    steps = workflow.get("steps")
    if not isinstance(steps, list) or not steps:
        raise AutoFlowError("Workflow must contain at least one step")

    ids: list[str] = []
    produced: dict[str, tuple[str, str]] = {}
    for step in steps:
        if not isinstance(step, dict):
            raise AutoFlowError("Every workflow step must be an object")
        step_id = str(step.get("id", "")).strip()
        module = str(step.get("module", "")).strip()
        action = str(step.get("action", "")).strip()
        if not step_id:
            raise AutoFlowError("Every workflow step needs a non-empty id")
        if step_id in ids:
            raise AutoFlowError(f"Duplicate step id: {step_id}")
        if module not in MODULE_ACTIONS or action not in MODULE_ACTIONS[module]:
            raise AutoFlowError(f"Unsupported module action in {step_id}: {module}.{action}")
        needs = step.get("needs", [])
        inputs = step.get("inputs", [])
        outputs = step.get("outputs", [])
        if not all(isinstance(values, list) for values in (needs, inputs, outputs)):
            raise AutoFlowError(f"Step {step_id} needs/inputs/outputs must be arrays")
        max_attempts = step.get("max_attempts", 3)
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or not 1 <= max_attempts <= 10:
            raise AutoFlowError(f"Step {step_id} max_attempts must be an integer from 1 to 10")
        for artifact_id in outputs:
            producer = produced.get(artifact_id)
            if producer is not None:
                producer_step, producer_module = producer
                shared_office_output = (
                    module == "office"
                    and producer_module == "office"
                    and artifact_id in {"office.document", "office.validation"}
                )
                if not shared_office_output:
                    raise AutoFlowError(
                        f"Artifact '{artifact_id}' is produced by both {producer_step} and {step_id}"
                    )
            produced[artifact_id] = (step_id, module)
        gate_after = step.get("gate_after")
        if gate_after is not None and gate_after not in {"source", "visual"}:
            raise AutoFlowError(f"Step {step_id} has unsupported gate_after '{gate_after}'")
        validator = step.get("validator")
        if validator not in VALIDATORS:
            raise AutoFlowError(f"Step {step_id} has unsupported validator '{validator}'")
        if module == "office":
            if step.get("format") not in OFFICE_FORMATS:
                raise AutoFlowError(f"Office step {step_id} must declare format in {', '.join(sorted(OFFICE_FORMATS))}")
            if validator != "office_acceptance":
                raise AutoFlowError(f"Office step {step_id} must use the office_acceptance validator")
            required_office_outputs = {"office.document", "office.validation"}
            if not required_office_outputs.issubset(outputs):
                raise AutoFlowError(
                    f"Office step {step_id} must declare outputs: {', '.join(sorted(required_office_outputs))}"
                )
        elif validator == "office_acceptance":
            raise AutoFlowError(f"Only office steps may use the office_acceptance validator: {step_id}")
        if module == "task" and action == "build":
            required_build_outputs = {"project.source", "task.result", "task.environment"}
            if not required_build_outputs.issubset(outputs):
                raise AutoFlowError(
                    f"Build step {step_id} must declare outputs: {', '.join(sorted(required_build_outputs))}"
                )
        if module == "video":
            if validator != "video_acceptance":
                raise AutoFlowError(f"Video step {step_id} must use the video_acceptance validator")
            required_video_outputs = {"video.media", "video.validation"}
            if not required_video_outputs.issubset(outputs):
                raise AutoFlowError(
                    f"Video step {step_id} must declare outputs: {', '.join(sorted(required_video_outputs))}"
                )
        elif validator == "video_acceptance":
            raise AutoFlowError(f"Only video steps may use the video_acceptance validator: {step_id}")
        if module == "package":
            if validator != "package_acceptance":
                raise AutoFlowError(f"Package step {step_id} must use the package_acceptance validator")
            required_package_outputs = {"package.bundle", "package.manifest"}
            if not required_package_outputs.issubset(outputs):
                raise AutoFlowError(
                    f"Package step {step_id} must declare outputs: {', '.join(sorted(required_package_outputs))}"
                )
        elif validator == "package_acceptance":
            raise AutoFlowError(f"Only package steps may use the package_acceptance validator: {step_id}")
        if gate_after == "source" and not (
            module == "task" and action == "research" and step.get("source_policy") == "github_first"
        ):
            raise AutoFlowError(f"Step {step_id} may use SOURCE_STOP only for task.research with github_first")
        if gate_after == "visual" and module not in VISUAL_MODULES:
            raise AutoFlowError(f"Step {step_id} may use VISUAL_STOP only for image, office, or video modules")
        ids.append(step_id)

    known = set(ids)
    for step in steps:
        step_id = step["id"]
        for dependency in step.get("needs", []):
            if dependency not in known:
                raise AutoFlowError(f"Step {step_id} depends on unknown step: {dependency}")
            if dependency == step_id:
                raise AutoFlowError(f"Step {step_id} cannot depend on itself")
        step_ids = {s["id"] for s in steps}
        for artifact_id in step.get("inputs", []):
            if artifact_id == "request":
                continue
            producer_id, _, base_id = artifact_id.partition("::")
            if "::" in artifact_id:
                if base_id not in produced:
                    raise AutoFlowError(
                        f"Step {step_id} consumes unknown artifact: {artifact_id}"
                    )
                if producer_id not in step_ids or base_id not in next(
                    s["outputs"] for s in steps if s["id"] == producer_id
                ):
                    raise AutoFlowError(
                        f"Step {step_id} consumes unknown producer artifact: {artifact_id}"
                    )
            elif artifact_id not in produced:
                raise AutoFlowError(f"Step {step_id} consumes unknown artifact: {artifact_id}")

    visiting: set[str] = set()
    visited: set[str] = set()
    by_id = {step["id"]: step for step in steps}

    def visit(step_id: str) -> None:
        if step_id in visiting:
            raise AutoFlowError(f"Workflow contains a dependency cycle at step: {step_id}")
        if step_id in visited:
            return
        visiting.add(step_id)
        for dependency in by_id[step_id].get("needs", []):
            visit(dependency)
        visiting.remove(step_id)
        visited.add(step_id)

    for step_id in ids:
        visit(step_id)


def validate_work_plan(path: Path) -> None:
    if not path.is_file():
        raise AutoFlowError(f"WORK_PLAN.md does not exist: {path}")
    content = path.read_text(encoding="utf-8")
    missing = [section for section in PLAN_REQUIRED_SECTIONS if section not in content]
    if missing:
        raise AutoFlowError("WORK_PLAN.md is missing sections: " + ", ".join(missing))
    if len(content.strip()) < 180 or "待填写" in content or "TODO" in content.upper():
        raise AutoFlowError("WORK_PLAN.md is still a template; complete it before PLAN_STOP approval")


def _declared_artifact_ids(workflow: dict[str, Any]) -> set[str]:
    return {
        artifact_id
        for step in workflow.get("steps", [])
        for artifact_id in step.get("outputs", [])
    }


def validate_requirement_map(
    path: Path,
    workflow: dict[str, Any],
    manifest: dict[str, Any] | None = None,
    for_delivery: bool = False,
) -> dict[str, Any]:
    data = load_json(path)
    if data.get("$schema") != REQUIREMENT_MAP_SCHEMA:
        raise AutoFlowError(f"requirement_map.json must use {REQUIREMENT_MAP_SCHEMA}")
    if data.get("workflow_id") != workflow.get("workflow_id"):
        raise AutoFlowError("requirement_map.json workflow_id does not match workflow.json")
    if data.get("status") not in {"planning", "verified"}:
        raise AutoFlowError("requirement_map.json.status must be planning or verified")
    if not str(data.get("target_tier", "")).strip():
        raise AutoFlowError("requirement_map.json.target_tier must describe the intended completion tier")
    source_files = data.get("source_files")
    if not isinstance(source_files, list) or not any(str(item).strip() for item in source_files):
        raise AutoFlowError("requirement_map.json must record at least one source requirement file")

    requirements = data.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        raise AutoFlowError("requirement_map.json must contain at least one requirement")
    declared = _declared_artifact_ids(workflow) | {"request"}
    seen: set[str] = set()
    for index, requirement in enumerate(requirements, start=1):
        if not isinstance(requirement, dict):
            raise AutoFlowError(f"Requirement {index} must be an object")
        requirement_id = str(requirement.get("id", "")).strip()
        if not requirement_id or requirement_id in seen:
            raise AutoFlowError(f"Requirement {index} has a missing or duplicate id: {requirement_id}")
        seen.add(requirement_id)
        if not str(requirement.get("description", "")).strip():
            raise AutoFlowError(f"Requirement {requirement_id} is missing description")
        acceptance = requirement.get("acceptance")
        if isinstance(acceptance, str):
            acceptance_ok = bool(acceptance.strip())
        else:
            acceptance_ok = isinstance(acceptance, list) and any(str(item).strip() for item in acceptance)
        if not acceptance_ok:
            raise AutoFlowError(f"Requirement {requirement_id} is missing acceptance criteria")
        if not isinstance(requirement.get("required"), bool):
            raise AutoFlowError(f"Requirement {requirement_id}.required must be true or false")
        evidence = requirement.get("evidence_artifacts")
        if not isinstance(evidence, list):
            raise AutoFlowError(f"Requirement {requirement_id}.evidence_artifacts must be an array")
        if requirement["required"] and not evidence:
            raise AutoFlowError(f"Required requirement {requirement_id} must map to at least one evidence artifact")
        unknown = sorted(set(evidence) - declared)
        if unknown:
            raise AutoFlowError(
                f"Requirement {requirement_id} references undeclared evidence artifacts: {', '.join(unknown)}"
            )
        validation = requirement.get("validation") or {}
        if validation.get("status") not in {"pending", "passed", "failed", "not_applicable"}:
            raise AutoFlowError(
                f"Requirement {requirement_id}.validation.status must be pending, passed, failed, or not_applicable"
            )
        if for_delivery and requirement["required"] and validation.get("status") != "passed":
            raise AutoFlowError(f"Required requirement {requirement_id} is not marked passed")

    figures = data.get("planned_figures", [])
    if not isinstance(figures, list):
        raise AutoFlowError("requirement_map.json.planned_figures must be an array")
    figure_ids: set[str] = set()
    for index, figure in enumerate(figures, start=1):
        if not isinstance(figure, dict):
            raise AutoFlowError(f"Planned figure {index} must be an object")
        figure_id = str(figure.get("id", "")).strip()
        if not figure_id or figure_id in figure_ids:
            raise AutoFlowError(f"Planned figure {index} has a missing or duplicate id: {figure_id}")
        figure_ids.add(figure_id)
        if figure.get("route") not in {"capture", "ai", "diagram", "chart"}:
            raise AutoFlowError(f"Planned figure {figure_id} has an invalid image route")
        mapped = figure.get("requirement_ids")
        if not isinstance(mapped, list) or not mapped or not set(mapped).issubset(seen):
            raise AutoFlowError(f"Planned figure {figure_id} must map to known requirement_ids")

    if for_delivery:
        if data.get("status") != "verified":
            raise AutoFlowError("requirement_map.json.status must be verified before DELIVERY_STOP approval")
        manifest_ids = set(_manifest_map(manifest or {}))
        for requirement in requirements:
            if not requirement["required"]:
                continue
            missing = sorted(set(requirement["evidence_artifacts"]) - {"request"} - manifest_ids)
            if missing:
                raise AutoFlowError(
                    f"Requirement {requirement['id']} is missing registered evidence: {', '.join(missing)}"
                )
    return data


def validate_delivery_review(
    path: Path,
    workflow: dict[str, Any],
    manifest: dict[str, Any],
    requirement_map: dict[str, Any],
) -> dict[str, Any]:
    data = load_json(path)
    if data.get("$schema") != DELIVERY_REVIEW_SCHEMA:
        raise AutoFlowError(f"delivery_review.json must use {DELIVERY_REVIEW_SCHEMA}")
    if data.get("workflow_id") != workflow.get("workflow_id"):
        raise AutoFlowError("delivery_review.json workflow_id does not match workflow.json")
    if data.get("review_completed") is not True or data.get("overall_pass") is not True:
        raise AutoFlowError("delivery_review.json must be completed with overall_pass=true")
    issues = data.get("issues_found")
    if not isinstance(issues, list) or issues:
        raise AutoFlowError("delivery_review.json.issues_found must be an empty array before approval")

    required_ids = {
        item["id"] for item in requirement_map["requirements"] if item.get("required") is True
    }
    results = data.get("requirement_results")
    if not isinstance(results, list):
        raise AutoFlowError("delivery_review.json.requirement_results must be an array")
    by_requirement = {str(item.get("id", "")): item for item in results if isinstance(item, dict)}
    if set(by_requirement) != required_ids:
        missing = sorted(required_ids - set(by_requirement))
        extra = sorted(set(by_requirement) - required_ids)
        raise AutoFlowError(
            "delivery_review.json requirement ids do not match required requirements: "
            f"missing={','.join(missing) or '-'}; extra={','.join(extra) or '-'}"
        )
    manifest_ids = set(_manifest_map(manifest))
    for requirement_id, result in by_requirement.items():
        if result.get("present") is not True or result.get("correct") is not True:
            raise AutoFlowError(f"Delivery review requirement {requirement_id} is not present and correct")
        evidence = result.get("evidence_artifacts")
        if not isinstance(evidence, list) or not evidence:
            raise AutoFlowError(f"Delivery review requirement {requirement_id} has no evidence artifacts")
        unknown = sorted(set(evidence) - {"request"} - manifest_ids)
        if unknown:
            raise AutoFlowError(
                f"Delivery review requirement {requirement_id} references missing artifacts: {', '.join(unknown)}"
            )

    artifact_results = data.get("artifact_results")
    if not isinstance(artifact_results, list):
        raise AutoFlowError("delivery_review.json.artifact_results must be an array")
    reviewed_artifacts = {str(item.get("id", "")) for item in artifact_results if isinstance(item, dict)}
    if reviewed_artifacts != manifest_ids:
        raise AutoFlowError("delivery_review.json must review every registered artifact exactly once")
    for item in artifact_results:
        if item.get("present") is not True or item.get("correct") is not True:
            raise AutoFlowError(f"Delivery artifact {item.get('id')} is not present and correct")
    return data


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_path(path: Path) -> str:
    if path.is_file():
        return _hash_file(path)
    if not path.is_dir():
        raise AutoFlowError(f"Artifact path does not exist: {path}")
    digest = hashlib.sha256()
    children: list[Path] = []
    for root, directories, files in os.walk(path):
        directories[:] = sorted(name for name in directories if name.lower() not in HASH_EXCLUDED_DIRS)
        children.extend(Path(root) / name for name in sorted(files))
    for child in sorted(children):
        digest.update(child.relative_to(path).as_posix().encode("utf-8"))
        digest.update(_hash_file(child).encode("ascii"))
    return digest.hexdigest()


def _artifact_type(path: Path) -> str:
    if path.is_dir():
        return "directory"
    suffix = path.suffix.lower()
    return {
        ".docx": "office_document",
        ".pptx": "office_presentation",
        ".xlsx": "office_spreadsheet",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".svg": "image",
        ".webp": "image",
        ".mp4": "video",
        ".mov": "video",
        ".avi": "video",
        ".zip": "package",
        ".json": "data",
        ".csv": "data",
    }.get(suffix, "file")


def validate_office_acceptance(artifacts: dict[str, Path]) -> None:
    document = artifacts.get("office.document")
    report_path = artifacts.get("office.validation")
    if not document or not document.is_file() or document.suffix.lower() not in {".docx", ".pptx", ".xlsx"}:
        raise AutoFlowError("office_acceptance requires office.document as an existing .docx/.pptx/.xlsx file")
    if not report_path or not report_path.is_file():
        raise AutoFlowError("office_acceptance requires office.validation as an existing JSON report")
    report = load_json(report_path)
    if report.get("$schema") != OFFICE_VALIDATION_SCHEMA:
        raise AutoFlowError(f"office.validation must use {OFFICE_VALIDATION_SCHEMA}")
    if report.get("overall_pass") is not True:
        raise AutoFlowError("office.validation.overall_pass must be true")
    recorded = report.get("document") or {}
    recorded_path = Path(str(recorded.get("path", ""))).expanduser().resolve()
    if recorded_path != document.resolve():
        raise AutoFlowError("office.validation document path does not match office.document")
    actual_hash = hash_path(document)
    if recorded.get("sha256") != actual_hash:
        raise AutoFlowError("office.validation document SHA-256 does not match office.document")
    checks = report.get("checks")
    if not isinstance(checks, list) or not checks:
        raise AutoFlowError("office.validation must contain non-empty checks")
    failed = [
        str(item.get("name", "unnamed"))
        for item in checks
        if not isinstance(item, dict) or item.get("status") != "passed"
    ]
    if failed:
        raise AutoFlowError("office.validation has failed or incomplete checks: " + ", ".join(failed))


def validate_video_acceptance(artifacts: dict[str, Path]) -> None:
    media = artifacts.get("video.media")
    report_path = artifacts.get("video.validation")
    if not media or not media.is_file():
        raise AutoFlowError("video_acceptance requires video.media as an existing file")
    if not report_path or not report_path.is_file():
        raise AutoFlowError("video_acceptance requires video.validation as an existing JSON report")
    report = load_json(report_path)
    if report.get("$schema") != VIDEO_VALIDATION_SCHEMA or report.get("overall_pass") is not True:
        raise AutoFlowError(f"video.validation must use {VIDEO_VALIDATION_SCHEMA} with overall_pass=true")
    if Path(str(report.get("file", ""))).expanduser().resolve() != media.resolve():
        raise AutoFlowError("video.validation file path does not match video.media")
    if report.get("sha256") != hash_path(media):
        raise AutoFlowError("video.validation SHA-256 does not match video.media")
    metadata = report.get("metadata") or {}
    if not (
        isinstance(metadata.get("duration_seconds"), (int, float))
        and metadata["duration_seconds"] > 0
        and isinstance(metadata.get("width"), int)
        and metadata["width"] > 0
        and isinstance(metadata.get("height"), int)
        and metadata["height"] > 0
        and str(metadata.get("codec", "")).strip()
    ):
        raise AutoFlowError("video.validation metadata must record positive duration/dimensions and a codec")


def validate_package_acceptance(artifacts: dict[str, Path], submit_root: Path | None = None) -> None:
    bundle = artifacts.get("package.bundle")
    manifest_path = artifacts.get("package.manifest")
    if not bundle or not bundle.exists():
        raise AutoFlowError("package_acceptance requires package.bundle as an existing folder or archive")
    if not manifest_path or not manifest_path.is_file():
        raise AutoFlowError("package_acceptance requires package.manifest as an existing JSON report")
    report = load_json(manifest_path)
    if report.get("$schema") != PACKAGE_MANIFEST_SCHEMA or report.get("overall_pass") is not True:
        raise AutoFlowError(f"package.manifest must use {PACKAGE_MANIFEST_SCHEMA} with overall_pass=true")
    output_zip = Path(str(report.get("output_zip", ""))).expanduser().resolve()
    output_folder = Path(str(report.get("output_folder", ""))).expanduser().resolve()
    if not output_zip.is_file() or not output_folder.is_dir():
        raise AutoFlowError("package.manifest output_zip and output_folder must both exist")
    if submit_root is not None:
        submit_root = submit_root.resolve()
        # The manifest is run metadata, not deliverable content: it lives in
        # .autoflow/intermediate/plans/ and is exempt. Only the deliverable
        # bundle, zip, and folder must stay below submit/.
        published_paths = (bundle.resolve(), output_zip, output_folder)
        if any(path == submit_root or submit_root not in path.parents for path in published_paths):
            raise AutoFlowError(
                "Every final package deliverable (bundle, zip, folder) must be located below autoflow/submit/; "
                "the package.manifest is run metadata and belongs in .autoflow/intermediate/plans/"
            )
    if bundle.resolve() not in {output_zip, output_folder}:
        raise AutoFlowError("package.manifest output paths do not include package.bundle")
    files = report.get("files")
    if not isinstance(files, list) or not files:
        raise AutoFlowError("package.manifest must contain at least one packaged file")
    if any(
        not isinstance(item, dict) or not item.get("requirement_ids") or not item.get("sha256")
        for item in files
    ):
        raise AutoFlowError("Every package.manifest file must record requirement_ids and SHA-256")
    checks = report.get("checks")
    if not isinstance(checks, list) or not checks or any(item.get("status") != "passed" for item in checks):
        raise AutoFlowError("package.manifest checks must all pass")


def validate_unpacked_final_locations(
    workflow: dict[str, Any], step: dict[str, Any], artifacts: dict[str, Path], submit_root: Path
) -> None:
    """Require terminal deliverables below submit when no package step exists."""
    if any(item.get("module") == "package" for item in workflow.get("steps", [])):
        return
    step_id = step["id"]
    if any(step_id in item.get("needs", []) for item in workflow.get("steps", []) if item.get("id") != step_id):
        return
    submit_root = submit_root.resolve()
    outside = [artifact_id for artifact_id, path in artifacts.items() if submit_root not in path.resolve().parents]
    if outside:
        raise AutoFlowError(
            "Final artifacts for workflows without package steps must be below autoflow/submit/: "
            + ", ".join(sorted(outside))
        )


def parse_artifact_specs(specs: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for spec in specs:
        if "=" not in spec:
            raise AutoFlowError("Artifacts must use ARTIFACT_ID=PATH syntax")
        artifact_id, raw_path = spec.split("=", 1)
        artifact_id = artifact_id.strip()
        raw_path = raw_path.strip()
        if not artifact_id or not raw_path:
            raise AutoFlowError("Artifacts must use non-empty ARTIFACT_ID=PATH values")
        result[artifact_id] = Path(raw_path).expanduser().resolve()
    return result


def _step_map(workflow: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {step["id"]: step for step in workflow["steps"]}


def sync_planning_state(workflow: dict[str, Any], state: dict[str, Any]) -> None:
    """Synchronize step state after the agent edits a custom DAG before PLAN_STOP."""
    validate_workflow_definition(workflow)
    plan_gate = state.get("gates", {}).get("plan", {})
    if plan_gate.get("status") not in {"pending", "rejected"}:
        raise AutoFlowError("Workflow steps can only be synchronized before PLAN_STOP approval")
    for item in state.get("steps", {}).values():
        if item.get("attempts", 0) or item.get("status") not in {"pending", "ready"}:
            raise AutoFlowError("Cannot synchronize a workflow after step execution has started")
    workflow["capabilities"] = workflow_capabilities(workflow["steps"])
    state["steps"] = {step["id"]: _new_step_state() for step in workflow["steps"]}
    state["status"] = "planning"
    state["updated_at"] = utc_now()


def _manifest_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in manifest.get("artifacts", [])}


def register_step_artifacts(
    workflow: dict[str, Any], manifest: dict[str, Any], step: dict[str, Any], artifacts: dict[str, Path]
) -> None:
    expected = set(step.get("outputs", []))
    supplied = set(artifacts)
    if expected != supplied:
        missing = sorted(expected - supplied)
        extra = sorted(supplied - expected)
        details = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if extra:
            details.append("unexpected=" + ",".join(extra))
        raise AutoFlowError(f"Artifacts for step {step['id']} do not match declared outputs: {'; '.join(details)}")

    existing = {
        f"{item['producer']}::{item['id']}": item for item in manifest.get("artifacts", [])
    }
    consumers = {
        artifact_id: [
            candidate["id"]
            for candidate in workflow["steps"]
            if any(
                (base_id := raw.partition("::")[2] or raw) == artifact_id
                for raw in candidate.get("inputs", [])
            )
        ]
        for artifact_id in expected
    }
    for artifact_id, path in artifacts.items():
        if not path.exists():
            raise AutoFlowError(f"Artifact path does not exist: {path}")
        record = {
            "id": artifact_id,
            "type": _artifact_type(path),
            "path": str(path),
            "producer": step["id"],
            "consumers": consumers[artifact_id],
            "sha256": hash_path(path),
            "validation": {"status": "valid", "validated_at": utc_now()},
        }
        existing[f"{step['id']}::{artifact_id}"] = record
    manifest["artifacts"] = sorted(existing.values(), key=lambda item: item["id"])
    manifest["updated_at"] = utc_now()


def _validate_candidates(candidates: list[dict[str, Any]]) -> None:
    if not 3 <= len(candidates) <= 5:
        raise AutoFlowError("SOURCE_STOP requires three to five genuinely usable GitHub candidates")
    score_keys = {"requirement_fit", "modification_distance", "stack", "buildability", "maintenance", "license"}
    for index, candidate in enumerate(candidates, start=1):
        required = ("rank", "name", "repository_url", "revision", "license", "judgment")
        missing = [key for key in required if not str(candidate.get(key, "")).strip()]
        scores = candidate.get("scores") or {}
        if missing or not score_keys.issubset(scores):
            details = missing + (["scores"] if not score_keys.issubset(scores) else [])
            raise AutoFlowError(f"Candidate {index} is missing: {', '.join(details)}")
        invalid_scores = [key for key in score_keys if not isinstance(scores.get(key), (int, float)) or not 0 <= scores[key] <= 5]
        if invalid_scores:
            raise AutoFlowError(f"Candidate {index} has invalid 0-5 scores: {', '.join(sorted(invalid_scores))}")


def validate_source_plan(path: Path, for_approval: bool = False) -> str:
    plan = load_json(path)
    status = str(plan.get("status", ""))
    queries = plan.get("queries", [])
    if not isinstance(queries, list) or not any(str(query).strip() for query in queries):
        raise AutoFlowError("source_candidates.json must record at least one real search query")
    candidates = plan.get("candidates", [])
    if not isinstance(candidates, list):
        raise AutoFlowError("source_candidates.json.candidates must be an array")
    if status == "awaiting_user_choice":
        if not candidates:
            raise AutoFlowError("awaiting_user_choice requires at least one GitHub candidate")
        _validate_candidates(candidates)
        if for_approval:
            raise AutoFlowError("Record the user's selected candidate before approving SOURCE_STOP")
        return status
    if status in {"selected", "completed"}:
        if not candidates:
            raise AutoFlowError("A selected source plan must retain its candidate list")
        _validate_candidates(candidates)
        selected = plan.get("selected_candidate") or {}
        required = ("name", "repository_url", "selected_revision", "selection_rationale")
        missing = [key for key in required if not str(selected.get(key, "")).strip()]
        if missing:
            raise AutoFlowError("selected_candidate is missing: " + ", ".join(missing))
        choice = plan.get("user_choice") or {}
        if choice.get("status") != "confirmed":
            raise AutoFlowError("source_candidates.json.user_choice.status must be confirmed")
        return status
    if status == "no_suitable_project":
        if candidates:
            raise AutoFlowError("no_suitable_project requires an empty candidate list")
        fallback = plan.get("fallback") or {}
        if not fallback.get("used") or not str(fallback.get("reason", "")).strip():
            raise AutoFlowError("No-candidate fallback requires used=true and a reason")
        rejected = plan.get("rejected_candidates") or []
        search_notes = str(plan.get("search_notes", "")).strip()
        if not rejected and not search_notes:
            raise AutoFlowError("No-candidate fallback must record rejected projects or search_notes")
        for index, item in enumerate(rejected, start=1):
            if not str(item.get("repository_url", "")).strip() or not str(item.get("reason", "")).strip():
                raise AutoFlowError(f"Rejected candidate {index} must include repository_url and reason")
        if for_approval:
            raise AutoFlowError("SOURCE_STOP is not approved when no candidates exist; mark it not_applicable")
        return status
    raise AutoFlowError(
        "source_candidates.json.status must be awaiting_user_choice, selected, completed, or no_suitable_project"
    )


def validate_build_completion(artifacts: dict[str, Path], source_plan_path: Path) -> None:
    project_path = artifacts.get("project.source")
    result_path = artifacts.get("task.result")
    if not project_path or not project_path.is_dir():
        raise AutoFlowError("task.build must produce project.source as an existing directory")
    if not any(project_path.iterdir()):
        raise AutoFlowError("project.source is empty")
    if not any((project_path / name).is_file() for name in ("README.md", "README.txt", "readme.md")):
        raise AutoFlowError("project.source must contain startup/handoff documentation (README.md)")
    if not result_path or not result_path.is_file():
        raise AutoFlowError("task.build must produce task.result as a JSON file")
    result = load_json(result_path)
    source_plan = load_json(source_plan_path)
    source_mode = result.get("source_mode")
    expected_mode = "github_adaptation" if source_plan.get("status") in {"selected", "completed"} else "from_scratch"
    if source_mode != expected_mode:
        raise AutoFlowError(f"task.result.source_mode must be {expected_mode}")
    baseline = result.get("baseline") or {}
    if baseline.get("status") != "passed" or not baseline.get("commands") or not str(baseline.get("result", "")).strip():
        raise AutoFlowError("task.result.baseline must record passed status, commands, and result")
    changed_files = result.get("changed_files") or []
    if not changed_files:
        raise AutoFlowError("task.result.changed_files must record the implemented/adapted files")
    verification = result.get("verification_results") or []
    if not verification or not any(item.get("status") == "passed" for item in verification if isinstance(item, dict)):
        raise AutoFlowError("task.result.verification_results must include at least one passed check")
    environment_path = artifacts.get("task.environment")
    if environment_path:
        validate_environment_report(environment_path, project_path)
    if expected_mode == "github_adaptation":
        if not (project_path / ".git").exists():
            raise AutoFlowError("A GitHub adaptation must retain a .git repository in project.source")
        selected = source_plan.get("selected_candidate") or {}
        upstream = result.get("upstream") or {}
        if upstream.get("repository_url") != selected.get("repository_url"):
            raise AutoFlowError("task.result upstream URL does not match the user-selected candidate")
        if upstream.get("selected_revision") != selected.get("selected_revision"):
            raise AutoFlowError("task.result upstream revision does not match the selected revision")


def validate_environment_report(report_path: Path, project_path: Path) -> dict[str, Any]:
    if not report_path.is_file():
        raise AutoFlowError("task.environment must be an existing JSON report")
    report = load_json(report_path)
    if report.get("$schema") != ENVIRONMENT_REPORT_SCHEMA:
        raise AutoFlowError(f"task.environment must use {ENVIRONMENT_REPORT_SCHEMA}")
    if report.get("command") != "agent-init":
        raise AutoFlowError("task.environment command must be agent-init")
    if report.get("status") != "ready":
        raise AutoFlowError("task.environment status must be ready")
    reported_project = Path(str(report.get("project", ""))).expanduser().resolve()
    if reported_project != project_path.resolve():
        raise AutoFlowError("task.environment project does not match project.source")
    runtime_root = Path(str(report.get("runtime_root", ""))).expanduser().resolve()
    project_root = project_path.resolve()
    if runtime_root == project_root or runtime_root in project_root.parents or project_root in runtime_root.parents:
        raise AutoFlowError("task.environment runtime_root must be outside project.source")
    if not runtime_root.is_dir():
        raise AutoFlowError("task.environment runtime_root does not exist")
    if report.get("missing_tools"):
        raise AutoFlowError("task.environment still reports missing tools")
    if report.get("project_kinds") and not report.get("checks"):
        raise AutoFlowError("task.environment must contain verification checks for every detected project stack")
    failed_checks = [item.get("name", "unknown") for item in report.get("checks", []) if item.get("status") != "passed"]
    if failed_checks:
        raise AutoFlowError("task.environment checks failed: " + ", ".join(failed_checks))
    return report


def _set_gate(state: dict[str, Any], gate_name: str, status: str, note: str, active: bool) -> None:
    gate = state["gates"][gate_name]
    previous = gate.get("status")
    now = utc_now()
    if gate.get("activated_at") and previous in {"pending", "rejected"} and status != previous:
        gate["wait_seconds"] = int(gate.get("wait_seconds", 0)) + _elapsed_seconds(gate["activated_at"], now)
    gate.setdefault("history", []).append(
        {"from": previous, "to": status, "note": note, "at": now}
    )
    gate.update(
        {
            "status": status,
            "note": note,
            "active": active,
            "updated_at": now,
            "activated_at": now if active and status in {"pending", "rejected"} else "",
        }
    )
    if gate_name == "visual" and status == "pending":
        gate["approved_artifacts"] = []
    state["updated_at"] = utc_now()


def _active_blocking_gate(state: dict[str, Any]) -> str | None:
    for gate_name in ("plan", "source", "visual"):
        gate = state["gates"][gate_name]
        if gate.get("active") and gate.get("status") in {"pending", "rejected"}:
            return gate_name
    return None


def refresh_ready(workflow: dict[str, Any], state: dict[str, Any]) -> list[str]:
    blocker = _active_blocking_gate(state)
    if blocker:
        for item in state["steps"].values():
            if item["status"] == "ready":
                item["status"] = "pending"
                item["updated_at"] = utc_now()
        return []

    ready: list[str] = []
    for step in workflow["steps"]:
        step_state = state["steps"][step["id"]]
        if step_state["status"] not in {"pending", "ready"}:
            continue
        dependency_states = [state["steps"][dep]["status"] for dep in step.get("needs", [])]
        can_run = all(status in {"completed", "skipped"} for status in dependency_states)
        if can_run:
            step_state["status"] = "ready"
            step_state["updated_at"] = utc_now()
            ready.append(step["id"])
        elif step_state["status"] == "ready":
            step_state["status"] = "pending"
            step_state["updated_at"] = utc_now()
    state["updated_at"] = utc_now()
    return ready


def _refresh_delivery(workflow: dict[str, Any], state: dict[str, Any]) -> None:
    step_statuses = [item["status"] for item in state["steps"].values()]
    if "failed" in step_statuses:
        state["status"] = "failed"
        state["gates"]["delivery"]["active"] = False
        return
    if "blocked" in step_statuses:
        state["status"] = "blocked"
        state["gates"]["delivery"]["active"] = False
        return
    all_done = all(item["status"] in {"completed", "skipped"} for item in state["steps"].values())
    blocker = _active_blocking_gate(state)
    gate = state["gates"]["delivery"]
    if all_done and blocker is None and state.get("status") != "completed":
        if not gate.get("active"):
            _set_gate(state, "delivery", "pending", "All workflow steps completed; delivery review required", True)
        state["status"] = "awaiting_delivery_approval"
    elif state.get("status") != "completed":
        state["status"] = "running" if state["gates"]["plan"]["status"] == "approved" else "planning"


def transition_step(
    workflow: dict[str, Any],
    state: dict[str, Any],
    manifest: dict[str, Any],
    paths: dict[str, Path],
    step_id: str,
    target: str,
    note: str,
    artifacts: dict[str, Path],
) -> None:
    steps = _step_map(workflow)
    if step_id not in steps:
        raise AutoFlowError(f"Unknown step: {step_id}")
    if target not in STEP_STATUSES - {"pending", "ready"}:
        raise AutoFlowError("transition --to must be running, blocked, completed, failed, or skipped")
    current = state["steps"][step_id]["status"]
    allowed = {
        "pending": {"running", "skipped"},
        "ready": {"running", "skipped"},
        "running": {"blocked", "completed", "failed"},
        "blocked": {"running", "failed"},
        "failed": {"running"},
        "completed": set(),
        "skipped": set(),
    }
    if target not in allowed[current]:
        raise AutoFlowError(f"Illegal step transition for {step_id}: {current} -> {target}")
    step = steps[step_id]
    if target == "skipped" and not step.get("optional", False):
        raise AutoFlowError(f"Step {step_id} is not optional and cannot be skipped")
    if target == "running":
        blocker = _active_blocking_gate(state)
        if blocker:
            raise AutoFlowError(f"Step {step_id} is blocked by {blocker.upper()}_STOP")
        unmet = [dep for dep in step.get("needs", []) if state["steps"][dep]["status"] not in {"completed", "skipped"}]
        if unmet:
            raise AutoFlowError(f"Step {step_id} has incomplete dependencies: {', '.join(unmet)}")
        step_state = state["steps"][step_id]
        max_attempts = int(step.get("max_attempts", 3))
        revision_attempts = int(step_state.get("revision_attempts", 0))
        if revision_attempts >= max_attempts:
            raise AutoFlowError(
                f"Step {step_id} exhausted its revision attempt budget ({max_attempts}); "
                "diagnose the repeated failure and use revise before another attempt"
            )
        step_state["attempts"] += 1
        step_state["revision_attempts"] = revision_attempts + 1
        step_state["started_at"] = utc_now()
        step_state.setdefault("history", []).append(
            {"from": current, "to": target, "note": note, "at": step_state["started_at"]}
        )
    if target == "completed":
        if step.get("module") == "task" and step.get("action") == "build":
            validate_build_completion(artifacts, paths["source_plan"])
        if step.get("validator") == "office_acceptance":
            validate_office_acceptance(artifacts)
        if step.get("validator") == "video_acceptance":
            validate_video_acceptance(artifacts)
        if step.get("validator") == "package_acceptance":
            validate_package_acceptance(artifacts, paths["submit"])
        validate_unpacked_final_locations(workflow, step, artifacts, paths["submit"])
        register_step_artifacts(workflow, manifest, step, artifacts)
    elif artifacts:
        raise AutoFlowError("--artifact may only be used when completing a step")

    now = utc_now()
    step_state = state["steps"][step_id]
    if target != "running" and step_state.get("started_at"):
        step_state["active_seconds"] = int(step_state.get("active_seconds", 0)) + _elapsed_seconds(
            step_state["started_at"], now
        )
        step_state["started_at"] = ""
    if target == "completed":
        step_state["completed_at"] = now
    if target != "running":
        step_state.setdefault("history", []).append(
            {"from": current, "to": target, "note": note, "at": now}
        )
    step_state.update({"status": target, "note": note, "updated_at": now})

    if target == "completed" and step.get("gate_after") == "source":
        source_status = validate_source_plan(paths["source_plan"])
        if source_status == "awaiting_user_choice":
            state["gates"]["source"]["required"] = True
            _set_gate(state, "source", "pending", "GitHub candidates require explicit user selection", True)
        elif source_status == "no_suitable_project":
            state["gates"]["source"]["required"] = False
            _set_gate(state, "source", "not_applicable", "No suitable project; use recorded from-scratch fallback", False)
        else:
            state["gates"]["source"]["required"] = True
            _set_gate(state, "source", "pending", "Selected source still requires explicit user approval", True)

    if target == "completed" and step.get("gate_after") == "visual":
        state["gates"]["visual"]["required"] = True
        _set_gate(state, "visual", "pending", f"Visual artifacts from {step_id} require user review", True)

    refresh_ready(workflow, state)
    _refresh_delivery(workflow, state)


def revise_step(
    workflow: dict[str, Any],
    state: dict[str, Any],
    manifest: dict[str, Any],
    paths: dict[str, Path],
    step_id: str,
    reason: str,
) -> list[str]:
    """Reopen an executed step and invalidate every transitive downstream consumer."""
    if not reason.strip():
        raise AutoFlowError("revise requires a non-empty reason")
    if state.get("status") == "completed" or state.get("gates", {}).get("delivery", {}).get("status") == "approved":
        raise AutoFlowError("A delivered workflow is immutable; initialize a new revision run")
    steps = _step_map(workflow)
    if step_id not in steps:
        raise AutoFlowError(f"Unknown step: {step_id}")
    current_status = state["steps"][step_id]["status"]
    if current_status in {"pending", "ready"}:
        raise AutoFlowError(f"Step {step_id} has not executed and does not need revision")

    affected = {step_id}
    changed = True
    while changed:
        changed = False
        for candidate in workflow["steps"]:
            if candidate["id"] not in affected and any(dep in affected for dep in candidate.get("needs", [])):
                affected.add(candidate["id"])
                changed = True
    affected_order = [candidate["id"] for candidate in workflow["steps"] if candidate["id"] in affected]

    revision = int(state.get("revision", 0)) + 1
    now = utc_now()
    affected_outputs = {
        artifact_id
        for candidate in workflow["steps"]
        if candidate["id"] in affected
        for artifact_id in candidate.get("outputs", [])
    }
    retained = []
    history = manifest.setdefault("artifact_history", [])
    for artifact in manifest.get("artifacts", []):
        if artifact.get("producer") in affected or artifact.get("id") in affected_outputs:
            history.append(
                {
                    **artifact,
                    "status": "superseded",
                    "superseded_at": now,
                    "superseded_by_revision": revision,
                    "reason": reason.strip(),
                }
            )
        else:
            retained.append(artifact)
    manifest["artifacts"] = sorted(retained, key=lambda item: item["id"])
    manifest["updated_at"] = now

    for candidate in workflow["steps"]:
        candidate_id = candidate["id"]
        if candidate_id not in affected:
            continue
        old = state["steps"][candidate_id]
        old.setdefault("history", []).append(
            {
                "from": old.get("status"),
                "to": "pending",
                "note": f"revision {revision}: {reason.strip()}",
                "at": now,
            }
        )
        old.update(
            {
                "status": "pending",
                "revision": int(old.get("revision", 0)) + 1,
                "revision_attempts": 0,
                "note": f"Revision {revision}: {reason.strip()}",
                "started_at": "",
                "completed_at": "",
                "updated_at": now,
            }
        )

    affected_steps = [steps[item] for item in affected]
    if any(step.get("gate_after") == "source" for step in affected_steps):
        _set_gate(state, "source", "not_applicable", f"Revision {revision} invalidated source evidence", False)
    if any(step.get("gate_after") == "visual" for step in affected_steps):
        _set_gate(state, "visual", "not_applicable", f"Revision {revision} invalidated visual evidence", False)
    _set_gate(state, "delivery", "pending", f"Revision {revision} requires a new delivery review", False)

    if paths["requirement_map"].is_file():
        requirement_map = load_json(paths["requirement_map"])
        requirement_map["status"] = "planning"
        for requirement in requirement_map.get("requirements", []):
            if set(requirement.get("evidence_artifacts", [])) & affected_outputs:
                requirement["validation"] = {
                    "status": "pending",
                    "notes": f"Invalidated by revision {revision}",
                }
        requirement_map["updated_at"] = now
        save_json(paths["requirement_map"], requirement_map)
    if paths["delivery_review"].is_file():
        delivery_review = load_json(paths["delivery_review"])
        delivery_review.update(
            {
                "review_completed": False,
                "requirement_results": [],
                "artifact_results": [],
                "issues_found": [],
                "overall_pass": False,
                "reviewer_notes": f"Invalidated by revision {revision}: {reason.strip()}",
                "updated_at": now,
            }
        )
        save_json(paths["delivery_review"], delivery_review)

    state["revision"] = revision
    state.setdefault("revision_history", []).append(
        {
            "revision": revision,
            "root_step": step_id,
            "affected_steps": affected_order,
            "reason": reason.strip(),
            "at": now,
        }
    )
    state["status"] = "running"
    state["updated_at"] = now
    refresh_ready(workflow, state)
    return affected_order


def _validate_artifacts(manifest: dict[str, Any], deep: bool = True) -> list[str]:
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    for item in manifest.get("artifacts", []):
        artifact_id = item.get("id")
        producer = str(item.get("producer", ""))
        key = (producer, artifact_id)
        if not artifact_id or key in seen:
            errors.append(f"Invalid or duplicate artifact id: {artifact_id}")
            continue
        seen.add(key)
        path = Path(str(item.get("path", "")))
        if not path.exists():
            errors.append(f"Artifact path missing: {artifact_id} -> {path}")
            continue
        if deep:
            actual = hash_path(path)
            if actual != item.get("sha256"):
                errors.append(f"Artifact changed after validation: {artifact_id} -> {path}")
        if (item.get("validation") or {}).get("status") != "valid":
            errors.append(f"Artifact is not marked valid: {artifact_id}")
    return errors


def _refresh_manifest_artifact(manifest: dict[str, Any], artifact_id: str) -> None:
    item = _manifest_map(manifest).get(artifact_id)
    if not item:
        raise AutoFlowError(f"Artifact manifest is missing: {artifact_id}")
    path = Path(item["path"])
    if not path.exists():
        raise AutoFlowError(f"Artifact path does not exist: {path}")
    item["sha256"] = hash_path(path)
    item["validation"] = {"status": "valid", "validated_at": utc_now()}
    manifest["updated_at"] = utc_now()


def approve_gate(
    workflow: dict[str, Any], state: dict[str, Any], manifest: dict[str, Any], paths: dict[str, Path], gate_name: str, note: str
) -> None:
    if gate_name not in GATE_NAMES:
        raise AutoFlowError(f"Unknown gate: {gate_name}")
    if not note.strip():
        raise AutoFlowError("Gate approval requires a non-empty note quoting or summarizing explicit user approval")
    gate = state["gates"][gate_name]
    if not gate.get("active") or gate.get("status") not in {"pending", "rejected"}:
        raise AutoFlowError(f"{gate_name.upper()}_STOP is not awaiting approval")
    if gate_name == "plan":
        sync_planning_state(workflow, state)
        validate_work_plan(paths["work_plan"])
        validate_workflow_definition(workflow)
        validate_capabilities(workflow)
        validate_requirement_map(paths["requirement_map"], workflow)
    elif gate_name == "source":
        validate_source_plan(paths["source_plan"], for_approval=True)
        _refresh_manifest_artifact(manifest, "source.plan")
    elif gate_name == "visual":
        visual_steps = {
            step["id"] for step in workflow["steps"] if step["module"] in VISUAL_MODULES and state["steps"][step["id"]]["status"] == "completed"
        }
        visual_artifacts = [item for item in manifest.get("artifacts", []) if item.get("producer") in visual_steps]
        if not visual_artifacts:
            raise AutoFlowError("VISUAL_STOP cannot be approved without completed visual artifacts")
        artifact_errors = _validate_artifacts({"artifacts": visual_artifacts})
        if artifact_errors:
            raise AutoFlowError("Visual artifact validation failed: " + "; ".join(artifact_errors))
        gate["approved_artifacts"] = [
            {"id": item["id"], "sha256": item["sha256"]} for item in visual_artifacts
        ]
    elif gate_name == "delivery":
        if not all(item["status"] in {"completed", "skipped"} for item in state["steps"].values()):
            raise AutoFlowError("DELIVERY_STOP cannot be approved before all steps complete")
        artifact_errors = _validate_artifacts(manifest)
        if artifact_errors:
            raise AutoFlowError("Delivery artifact validation failed: " + "; ".join(artifact_errors))
        requirement_map = validate_requirement_map(
            paths["requirement_map"], workflow, manifest=manifest, for_delivery=True
        )
        validate_delivery_review(paths["delivery_review"], workflow, manifest, requirement_map)

    _set_gate(state, gate_name, "approved", note.strip(), False)
    if gate_name == "delivery":
        state["status"] = "completed"
    else:
        state["status"] = "running"
        refresh_ready(workflow, state)
        _refresh_delivery(workflow, state)


def set_gate_state(
    workflow: dict[str, Any], state: dict[str, Any], paths: dict[str, Path], gate_name: str, target: str, note: str
) -> None:
    if gate_name not in GATE_NAMES:
        raise AutoFlowError(f"Unknown gate: {gate_name}")
    if target not in {"rejected", "not_applicable"}:
        raise AutoFlowError("gate --to must be rejected or not_applicable")
    if not note.strip():
        raise AutoFlowError("Changing a gate requires a non-empty note")
    if gate_name in {"plan", "delivery"} and target == "not_applicable":
        raise AutoFlowError(f"{gate_name.upper()}_STOP is mandatory and cannot be not_applicable")
    gate = state["gates"][gate_name]
    if target == "rejected" and not gate.get("active"):
        raise AutoFlowError(f"{gate_name.upper()}_STOP is not active and cannot be rejected")
    if target == "not_applicable" and gate_name == "source":
        if validate_source_plan(paths["source_plan"]) != "no_suitable_project":
            raise AutoFlowError("SOURCE_STOP is not applicable only after a validated no-candidate search")
    if target == "not_applicable" and gate_name == "visual":
        visual_steps = [step for step in workflow["steps"] if step.get("gate_after") == "visual"]
        if any(state["steps"][step["id"]]["status"] != "skipped" for step in visual_steps):
            raise AutoFlowError("VISUAL_STOP is not applicable only when every visual-gated step is skipped")
    _set_gate(state, gate_name, target, note.strip(), target == "rejected")
    state["status"] = "blocked" if target == "rejected" else state.get("status", "running")


def validate_run(
    workflow: dict[str, Any],
    state: dict[str, Any],
    manifest: dict[str, Any],
    paths: dict[str, Path],
    deep: bool = True,
) -> list[str]:
    errors: list[str] = []
    try:
        validate_workflow_definition(workflow)
    except AutoFlowError as exc:
        errors.append(str(exc))
    try:
        validate_capabilities(workflow)
    except AutoFlowError as exc:
        errors.append(str(exc))
    if state.get("schema_version") != SCHEMA_VERSION or state.get("workflow_id") != workflow.get("workflow_id"):
        errors.append("run_state.json does not match workflow schema/id")
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("workflow_id") != workflow.get("workflow_id"):
        errors.append("artifact_manifest.json does not match workflow schema/id")
    request_file = Path(str(workflow.get("request_file", "")))
    if not request_file.is_file():
        errors.append(f"Request file does not exist: {request_file}")
    output_dir = Path(str(workflow.get("output_dir", ""))).resolve()
    if output_dir != paths["root"]:
        errors.append(f"workflow.output_dir does not match the run directory: {output_dir}")
    if workflow.get("run_layout") != RUN_LAYOUT_SCHEMA:
        errors.append(f"workflow.run_layout must be {RUN_LAYOUT_SCHEMA}")
    declared_directories = workflow.get("directories")
    if not isinstance(declared_directories, dict):
        errors.append("workflow.directories is missing from the run layout")
    else:
        for name in ("root", "internal", "scripts", "runtime", "intermediate", "verification", "config", "plans", "artifacts", "submit"):
            declared = Path(str(declared_directories.get(name, ""))).expanduser().resolve()
            if declared != paths[name]:
                errors.append(f"workflow.directories.{name} does not match the run layout: {declared}")
    expected_steps = {step["id"] for step in workflow.get("steps", [])}
    if set(state.get("steps", {})) != expected_steps:
        errors.append("run_state.json step ids do not match workflow.json")
    for step_id, item in state.get("steps", {}).items():
        if item.get("status") not in STEP_STATUSES:
            errors.append(f"Invalid status for step {step_id}: {item.get('status')}")
    for gate_name in GATE_NAMES:
        gate = (state.get("gates") or {}).get(gate_name)
        if not gate:
            errors.append(f"Missing gate state: {gate_name}")
        elif gate.get("status") not in GATE_STATUSES:
            errors.append(f"Invalid status for gate {gate_name}: {gate.get('status')}")
    errors.extend(_validate_artifacts(manifest, deep=deep))

    manifest_ids = set(_manifest_map(manifest))
    by_id = _step_map(workflow) if workflow.get("steps") else {}
    for step_id, item in state.get("steps", {}).items():
        if item.get("status") == "completed" and step_id in by_id:
            missing = set(by_id[step_id].get("outputs", [])) - manifest_ids
            if missing:
                errors.append(f"Completed step {step_id} is missing artifacts: {', '.join(sorted(missing))}")
    try:
        validate_work_plan(paths["work_plan"])
    except AutoFlowError as exc:
        errors.append(str(exc))
    try:
        validate_requirement_map(paths["requirement_map"], workflow)
    except AutoFlowError as exc:
        errors.append(str(exc))
    source_gate = state.get("gates", {}).get("source", {})
    if source_gate.get("status") == "approved":
        try:
            validate_source_plan(paths["source_plan"], for_approval=True)
        except AutoFlowError as exc:
            errors.append(str(exc))
    if state.get("status") == "completed" and state.get("gates", {}).get("delivery", {}).get("status") != "approved":
        errors.append("A completed run must have an approved DELIVERY_STOP")
    if state.get("gates", {}).get("delivery", {}).get("status") == "approved":
        try:
            requirement_map = validate_requirement_map(
                paths["requirement_map"], workflow, manifest=manifest, for_delivery=True
            )
            validate_delivery_review(paths["delivery_review"], workflow, manifest, requirement_map)
        except AutoFlowError as exc:
            errors.append(str(exc))
    return errors


def save_run(state: dict[str, Any], manifest: dict[str, Any], paths: dict[str, Path]) -> None:
    state["updated_at"] = utc_now()
    manifest["updated_at"] = utc_now()
    save_json(paths["state"], state)
    save_json(paths["manifest"], manifest)


def route_for_direct(module: str, action: str, format_name: str | None = None, compact: bool = True) -> dict[str, Any]:
    """Resolve one local module without creating a managed workflow run."""
    if module not in MODULE_ACTIONS:
        raise AutoFlowError(f"Unknown direct module: {module}")
    if action not in MODULE_ACTIONS[module]:
        allowed = ", ".join(sorted(MODULE_ACTIONS[module]))
        raise AutoFlowError(f"Unknown direct action {module}.{action}; allowed actions: {allowed}")
    if module == "office" and format_name not in OFFICE_FORMATS:
        raise AutoFlowError(
            f"Office direct route requires --format in {', '.join(sorted(OFFICE_FORMATS))}"
        )

    step: dict[str, Any] = {
        "id": "direct",
        "module": module,
        "action": action,
        "needs": [],
        "inputs": ["request"],
        "outputs": [f"{module}.result"],
        "optional": False,
    }
    if module == "office":
        step["format"] = format_name

    workflow = {
        "workflow_id": "direct",
        "recipe": "direct",
        "steps": [step],
        "capabilities": workflow_capabilities([step]),
    }
    state = {"steps": {"direct": {"status": "ready"}}}
    payload = route_for_workflow(workflow, state, "direct", compact=compact)
    payload["$schema"] = "autoflow/direct-route/1.0"
    payload["execution_mode"] = "direct"
    payload["workflow_files_created"] = False
    payload["stop_gates"] = []
    payload["output_policy"] = {
        "location": "task_workspace_submit",
        "workspace_initialization_required": True,
        "workspace_directories": [".autoflow/intermediate", ".autoflow/runtime", "submit"],
        "submit_required": True,
        "managed_submit_required": False,
        "minimum_requested_outputs": True,
        "sidecars": "only_when_requested_or_required",
        "sidecar_formats_are_one_artifact_family": True,
    }
    return payload


def route_for_workflow(
    workflow: dict[str, Any], state: dict[str, Any], step_id: str | None = None, compact: bool = True
) -> dict[str, Any]:
    root = Path(__file__).resolve().parent.parent
    by_id = _step_map(workflow)
    if step_id:
        if step_id not in by_id:
            raise AutoFlowError(f"Unknown workflow step: {step_id}")
        selected = [by_id[step_id]]
    else:
        selected = workflow.get("steps", [])

    office = (workflow.get("capabilities") or {}).get("office") or detect_office_backend()
    video = (workflow.get("capabilities") or {}).get("video") or detect_video_backend()
    image = (workflow.get("capabilities") or {}).get("image") or detect_image_backend()
    impeccable = (workflow.get("capabilities") or {}).get("impeccable") or detect_impeccable_backend()
    routed_steps: list[dict[str, Any]] = []
    for step in selected:
        if step.get("module") == "office" and step.get("format") == "word":
            selected_skill = (office.get("word_backend") or {}).get("skill_file", "")
            if selected_skill and not Path(selected_skill).is_file():
                raise AutoFlowError(f"Selected Word Skill is no longer installed: {selected_skill}")
        status = (state.get("steps", {}).get(step["id"]) or {}).get("status", "pending")
        names: list[str] = []
        if step.get("design_backend") == "integrated-impeccable":
            names.append("impeccable")

        capability_names: list[str] = []
        if step.get("module") == "office":
            capability_names.append("office")
        if step.get("module") == "video":
            capability_names.append("video")
        if step.get("module") == "image":
            capability_names.append("image")
        if step.get("design_backend") == "integrated-impeccable":
            capability_names.append("impeccable")
        capability_files: list[str] = []
        if step.get("module") == "office":
            capability_files = [
                str(office.get(key, ""))
                for key in ("engine_script", "validator_script", "exe")
                if str(office.get(key, ""))
            ]
            if step.get("format") == "word" and (office.get("word_backend") or {}).get("skill_file"):
                capability_files.append(office["word_backend"]["skill_file"])
        if step.get("module") == "video":
            capability_files = [
                str(video.get(key, ""))
                for key in ("script", "ffmpeg", "ffprobe")
                if str(video.get(key, ""))
            ]
        if step.get("module") == "image":
            image_action = (image.get("actions") or {}).get(step.get("action", ""), {})
            capability_files = list(image_action.get("files", []))
        routed_capabilities = {
            name: (workflow.get("capabilities") or {}).get(name, {})
            for name in capability_names
        }
        if step.get("module") == "image":
            routed_capabilities["image"] = image_capability_for_action(image, step.get("action", ""))
        module_file = (
            root / "modules" / step["module"] / f"{step.get('format', '')}.md"
            if step.get("module") == "office"
            else root / "modules" / f"{step['module']}.md"
        ).resolve()
        module_files = (
            [str((root / "modules" / "office.md").resolve()), str(module_file)]
            if step.get("module") == "office" else [str(module_file)]
        )
        routed_steps.append(
            {
                "id": step["id"],
                "module": step["module"],
                "action": step["action"],
                "status": status,
                "module_file": str(module_file),
                "module_files": module_files,
                "skill_names": names,
                "skill_files": [
                    impeccable.get("skill_file", "")
                    if name == "impeccable"
                    else ""
                    for name in names
                ] + ([office["word_backend"]["skill_file"]] if step.get("module") == "office" and step.get("format") == "word" and (office.get("word_backend") or {}).get("skill_file") else []),
                "capability_files": capability_files,
                "capability_names": capability_names,
                "capabilities": routed_capabilities,
                **({"authoring_skill": office["word_backend"]["selected"]} if step.get("module") == "office" and step.get("format") == "word" and office.get("word_backend") else {}),
            }
        )

    payload: dict[str, Any] = {
        "$schema": "autoflow/route/1.0",
        "workflow_id": workflow.get("workflow_id", ""),
        "recipe": workflow.get("recipe", ""),
        "mode": "compact" if compact else "full",
        "global_skill_names": [],
        "steps": routed_steps,
    }
    if step_id:
        payload["step"] = routed_steps[0]
        payload.update(routed_steps[0])
    return payload


def gate_review_packet(
    workflow: dict[str, Any],
    state: dict[str, Any],
    manifest: dict[str, Any],
    paths: dict[str, Path],
    gate_name: str,
) -> dict[str, Any]:
    """Build the information packet that must be shown before requesting approval."""
    if gate_name not in GATE_NAMES:
        raise AutoFlowError(f"Unknown gate: {gate_name}")
    gate = (state.get("gates") or {}).get(gate_name) or {}
    if not gate.get("active"):
        raise AutoFlowError(f"{gate_name.upper()}_STOP is not active")

    packet: dict[str, Any] = {
        "$schema": "autoflow/gate-review/1.0",
        "workflow_id": workflow.get("workflow_id", ""),
        "gate": gate_name,
        "gate_status": gate.get("status", ""),
        "must_show_before_approval": True,
    }

    if gate_name == "plan":
        validate_workflow_definition(workflow)
        validate_capabilities(workflow)
        validate_work_plan(paths["work_plan"])
        requirement_map = validate_requirement_map(paths["requirement_map"], workflow)
        packet.update(
            {
                "title": "Execution plan review",
                "summary": {
                    "name": workflow.get("name", ""),
                    "recipe": workflow.get("recipe", ""),
                    "recipe_description": workflow.get("recipe_description", ""),
                    "steps": [
                        {
                            "id": step["id"],
                            "operation": f"{step['module']}.{step['action']}",
                            "needs": step.get("needs", []),
                            "outputs": step.get("outputs", []),
                        }
                        for step in workflow.get("steps", [])
                    ],
                    "required_requirements": [
                        {
                            "id": item.get("id", ""),
                            "description": item.get("description", ""),
                            "evidence_artifacts": item.get("evidence_artifacts", []),
                        }
                        for item in requirement_map.get("requirements", [])
                        if item.get("required")
                    ],
                    "planned_figures": requirement_map.get("planned_figures", []),
                },
                "review_file": str(paths["work_plan"].resolve()),
                "supporting_files": [
                    str(paths["workflow"].resolve()),
                    str(paths["requirement_map"].resolve()),
                ],
                "required_display": [
                    "goal and scope",
                    "recipe and ordered steps",
                    "expected deliverables and paths or types",
                    "important decisions, exclusions, and risks",
                    "absolute WORK_PLAN.md path",
                ],
                "decision_prompt": "Approve this plan, or identify the step/scope/output that must change.",
            }
        )
        return packet

    if gate_name == "source":
        source_status = validate_source_plan(paths["source_plan"])
        source_plan = load_json(paths["source_plan"])
        packet.update(
            {
                "title": "GitHub source selection review",
                "source_status": source_status,
                "queries": source_plan.get("queries", []),
                "criteria": source_plan.get("criteria")
                or [
                    "requirement_fit",
                    "modification_distance",
                    "stack",
                    "buildability",
                    "maintenance",
                    "license",
                ],
                "candidates": source_plan.get("candidates", []),
                "fallback": source_plan.get("fallback", {}),
                "review_file": str(paths["source_plan"].resolve()),
                "required_display": [
                    "real search queries",
                    "three to five candidate names and repository links",
                    "scores, license, pinned revision, fit, modification cost, and risks",
                    "recommended candidate and why",
                    "absolute source_candidates.json path",
                ],
                "decision_prompt": "Select a candidate rank, reject all candidates, or request a new search.",
            }
        )
        return packet

    visual_steps = {
        step["id"]
        for step in workflow.get("steps", [])
        if step.get("module") in VISUAL_MODULES
        and (state.get("steps", {}).get(step["id"]) or {}).get("status") == "completed"
    }
    visual_artifacts = [item for item in manifest.get("artifacts", []) if item.get("producer") in visual_steps]

    if gate_name == "visual":
        if not visual_artifacts:
            raise AutoFlowError("VISUAL_STOP review requires completed visual artifacts")
        artifact_errors = _validate_artifacts({"artifacts": visual_artifacts})
        if artifact_errors:
            raise AutoFlowError("Visual artifact validation failed: " + "; ".join(artifact_errors))
        packet.update(
            {
                "title": "Visual artifact review",
                "artifacts": visual_artifacts,
                "required_display": [
                    "the actual images, rendered slides, or sampled video frames",
                    "purpose and downstream use of each artifact",
                    "absolute artifact paths plus dimensions, page count, or duration when applicable",
                    "validation results, visible issues, and changes since the previous review",
                    "the exact items that need a visual decision",
                ],
                "decision_prompt": "Approve the displayed visual batch, or specify concrete revisions per artifact.",
            }
        )
        return packet

    validation_errors = validate_run(workflow, state, manifest, paths, deep=True)
    requirement_map = load_json(paths["requirement_map"])
    delivery_review = load_json(paths["delivery_review"])
    packet.update(
        {
            "title": "Final delivery review",
            "artifacts": manifest.get("artifacts", []),
            "requirement_results": delivery_review.get("requirement_results", []),
            "artifact_results": delivery_review.get("artifact_results", []),
            "issues_found": delivery_review.get("issues_found", []),
            "overall_pass": delivery_review.get("overall_pass", False),
            "validation_errors": validation_errors,
            "ready_for_decision": not validation_errors and delivery_review.get("overall_pass", False),
            "review_file": str(paths["delivery_review"].resolve()),
            "supporting_files": [
                str(paths["manifest"].resolve()),
                str(paths["requirement_map"].resolve()),
            ],
            "required_requirement_ids": [
                item.get("id", "") for item in requirement_map.get("requirements", []) if item.get("required")
            ],
            "required_display": [
                "final deliverable list with absolute paths",
                "requirement-to-artifact mapping",
                "build, test, render, media, and package validation results",
                "archive contents and sensitive-file scan result when a package exists",
                "known limitations or an explicit statement that none remain",
                "absolute delivery_review.json path",
            ],
            "decision_prompt": "Sign off the final delivery, or identify the deliverable or requirement that must be revised.",
        }
    )
    return packet


def status_summary(
    workflow: dict[str, Any],
    state: dict[str, Any],
    manifest: dict[str, Any],
    include_timings: bool = False,
) -> dict[str, Any]:
    payload = {
        "workflow_id": workflow["workflow_id"],
        "name": workflow["name"],
        "recipe": workflow["recipe"],
        "status": state["status"],
        "steps": [
            {
                "id": step["id"],
                "module": step["module"],
                "action": step["action"],
                "status": state["steps"][step["id"]]["status"],
                **(
                    {
                        "attempts": state["steps"][step["id"]].get("attempts", 0),
                        "revision_attempts": state["steps"][step["id"]].get("revision_attempts", 0),
                        "max_attempts": step.get("max_attempts", 3),
                        "revision": state["steps"][step["id"]].get("revision", 0),
                        "active_seconds": state["steps"][step["id"]].get("active_seconds", 0)
                        + _elapsed_seconds(state["steps"][step["id"]].get("started_at", "")),
                        "started_at": state["steps"][step["id"]].get("started_at", ""),
                        "completed_at": state["steps"][step["id"]].get("completed_at", ""),
                    }
                    if include_timings
                    else {}
                ),
            }
            for step in workflow["steps"]
        ],
        "gates": {
            name: {
                "status": state["gates"][name]["status"],
                "active": state["gates"][name]["active"],
                "note": state["gates"][name]["note"],
                **(
                    {
                        "wait_seconds": state["gates"][name].get("wait_seconds", 0)
                        + _elapsed_seconds(state["gates"][name].get("activated_at", "")),
                        "activated_at": state["gates"][name].get("activated_at", ""),
                    }
                    if include_timings
                    else {}
                ),
            }
            for name in GATE_NAMES
        },
        "artifact_count": len(manifest.get("artifacts", [])),
    }
    if include_timings:
        payload["revision"] = state.get("revision", 0)
        payload["total_active_seconds"] = sum(item.get("active_seconds", 0) for item in payload["steps"])
        payload["total_gate_wait_seconds"] = sum(item.get("wait_seconds", 0) for item in payload["gates"].values())
    return payload


def evaluation_summary(
    workflow: dict[str, Any],
    state: dict[str, Any],
    manifest: dict[str, Any],
    expected_gate: str = "",
    validation_errors: list[str] | None = None,
) -> dict[str, Any]:
    """Classify an evaluation without weakening human STOP approval rules."""
    errors = list(validation_errors or [])
    required_steps = [step for step in workflow["steps"] if not step.get("optional", False)]
    required_step_ids = [step["id"] for step in required_steps]
    incomplete_steps = [
        step_id
        for step_id in required_step_ids
        if state["steps"][step_id]["status"] not in {"completed", "skipped"}
    ]
    registered_ids = {item.get("id") for item in manifest.get("artifacts", [])}
    missing_outputs = sorted(
        artifact_id
        for step in required_steps
        if state["steps"][step["id"]]["status"] == "completed"
        for artifact_id in step.get("outputs", [])
        if artifact_id not in registered_ids
    )
    active_gates = [
        name
        for name in GATE_NAMES
        if state["gates"][name].get("active") and state["gates"][name].get("status") == "pending"
    ]
    artifact_execution_complete = not incomplete_steps and not missing_outputs

    if errors:
        outcome = "invalid"
    elif state.get("status") == "completed":
        outcome = "full_test_pass"
    elif expected_gate and expected_gate in active_gates:
        outcome = "checkpoint_pass"
    elif active_gates:
        outcome = "awaiting_user_approval"
    elif any(state["steps"][step_id]["status"] == "failed" for step_id in required_step_ids):
        outcome = "failed"
    elif any(state["steps"][step_id]["status"] == "blocked" for step_id in required_step_ids):
        outcome = "blocked"
    else:
        outcome = "incomplete"

    return {
        "$schema": "autoflow/evaluation-status/1.0",
        "workflow_id": workflow["workflow_id"],
        "recipe": workflow["recipe"],
        "outcome": outcome,
        "workflow_status": state.get("status", ""),
        "valid": not errors,
        "validation_errors": errors,
        "artifact_execution_complete": artifact_execution_complete,
        "full_test_eligible": outcome == "full_test_pass",
        "expected_gate": expected_gate,
        "active_gates": active_gates,
        "incomplete_steps": incomplete_steps,
        "missing_outputs": missing_outputs,
        "artifact_count": len(manifest.get("artifacts", [])),
        "note": (
            "A checkpoint pass proves the expected STOP behavior only; it is not a completed end-to-end run."
            if outcome == "checkpoint_pass"
            else "Only full_test_pass may be reported as a completed end-to-end evaluation."
        ),
    }
