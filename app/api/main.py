from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.routers import admin, bookings, health
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(title="Room Booking Service")
register_exception_handlers(app)
app.include_router(health.router)
app.include_router(bookings.router)
app.include_router(admin.router)
