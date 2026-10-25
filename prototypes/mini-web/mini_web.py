#!/usr/bin/env python3
"""mini-web: a prototype of AlterOffice Web (Nextcloud) for manual tests of the licensing server.

It talks to the server the way the Nextcloud app "support" does (section 11.1 of document 2):

    POST {support.backend}/apps/zammad_organisation_management/api/query/subscription/{key}
    {"instanceId", "userCount", "activeUserCount", "apps", "version"}
    -> {"endDate", "extendedSupport", "amountOfUsers", "onlyCountActiveUsers", "accountManagerInfo"}

and shows what the product does with the answer: the end date, the user limit, warnings. Stage 1
only warns (the soft and hard blocks of the web version are notifications); --enforce shows the
behaviour to carry into the product later: no new users above the limit, read-only after the end.

    python3 mini_web.py [--port 8088] [--state mini-web.json] [--cafile CA.pem] [--enforce]

Only the standard library of Python 3.12 (Ubuntu 24.04). The state (users, settings, the last
answer) is a JSON file; the subscription key is kept there as in Nextcloud config, never logged.
"""

import argparse
import html
import json
import secrets
import ssl
import string
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

VERSION = "28.0.4.1"  # the Nextcloud version the prototype reports
APPS = {"files": "2.0.0", "calendar": "4.6.5", "contacts": "5.5.3", "mail": "3.6.1", "spreed": "18.0.7"}
SUBSCRIPTION_PATH = "/apps/zammad_organisation_management/api/query/subscription/"
WARN_DAYS = 30


def new_instance_id() -> str:
    """Nextcloud instanceid: 12 characters [a-z0-9], made once at installation."""
    alphabet = string.ascii_lowercase + string.digits
    return "oc" + "".join(secrets.choice(alphabet) for _ in range(10))


class State:
    def __init__(self, path: Path) -> None:
        self.path = path
        if path.exists():
            self.data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        else:
            self.data = {
                "instance_id": new_instance_id(),
                "backend": "",
                "key": "",
                "users": {"admin": {"active": True}},
                "subscription": None,
                "checked_at": None,
                "error": None,
            }
            self.save()

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.path.chmod(0o600)  # the subscription key is a secret of the customer


