"""HTTP exception handlers so client errors share the QueryResponse shape."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.api.models import QueryResponse


def _format_validation_errors(exc: RequestValidationError) -> list[str]:
    messages: list[str] = []
    for err in exc.errors():
        loc_parts = [str(part) for part in err.get("loc", []) if part != "body"]
        location = ".".join(loc_parts)
        msg = err.get("msg") or "Invalid request."
        messages.append(f"{location}: {msg}" if location else msg)
    return messages or ["Invalid request."]


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = _format_validation_errors(exc)
        payload = QueryResponse(
            status="error",
            final_answer="Request could not be processed: " + " ".join(errors),
            plan=None,
            tool_results=[],
            errors=errors,
        )
        return JSONResponse(status_code=400, content=payload.model_dump())
