# I0-02. Каркас сервера

```text
Создай Django-проект в server/ по разделам 13 и 14 docs/specs/01-architecture.md.

Требования:
- Python 3.13, Django 5.2, DRF, drf-spectacular, psycopg 3; управление зависимостями — uv, файл server/pyproject.toml с зафиксированными версиями;
- settings разделены: base, dev, ci, prod; конфигурация только из переменных окружения (django-environ); DEPLOYMENT_MODE = central | local, проверка значения при старте;
- пустые приложения apps/: catalog, licensing, activation, policy, packages, signing, stats, audit, iam, outbox, api_product, api_admin, api_sync, compat; в каждом domain/__init__.py, models.py, api/, tests/;
- infra/clock.py: протокол Clock с методом now() -> datetime (UTC, aware); SystemClock; FrozenClock для тестов;
- infra/crypto/provider.py: протокол CryptoProvider (sign, verify, public_key, kid) без реализации;
- конфигурация import-linter: модуль может импортировать из другого модуля только <модуль>.domain; api_* не импортируются никем;
- конфигурация ruff (правила из раздела 4.1 docs/specs/06-ai-rules.md), mypy strict для domain и infra;
- один тест на SystemClock и FrozenClock;
- /health и /ready (ready проверяет соединение с БД).
Коммиты по шагам: chore(server): project skeleton; feat(infra): clock; chore(server): lint and import rules.
```
