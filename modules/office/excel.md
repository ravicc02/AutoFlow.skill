# Office submodule: excel (.xlsx)

Dispatched from `modules/office.md` when `format=excel`. All edits run through
`officecli`; validation follows `scripts/office_engine.py` + `scripts/validate_office.py`.
Read the official operating manual in [officecli SKILL.md](../../integrations/officecli/SKILL.md) first —
this submodule applies it to XLSX workflows, it does not replace it.

## Workflow (per action)

1. Inspect the workbook: `officecli view <file> stats|text --json`,
   `officecli get <file> '/Sheet1' --depth N`, `officecli query <file> 'cell[value>0]'`.
2. Build the workbook layout (sheets, columns, rows) and formula/styling plan before
   editing.
3. Edit with L2 DOM operations:
   - cells: `officecli set <file> '/Sheet1/A1' --prop value=... --prop bold=true ...`;
     formulas are auto-detected; ranges support `A1:D100` selectors and
     `Sheet1!row[Salary>5000]` row-by-column-name queries.
   - rows/cols: `officecli add/remove` with `--shift` for Excel-UI parity;
     formulas rewrite on row/col insert.
   - tables/pivots/charts: `officecli add <file> /Sheet1 --type table|pivottable|chart ...`.
   - multi-step edits: `officecli batch` (atomic by default); sort with
     `--prop sort="C desc" --prop sortHeader=true`.
4. Verify with `officecli validate` + `officecli view <file> issues --json`, then the
   plan-aware validation below.

## Excel-specific plan checks

- sheet count matches the plan and every declared sheet has a worksheet part;
- no unresolved placeholders or Agent/AI voice in cell text;
- rendered review recorded in the plan.

## Render review

Render the workbook (`officecli view <file> html --browser`, or screenshot the
relevant sheets) and inspect for overflow, unreadable cells, broken formulas, and
visual inconsistency. Record the review in `.autoflow/intermediate/plans/office.json`
(`visual_review.status=passed` with evidence).
