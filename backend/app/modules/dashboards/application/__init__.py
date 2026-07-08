"""Persona dashboard read-model services.

Read strategy (``docs/SYSTEM_ACCEPTANCE_BAR.md`` §4 — read models need a refresh
strategy, staleness expectation, and failure behavior):

- **Refresh / staleness:** every widget is computed by a *live* read against the
  owning module's application-layer facade at request time. There is no cached
  projection; staleness is therefore zero (always live). This is acceptable for
  V1 volume — each widget is a single small, indexed, scoped query, never a heavy
  multi-domain join. A materialized projection (event-fed read model) is a future
  optimization recorded for when per-persona traffic or fan-out grows.
- **Composition boundary:** these services call only other modules' *application*
  facades / scoped read helpers — never their ORM — so the dashboards module
  stays a pure consumer and cannot drift from the source modules' visibility and
  RBAC rules.
- **Failure behavior:** the persona RBAC gate runs first and is *not* swallowed
  (a wrong persona still returns 401/403/404). Each individual widget is then
  computed inside :func:`_common.safe`: a failing sub-query degrades that one
  widget to a null/empty fallback and rolls back the read transaction so the
  remaining widgets still load — a single failing widget never 500s the whole
  dashboard.
- **Writes / audit:** none. Dashboards are reads, so (consistent with other read
  endpoints) they create no audit rows.
"""
