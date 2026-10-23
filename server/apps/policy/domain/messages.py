"""Messages of the lease and of the response (section 9 of document 2, E04-04 part).

Default texts — section 3.1 of document 5 (АльтерОфис Desktop, class commercial); a profile
overrides fields of a message by id in params["messages"]. The product shows the text as is
and fills the substitutions itself.
"""

from typing import Any

# id -> message without id; "restricted.feature" (a tooltip next to a disabled function) has no
# placement in section 9 of document 2, the DL module shows its built-in text for it.
DEFAULT_MESSAGES: dict[str, dict[str, Any]] = {
    "notice.banner": {
        "state": "NOTICE",
        "severity": "info",
        "placement": "banner",
        "repeat": "daily",
        "text": {
            "ru": "Лицензия действует до {valid_until}. Осталось {days_left}.",
            "en": "License is valid until {valid_until}. {days_left} left.",
        },
    },
    "notice.7days": {
        "state": "NOTICE",
        "severity": "warning",
        "placement": "dialog",
        "repeat": "daily",
        "text": {
            "ru": "Лицензия {product} заканчивается {valid_until}. Обратитесь к администратору "
            "или в {support_contact}, чтобы продлить её.",
            "en": "The {product} license expires on {valid_until}. Contact your administrator "
            "or {support_contact} to renew it.",
        },
    },
    "grace.banner": {
        "state": "GRACE",
        "severity": "warning",
        "placement": "banner",
        "repeat": "each_start",
        "text": {
            "ru": "Срок лицензии истёк {valid_until}. Продукт работает без ограничений ещё "
            "{days_left}.",
            "en": "The license expired on {valid_until}. The product works without limitations "
            "for {days_left} more.",
        },
    },
    "grace.dialog": {
        "state": "GRACE",
        "severity": "warning",
        "placement": "dialog",
        "repeat": "daily",
        "text": {
            "ru": "Срок лицензии истёк. Через {days_left} будут отключены обновления, макросы и "
            "совместная работа. Документы и данные останутся доступны.",
            "en": "The license has expired. In {days_left}, updates, macros and collaboration "
            "will be disabled. Your documents and data remain available.",
        },
    },
    "restricted.banner": {
        "state": "RESTRICTED",
        "severity": "warning",
        "placement": "banner",
        "repeat": "each_start",
        "text": {
            "ru": "Лицензия не продлена. Обновления, макросы и совместная работа отключены. "
            "Документы доступны.",
            "en": "The license has not been renewed. Updates, macros and collaboration are "
            "disabled. Documents are available.",
        },
    },
    "blocked.read_only": {
        "state": "BLOCKED",
        "severity": "critical",
        "placement": "dialog",
        "repeat": "each_start",
        "text": {
            "ru": "Лицензия не действует. Продукт работает в режиме просмотра: документы можно "
            "открыть, распечатать и экспортировать, но не изменить. Для продления обратитесь к "
            "администратору или в {support_contact}.",
            "en": "The license is not valid. The product works in view-only mode: you can open, "
            "print and export documents but not edit them. Contact your administrator or "
            "{support_contact} to renew.",
        },
    },
    "blocked.no_start": {
        "state": "BLOCKED",
        "severity": "critical",
        "placement": "dialog",
        "repeat": "each_start",
        "text": {
            "ru": "Лицензия не действует, продукт не может быть запущен. Ваши документы не "
            "изменены и доступны в других программах. Обратитесь к администратору или в "
            "{support_contact}.",
            "en": "The license is not valid and the product cannot start. Your documents are "
            "unchanged and available in other applications. Contact your administrator or "
            "{support_contact}.",
        },
    },
    "revoked.dialog": {
        "state": "REVOKED",
        "severity": "critical",
        "placement": "dialog",
        "repeat": "each_start",
        "text": {
            "ru": "Лицензия отозвана владельцем. Продукт работает в режиме просмотра. Для "
            "уточнения обратитесь к администратору.",
            "en": "The license has been revoked by its owner. The product works in view-only "
            "mode. Contact your administrator for details.",
        },
    },
}


def _catalog(params: dict[str, Any]) -> dict[str, dict[str, Any]]:
    overrides: dict[str, dict[str, Any]] = params.get("messages", {})
    merged = {key: value | overrides.get(key, {}) for key, value in DEFAULT_MESSAGES.items()}
    for key, value in overrides.items():
        merged.setdefault(key, value)
    return merged


def messages_for(ids: tuple[str, ...], params: dict[str, Any]) -> list[dict[str, Any]]:
    """Messages of the current state, in the order of PolicyResult.message_ids."""
    catalog = _catalog(params)
    return [{"id": key} | catalog[key] for key in ids if key in catalog]


def lease_messages(params: dict[str, Any]) -> list[dict[str, Any]]:
    """All messages by state: the product shows them offline when the state changes."""
    return [{"id": key} | value for key, value in sorted(_catalog(params).items())]
