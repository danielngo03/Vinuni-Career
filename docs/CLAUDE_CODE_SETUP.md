# Claude Code Setup — VinUni Career Platform

> Phiên bản: 1.0 | Cập nhật: 26/06/2026  
> Purpose: verified setup steps for Claude Code memory, agents, skills, hooks, plugins, and MCP.

## 0. Official Claude Code Alignment

This project follows the official Claude Code operating model:

- Keep root `CLAUDE.md` concise and canonical; move long procedures into
  `.claude/rules/`, `.claude/skills/`, and `docs/`.
- Use `.claude/rules/` for modular/path-scoped guidance that should appear only
  when relevant.
- Use skills for repeatable workflows such as feature delivery, docs audit,
  AI product planning, UI polish, security review, test gates, and status update.
- Keep subagents focused, give them strong `description` fields, and limit tools
  according to role. Domain agents review/spec only; implementation agents can
  edit/write/test.
- Treat hooks as deterministic guardrails for sensitive files and workflow
  logging, not as the main product brain.
- Use plugins/MCP as accelerators, then validate through VinUni docs, agents,
  browser evidence, tests, and `docs/SYSTEM_ACCEPTANCE_BAR.md`.

## 1. Memory

- Canonical project memory: `CLAUDE.md`.
- `.claude/CLAUDE.md` is intentionally not used to avoid duplicate instructions.
- Detailed build-speed rules live in `docs/CLAUDE_BUILD_OPTIMIZATION.md`.
- Verify in Claude Code with `/memory`.

Expected:

- `CLAUDE.md` is loaded.
- Source-of-truth docs point to `docs/...`.
- Greenfield directive is visible.

## 2. Agents, Rules, Skills

Verify:

- `/agents` shows 10 project agents from `.claude/agents/`.
- Rule overlays load from `.claude/rules/` when relevant.
- Project skills exist in `.claude/skills/`:
  - `vinuni-feature`
  - `vinuni-docs-audit`
  - `vinuni-ai-product`
  - `vinuni-security-review`
  - `vinuni-test-gate`
  - `vinuni-ui-polish`
  - `vinuni-status`

Performance note:

- For latency-sensitive implementation, prefer main-conversation work and use
  subagents as reviewers only when their lens is independent.
- For long sessions, ask Claude to maintain `.claude/run-state.md` so it does
  not reread long docs unnecessarily.
- Use `/build-burst` for faster batch implementation, then run a verification
  checkpoint before claiming completion.
- Use `/overnight-burst-loop` when you want repeated burst/checkpoint cycles
  through the night.

## 3. Hooks

Verify with `/hooks`.

Expected project hooks:

- `PreToolUse`: `.claude/hooks/guard-sensitive.py`
- `UserPromptSubmit`, `PostToolUse`, `Stop`: `.claude/hooks/log-hook.py`

There should be no hook command pointing to legacy `scripts/`.

## 4. Plugin Marketplaces

Use the Claude Code CLI from `PATH` when available. This repo also includes a wrapper:

```bash
.claude/bin/claude-code --version
```

The wrapper prefers `claude` from `PATH`, then falls back to the Antigravity extension binary glob at `~/.antigravity-ide/extensions/anthropic.claude-code-*/resources/native-binary/claude`. The exact path is machine-specific — use the wrapper instead of hardcoding it.

Recommended setup:

```bash
claude plugin marketplace add anthropics/claude-plugins-official
claude plugin marketplace update claude-plugins-official
claude plugin marketplace add anthropics/claude-plugins-community
claude plugin marketplace update claude-community
```

Note: the community marketplace registers as `claude-community`.

## 5. Plugin Tiers

Always-on core:

- `frontend-design`
- `feature-dev`
- `code-review`
- `security-guidance`
- `pr-review-toolkit`
- `commit-commands`
- `pyright-lsp`
- `typescript-lsp`
- `context7`
- `playwright`
- `chrome-devtools-mcp`
- `code-simplifier`
- `claude-md-management`

Important plugin expectation:

- `frontend-design` is a design-assistance plugin, not a guarantee that every UI
  will be product-correct or beautiful by itself.
- For VinUni, `frontend-design` must be invoked **before** major UI code changes
  and must follow `docs/FRONTEND_DESIGN_PLUGIN_USAGE.md`: subject/audience/job,
  screenshot diagnosis, compact color/type/layout system, signature element,
  motion plan, self-critique, `globals.css` light/dark/system theme audit, and
  post-build screenshot critique.
- Some plugins expose slash commands/skills/hooks rather than MCP servers, so
  they may not appear in `/mcp`. Verify them with `/plugin list` and
  `claude plugin details`, not only the MCP screen.
- For VinUni, plugin suggestions are advisory. The mandatory gate is:
  `docs/DESIGN.md` + `docs/UI_QUALITY_BAR.md` + `docs/SCREEN_SPECS.md` +
  browser/Playwright screenshots + persona workflow review.
- If plugin output creates generic SaaS pages, decorative cards, fake metrics,
  or one-size-fits-all dashboards, reject it and re-route through
  `vinuni-ui-polish`, `product-owner-system-planner`, the relevant domain agent,
  and `tester-qa`.

Enable when relevant:

- `redis-development`
- `plugin-dev`
- `agent-sdk-dev`
- `hookify`
- `github` after `claude mcp login` or valid auth.
- `aikido` after Aikido setup/auth.

Utility skills currently enabled:

- `superpowers`
- `skill-creator`

Task-only or disabled by default:

- `ralph-wiggum`
- `ralph-loop`
- `learning-output-style`
- `explanatory-output-style`
- `desktop-commander`

## 6. External Plugin Audit

External/community plugins are allowed only when they are genuinely useful and pass this audit:

- Source repo is clear and trusted enough for the task.
- Manifest validates with `claude plugin validate`.
- `claude plugin details <plugin>` shows acceptable token cost and component inventory.
- Hooks do not auto-run destructive shell commands.
- MCP servers do not request broad filesystem/network access without need.
- Secrets are not required until the actual integration is used.
- Plugin can be disabled cleanly after the task.

Strong candidates when needed:

- Figma/design plugin if real Figma files exist.
- Sentry plugin when production error monitoring exists.
- Linear/Jira plugin when backlog lives there.
- Postgres MCP/plugin after Phase 0 has a real database.
- Vercel plugin if deployment uses Vercel.

## 7. Environment And AI Test Keys

- Environment variable names live in `docs/ENVIRONMENT.md`.
- Real keys live only in local `.env` files.
- Do not write real keys into docs, code, tests, prompts, fixtures, or tracked config.
- For AI smoke tests, prefer OpenRouter/DeepSeek-compatible low-cost or free aliases.
- Unit tests and CI should use offline/fake providers by default.

## 8. Verification Commands

```bash
.claude/bin/claude-code plugin marketplace list
.claude/bin/claude-code plugin list
.claude/bin/claude-code plugin details playwright@claude-plugins-official
.claude/bin/claude-code mcp list
```

Inside Claude Code:

```text
/memory
/agents
/hooks
/plugin list
/plugin marketplace list
/doctor
```
