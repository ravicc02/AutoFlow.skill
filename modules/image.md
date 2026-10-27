# Image module

Use this module for visual artifacts. Computation belongs to `task.compute`; this module renders or captures its results.

## Direct mode

A small request for one visual artifact family—such as one ER diagram with `.mmd`, `.svg`, and `.png` representations—runs directly. Use [environment initialization](../references/init.md) for environment setup, then initialize the direct workspace required by `SKILL.md`, including `.autoflow/intermediate`, `.autoflow/runtime`, and `submit/`. Resolve it with `autoflow.py direct-route --module image --action <action>`, read only the returned files, render, validate, and deliver it below `submit/`. Do not select a recipe or create workflow config, plans, manifests, or PLAN/VISUAL/DELIVERY STOP for this case.

The quality rules below still apply in direct mode. Generate only the requested formats. If no format is specified, prefer one broadly viewable final such as PNG; retain editable DSL or additional SVG/PDF exports only when requested or materially needed. Validation can remain internal rather than becoming another delivery file. Show the finished visual and report its path and validation once; do not ask for a second approval unless the user explicitly requested an iterative review.

For diagrams, pass `--direct` to `generate_diagram_assets.py`; it defaults to one PNG and omits source, SVG, and the managed generation report. Use `--format svg|source|all` or `--keep-report` only when the request needs them.

## Actions

- `capture`: real browser/application/terminal evidence. Prefer deterministic capture from the actual local result.
- `ai`: AI-generated screenshots, explanatory assets, and scientific schematics only when real capture is unavailable or the request explicitly needs generation. The scientific-figure adapter uses AutoFlow's `.env` upstream with `gpt-image-2`; it does not call OpenRouter.
- `diagram`: architecture, ER, UML, process, data-flow, and any other structured diagram. Prefer deterministic DSL renderers, but accept arbitrary Mermaid/D2/PlantUML source through the custom DSL route; the built-in semantic kinds are convenience templates, not a closed whitelist.
- `chart`: plots derived from real task data and calculations. Publication-grade
  volcano, ROC, dot plot, marginal, and paired templates are provided by the
  integrated Nature Figure backend.

The action boundary is stable while internal families remain explicit. Read
`references/image-routing-taxonomy.md` and treat its union as the image module's
full regression surface; an integrated family is never omitted from testing.

In managed mode before PLAN_STOP, read the `image` capability report in
`workflow.json.capabilities.image`. It contains action-level status and local
file paths for `ai`, `capture`, `diagram`, and `chart`; a missing upstream,
browser runtime, or DSL renderer is a `blocked` capability, not a reason to
call an unverified external Skill.

Read only the route-specific guidance needed:

- AI assets: read `references/image-parameter-matrix.md` and
  `docs/prompts/image_prompt_rules.md`, then use `generate_images.py` and
  `validate_prompt.py`.
  Run the redacted `autoflow.py env-check --json` preflight once per batch.
  The default policy uses one upstream probe and at most two generation
  attempts per image; increase limits only for a known flaky upstream.
- Browser evidence: use `scripts/capture_frontend_screenshots.py` with a local
  Playwright runtime for the declared capture plan. Verify the app is real and
  locally reachable first; a missing or unreachable browser runtime is a
  `blocked` capability, not a reason to fabricate screenshots.
  Set each screenshot's `capture_scope` deliberately: `viewport` for a
  self-contained viewport, `selector` plus `capture_selector` for one complete
  board/section that extends below the fold, or `page` only when the page itself
  is one board. "Do not use long screenshots" means one image must not combine
  multiple independent boards; it does not limit the height of one complete
  board. Never crop a required board merely to fit one viewport.
- Frontend visual quality: when the step declares
  `design_backend: integrated-impeccable`, read
  `integrations/impeccable/SKILL.md` and follow its command reference and
  local tools — usage knowledge lives in the package, AutoFlow does not
  re-document it. Its offline entry point is
  `integrations/impeccable/scripts/impeccable_adapter.mjs`; any visual
  findings become evidence or remediation inputs, not an automatic approval.
- Diagrams: `docs/prompts/diagram_asset_rules.md`, then use `generate_diagram_assets.py`.
- Scientific schematics: use `generate_scientific_schematic.py` and validate with `validate_scientific_figure.py`.
- Publication charts: read `integrations/nature-figure/SKILL.md` and follow
  it, running the package's own `scripts/plot_templates.py` — usage knowledge
  lives in the package, AutoFlow does not re-document it. Do not invoke a
  user-level nature-figure Skill or depend on the separate source checkout.
- Human visual review: `VISUAL_STOP` is human-only; the agent must present the
  images and wait for explicit approval, and must never approve the gate or
  continue downstream on its own. There is no AI or automatic pre-check:
  every image goes straight from generation to human review, regardless of
  route or content.

In managed mode, group a coherent review batch into one image step. Complete it with the generated directory or manifest as its artifact. A step with `gate_after: visual` activates `VISUAL_STOP`; downstream modules cannot consume the visuals until the user approves them. No automatic quality result may substitute for that approval.

In managed mode before PLAN_STOP, record every planned visual in `requirement_map.json.planned_figures` with a stable id, requirement ids, route, purpose, and expected caption. The number of generated visuals must satisfy this plan. Do not add decorative figures that prove no requirement.

After generation, preserve the route-specific report, source files for diagrams/charts, real capture URL or command where applicable, and any img2img fixup history. A fix creates a new artifact hash and reopens `VISUAL_STOP`.

Reject blurry text, mosaics, malformed UI, inconsistent scene identity, unreadable diagrams, deceptive screenshots, and charts without labels or data provenance.
