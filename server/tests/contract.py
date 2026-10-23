"""Validation against the contract: contracts/schemas (JSON Schema 2020-12) and OpenAPI components.

Used by API tests: every response shape and signed object is checked against contracts/ itself.
"""

import json
import re
import uuid
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
OPENAPI = "urn:almi:openapi-product-api-v1"
_RFC3339 = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|[+-]\d\d:\d\d)")

# date-time and uuid without extra packages (jsonschema checks them only with optional extras).
FORMATS = FormatChecker([])


@FORMATS.checks("date-time", raises=ValueError)
def _date_time(value: object) -> bool:
    if not isinstance(value, str):
        return True
    if not _RFC3339.fullmatch(value):
        raise ValueError("not RFC 3339")
    datetime.fromisoformat(value)
    return True


@FORMATS.checks("uuid", raises=ValueError)
def _uuid(value: object) -> bool:
    if isinstance(value, str):
        uuid.UUID(value)
    return True


@cache
def _registry() -> Registry:
    resources = []
    for path in sorted((CONTRACTS / "schemas").glob("*.schema.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        resources.append((document["$id"], Resource.from_contents(document, DRAFT202012)))
    openapi = yaml.safe_load((CONTRACTS / "openapi-product-api-v1.yaml").read_text("utf-8"))
    resources.append((OPENAPI, Resource.from_contents(openapi, DRAFT202012)))
    return Registry().with_resources(resources)


def _errors(schema: dict[str, Any], instance: Any) -> list[str]:
    validator = Draft202012Validator(schema, registry=_registry(), format_checker=FORMATS)
    return [f"{list(e.absolute_path)}: {e.message}" for e in validator.iter_errors(instance)]


def openapi_errors(component: str, instance: Any) -> list[str]:
    """Errors of instance against components/schemas/<component> of the Product API."""
    return _errors({"$ref": f"{OPENAPI}#/components/schemas/{component}"}, instance)


def schema_errors(name: str, instance: Any) -> list[str]:
    """Errors of instance against contracts/schemas/<name>.schema.json."""
    return _errors({"$ref": f"https://license.alter-os.ru/schemas/v1/{name}.schema.json"}, instance)
