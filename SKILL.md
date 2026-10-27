---
name: autoflow
description: "Route artifact work through either a lightweight direct module or a managed multi-step workflow. Use direct mode for small single-module deliverables without dependencies or consequential choices; use managed task/image/office/video/package DAGs with durable state and human STOP reviews for connected or high-consequence work. Explicit autoflow invocation selects this Skill but does not force full workflow overhead."
---

# AutoFlow

AutoFlow has two execution modes. Small, low-risk, single-module requests run directly from the relevant module contract. Connected or consequential work becomes an explicit artifact DAG whose dependencies, state transitions, approvals, and outputs are validated by deterministic scripts.

The repository layout and integration policy are documented in
`references/directory-layout.md`. Read it when adding or routing a capability.

Explicit invocation always wins: if the user asks for `autoflow`, use this Skill. It selects AutoFlow routing, not automatically the managed workflow mode.

## Core principles

- Compose only the modules the request needs: `task`, `image`, `office`, `video`, `package`.
- Use direct mode for small work; do not create workflow files or STOP gates merely because AutoFlow was named.
- Preserve decisions and evidence in files when the task actually needs a resumable managed workflow.
- In managed mode, treat `workflow.json` as a contract, not a narrative checklist.
- Complete real prerequisite work before writing downstream documents about it.
- Managed mode never infers approval from silence. Every PLAN, SOURCE, VISUAL, or DELIVERY request must first show its complete review packet.
- Register only real, validated artifacts. Placeholder code, mock evidence, and unverified deliverables do not count.
- This is AutoFlow Schema 1.0. Do not run legacy AutoLab workflow files.

When maintaining AutoFlow itself (rather than producing a task artifact),
update `CHANGELOG.md` under `Unreleased` before committing any Skill,
reference, code, configuration, example, or test change. Verify tests and
check that the staged commit contains both the intended change and its
changelog entry. Follow `CONTRIBUTING.md`; do not include unrelated edits.

## Read before acting

Always read:

1. [Environment initialization](references/init.md)
2. `references/execution-modes.md`
3. The selected module file.

For direct mode, use [environment initialization](references/init.md) only to prepare the selected environment. Then
initialize the direct workspace described below and read only the route-specific
guidance required by that module. Do not enter the managed DAG.

For managed mode, also read:

1. `references/workflow-contract.md`
2. `references/stop-gates.md`
3. `references/acceptance-contracts.md`
4. `references/anti-patterns.md`

Read `references/environment-contract.md` for project build or execution steps.

Then read only the modules selected for this run:

| Module | Read | Purpose |
|---|---|---|
| task | `modules/task.md` | Research, GitHub-first builds, computation, execution |
| image | `modules/image.md` | Capture, AI assets, diagrams, charts |
| office | `modules/office.md` | Unified DOCX/PPTX/XLSX work; dispatches to `modules/office/{word,ppt,excel}.md` by `format` |
| video | `modules/video.md` | Analysis, recording, creation, processing |
| package | `modules/package.md` | Requirement-driven delivery assembly |

Before planning or executing a step, resolve the exact local instructions with
the CLI instead of invoking an external plugin:

```bash
python scripts/autoflow.py route --workflow <workflow.json> --step <step-id> --json --compact
```

To audit all checked-in external capabilities before planning, use:

```bash
python scripts/autoflow.py integrations --json
```

To inspect the resolved backend status of every module (office/image/video
plus the impeccable capability, each with local file paths), use:

```bash
python scripts/autoflow.py capabilities --json
```

Before an AI-image batch, inspect the redacted environment report once:

```bash
python scripts/autoflow.py env-check --json
```

It reports the selected image model, resolution, retry limits, and validator
configuration without exposing secrets. Office backend availability is reported
separately by `capabilities --json`.
For AI-image batch size selection, follow
[the image parameter matrix](references/image-parameter-matrix.md): default
4K with an auto-selected aspect ratio, unless the request specifies otherwise.

