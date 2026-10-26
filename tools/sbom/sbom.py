#!/usr/bin/env python3
"""SBOM of the ALMI deliverables (docs/sbom.md): CycloneDX 1.6 JSON, licences and their policy.

Syft (tools/sbom/build.sh) catalogues the images and the lock files; this script adds what Syft
does not see, collects the licence texts and checks everything against the licence policy:

  vcpkg      SBOM of the DL module: ports of vcpkg_installed linked into license_module
             (dependencies of libsodium, curl, nlohmann-json) or used by the tests only
  finalize   a Syft SBOM made ready to hand over: no file entries, the artifact named, libraries
             bundled in Python wheels added (vendored.json), concluded licences applied
  notices    licence texts: Python packages of an image, npm packages of node_modules
  report     Markdown and CSV of every SBOM with the policy verdicts; exit code 1 on a violation

Standard library only: it runs on the CI runners (Linux and Windows) and on a host without
network.
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import json
import re
import subprocess
import sys
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
TOOL = {"type": "application", "name": "almi-sbom", "version": "1"}
# Properties of a component that the report and the policy read.
KIND = "almi:policy-kind"  # linked | application | os | dev
ARTIFACT = "almi:artifact"
# Package types of Syft for the ecosystems our lock files install.
APP_TYPES = {"python", "npm"}
# Ports of vcpkg that only build other ports (cmake helpers): not part of any binary.
HOST_PORTS = re.compile(r"^vcpkg-")

Json = dict[str, Any]


# --------------------------------------------------------------------------- CycloneDX helpers


def new_bom(name: str, version: str, kind: str, properties: dict[str, str] | None = None) -> Json:
    props = {ARTIFACT: name, KIND: kind, **(properties or {})}
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "tools": {"components": [TOOL]},
            "component": {
                "type": "application" if kind != "linked" else "library",
                "bom-ref": name,
                "name": name,
                "version": version,
                "properties": [{"name": k, "value": v} for k, v in props.items()],
            },
        },
        "components": [],
        "dependencies": [],
    }


def stamp(bom: Json, timestamp: str | None) -> Json:
    """Serial number derived from the content (the same input gives the same file) and the time of
    the build (SOURCE_DATE_EPOCH of build.sh), not of this run."""
    bom.pop("serialNumber", None)
    if timestamp:
        bom["metadata"]["timestamp"] = timestamp
    body = json.dumps(bom, sort_keys=True, ensure_ascii=False)
    bom["serialNumber"] = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, body)}"
    return bom


def licence_entries(expression: str | None) -> list[Json]:
    if not expression or expression in ("NOASSERTION", "NONE"):
        return []
    if re.fullmatch(r"[A-Za-z0-9.+-]+", expression) and not expression.startswith("LicenseRef"):
        return [{"license": {"id": expression}}]
    if re.search(r"\s(AND|OR|WITH)\s", expression) or expression.startswith("LicenseRef-"):
        return [{"expression": expression}]
    return [{"license": {"name": expression}}]


def licences_of(component: Json) -> list[str]:
    out = []
    for entry in component.get("licenses", []):
        if "expression" in entry:
            out.append(entry["expression"])
        else:
            lic = entry.get("license", {})
            value = lic.get("id") or lic.get("name")
            if value:
                out.append(value)
    return out


def prop(component: Json, name: str) -> str | None:
    for p in component.get("properties", []):
        if p.get("name") == name:
            return str(p.get("value"))
    return None


def set_prop(component: Json, name: str, value: str) -> None:
    props = [p for p in component.get("properties", []) if p.get("name") != name]
    props.append({"name": name, "value": value})
    component["properties"] = props


def write_json(path: Path, data: Json) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> Json:
    data: Json = json.loads(path.read_text(encoding="utf-8"))
    return data


# --------------------------------------------------------------------------- vcpkg (DL module)


@dataclass
class Port:
    name: str
    version: str = ""
    port_version: str = "0"
    depends: set[str] = field(default_factory=set)
    features: set[str] = field(default_factory=set)


def _paragraphs(text: str) -> list[dict[str, str]]:
    out = []
    for block in re.split(r"\n\s*\n", text):
        fields: dict[str, str] = {}
        key = ""
        for line in block.splitlines():
            if line[:1] in (" ", "\t") and key:
                fields[key] += " " + line.strip()
            elif ":" in line:
                key, _, value = line.partition(":")
                fields[key.strip()] = value.strip()
        if fields:
            out.append(fields)
    return out


def _dependency_names(value: str) -> set[str]:
    names = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        # "zlib", "openssl:x64-linux", "vcpkg-cmake:x64-linux", "curl[ssl]"
        names.add(re.split(r"[:\[]", item, maxsplit=1)[0].strip())
    return names


def read_vcpkg_status(installed: Path, triplet: str) -> dict[str, Port]:
    """Ports of one triplet from vcpkg_installed/vcpkg/status (Debian control format; a port has a
    paragraph of its core and one per installed feature, each with its Depends)."""
    status = installed / "vcpkg" / "status"
    ports: dict[str, Port] = {}
    for p in _paragraphs(status.read_text(encoding="utf-8")):
        if p.get("Architecture") != triplet or not p.get("Status", "").endswith(" installed"):
            continue
        port = ports.setdefault(p["Package"], Port(p["Package"]))
        if "Feature" in p:
            port.features.add(p["Feature"])
        else:
            port.version = p.get("Version", "")
            port.port_version = p.get("Port-Version", "0")
            port.features.add("core")
        # A feature depends on the core of its own port ("curl[core,ssl]"): not a dependency.
        port.depends |= _dependency_names(p.get("Depends", "")) - {port.name}
    return ports


def closure(ports: dict[str, Port], roots: list[str]) -> list[str]:
    seen: list[str] = []
    stack = list(roots)
    while stack:
        name = stack.pop()
        if name in seen or name not in ports or HOST_PORTS.match(name):
            continue
        seen.append(name)
        stack.extend(sorted(ports[name].depends))
    return sorted(seen)


def port_metadata(installed: Path, triplet: str, port: str) -> Json:
    """Licence, home page and sources of a port from the SPDX document vcpkg writes for it."""
    meta: Json = {"license": None, "homepage": None, "sources": [], "copyright": None}
    share = installed / triplet / "share" / port
    spdx = share / "vcpkg.spdx.json"
    if spdx.is_file():
        doc = read_json(spdx)
        for pkg in doc.get("packages", []):
            if pkg.get("SPDXID") == "SPDXRef-port":
                for key in ("licenseConcluded", "licenseDeclared"):
                    value = pkg.get(key)
                    if value and value not in ("NOASSERTION", "NONE"):
                        meta["license"] = value
                        break
                meta["homepage"] = pkg.get("homepage")
            elif str(pkg.get("SPDXID", "")).startswith("SPDXRef-resource"):
                location = pkg.get("downloadLocation")
                if location and location not in ("NOASSERTION", "NONE"):
                    meta["sources"].append(location)
    copyright_file = share / "copyright"
    if copyright_file.is_file():
        meta["copyright"] = copyright_file.read_text(encoding="utf-8", errors="replace")
    return meta


def vcpkg_component(installed: Path, triplet: str, port: Port, scope: str) -> Json:
    meta = port_metadata(installed, triplet, port.name)
    version = port.version
    purl = f"pkg:generic/{port.name}@{version}?vcpkg_port_version={port.port_version}"
    component: Json = {
        "type": "library",
        "bom-ref": f"vcpkg:{port.name}",
        "name": port.name,
        "version": version,
        "purl": purl,
        "scope": scope,
        "licenses": licence_entries(meta["license"]),
        "properties": [
            {"name": "almi:vcpkg:port-version", "value": port.port_version},
            {"name": "almi:vcpkg:features", "value": ",".join(sorted(port.features))},
            {"name": "almi:vcpkg:triplet", "value": triplet},
            {"name": "almi:linkage", "value": "static"},
            # Linked into the products (the module) or used by its tests only.
            {"name": KIND, "value": "linked" if scope == "required" else "dev"},
        ],
    }
    refs = []
    if meta["homepage"]:
        refs.append({"type": "website", "url": meta["homepage"]})
    refs += [{"type": "distribution", "url": url} for url in meta["sources"]]
    if refs:
        component["externalReferences"] = refs
    return component


def cmd_vcpkg(args: argparse.Namespace) -> int:
    installed = Path(args.installed)
    ports = read_vcpkg_status(installed, args.triplet)
    if not ports:
        print(f"no ports of {args.triplet} in {installed}/vcpkg/status", file=sys.stderr)
        return 1
    linked = closure(ports, args.roots.split(","))
    missing = [r for r in args.roots.split(",") if r not in ports]
    if missing:
        print(f"ports not installed: {', '.join(missing)}", file=sys.stderr)
        return 1
    tests = [n for n in closure(ports, sorted(ports)) if n not in linked]

    module = new_bom(args.name, args.version, "linked", {"almi:platform": args.triplet})
    module["metadata"]["component"]["description"] = (
        "Модуль лицензирования DL; зависимости собраны vcpkg и связаны статически"
    )
    # One SBOM per platform: the report keeps them apart.
    set_prop(module["metadata"]["component"], ARTIFACT, f"{args.name} ({args.triplet})")
    for name in linked:
        module["components"].append(
            vcpkg_component(installed, args.triplet, ports[name], "required")
        )
    module["dependencies"] = [
        {"ref": args.name, "dependsOn": [f"vcpkg:{r}" for r in args.roots.split(",")]}
    ] + [
        {
            "ref": f"vcpkg:{n}",
            "dependsOn": [f"vcpkg:{d}" for d in sorted(ports[n].depends) if d in linked],
        }
        for n in linked
    ]
    write_json(Path(args.out), stamp(module, args.timestamp))

    if args.dev_out:
        dev = new_bom(f"{args.name}-tests", args.version, "dev", {"almi:platform": args.triplet})
        for name in tests:
            dev["components"].append(
                vcpkg_component(installed, args.triplet, ports[name], "excluded")
            )
        write_json(Path(args.dev_out), stamp(dev, args.timestamp))

    if args.notices:
        lines = [
            f"Сторонние компоненты {args.name} {args.version} ({args.triplet}).",
            "Тексты лицензий и уведомления об авторских правах, как их установил vcpkg.",
            "",
        ]
        for name in linked:
            meta = port_metadata(installed, args.triplet, name)
            lines += [
                "=" * 78,
                f"{name} {ports[name].version} — {meta['license'] or 'NOASSERTION'}",
                "=" * 78,
                (meta["copyright"] or "(файл copyright не найден)").rstrip(),
                "",
            ]
        notices = Path(args.notices)
        notices.parent.mkdir(parents=True, exist_ok=True)
        notices.write_text("\n".join(lines), encoding="utf-8")
    print(f"ok   {args.out}: {len(linked)} linked, {len(tests)} test-only ({args.triplet})")
    return 0


# --------------------------------------------------------------------------- finalize


def _image_libs(image: str, site: str) -> list[str]:
    script = f"cd {site} && ls -1 *.libs/* 2>/dev/null || true"
    result = subprocess.run(  # noqa: S603  (docker with the image of the build, no shell)
        ["docker", "run", "--rm", "--entrypoint", "sh", image, "-c", script],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _python_component(bom: Json, distribution: str) -> Json | None:
    wanted = re.sub(r"[-_.]+", "-", distribution).lower()
    components: list[Json] = bom["components"]
    for c in components:
        if (
            c.get("purl", "").startswith("pkg:pypi/")
            and re.sub(r"[-_.]+", "-", c["name"]).lower() == wanted
        ):
            return c
    return None


def add_vendored(bom: Json, vendored: Json, image_libs: list[str] | None) -> list[str]:
    """Libraries inside Python wheels: shared objects of auditwheel (<wheel>.libs/, checked against
    the image) and static ones (from the wheel's documentation). Returns the problems found."""
    problems = []
    seen_libs = set()
    for distribution, entry in vendored.items():
        parent = _python_component(bom, distribution)
        if parent is None:
            continue
        if parent.get("version") != entry["version"]:
            problems.append(
                f"{distribution} {parent.get('version')} differs from vendored.json "
                f"({entry['version']}): check its bundled libraries and update the file"
            )
            continue
        children = []
        for lib in entry.get("libraries", []):
            ref = f"vendored:{distribution}/{lib['id']}"
            component: Json = {
                "type": "library",
                "bom-ref": ref,
                "name": lib["name"],
                "scope": "required",
                "licenses": licence_entries(lib["license"]),
                "properties": [
                    {"name": "almi:vendored-in", "value": f"{distribution} {entry['version']}"},
                    {"name": "almi:linkage", "value": lib.get("linkage", "shared")},
                ],
            }
            if lib.get("version"):
                component["version"] = lib["version"]
            if lib.get("url"):
                component["externalReferences"] = [{"type": "website", "url": lib["url"]}]
            if lib.get("files"):
                seen_libs.update(lib["files"])
                set_prop(component, "almi:files", ", ".join(lib["files"]))
            bom["components"].append(component)
            children.append(ref)
        bom["dependencies"].append({"ref": parent["bom-ref"], "dependsOn": children})
    if image_libs is not None:
        unknown = []
        for path in image_libs:
            folder, _, name = path.partition("/")
            prefix = re.sub(r"-[0-9a-f]{8}\.so.*$", "", name)
            if f"{folder}/{prefix}" not in seen_libs:
                unknown.append(path)
        if unknown:
            problems.append("libraries of wheels missing from vendored.json: " + ", ".join(unknown))
    return problems


def apply_overrides(bom: Json, overrides: list[Json]) -> None:
    """Concluded licences for packages whose metadata has none or a wrong one (with the source
    the licence was taken from)."""
    for c in bom["components"]:
        for rule in overrides:
            purl = unquote(c.get("purl", ""))  # "libstdc%2B%2B6" is "libstdc++6"
            if ("purl" in rule and purl.startswith(rule["purl"])) or c.get("name") == rule.get(
                "name"
            ):
                c["licenses"] = licence_entries(rule["license"])
                set_prop(c, "almi:license-concluded-from", rule["source"])


def merge(paths: list[str]) -> Json:
    """One SBOM of several scans of an artifact (an image and the lock file of what it bundles)."""
    bom = read_json(Path(paths[0]))
    refs = {c["bom-ref"] for c in bom.get("components", [])}
    for path in paths[1:]:
        other = read_json(Path(path))
        for c in other.get("components", []):
            if c["bom-ref"] not in refs:
                bom.setdefault("components", []).append(c)
                refs.add(c["bom-ref"])
        bom.setdefault("dependencies", []).extend(other.get("dependencies", []))
    return bom


def identity(component: Json) -> str:
    return component.get("purl") or f"{component.get('name')}@{component.get('version')}"


def cmd_finalize(args: argparse.Namespace) -> int:
    bom = merge(args.input)
    kind = args.kind
    meta = bom.setdefault("metadata", {})
    tools = meta.setdefault("tools", {}).setdefault("components", [])
    if TOOL not in tools:
        tools.append(TOOL)
    root = meta.get("component") or {}
    root.update({"name": args.name, "version": args.version})
    root.setdefault("bom-ref", args.name)
    for key, value in ((ARTIFACT, args.name), (KIND, kind)):
        set_prop(root, key, value)
    if args.description:
        root["description"] = args.description
    meta["component"] = root

    # Files are evidence of the scan, not components to hand over; own packages are the artifact.
    own = set(args.own or [])
    elsewhere = {
        identity(c)
        for path in args.exclude_from or []
        for c in read_json(Path(path)).get("components", [])
    }
    dropped = {
        c["bom-ref"]
        for c in bom.get("components", [])
        if c.get("type") == "file" or c.get("name") in own or identity(c) in elsewhere
    }
    bom["components"] = [c for c in bom.get("components", []) if c["bom-ref"] not in dropped]
    bom["dependencies"] = [
        {"ref": d["ref"], "dependsOn": [x for x in d.get("dependsOn", []) if x not in dropped]}
        for d in bom.get("dependencies", [])
        if d["ref"] not in dropped
    ]

    policy = read_json(Path(args.policy))
    apply_overrides(bom, policy.get("overrides", []))
    problems: list[str] = []
    if args.vendored:
        libs = _image_libs(args.image, args.site) if args.image else None
        problems += add_vendored(bom, read_json(Path(args.vendored)), libs)
    for c in bom["components"]:
        set_prop(c, KIND, component_kind(c, kind))
    write_json(Path(args.out), stamp(bom, args.timestamp))
    for p in problems:
        print(f"FAIL {p}", file=sys.stderr)
    print(f"ok   {args.out}: {len(bom['components'])} components")
    return 1 if problems else 0


def component_kind(component: Json, artifact_kind: str) -> str:
    """Packages of the ecosystems we install (Python from uv.lock, npm from package-lock.json, the
    libraries bundled in their wheels) follow the artifact: linked into a product, our application,
    a dev tool. Everything else Syft finds in an image (Debian packages, binaries, a jar of the
    base image) is the base image: separate programs aggregated with ours."""
    if artifact_kind in ("dev", "os"):
        return artifact_kind
    package_type = prop(component, "syft:package:type")
    if package_type in APP_TYPES or prop(component, "almi:vendored-in"):
        return artifact_kind
    return "os"


# --------------------------------------------------------------------------- notices

_PY_NOTICES = r"""
import importlib.metadata as m, json, sys
out = []
for d in sorted(m.distributions(), key=lambda d: d.metadata["Name"].lower()):
    texts = []
    names = ("LICEN", "COPYING", "NOTICE", "AUTHORS")
    files = [f for f in (d.files or []) if f.name.upper().startswith(names)]
    for f in files:
        try:
            texts.append((str(f), f.locate().read_text(encoding="utf-8", errors="replace")))
        except OSError:
            pass
    out.append({"name": d.metadata["Name"], "version": d.version,
                "license": d.metadata.get("License-Expression") or d.metadata.get("License") or "",
                "texts": texts})
json.dump(out, sys.stdout)
"""


def cmd_notices(args: argparse.Namespace) -> int:
    entries: list[Json] = []
    if args.image or args.local_python:
        command = (
            ["docker", "run", "--rm", "-i", "--entrypoint", args.python, args.image, "-I", "-"]
            if args.image
            else [args.local_python, "-I", "-"]
        )
        result = subprocess.run(  # noqa: S603  (docker or the interpreter of the build, no shell)
            command,
            input=_PY_NOTICES,
            check=True,
            capture_output=True,
            text=True,
        )
        entries = [e for e in json.loads(result.stdout) if e["name"] not in set(args.own or [])]
    elif args.npm_lock:
        lock = read_json(Path(args.npm_lock))
        base = Path(args.npm_lock).parent
        for key, pkg in sorted(lock.get("packages", {}).items()):
            if not key or pkg.get("dev") or (pkg.get("devOptional") and not pkg.get("optional")):
                continue
            folder = base / key
            if not folder.is_dir():  # an optional package of another platform
                continue
            texts = []
            for f in sorted(folder.iterdir()):
                if f.is_file() and f.name.upper().startswith(("LICEN", "COPYING", "NOTICE")):
                    texts.append((f.name, f.read_text(encoding="utf-8", errors="replace")))
            name = key.split("node_modules/")[-1]
            entries.append(
                {
                    "name": name,
                    "version": pkg.get("version", ""),
                    "license": pkg.get("license", ""),
                    "texts": texts,
                }
            )
    lines = [args.title, "", f"Компонентов: {len(entries)}.", ""]
    without = []
    for e in entries:
        lines += [
            "=" * 78,
            f"{e['name']} {e['version']} — {e['license'] or 'лицензия не указана в метаданных'}",
            "=" * 78,
        ]
        if not e["texts"]:
            without.append(e["name"])
            lines.append("(текст лицензии не приложен к пакету; см. метаданные и SBOM)")
        for name, text in e["texts"]:
            lines += [f"--- {name}", text.rstrip()]
        lines.append("")
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"ok   {args.out}: {len(entries)} packages, {len(without)} without a licence file")
    return 0


