import argparse
import json
import sys
from pathlib import Path

from autoflow_core import OFFICE_FORMATS
from env_config import env_report
from autoflow_core import (
    AutoFlowError,
    approve_gate,
    detect_impeccable_backend,
    detect_image_backend,
    detect_office_backend,
    detect_video_backend,
    evaluation_summary,
    integration_catalog,
    gate_review_packet,
    initialize_run,
    load_run,
    parse_artifact_specs,
    refresh_ready,
    revise_step,
    route_for_direct,
    route_for_workflow,
    save_json,
    save_run,
    set_gate_state,
    status_summary,
    sync_planning_state,
    transition_step,
    validate_run,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Initialize, validate, and advance an AutoFlow workflow.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create a new AutoFlow run directory")
    init.add_argument("--request-file", required=True)
    init.add_argument(
        "--output-dir",
        default=None,
        help="Run root directory (defaults to the request file's directory)",
    )
    init.add_argument("--recipe", default="auto")

    for name in ("status", "next", "sync"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--workflow", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--workflow", required=True)
    validate_mode = validate.add_mutually_exclusive_group()
    validate_mode.add_argument("--fast", action="store_true", help="Skip full artifact rehashing during iteration")
    validate_mode.add_argument("--deep", action="store_true", help="Force full artifact rehashing (default)")

    status = subparsers.choices["status"]
    status.add_argument("--timings", action="store_true", help="Include step and gate timing metrics")

    eval_status = subparsers.add_parser(
        "eval-status",
        help="Classify a real evaluation as incomplete, checkpoint pass, or full end-to-end pass",
    )
    eval_status.add_argument("--workflow", required=True)
    eval_status.add_argument(
        "--expected-gate",
        choices=["plan", "source", "visual", "delivery"],
        default="",
        help="Count reaching this active STOP as a checkpoint pass, never as a full test pass",
    )

    capabilities = subparsers.add_parser("capabilities", help="Inspect integrated and optional module backends")
    capabilities.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    env_check = subparsers.add_parser("env-check", help="Inspect Skill environment configuration without exposing secrets")
    env_check.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    integrations = subparsers.add_parser("integrations", help="List and audit checked-in integrations")
    integrations.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    route = subparsers.add_parser("route", help="Resolve local module, backend, and capability files for a workflow step")
    route.add_argument("--workflow", required=True)
    route.add_argument("--step", default="")
    route.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    route_mode = route.add_mutually_exclusive_group()
    route_mode.add_argument("--compact", action="store_true", help="Load only required step guidance (default)")
    route_mode.add_argument("--full", action="store_true", help="Compat alias of compact routing (no methodology overlay loader exists)")

    direct_route = subparsers.add_parser(
        "direct-route",
        help="Resolve one local module without creating workflow files or STOP gates",
    )
    direct_route.add_argument("--module", required=True)
    direct_route.add_argument("--action", required=True)
    direct_route.add_argument(
        "--format",
        choices=sorted(OFFICE_FORMATS),
        help="Required when --module office: word, ppt, or excel",
    )
    direct_route.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    direct_mode = direct_route.add_mutually_exclusive_group()
    direct_mode.add_argument("--compact", action="store_true", help="Load only required guidance (default)")
    direct_mode.add_argument("--full", action="store_true", help="Compat alias of compact routing (no methodology overlay loader exists)")

    review = subparsers.add_parser(
        "review",
        help="Build the information packet that must be shown before requesting STOP approval",
    )
    review.add_argument("--workflow", required=True)
    review.add_argument("--gate", required=True, choices=["plan", "source", "visual", "delivery"])

    transition = subparsers.add_parser("transition", help="Advance one workflow step")
    transition.add_argument("--workflow", required=True)
    transition.add_argument("--step", required=True)
    transition.add_argument("--to", required=True, choices=["running", "blocked", "completed", "failed", "skipped"])
    transition.add_argument("--note", default="")
    transition.add_argument("--artifact", action="append", default=[], metavar="ARTIFACT_ID=PATH")

    revise = subparsers.add_parser("revise", help="Reopen a step and invalidate all downstream artifacts")
    revise.add_argument("--workflow", required=True)
    revise.add_argument("--step", required=True)
    revise.add_argument("--reason", required=True)

    approve = subparsers.add_parser("approve", help="Record explicit user approval for a STOP gate")
    approve.add_argument("--workflow", required=True)
    approve.add_argument("--gate", required=True, choices=["plan", "source", "visual", "delivery"])
    approve.add_argument("--note", required=True)

    gate = subparsers.add_parser("gate", help="Reject or mark a conditional STOP as not applicable")
    gate.add_argument("--workflow", required=True)
    gate.add_argument("--gate", required=True, choices=["plan", "source", "visual", "delivery"])
    gate.add_argument("--to", required=True, choices=["rejected", "not_applicable"])
    gate.add_argument("--note", required=True)
    return parser.parse_args()


def emit(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main() -> int:
    args = parse_args()
    try:
        if args.command == "init":
            output_dir = Path(args.output_dir) if args.output_dir else None
            path = initialize_run(Path(args.request_file), output_dir, args.recipe)
            emit({"status": "initialized", "workflow": str(path)})
            return 0
        if args.command == "capabilities":
            payload = {
                "$schema": "autoflow/capabilities/1.0",
                    "capabilities": {
                    "office": detect_office_backend(),
                    "impeccable": detect_impeccable_backend(),
                    "video": detect_video_backend(),
                    "image": detect_image_backend(),
                },
            }
            if args.json:
                emit(payload)
            else:
                for name, capability in payload["capabilities"].items():
                    backend = capability.get("backend") or "not configured"
                    print(f"{name}: {capability.get('status', 'unknown')} ({backend})")
            return 0
        if args.command == "env-check":
            payload = {"$schema": "autoflow/env-report/1.0", "environment": env_report(Path(__file__).resolve().parent.parent)}
            if args.json:
                emit(payload)
            else:
                environment = payload["environment"]
                print(f"image: {'available' if environment['image']['configured'] else 'missing'} ({environment['image']['model']}, {environment['image']['default_resolution']})")
                print(f"validator: {'available' if environment['validator']['configured'] else 'missing'} ({environment['validator']['model'] or 'not selected'})")
            return 0
        if args.command == "integrations":
            payload = {"$schema": "autoflow/integrations/1.0", "integrations": integration_catalog()}
            if args.json:
                emit(payload)
            else:
                for item in payload["integrations"]:
                    print(f"{item['name']}: {item['status']} ({item.get('license', 'unknown')})")
            return 0
        if args.command == "direct-route":
            payload = route_for_direct(args.module, args.action, args.format, compact=not args.full)
            if args.json:
                emit(payload)
            else:
                print(f"{payload['module']}.{payload['action']} ({payload['execution_mode']})")
                for path in payload["module_files"]:
                    print(f"  module: {path}")
                for path in payload.get("capability_files", []):
                    print(f"  capability: {path}")
            return 0

        workflow, state, manifest, paths = load_run(Path(args.workflow))
        if args.command == "review":
            emit(gate_review_packet(workflow, state, manifest, paths, args.gate))
            return 0
        if args.command == "route":
            payload = route_for_workflow(workflow, state, args.step or None, compact=not args.full)
            if args.json:
                emit(payload)
            else:
                for item in payload.get("steps", [payload.get("step", payload)]):
                    print(f"{item['id']}: {item['module']}.{item['action']}")
                    for path in item["module_files"]:
                        print(f"  module: {path}")
                    print(f"  skills: {', '.join(item['skill_names'])}")
                    for path in item["skill_files"]:
                        print(f"    - {path}")
                    for path in item.get("capability_files", []):
                        print(f"  capability: {path}")
            return 0
        if args.command == "validate":
            errors = validate_run(workflow, state, manifest, paths, deep=not args.fast)
            if errors:
                emit({"status": "invalid", "errors": errors})
                return 1
            emit({"status": "valid", "workflow": str(paths["workflow"])})
            return 0
        if args.command == "status":
            emit(status_summary(workflow, state, manifest, include_timings=args.timings))
            return 0
        if args.command == "eval-status":
            errors = validate_run(workflow, state, manifest, paths, deep=False)
            payload = evaluation_summary(
                workflow,
                state,
                manifest,
                expected_gate=args.expected_gate,
                validation_errors=errors,
            )
            emit(payload)
            return 0 if payload["outcome"] in {"checkpoint_pass", "full_test_pass"} else 1
        if args.command == "next":
            ready = refresh_ready(workflow, state)
            save_run(state, manifest, paths)
            emit({"ready_steps": ready, "state": status_summary(workflow, state, manifest)})
            return 0
        if args.command == "sync":
            sync_planning_state(workflow, state)
            save_json(paths["workflow"], workflow)
            save_run(state, manifest, paths)
            emit({"status": "synchronized", "state": status_summary(workflow, state, manifest)})
            return 0
        if args.command == "transition":
            artifacts = parse_artifact_specs(args.artifact)
            transition_step(workflow, state, manifest, paths, args.step, args.to, args.note, artifacts)
            save_run(state, manifest, paths)
            emit(status_summary(workflow, state, manifest))
            return 0
        if args.command == "revise":
            affected = revise_step(workflow, state, manifest, paths, args.step, args.reason)
            save_run(state, manifest, paths)
            emit({"status": "revised", "affected_steps": affected, "state": status_summary(workflow, state, manifest)})
            return 0
        if args.command == "approve":
            approve_gate(workflow, state, manifest, paths, args.gate, args.note)
            if args.gate == "plan":
                save_json(paths["workflow"], workflow)
            save_run(state, manifest, paths)
            emit(status_summary(workflow, state, manifest))
            return 0
        if args.command == "gate":
            set_gate_state(workflow, state, paths, args.gate, args.to, args.note)
            save_run(state, manifest, paths)
            emit(status_summary(workflow, state, manifest))
            return 0
        raise AutoFlowError(f"Unsupported command: {args.command}")
    except AutoFlowError as exc:
        print(f"AutoFlow error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