The command validates each integration manifest against
`autoflow/integration-manifest/2.0` (name, type, capabilities, check entry,
provenance fields) and runs the package's own check script to verify local run
conditions, reporting `available`/`missing`/`incomplete` plus declared
capabilities. Usage knowledge stays inside each package's SKILL.md — AutoFlow
never re-writes it. A workflow must use the local paths reported by `route`; a
manifest or runtime marked unavailable is a hard capability signal, not
permission to invent a tool call.

Compact routing includes the module file, fresh verification, and required
capability adapters. There is no methodology overlay loader — `route --full`
is a compat alias of compact routing and no longer loads additional files.
Read only the local paths returned by the selected route.

Frontend project steps may additionally resolve the integrated `impeccable`
design language and offline detector when the step declares
`design_backend: integrated-impeccable`. Use the returned local adapter; never
fall back to `npx impeccable`, a remote URL scan, or an uninstalled plugin.

## Choose the execution mode

Make this decision before creating a request file, plan, run directory, or state file.

Use **direct mode** only when all of these are true:

- One module is sufficient.
- The request has one semantic artifact family. Editable source plus exports of the same diagram, such as `.mmd + .svg + .png`, still count as one family.
- There is no upstream/downstream dependency, GitHub source-selection decision, packaging contract, rubric-wide evidence map, or need to resume across steps.
- The work is low-risk and does not require a consequential, destructive, public, financial, or security-sensitive decision.
- The scope is already clear enough to execute without comparing materially different approaches.

In direct mode:

1. Follow [environment initialization](references/init.md) to check/install only the selected capability's environment.
2. Initialize the task workspace, including the normal scratch/runtime directories and required `submit/` directory:

```powershell
$taskRoot = "<task-project>"
New-Item -ItemType Directory -Force -Path (Join-Path $taskRoot ".autoflow\intermediate") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $taskRoot ".autoflow\runtime") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $taskRoot "submit") | Out-Null
```

3. Do not select a recipe, transition workflow steps, or create `.autoflow/config/workflow.json`, `WORK_PLAN.md`, requirement maps, manifests, or approval gates.
4. Resolve the checked-in local capability without a workflow:

```bash
python scripts/autoflow.py direct-route --module <module> --action <action> --json
```

5. Read the returned module and capability files, perform the real work, run the module's relevant quality check, and deliver the minimum requested output set below `submit/`. Do not expose extra source/export/report files unless requested or genuinely required.
6. Do not trigger PLAN, SOURCE, VISUAL, or DELIVERY STOP. Show the finished artifact and concise validation result once. Ask a targeted question only if a missing decision truly blocks execution.

Use **managed mode** when any direct-mode condition is false. Common triggers are multiple modules, dependent artifacts, GitHub-first project builds, packages/submission contracts, complex rubric or template evidence, multiple revision checkpoints, significant external side effects, or a user request for a resumable/auditable workflow.

When unsure, do not inflate a clearly small request. Choose managed mode only when the unresolved complexity changes scope, safety, dependencies, or acceptance.

## Start a managed run

1. Inspect the request and all supplied files before asking discoverable questions.
2. Choose the closest recipe:
   - `lab-report`: task → image → office(word) → package
   - `report-and-slides`: task → image → office(word) + office(ppt) → package
   - `project-delivery`: GitHub discovery → build → image → package
   - `project-and-report`: GitHub discovery → build → image → office(word) → package
   - `project-report-and-slides`: GitHub discovery → build → image → office(word) + office(ppt) → package
   - `video-delivery`: video → package
   - `document`: optional task/image → office(word)
   - `presentation`: optional task/image → office(ppt)
   - `custom`: Agent-authored DAG
3. Follow [environment initialization](references/init.md) to prepare the required environment, then put the durable user request in a UTF-8 file **inside the task project directory** (the directory that owns this task, which may be a subdirectory of the session workspace). Do not rely on conversation memory alone.
4. Materialize the managed state. The run is anchored to the **request file's directory**, not the session workspace root — this keeps `.autoflow/` and `submit/` inside the task project:

```bash
python scripts/autoflow.py init \
  --request-file <task-project>/request.md \
  --recipe <recipe-or-auto>
```

