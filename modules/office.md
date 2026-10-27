# Office module (unified)

Use this module whenever a `.docx`, `.pptx`, or `.xlsx` file is created, edited, or filled.
It is the single entry point for all Office document work and dispatches to a format
submodule below.

## Actions

- `create`: create a new document/workbook/deck without an existing template.
- `edit`: revise an existing file while preserving unrelated content and structure.
- `fill`: fill a supplied template without rebuilding its shell.

Every office step must declare `format` in `{word, ppt, excel}`. Read the dispatched
submodule before acting:

| format | Read | Purpose |
|--------|------|---------|
| word  | `modules/office/word.md`  | DOCX creation, editing, template filling |
| ppt   | `modules/office/ppt.md`   | PPTX creation/editing with visual review |
| excel | `modules/office/excel.md` | XLSX workbooks, formulas, tables, styling |

## Backend

An explicit `WORD_AUTHORING_SKILL` selection from the local settings page
overrides automatic Word authoring. Otherwise the agent selects by task shape.
`minimaxdocx` (the checked-in
`integrations/minimax-docx` package) is the default for complex reports and
theses; `officecli` is suitable for simple Word edits. `excel` and `ppt` remain on
`officecli`. AutoFlow always uses
`officecli` through `scripts/office_engine.py` and `scripts/validate_office.py`
for common validation and rendering, regardless of the Word authoring backend.
If the selected backend is missing, report a blocked capability and stop; never
silently substitute another backend. Read `workflow.json.capabilities.office`
for the selected backend and runtime status, and read the selected Skill file
from `route` / `direct-route` before authoring. Existing managed runs keep
their selection snapshot until re-planned.

The official operating manual is `integrations/officecli/SKILL.md` (checked-in
package copy) — read it before working; the sections below only distill the
constraints that prevent costly mistakes and do not replace the official
documentation.

The module accepts the original request plus any approved task and image artifacts.
It must not consume images while `VISUAL_STOP` is pending or rejected. Read
`references/acceptance-contracts.md` and write `.autoflow/intermediate/plans/office.json`
before editing.

## officecli key constraints

- **Layers**: L1 read/inspect → L2 DOM edit → L3 raw XML. Prefer higher layers; add
  `--json` for structured output.
- **Help is the schema**: before guessing property names or value formats, run
  `officecli help <format> <element>` (or `--json` for machine-readable schema).
  One help query beats guess-fail-retry loops.
- **Addressing**: paths are 1-based XPath-style (`/body/p[3]`, `/slide[1]`,
  `/Sheet1/A1`); prefer stable-ID paths (`/body/p[@paraId=...]`,
  `/slide[N]/shape[@id=...]`) in multi-step edits — positional indices shift on insert.
- **Resident mode**: officecli keeps files in memory and auto-flushes. Only run
  `officecli save` / `officecli close` before a non-officecli program reads the file
  (Word, Excel, renderers, delivery).
- **Atomic batches**: use `officecli batch --json` for multi-step edits; any failed
  item rolls back the whole batch unless `--best-effort` is deliberate.
- **Verify after every file change**: run `officecli validate <file>` and
  `officecli view <file> issues --json`; fix findings before proceeding.

## Validation contract

Run the engine checks first, then the full plan-aware validation:

```bash
python scripts/office_engine.py validate \
  --document <output> --format <word|ppt|excel> \
  --template <template> --source <source> \
  --report <run>/.autoflow/intermediate/artifacts/office_engine_validation.json

python scripts/validate_office.py \
  --document <output> --format <word|ppt|excel> \
  --template <template> --plan <run>/.autoflow/intermediate/plans/office.json \
  --engine-report <run>/.autoflow/intermediate/artifacts/office_engine_validation.json \
  --report <run>/.autoflow/intermediate/artifacts/office_validation.json
```

Register both `office.document` and `office.validation`. The core rejects an office
step if the report is failed, incomplete, stale, or refers to a different file hash
(`office_acceptance` validator). The engine report is reused only when document,
template, source, and validator fingerprints all match; use `--force` only for
cache diagnosis.

After the file is final, render it (e.g. `officecli view <file> html` or the
submodule's render step) and record a passed rendered visual review in the plan
before completing the step.
