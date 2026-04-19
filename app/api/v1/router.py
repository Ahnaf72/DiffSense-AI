"""Aggregated v1 API router — single import for main.py."""

from fastapi import APIRouter

from app.api.v1 import auth, documents, health, jobs, references, reports, users

router = APIRouter(prefix="/api/v1")

router.include_router(health.router)
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(documents.router)
router.include_router(references.router)
router.include_router(reports.router)
router.include_router(jobs.router)
