from collections.abc import Mapping
from typing import Any

from app.core.messages import VALIDATION_ERRORS

# FastAPI prefixes body errors with this location; it is not a field name.
_BODY_LOC = "body"
# Error types whose location is a byte position, not a field.
_POSITIONAL_ERRORS = {"json_invalid"}


def error_field(error: Mapping[str, Any]) -> str | None:
    """Dotted field path of a Pydantic/FastAPI error, or None for whole-body errors."""
    if error["type"] in _POSITIONAL_ERRORS:
        return None
    path = [str(part) for part in error["loc"] if part != _BODY_LOC]
    return ".".join(path) or error.get("ctx", {}).get("campo")


def error_message(error: Mapping[str, Any]) -> str:
    return VALIDATION_ERRORS.get(error["type"], error["msg"])


def format_error(error: Mapping[str, Any]) -> str:
    field = error_field(error)
    message = error_message(error)
    return f"{field}: {message}" if field else message
