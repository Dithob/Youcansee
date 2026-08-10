#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
see_image.py - YouCanSee 多档位读图脚本

给没有视觉能力的模型（如 DeepSeek 纯文本模型）补眼睛：
把本地图片（或 http(s) 图片 URL）发给 OpenAI 兼容的多模态模型，把返回的文字给主模型继续推理。

档位（tier）：max > high > medium > low
- 每档可配多个候选（自动兜底：连接失败 / 超时 / HTTP 错误 / 返回空 / 解析失败 -> 试下一个）
- low 档支持本地 OCR（Windows 自带）或本地 VLM（如 Ollama），无需云端 Key

配置来源优先级：环境变量 > ~/.config/youcansee.env > ~/.config/image-see.env（兼容旧配置）

配置命名：
  候选 1：YOUCANSEE_MAX_API_KEY / YOUCANSEE_MAX_BASE_URL / YOUCANSEE_MAX_MODEL
  候选 2：YOUCANSEE_MAX_2_API_KEY / YOUCANSEE_MAX_2_BASE_URL / YOUCANSEE_MAX_2_MODEL
  候选 N：YOUCANSEE_MAX_{N}_...（N 最大 9）；档位名换成 HIGH / MEDIUM / LOW 同理

兼容旧配置：YOUCANSEE_API_KEY / YOUCANSEE_BASE_URL / YOUCANSEE_MODEL 自动作为 max 档候选 1。

low 档特殊变量：
  YOUCANSEE_LOW_MODE=auto|vlm|ocr   默认 auto
    auto：先试本地 VLM（配置了 base_url），失败再用 Windows 本地 OCR
    vlm ：只用本地 VLM 候选
    ocr ：只用 Windows 本地 OCR（不需要 Key 与网络）
  本地 VLM 示例（Ollama）：
    YOUCANSEE_LOW_BASE_URL=http://127.0.0.1:11434/v1
    YOUCANSEE_LOW_MODEL=llava

其它变量：
  YOUCANSEE_DEFAULT_TIER   未指定档位时的默认档（不配则自动选最高可用档）
  YOUCANSEE_FORCE_JPEG / YOUCANSEE_TIMEOUT / YOUCANSEE_MAX_TOKENS（作用于 API 候选）

用法：
  python see_image.py <图片路径或URL> [--mode ocr|describe|ask] [--ask "问题"]
                       [--tier max|high|medium|low] [--provider N] [--dry-run]

