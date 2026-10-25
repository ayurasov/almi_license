"""Prometheus metrics of the process in the text exposition format 0.0.4 (E15-05).

No client library: counters and histograms of one process, rendered by render(). Labels are
bounded by the caller (route patterns, not paths), so the number of series stays small.
"""

import threading
from collections.abc import Iterable
from dataclasses import dataclass, field

# Seconds; the last bucket is +Inf.
BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
Labels = tuple[tuple[str, str], ...]


def _labels(labels: Labels, extra: Labels = ()) -> str:
    items = labels + extra
    if not items:
        return ""
    text = ",".join(f'{k}="{_escape(v)}"' for k, v in items)
    return "{" + text + "}"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else repr(value)


@dataclass
class Counter:
    name: str
    help: str
    values: dict[Labels, float] = field(default_factory=dict)

    def inc(self, labels: Labels = (), amount: float = 1) -> None:
        with _lock:
            self.values[labels] = self.values.get(labels, 0) + amount

    def render(self) -> Iterable[str]:
        yield f"# HELP {self.name} {self.help}"
        yield f"# TYPE {self.name} counter"
        for labels, value in sorted(self.values.items()):
            yield f"{self.name}{_labels(labels)} {_number(value)}"


@dataclass
class Histogram:
    name: str
    help: str
    counts: dict[Labels, list[int]] = field(default_factory=dict)
    sums: dict[Labels, float] = field(default_factory=dict)

    def observe(self, value: float, labels: Labels = ()) -> None:
        with _lock:
            counts = self.counts.setdefault(labels, [0] * (len(BUCKETS) + 1))
            for i, bound in enumerate(BUCKETS):
                if value <= bound:
                    counts[i] += 1
            counts[-1] += 1
            self.sums[labels] = self.sums.get(labels, 0.0) + value

    def render(self) -> Iterable[str]:
        yield f"# HELP {self.name} {self.help}"
        yield f"# TYPE {self.name} histogram"
        for labels, counts in sorted(self.counts.items()):
            for bound, count in zip((*map(str, BUCKETS), "+Inf"), counts, strict=True):
                yield f"{self.name}_bucket{_labels(labels, (('le', bound),))} {count}"
            yield f"{self.name}_sum{_labels(labels)} {_number(round(self.sums[labels], 6))}"
            yield f"{self.name}_count{_labels(labels)} {counts[-1]}"


def gauge(name: str, help_text: str, value: float) -> list[str]:
    return [f"# HELP {name} {help_text}", f"# TYPE {name} gauge", f"{name} {_number(value)}"]


_lock = threading.Lock()

REQUESTS = Counter("almi_http_requests_total", "HTTP requests by method, route and status")
ERRORS = Counter("almi_http_errors_total", "HTTP responses with status 5xx by route")
DURATION = Histogram("almi_http_request_duration_seconds", "Duration of HTTP requests by route")


def render(extra: Iterable[str] = ()) -> str:
    lines = [*REQUESTS.render(), *ERRORS.render(), *DURATION.render(), *extra]
    return "\n".join(lines) + "\n"


def reset() -> None:
    """Tests only: forget the values of this process."""
    with _lock:
        REQUESTS.values.clear()
        ERRORS.values.clear()
        DURATION.counts.clear()
        DURATION.sums.clear()
