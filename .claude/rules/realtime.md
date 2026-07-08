---
description: WebSocket, SSE, messaging, presence, push notification, and live activity rules.
paths:
  - backend/app/modules/messaging/**
  - backend/app/modules/workflow/**
  - frontend/**
  - docs/ARCHITECTURE.md
  - docs/API_CONTRACTS.md
  - docs/BUSINESS_LOGIC.md
---

# Real-time & Messaging Rules

Use for WebSocket, SSE, in-app messaging, presence, push notifications, live activity feeds, and visual workflow execution updates.

## Must Read

- `CLAUDE.md`
- `docs/ARCHITECTURE.md` — WebSocket, Redis fan-out, workflow engine.
- `docs/BUSINESS_LOGIC.md` — messaging permission matrix and workflow rules.
- `docs/API_CONTRACTS.md` — event and streaming contracts.
- `docs/SECURITY_PRIVACY.md`
- `docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md` when alerts, email, push, or notification preferences are involved.
- `docs/SYSTEM_ACCEPTANCE_BAR.md`

## Non-Negotiables

- Student-to-student messaging is never allowed.
- Partner-to-student messaging requires recruitment context or explicitly permitted outreach and service-layer rate limits.
- Message content must be persisted before WebSocket delivery.
- WebSocket auth must re-check user identity and tenant scope.
- Partners never see raw student online status; use coarse activity buckets only when permitted.
- AI streaming uses SSE or an approved stream endpoint; do not leak provider/model/token/latency internals.
- Workflow graphs are DAG-only, versioned, and cannot edit active running versions in place.
- Real-time events must not bypass RBAC just because the HTTP API is protected.
- Real-time UX must support practical recovery: offline state, retry state, stale data state, and user-visible next action.

## Implementation Defaults

- WebSocket namespace: `/ws/`.
- Backend fan-out: Redis Pub/Sub or Streams after persistence.
- Frontend reconnect: exponential backoff with capped retries.
- Push notifications require explicit browser permission and safe payloads.
- Flow builder UI uses a proven library such as React Flow.

## Delivery Checklist

- Connection auth and disconnect behavior covered.
- Permission matrix enforced in backend service layer.
- Cross-tenant event delivery tests added.
- Offline/reconnect/read-receipt behavior defined.
- Rate limit and anti-spam cases covered.
- No sensitive payloads in push notifications or logs.
