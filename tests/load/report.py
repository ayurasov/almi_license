"""Markdown report of a load run (E16-05) from the k6 summaries, /metrics and top queries."""

import json
import sys
from pathlib import Path

out, active, expected = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
lines = ["# Отчёт нагрузки этапа 1", ""]
lines += [
    "| Сценарий | Запросов | p95, мс | p99, мс | Ошибки | Цель |",
    "|---|---|---|---|---|---|",
]
targets = {
    "check": "p95 < 500 мс, ошибки < 0,1 %",
    "activate": "p95 < 500 мс",
    "race": "без двойного списания",
}
for name in ("check", "activate", "race"):
    path = out / f"{name}-summary.json"
    if not path.exists():
        lines.append(f"| {name} | — | — | — | — | {targets[name]} |")
        continue
    metrics = json.loads(path.read_text())["metrics"]
    duration = metrics["http_req_duration"]
    failed = metrics.get("http_req_failed", {}).get("value", 0)
    count = metrics["http_reqs"]["count"]
    lines.append(
        f"| {name} | {count} | {duration['p(95)']:.0f} | {duration['p(99)']:.0f} | "
        f"{failed * 100:.3f} % | {targets[name]} |"
    )
lines += [
    "",
    f"Гонка: активных активаций у лицензии с limit = 100 — {active} (ожидается {expected}).",
    "",
]
top = out / "top-queries.txt"
if top.exists():
    lines += ["## Топ-10 запросов БД по времени", "", "```", top.read_text().strip(), "```", ""]
print("\n".join(lines))
