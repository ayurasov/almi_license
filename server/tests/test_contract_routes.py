"""Routes of the implementation against contracts/openapi-product-api-v1.yaml (make contract-check).

Every operation of stage 1 is served, with its HTTP method for class-based views; every public
route under the contract prefixes is described in the contract. Operations marked "(этап 2)" in
their summary are not implemented yet and must not be served.
"""

import re
from typing import Any

import yaml
from django.urls import URLPattern, URLResolver, get_resolver

from tests.contract import CONTRACTS

METHODS = ("get", "post", "put", "patch", "delete")
PUBLIC = (
    "/.well-known/",
    "/api/v1/",
    "/api/sync/",
    "/api/integration/",
    "/apps/",
    "/api/activate/",
)


def contract_operations() -> dict[str, dict[str, Any]]:
    document = yaml.safe_load((CONTRACTS / "openapi-product-api-v1.yaml").read_text("utf-8"))
    return {
        _shape(path): {m: op for m, op in item.items() if m in METHODS}
        for path, item in document["paths"].items()
    }


def _shape(path: str) -> str:
    """Parameter names differ between the contract and the code: only their places matter."""
    return re.sub(r"\{[^}]+\}", "{}", path)


def served_routes() -> dict[str, Any]:
    routes: dict[str, Any] = {}

    def walk(patterns: list[Any], prefix: str) -> None:
        for pattern in patterns:
            route = prefix + str(pattern.pattern)
            if isinstance(pattern, URLResolver):
                walk(pattern.url_patterns, route)
            elif isinstance(pattern, URLPattern):
                routes[_shape("/" + re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", route))] = pattern.callback

    walk(get_resolver().url_patterns, "")
    return routes


def stage(operation: dict[str, Any]) -> int:
    return 2 if "(этап 2)" in operation.get("summary", "") else 1


def test_every_stage1_operation_is_served_with_its_method() -> None:
    served = served_routes()
    missing, wrong_method = [], []
    for path, operations in contract_operations().items():
        for method, operation in operations.items():
            if stage(operation) != 1:
                continue
            if path not in served:
                missing.append(f"{method.upper()} {path}")
                continue
            view = getattr(served[path], "view_class", None)
            if view is not None and not hasattr(view, method):
                wrong_method.append(f"{method.upper()} {path}")
    assert missing == []
    assert wrong_method == []


def test_stage2_operations_are_not_served_yet() -> None:
    served = served_routes()
    early = [
        f"{method.upper()} {path}"
        for path, operations in contract_operations().items()
        for method, operation in operations.items()
        if stage(operation) == 2 and path in served
    ]
    assert early == []


def test_every_public_route_is_in_the_contract() -> None:
    contract = contract_operations()
    extra = [path for path in served_routes() if path.startswith(PUBLIC) and path not in contract]
    assert extra == []
