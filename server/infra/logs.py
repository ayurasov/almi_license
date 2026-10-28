"""JSON log lines on stdout (E15-05; section 11 of document 7).

One object per line: time (UTC), level, logger, message, and the exception type when there is
one. Messages are written by the code, which never logs keys, leases, signatures or passwords
(AGENTS.md, rule 9); the formatter adds nothing from the request.
"""

import json
import logging
import re
from datetime import UTC, datetime

# Licence keys that reach a log line through a URL (AGENTS.md, rule 9): the key of the Nextcloud
# adapter is a path segment, the key of /api/activate/ the lic parameter; any key of the format
# WWyy-XXXX-XXXX-XXXX is masked wherever it appears.
_KEYS = (
    (re.compile(r"(/subscription/)[^/?\s\"']+"), r"\1***"),
    (re.compile(r"([?&]lic=)[^&\s\"']*"), r"\1***"),
    (re.compile(r"\b\d{4}-[0-9A-Za-z]{4}-[0-9A-Za-z]{4}-[0-9A-Za-z]{4}\b"), "***"),
)


def redact(text: str) -> str:
    for pattern, replacement in _KEYS:
        text = pattern.sub(replacement, text)
    return text


class RedactKeys(logging.Filter):
    """Masks licence keys in the message of every record it sees (Django and uvicorn loggers)."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        masked = redact(message)
        if masked != message:
            record.msg, record.args = masked, None
        return True


def install_key_filter(*names: str) -> None:
    """Adds RedactKeys to loggers that write without the LOGGING handlers (gunicorn access)."""
    for name in names:
        logger = logging.getLogger(name)
        if not any(isinstance(f, RedactKeys) for f in logger.filters):
            logger.addFilter(RedactKeys())


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
