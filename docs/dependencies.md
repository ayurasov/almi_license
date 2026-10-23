# Реестр зависимостей

Каждая зависимость добавляется только после согласования с техническим лидером (`AGENTS.md`, раздел «Стек и версии»).
Версии фиксируются точно (`==`) в манифесте; транзитивные — в lock-файле (`server/uv.lock`).
Новая строка добавляется в том же запросе на слияние, что и зависимость.

## Сервер (`server/pyproject.toml`)

### Выполнение

| Пакет | Версия | Назначение | Добавлена | Согласовано |
|---|---|---|---|---|
| django | 5.2.18 | Фреймворк сервера (5.2 LTS) | I0-02 | Стек `AGENTS.md` |
| djangorestframework | 3.16.1 | REST API | I0-02 | Стек `AGENTS.md` (3.16 подтверждена 23.10.2026, примечание 1) |
| drf-spectacular | 0.30.0 | Генерация OpenAPI для сверки с `contracts/` | I0-02 | Стек `AGENTS.md` |
| psycopg[binary] | 3.3.6 | Драйвер PostgreSQL 17 | I0-02 | Стек `AGENTS.md` |
| django-environ | 0.14.0 | Настройки только из переменных окружения | I0-02 | Промпт I0-02 |

### Разработка и CI (группа `dev`)

| Пакет | Версия | Назначение | Добавлена | Согласовано |
|---|---|---|---|---|
| pytest | 9.1.1 | Тесты | I0-02 | Стек `AGENTS.md` |
| pytest-django | 4.14.0 | Интеграция pytest и Django | I0-02 | Промпт I0-02 |
| pytest-cov | 7.1.0 | Покрытие и пороги (раздел 6.2 документа 7) | I0-02 | Документ 7 |
| ruff | 0.17.2 | Линтер и форматирование | I0-02 | Документ 6, раздел 4.1 |
| mypy | 1.19.1 | Проверка типов (`--strict` для `domain/` и `infra/`) | I0-02 | Документ 6, раздел 4.1; 1.19 — последняя версия, совместимая с django-stubs 5.2 |
| django-stubs[compatible-mypy] | 5.2.9 | Типы Django для mypy | I0-02 | Документ 6, раздел 4.1 |
| djangorestframework-stubs | 3.16.9 | Типы DRF для mypy | I0-02 | Документ 6, раздел 4.1 |
| import-linter | 2.15 | Модульные границы (правило 3 `AGENTS.md`) | I0-02 | `AGENTS.md`, документ 7 |

Запланированы стеком, будут добавлены вместе с первым использованием: `cryptography` (E02-02), `hypothesis`, `factory-boy` (I1-03 и далее).

## Модуль DL (`sdk/cpp/vcpkg.json`)

Версии фиксирует `builtin-baseline` vcpkg `23b8a8e7409c2d6346114a88e834165bde79a51c` (23.10.2026); сборка статическая (`x64-linux`, `x64-windows-static`).

| Пакет | Версия | Назначение | Добавлен | Согласовано |
|---|---|---|---|---|
| libsodium | 1.0.22 | Ed25519, обнуление секретов (`sodium_memzero`) | I0-04 | Стек `AGENTS.md` |
| curl[ssl] | 8.23.0 | HTTPS-транспорт; TLS — OpenSSL 3.6.5 (Linux), Schannel (Windows) | I0-04 | Стек `AGENTS.md` |
| nlohmann-json | 3.12.0 | JSON | I0-04 | Стек `AGENTS.md` |
| gtest | 1.18.0 | Тесты (`lm_tests`) | I0-04 | Стек `AGENTS.md` |

## Образы и инструменты CI (не входят в `uv.lock`)

| Компонент | Версия | Где | Назначение | Добавлен |
|---|---|---|---|---|
| python | 3.13-slim | `deploy/Dockerfile` | Базовый образ (раздел 7.1 документа 7) | I0-03 |
| ghcr.io/astral-sh/uv | 0.11.32 | `deploy/Dockerfile`, CI | Установка зависимостей по `uv.lock` | I0-03 |
| postgres | 17 | `deploy/dev`, CI | БД | I0-03 |
| nginx | 1.27 | `deploy/dev` | Шлюз | I0-03 |
| node | 22 | `deploy/dev`, CI | Консоль | I0-03 |
| gitleaks | 8.30.1 (sha256 в `ci.yml`) | CI, pre-commit | Поиск секретов | I0-01, I0-03 |
| openapi-spec-validator | 0.9.0 | `make contract-check` (`uvx`) | Валидность `contracts/openapi-product-api-v1.yaml` | I0-03 |
| jsonschema | 4.26.0 | `tools/contract_check.py` (uv-скрипт, `tools/contract_check.py.lock`) | Проверка JSON Schema 2020-12, примеров и примеров документа 2 | I1-01 |
| pyyaml | 6.0.3 | `tools/contract_check.py` | Чтение OpenAPI для сверки схем | I1-01 |
| pynacl | 1.6.2 | `tools/vectors/generate.py` (uv-скрипт, `generate.py.lock`) | Ed25519 для эталонных векторов, независимо от `cryptography` сервера (промпт I1-02) | I1-02 |
| actions/checkout, actions/setup-node | v7 | CI | | I0-03 |
| actions/cache | v6 | CI | Кэш бинарных пакетов vcpkg | I0-04 |
| actions/upload-artifact | v7 | CI | `license_module.dll`, `liblicense_module.so`, заголовок, `lm-demo` | I0-04 |
| vcpkg | коммит `builtin-baseline` | CI, локально (`VCPKG_ROOT`) | Зависимости DL | I0-04 |
| clang-format | 23.1.3 | pre-commit, `make lint-dl` (`uvx`) | Форматирование C++ | I0-01, I0-04 |
| clang-tidy | 18 (раннер ubuntu-24.04) | `make lint-dl` | Анализ C++ | I0-04 |
| astral-sh/setup-uv | v10.3.2 | CI | Плавающих тегов после v7 нет | I0-03 |

## Примечания

1. DRF 3.15.2 официально поддерживает Django до 5.0 и Python до 3.12. Стек требует Python 3.13 и Django 5.2, официальная поддержка которых появилась в DRF 3.16. Выбрана 3.16.1; подтверждено руководителем проекта 23.10.2026, строка стека в `AGENTS.md` исправлена (в разделе 3 документа 6 пока «3.15»).
