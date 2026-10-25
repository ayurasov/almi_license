"""Line coverage of the DL module from gcov (E13-12), without extra tools.

Usage: python3 tools/dl_coverage.py <build dir> [--min 90] [file ...]
Runs gcov in JSON mode over the object files of lm_internal and prints the covered share of the
executable lines of each source file; exits 1 when a listed file is under --min percent.
"""

import argparse
import gzip
import json
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_FILES = [
    "src/crypto/lease_verifier.cpp",
    "src/policy/state_evaluator.cpp",
    "src/state/trial_tracker.cpp",
]


def coverage(build: Path, source_root: Path) -> dict[str, tuple[int, int]]:
    """{relative source path: (covered lines, executable lines)} over all .gcda of the build."""
    result: dict[str, set[int]] = {}
    lines: dict[str, set[int]] = {}
    gcda = sorted(build.rglob("*.gcda"))
    with tempfile.TemporaryDirectory() as out:
        for data in gcda:
            subprocess.run(
                ["gcov", "--json-format", "--preserve-paths", str(data)],
                cwd=out,
                check=True,
                capture_output=True,
            )
        for report in Path(out).glob("*.gcov.json.gz"):
            document = json.loads(gzip.decompress(report.read_bytes()))
            for item in document.get("files", []):
                path = Path(item["file"])
                if not path.is_absolute():
                    path = (Path(document.get("current_working_directory", build)) / path).resolve()
                try:
                    name = str(path.resolve().relative_to(source_root))
                except ValueError:
                    continue
                for line in item.get("lines", []):
                    lines.setdefault(name, set()).add(line["line_number"])
                    if line["count"] > 0:
                        result.setdefault(name, set()).add(line["line_number"])
    return {name: (len(result.get(name, set())), len(numbers)) for name, numbers in lines.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("build", type=Path)
    parser.add_argument("files", nargs="*", default=DEFAULT_FILES)
    parser.add_argument("--min", type=float, default=90.0)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1] / "sdk/cpp")
    args = parser.parse_args()
    table = coverage(args.build.resolve(), args.root.resolve())
    failed = False
    for name in args.files:
        covered, total = table.get(name, (0, 0))
        share = 100.0 * covered / total if total else 0.0
        mark = "ok  " if share >= args.min else "FAIL"
        failed |= share < args.min
        print(f"{mark} {share:5.1f} %  {covered:4d}/{total:<4d} {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