# --------------------------------------------------------------------------- policy and report

ORDER = [
    "permissive",
    "weak-copyleft",
    "strong-copyleft",
    "network-copyleft",
    "not-open",
    "unknown",
]
VERDICTS = ["ok", "obligation", "review", "fail"]


class Policy:
    def __init__(self, data: Json) -> None:
        self.categories: list[tuple[str, list[str]]] = [
            (name, [p.lower() for p in patterns]) for name, patterns in data["categories"].items()
        ]
        self.exceptions = [p.lower() for p in data.get("linking-exceptions", [])]
        self.rules: dict[str, dict[str, str]] = data["rules"]
        self.obligations: dict[str, str] = data.get("obligations", {})

    def category_of_id(self, licence: str) -> str:
        value = licence.strip().lower()
        for name, patterns in self.categories:
            if any(fnmatch.fnmatchcase(value, p) for p in patterns):
                return name
        return "unknown"

    def category(self, expression: str) -> str:
        """Category of an SPDX expression: OR takes the most permissive branch, AND the most
        restrictive, WITH a linking exception makes a strong copyleft weak."""
        tokens = re.findall(r"\(|\)|[^\s()]+", expression)
        pos = 0

        def parse_or() -> str:
            nonlocal pos
            best = parse_and()
            while pos < len(tokens) and tokens[pos].upper() == "OR":
                pos += 1
                other = parse_and()
                best = min(best, other, key=ORDER.index)
            return best

        def parse_and() -> str:
            nonlocal pos
            worst = parse_with()
            while pos < len(tokens) and tokens[pos].upper() == "AND":
                pos += 1
                other = parse_with()
                worst = max(worst, other, key=ORDER.index)
            return worst

        def parse_with() -> str:
            nonlocal pos
            if pos < len(tokens) and tokens[pos] == "(":
                pos += 1
                value = parse_or()
                pos += 1  # ")"
            else:
                value = self.category_of_id(tokens[pos]) if pos < len(tokens) else "unknown"
                pos += 1
            if pos < len(tokens) and tokens[pos].upper() == "WITH":
                exception = tokens[pos + 1].lower() if pos + 1 < len(tokens) else ""
                pos += 2
                if value == "strong-copyleft" and any(
                    fnmatch.fnmatchcase(exception, p) for p in self.exceptions
                ):
                    value = "weak-copyleft"
            return value

        if not tokens:
            return "unknown"
        if not re.search(r"\s(AND|OR|WITH)\s|[()]", expression):
            return self.category_of_id(expression)
        return parse_or()

    def judge(self, component: Json, default_kind: str = "application") -> tuple[str, str]:
        licences = licences_of(component)
        kind = prop(component, KIND) or default_kind
        # Several licences of one package apply together. A Debian copyright file names many,
        # including its own short names for notices of single files: for the packages of the
        # base images the recognised ones decide, the package is "unknown" only without any.
        categories = [self.category(lic) for lic in licences]
        if kind == "os":
            categories = [c for c in categories if c != "unknown"] or ["unknown"]
        category = max(categories, key=ORDER.index) if categories else "unknown"
        return category, self.rules[kind][category]


