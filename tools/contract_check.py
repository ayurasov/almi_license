# /// script
# requires-python = ">=3.13"
# dependencies = ["jsonschema==4.26.0", "pyyaml==6.0.3"]
# ///
"""Contract checks for contracts/ (make contract-check; E00-03).

1. Every contracts/schemas/*.schema.json is a valid JSON Schema 2020-12.
2. contracts/schemas/examples/<schema>/valid-*.json pass, invalid-*.json fail.
3. Every ```json block of docs/specs/02-interaction-spec.md validates against the
   schema assigned to it in DOC_BLOCKS (a new block without an assignment fails).
4. Schemas that mirror an OpenAPI component match it by fields and types.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "contracts" / "schemas"
EXAMPLES = SCHEMAS / "examples"
OPENAPI = ROOT / "contracts" / "openapi-product-api-v1.yaml"
DOC = ROOT / "docs" / "specs" / "02-interaction-spec.md"
BASE = "https://license.alter-os.ru/schemas/v1/"
OPENAPI_URI = "urn:almi:openapi-product-api-v1"

# (section heading, ordinal of the json block inside it) -> "schema:<name>" or "openapi:<component>"
DOC_BLOCKS: dict[tuple[str, int], str] = {
    ("4.1. Адрес и обнаружение", 1): "schema:config",
    ("4.5. Ошибки", 1): "schema:problem",
    ("5.1. Обнаружение сервера", 1): "openapi:Discovery",
    ("5.2. Активация", 1): "openapi:ActivateRequest",
    ("5.2. Активация", 2): "openapi:LeaseResponse",
    ("5.5. Доверенные ключи", 1): "openapi:TrustBundle",
    ("5.6. События", 1): "openapi:EventsRequest",
    ("6.1. Заголовок JWS", 1): "schema:jws-header",
    ("6.2. Утверждения", 1): "schema:lease",
    ("8. Директивы сервера", 1): "schema:directive",
    ("9. Сообщения", 1): "schema:message",
    ("10. Офлайн-файлы", 1): "schema:alk-file",
    (
        "11.1. Этап 1: адаптер подписки Nextcloud",
        1,
    ): "openapi:NextcloudSubscriptionResponse",
    ("14.3. Вебхуки (этап 2)", 1): "openapi:WebhookEvent",
    ("Приложение А. Пример `.alk-req`", 1): "schema:alk-file",
    ("Приложение А. Пример `.alk-req`", 2): "schema:alk-req",
    ("Приложение Б. Пример `.alk-lic`", 1): "schema:alk-file",
}

# Schemas that must match an OpenAPI component by fields and types.
OPENAPI_MIRRORS: dict[str, str] = {
    "license-state": "LicenseState",
    "product": "Product",
    "os-info": "OsInfo",
    "instance": "Instance",
    "fingerprint": "Fingerprint",
    "usage": "Usage",
    "policy": "Policy",
    "message": "Message",
    "directive": "Directive",
    "problem": "Problem",
    "lease": "LeaseClaims",
    "alk-file": "AlkFile",
}

# Keywords that describe a value without changing what is valid.
ANNOTATIONS = {"$schema", "$id", "title", "description", "examples", "default"}


def load_schemas() -> dict[str, dict[str, Any]]:
    return {
        path.name.removesuffix(".schema.json"): json.loads(
            path.read_text(encoding="utf-8")
        )
        for path in sorted(SCHEMAS.glob("*.schema.json"))
    }


def build_registry(
    schemas: dict[str, dict[str, Any]], openapi: dict[str, Any]
) -> Registry:
    resources = [
        (schema["$id"], DRAFT202012.create_resource(schema))
        for schema in schemas.values()
    ]
    resources.append(
        (
            OPENAPI_URI,
            Resource.from_contents(openapi, default_specification=DRAFT202012),
        )
    )
    return Registry().with_resources(resources)


def validator_for(target: str, registry: Registry) -> Draft202012Validator:
    kind, name = target.split(":", 1)
    ref = (
        BASE + f"{name}.schema.json"
        if kind == "schema"
        else f"{OPENAPI_URI}#/components/schemas/{name}"
    )
    return Draft202012Validator({"$ref": ref}, registry=registry)


def errors_of(validator: Draft202012Validator, instance: Any) -> list[str]:
    return [
        f"{'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
        for error in validator.iter_errors(instance)
    ]


def check_metaschema(schemas: dict[str, dict[str, Any]]) -> list[str]:
    problems = []
    for name, schema in schemas.items():
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as error:  # noqa: BLE001  (any schema error is a finding; E00-03)
            problems.append(f"schema {name}: {error}")
        if schema.get("$id") != BASE + f"{name}.schema.json":
            problems.append(f"schema {name}: $id must be {BASE}{name}.schema.json")
    return problems


def check_examples(schemas: dict[str, dict[str, Any]], registry: Registry) -> list[str]:
    problems = []
    for name in schemas:
        folder = EXAMPLES / name
        valid = sorted(folder.glob("valid-*.json"))
        invalid = sorted(folder.glob("invalid-*.json"))
        if len(valid) < 1 or len(invalid) < 2:
            problems.append(
                f"examples {name}: need at least 1 valid and 2 invalid, found {len(valid)}/{len(invalid)}"
            )
        validator = validator_for(f"schema:{name}", registry)
        for path in valid:
            for message in errors_of(
                validator, json.loads(path.read_text(encoding="utf-8"))
            ):
                problems.append(f"{path.relative_to(ROOT)} must be valid: {message}")
        for path in invalid:
            if not errors_of(validator, json.loads(path.read_text(encoding="utf-8"))):
                problems.append(f"{path.relative_to(ROOT)} must be invalid but passes")
    return problems


def doc_json_blocks() -> list[tuple[str, int, int, str]]:
    blocks: list[tuple[str, int, int, str]] = []
    heading, counters = "", {}
    lines = DOC.read_text(encoding="utf-8").split("\n")
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
        if line.strip() == "```json":
            end = lines.index("```", index + 1)
            counters[heading] = counters.get(heading, 0) + 1
            blocks.append(
                (
                    heading,
                    counters[heading],
                    index + 1,
                    "\n".join(lines[index + 1 : end]),
                )
            )
            index = end
        index += 1
    return blocks


def check_doc_examples(registry: Registry) -> list[str]:
    problems = []
    seen = set()
    for heading, ordinal, line, text in doc_json_blocks():
        key = (heading, ordinal)
        seen.add(key)
        target = DOC_BLOCKS.get(key)
        where = f"{DOC.relative_to(ROOT)}:{line} [{heading} #{ordinal}]"
        if target is None:
            problems.append(
                f"{where}: json block has no schema in tools/contract_check.py DOC_BLOCKS"
            )
            continue
        try:
            instance = json.loads(text)
        except json.JSONDecodeError as error:
            problems.append(f"{where}: not JSON: {error}")
            continue
        for message in errors_of(validator_for(target, registry), instance):
            problems.append(f"{where} vs {target}: {message}")
    for key in DOC_BLOCKS.keys() - seen:
        problems.append(f"DOC_BLOCKS entry {key} matches no json block in the document")
    return problems


def normalize(node: Any, refs: dict[str, str]) -> Any:
    """Reduce a schema to what affects validity, with $ref replaced by the mirror name."""
    if isinstance(node, dict):
        if "$ref" in node:
            return {"$ref": refs.get(node["$ref"], node["$ref"])}
        result = {
            key: normalize(value, refs)
            for key, value in node.items()
            if key not in ANNOTATIONS
        }
        if result.get("additionalProperties") is True:
            del result["additionalProperties"]  # same as absent
        return result
    if isinstance(node, list):
        return [normalize(item, refs) for item in node]
    return node


def check_openapi_mirrors(
    schemas: dict[str, dict[str, Any]], openapi: dict[str, Any]
) -> list[str]:
    components = openapi["components"]["schemas"]
    refs = {
        f"{name}.schema.json": component for name, component in OPENAPI_MIRRORS.items()
    }
    refs |= {
        f"#/components/schemas/{component}": component
        for component in OPENAPI_MIRRORS.values()
    }
    problems = []
    for name, component in OPENAPI_MIRRORS.items():
        ours, theirs = (
            normalize(schemas[name], refs),
            normalize(components[component], refs),
        )
        if ours != theirs:
            problems.append(
                f"schema {name} differs from OpenAPI {component}:\n"
                f"  schema:  {json.dumps(ours, ensure_ascii=False, sort_keys=True)}\n"
                f"  openapi: {json.dumps(theirs, ensure_ascii=False, sort_keys=True)}"
            )
    return problems


def main() -> int:
    schemas = load_schemas()
    openapi = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    registry = build_registry(schemas, openapi)
    checks = {
        "metaschema": check_metaschema(schemas),
        "examples": check_examples(schemas, registry),
        "docs/specs/02 json blocks": check_doc_examples(registry),
        "OpenAPI mirrors": check_openapi_mirrors(schemas, openapi),
    }
    failed = False
    for title, problems in checks.items():
        print(f"{title}: {'OK' if not problems else f'{len(problems)} problem(s)'}")
        for problem in problems:
            print(f"  - {problem}")
        failed = failed or bool(problems)
    print(f"{len(schemas)} schemas, {len(DOC_BLOCKS)} document examples")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
