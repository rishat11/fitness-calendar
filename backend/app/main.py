import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import router as auth_router
from app.api.blocks import router as blocks_router
from app.api.deps import DbSession
from app.api.exercises import router as exercises_router
from app.api.log import router as log_router
from app.api.plan import router as plan_router
from app.api.profile import router as profile_router
from app.api.progression import router as progression_router
from app.api.today import router as today_router
from app.api.transfer import router as transfer_router
from app.api.volume import router as volume_router
from app.api.workouts import router as workouts_router
from app.services.rate_limit import limiter

logger = logging.getLogger(__name__)

app = FastAPI(title="Фитнес-календарь")
app.state.limiter = limiter
app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(exercises_router)
app.include_router(workouts_router)
app.include_router(plan_router)
app.include_router(log_router)
app.include_router(progression_router)
app.include_router(today_router)
app.include_router(transfer_router)
app.include_router(volume_router)
app.include_router(blocks_router)


@app.get("/health")
async def health(db: DbSession) -> JSONResponse:
    try:
        await db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.warning("database health check failed")
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ok"})
