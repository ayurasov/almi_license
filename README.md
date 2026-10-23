# Система лицензирования АЛМИ — стартовый комплект репозитория

Комплект для разработки этапа 1 с ИИ-ассистентами. Структура и имена файлов совпадают с путями, на которые ссылаются промпты.

## Состав

```text
AGENTS.md                         правила для ИИ-ассистента (раздел 3 документа 6)
CODEOWNERS                        обязательное ревью технического лидера
CHANGELOG.md
.github/pull_request_template.md  шаблон запроса на слияние
contracts/openapi-product-api-v1.yaml   контракт Product API v1
docs/specs/                       документы комплекта с короткими именами
  01-architecture.md … 08-lk-tz.md, 10-ai-prompts.md, diagrams/
docs/progress/stage1.md           журнал этапа — память ассистента
docs/progress/iteration-template.md
docs/decisions.md, docs/adr/
prompts/README.md                 итерационная модель, правила сессий, признаки проблем
prompts/base/                     P00–P12 — цикл истории
prompts/iterations/I0…I6/         цель, план, готовые промпты, критерии выхода
prompts/streams/                  QA, DevOps, модуль DL
```

## Порядок работы

1. Распаковать в корень пустого репозитория `almi-license`, закоммитить в ветку `stage1`.
2. Технический лидер проверяет `AGENTS.md` и `CODEOWNERS` (заменить `@tech-lead` на учётную запись).
3. Выполнить итерацию I0 по `prompts/iterations/I0-preparation/README.md`. Промпт I0-01 не перезаписывает уже размещённые `AGENTS.md`, `CODEOWNERS`, `docs/` — только дополняет структуру.
4. Каждую историю вести по циклу `prompts/base/` (P0 → P9); в конце итерации — P10 и файл `docs/progress/iteration-N.md` по шаблону.
5. `docs/specs/` и `contracts/` меняются только через ревью технического лидера.
