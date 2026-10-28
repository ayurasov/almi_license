"""Tests of tools/sbom/sbom.py (python3 -m unittest discover tools/sbom/tests)."""

from __future__ import annotations

import contextlib
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sbom  # noqa: E402

POLICY = Path(sbom.__file__).with_name("license-policy.json")
TIME = "2026-10-26T00:00:00Z"

STATUS = """\
Package: vcpkg-cmake
Version: 2025-08-07
Architecture: x64-linux
Status: install ok installed

Package: zlib
Version: 1.3.2
Port-Version: 2
Depends: vcpkg-cmake:x64-linux
Architecture: x64-linux
Status: install ok installed

Package: openssl
Version: 3.6.5
Port-Version: 2
Depends: vcpkg-cmake:x64-linux, vcpkg-cmake-config:x64-linux
Architecture: x64-linux
Status: install ok installed

Package: curl
Version: 8.23.0
Depends: vcpkg-cmake:x64-linux, zlib
Architecture: x64-linux
Status: install ok installed

Package: curl
Feature: openssl
Depends: curl[core,ssl], openssl
Architecture: x64-linux
Status: install ok installed

Package: curl
Feature: ssl
Depends: curl[core,openssl]
Architecture: x64-linux
Status: install ok installed

Package: libsodium
Version: 1.0.22
Port-Version: 1
Architecture: x64-linux
Status: install ok installed

Package: nlohmann-json
Version: 3.12.0
Port-Version: 2
Architecture: x64-linux
Status: install ok installed

Package: brotli
Version: 1.2.0
Architecture: x64-linux
Status: install ok installed

Package: cpp-httplib
Version: 0.63.0
Depends: brotli
Architecture: x64-linux
Status: install ok installed

Package: gtest
Version: 1.18.0
Architecture: x64-linux
Status: install ok installed

Package: zlib
Version: 1.3.2
Architecture: x64-windows-static
Status: install ok installed

Package: openssl
Version: 3.6.5
Architecture: x64-linux
Status: purge ok not-installed
"""

LICENCES = {
    "zlib": "Zlib",
    "openssl": "Apache-2.0",
    "curl": "curl AND ISC AND BSD-3-Clause",
    "libsodium": "ISC",
    "nlohmann-json": "MIT",
    "brotli": "MIT",
    "cpp-httplib": "MIT",
    "gtest": "BSD-3-Clause",
}


def vcpkg_tree(root: Path, licences: dict[str, str] = LICENCES) -> Path:
    installed = root / "vcpkg_installed"
    (installed / "vcpkg").mkdir(parents=True)
    (installed / "vcpkg" / "status").write_text(STATUS, encoding="utf-8")
    for port, licence in licences.items():
        share = installed / "x64-linux" / "share" / port
        share.mkdir(parents=True)
        spdx = {
            "packages": [
                {
                    "SPDXID": "SPDXRef-port",
                    "name": port,
                    "licenseConcluded": licence,
                    "homepage": f"https://{port}.example",
                },
                {
                    "SPDXID": "SPDXRef-binary",
                    "name": f"{port}:x64-linux",
                    "licenseConcluded": "NOASSERTION",
                },
                {
                    "SPDXID": "SPDXRef-resource-0",
                    "name": port,
                    "downloadLocation": f"git+https://example.org/{port}@abc",
                },
            ]
        }
        (share / "vcpkg.spdx.json").write_text(json.dumps(spdx), encoding="utf-8")
        (share / "copyright").write_text(f"Copyright (c) the {port} authors\n", encoding="utf-8")
    return installed


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = sbom.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def component(
    name: str, licence: str | None, package_type: str = "python", purl: str | None = None
) -> dict:
    c: dict = {
        "type": "library",
        "bom-ref": f"ref-{name}",
        "name": name,
        "version": "1.0",
        "purl": purl or f"pkg:pypi/{name}@1.0",
        "properties": [{"name": "syft:package:type", "value": package_type}],
    }
    if licence:
        c["licenses"] = sbom.licence_entries(licence)
    return c


