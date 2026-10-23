"""keytool.log: one JSON line per operation — what, when, which key. Never secrets."""

import json
from datetime import datetime
from pathlib import Path


def record(
    log: Path, at: datetime, command: str, *, kid: str, fingerprint: str, result: str
) -> None:
    entry = {
        "at": at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": command,
        "kid": kid,
        "fingerprint": fingerprint,
        "result": result,
    }
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
