from fastapi import APIRouter

from api.v1 import (
    admin_retention,
    admin_siem,
    admin_tenants,
    audit,
    compliance,
    operations,
    review,
    scan,
    waivers,
)

v1_router = APIRouter()

v1_router.include_router(scan.router)
v1_router.include_router(audit.router)
v1_router.include_router(review.router)
v1_router.include_router(operations.router)
v1_router.include_router(waivers.router)
v1_router.include_router(admin_tenants.router)
v1_router.include_router(admin_siem.router)
v1_router.include_router(admin_retention.router)
v1_router.include_router(compliance.router)