@dataclass
class Row:
    artifact: str
    file: str
    name: str
    version: str
    type: str
    licences: str
    category: str
    verdict: str
    kind: str
    purl: str


def collect(paths: list[Path], policy: Policy) -> tuple[list[Json], list[Row]]:
    boms, rows = [], []
    for path in paths:
        bom = read_json(path)
        boms.append({"path": path, "bom": bom})
        root = bom.get("metadata", {}).get("component", {})
        artifact = prop(root, ARTIFACT) or root.get("name", path.stem)
        # A component without its own kind takes the kind of the artifact.
        default_kind = prop(root, KIND) or "application"
        for c in bom.get("components", []):
            if c.get("type") == "operating-system":  # the distribution: its packages are listed
                continue
            category, verdict = policy.judge(c, default_kind)
            rows.append(
                Row(
                    artifact=artifact,
                    file=path.name,
                    name=c.get("name", ""),
                    version=c.get("version", ""),
                    type=prop(c, "syft:package:type") or c.get("type", ""),
                    licences="; ".join(licences_of(c)),
                    category=category,
                    verdict=verdict,
                    kind=prop(c, KIND) or default_kind,
                    purl=c.get("purl", ""),
                )
            )
    return boms, rows


CATEGORY_RU = {
    "permissive": "разрешительная",
    "weak-copyleft": "слабый копилефт",
    "strong-copyleft": "сильный копилефт",
    "network-copyleft": "сетевой копилефт",
    "not-open": "не открытая",
    "unknown": "не определена",
}
VERDICT_RU = {
    "ok": "допустимо",
    "obligation": "допустимо с обязательствами",
    "review": "проверить",
    "fail": "нарушение",
}
KIND_RU = {
    "linked": "связывается с продуктом",
    "application": "в составе приложения",
    "os": "пакет ОС образа",
    "dev": "разработка и тесты",
}


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def write_report(
    boms: list[Json], rows: list[Row], policy: Policy, out: Path, title: str, meta: Json
) -> None:
    by_artifact: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        by_artifact[r.artifact].append(r)
    lines = [f"# {title}", ""]
    lines += [f"- {k}: {v}" for k, v in meta.items()]
    lines += [
        "",
        "Формат — CycloneDX 1.6 JSON, один файл на артефакт поставки. Вердикты — по политике "
        "`tools/sbom/license-policy.json` (`docs/sbom.md`, раздел 4).",
        "",
        "## 1. Сводка",
        "",
        "| Артефакт | Файл | Компонентов | Допустимо | С обязательствами | Проверить | Нарушения |",
        "|---|---|---|---|---|---|---|",
    ]
    totals: Counter[str] = Counter()
    for artifact, items in by_artifact.items():
        verdicts = Counter(r.verdict for r in items)
        totals.update(verdicts)
        totals["all"] += len(items)
        lines.append(
            f"| {artifact} | `{items[0].file}` | {len(items)} | {verdicts['ok']} | "
            f"{verdicts['obligation']} | {verdicts['review']} | {verdicts['fail']} |"
        )
    lines.append(
        f"| **Всего** | | **{totals['all']}** | {totals['ok']} | {totals['obligation']} | "
        f"{totals['review']} | **{totals['fail']}** |"
    )

    lines += [
        "",
        "## 2. Лицензии",
        "",
        "| Лицензия | Категория | Компонентов | Артефакты |",
        "|---|---|---|---|",
    ]
    per_licence: dict[str, set[str]] = defaultdict(set)
    count: Counter[str] = Counter()
    for r in rows:
        for lic in r.licences.split("; ") if r.licences else ["—"]:
            per_licence[lic].add(r.artifact)
            count[lic] += 1
    for lic, n in sorted(count.items(), key=lambda kv: (-kv[1], kv[0])):
        category = policy.category(lic) if lic != "—" else "unknown"
        artifacts = ", ".join(sorted(per_licence[lic]))
        lines.append(f"| {_md(lic)} | {CATEGORY_RU[category]} | {n} | {artifacts} |")

    for verdict, heading in (
        ("fail", "3. Нарушения политики"),
        ("review", "4. Требуют проверки"),
        ("obligation", "5. Допустимо с обязательствами"),
    ):
        items = [r for r in rows if r.verdict == verdict]
        lines += ["", f"## {heading}", ""]
        if not items:
            lines.append("Нет.")
            continue
        if verdict == "obligation":
            lines.append("Что выполнить — по категории лицензии:")
            lines.append("")
            for category in ORDER:
                if category in policy.obligations and any(r.category == category for r in items):
                    lines.append(f"- **{CATEGORY_RU[category]}**: {policy.obligations[category]}")
            lines.append("")
        lines += [
            "| Артефакт | Компонент | Версия | Где | Лицензия | Категория |",
            "|---|---|---|---|---|---|",
        ]
        for r in sorted(items, key=lambda r: (r.artifact, r.name)):
            lines.append(
                f"| {r.artifact} | {_md(r.name)} | {_md(r.version)} | "
                f"{KIND_RU.get(r.kind, r.kind)} | {_md(r.licences) or '—'} | "
                f"{CATEGORY_RU[r.category]} |"
            )

    lines += ["", "## 6. Полный перечень по артефактам"]
    for n, (artifact, items) in enumerate(by_artifact.items(), start=1):
        bom = next(b["bom"] for b in boms if b["path"].name == items[0].file)
        root = bom.get("metadata", {}).get("component", {})
        lines += ["", f"### 6.{n}. {artifact} {root.get('version', '')}", ""]
        if root.get("description"):
            lines += [root["description"], ""]
        lines += [
            f"Файл `{items[0].file}`, компонентов {len(items)}.",
            "",
            "| Компонент | Версия | Тип | Лицензия | Вердикт | purl |",
            "|---|---|---|---|---|---|",
        ]
        for r in sorted(items, key=lambda r: (r.type, r.name.lower())):
            lines.append(
                f"| {_md(r.name)} | {_md(r.version)} | {r.type} | {_md(r.licences) or '—'} | "
                f"{VERDICT_RU[r.verdict]} | {_md(r.purl)} |"
            )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_report(args: argparse.Namespace) -> int:
    paths = [Path(p) for p in args.sboms]
    policy = Policy(read_json(Path(args.policy)))
    boms, rows = collect(paths, policy)
    meta = dict(item.split("=", 1) for item in args.meta or [])
    write_report(boms, rows, policy, Path(args.out), args.title, meta)
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    "artifact",
                    "name",
                    "version",
                    "type",
                    "licenses",
                    "category",
                    "verdict",
                    "policy_kind",
                    "purl",
                ]
            )
            for r in rows:
                writer.writerow(
                    [
                        r.artifact,
                        r.name,
                        r.version,
                        r.type,
                        r.licences,
                        r.category,
                        r.verdict,
                        r.kind,
                        r.purl,
                    ]
                )
    verdicts = Counter(r.verdict for r in rows)
    print(
        f"ok   {args.out}: {len(rows)} components in {len(paths)} SBOMs; "
        f"obligations {verdicts['obligation']}, review {verdicts['review']}, "
        f"violations {verdicts['fail']}"
    )
    for r in rows:
        if r.verdict == "fail":
            print(
                f"FAIL {r.artifact}: {r.name} {r.version} — "
                f"{r.licences or 'no licence'} ({r.category})",
                file=sys.stderr,
            )
    return 1 if verdicts["fail"] else 0


