# Task module

Use this module for work that creates the factual or executable foundation consumed by later modules.

## Actions

- `research`: gather and verify source material. For runnable project requests, this becomes GitHub source discovery.
- `build`: clone and adapt a selected project, or implement from scratch after a documented no-candidate result.
- `compute`: calculate, clean, transform, simulate, or analyze data. Charts still belong to `image.chart`.
- `execute`: run an experiment, application, script, database operation, or other concrete task.

Every completed step must produce the artifact IDs declared in `workflow.json`. Register them through `autoflow.py transition --to completed --artifact ID=PATH`.

Before acting on a task step, run `autoflow.py route --workflow ... --step ...
--json --compact` and read the returned required files. Managed routing uses
the run's capability snapshot and only guidance required by the current step;
re-plan after backend changes. Read the
exact paths returned by the CLI; independent or cross-model review is not part
of the default route.

## Requirement-driven task selection

Use `requirement_map.json` to decide whether a task step is real prerequisite work. Add `task.compute`, `task.execute`, or `task.build` only when one or more requirements need its output as evidence or as an upstream dependency. Do not invent a task for convenience-only document editing. Record the consuming requirement ids in the task plan/result so delivery review can trace the evidence.

## GitHub-first project flow

For code, websites, applications, systems, databases, or runnable project requests, create separate `task.research` and `task.build` steps. Do not merge them because `SOURCE_STOP` sits between discovery and modification.

1. Read the request and extract required features, technology constraints, deliverables, and forbidden substitutions.
2. Search GitHub with several requirement-derived queries. Inspect repository files, license, maintenance activity, build instructions, dependencies, and screenshots where available.
3. Score candidates from 0–5 for requirement fit, modification distance, stack compatibility, buildability, maintenance, and license compatibility.
4. Keep only genuinely usable candidates. Write three to five to `.autoflow/intermediate/plans/source_candidates.json`.
5. Complete the research step. AutoFlow activates `SOURCE_STOP` when candidates exist.
6. Show a compact candidate table to the user and wait. Do not clone or modify a candidate before the user chooses.
7. After the user selects, record the choice, selected revision, and rationale, then approve `SOURCE_STOP` with the user's explicit confirmation note.
8. Clone the selected revision, run its baseline, adapt it to the requirement, and record changed files and verification results.

An unmodified clone is not a completed build.

For frontend project builds, use the integrated `impeccable` route when the
step declares `design_backend: integrated-impeccable`. Read
[impeccable SKILL.md](../integrations/impeccable/SKILL.md) and follow its command reference and
local tools — usage knowledge lives in the package, AutoFlow does not
re-document it. Its offline entry point is
`integrations/impeccable/scripts/impeccable_adapter.mjs`; do not run
`npx impeccable`, URL scans, update checks, or plugin hooks.

## Source plan contract

Candidate selection state:

```json
{
  "status": "awaiting_user_choice",
  "queries": ["requirement-derived query"],
  "criteria": ["requirement_fit", "modification_distance", "stack", "buildability", "maintenance", "license"],
  "candidates": [
    {
      "rank": 1,
      "name": "owner/repository",
      "repository_url": "https://github.com/owner/repository",
      "revision": "commit sha inspected during research",
      "license": "MIT",
      "scores": {
        "requirement_fit": 5,
        "modification_distance": 4,
        "stack": 5,
        "buildability": 4,
        "maintenance": 4,
        "license": 5
      },
      "judgment": "Why it is a strong adaptation base"
    }
  ],
  "selected_candidate": {},
  "user_choice": {"status": "awaiting_user_choice"},
  "fallback": {"used": false, "reason": ""}
}
```

After user selection, set `status` to `selected`, set `user_choice.status` to `confirmed`, and provide `selected_candidate.name`, `repository_url`, `selected_revision`, and `selection_rationale`.

When no suitable project exists, do not invent a candidate. Use:

```json
{
  "status": "no_suitable_project",
  "queries": ["queries actually used"],
  "candidates": [],
  "rejected_candidates": [{"repository_url": "...", "reason": "..."}],
  "fallback": {"used": true, "reason": "Why implementation must start from scratch"}
}
```

Completing the research step marks `SOURCE_STOP` not applicable in this case and allows from-scratch implementation.

## Build completion

Before baseline or dependency commands, read the [environment contract](../references/environment-contract.md) and follow [environment initialization](../references/init.md). Inspect the project manifest, run only the selected setup commands as the Agent, place the managed runtime below `.autoflow/runtime/<step-id>/`, and register its ready `agent-init` report as `task.environment` when declared. Ordinary missing runtimes and dependencies are automatic remediation work, not a user blocker.

Record the selected upstream URL and revision, baseline commands/results, change plan, changed files, startup documentation, and verification commands. Produce the project directory, a machine-readable result summary, and the environment report when the workflow declares those outputs.

The project directory must be non-empty and contain a README with startup/handoff instructions. For GitHub adaptation it must retain `.git`. The `task.result` JSON must contain:

```json
{
  "source_mode": "github_adaptation",
  "baseline": {"status": "passed", "commands": ["..."], "result": "..."},
  "changed_files": ["src/...", "README.md"],
  "verification_results": [{"command": "...", "status": "passed", "notes": "..."}],
  "upstream": {
    "repository_url": "https://github.com/owner/repository",
    "selected_revision": "commit sha"
  }
}
```

For a documented no-candidate fallback, use `source_mode: from_scratch`; upstream fields are not required, but implemented files and passed verification still are.