Pass `--output-dir <path>` only to place the run somewhere else explicitly:

```bash
python scripts/autoflow.py init \
  --request-file <task-project>/request.md \
  --output-dir <task-project>/autoflow \
  --recipe <recipe-or-auto>
```

5. Read the generated files from `<request-file-dir>/.autoflow/config/`: `workflow.json`, `run_state.json`, `artifact_manifest.json`, `requirement_map.json`, `delivery_review.json`, and `WORK_PLAN.md`.
6. If `auto` was used, inspect `workflow.json.recipe_selection`, including its matched signals and reason. Keep the recommended recipe when it fits; if it selected `custom`, replace its steps with the actual DAG before asking for approval.
7. Fill every `.autoflow/config/WORK_PLAN.md` section. Map each requirement or rubric item to declared evidence in `.autoflow/config/requirement_map.json`; record planned figures and real information substitutions rather than leaving these decisions implicit.
8. After editing workflow steps, synchronize the still-unstarted state and validate the configuration:

```bash
python scripts/autoflow.py sync --workflow <request-file-dir>/.autoflow/config/workflow.json
python scripts/autoflow.py validate --workflow <request-file-dir>/.autoflow/config/workflow.json
```

9. Build the PLAN review packet, present its substantive contents and paths, then stop:

```bash
python scripts/autoflow.py review \
  --workflow <request-file-dir>/.autoflow/config/workflow.json \
  --gate plan
```

Do not ask only “approve?” or “continue?”. Tell the user the goal, scope, recipe, ordered steps, expected outputs, important decisions/risks, and the absolute `WORK_PLAN.md` path. After explicit approval, record it:

```bash
python scripts/autoflow.py approve \
  --workflow <request-file-dir>/.autoflow/config/workflow.json \
  --gate plan \
  --note "<summary of the user's explicit approval>"
```

Do not start managed module work before PLAN_STOP approval.

## Execute the DAG

Ask AutoFlow which steps are ready:

```bash
python scripts/autoflow.py next --workflow <request-file-dir>/.autoflow/config/workflow.json
```

Resolve the local module and capability route before acting on a ready step:

```bash
python scripts/autoflow.py route --workflow <request-file-dir>/.autoflow/config/workflow.json --step <step-id> --json --compact
```

For each ready step:

1. Read its module instructions.
2. Mark it running.
3. Perform the actual work.
4. Validate every declared output.
5. Complete it with exactly one artifact mapping for each declared output.

When multiple ready steps have no write conflict, prepare them together and run
their deterministic backends concurrently. In particular, run officecli
build/render commands for separate office steps in parallel after shared image
evidence is approved.
Do not introduce extra Agents to gain concurrency.

For project builds, follow [environment initialization](references/init.md), inspect the project's manifest, and run
the required setup commands as the Agent before baseline/build commands. Keep
the managed environment below `.autoflow/runtime/<step-id>/` and register the
ready `task.environment` report with `command: "agent-init"`. Do not ask the
user to install an ordinary missing runtime or dependency.

Office steps must register both `office.document` and the matching `office.validation` report produced by `scripts/office_engine.py` + `scripts/validate_office.py`. Follow the same report-first principle for video and package outputs described in `references/acceptance-contracts.md`.

```bash
python scripts/autoflow.py transition \
  --workflow <request-file-dir>/.autoflow/config/workflow.json \
  --step <step-id> \
  --to running

python scripts/autoflow.py transition \
  --workflow <request-file-dir>/.autoflow/config/workflow.json \
  --step <step-id> \
  --to completed \
  --artifact artifact.id=<absolute-path>
```

Use `--to blocked` when external input is genuinely required and `--to failed --note ...` when execution fails. Only optional steps may be skipped.

AutoFlow has no generic `run` command. The Agent invokes each module's real backend and uses the core CLI for state and validation.

## GitHub-first source selection

Code and runnable project tasks use separate `task.research` and `task.build` steps. Follow `modules/task.md` exactly.

