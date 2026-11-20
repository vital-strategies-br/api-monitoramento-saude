import math
from collections import deque
from collections.abc import Mapping
from typing import Any

from app.core import messages

# FastAPI prefixes body errors with this location; it is not a field name.
_BODY_LOC = "body"
# Error types whose location is a byte position, not a field.
_POSITIONAL_ERRORS = {"json_invalid"}
_MISSING = "missing"


def error_field(error: Mapping[str, Any]) -> str | None:
    """Dotted field path of a Pydantic/FastAPI error, or None for whole-body errors."""
    if error["type"] in _POSITIONAL_ERRORS:
        return None
    path = [str(part) for part in error["loc"] if part != _BODY_LOC]
    return ".".join(path) or (error.get("ctx") or {}).get("campo") or None


def error_message(error: Mapping[str, Any]) -> str:
    # JS sends null for null, NaN and undefined array items: name it instead of
    # reporting the type the field expected.
    if error["type"] != _MISSING and "input" in error and error["input"] is None:
        return messages.NULL_VALUE
    if error["type"] in messages.OWN_ERROR_TYPES:
        return str(error["msg"])
    return messages.VALIDATION_ERRORS.get(error["type"], messages.INVALID_VALUE)


def format_error(error: Mapping[str, Any]) -> str:
    field = error_field(error)
    if field is None and error["type"] == _MISSING:
        return messages.BODY_MISSING
    message = error_message(error)
    return f"{field}: {message}" if field else message


def is_storable_text(text: str) -> bool:
    """False for text PostgreSQL or UTF-8 output cannot carry: NUL or lone surrogates."""
    if "\x00" in text:
        return False
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def find_unstorable_value(value: Any) -> tuple[str, str] | None:
    """(dotted path, message) of the first value PostgreSQL JSONB cannot store, else None.

    Catches what a JSON parser lets through but storage rejects: NUL or lone
    surrogates in keys and strings, and NaN / Infinity (also from overflowing
    literals such as 1e400). "" as path means a key of the top-level object.
    Iterative, so deeply nested JSON cannot exhaust the call stack. Returned
    paths only contain storable keys, so they are safe to echo and log.
    """
    queue: deque[tuple[str, Any]] = deque([("", value)])
    while queue:
        path, current = queue.popleft()
        if isinstance(current, str):
            if not is_storable_text(current):
                return path, messages.INVALID_TEXT
        elif isinstance(current, float):
            if not math.isfinite(current):
                return path, messages.INVALID_NUMBER
        elif isinstance(current, dict):
            for key, child in current.items():
                if not is_storable_text(key):
                    return path, messages.INVALID_TEXT
                queue.append((f"{path}.{key}" if path else key, child))
        elif isinstance(current, list):
            queue.extend((f"{path}.{i}" if path else str(i), child) for i, child in enumerate(current))
    return None
