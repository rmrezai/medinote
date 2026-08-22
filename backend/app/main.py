from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.routes import router
from app.api.clinical_routes import router as clinical_router
from app.api.analysis_routes import router as analysis_router
from app.api.overview_routes import router as overview_router
from app.api.progress_routes import router as progress_router
from app.api.audit_routes import router as audit_router
from app.api.hp_routes import router as hp_router
from app.api.discharge_routes import router as discharge_router
from app.api.med_rec_routes import router as med_rec_router
from app.api.signout_routes import router as signout_router
from app.api.auth_routes import router as auth_router
from app.api.validation_routes import router as validation_router
from app.api.contradiction_routes import router as contradiction_router
from app.api.recovery_routes import router as recovery_router
from app.api.forensic_routes import router as forensic_router
from app.api.retention_routes import router as retention_router
from app.core.security_middleware import security_middleware
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.services.validation_seed import seed_validation_cases
import app.models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_validation_cases(db)
    yield


_docs_url = "/docs" if settings.enable_api_docs else None
_redoc_url = "/redoc" if settings.enable_api_docs else None
_openapi_url = "/openapi.json" if settings.enable_api_docs else None
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
)
app.middleware("http")(security_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)
app.include_router(auth_router)
app.include_router(router)
app.include_router(clinical_router)
app.include_router(analysis_router)
app.include_router(overview_router)
app.include_router(progress_router)
app.include_router(audit_router)
app.include_router(hp_router)
app.include_router(discharge_router)
app.include_router(med_rec_router)
app.include_router(signout_router)
app.include_router(validation_router)
app.include_router(contradiction_router)
app.include_router(recovery_router)
app.include_router(forensic_router)
app.include_router(retention_router)

# Serve the dependency-light physician UI from the same origin as the API.
# This gives cloud deployments one shareable HTTPS URL and keeps API calls same-origin.
_frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
