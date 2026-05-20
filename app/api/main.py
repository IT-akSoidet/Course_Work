from fastapi import FastAPI

from app.api.routers import health
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(title="Room Booking Service")
app.include_router(health.router)
