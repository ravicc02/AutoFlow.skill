# Image Prompt Rules

This document defines how `AutoFlow image.ai` should write its prompt configuration.

## Scope boundary

`prompt_config.json` is only for the `image.ai` action.

Use it for:
- terminal screenshots
- command output screenshots
- software / system configuration screenshots

Do not use it for:
- local frontend page screenshots
- self-built app/web product flows
- development software practice screenshots for the user's own app/web project when the UI should reflect the local running build
- function diagrams, flowcharts, data flow diagrams, or ER diagrams

Those belong to `image.capture`, `image.diagram`, or `image.chart` plans.

## Planning order

Before writing prompts:
1. Read the requirement document.
2. Read the image step and its declared input artifacts.
3. Complete required task steps and absorb their real outputs.
4. Decide which assets require `image.ai`, `image.capture`, `image.diagram`, or `image.chart`.
5. Only write prompts for assets assigned to `image.ai`.

## Prompt quality rules

- The goal is believable screenshot realism, not explainer collage style.
- The whole image set should share one coherent environment.
- The whole image set should stay consistent at the environment, lighting, UI rendering, and camera-treatment level.
- Keep the background treatment consistent across the set unless the requirement explicitly needs different scenes.
- Show only necessary information and keep a believable background.
- Avoid high information density, tiny unreadable text blocks, and overloaded dashboards.
- Require pixel-level sharpness, crisp readable text, and clean UI edges.
- Explicitly forbid blur, haze, mosaic blocks, blocky compression, smeared glyphs, and muddy textures.
- If time or date appears on screen, keep it realistic and temporally consistent across the same screenshot session.
- Use the application's real URL. If the app genuinely runs on localhost, localhost is the real URL — do not fabricate a fake production domain. Only avoid exposing obviously temporary dev-server ephemeral ports (e.g., `:3000`, `:5173`) unless they are part of the actual running application.
- Do not expose AI origin through visible text such as `AI生成`, `示意图`, or similar.
- Do not use poster / callout / diagram language for screenshot prompts.

## Output contract

`prompt_config.json` should:
- match only the `image.ai` artifacts
- keep names aligned with `copywriting.md` placeholders
- never include browser-capture-only or diagram-only figures
- stay free of comments and helper fields

## Resolution and concurrency

- Read `references/image-parameter-matrix.md` for all 1K/2K/4K and eight
  aspect-ratio combinations. The batch default is `resolution: "4K"` plus
  `aspect_ratio: "auto"`, resolved for each image before requesting the API.
- Select a requested ratio explicitly. When it is unspecified, auto follows a
  reference image, then the asset-type fallback documented in the matrix.
- Use `2560x1440` for 2K 16:9 and `3840x2160` for 4K 16:9. Existing explicit
  pixel sizes remain valid; do not relabel a legacy size as a matrix preset.
- Do not assume maximum concurrency is supported upstream.
- Test 2K/4K 16:9 with `tests/test_image_concurrency.py` when a batch run will be expensive or time-sensitive.
- If high concurrency fails, reduce to the highest passing worker count and record whether the failure came from upstream API rejection, timeout/rate limits, or a local script/config issue.
- If only part of a batch fails or only a subset needs regeneration after visual review, create and use a supplement config instead of rerunning the full batch.
