# youcansee

一个可安装到多种 coding-agent 的多档位读图 / OCR skill。它在当前模型无法原生看图或原生视觉失败时，调用 `scripts/see_image.py`，通过 OpenAI-compatible vision API、可选本地 VLM，或 Windows OCR 获取图像证据。

[![Skill](https://img.shields.io/badge/agent--skill-youcansee-2563eb)](SKILL.md)
[![License](https://img.shields.io/badge/license-MIT-22c55e)](LICENSE)

## 能力

- `ocr`：完整抄录可见文字；表格尽量输出为 Markdown 表格
- `describe`：结构化描述场景、布局、UI 状态和图中文字
- `ask`：带具体问题进行读图问答
- 四档：`max` / `high` / `medium` / `low`
- 同一档候选 1–9 自动故障转移
- `low` 支持本地 VLM；Windows 支持系统 OCR 兜底
- 本地图片转 base64 data URL；单文件上限 20 MB
- `--dry-run` 只预览请求，不发远程请求

## 安装

### 使用 `npx skills`

将本仓库推送到 GitHub 后，可按仓库地址安装：

```bash
npx skills add <owner>/<repo> --skill youcansee -g -y
```

如果仓库根目录就是这个 skill，也可以直接安装仓库：

```bash
npx skills add <owner>/<repo> -g -y
```

安装到指定 agent 的示例：

```bash
npx skills add <owner>/<repo> --skill youcansee -a codex -a claude-code -y
```

### 本地验证安装

```bash
npx skills add ./youcansee --list
npx skills add ./youcansee --skill youcansee --copy -y
```

> `npx skills add` 支持仓库、仓库子路径和本地 skill 路径。发布前请把 `<owner>/<repo>` 替换为实际 GitHub owner/repository。

## 配置

复制示例配置到用户目录，再填写自己的网关与模型：

```bash
mkdir -p ~/.config
cp youcansee.env.example ~/.config/youcansee.env
chmod 600 ~/.config/youcansee.env
```

环境变量优先于配置文件。按档位配置候选：

```dotenv
YOUCANSEE_MAX_API_KEY=sk-your-key
YOUCANSEE_MAX_BASE_URL=https://your-gateway.example.com/v1
YOUCANSEE_MAX_MODEL=your-vision-model

# 可选备用候选
# YOUCANSEE_MAX_2_API_KEY=sk-backup-key
# YOUCANSEE_MAX_2_BASE_URL=https://backup.example.com/v1
# YOUCANSEE_MAX_2_MODEL=backup-vision-model
```

可选的全局配置：

- `YOUCANSEE_DEFAULT_TIER=max|high|medium|low`
- `YOUCANSEE_LOW_MODE=auto|vlm|ocr`
- `YOUCANSEE_FORCE_JPEG=1`
- `YOUCANSEE_TIMEOUT=180`
- `YOUCANSEE_MAX_TOKENS=4000`

旧版变量 `YOUCANSEE_API_KEY`、`YOUCANSEE_BASE_URL`、`YOUCANSEE_MODEL` 仍作为 `max` 档第一个候选兼容读取。不要把真实 Key 写入仓库、issue、日志或聊天。

## 用法

```bash
python scripts/see_image.py /path/to/image.png
python scripts/see_image.py /path/to/image.png --mode describe --tier high
python scripts/see_image.py /path/to/image.png --ask "表格金额合计是多少？" --tier max
python scripts/see_image.py /path/to/image.png --tier low
python scripts/see_image.py /path/to/image.png --dry-run
```

成功时 stdout 输出单行 JSON，例如：

```json
{"ok": true, "text": "...", "error": null, "tier": "max", "model": "...", "attempts": [], "seconds": 1.2}
```

失败时查看 `error` 和 `attempts`。静态检查、dry-run 或本地 OCR 只能证明对应路径被执行，不能证明远程付费 API 调用成功。

## 目录

```text
youcansee/
├── SKILL.md
├── agents/openai.yaml
├── scripts/see_image.py
├── scripts/ocr_windows.ps1
├── youcansee.env.example
├── LICENSE
├── README.md
├── CHANGELOG.md
└── tests/test_see_image.py
```

## 验证

不需要网络或真实 API Key：

```bash
python3 scripts/verify_skill.py
python3 -m unittest discover -s tests -v
```

验证会检查 frontmatter、公开文件中的疑似密钥、Python 编译、CLI 参数解析、dry-run，以及本地图片大小/路径错误分支。

## 发布

1. 在公开 Git 仓库中保留 `SKILL.md` 及脚本资源。
2. 确认仓库没有真实 Key、私有配置、缓存或本地输出。
3. 推送后用 `npx skills add <owner>/<repo> --list` 检查能发现 `youcansee`。
4. 用 `npx skills add <owner>/<repo> --skill youcansee --copy -y` 做一次干净安装验证。
5. 可选：在 `skills.sh` 或目标 agent 中确认安装后能触发；不要把测试 Key 写入提交。

## 许可证

MIT，见 [LICENSE](LICENSE)。