def check_subscription(state: State, cafile: str | None) -> None:
    """The request of the app support; the answer replaces the stored subscription."""
    data = state.data
    if not data["backend"] or not data["key"]:
        data["error"] = "Не задан адрес сервера или ключ подписки."
        state.save()
        return
    users = data["users"]
    body = {
        "instanceId": data["instance_id"],
        "userCount": len(users),
        "activeUserCount": sum(1 for u in users.values() if u["active"]),
        "apps": APPS,
        "version": VERSION,
    }
    url = data["backend"].rstrip("/") + SUBSCRIPTION_PATH + urllib.parse.quote(data["key"], safe="")
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": f"Nextcloud/{VERSION} mini-web"},
        method="POST",
    )
    context = ssl.create_default_context(cafile=cafile)
    try:
        with urllib.request.urlopen(request, timeout=15, context=context) as reply:
            data["subscription"] = json.loads(reply.read(64 * 1024))
            data["error"] = None
    except urllib.error.HTTPError as error:
        # 404: the key is unknown or revoked; the app shows "no subscription" (fixtures E00-09).
        messages = {404: "Подписка не найдена.", 429: "Слишком много запросов, повторите позже."}
        data["error"] = messages.get(error.code, f"Сервер ответил {error.code}.")
        if error.code == 404:
            data["subscription"] = None
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        # No connection: the last answer stays in force, as in the app.
        data["error"] = f"Нет связи с сервером лицензирования: {getattr(error, 'reason', error)}"
    data["checked_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    state.save()


def evaluate(data: dict[str, Any], today: date) -> dict[str, Any]:
    """What the product concludes from the stored answer (the logic to port)."""
    sub = data["subscription"]
    users = data["users"]
    if sub is None:
        return {"licensed": False, "warnings": ["Подписка не активна."], "over_limit": False, "expired": True}
    end = date.fromisoformat(sub["endDate"]) if sub.get("endDate") else None
    counted = sum(1 for u in users.values() if u["active"]) if sub["onlyCountActiveUsers"] else len(users)
    limit = sub["amountOfUsers"]
    warnings = []
    expired = end is not None and today > end
    if end is not None and expired:
        warnings.append(f"Подписка закончилась {end:%d.%m.%Y}. Продлите подписку.")
    elif end is not None and (end - today).days <= WARN_DAYS:
        warnings.append(f"Подписка заканчивается {end:%d.%m.%Y}: осталось дней {(end - today).days}.")
    over = limit is not None and counted > limit
    if over:
        warnings.append(f"Пользователей {counted} при лимите {limit}: обратитесь к менеджеру.")
    if not sub["extendedSupport"]:
        warnings.append("Расширенная поддержка не действует.")
    return {
        "licensed": True,
        "warnings": warnings,
        "over_limit": over,
        "at_limit": limit is not None and counted >= limit,
        "expired": expired,
        "counted": counted,
        "limit": limit,
        "end": end,
    }


PAGE = """<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"><title>mini-web</title>
<style>body{{font-family:sans-serif;max-width:900px;margin:2em auto}}.warn{{background:#fff3cd;padding:.5em;margin:.3em 0}}
.err{{background:#f8d7da;padding:.5em}}table{{border-collapse:collapse}}td,th{{border:1px solid #ccc;padding:.3em .6em}}</style>
</head><body><h1>mini-web <small>(аналог АльтерОфис Web, Nextcloud {version})</small></h1>
{banners}
<h2>Пользователи</h2><table><tr><th>Логин</th><th>Активен</th><th></th></tr>{rows}</table>
<form method="post" action="/users/add"><input name="name" placeholder="логин" required> <button {add_disabled}>Добавить</button></form>
<h2>Документы</h2><form method="post" action="/edit"><button {edit_disabled}>Создать документ</button></form>{edit_note}
<h2>Поддержка (настройка подписки)</h2>
<form method="post" action="/support"><p>support.backend: <input name="backend" size="40" value="{backend}"></p>
<p>Ключ подписки: <input name="key" size="40" value="{key_mask}" placeholder="ключ"></p><button>Сохранить и проверить</button></form>
<form method="post" action="/check"><button>Проверить сейчас</button></form>
<h3>Ответ сервера</h3><pre>{answer}</pre><p>Проверено: {checked}. instanceId: <code>{instance}</code></p>
<p>Режим: {mode}</p></body></html>"""


def render(state: State, enforce: bool, notice: str = "") -> str:
    data = state.data
    result = evaluate(data, datetime.now(UTC).date())
    banners = "".join(f'<div class="warn">{html.escape(w)}</div>' for w in result["warnings"])
    if data["error"]:
        banners += f'<div class="err">{html.escape(data["error"])}</div>'
    if notice:
        banners += f'<div class="err">{html.escape(notice)}</div>'
    rows = "".join(
        f"<tr><td>{html.escape(name)}</td><td>{'да' if u['active'] else 'нет'}</td>"
        f"<td>{button('/users/toggle', name, 'вкл/выкл')} {button('/users/delete', name, 'удалить')}</td></tr>"
        for name, u in data["users"].items()
    )
    blocked_add = enforce and (not result["licensed"] or result.get("at_limit", False))
    blocked_edit = enforce and result["expired"]
    sub = data["subscription"]
    return PAGE.format(
        version=VERSION,
        banners=banners,
        rows=rows,
        add_disabled="disabled" if blocked_add else "",
        edit_disabled="disabled" if blocked_edit else "",
        edit_note="<p>Только чтение: подписка закончилась.</p>" if blocked_edit else "",
        backend=html.escape(data["backend"]),
        key_mask=html.escape(mask(data["key"])),
        answer=html.escape(json.dumps(sub, ensure_ascii=False, indent=2)) if sub else "нет",
        checked=html.escape(data["checked_at"] or "ещё не проверялось"),
        instance=html.escape(data["instance_id"]),
        mode="ограничения включены (--enforce)" if enforce else "этап 1: только уведомления",
    )


def button(action: str, name: str, label: str) -> str:
    value = html.escape(name)
    return (
        f'<form method="post" action="{action}" style="display:inline">'
        f'<input type="hidden" name="name" value="{value}"><button>{label}</button></form>'
    )


def mask(key: str) -> str:
    return f"…{key[-4:]}" if key else ""


def make_handler(state: State, cafile: str | None, enforce: bool) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            # The path carries no secrets here; the key goes only in the body of /support.
            sys.stderr.write(f"{self.command} {self.path.split('?')[0]}\n")

        def do_GET(self) -> None:
            self._page(render(state, enforce))

        def do_POST(self) -> None:
            length = min(int(self.headers.get("Content-Length") or 0), 16 * 1024)
            form = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(length).decode()).items()}
            users = state.data["users"]
            name = form.get("name", "").strip()[:64]
            notice = ""
            result = evaluate(state.data, datetime.now(UTC).date())
            if self.path == "/users/add" and name:
                if enforce and (not result["licensed"] or result.get("at_limit", False)):
                    notice = "Новые пользователи недоступны: достигнут лимит подписки."
                else:
                    users.setdefault(name, {"active": True})
            elif self.path == "/users/toggle" and name in users:
                users[name]["active"] = not users[name]["active"]
            elif self.path == "/users/delete" and name in users and name != "admin":
                del users[name]
            elif self.path == "/edit":
                if enforce and result["expired"]:
                    notice = "Редактирование недоступно: подписка закончилась."
                else:
                    notice = "Документ создан."
            elif self.path == "/support":
                state.data["backend"] = form.get("backend", "").strip()
                key = form.get("key", "").strip()
                if key and not key.startswith("…"):
                    state.data["key"] = key
                check_subscription(state, cafile)
            elif self.path == "/check":
                check_subscription(state, cafile)
            state.save()
            self._page(render(state, enforce, notice))

        def _page(self, body: str) -> None:
            payload = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", type=int, default=8088)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--state", type=Path, default=Path("mini-web.json"))
    parser.add_argument("--cafile", help="CA of a test server with a self-signed certificate")
    parser.add_argument("--enforce", action="store_true", help="limits instead of warnings only")
    parser.add_argument("--check", action="store_true", help="one check, print the result, exit (cron)")
    args = parser.parse_args()
    state = State(args.state)
    if args.check:
        check_subscription(state, args.cafile)
        result = evaluate(state.data, datetime.now(UTC).date())
        print(json.dumps({"error": state.data["error"], **result}, ensure_ascii=False, default=str))
        sys.exit(0 if result["licensed"] and not state.data["error"] else 1)
    server = ThreadingHTTPServer((args.bind, args.port), make_handler(state, args.cafile, args.enforce))
    print(f"mini-web: http://{args.bind}:{args.port}/ (state {args.state})")
    server.serve_forever()


if __name__ == "__main__":
    main()
