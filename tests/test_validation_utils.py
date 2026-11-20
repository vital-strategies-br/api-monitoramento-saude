import pytest

from app.core import messages
from app.utils.validation import find_unstorable_value, is_storable_text


@pytest.mark.parametrize("text, ok", [
    ("", True), ("ação 😀", True), ("a\x00b", False), ("\ud800", False),
])
def test_is_storable_text(text, ok):
    assert is_storable_text(text) is ok


@pytest.mark.parametrize("value, expected", [
    ({"a": "ok", "b": [1, 2.5, None, True, {"c": "ok"}]}, None),
    ({"a": {"b": ["ok", "x\x00"]}}, ("a.b.1", messages.INVALID_TEXT)),
    ({"bad\ud800key": 1}, ("", messages.INVALID_TEXT)),
    ({"a": {"bad\x00key": 1}}, ("a", messages.INVALID_TEXT)),
    ({"a": [1, float("nan")]}, ("a.1", messages.INVALID_NUMBER)),
    ({"a": float("-inf")}, ("a", messages.INVALID_NUMBER)),
])
def test_find_unstorable_value_returns_safe_path(value, expected):
    assert find_unstorable_value(value) == expected


def test_find_unstorable_value_handles_deep_nesting_without_recursion():
    deep: object = "x\x00"
    for _ in range(100_000):
        deep = [deep]
    assert find_unstorable_value({"a": deep}) == ("a" + ".0" * 100_000, messages.INVALID_TEXT)
