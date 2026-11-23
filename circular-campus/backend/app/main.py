"""FastAPI application entry point.

Run:  uvicorn app.main:app --reload   (from the backend folder)
If frontend/dist exists (after `npm run build`), the built interface is served
from the same address, so one command runs the whole prototype.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .config import settings
from .database import SessionLocal, init_db
from .errors import AppError


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    from .seed import seed_if_empty

    with SessionLocal() as db:
        seed_if_empty(db)
    yield


app = FastAPI(title="Circular Campus API", version="0.6.0", lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json")
app.include_router(router)


@app.exception_handler(AppError)
async def app_error(_: Request, exc: AppError):
    body = {"detail": exc.message}
    if exc.field:
        body["fields"] = {exc.field: exc.message}
    return JSONResponse(status_code=exc.status_code, content=body)


FIELD_MESSAGES = {
    "missing": "This field is required.",
    "string_too_short": "This field is too short.",
    "greater_than_equal": "Enter a value that is not negative.",
}


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    fields: dict[str, str] = {}
    general: list[str] = []
    for err in exc.errors():
        loc = [str(x) for x in err.get("loc", []) if x not in ("body", "query", "path")]
        msg = err.get("msg", "Invalid value.").removeprefix("Value error, ")
        if err.get("type") == "missing":
            msg = FIELD_MESSAGES["missing"]
        elif err.get("type") == "greater_than_equal" and err.get("ctx", {}).get("ge") == 1:
            msg = "Enter at least 1."
        if loc:
            fields.setdefault(loc[0], msg)
        else:
            general.append(msg)
    detail = general[0] if general else "Please correct the highlighted fields."
    return JSONResponse(status_code=422, content={"detail": detail, "fields": fields})


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if request.url.path.startswith("/api"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


# ---- serve the built React app (single-page app fallback) -------------------
dist = settings.frontend_dist
if (dist / "index.html").exists():
    if (dist / "static").exists():
        app.mount("/static", StaticFiles(directory=dist / "static"), name="static-files")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith("api"):
            return JSONResponse(status_code=404, content={"detail": "Not found."})
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")
