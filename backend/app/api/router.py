from fastapi import APIRouter

from app.api.v1 import webhook
from app.api.v1.routers import ai, auth, cvs, files, health, jobs, orgs, search, students

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(orgs.router, prefix="/orgs", tags=["organizations"])
api_router.include_router(students.router, prefix="/students", tags=["students"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(cvs.router, prefix="/cvs", tags=["cvs"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(webhook.router, prefix="/webhooks", tags=["webhooks"])
