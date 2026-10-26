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
| cryptography | 50.0.2 | Ed25519 ключа выпуска (`infra/crypto/ed25519.py`); тянет `cffi` 2.1.1, `pycparser` 3.12 | I2-01 | Стек документа 1, раздел 13; промпт I2-01 |
| openpyxl | 3.1.5 | Разбор XLSX-выгрузки ЛК в режиме `read_only` (E06-01); тянет `et-xmlfile` 2.0.0 | I2-06 | Промпт I2-06 |
| argon2-cffi | 25.1.0 | Argon2id для паролей консоли (`PASSWORD_HASHERS`, E07-02); тянет `argon2-cffi-bindings` 26.1.0 | I2-07 | Критерий E07-02 документа 3 |
| django-environ | 0.14.0 | Настройки только из переменных окружения | I0-02 | Промпт I0-02 |
| gunicorn | 26.2.0 | Процесс-менеджер `api` образа (`deploy/entrypoint.sh`) | I4 (E15-04) | Документ 7, раздел 7.1: «Gunicorn + Uvicorn workers» |
| uvicorn, uvicorn-worker | 0.54.0, 0.4.0 | ASGI-сервер и рабочий класс Gunicorn; тянут `click` 8.5.0, `h11` 0.16.0 | I4 (E15-04) | Документ 7, раздел 7.1 |
| prometheus-client | 0.26.0 | Метрики `/metrics` с суммированием по рабочим процессам Gunicorn (`PROMETHEUS_MULTIPROC_DIR`); без зависимостей | v0.4.2 (вопрос 42) | Ответ руководителя проекта 25.10.2026: вариант multiprocess |
| captcha, pillow | 0.7.1, 12.3.0 | Капча портала офлайн-активации: изображение PNG локальной библиотекой, без внешнего сервиса (работает в изолированном контуре); Pillow 13.0.0 моложе двух недель | v0.4.2 (вопрос 45) | Ответ руководителя проекта 25.10.2026: «нужна, локальная библиотека» |
| psycopg-pool | 3.3.3 | Пул соединений Django (`DATABASES.OPTIONS.pool`): под ASGI число соединений ограничено на процесс, запросы ждут свободное (E16-05); официальный спутник psycopg 3 | v0.5.0 (E16-05) | Согласовано руководителем проекта 25.10.2026 (найдено нагрузкой: 200 одновременных активаций превысили `max_connections`) |
| croniter | 6.2.4 | Cron-выражения расписания задач (E12-01); тянет `python-dateutil` 2.9.0.post0 (ограничение `constraint-dependencies`: 3.0.0 моложе двух недель) и `six` 1.17.0 | I4-03 | Промпт I4-03 |

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
| hypothesis | 6.170.8 | Property-тесты `PolicyEngine` (E04-02) | I2-02 | Стек `AGENTS.md`; промпт I2-02 |
| jsonschema | 4.26.0 | Контрактные тесты API: ответы по OpenAPI, аренда по `contracts/schemas` (`server/tests/contract.py`) | I2-05 | Уже согласован для `tools/contract_check.py` (I1-01) |
| types-croniter | 6.2.4.20261006 | Типы croniter для mypy | I4-03 | Промпт I4-03 |
| types-openpyxl | 3.1.5.20260827 | Типы openpyxl для mypy | I2-06 | Выпуск старше двух недель (20261017 — слишком свежий) |
| import-linter | 2.15 | Модульные границы (правило 3 `AGENTS.md`) | I0-02 | `AGENTS.md`, документ 7 |

Запланированы стеком, будут добавлены вместе с первым использованием: `factory-boy`.

## almi-keytool (`tools/almi-keytool/pyproject.toml`, `uv.lock`)

Отдельный проект без зависимости от `server/` (промпт I1-04).

| Пакет | Версия | Назначение | Добавлена | Согласовано |
|---|---|---|---|---|
| click | 8.5.0 | Командная строка, ввод пароля без эха | I1-04 | Промпт I1-04 |
| pynacl | 1.6.2 | Ed25519, Argon2id, XChaCha20-Poly1305 (libsodium) | I1-04 | Промпт I1-04 |
| pytest, ruff, mypy (dev) | 9.1.1, 0.17.2, 1.19.1 | Тесты и линтеры, те же версии, что у сервера | I1-04 | Документ 6, раздел 4.1 |
| hatchling (сборка) | 1.32.4 | Сборка пакета `almi-keytool` | I1-04 | — |

