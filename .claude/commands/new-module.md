---
description: Plan or scaffold a new greenfield backend module using VinUni conventions
argument-hint: <domain-name>
allowed-tools: Read, Edit, MultiEdit, Write, Bash, Glob, Grep, TodoWrite
---

# VinUni New Module

Module name:

`$ARGUMENTS`

Use `.claude/skills/vinuni-feature/SKILL.md` plus `.claude/rules/backend.md`.

Before writing files:

- Verify ownership in `docs/PRODUCT_REQUIREMENTS.md`, `docs/ARCHITECTURE.md`, and `docs/DATA_MODEL.md`.
- Confirm API/error/auth shape in `docs/API_CONTRACTS.md`.
- Confirm RBAC/audit/privacy in `docs/SECURITY_PRIVACY.md`.
- Create or update tests according to `docs/TEST_STRATEGY.md`.
