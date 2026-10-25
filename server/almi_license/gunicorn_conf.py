"""Gunicorn settings of the image (deploy/entrypoint.sh): metrics of a stopped worker are kept
in PROMETHEUS_MULTIPROC_DIR only for counters; its live gauges are dropped (question 42)."""

from typing import Any

from prometheus_client import multiprocess


def child_exit(server: Any, worker: Any) -> None:
    multiprocess.mark_process_dead(worker.pid)