- Search and inspect GitHub before implementation.
- Write `.autoflow/intermediate/plans/source_candidates.json` with real queries, scores, licenses, revisions, and judgments.
- Completing discovery activates SOURCE_STOP when usable candidates exist.
- Run `autoflow.py review --workflow ... --gate source`, show the 3–5 candidate comparison and source plan path, then wait for the user's selection.
- Record the selected candidate and revision before approving the gate.
- Clone and modify only after approval.
- If none are suitable, record rejected candidates and the reason for `from_scratch`; do not create a fake choice.

```bash
python scripts/autoflow.py approve \
  --workflow <request-file-dir>/.autoflow/config/workflow.json \
  --gate source \
  --note "User selected candidate <rank/name>"
```

## Visual review

In managed mode, any step with `gate_after: visual` activates VISUAL_STOP after completion. Run `autoflow.py review --workflow ... --gate visual`. Show the actual new artifacts, their purpose, paths, dimensions/page count/duration where applicable, validation results, visible concerns, and the exact decision needed. A filename-only or “please approve” message is invalid. Downstream office and packaging steps remain blocked until explicit approval.

```bash
python scripts/autoflow.py approve \
  --workflow <request-file-dir>/.autoflow/config/workflow.json \
  --gate visual \
  --note "User approved the displayed visual batch"
```

A later office (deck/slides) or image batch reopens the same gate because it has not been reviewed yet.

## Delivery review

When all steps complete, AutoFlow activates DELIVERY_STOP. Before asking for approval:

- Run `autoflow.py review --workflow ... --gate delivery` and present the returned review packet.
- Run `validate` and resolve every error.
- Set `requirement_map.json.status` to `verified`, with every required item marked passed and backed by registered artifacts.
- Complete `delivery_review.json` with one result per required requirement and one result per registered artifact.
- Show final artifact paths and what requirement each satisfies.
- Inspect office documents/decks and media visually where applicable.
- List archive contents rather than assuming packaging succeeded.
- Confirm source code or applications actually run.
- State known limitations, or explicitly state that none remain.
- Provide the absolute `delivery_review.json` path. Never ask for sign-off with only a generic completion sentence.

After the user signs off:

```bash
python scripts/autoflow.py approve \
  --workflow <request-file-dir>/.autoflow/config/workflow.json \
  --gate delivery \
  --note "User approved the final delivery"
```

The run is complete only when `run_state.json.status` is `completed`.

## Status and recovery

```bash
python scripts/autoflow.py status --workflow <request-file-dir>/.autoflow/config/workflow.json
python scripts/autoflow.py status --workflow <request-file-dir>/.autoflow/config/workflow.json --timings
python scripts/autoflow.py eval-status --workflow <request-file-dir>/.autoflow/config/workflow.json
python scripts/autoflow.py validate --workflow <request-file-dir>/.autoflow/config/workflow.json --fast
python scripts/autoflow.py validate --workflow <request-file-dir>/.autoflow/config/workflow.json --deep
```

For evaluation runs, use `eval-status --expected-gate <gate>` when the test is
supposed to prove a STOP checkpoint. A `checkpoint_pass` is not a completed
end-to-end run; only `full_test_pass` may be reported as such.

Reuse hash-matched office validation and render caches. Use `--force` only
after inputs or validation requirements change, or when diagnosing a suspected
cache defect.

- Never hand-edit `.autoflow/config/run_state.json` or `.autoflow/config/artifact_manifest.json` to bypass a gate.
- If the user rejects a STOP, record it with `autoflow.py gate --to rejected`, then use `autoflow.py revise --step <id> --reason <reason>` before regenerating terminal steps.
- If an artifact changes after registration, never refresh its hash by hand. Use `revise`; it supersedes target/downstream artifacts, resets requirement evidence, and reopens affected gates.
- A DELIVERY_STOP-approved run is immutable. Initialize a new revision run for later changes.
- If an integrated capability (for example `officecli` or the selected Minimax Word runtime) is missing, stop with a capability report rather than silently substituting a user-level or lower-quality backend.

### Failure and recovery

When any command or validation fails, use this table before inventing a workaround. Each row names the trigger, the first-line fix, and the fallback when that fix is not enough.

