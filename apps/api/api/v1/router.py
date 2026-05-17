from fastapi import APIRouter

from api.v1 import scan

v1_router = APIRouter()

v1_router.include_router(scan.router)
