# AutoFlow workflow contract

This contract applies to managed mode only. Direct mode follows `references/execution-modes.md`, resolves one module with `direct-route`, and creates none of the run layout or state files below.

## Run layout

Every new run is created inside the task project directory — the request
file's directory — with `.autoflow/` directly anchored there:

```text
<task-project>/
├── .autoflow/
│   ├── scripts/                 # task-specific scripts
│   ├── runtime/                 # managed environments, never packaged
│   ├── intermediate/            # plans, artifacts, screenshots, logs, reports
│   │   ├── plans/
│   │   └── artifacts/
│   └── config/                  # workflow and mutable control state
└── submit/                      # only final deliverables and delivery bundles
```

Pass `--output-dir` to place the run elsewhere explicitly.

`workflow.json.directories` is the authoritative path map for the run. Agents
must use it instead of inventing sibling folders.

## Durable files

- `.autoflow/config/workflow.json` is the declarative DAG. It changes only when the user approves a revised plan.
- `.autoflow/config/run_state.json` is mutable execution state for steps and STOP gates.
- `.autoflow/config/artifact_manifest.json` records verified outputs and their hashes.
- `.autoflow/config/requirement_map.json` maps requirements and scoring items to declared evidence.
- `.autoflow/config/delivery_review.json` records final correctness for every requirement and artifact.
- `.autoflow/config/WORK_PLAN.md` is the human-readable plan reviewed at `PLAN_STOP`.
- `.autoflow/intermediate/plans/` contains module-specific plans such as `source_candidates.json` and `package.json`.
- `workflow.json.capabilities` records the integrated capability backends and
  their resolved local paths; route decisions must use those paths.
- `autoflow.py integrations --json` is the repository-level catalog. It must
  report every directory under `integrations/` with a valid manifest before a
  new external capability is considered routable.

## Workflow step

Every step contains:

```json
{
  "id": "office",
  "module": "office",
  "format": "word",
  "action": "fill",
  "needs": ["task", "image"],
  "inputs": ["request", "task.result", "image.assets"],
  "outputs": ["office.document", "office.validation"],
  "validator": "office_acceptance",
  "optional": false,
  "max_attempts": 3
}
```

Backend selectors are explicit when a step needs an integrated capability:
`design_backend: integrated-impeccable` routes frontend design context and
local anti-pattern detection to the bundled Impeccable adapter. A selector is
a capability requirement, not permission to silently substitute another
external tool.

`needs` controls execution order. `inputs` and `outputs` are artifact IDs. `request` is the only built-in input. Output IDs must be unique across the workflow. When two steps produce the same artifact ID (two office steps both emit `office.document`), an input may disambiguate with `producer::artifact` — for example `word::office.document` — and the CLI accepts the same `producer::artifact=PATH` form when completing a step. The producer must be the step that actually declared that output.

When `init --recipe auto` is used, `workflow.json.recipe_selection` records the
selected recipe, matched request signals, selection mode, and reason. This is a
transparent starting recommendation; it does not approve the plan or bypass
PLAN_STOP. The Agent may edit the steps and must run `sync` before approval.

When the Agent changes a custom DAG before PLAN_STOP, run `autoflow.py sync --workflow ...`. Synchronization is rejected after any step has started.

Allowed modules and actions:

- task: research, build, compute, execute
- image: capture, ai, diagram, chart
- office: create, edit, fill (must also declare `format`: word, ppt, or excel)
- video: analyze, record, create, process
- package: assemble

Office steps use `office_acceptance` with `office.document` and `office.validation`; `format` dispatches to `modules/office/{word,ppt,excel}.md`. The route's `module_files` lists `modules/office.md` before that format file, while the legacy `module_file` remains the format file. Managed routes use the capability snapshot saved with the workflow; a local backend or selection change requires re-planning. Video steps use `video_acceptance` with `video.media` and `video.validation`. Package steps use `package_acceptance` with `package.bundle` and `package.manifest`. Other steps use `artifacts_exist` unless their module contract defines a stricter report validator.

## State transitions

Steps start as `pending` and become `ready` after their dependencies complete and no STOP blocks execution.

- pending/ready → running
- running → blocked/completed/failed
- blocked/failed → running
- optional pending/ready → skipped

A completed or skipped step is terminal during normal transitions. Before DELIVERY_STOP approval, reopen it with:

```bash
python scripts/autoflow.py revise --workflow <workflow.json> --step <step-id> --reason <reason>
```

Revision moves current target/downstream artifacts to `artifact_history`, invalidates transitive dependents, resets affected requirement evidence, and reopens the necessary gates. A delivered workflow is immutable; initialize a new revision run after DELIVERY_STOP approval.

`max_attempts` defaults to 3 and may be set from 1 to 10. The budget applies
within one revision. Exhaustion is a diagnostic stop, not permission for an
unbounded retry; use `revise` after identifying and recording the cause.

Complete a step with one `--artifact ID=PATH` for every declared output. AutoFlow verifies existence, records consumers, calculates SHA-256, and rejects undeclared or missing outputs.

## Agent-led execution

Normal execution uses compact routing. Route returns the module file plus the
declared capability adapter paths only; it never loads a methodology overlay
or every available Skill. Run independent ready deterministic backends
concurrently when they do not share output paths; separate office steps (e.g.
a word report and a ppt deck) are the primary example.

Use `validate --fast` during iteration and `validate --deep` at STOP gates.
Use `status --timings` to separate active-step time from user gate wait time.
Provision environments once below `.autoflow/runtime/` and reuse them while
dependency manifests are unchanged. Freeze inputs, verify in isolation,
publish the package once, then use only read-only package verification.

Use `autoflow.py eval-status` for evaluation evidence. It classifies runs as
`incomplete`, `blocked`, `failed`, `awaiting_user_approval`,
`checkpoint_pass`, `invalid`, or `full_test_pass`. Reaching an expected STOP
may prove that checkpoint, but only a valid workflow with status `completed`
is eligible for a full end-to-end test claim.

AutoFlow does not contain a generic `run` command. The Agent reads the relevant module file, performs the work with the appropriate tool or Skill, and uses the CLI only to validate and advance state. This keeps human choices and cross-Skill operations visible while preserving deterministic gates and artifact contracts.

Use compact routing by default. It returns the module file and the minimum
required capability guidance. `route --full` exists only as a compat alias of
compact routing — there is no methodology overlay loader — so call compact
routing for every step.