class VcpkgTest(unittest.TestCase):
    def test_the_module_links_the_closure_of_its_roots_and_the_tests_get_the_rest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            installed = vcpkg_tree(root)
            code, out, _ = run(
                "--timestamp",
                TIME,
                "vcpkg",
                "--installed",
                str(installed),
                "--triplet",
                "x64-linux",
                "--version",
                "1.0.0",
                "--out",
                str(root / "dl.json"),
                "--dev-out",
                str(root / "tests.json"),
                "--notices",
                str(root / "notices" / "dl.txt"),
            )
            self.assertEqual(code, 0, out)
            module = json.loads((root / "dl.json").read_text())
            names = [c["name"] for c in module["components"]]
            self.assertEqual(names, ["curl", "libsodium", "nlohmann-json", "openssl", "zlib"])
            tests = json.loads((root / "tests.json").read_text())
            self.assertEqual(
                [c["name"] for c in tests["components"]], ["brotli", "cpp-httplib", "gtest"]
            )

            curl = next(c for c in module["components"] if c["name"] == "curl")
            self.assertEqual(curl["licenses"], [{"expression": "curl AND ISC AND BSD-3-Clause"}])
            self.assertEqual(curl["purl"], "pkg:generic/curl@8.23.0?vcpkg_port_version=0")
            self.assertEqual(sbom.prop(curl, "almi:vcpkg:features"), "core,openssl,ssl")
            self.assertEqual(sbom.prop(curl, "almi:linkage"), "static")
            self.assertIn(
                {"type": "distribution", "url": "git+https://example.org/curl@abc"},
                curl["externalReferences"],
            )
            deps = {d["ref"]: d["dependsOn"] for d in module["dependencies"]}
            self.assertEqual(
                deps["license_module"], ["vcpkg:libsodium", "vcpkg:curl", "vcpkg:nlohmann-json"]
            )
            self.assertEqual(deps["vcpkg:curl"], ["vcpkg:openssl", "vcpkg:zlib"])
            self.assertEqual(sbom.prop(module["metadata"]["component"], sbom.KIND), "linked")
            self.assertEqual(
                sbom.prop(module["metadata"]["component"], sbom.ARTIFACT),
                "license_module (x64-linux)",
            )
            self.assertEqual(module["metadata"]["timestamp"], TIME)

            notices = (root / "notices" / "dl.txt").read_text()
            self.assertIn("openssl 3.6.5 — Apache-2.0", notices)
            self.assertIn("Copyright (c) the openssl authors", notices)
            self.assertNotIn("gtest", notices)

    def test_the_same_tree_gives_the_same_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            installed = vcpkg_tree(root)
            for name in ("a.json", "b.json"):
                run(
                    "--timestamp",
                    TIME,
                    "vcpkg",
                    "--installed",
                    str(installed),
                    "--triplet",
                    "x64-linux",
                    "--version",
                    "1.0.0",
                    "--out",
                    str(root / name),
                )
            self.assertEqual((root / "a.json").read_text(), (root / "b.json").read_text())

    def test_a_port_without_a_licence_breaks_the_policy_of_the_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            installed = vcpkg_tree(root, {**LICENCES, "zlib": "NOASSERTION"})
            run(
                "--timestamp",
                TIME,
                "vcpkg",
                "--installed",
                str(installed),
                "--triplet",
                "x64-linux",
                "--version",
                "1.0.0",
                "--out",
                str(root / "dl.json"),
            )
            code, _, err = run("report", str(root / "dl.json"), "--out", str(root / "r.md"))
            self.assertEqual(code, 1)
            self.assertIn("zlib", err)

    def test_a_copyleft_port_in_the_module_is_a_violation_and_in_the_tests_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            installed = vcpkg_tree(
                root, {**LICENCES, "zlib": "LGPL-2.1-or-later", "gtest": "GPL-3.0-only"}
            )
            run(
                "--timestamp",
                TIME,
                "vcpkg",
                "--installed",
                str(installed),
                "--triplet",
                "x64-linux",
                "--version",
                "1.0.0",
                "--out",
                str(root / "dl.json"),
                "--dev-out",
                str(root / "t.json"),
            )
            module = json.loads((root / "dl.json").read_text())
            self.assertEqual({sbom.prop(c, sbom.KIND) for c in module["components"]}, {"linked"})
            code, _, err = run("report", str(root / "dl.json"), "--out", str(root / "r.md"))
            self.assertEqual(code, 1)
            self.assertIn("zlib", err)
            code, _, _ = run("report", str(root / "t.json"), "--out", str(root / "t.md"))
            self.assertEqual(code, 0)

    def test_a_component_without_a_kind_takes_the_kind_of_its_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bom = sbom.new_bom("license_module", "1.0.0", "linked")
            bom["components"] = [component("libfoo", "LGPL-2.1-or-later")]
            (root / "m.json").write_text(json.dumps(bom))
            code, _, err = run("report", str(root / "m.json"), "--out", str(root / "r.md"))
            self.assertEqual(code, 1)
            self.assertIn("libfoo", err)

    def test_a_missing_root_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            installed = vcpkg_tree(root)
            code, _, err = run(
                "vcpkg",
                "--installed",
                str(installed),
                "--triplet",
                "x64-linux",
                "--roots",
                "libsodium,libuv",
                "--version",
                "1",
                "--out",
                str(root / "dl.json"),
            )
            self.assertEqual(code, 1)
            self.assertIn("libuv", err)


