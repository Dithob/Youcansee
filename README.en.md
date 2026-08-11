# youcansee

[English](README.en.md) | [中文](README.md)

An installable multi-tier image-reading and OCR skill for coding agents. When the
current model cannot inspect images natively, or native vision fails, it calls
`scripts/see_image.py` and obtains image evidence through an OpenAI-compatible
vision API, an optional local VLM, or Windows OCR.

[![Skill](https://img.shields.io/badge/agent--skill-youcansee-2563eb)](SKILL.md)
[![License](https://img.shields.io/badge/license-MIT-22c55e)](LICENSE)

## Capabilities

- `ocr`: transcribe visible text, preserving numbers, symbols, and tables where possible
- `describe`: describe the scene, layout, UI state, and visible text
- `ask`: answer a specific question about an image
- Four tiers: `max` / `high` / `medium` / `low`
- Automatic failover across candidates 1–9 within the selected tier
- Local VLM support for `low`; Windows system OCR fallback on Windows
- Local images are sent as base64 data URLs; the per-file limit is 20 MB
- `--dry-run` previews the request without making a remote call

## Installation

### With `npx skills`

After pushing this repository to GitHub, install it by repository address:

```bash
npx skills add <owner>/<repo> --skill youcansee -g -y
```

If the repository root contains only this skill, you can install the repository
directly:

```bash
npx skills add <owner>/<repo> -g -y
```

Install it for specific agents:

```bash
npx skills add <owner>/<repo> --skill youcansee -a codex -a claude-code -y
```

### Verify a local installation

```bash
npx skills add . --list
npx skills add . --skill youcansee --copy -y
```

> `npx skills add` supports repositories, repository subpaths, and local skill
> paths. Replace `<owner>/<repo>` with the actual GitHub owner/repository before
> publishing.

## Configuration

Copy the example configuration to the user config directory and fill in your
own gateway and model:

```bash
mkdir -p ~/.config
cp youcansee.env.example ~/.config/youcansee.env
chmod 600 ~/.config/youcansee.env
```

Environment variables take precedence over config files. Configure candidates
by tier:

```dotenv
YOUCANSEE_MAX_API_KEY=sk-your-key
YOUCANSEE_MAX_BASE_URL=https://your-gateway.example.com/v1
YOUCANSEE_MAX_MODEL=your-vision-model

# Optional backup candidate
# YOUCANSEE_MAX_2_API_KEY=sk-backup-key
# YOUCANSEE_MAX_2_BASE_URL=https://backup.example.com/v1
# YOUCANSEE_MAX_2_MODEL=backup-vision-model
```

Optional global settings:

- `YOUCANSEE_DEFAULT_TIER=max|high|medium|low`
- `YOUCANSEE_LOW_MODE=auto|vlm|ocr`
- `YOUCANSEE_FORCE_JPEG=1`
- `YOUCANSEE_TIMEOUT=180`
- `YOUCANSEE_MAX_TOKENS=4000`

The legacy variables `YOUCANSEE_API_KEY`, `YOUCANSEE_BASE_URL`, and
`YOUCANSEE_MODEL` are still supported as the first candidate of the `max`
tier. Never put a real key in the repository, issues, logs, or chat messages.

## Usage

```bash
python scripts/see_image.py /path/to/image.png
python scripts/see_image.py /path/to/image.png --mode describe --tier high
python scripts/see_image.py /path/to/image.png --ask "What is the total amount in the table?" --tier max
python scripts/see_image.py /path/to/image.png --tier low
python scripts/see_image.py /path/to/image.png --dry-run
```

On success, stdout contains one line of JSON, for example:

```json
{"ok": true, "text": "...", "error": null, "tier": "max", "model": "...", "attempts": [], "seconds": 1.2}
```

On failure, inspect `error` and `attempts`. Static checks, `--dry-run`, and
local OCR only prove that the corresponding path ran; they do not prove that a
remote paid API call succeeded.

## Repository layout

```text
youcansee/
├── SKILL.md
├── README.md
├── README.en.md
├── agents/openai.yaml
├── scripts/see_image.py
├── scripts/ocr_windows.ps1
├── youcansee.env.example
├── LICENSE
├── CHANGELOG.md
└── tests/test_see_image.py
```

## Validation

No network or real API key is required:

```bash
python3 scripts/verify_skill.py
python3 -m unittest discover -s tests -v
```

The checks cover frontmatter, possible secrets in public files, Python
compilation, CLI argument parsing, `--dry-run`, and local image
size/path-error branches.

## Publishing

1. Keep `SKILL.md` and its scripts in a public Git repository.
2. Confirm that the repository contains no real keys, private config, caches,
   or local output.
3. After pushing, run `npx skills add <owner>/<repo> --list` to verify that
   `youcansee` is discoverable.
4. Run
   `npx skills add <owner>/<repo> --skill youcansee --copy -y` as a clean
   installation check.
5. Optionally confirm installation and triggering in `skills.sh` or your
   target agent. Do not commit test keys.

## License

MIT. See [LICENSE](LICENSE).
