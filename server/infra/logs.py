"""JSON log lines on stdout (E15-05; section 11 of document 7).

One object per line: time (UTC), level, logger, message, and the exception type when there is
one. Messages are written by the code, which never logs keys, leases, signatures or passwords
(AGENTS.md, rule 9); the formatter adds nothing from the request.
"""

import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            # The type only: the text of an exception may hold data from the request.
            line["exception"] = record.exc_info[0].__name__
        return json.dumps(line, ensure_ascii=False)
