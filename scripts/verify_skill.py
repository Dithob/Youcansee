#!/usr/bin/env python3
"""Offline repository checks for the youcansee skill."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"VERIFY_FAIL: {message}")


def require_file(relative: str) -> Path:
    path = ROOT / relative
    if not path.is_file():
        fail(f"missing file: {relative}")
    return path


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        fail("SKILL.md does not have YAML frontmatter")
    values: dict[str, str] = {}
    current = None
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  ") and current:
            values[current] = values[current] + " " + line.strip()
            continue
        key, sep, value = line.partition(":")
        if not sep:
            fail(f"invalid frontmatter line: {line}")
        current = key.strip()
        values[current] = value.strip().strip('"\'')
    for key in ("name", "description"):
        if not values.get(key):
            fail(f"missing frontmatter key: {key}")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", values["name"]):
        fail("skill name is not hyphen-case")
    return values


def check_no_secrets() -> None:
    secret_pattern = re.compile(
        r"(?:sk-[A-Za-z0-9_-]{12,}|(?:api[_-]?key|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{16,})",
        re.IGNORECASE,
    )
    ignored = {"__pycache__", ".git"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in ignored for part in path.parts):
            continue
        if path.name in {"verify_skill.py", "test_see_image.py", "youcansee.env.example"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if secret_pattern.search(text):
            fail(f"possible secret in {path.relative_to(ROOT)}")


def run(*args: str, expect: int = 0) -> str:
    proc = subprocess.run(args, cwd=ROOT, text=True, capture_output=True)
    if proc.returncode != expect:
        fail(f"command failed ({proc.returncode} != {expect}): {' '.join(args)}\n{proc.stdout}{proc.stderr}")
    return proc.stdout


def main() -> int:
    parse_frontmatter(require_file("SKILL.md"))
    require_file("agents/openai.yaml")
    require_file("scripts/see_image.py")
    require_file("scripts/ocr_windows.ps1")
    require_file("youcansee.env.example")
    require_file("LICENSE")
    require_file("README.md")
    if not (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8").startswith("interface:\n"):
        fail("agents/openai.yaml is missing interface metadata")
    check_no_secrets()
    compile_env = dict(os.environ)
    compile_env.setdefault("PYTHONPYCACHEPREFIX", "/tmp/youcansee-pycache")
    compile_proc = subprocess.run(
        [sys.executable, "-m", "py_compile", "scripts/see_image.py", "scripts/verify_skill.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=compile_env,
    )
    if compile_proc.returncode != 0:
        fail(f"Python compilation failed:\n{compile_proc.stdout}{compile_proc.stderr}")
    with tempfile.TemporaryDirectory() as temp_dir:
        image = Path(temp_dir) / "fixture.png"
        image.write_bytes(b"not-a-real-image")
        env = dict(os.environ)
        for key in tuple(env):
            if key.startswith("YOUCANSEE_") or key.startswith("IMAGE_SEE_"):
                env.pop(key)
        proc = subprocess.run(
            [sys.executable, "scripts/see_image.py", str(image)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            env=env,
        )
        if proc.returncode != 1 or '"ok": false' not in proc.stdout or "没有任何可用配置" not in proc.stdout:
            fail("missing-config branch did not return expected JSON")
    print("VERIFY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
