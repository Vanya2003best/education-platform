import asyncio
import json
import os
import sys
from pathlib import Path
import types

from fastapi.exceptions import RequestValidationError
from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/tests")

cv2_stub = types.ModuleType("cv2")
cv2_stub.imread = lambda *args, **kwargs: None
cv2_stub.cvtColor = lambda image, code: image
cv2_stub.COLOR_BGR2GRAY = 0
cv2_stub.fastNlMeansDenoising = lambda *args, **kwargs: None
cv2_stub.adaptiveThreshold = lambda *args, **kwargs: None
cv2_stub.ADAPTIVE_THRESH_GAUSSIAN_C = 0
cv2_stub.THRESH_BINARY = 0
cv2_stub.morphologyEx = lambda *args, **kwargs: None
cv2_stub.MORPH_CLOSE = 0
cv2_stub.minAreaRect = lambda coords: ((0, 0), (0, 0), 0)
cv2_stub.getRotationMatrix2D = lambda *args, **kwargs: None
cv2_stub.warpAffine = lambda *args, **kwargs: None
cv2_stub.INTER_CUBIC = 0
cv2_stub.BORDER_REPLICATE = 0
sys.modules.setdefault("cv2", cv2_stub)

from app.main import validation_exception_handler, _stringify_exceptions


def test_validation_handler_serializes_exception_in_context():
    async def receive():  # pragma: no cover - required by Request signature
        return {"type": "http.request"}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/register",
            "app": None,
            "headers": [],
        },
        receive,
    )

    error_message = "Password must contain at least one uppercase letter"
    exc = RequestValidationError(
        [
            {
                "loc": ("body", "password"),
                "msg": f"Value error, {error_message}",
                "type": "value_error",
                "ctx": {"error": ValueError(error_message)},
            }
        ],
        body={"password": "123456789"},
    )

    async def invoke_handler():
        response = await validation_exception_handler(request, exc)
        return json.loads(response.body)

    payload = asyncio.run(invoke_handler())

    assert payload["error"]["details"][0]["ctx"]["error"] == error_message
    assert payload["error"]["body"] is None


def test_stringify_exceptions_handles_nested_structures():
    nested = {
        "outer": ValueError("outer"),
        "inner": {
            "list": [ValueError("list"), {"tuple": (ValueError("tuple"),)}],
            "set": {ValueError("set")},
        },
    }

    transformed = _stringify_exceptions(nested)

    assert transformed["outer"] == "outer"
    assert transformed["inner"]["list"][0] == "list"
    assert transformed["inner"]["list"][1]["tuple"][0] == "tuple"
    assert transformed["inner"]["set"] == ["set"]