输出：stdout 打印 JSON {"ok","text","error","tier","model","attempts","seconds"}
"""

import base64
import io
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

MAX_FILE_MB = 20
DEFAULT_MODEL = "gpt-5.6-luna"
DEFAULT_TIMEOUT = 180
DEFAULT_MAX_TOKENS = 4000
MODES = {"ocr", "describe", "ask"}
TIER_ORDER = ["max", "high", "medium", "low"]
MAX_CANDIDATES = 9
USAGE = '用法: see_image.py <图片> [--mode ocr|describe|ask] [--ask "问题"] [--tier max|high|medium|low] [--provider N] [--dry-run]'

PROMPTS = {
    "ocr": (
        "你是精确的读图助手（给无法看图的大模型当眼睛）。"
        "请完整抄录图片中的全部可见文字（含中文、英文、数字、符号、表格）。"
        "按原样输出，不要翻译，不要总结，不要加解释。"
        "表格请用 Markdown 表格输出。若几乎无文字，再简短说明画面内容。"
    ),
    "describe": (
        "请结构化描述这张图片：场景、主体、布局、关键细节以及图中文字；"
        "若是截图或 UI，请说明界面元素、状态和可见文字。"
    ),
}

# Windows 控制台 UTF-8 输出，避免 GBK 报错
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def parse_env_file(path):
    data = {}
    if not path or not os.path.isfile(path):
        return data
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                data[key.strip()] = val.strip().strip('"').strip("'")
    except OSError:
        pass
    return data


def resolve_config():
    """合并配置源，返回 (tiers, globals)。"""
    merged = {}
    # 跨 Agent 配置镜像：主配置 ~/.config/youcansee.env 由所有 Agent 按标准约定读取；
    # 若某个 Agent 的沙箱读不到该路径，脚本会回退到其各自目录下的镜像副本：
    # - ~/.codex/youcansee/youcansee.env（Codex 沙箱可读）
    # - ~/.claude/youcansee.env（Claude 等沙箱可读）
    # 主配置可读时优先采用它，并尽力把最新内容同步到所有镜像，避免多份漂移。
    canonical = os.path.expanduser("~/.config/youcansee.env")
    mirrors = [
        os.path.expanduser("~/.codex/youcansee/youcansee.env"),
        os.path.expanduser("~/.claude/youcansee.env"),
    ]
    try:
        if os.path.isfile(canonical):
            with open(canonical, "rb") as f:
                data = f.read()
            for mirror in mirrors:
                try:
                    need_sync = True
                    if os.path.isfile(mirror):
                        with open(mirror, "rb") as f:
                            need_sync = f.read() != data
                    if need_sync:
                        os.makedirs(os.path.dirname(mirror), exist_ok=True)
                        tmp = mirror + ".tmp"
                        with open(tmp, "wb") as f:
                            f.write(data)
                        os.replace(tmp, mirror)
                except OSError:
                    continue
    except OSError:
        pass
    files = [parse_env_file(canonical)]
    for mirror in mirrors:
        files.append(parse_env_file(mirror))
    files.append(parse_env_file(os.path.expanduser("~/.config/image-see.env")))
    for src in [os.environ] + files:
        for k, v in src.items():
            if k not in merged:
                merged[k] = v

    def first(*names):
        for n in names:
            v = merged.get(n)
            if v:
                return str(v).strip()
        return None

    force_jpeg = first("YOUCANSEE_FORCE_JPEG", "IMAGE_SEE_FORCE_JPEG") == "1"
    try:
        timeout = float(first("YOUCANSEE_TIMEOUT", "IMAGE_SEE_TIMEOUT") or DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        timeout = float(DEFAULT_TIMEOUT)
    try:
        max_tokens = int(first("YOUCANSEE_MAX_TOKENS", "IMAGE_SEE_MAX_TOKENS") or DEFAULT_MAX_TOKENS)
    except (TypeError, ValueError):
        max_tokens = int(DEFAULT_MAX_TOKENS)
    default_tier = first("YOUCANSEE_DEFAULT_TIER") or None
    if default_tier and default_tier not in TIER_ORDER:
        default_tier = None
    low_mode = (first("YOUCANSEE_LOW_MODE") or "auto").lower()
    if low_mode not in ("auto", "vlm", "ocr"):
        low_mode = "auto"

    legacy = None
    legacy_base = first("YOUCANSEE_BASE_URL", "IMAGE_SEE_BASE_URL")
    if legacy_base:
        legacy = {
            "kind": "api",
            "api_key": first("YOUCANSEE_API_KEY", "IMAGE_SEE_API_KEY") or "",
            "base_url": legacy_base,
            "model": first("YOUCANSEE_MODEL", "IMAGE_SEE_MODEL") or DEFAULT_MODEL,
            "timeout": timeout,
            "max_tokens": max_tokens,
        }

    tiers = {}
    for tier in TIER_ORDER:
        cands = []
        for n in range(1, MAX_CANDIDATES + 1):
            mid = "" if n == 1 else str(n)
            pref = "YOUCANSEE_" + tier.upper() + ("" if n == 1 else "_" + mid) + "_"
            base_url = first(pref + "BASE_URL")
            if not base_url:
                continue
            cand = {
                "kind": "api",
                "api_key": first(pref + "API_KEY") or "",
                "base_url": base_url,
                "model": first(pref + "MODEL") or DEFAULT_MODEL,
                "timeout": float(first(pref + "TIMEOUT") or timeout),
                "max_tokens": int(first(pref + "MAX_TOKENS") or max_tokens),
            }
            cands.append(cand)
        if tier == "max" and legacy and not first("YOUCANSEE_MAX_BASE_URL"):
            cands.insert(0, dict(legacy))
        tiers[tier] = cands

    return tiers, {
        "force_jpeg": force_jpeg,
        "timeout": timeout,
        "max_tokens": max_tokens,
        "default_tier": default_tier,
        "low_mode": low_mode,
    }


def chat_endpoint(base):
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def try_jpeg_bytes(src):
    try:
        from PIL import Image
        img = Image.open(src)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=90)
        return buf.getvalue()
    except Exception:
        return None


def to_image_url(src, force_jpeg):
    if re.match(r"^https?://", src, re.IGNORECASE):
        return src
    if not os.path.isfile(src):
        raise ValueError("图片文件不存在: " + src)
    size_mb = os.path.getsize(src) / 1024.0 / 1024.0
    if size_mb > MAX_FILE_MB:
        raise ValueError("图片超过 20MB 上限: %.1fMB" % size_mb)
    mime, _ = mimetypes.guess_type(src)
    ext = os.path.splitext(src)[1].lower()
    if not mime or not mime.startswith("image/"):
        mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
                ".webp": "image/webp", ".bmp": "image/bmp"}.get(ext, "image/png")
    if force_jpeg and ext not in (".jpg", ".jpeg"):
        jpg = try_jpeg_bytes(src)
        if jpg:
            return "data:image/jpeg;base64," + base64.b64encode(jpg).decode("ascii")
    with open(src, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return "data:%s;base64,%s" % (mime, b64)


def local_ocr(image_src):
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ocr_windows.ps1")
    if not os.path.isfile(script):
        raise RuntimeError("缺少 ocr_windows.ps1")
    cmd = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", script, "-Path", image_src,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)
    if proc.returncode != 0:
        err = (proc.stderr or "").strip()[:500]
        raise RuntimeError("本地 OCR 失败: " + err if err else "本地 OCR 失败")
    out = (proc.stdout or "").strip()
    if not out:
        raise RuntimeError("本地 OCR 未识别到文字")
    return out


def parse_args(argv):
    mode = "ocr"
    ask = None
    dry_run = False
    tier = None
    only_index = None
    image = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--dry-run":
            dry_run = True
        elif a == "--mode":
            i += 1
            if i >= len(argv) or argv[i] not in MODES:
                die(USAGE)
            mode = argv[i]
        elif a == "--ask":
            i += 1
            if i >= len(argv):
                die("--ask 需要一个问题参数")
            ask = argv[i]
            mode = "ask"
        elif a == "--tier":
            i += 1
            if i >= len(argv) or argv[i] not in TIER_ORDER:
                die("--tier 需要 max|high|medium|low 之一")
            tier = argv[i]
        elif a == "--provider":
            i += 1
            if i >= len(argv) or not argv[i].isdigit():
                die("--provider 需要一个数字（1-9）")
            only_index = int(argv[i])
        elif a.startswith("--"):
            die("未知参数: " + a)
        elif image is None:
            image = a
        else:
            die("多余参数: " + a)
        i += 1
    if not image:
        die(USAGE)
    prompt = ask if ask is not None else PROMPTS[mode]
    return image, prompt, dry_run, tier, only_index


def build_payload(cand, prompt, image_url):
    return {
        "model": cand["model"],
        "temperature": 0,
        "stream": False,
        "max_tokens": cand["max_tokens"],
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url, "detail": "auto"}},
            ],
        }],
    }


def call_api(cand, payload):
    endpoint = chat_endpoint(cand["base_url"])
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if cand["api_key"]:
        headers["Authorization"] = "Bearer " + cand["api_key"]
    req = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=cand["timeout"]) as resp:
        body = resp.read().decode("utf-8", "replace")
    obj = json.loads(body)
    text = obj["choices"][0]["message"]["content"]
    if isinstance(text, list):
        text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
    text = str(text).strip() if text is not None else ""
    if not text:
        raise RuntimeError("模型返回空内容")
    return text


def run_candidate(cand, prompt, image_src, image_url):
    if cand["kind"] == "local-ocr":
        return local_ocr(image_src)
    return call_api(cand, build_payload(cand, prompt, image_url))


def emit(ok, text=None, error=None, tier=None, model=DEFAULT_MODEL,
         seconds=0.0, attempts=None):
    out = {
        "ok": ok,
        "text": text,
        "error": error,
        "tier": tier,
        "model": model,
        "attempts": attempts or [],
        "seconds": round(seconds, 1),
    }
    print(json.dumps(out, ensure_ascii=False))


def main(argv):
    t0 = time.time()
    image_src, prompt, dry_run, tier_name, only_index = parse_args(argv)
    tiers, g = resolve_config()

    tier = tier_name or g["default_tier"]
    if tier is None:
        for t in TIER_ORDER:
            if tiers[t] or (t == "low" and g["low_mode"] in ("auto", "ocr") and os.name == "nt"):
                tier = t
                break
    if tier is None:
        emit(False, error=(
            "没有任何可用配置。请在 ~/.config/youcansee.env 中配置至少一个模型："
            "YOUCANSEE_API_KEY / YOUCANSEE_BASE_URL / YOUCANSEE_MODEL（或按档位 "
            "YOUCANSEE_MAX_* / HIGH / MEDIUM / LOW，low 档也可纯本地 OCR）。"),
            seconds=time.time() - t0)
        return 1

    cands = []
    if tier == "low":
        mode = g["low_mode"]
        if mode == "ocr":
            if os.name == "nt":
                cands.append({"kind": "local-ocr", "model": "Windows OCR"})
        elif mode == "vlm":
            cands = list(tiers["low"])
        else:
            cands = list(tiers["low"])
            if os.name == "nt":
                cands.append({"kind": "local-ocr", "model": "Windows OCR"})
    else:
        cands = list(tiers[tier])

    if not cands:
        emit(False, error=("档位 " + tier + " 没有任何可用候选。请配置 "
                           "YOUCANSEE_" + tier.upper() + "_BASE_URL 等变量。"),
             tier=tier, seconds=time.time() - t0)
        return 1

    if only_index is not None:
        if only_index < 1 or only_index > len(cands):
            emit(False, error=("--provider %d 超出范围（档位 %s 共有 %d 个候选）"
                               % (only_index, tier, len(cands))),
                 tier=tier, seconds=time.time() - t0)
            return 1
        cands = [cands[only_index - 1]]

    try:
        image_url = to_image_url(image_src, g["force_jpeg"])
    except ValueError as e:
        emit(False, error=str(e), tier=tier, seconds=time.time() - t0)
        return 1

    attempts = []
    last_error = None
    for n, cand in enumerate(cands, 1):
        t1 = time.time()
        attempt = {
            "tier": tier,
            "cand": n,
            "kind": cand.get("kind", "api"),
            "model": cand.get("model", ""),
            "base_url": cand.get("base_url", "local"),
            "status": "ok",
            "error": None,
        }
        if dry_run:
            attempt["status"] = "dry-run"
            if cand.get("kind") == "local-ocr":
                print("[dry-run] local Windows OCR, model=" + str(cand.get("model")), file=sys.stderr)
            else:
                payload = build_payload(cand, prompt, image_url)
                preview = json.loads(json.dumps(payload))
                u = preview["messages"][0]["content"][1]["image_url"]["url"]
                if u.startswith("data:"):
                    preview["messages"][0]["content"][1]["image_url"]["url"] = u[:40] + "...<base64 %d chars>" % len(u)
                print("[dry-run] POST " + chat_endpoint(cand["base_url"]) + " model=" + cand["model"], file=sys.stderr)
                print(json.dumps(preview, ensure_ascii=False, indent=2), file=sys.stderr)
            attempt["seconds"] = round(time.time() - t1, 1)
            attempts.append(attempt)
            continue
        try:
            text = run_candidate(cand, prompt, image_src, image_url)
            attempt["seconds"] = round(time.time() - t1, 1)
            attempts.append(attempt)
            emit(True, text=text, tier=tier, model=attempt["model"],
                 seconds=time.time() - t0, attempts=attempts)
            return 0
        except Exception as e:
            attempt["status"] = "error"
            attempt["error"] = str(e)
            attempt["seconds"] = round(time.time() - t1, 1)
            attempts.append(attempt)
            last_error = str(e)

    if dry_run:
        emit(True, text="(dry-run)", tier=tier, model=cands[0].get("model", DEFAULT_MODEL),
             seconds=time.time() - t0, attempts=attempts)
        return 0

    emit(False, error=("档位 " + tier + " 全部 " + str(len(attempts)) + " 个候选失败。"
                       "最后一个错误: " + last_error),
         tier=tier, seconds=time.time() - t0, attempts=attempts)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
