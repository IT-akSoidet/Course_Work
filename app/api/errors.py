from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.booking_service import BookingConflictError, BookingValidationError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BookingValidationError)
    async def booking_validation_handler(_: Request, exc: BookingValidationError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(BookingConflictError)
    async def booking_conflict_handler(_: Request, exc: BookingConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"detail": "Внутренняя ошибка сервиса", "error_type": exc.__class__.__name__},
        )