# --------------------------------------------------------------------------- command line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--timestamp", help="ISO 8601 time of the build (build.sh: SOURCE_DATE_EPOCH)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("vcpkg", help="SBOM of the DL module from vcpkg_installed")
    p.add_argument("--installed", required=True, help="vcpkg_installed directory of the build")
    p.add_argument("--triplet", required=True)
    p.add_argument(
        "--roots", default="libsodium,curl,nlohmann-json", help="ports linked into the module"
    )
    p.add_argument("--name", default="license_module")
    p.add_argument("--version", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--dev-out", help="SBOM of the ports used by the tests only")
    p.add_argument("--notices", help="licence texts of the linked ports")
    p.set_defaults(func=cmd_vcpkg)

    p = sub.add_parser("finalize", help="a Syft SBOM made ready to hand over")
    p.add_argument(
        "--in", dest="input", nargs="+", required=True, help="Syft SBOMs of the artifact"
    )
    p.add_argument("--out", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--kind", required=True, choices=["linked", "application", "os", "dev"])
    p.add_argument("--description")
    p.add_argument("--own", nargs="*", help="names of our own packages (the artifact itself)")
    p.add_argument(
        "--exclude-from", nargs="*", help="SBOMs whose components are left out (the dev SBOM)"
    )
    p.add_argument("--policy", default=str(HERE / "license-policy.json"))
    p.add_argument("--vendored", help="vendored.json: libraries inside Python wheels")
    p.add_argument("--image", help="image to check the shared libraries of wheels in")
    p.add_argument("--site", default="/opt/venv/lib/python3.13/site-packages")
    p.set_defaults(func=cmd_finalize)

    p = sub.add_parser("notices", help="licence texts of Python or npm packages")
    p.add_argument("--image", help="image with the Python packages")
    p.add_argument("--python", default="/opt/venv/bin/python")
    p.add_argument("--local-python", help="interpreter of a local environment instead of an image")
    p.add_argument("--npm-lock", help="package-lock.json next to node_modules")
    p.add_argument("--own", nargs="*")
    p.add_argument("--title", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_notices)

    p = sub.add_parser("report", help="Markdown and CSV of SBOMs; exit 1 on a violation")
    p.add_argument("sboms", nargs="+")
    p.add_argument("--policy", default=str(HERE / "license-policy.json"))
    p.add_argument("--title", default="SBOM системы лицензирования АЛМИ")
    p.add_argument("--meta", nargs="*", help="key=value lines at the top of the report")
    p.add_argument("--out", required=True)
    p.add_argument("--csv")
    p.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