class PolicyTest(unittest.TestCase):
    policy = sbom.Policy(json.loads(POLICY.read_text()))

    def test_categories_of_expressions(self) -> None:
        cases = {
            "MIT": "permissive",
            "mit": "permissive",
            "Apache-2.0 OR GPL-2.0-only": "permissive",
            "MIT AND LGPL-2.1-only": "weak-copyleft",
            "GPL-3.0-or-later WITH GCC-exception-3.1": "weak-copyleft",
            "GPL-2.0-only": "strong-copyleft",
            "AGPL-3.0-only": "network-copyleft",
            "BUSL-1.1": "not-open",
            "(MIT OR GPL-2.0-only) AND BSD-3-Clause": "permissive",
            "FTL OR GPL-2.0-or-later": "permissive",
            "LGPL-3.0-or-later OR GPL-2.0-or-later": "weak-copyleft",
            "Some-Custom-Text": "unknown",
            "GPL-2+-with-link-exception": "weak-copyleft",
        }
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                self.assertEqual(self.policy.category(expression), expected)

    def judge(self, licence: str | None, kind: str, *more: str) -> tuple[str, str]:
        c = component("x", licence)
        for extra in more:
            c["licenses"] = c.get("licenses", []) + sbom.licence_entries(extra)
        sbom.set_prop(c, sbom.KIND, kind)
        return self.policy.judge(c)

    def test_the_module_takes_only_permissive_licences(self) -> None:
        self.assertEqual(self.judge("ISC", "linked"), ("permissive", "ok"))
        self.assertEqual(self.judge("LGPL-2.1-or-later", "linked"), ("weak-copyleft", "fail"))
        self.assertEqual(self.judge(None, "linked"), ("unknown", "fail"))

    def test_the_application_takes_weak_copyleft_with_obligations(self) -> None:
        self.assertEqual(
            self.judge("LGPL-3.0-only", "application"), ("weak-copyleft", "obligation")
        )
        self.assertEqual(self.judge("GPL-3.0-only", "application"), ("strong-copyleft", "fail"))
        self.assertEqual(self.judge("Dual License", "application"), ("unknown", "fail"))

    def test_packages_of_the_os_are_judged_by_their_recognised_licences(self) -> None:
        self.assertEqual(
            self.judge("GPL-2.0-only", "os", "TEXT-TABS"), ("strong-copyleft", "obligation")
        )
        self.assertEqual(self.judge("sha256:abc", "os"), ("unknown", "review"))
        # Without the OS rule one unknown name makes the package unknown.
        self.assertEqual(self.judge("MIT", "application", "TEXT-TABS"), ("unknown", "fail"))

    def test_dev_tools_are_not_delivered(self) -> None:
        self.assertEqual(self.judge("GPL-3.0-only", "dev"), ("strong-copyleft", "ok"))
        self.assertEqual(self.judge(None, "dev"), ("unknown", "review"))

    def test_licence_entries_are_valid_cyclonedx(self) -> None:
        self.assertEqual(sbom.licence_entries("MIT"), [{"license": {"id": "MIT"}}])
        self.assertEqual(
            sbom.licence_entries("MIT OR Apache-2.0"), [{"expression": "MIT OR Apache-2.0"}]
        )
        self.assertEqual(
            sbom.licence_entries("LicenseRef-public-domain"),
            [{"expression": "LicenseRef-public-domain"}],
        )
        self.assertEqual(
            sbom.licence_entries("Dual License"), [{"license": {"name": "Dual License"}}]
        )
        self.assertEqual(sbom.licence_entries("NOASSERTION"), [])