| Trigger | First-line fix | Fallback if still failing |
|---|---|---|
| `init` fails or the recipe cannot be matched | Correct the request file or recipe name and rerun `init` | If `.autoflow/config/` is corrupt or partial, remove the run directory and re-init; never hand-edit generated config |
| `route` reports a capability `blocked`/`missing` | Re-read [environment initialization](references/init.md) and install the selected missing dependency | Stop with a capability report; never substitute a user-level skill or an uninspected external tool |
| `transition --to completed` rejects an artifact | Recheck the artifact id against `artifact_manifest.json` and pass the exact absolute path | Regenerate the artifact from the module and retry; if the step cannot complete, `--to failed --note ...` and revise the plan |
| `validate` reports workflow errors | Fix the offending step definition per `workflow-contract.md` and rerun `validate` | Use `validate --deep` to localize the error; restart the step with `revise --step ... --reason ...` if needed |
| `officecli` or the selected Word backend runtime is missing | Install it, then rerun `capabilities --json` and the selected backend's check | Stop with a capability report; never silently fall back to a different document backend |
| Artifact hash mismatch after completion | Regenerate the artifact by rerunning its module | Use `revise` to supersede the stale artifact; never refresh the manifest hash by hand |
| A STOP gate is rejected by the user | Record it with `gate --to rejected`, then `revise --step ... --reason ...` before regenerating | If DELIVERY_STOP was already approved, start a new revision run; the approved run is immutable |
| `sync` fails after editing workflow steps | Fix the step edits and rerun `sync` | Validate with `--deep`; if unrecoverable, re-init with the same request file and re-apply the plan |

See `references/anti-patterns.md` for the complete replacement action for each prohibited state.

## Prohibited actions and dangerous states

- Do not run tests, migrations, installers, or applications inside `submit/`.
- `submit/` contains only final deliverable content the user can hand over directly. Never place compiled programs, build output (`dist/`, `build/`, `target/`, `out/`, `bin/`, `obj/`, `.next/`, `*.exe`, `*.dll`, `*.class`, …), editor/tool metadata (`.idea/`, `.vscode/`, `coverage/`), or AutoFlow run metadata (`manifest.json`, `*_manifest.json`, `workflow.json`, `artifact_manifest.json`, `run_state.json`, `requirement_map.json`, `delivery_review.json`) inside `submit/` — the packager rejects these and `--verify-only` detects them as pollution.
- Do not place virtual environments, `node_modules`, caches, or runtime databases inside source artifacts.
- Do not package the workspace or `.autoflow/` by habit. The `package_submission.py` manifest is run metadata: it stays in `.autoflow/intermediate/plans/`, never in `submit/`.
- Do not repeat full rendering, hashing, or packaging when inputs are unchanged.
- Do not invent approvals, source candidates, tool calls, or evidence.
- Do not turn a qualifying direct request into a managed run with control files and four STOP gates.
- Do not request STOP approval before showing the gate-specific review packet and its file paths.

Read `references/anti-patterns.md` for the complete replacement action for each prohibited state.

## Definition of done

For direct mode:

- The task workspace contains `.autoflow/intermediate`, `.autoflow/runtime`, and `submit/`; it has no managed workflow state.
- The requested artifact family exists below `submit/` at the clearly reported path.
- The relevant module-level quality check passed.
- No workflow control directory, plan, package, or STOP interaction was added without need.
- The user receives the artifact, path, and concise validation result in one completion message.

For managed mode:

- The selected recipe or custom DAG matches the request.
- Every STOP request first presented its required information and review paths; required approvals are recorded from explicit user responses.
- Every completed step has all declared artifacts.
- Artifact paths exist and hashes validate.
- Module-specific quality checks pass.
- Project environments are ready, verified, and outside source artifacts.
- Source/application tests ran before packaging in the isolated verification area.
- Final delivery passes `package_submission.py --verify-only` without modifying `submit/`.
- Every required requirement maps to present, correct evidence in `requirement_map.json` and `delivery_review.json`.
- `autoflow.py validate` returns `valid`.
- DELIVERY_STOP is explicitly approved.
