from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes.auth import router as auth_router
from backend.api.routes.health import router as health_router
from backend.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="ReconAI — GST Reconciliation & Evidence Intelligence Platform",
    description="Deterministic GST reconciliation and audit workflow for CA firms.",
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
origins = settings.cors_origins
if isinstance(origins, str):
    origins = [o.strip() for o in origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# RFC 7807 Exception Handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "type": "https://recon.ai/errors/validation-error",
            "title": "Validation Error",
            "status": 422,
            "detail": exc.errors(),
            "instance": request.url.path,
        },
    )


# API v1 Router Registration
app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")

# Convenience root health check
app.include_router(health_router, prefix="")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
