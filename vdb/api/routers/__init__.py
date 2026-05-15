from fastapi import APIRouter
from vdb.api.routers.vdb import router as vdb_router

router = APIRouter()
router.include_router(vdb_router, prefix="/vdb", tags=["vdb"])
