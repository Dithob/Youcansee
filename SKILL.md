---
name: youcansee
description: >-
  Read, OCR, describe, or answer questions about local images when the current
  model cannot see images natively or native vision fails. Use the bundled
  scripts/see_image.py helper, which supports an OpenAI-compatible vision API,
  four quality tiers (max/high/medium/low), per-tier provider failover, local
  VLMs, and Windows OCR. Triggers include 读图、看图、OCR、截图内容、图片描述、图片里是什么；
  English triggers include read image、look at image、OCR、image text、screenshot content、
  describe image、what is in this image、image question、visual question answering；
  tier selectors include 最强神眼/全力/完全体/最高档/max、最强、天花板，
  高档/high/stronger/clearer、 中档/medium/normal/quick/balanced、
  低档/low/local/cheap/save money/offline/fast。
  Do not use this skill for image generation or editing.
license: MIT
---

# YouCanSee：多档位读图

## When to use

- The user gives a local image path or image URL and asks for OCR, a description, or visual question answering.
- The current model cannot inspect images natively, or native image inspection returned an unsupported-image/error result.
- The user explicitly selects a quality tier such as `max`, `high`, `medium`, or `low`.

If the current model can reliably inspect the image natively, use that capability first and do not run the helper script.

## Workflow

1. Confirm the image path or URL. For a local file, the helper accepts images up to 20 MB.
2. If native vision is unavailable or failed, run:

   ```bash
   python scripts/see_image.py <image-path-or-url> [--mode ocr|describe|ask] [--ask "question"] [--tier max|high|medium|low] [--provider N]
   ```

3. Parse the single JSON result printed to stdout.
   - `ok: true`: use `text` as the image evidence and continue the user's task.
   - `ok: false`: report `error` faithfully; use `attempts` to explain which candidates were tried.
4. Do not claim a successful remote vision call when only `--dry-run`, local static checks, or Windows OCR was exercised.

## Tier selection

| Tier | Use when the user says | Behavior |
|---|---|---|
| `max` | 最强神眼、全力、完全体、最高档、最强、天花板; `max`, strongest, best quality, highest quality, top quality, maximum, full power | Highest configured cloud/API tier; default when configured |
| `high` | 高档、好一点、更清晰; `high`, higher quality, better quality, clearer, more accurate, strong | Stronger configured cloud/API tier |
| `medium` | 中档、普通、快速、平衡; `medium`, normal quality, standard quality, quick, fast, balanced | Middle configured cloud/API tier |
| `low` | 低档、本地、省钱、离线、快一点; `low`, local, cheap, low cost, offline, fastest, save money | Local VLM first when configured; Windows OCR fallback on Windows |

When no tier is specified, use `YOUCANSEE_DEFAULT_TIER`; otherwise choose the highest available configured tier in `max → high → medium → low` order.

## Modes and examples

- `ocr` (default): transcribe visible text; preserve text, numbers, symbols, and tables.
- `describe`: describe scene, layout, UI state, and visible text.
- `ask`: answer a specific image question with `--ask`.

```bash
python scripts/see_image.py "/path/to/screenshot.png"
python scripts/see_image.py "/path/to/screenshot.png" --mode describe --tier high
python scripts/see_image.py "/path/to/screenshot.png" --ask "表格金额合计是多少？" --tier max
python scripts/see_image.py "/path/to/screenshot.png" --tier low
python scripts/see_image.py "/path/to/screenshot.png" --dry-run
```

## Configuration and safety

- Copy `youcansee.env.example` to `~/.config/youcansee.env` and fill in the user's own endpoint and key. Environment variables override file values.
- Keep keys only in environment variables or the user's local config file. Never put secrets in this repository, generated logs, or chat messages.
- Configure candidates as `YOUCANSEE_<TIER>_BASE_URL`, `_API_KEY`, and `_MODEL`; candidates 2–9 use `_2_` through `_9_`. The legacy `YOUCANSEE_API_KEY`, `YOUCANSEE_BASE_URL`, and `YOUCANSEE_MODEL` names remain supported as the first `max` candidate.
- `YOUCANSEE_LOW_MODE=auto|vlm|ocr` controls local fallback. `low` VLM candidates should use a local endpoint such as Ollama; Windows OCR needs no API key.
- The script reads `~/.config/youcansee.env`, optional compatibility config `~/.config/image-see.env`, and platform-specific readable mirrors. It may synchronize the canonical config to those mirrors; do not use this behavior to store credentials in the repository.
- The helper sends local images as base64 data URLs to API candidates. Use `--dry-run` to inspect the endpoint and redacted payload without making a request.

## Limitations

- This skill reads/describes images; it does not generate or edit them.
- API behavior depends on the configured OpenAI-compatible gateway and vision-capable model.
- Windows OCR is available only when the host has PowerShell, Windows Runtime OCR, and the required language pack.
