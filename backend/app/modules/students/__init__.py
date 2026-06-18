"""
Students module — onboarding, academic profile, CV, privacy.

Four-layer layout:
  api/            Routers, dependencies, response schemas
  application/    Commands, queries, use cases
  domain/         StudentProfile entity, AcademicRecord, privacy policies
  infrastructure/ SQLAlchemy repositories
"""
from __future__ import annotations
