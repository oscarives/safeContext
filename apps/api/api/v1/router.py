from fastapi import APIRouter

from api.v1 import audit, review, scan

v1_router = APIRouter()

v1_router.include_router(scan.router)
v1_router.include_router(audit.router)
v1_router.include_router(review.router)
