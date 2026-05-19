from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.errors import register_exception_handlers
from app.api.routers import admin, bookings, health, webapp
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(title="Сервис бронирования аудиторий ВШЭ")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(health.router)
app.include_router(bookings.router)
app.include_router(admin.router)
app.include_router(webapp.router)

_FRONTEND_BUILD = Path(__file__).parent.parent.parent / "frontend_build"
if _FRONTEND_BUILD.exists():
    app.mount("/static", StaticFiles(directory=_FRONTEND_BUILD / "static"), name="static-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        index = _FRONTEND_BUILD / "index.html"
        return FileResponse(index)
