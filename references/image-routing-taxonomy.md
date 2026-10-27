# AutoFlow image routing taxonomy

All visual capabilities remain inside the `image` module. Integration changes
implementation ownership, not module boundaries.

| Action | Internal family | Canonical backend |
|---|---|---|
| `capture` | browser/application/terminal evidence | local Playwright capture or deterministic local capture |
| `ai` | general txt2img/img2img | AutoFlow image upstream |
| `ai` | Nature scientific schematics | integrated nature-figure contract + AutoFlow upstream |
| `diagram` | structured DSL diagrams | Mermaid, D2, PlantUML |
| `chart` | ordinary computed charts | task data + local plotting code |
| `chart` | Nature publication templates | integrated nature-figure Python templates |

Full image validation is the union of these families. No integration may be
excluded merely because its implementation lives under `integrations/`.

## AI image size matrix

This is the size matrix supplied for AutoFlow's configured OpenAI-compatible
image upstream. It is a local upstream contract, not a claim that every image
provider or model accepts every value. The upstream API receives a concrete
`size` in `WIDTHxHEIGHT` form; AutoFlow does not send an unverified `4K` or
`aspect_ratio` field to the API.

| Aspect ratio | 1K | 2K | 4K |
| --- | --- | --- | --- |
| 1:1 | 1024x1024 | 2048x2048 | 2880x2880 |
| 3:2 | 1536x1024 | 2160x1440 | 3456x2304 |
| 2:3 | 1024x1536 | 1440x2160 | 2304x3456 |
| 16:9 | 1280x720 | 2560x1440 | 3840x2160 |
| 9:16 | 720x1280 | 1440x2560 | 2160x3840 |
| 4:3 | 1024x768 | 2048x1536 | 3200x2400 |
| 3:4 | 768x1024 | 1536x2048 | 2400x3200 |
| 21:9 | 1280x544 | 2560x1088 | 3840x1600 |

### Batch selection

- A batch without an explicit size uses `resolution: "4K"` and
  `aspect_ratio: "auto"`. `IMAGE_DEFAULT_RESOLUTION` may override the default
  tier, and a task or image entry may override the tier or aspect ratio.
- `auto` is resolved per image before the API request: preserve the nearest
  supported aspect ratio of a reference image; otherwise use 16:9 for screen
  captures/UI mockups and 1:1 for other AI assets. A requested aspect ratio
  must be set explicitly in the image entry (or at batch level); do not let
  these fallbacks override a user requirement.
- An image entry with `resolution: "auto"` inherits the batch tier. Explicit
  `WIDTHxHEIGHT` values remain accepted for existing configurations. A
  conflicting explicit `aspect_ratio` and pixel size is an error.
- The chosen pixel size is passed unchanged as the API `size` parameter.
  Actual acceptance is determined by the configured model/upstream; report a
  rejected size and do not silently substitute a different tier or ratio.

### Reference-image editing

For `image.ai` batches with `reference_image`, `IMAGE_EDIT_MODEL` selects the
primary model (blank inherits `IMAGE_MODEL`). `IMAGE_EDIT_DEFAULT_RESOLUTION`
defaults to 4K; the reference image supplies the auto aspect ratio. A task or
image entry can explicitly override the edit settings. The primary model is
tried up to `IMAGE_EDIT_MAX_RETRIES` times. Only after those attempts fail does
`IMAGE_EDIT_FALLBACK_MODEL` run, with its own retry budget. A blank fallback
disables it. The result records the actual model and whether fallback ran.
