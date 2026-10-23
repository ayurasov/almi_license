# almi-license — система лицензирования АЛМИ

Сервер лицензирования (Django), веб-консоль (Vue 3) и модуль лицензирования DL (C++) для продуктов АЛМИ Партнер (АльтерОфис Desktop, АльтерОфис Web, АльтерОС).
Один образ сервера работает в двух режимах: центральный сервер (`DEPLOYMENT_MODE=central`) и локальный сервер заказчика, в том числе в изолированном контуре (`DEPLOYMENT_MODE=local`).

Правила разработки для людей и ИИ-ассистентов — [AGENTS.md](AGENTS.md). Источник истины — каталог [contracts/](contracts/) и документы [01](docs/specs/01-architecture.md), [02](docs/specs/02-interaction-spec.md).

## Документы

| Документ | Файл |
|---|---|
| 1. Архитектура и план разработки | [docs/specs/01-architecture.md](docs/specs/01-architecture.md) |
| 2. Спецификация взаимодействия | [docs/specs/02-interaction-spec.md](docs/specs/02-interaction-spec.md) |
| 3. Бэклог этапа 1 | [docs/specs/03-backlog.md](docs/specs/03-backlog.md) |
| 4. Каталог продуктов и функций | [docs/specs/04-catalog.md](docs/specs/04-catalog.md) |
| 5. Тексты сообщений | [docs/specs/05-messages.md](docs/specs/05-messages.md) |
| 6. Правила разработки с ИИ-ассистентами | [docs/specs/06-ai-rules.md](docs/specs/06-ai-rules.md) |
| 7. Стенды, CI/CD и порядок выпуска | [docs/specs/07-environments.md](docs/specs/07-environments.md) |
| 8. Техническое задание на ЛК АльтерСофт 3.0 | [docs/specs/08-lk-tz.md](docs/specs/08-lk-tz.md) |
| 10. Промпты для разработки этапа 1 | [docs/specs/10-ai-prompts.md](docs/specs/10-ai-prompts.md) |
| Диаграммы C4 и последовательностей | [docs/specs/diagrams/](docs/specs/diagrams/) |
| Контракт Product API v1 | [contracts/openapi-product-api-v1.yaml](contracts/openapi-product-api-v1.yaml) |

Рабочие файлы этапа: журнал [docs/progress/stage1.md](docs/progress/stage1.md), решения [docs/decisions.md](docs/decisions.md), ADR [docs/adr/](docs/adr/), изменения [CHANGELOG.md](CHANGELOG.md).

## Структура

Раздел 14 документа 1.

```text
contracts/      OpenAPI, JSON Schema (schemas/), эталонные векторы (vectors/) — только через ревью TL
server/         Django-проект: almi_license/ (settings, urls), apps/ (модули), infra/, tests/
console/        веб-консоль Vue 3 + TypeScript
sdk/cpp/        модуль лицензирования DL (license_module)
sdk/php/        SDK веб-продуктов (этап 2)
tools/          almi-keytool (ключи и сертификаты), conformance (тесты соответствия продукта)
deploy/         central/, local/, dev/ (локальное окружение), airgap-bundle/
docs/           specs/ (документы комплекта), adr/, progress/
prompts/        промпты итераций I0–I6 и базового цикла истории P0–P12
```

## Команды

Цели из раздела 5 документа 7. Пока код не написан, цель печатает `not implemented` и завершается с кодом 0.

| Команда | Действие |
|---|---|
| `make help` | Список целей |
| `make up` / `make down` | Поднять и остановить локальное окружение |
| `make up-local` | То же в режиме `DEPLOYMENT_MODE=local` |
| `make seed` | Миграции и набор `seed-minimal` |
| `make test` | Все тесты: `test-server`, `test-console`, `test-dl` |
| `make lint` | Все линтеры: ruff, mypy, eslint, vue-tsc, clang-tidy |
| `make contract-check` | Сверка OpenAPI реализации с `contracts/openapi-product-api-v1.yaml` |
| `make vectors` | Эталонные векторы на сервере и в DL |
| `make e2e` | Playwright и сценарии API против `dev` |
| `make bundle-airgap` | Собрать комплект изолированного контура локально |

Хуки перед коммитом (ruff, ruff-format, eslint, clang-format, gitleaks):

```sh
pre-commit install
pre-commit run --all-files
```

## Порядок работы

1. Работа ведётся итерациями I0–I6 по [prompts/iterations/](prompts/iterations/README.md); каждая история — по циклу [prompts/base/](prompts/base/README.md) (P0 → P9).
2. Ветки задач создаются от `stage1`, слияние — squash через запрос по шаблону [.github/pull_request_template.md](.github/pull_request_template.md) (раздел 6 документа 6).
3. Технический лидер заменяет `@tech-lead` в [CODEOWNERS](CODEOWNERS) на свою учётную запись.
4. `docs/specs/` и `contracts/` меняются только через ревью технического лидера.