class FinalizeTest(unittest.TestCase):
    def syft_bom(self) -> dict:
        return {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "metadata": {
                "component": {"bom-ref": "img", "type": "container", "name": "almi-license"}
            },
            "components": [
                component("django", "BSD-3-Clause"),
                component("psycopg-binary", "LGPL-3.0-only"),
                component("sqlparse", None),
                component(
                    "libstdc++6", None, "deb", "pkg:deb/debian/libstdc%2B%2B6@14.2.0-19?arch=amd64"
                ),
                component(
                    "almi-license-console",
                    "UNLICENSED",
                    "npm",
                    "pkg:npm/almi-license-console@0.0.0",
                ),
                {"type": "file", "bom-ref": "file-1", "name": "/usr/lib/x.so"},
            ],
            "dependencies": [{"ref": "ref-django", "dependsOn": ["file-1"]}],
        }

    def finalize(self, root: Path, *extra: str) -> tuple[int, dict, str]:
        source = root / "syft.json"
        source.write_text(json.dumps(self.syft_bom()))
        code, _, err = run(
            "--timestamp",
            TIME,
            "finalize",
            "--in",
            str(source),
            "--out",
            str(root / "out.json"),
            "--name",
            "almi-license",
            "--version",
            "1.0.0",
            "--kind",
            "application",
            "--own",
            "almi-license-console",
            *extra,
        )
        return code, json.loads((root / "out.json").read_text()), err

    def test_files_and_own_packages_are_dropped_and_licences_concluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, bom, _ = self.finalize(Path(tmp))
            self.assertEqual(code, 0)
            by_name = {c["name"]: c for c in bom["components"]}
            self.assertEqual(
                sorted(by_name), ["django", "libstdc++6", "psycopg-binary", "sqlparse"]
            )
            self.assertEqual(bom["dependencies"], [{"ref": "ref-django", "dependsOn": []}])
            self.assertEqual(sbom.licences_of(by_name["sqlparse"]), ["BSD-3-Clause"])
            self.assertEqual(
                sbom.licences_of(by_name["libstdc++6"]), ["GPL-3.0-or-later WITH GCC-exception-3.1"]
            )
            self.assertEqual(sbom.prop(by_name["django"], sbom.KIND), "application")
            self.assertEqual(sbom.prop(by_name["libstdc++6"], sbom.KIND), "os")
            root = bom["metadata"]["component"]
            self.assertEqual((root["name"], root["version"]), ("almi-license", "1.0.0"))
            self.assertTrue(bom["serialNumber"].startswith("urn:uuid:"))

    def test_libraries_of_wheels_are_added_and_checked(self) -> None:
        bom = self.syft_bom()
        vendored = {
            "$comment": "ignored",
            "psycopg-binary": {
                "version": "1.0",
                "libraries": [
                    {
                        "id": "libpq",
                        "name": "libpq",
                        "version": "18.0.6",
                        "license": "PostgreSQL",
                        "files": ["psycopg_binary.libs/libpq", "psycopg_binary.libs/libpq5"],
                    },
                    {
                        "id": "openssl",
                        "name": "OpenSSL",
                        "license": "Apache-2.0",
                        "linkage": "static",
                    },
                ],
            },
        }
        problems = sbom.add_vendored(
            bom,
            vendored,
            [
                "psycopg_binary.libs/libpq-e9b5c9ac.so.5.18",
                "psycopg_binary.libs/libssl-8bd944e8.so.3",
            ],
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("libssl-8bd944e8.so.3", problems[0])
        libpq = next(c for c in bom["components"] if c["name"] == "libpq")
        self.assertEqual(libpq["version"], "18.0.6")
        self.assertEqual(sbom.prop(libpq, "almi:vendored-in"), "psycopg-binary 1.0")
        self.assertEqual(
            sbom.prop(libpq, "almi:files"), "psycopg_binary.libs/libpq, psycopg_binary.libs/libpq5"
        )
        self.assertEqual(sbom.component_kind(libpq, "application"), "application")
        self.assertIn(
            {
                "ref": "ref-psycopg-binary",
                "dependsOn": ["vendored:psycopg-binary/libpq", "vendored:psycopg-binary/openssl"],
            },
            bom["dependencies"],
        )

    def test_a_new_version_of_a_wheel_asks_to_check_its_libraries(self) -> None:
        bom = self.syft_bom()
        problems = sbom.add_vendored(bom, {"django": {"version": "0.9", "libraries": []}}, None)
        self.assertEqual(len(problems), 1)
        self.assertIn("django 1.0 differs from vendored.json (0.9)", problems[0])

    def test_the_dev_sbom_leaves_out_what_is_delivered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            delivered = root / "delivered.json"
            delivered.write_text(json.dumps({"components": [component("django", "BSD-3-Clause")]}))
            code, bom, _ = self.finalize(root, "--exclude-from", str(delivered))
            self.assertEqual(code, 0)
            self.assertNotIn("django", [c["name"] for c in bom["components"]])

    def test_vendored_json_of_the_repository_is_consistent(self) -> None:
        data = json.loads(POLICY.with_name("vendored.json").read_text())
        policy = sbom.Policy(json.loads(POLICY.read_text()))
        for distribution, entry in data.items():
            if distribution.startswith("$"):
                continue
            for lib in entry["libraries"]:
                with self.subTest(distribution=distribution, library=lib["id"]):
                    self.assertNotEqual(policy.category(lib["license"]), "unknown")
                    self.assertTrue(lib.get("files") or lib.get("linkage") == "static")


class ReportTest(unittest.TestCase):
    def test_report_and_csv_with_verdicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bom = sbom.new_bom("almi-license", "1.0.0", "application")
            bom["components"] = [
                component("django", "BSD-3-Clause"),
                component("psycopg", "LGPL-3.0-only"),
            ]
            for c in bom["components"]:
                sbom.set_prop(c, sbom.KIND, "application")
            path = root / "a.cdx.json"
            path.write_text(json.dumps(bom))
            code, out, _ = run(
                "report",
                str(path),
                "--out",
                str(root / "r.md"),
                "--csv",
                str(root / "r.csv"),
                "--meta",
                "Версия=1.0.0",
            )
            self.assertEqual(code, 0, out)
            report = (root / "r.md").read_text()
            self.assertIn("- Версия: 1.0.0", report)
            self.assertIn("| almi-license | `a.cdx.json` | 2 | 1 | 1 | 0 | 0 |", report)
            self.assertIn(
                "| almi-license | psycopg | 1.0 | в составе приложения | LGPL-3.0-only "
                "| слабый копилефт |",
                report,
            )
            with (root / "r.csv").open(encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(
                [(r["name"], r["verdict"]) for r in rows],
                [("django", "ok"), ("psycopg", "obligation")],
            )


if __name__ == "__main__":
    unittest.main()
