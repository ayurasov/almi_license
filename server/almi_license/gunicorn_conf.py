"""Gunicorn settings of the image (deploy/entrypoint.sh): metrics of a stopped worker are kept
in PROMETHEUS_MULTIPROC_DIR only for counters; its live gauges are dropped (question 42). The
access log of the workers masks licence keys of URLs (AGENTS.md, rule 9)."""

from typing import Any

from prometheus_client import multiprocess

from infra.logs import install_key_filter


def post_worker_init(worker: Any) -> None:
    install_key_filter("uvicorn.access", "uvicorn.error")


def child_exit(server: Any, worker: Any) -> None:
    multiprocess.mark_process_dead(worker.pid)
