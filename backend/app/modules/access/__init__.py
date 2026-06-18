"""
Access module — accounts, credentials, sessions, OIDC, RBAC.

Four-layer layout:
  api/          Routers, FastAPI dependencies, request/response schemas
  application/  Commands, queries, use cases
  domain/       Entities, value objects, policies
  infrastructure/  SQLAlchemy repositories, session adapters
"""
from __future__ import annotations
