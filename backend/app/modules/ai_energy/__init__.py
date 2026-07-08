"""AI energy administration module — the WRITE path for the energy meter.

The persona-agnostic energy METER (read-only allowance resolution + the hard
gate) lives in the shared ``app.ai.energy`` infra layer. This module is the
partner/university-facing WRITE surface layered on top of it: org overview,
department/member sub-allocation, goodwill wallet grants, and manual/bank-transfer
top-up purchases.

Dependency direction (module boundary): ``app.modules.ai_energy`` imports the
shared ``app.ai.energy`` infra (models + meter), never the reverse. Relocating
the write path here removed an inverted dependency — the shared ``app.ai`` layer
must not import ``app.modules`` (auth / organization), which the write path does.
"""
