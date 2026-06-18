---
description: "Ghi log AI thủ công — CHỈ dùng cho web tool (ChatGPT, Gemini Web, Claude.ai, v.v.). KHÔNG dùng cho Antigravity."
---

# Ghi log AI thủ công (chỉ web tool)

Antigravity IDE, Claude Code, Cursor, Codex, Copilot, Gemini CLI đã **tự động log** qua hook hoặc qua `log_antigravity.py` chạy trong pre-push. **Không cần** chạy lệnh dưới đây cho các tool đó.

Workflow này chỉ dành cho khi bạn dùng **tool web không có hook** — ví dụ ChatGPT, Gemini Web, Claude.ai, Perplexity, v.v.

## Cách chạy

**Linux / macOS / Git Bash:**
```bash
# Interactive mode (script sẽ hỏi tool + prompt)
bash scripts/_pyrun.sh scripts/log_manual.py

# One-line mode
bash scripts/_pyrun.sh scripts/log_manual.py --tool "<tên tool>" --prompt "<mô tả việc đã làm>"
```

**Windows (cmd.exe / PowerShell):**
```cmd
scripts\_pyrun.cmd scripts\log_manual.py
scripts\_pyrun.cmd scripts\log_manual.py --tool "<tên tool>" --prompt "<mô tả việc đã làm>"
```

## Ví dụ

```bash
bash scripts/_pyrun.sh scripts/log_manual.py --tool chatgpt --prompt "Brainstorm UI layout for verify page"
bash scripts/_pyrun.sh scripts/log_manual.py --tool gemini-web --prompt "Research risk scoring algorithms"
bash scripts/_pyrun.sh scripts/log_manual.py --tool claude-web --prompt "Explain OAuth2 PKCE flow"
```

Entry sẽ được append vào `.ai-log/session.jsonl` và submit cùng các log auto khác trong lần `git push` kế tiếp.
