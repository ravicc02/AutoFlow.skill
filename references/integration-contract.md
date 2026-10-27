# AutoFlow integration self-containment contract

Every directory under `integrations/` is a self-contained third-party
capability package. Its knowledge (`SKILL.md`) and its tools (`scripts/`)
travel together; AutoFlow never re-writes third-party usage guidance. The
agent reads the package's own documentation and follows it.

The local settings UI stores user-cloned GitHub Skills separately in
`user_skills/` (Git ignored). These are untrusted knowledge files, not
manifest-validated integrations; installing one does not authorize running
its scripts or claim that its tools are available. Only the explicitly
selected Word authoring Skill is included in the Word route.

## Package contract (manifest 2.0)

Each package directory must contain `manifest.json` declaring:

- `$schema`: `autoflow/integration-manifest/2.0`;
- `name`: must match the directory name;
- `type`: `tool` (ships runnable tools) or `knowledge-only` (pure methodology);
- `role`: `engine` for AutoFlow's own managed runtimes (e.g. officecli),
  `capability` otherwise;
- `capabilities`: non-empty map of capability names the package provides —
  the only thing module docs may dispatch on;
- `check`: `{"entry": "...", "runtime": "python"}` for `tool` packages — the
  script that probes local run conditions; `null`/absent for `knowledge-only`;
- `upstream`, `revision`, `license`: provenance, pinned for auditability;
- `self_contained: true`, `external_user_skill_required: false`,
  `source_checkout_required: false`.

The manifest must NOT contain usage instructions, parameters, or command
details. Usage knowledge lives in the package's `SKILL.md`.

## check semantics

A `tool` package's check script prints one JSON object:
`{"status": "available"|"missing"|"blocked", "version": ...}`. It only verifies
local run conditions (binary in PATH, runtime importable, package files
present) — never the package's internal structure. `knowledge-only` packages
need no check: availability means `SKILL.md` exists.

## Enforcement

`autoflow.py integrations --json` validates every package against the
contract above and runs each `tool` package's check. A package is `available`
only when its manifest is valid AND its check passes. A new package is not
routable until the catalog reports `available`.

Operating-system runtimes and language dependencies may remain provisioned
dependencies when bundling them would be inappropriate. AutoFlow must detect
them and provision them by following
[environment initialization](init.md) as the Agent; this does not
permit resolving executable code from another Skill directory.
