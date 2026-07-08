$ErrorActionPreference = "Stop"

$root = git rev-parse --show-toplevel 2>$null
if (-not $root) { $root = (Get-Location).Path }
Set-Location $root

New-Item -ItemType Directory -Force -Path ".ai-log/archive" | Out-Null
New-Item -ItemType Directory -Force -Path ".git/hooks" | Out-Null
if (-not (Test-Path ".ai-log/.gitkeep")) {
  New-Item -ItemType File -Path ".ai-log/.gitkeep" | Out-Null
}

$hook = @'
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

bash scripts/_pyrun.sh scripts/log_antigravity.py || true
bash scripts/_pyrun.sh scripts/submit_log.py
'@

Set-Content -Path ".git/hooks/pre-push" -Value $hook -Encoding UTF8
Write-Host "AI logging hooks installed."
Write-Host "Pre-push hook: .git/hooks/pre-push"
Write-Host "Log file: .ai-log/session.jsonl"
