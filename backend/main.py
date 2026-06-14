"""
Student Portal Backend - FastAPI Application
"""
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from routers import cv, jobs, review

load_dotenv()

app = FastAPI(
    title="Student Portal API",
    description="API cho sinh viên upload CV, xem job phù hợp, và nhận AI review",
    version="1.0.0",
)

# CORS cho phép frontend test
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Routers
app.include_router(cv.router, prefix="/api/cv", tags=["CV"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["Jobs"])
app.include_router(review.router, prefix="/api/review", tags=["Review"])


@app.get("/", include_in_schema=False)
async def serve_frontend():
    """Serve test frontend."""
    return FileResponse("static/index.html")


@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Student Portal API is running"}
