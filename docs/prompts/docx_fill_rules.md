# DOCX Fill Rules

This document defines how `AutoFlow office.fill` (format `word`) should preserve a supplied template shell.

## Core policy

- Preserve the template structure and styling intent.
- Save to a new output file, never overwrite the source template.
- Follow the selected Word authoring Skill in the [Word module](../../modules/office/word.md): `auto` picks available `minimaxdocx` first, then `officecli`; an explicit installed GitHub Skill is also valid. Never silently replace a pinned backend. `officecli` remains the common validation/render backend.
- After editing, run the office acceptance pipeline (`office_engine.py validate` + `validate_office.py`) and keep the engine report as part of `office.validation`.
- Plan figures before writing report text.
- Default target tier is `excellent`.
- Default report style is figure-supported, not pure-text.
- Write from the perspective of a student submitting completed coursework, not from the perspective of an agent describing actions.

## Route boundary

Four image actions may appear in the same document:

- `image.ai`
  - terminal screenshots
  - command output screenshots
  - software/system configuration screenshots

- `image.capture`
  - local frontend page screenshots
  - self-built app/web screenshots
  - development software practice screenshots for the user's own app/web flow

- `image.diagram` / `image.chart`
  - function diagrams
  - flowcharts
  - data flow diagrams
  - ER diagrams

- `video.analyze` / `video.record`
  - existing operation videos
  - short local operation recordings
  - representative frame evidence

## Mandatory pre-work

Before editing the document:
1. Read the template and identify headings, body zones, tables, and figure anchors.
2. Read `.autoflow/config/workflow.json` and `.autoflow/config/artifact_manifest.json`; use only inputs declared for the office step.
3. Confirm all upstream task steps are completed and all consumed artifacts still validate.
4. If the document consumes image or PPT artifacts, confirm `VISUAL_STOP` is approved.
5. Read the relevant module plans under `plans/` rather than assuming every route exists.
7. Combine task outputs with the original request instead of writing a disconnected generic report.
8. Review the template for directories, field-based tables of contents, sample text, formatting instructions, and reference wording that must be replaced or removed.

## Typography and fill-quality rules

These are principle-level constraints for how filled content should look. Follow
the template's own typographic system as the source of truth; never invent
specific numeric values (font sizes, spacings, margins) that the template or the
user request does not provide.

- Text quality: filled text reads as finished document prose in the required
  voice — grammatical, complete sentences, no placeholder fragments, no
  tool/agent narration, no untranslated drafting notes.
- Placement correctness: content goes into the correct anchors identified during
  pre-work; nothing lands in headers/footers/TOC areas by accident; fills never
  push template layout out of shape.
- Spacing: paragraph spacing, indentation, and the whitespace around figures,
  tables, and captions stay visually even and follow the template's existing
  rhythm — no cramped runs and no randomly blank stretches.
- Font-size hierarchy: body text, headings, captions, and table text each keep
  one consistent size role across the whole document, taken from the template's
  existing hierarchy. The same role never mixes sizes.
- Line spacing and white space: line spacing and margins stay uniform throughout;
  do not override the template's spacing unless the request requires it, and then
  apply the override consistently everywhere.
- Heading levels: respect the template's heading hierarchy; do not skip, flatten,
  or duplicate levels; numbering style (if any) follows the template's convention
  and stays sequential.
- Chinese fonts and punctuation: keep the template's Chinese font settings;
  use full-width punctuation for Chinese text and half-width for embedded Latin
  words, numbers, and code; never mix full/half-width styles for the same kind
  of punctuation within the document; no stray spaces around Chinese punctuation.
- Caption format: every caption follows the template's caption style (position,
  numbering scheme, ending punctuation); caption numbers stay unique and in
  order; captions match the figure they anchor.
- Overall regularity: the finished document should look uniform and deliberate —
  aligned elements, consistent styles across sections, no half-filled or
  style-drifting regions. When in doubt, match the template instead of inventing.

## Figure rules

- If the template already contains image placeholders, reuse them.
- If not, place figures at planned semantic anchors.
- Each figure should have:
  - a lead-in sentence
  - the image
  - a caption
  - a short analysis paragraph

## Verification expectations

The template-specific verify script should check at least:
- no unresolved placeholders remain unless intentionally documented
- the planned figure count is satisfied
- route coverage is satisfied when multiple routes are required
- declared video analysis/recording artifacts exist when the document consumes video evidence
- filled-reference cleanup preserved cover/front matter and retained level-1/level-2 headings when required
- task artifacts are accurately reflected when the request depends on them
- captions exist
- figures are not dumped at the end without context
- placeholder/sample text is removed
- template formatting instructions and reference wording are removed when they are not part of the final report content
- table-of-contents or directory areas are not silently left broken when the template expects them to be filled or updated
- report narration stays in student voice instead of tool/agent voice
- the template shell remains stable
