"""Shared helpers for building consistent CORS/preflight responses."""
from __future__ import annotations

from typing import Iterable, Sequence

from fastapi import Request, Response, status

from app.config import settings

# Methods explicitly allowed both for the FastAPI router configuration and for
# any handcrafted preflight handlers we expose.  Browsers expect OPTIONS to be
# present in the allow-list even if the actual request will use another verb.
ALLOWED_CORS_METHODS: tuple[str, ...] = (
    "OPTIONS",
    "GET",
    "POST",
    "PATCH",
    "DELETE",
    "HEAD",
)

_DEFAULT_PREFLIGHT_MAX_AGE = 600  # seconds


def _normalise_methods(methods: Iterable[str]) -> list[str]:
    """Return a unique list of HTTP methods in the order they should appear."""

    seen: list[str] = []
    for method in methods:
        if not method:
            continue
        upper = method.upper()
        if upper not in seen:
            seen.append(upper)

    if "OPTIONS" not in seen:
        seen.insert(0, "OPTIONS")

    return seen


def build_preflight_response(
    request: Request,
    methods: Sequence[str] | None = None,
    *,
    status_code: int = status.HTTP_204_NO_CONTENT,
) -> Response:
    """Construct a uniform preflight response with the proper CORS headers."""

    requested_headers = request.headers.get("access-control-request-headers")
    allow_headers = requested_headers or "Authorization, Content-Type"
    origin = request.headers.get("origin") or "*"
    allow_methods = ", ".join(_normalise_methods(methods or ALLOWED_CORS_METHODS))
    max_age = getattr(settings, "CORS_MAX_AGE", _DEFAULT_PREFLIGHT_MAX_AGE)

    headers = {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": allow_methods,
        "Access-Control-Allow-Headers": allow_headers,
        "Access-Control-Max-Age": str(max_age),
    }

    if settings.CORS_ALLOW_CREDENTIALS:
        headers["Access-Control-Allow-Credentials"] = "true"

    if origin != "*":
        vary_headers = ["Origin"]
        if requested_headers:
            vary_headers.append("Access-Control-Request-Headers")
        headers["Vary"] = ", ".join(vary_headers)

    return Response(status_code=status_code, headers=headers)
