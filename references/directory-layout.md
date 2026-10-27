# AutoFlow directory layout

AutoFlow separates routing instructions, deterministic execution code,
integrated capabilities, and generated run data.

```text
autoflow/
├── SKILL.md                 # compact entrypoint and routing rules
├── modules/                 # task/image/office/video/package contracts (office dispatches by format)
├── integrations/            # audited local capability implementations
├── user_skills/             # ignored, user-cloned GitHub knowledge Skills
├── scripts/                 # CLI, adapters, validators, and executors
├── references/              # workflow contracts, gates, acceptance rules
├── recipes/                 # reusable DAG templates
├── examples/                # schema and plan examples
├── tests/                   # unit and integration tests
├── docs/                    # project documentation site
└── evals/                   # skill evaluation prompts
```

Each user run remains outside the Skill source tree. A run is anchored to the
task project directory — the request file's directory — not the session
workspace root, so runs land inside the task project even when the workspace
root is a parent directory. Pass `--output-dir` to place a run elsewhere:

```text
<task-project>/
├── .autoflow/
│   ├── scripts/
│   ├── runtime/
│   ├── intermediate/
│   │   ├── plans/
│   │   ├── artifacts/
│   │   └── verification/
│   └── config/
└── submit/
```

## Integration policy

`integrations/` is the only place for an external Skill or tool that AutoFlow
has reviewed and made locally callable. Each package is self-contained:
its knowledge (SKILL.md) and its tools (scripts/) travel together, and it
declares a manifest (`autoflow/integration-manifest/2.0`) with provenance,
capabilities, and a check entry that probes local run conditions. AutoFlow
does not re-write usage guidance — the agent reads the package's own SKILL.md.

Current packages: `officecli` (role: engine — the office document binary plus
its official SKILL.md; `scripts/office_engine.py` is AutoFlow's thin call
wrapper on top of it), `minimax-docx`, `nature-figure`, and `impeccable`.

Read [the integration contract](../integrations/README.md) before adding or updating an
integration. A package whose check reports `missing` or whose manifest is
invalid is a hard capability signal, never a hint to substitute a user-level
Skill or plugin.

## Runtime data

- `.autoflow/config/` stores workflow, mutable state, approvals, request copy,
  requirement map, and path map.
- `.autoflow/intermediate/` stores plans, evidence, logs, and validation reports
  that are not final deliverables.
- `.autoflow/intermediate/verification/` stores isolated test copies, temporary
  databases, migration state, and smoke-test output. Verification must not run
  inside `submit/`.
- `.autoflow/runtime/` stores Agent-managed environments and dependency caches.
  It must remain outside every registered source artifact.
- `.autoflow/scripts/` stores scripts specific to one run; shared executors stay
  in this Skill's `scripts/` directory.
- `submit/` contains only frozen final deliverables intended for handoff.

Disposable backend/test directories such as `test_output/`, `output/`,
`generated_images/`, `conversations/`, and `.probe_cache/` are not source,
examples, or deliverables. Never commit runtime artifacts, credentials, caches,
or temporary browser profiles to the Skill package.