## Консоль (`console/package.json`, `package-lock.json`)

Точные версии, каждая выпущена не позже чем за две недели до добавления (23.10.2026); в рамках стека `AGENTS.md` (Vue 3.5, TypeScript 5, Vite 6, PrimeVue 4).

| Пакет | Версия | Назначение | Добавлена | Согласовано |
|---|---|---|---|---|
| vue | 3.5.43 | Интерфейс | I2-07 | Стек `AGENTS.md` |
| primevue, @primeuix/themes, primeicons | 4.5.5, 2.0.3, 7.0.0 | Компоненты и тема Aura (`@primevue/themes` устарел, заменён `@primeuix/themes`) | I2-07 | Стек `AGENTS.md`, промпт I2-07 |
| pinia | 3.0.4 | Состояние | I2-07 | Стек `AGENTS.md` |
| vue-router | 4.6.4 | Маршруты | I2-07 | Стек `AGENTS.md` |
| vue-i18n | 11.4.13 | Тексты ru/en | I2-07 | Стек `AGENTS.md` |
| openapi-fetch, openapi-typescript | 0.17.0, 7.13.0 | Клиент Admin API, генерация типов (`npm run gen:api`) | I2-07 | Промпт I2-07 |
| zod | 3.25.76 | Проверка форм | I2-07 | Промпт I2-07 |
| vite, @vitejs/plugin-vue | 6.4.4, 5.2.4 | Сборка | I2-07 | Стек `AGENTS.md` |
| typescript, vue-tsc | 5.9.3, 2.2.12 | Типы (strict) | I2-07 | Стек `AGENTS.md` |
| vitest, @vue/test-utils, jsdom | 3.2.7, 2.5.1, 26.1.0 | Модульные тесты | I2-07 | Стек `AGENTS.md` |
| @playwright/test | 1.63.0 | Сквозной сценарий консоли (версия совпадает с браузерами окружения) | I2-07 | Стек `AGENTS.md` |
| eslint, eslint-plugin-vue, typescript-eslint, @vue/eslint-config-typescript | 9.39.5, 10.11.1, 8.71.1, 14.9.0 | Линтер | I2-07 | Стек `AGENTS.md` |
| @types/node | 22.20.5 | Типы Node для конфигураций | I2-07 | — |

## Модуль DL (`sdk/cpp/vcpkg.json`)

Версии фиксирует `builtin-baseline` vcpkg `23b8a8e7409c2d6346114a88e834165bde79a51c` (23.10.2026); сборка статическая (`x64-linux`, `x64-windows-static`).

| Пакет | Версия | Назначение | Добавлен | Согласовано |
|---|---|---|---|---|
| libsodium | 1.0.22 | Ed25519, SHA-256, XChaCha20-Poly1305, HKDF-SHA256 (нужен 1.0.19+), обнуление секретов (`sodium_memzero`) | I0-04 | Стек `AGENTS.md` |
| curl[ssl] | 8.23.0 | HTTPS-транспорт; TLS — OpenSSL 3.6.5 (Linux), Schannel (Windows) | I0-04 | Стек `AGENTS.md` |
| nlohmann-json | 3.12.0 | JSON | I0-04 | Стек `AGENTS.md` |
| gtest | 1.18.0 | Тесты (`lm_tests`) | I0-04 | Стек `AGENTS.md` |
| cpp-httplib | по `builtin-baseline` | Локальный HTTP-сервер в тестах `Transport` (только `lm_tests`, в модуль не входит) | I2-08 | Промпт I2-08 |

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
| Syft (anchore/syft) | 1.54.1 (sha256 в `tools/sbom/install-syft.sh`) | CI `sbom`, `make sbom` (в `.tools/`, не в образах) | SBOM образов и lock-файлов (`docs/sbom.md`); инструмент назван в документе 1 (раздел 13) и документе 7 (раздел 6); 1.55.0 моложе двух недель | v0.6.2, запрос руководителя проекта 26.10.2026 |
| actions/download-artifact | v8 | CI `sbom` | SBOM модуля DL из `test-dl` (пара к upload-artifact v7) | v0.6.2 |

## Примечания

1. DRF 3.15.2 официально поддерживает Django до 5.0 и Python до 3.12. Стек требует Python 3.13 и Django 5.2, официальная поддержка которых появилась в DRF 3.16. Выбрана 3.16.1; подтверждено руководителем проекта 23.10.2026, строка стека в `AGENTS.md` исправлена (в разделе 3 документа 6 пока «3.15»).
