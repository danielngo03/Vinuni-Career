"""
app/bootstrap — Application composition layer.

Responsibilities:
  - Create the FastAPI application (app.py)
  - Register all routers (routes.py)
  - App startup/shutdown lifecycle (lifespan.py)
  - Middleware configuration (middleware.py)

Nothing from the business domain or AI layer should import from bootstrap.
Bootstrap depends on everything; nothing depends on bootstrap.
"""
from __future__ import annotations

from app.bootstrap.app import create_app

__all__ = ["create_app"]
