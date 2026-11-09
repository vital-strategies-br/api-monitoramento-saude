from typing import Any


def json_examples(**examples: tuple[str, Any]) -> dict[str, Any]:
    """Build an OpenAPI `application/json` content block with named examples."""
    return {
        "application/json": {
            "examples": {
                name: {"summary": summary, "value": value}
                for name, (summary, value) in examples.items()
            },
        },
    }
