# AutoFlow integrations

Third-party capability packages, checked in under `integrations/`. Each package
is self-contained: its knowledge (SKILL.md) and its tools (scripts/) travel
together. AutoFlow does not re-write third-party usage guidance — the agent
reads the package's own SKILL.md and follows it. AutoFlow only does three
things: **discover** (scan directories), **verify** (run each package's check),
and **dispatch** (module docs map needs to capabilities).

Run `python scripts/autoflow.py integrations --json` to audit the catalog.

The settings UI stores user-cloned GitHub Skills under Git-ignored
`user_skills/`, not here. They are untrusted knowledge files, not audited
integration runtimes. Installing one does not authorize running its scripts
or assert that its tools are available; only an explicitly selected Word
authoring Skill enters the Word route.

## Package contract (manifest 2.0)

Every package directory must contain a `manifest.json`:

| Field | Meaning |
|---|---|
| `$schema` | `autoflow/integration-manifest/2.0` |
| `name` | Must match the directory name |
| `type` | `tool` (ships runnable tools) or `knowledge-only` (pure methodology, SKILL.md only) |
| `role` | `engine` (AutoFlow's own managed runtime, e.g. officecli) or `capability` (default) |
| `capabilities` | Map of capability names this package provides (what a module can dispatch on) |
| `check` | `{"entry": "...", "runtime": "python"}` — the script that probes local availability; `null` for `knowledge-only` |
| `upstream` / `revision` / `license` | Provenance, pinned for auditability |
| `self_contained` | Must be `true`: no network, no external skill, no separate checkout |
| `external_user_skill_required` / `source_checkout_required` | Both must be `false` |

**What the manifest does not contain:** usage instructions, parameters, or
command details. Usage knowledge lives in the package's own `SKILL.md`; the
agent reads it directly.

## check scripts

Each `tool` package provides a check entry (run with its declared runtime)
that prints one JSON object and exits:

```json
{"status": "available", "version": "1.0.144"}
```

`status` is `available` | `missing` (not installed) | `blocked` (present but
unusable). The check only verifies **local run conditions** (binary in PATH,
runtime importable, package files present) — never internal file structure of
the skill. `knowledge-only` packages need no check: availability means
`SKILL.md` exists.

The catalog validates each manifest and runs the local check for each `tool`
package. It reports `available` only when both pass. A new package is not
routable before that; never substitute a user-level Skill for an unavailable
built-in capability. Operating-system runtimes may remain dependencies when
bundling is inappropriate: provision them using
[environment initialization](../references/init.md), not by resolving
executable code from another Skill directory.

## Current packages

- `officecli/` (role: engine): the office document binary plus its official
  SKILL.md. AutoFlow's `scripts/office_engine.py` is a thin call wrapper
  (check/validate orchestration and report parsing) on top of the binary —
  operating knowledge stays in the package's SKILL.md.
- `minimax-docx/`: the complex Word authoring package, with its OpenXML SDK
  tools and usage knowledge checked in together.
- `nature-figure/`: Apache-2.0 scientific figure skill. Knowledge in
  `SKILL.md`, tools in `scripts/plot_templates.py` (and AutoFlow's own
  schematic/validator scripts referenced from it).
- `impeccable/`: Apache-2.0 frontend design language. Knowledge in `SKILL.md`
  plus its `reference/` docs; tools in `scripts/` (context, palette, offline
  detector, `impeccable_adapter.mjs` entry). All offline; no npx, no URL
  scans, no update checks.

Adding a new package = copy the directory in, write a 15-line manifest, add a
check script. Core and module docs do not change.
