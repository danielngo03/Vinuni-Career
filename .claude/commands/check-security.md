---
description: Run a VinUni security, privacy, RBAC, AI-safety, and sponsored-content review
argument-hint: <module, feature, or current changes>
allowed-tools: Read, Bash, Glob, Grep
---

# VinUni Security Review

Scope:

`$ARGUMENTS`

Use `.claude/skills/vinuni-security-review/SKILL.md` as the primary review workflow.

Report findings by severity first. Cover RBAC, tenant isolation, audit, PII, AI provider leakage, mutating AI confirmation, file access, messaging boundaries, advertising labels, injection/XSS/SSRF, and required regression tests.
