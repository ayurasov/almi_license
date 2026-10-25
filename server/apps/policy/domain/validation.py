"""Rules of a policy profile (section 6.4 of document 2, table 8.2 of document 1; E01-03).

Returns field errors in Russian for the console; an empty dict means the profile is valid.
"""

import re
from typing import Any

ENFORCEMENT = ("enforce", "monitor")
EXPIRY_ACTIONS = ("none", "restrict", "block")
HARD_BLOCK_MODES = ("read_only", "no_start")
MESSAGE_FIELDS = {"state", "severity", "placement", "text", "action", "repeat"}
SEVERITIES = ("info", "warning", "critical")
PLACEMENTS = ("banner", "dialog", "about", "tray")
REPEATS = ("once", "daily", "each_start")
STATES = ("TRIAL", "UNLICENSED", "ACTIVE", "NOTICE", "GRACE", "RESTRICTED", "BLOCKED", "REVOKED")
# Section 9 of document 2 plus the ones the default texts of document 5 use; the product fills them.
SUBSTITUTIONS = frozenset(
    {"days_left", "valid_until", "customer", "used", "limit", "product", "support_contact"}
)
PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
# name: (minimum, maximum, nullable)
RANGES: dict[str, tuple[int, int, bool]] = {
    "notify_before_days": (0, 365, False),
    "grace_days": (0, 365, False),
    "restricted_days": (0, 365, True),
    "offline_grace_days": (1, 3650, True),
    "check_interval_hours": (1, 168, False),
    "release_after_days": (7, 365, False),
    "reserve_pct": (0, 100, False),
}


def _messages(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["Ожидается объект «id сообщения → поля»."]
    errors = []
    for key, message in value.items():
        if not isinstance(message, dict) or set(message) - MESSAGE_FIELDS:
            errors.append(f"{key}: допустимы поля {', '.join(sorted(MESSAGE_FIELDS))}.")
            continue
        text = message.get("text", {})
        if not isinstance(text, dict) or not all(isinstance(t, str) for t in text.values()):
            errors.append(f"{key}: text — тексты по языкам.")
            continue
        unknown = {name for t in text.values() for name in PLACEHOLDER.findall(t)} - SUBSTITUTIONS
        if unknown:
            errors.append(f"{key}: неизвестные подстановки {', '.join(sorted(unknown))}.")
        if "state" in message and message["state"] not in STATES:
            errors.append(f"{key}: state — одно из {', '.join(STATES)}.")
        for field, allowed in (
            ("severity", SEVERITIES),
            ("placement", PLACEMENTS),
            ("repeat", REPEATS),
        ):
            if field in message and message[field] not in allowed:
                errors.append(f"{key}: {field} — одно из {', '.join(allowed)}.")
    return errors


def profile_errors(params: dict[str, Any]) -> dict[str, list[str]]:
    errors: dict[str, list[str]] = {}

    def add(field: str, message: str) -> None:
        errors.setdefault(field, []).append(message)

    for field, allowed in (
        ("enforcement", ENFORCEMENT),
        ("expiry_action", EXPIRY_ACTIONS),
        ("hard_block_mode", HARD_BLOCK_MODES),
    ):
        if params.get(field) not in allowed:
            add(field, f"Одно из: {', '.join(allowed)}.")
    for field, (low, high, nullable) in RANGES.items():
        value = params.get(field)
        if value is None and nullable:
            continue
        if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
            suffix = " или пусто" if nullable else ""
            add(field, f"Целое от {low} до {high}{suffix}.")
    for field in ("restricted_caps", "read_only_caps"):
        value = params.get(field, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            add(field, "Список кодов функций.")
    if "messages" in params:
        for message in _messages(params["messages"]):
            add("messages", message)
    if "directives" in params:
        directives = params["directives"]
        if not isinstance(directives, list) or not all(
            isinstance(d, dict) and isinstance(d.get("id"), str) and isinstance(d.get("type"), str)
            for d in directives
        ):
            add("directives", "Список объектов с id и type.")
    return errors
