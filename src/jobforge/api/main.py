from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from jobforge.api.routes import (
    applications,
    apply_assist,
    company,
    dashboard,
    jobs,
    preferences,
    profile,
    skills,
    tailor,
    telegram,
)
from jobforge.logging_setup import (
    get_logger,
    new_request_id,
    set_request_id,
    setup_logging,
)

setup_logging()
log = get_logger("jobforge.api")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        rid = request.headers.get("x-request-id") or new_request_id()
        set_request_id(rid)
        log.info("http.request", extra={"method": request.method, "path": request.url.path})
        try:
            response = await call_next(request)
        except Exception:
            log.exception("http.unhandled")
            raise
        response.headers["X-Request-ID"] = rid
        log.info(
            "http.response",
            extra={"status_code": response.status_code, "path": request.url.path},
        )
        return response


app = FastAPI(title="JobForge API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(RequestIdMiddleware)
app.include_router(profile.router, prefix="/profile", tags=["profile"])
app.include_router(tailor.router, prefix="/tailor", tags=["tailor"])
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
app.include_router(preferences.router, prefix="/preferences", tags=["preferences"])
app.include_router(applications.router, prefix="/applications", tags=["applications"])
app.include_router(apply_assist.router, prefix="/applications", tags=["apply-assist"])
app.include_router(company.router, prefix="/companies", tags=["companies"])
app.include_router(skills.router, prefix="/skills", tags=["skills"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(telegram.router, prefix="/telegram", tags=["telegram"])


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
