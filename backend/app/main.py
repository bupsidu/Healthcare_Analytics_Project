from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from app.api.auth import router as auth_router
from app.api.climate import router as climate_router
from app.api.health import router as health_router
from app.api.intakes import router as intakes_router
from app.api.ml_data import router as ml_data_router
from app.api.predictions import router as predictions_router
from app.core.config import BASE_DIR, settings
from app.db.session import Base, engine
from app.services.ml_service import PredictionService

import app.models.user
import app.models.establishment
import app.models.intake
import app.models.ml_data


@asynccontextmanager
async def lifespan(application: FastAPI):
    Base.metadata.create_all(bind=engine)
    await run_in_threadpool(application.state.prediction_service.load)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API REST para el Sistema Hospitalario de Alerta Temprana",
    version="0.1.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

artifacts_dir = settings.ML_ARTIFACTS_DIR
if not artifacts_dir.is_absolute():
    artifacts_dir = BASE_DIR / artifacts_dir
app.state.prediction_service = PredictionService(artifacts_dir.resolve())

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.FRONTEND_ORIGINS.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=settings.API_V1_STR)
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(intakes_router, prefix=settings.API_V1_STR)
app.include_router(climate_router, prefix=settings.API_V1_STR)
app.include_router(predictions_router, prefix=settings.API_V1_STR)
app.include_router(ml_data_router, prefix=settings.API_V1_STR)


@app.get("/")
def read_root():
    return {
        "status": "online",
        "system": settings.PROJECT_NAME,
        "version": "0.1.0",
        "docs": "/docs",
    }
