# Environment Initialization

Use these Agent instructions to check and prepare the environment required to
run AutoFlow and the selected module. This document is client-neutral: run the
commands from the installed Skill root, regardless of the host Agent client.
Workspace layout and execution-mode setup belong in `SKILL.md`.

```bash
python --version
python -m pip --version
git --version
node --version
```

Install only the missing dependencies required by the selected module, then
repeat its check. From the Skill root, install AutoFlow's Python dependencies
with:

```bash
python -m pip install -r requirements.txt
```

| Need | Check | Install when missing |
|---|---|---|
| Git for task research/build | `git --version` | Use the host package manager, for example `winget install --id Git.Git -e`, `brew install git`, or `sudo apt-get install git`. |
| Node tooling | `node --version` | Use the host package manager, for example `winget install --id OpenJS.NodeJS.LTS -e`, `brew install node`, or `sudo apt-get install nodejs npm`. |
| .NET SDK for Minimax Word | `dotnet --version` | Use the official .NET installer or the host package manager, for example `winget install --id Microsoft.DotNet.SDK.8 -e`, `brew install dotnet-sdk`, or `sudo apt-get install dotnet-sdk-8.0`. |
| Browser capture | `python -c "import playwright"` | `python -m pip install playwright`, then `python -m playwright install chromium`. If the browser is not on `PATH`, set `AUTOFLOW_BROWSER_PATH` to its executable. |
| Mermaid diagrams | `mmdc --version` | `npm install -g @mermaid-js/mermaid-cli` |
| D2 diagrams | `d2 --version` | Install D2 with the host package manager or the official D2 installer. |
| Office documents | `officecli --version` | Follow the platform-specific installer in `integrations/officecli/SKILL.md`. |
| Video processing | `ffmpeg -version` | Use the host package manager, for example `winget install --id Gyan.FFmpeg -e`, `brew install ffmpeg`, or `sudo apt-get install ffmpeg`. |

Do not create image API credentials or invent values for `BASEURL` or `APIKEY`.
An unavailable AI-image route remains blocked until the user supplies valid
credentials.

AutoFlow reads a client-neutral `.env` at the Skill root. Prefer `KEY=value`
lines; legacy `KEY:value` lines remain readable for compatibility. Run the
capability check once before a batch and do not print secret values:

```bash
python scripts/autoflow.py capabilities --json
```

The AI report includes the configured image model, default resolution, retry
limits, and missing validator fields without exposing `APIKEY` values. The
default image settings are `IMAGE_MODEL=gpt-image-2.5`,
`IMAGE_DEFAULT_RESOLUTION=4K` (batch tier, auto aspect ratio),
`IMAGE_MAX_RETRIES=2`, and
`IMAGE_PROBE_RETRIES=1`.

Office backends are not configured in `.env`. The checked-in
`integrations/minimax-docx` package is the default for complex Word reports and
theses; its check verifies the .NET runtime. `officecli` remains the common
validation/render backend and is suitable for simple Word edits. The Agent
selects by task shape and never silently substitutes an unavailable backend.
