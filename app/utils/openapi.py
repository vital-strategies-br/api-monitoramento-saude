from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute

_JSON = "application/json"


def json_examples(**examples: tuple[str, Any]) -> dict[str, Any]:
    """Build an OpenAPI `application/json` content block with named examples."""
    return {
        _JSON: {
            "examples": {
                name: {"summary": summary, "value": value}
                for name, (summary, value) in examples.items()
            },
        },
    }


def keep_nulls_in_examples(app: FastAPI) -> None:
    """Show response examples exactly as written, `null` values included.

    FastAPI drops every None while building the OpenAPI document, so an example
    such as {"evento_id": null, ...} would appear without the key, unlike the
    real response. This copies the documented example values back afterwards.
    """
    generate = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = generate()
        for route in app.routes:
            if isinstance(route, APIRoute):
                _restore_examples(schema, route)
        return schema

    app.openapi = openapi  # type: ignore[method-assign]


def _restore_examples(schema: dict[str, Any], route: APIRoute) -> None:
    for status, doc in route.responses.items():
        examples = doc.get("content", {}).get(_JSON, {}).get("examples", {})
        if not examples:
            continue
        for method in route.methods:
            operation = schema["paths"][route.path_format][method.lower()]
            target = operation["responses"][str(status)]["content"][_JSON]["examples"]
            for name, example in examples.items():
                target[name]["value"] = example["value"]
