# Office submodule: ppt (.pptx)

Dispatched from `modules/office.md` when `format=ppt`. All edits run through
`officecli`; validation follows `scripts/office_engine.py` + `scripts/validate_office.py`.
Read the official operating manual in [officecli SKILL.md](../../integrations/officecli/SKILL.md) first —
this submodule applies it to PPTX workflows, it does not replace it.

## Workflow (per action)

1. Inspect the deck: `officecli view <file> outline --json`, `officecli get <file> /slide[N] --depth 1`.
2. Build a slide outline, visual system, and source mapping before generation.
3. Edit with L2 DOM operations:
   - `officecli add <file> / --type slide --prop title="..." --prop background=...`
   - shapes/tables/charts/pictures: `officecli add <file> '/slide[N]' --type shape
     --prop text=... --prop x=2cm --prop y=5cm ...`; prefer stable IDs
     (`shape[@id=...]`) for later edits.
   - `officecli set` with `--find/--replace` for text changes; `officecli batch` for
     multi-step edits.
4. Verify with `officecli validate` + `officecli view <file> issues --json`, then the
   plan-aware validation below.

## PPT-specific plan checks

- slide parts match the declared slide count;
- every slide has a title, and slide titles are unique;
- no unresolved placeholders or Agent/AI voice in slide text;
- rendered slide review recorded in the plan.

## Render review

Render or thumbnail the deck (`officecli view <file> html --browser` /
`officecli view <file> screenshot -o` per slide, or `watch`) and inspect every slide
for overflow, overlap, clipping, unreadable text, broken media, and visual
inconsistency. Record the review in `.autoflow/intermediate/plans/office.json`
(`visual_review.status=passed` with evidence).

PPT steps use `gate_after: visual`. Completing a deck reopens `VISUAL_STOP` even if an
earlier image batch was approved, because the assembled slides are a new visual
artifact.
