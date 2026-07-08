#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

mkdir -p .ai-log/archive .git/hooks
touch .ai-log/.gitkeep

cat > .git/hooks/pre-push <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

bash scripts/_pyrun.sh scripts/log_antigravity.py || true
bash scripts/_pyrun.sh scripts/submit_log.py
HOOK

chmod +x .git/hooks/pre-push
chmod +x scripts/_pyrun.sh scripts/log_hook.py scripts/log_manual.py scripts/log_antigravity.py scripts/submit_log.py scripts/setup_hooks.sh

echo "AI logging hooks installed."
echo "Pre-push hook: .git/hooks/pre-push"
echo "Log file: .ai-log/session.jsonl"
