# Стенды, CI/CD и порядок выпуска

| Параметр | Значение |
|---|---|
| Документ | Стенды и CI/CD (документ 7 комплекта) |
| Версия | 1.0 |
| Дата | 14.10.2026 |
| Статус | Проект; утверждает технический лидер, исполняет DevOps-инженер |
| Связанные документы | 1 — Архитектура (разделы 6, 13, 14); 3 — Бэклог (E00, E15); 6 — Правила разработки |

## 1. Назначение

Документ определяет окружения разработки и тестирования, тестовые ключи и данные, конвейер CI/CD, порядок выпуска сервера, модуля DL и комплекта для изолированного контура. Всё описанное создаётся на неделях 1–3 этапа 1 (истории E00-06, E00-07, E15-01…E15-07).

## 2. Окружения

| Окружение | Назначение | Где | Режим | Ключи | Данные | Обновление |
|---|---|---|---|---|---|---|
| `dev` | Разработка на рабочем месте | Ноутбук разработчика, Docker Compose | `central` или `local` | `dev-root` (в репозитории, только открытая часть встраивается в DL тестовых сборок) | Фикстуры `make seed` | Вручную |
| `ci` | Автотесты | Раннеры CI, сервисный контейнер PostgreSQL | Оба | `ci-root`, создаётся на каждый прогон | Фикстуры | На каждый коммит |
| `test-central` | Интеграция, ручные тесты, демонстрации | ВМ в контуре АЛМИ, `license-test.alter-os.ru` | `central` | `test-root` | Обезличенная копия выгрузки ЛК, тестовые заказчики | Автоматически после слияния в `stage1` |
| `test-local` | Локальный сервер с исходящим доступом к `test-central` | ВМ в отдельной подсети, `license.test-corp.local` | `local` | Сертификат от `test-root` | Пакеты с `test-central` | Автоматически, вместе с `test-central` |
| `test-airgap` | Изолированный контур, обмен только файлами | ВМ без сетевого доступа к другим стендам; доступ через jump-хост для загрузки файлов | `local` | Сертификат от `test-root` | Пакеты файлом | Вручную, из комплекта изолированного контура |
| `staging` | Предвыпускная проверка | ВМ, конфигурация как у продуктива | `central` | `staging-root` | Копия продуктивной БД без ключей (с недели 6) | По тегу `v*-rc*` |
| `prod` | Продуктив | `license.alter-os.ru` | `central` | Продуктивный корневой ключ (церемония E17-04) | Реальные | По тегу `v*` после readiness gate |

Рабочие станции для тестов продукта: Windows 10, Windows 11, Astra Linux SE, РЕД ОС, АльтерОС — по одной ВМ в подсети `test-local` и одной в `test-airgap`. Сервер АльтерОфис Web (Nextcloud) — по одному экземпляру в `test-central` и `test-local`.

## 3. Ключи стендов

| Корневой ключ | Где хранится закрытая часть | Встраивается в | Кто имеет доступ |
|---|---|---|---|
| `dev-root` | `contracts/vectors/keys/dev-root.key` (публично в репозитории) | Отладочные сборки DL, `lm-demo` | Все |
| `ci-root` | Генерируется в прогоне, удаляется после | Сборки DL в CI | CI |
| `test-root` | Хранилище секретов CI (зашифровано) | Тестовые сборки продукта для QA | DevOps, технический лидер |
| `staging-root` | Офлайн-носитель, как у продуктива | Предвыпускные сборки продукта | Двое ответственных |
| Продуктивный | Офлайн-носитель, двойной контроль (документ 1, раздел 9) | Выпускные сборки продукта | Двое ответственных |

Правила:

1. Продуктивный открытый ключ встраивается только в сборки, собранные из тега `v*`. Сборка продукта с тестовым ключом не может попасть в продуктив: в имени артефакта и в окне «О программе» указывается «Тестовая сборка».
2. Модуль DL принимает список корневых ключей, заданный при сборке (`LM_TRUST_ROOTS`); тестовые и продуктивные ключи в одном списке не смешиваются.
3. Ключи выпуска стендов перевыпускаются раз в 90 дней; продуктивный — раз в год (документ 1, раздел 9).

## 4. Тестовые данные

| Набор | Содержимое | Где используется |
|---|---|---|
| `seed-minimal` | 1 продукт каждого вида, 3 заказчика, 10 лицензий всех типов, по 1 профилю каждого класса | `dev`, `ci` |
| `seed-load` | 1 000 заказчиков, 20 000 лицензий, 500 000 активаций | Нагрузочный тест на `test-central` |
| `lk-export-anon.xlsx` | Реальная выгрузка ЛК с заменой названий, ИНН и ключей | Тест импорта (E06-04) |
| `compat-fixtures/` | Записанные запросы и ответы Nextcloud и `registration.sh` (E00-09) | Тесты совместимости в `ci` |
| `vectors/` | Эталонные векторы (E00-04) | `ci`, все тесты сервера и DL |

Обезличивание выгрузки ЛК выполняет скрипт `tools/anonymize-lk.py`: ИНН заменяются на валидные синтетические, названия — на «Заказчик N», ключи — на новые с тем же форматом, даты и количества сохраняются.

## 5. Локальное окружение

Файл `deploy/dev/docker-compose.yml`:

```yaml
name: almi-license-dev
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_DB: almi_license
      POSTGRES_USER: almi
      POSTGRES_PASSWORD: dev-only
    ports: ["5432:5432"]
    volumes: [db:/var/lib/postgresql/data]
  api:
    build: { context: ../.., dockerfile: deploy/Dockerfile, target: dev }
    command: python manage.py runserver 0.0.0.0:8000
    environment:
      DEPLOYMENT_MODE: ${DEPLOYMENT_MODE:-central}
      DATABASE_URL: postgres://almi:dev-only@db:5432/almi_license
      SIGNING_KEY_FILE: /run/secrets/signing_key
      DJANGO_SETTINGS_MODULE: almi_license.settings.dev
    secrets: [signing_key]
    volumes: [../../server:/app/server]
    depends_on: [db]
  worker:
    build: { context: ../.., dockerfile: deploy/Dockerfile, target: dev }
    command: python manage.py run_worker
    environment:
      DEPLOYMENT_MODE: ${DEPLOYMENT_MODE:-central}
      DATABASE_URL: postgres://almi:dev-only@db:5432/almi_license
    depends_on: [db]
  console:
    image: node:22
    working_dir: /app
    command: sh -c "npm ci && npm run dev -- --host"
    volumes: [../../console:/app]
    ports: ["5173:5173"]
  nginx:
    image: nginx:1.27
    volumes: [./nginx.conf:/etc/nginx/conf.d/default.conf:ro]
    ports: ["8080:80"]
    depends_on: [api, console]
secrets:
  signing_key:
    file: ../../contracts/vectors/keys/dev-issuer.key
volumes:
  db: {}
```

Цели `Makefile`:

| Цель | Действие |
|---|---|
| `make up` / `make down` | Поднять и остановить окружение |
| `make up-local` | То же в режиме `local` (`DEPLOYMENT_MODE=local`) |
| `make seed` | Миграции и набор `seed-minimal` |
| `make test`, `make test-server`, `make test-console`, `make test-dl` | Тесты |
| `make lint` | Все линтеры |
| `make contract-check` | Сверка OpenAPI |
| `make vectors` | Эталонные векторы на сервере и в DL |
| `make e2e` | Playwright и сценарии API против `dev` |
| `make bundle-airgap` | Собрать комплект изолированного контура локально |

## 6. Конвейер CI

Платформа — GitHub Actions (при переходе на GitLab CI структура задач сохраняется).

### 6.1. Задачи

| Стадия | Задача | Когда | Блокирует слияние |
|---|---|---|---|
| Проверка | `lint-server` — ruff, mypy | Каждый запрос | Да |
| Проверка | `lint-console` — eslint, vue-tsc | Каждый запрос | Да |
| Проверка | `lint-dl` — clang-format, clang-tidy | Каждый запрос | Да |
| Проверка | `contract` — `openapi-spec-validator`, сверка drf-spectacular с `contracts/`, проверка JSON Schema | Каждый запрос | Да |
| Проверка | `arch` — import-linter | Каждый запрос | Да |
| Безопасность | `secrets` — gitleaks | Каждый запрос | Да |
| Безопасность | `deps` — pip-audit, npm audit, osv-scanner | Каждый запрос | Да для критичных уязвимостей |
| Тесты | `test-server` — pytest с PostgreSQL 17, покрытие | Каждый запрос | Да (с порогами покрытия) |
| Тесты | `test-console` — vitest | Каждый запрос | Да |
| Тесты | `test-dl-linux` — сборка GCC, ctest, ASan/UBSan | Каждый запрос | Да |
| Тесты | `test-dl-windows` — сборка MSVC, ctest | Каждый запрос | Да |
| Тесты | `vectors` — векторы на сервере и в DL, сравнение результатов | Каждый запрос | Да |
| Тесты | `compat` — фикстуры Nextcloud и `registration.sh` | Каждый запрос | Да |
| Сборка | `image` — образ, публикация в реестр с тегом коммита | Слияние в `stage1`, теги | — |
| Сборка | `dl-artifacts` — `license_module.dll`, `liblicense_module.so`, заголовок, `lm-demo` | Слияние в `stage1`, теги | — |
| Развёртывание | `deploy-test` — `test-central` и `test-local` | Слияние в `stage1` | — |
| Тесты | `e2e` — Playwright и сценарии API против `test-central` | После `deploy-test`, ночью полный набор | Нет, но красный E2E блокирует тег `rc` |
| Тесты | `load` — k6 против `test-central` | Ночью, перед тегом `rc` | Нет |
| Выпуск | `bundle-airgap` — комплект изолированного контура | Теги `v*` | — |
| Выпуск | `deploy-staging` | Тег `v*-rc*` | — |
| Выпуск | `deploy-prod` | Тег `v*`, ручное подтверждение двумя участниками | — |

С этапа 2 добавляются подпись образов (cosign), SBOM (Syft) и сканирование образа (Trivy).

### 6.2. Каркас `.github/workflows/ci.yml`

```yaml
name: ci
on:
  pull_request:
  push:
    branches: [stage1, main]
    tags: ['v*']
jobs:
  lint-server:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --project server --frozen
      - run: uv run --project server ruff check server && uv run --project server ruff format --check server
      - run: uv run --project server mypy server
  contract:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --project server --frozen
      - run: make contract-check
  test-server:
    runs-on: ubuntu-24.04
    services:
      postgres:
        image: postgres:17
        env: { POSTGRES_PASSWORD: ci, POSTGRES_DB: almi_license }
        ports: ['5432:5432']
        options: >-
          --health-cmd pg_isready --health-interval 5s --health-retries 10
    env:
      DATABASE_URL: postgres://postgres:ci@localhost:5432/almi_license
      DJANGO_SETTINGS_MODULE: almi_license.settings.ci
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --project server --frozen
      - run: uv run --project server pytest server --cov --cov-fail-under=70
      - run: uv run --project server python tools/coverage_gate.py activation=85 policy=85 signing=85
  test-dl:
    strategy:
      matrix:
        os: [ubuntu-24.04, windows-2022]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - run: cmake -S sdk/cpp -B build -DCMAKE_BUILD_TYPE=Release -DLM_TRUST_ROOTS=ci
      - run: cmake --build build --config Release
      - run: ctest --test-dir build -C Release --output-on-failure
  vectors:
    needs: [test-server, test-dl]
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - run: make vectors
  image:
    if: github.event_name == 'push'
    needs: [lint-server, contract, test-server, vectors]
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: docker/build-push-action@v6
        with:
          context: .
          file: deploy/Dockerfile
          target: runtime
          push: true
          tags: ${{ vars.REGISTRY }}/almi-license:${{ github.sha }}
```

Задачи `lint-console`, `lint-dl`, `arch`, `secrets`, `deps`, `test-console`, `compat`, `deploy-*`, `e2e`, `load`, `bundle-airgap` описываются в том же файле и в `release.yml` по образцу.

### 6.3. Правила для веток

| Ветка | Защита |
|---|---|
| `main` | Слияние только из `stage1` или `hotfix/*` через запрос; все задачи зелёные; два одобрения, одно — технического лидера |
| `stage1` | Слияние через запрос; все блокирующие задачи зелёные; одно одобрение; для путей CODEOWNERS — технический лидер |
| `contract/*` | Одобрение технического лидера обязательно |

## 7. Образ и версии

### 7.1. Образ

| Параметр | Значение |
|---|---|
| Базовый образ | `python:3.13-slim` (этап сборки), `gcr.io/distroless/python3` или `python:3.13-slim` (запуск) |
| Сборка консоли | Отдельный этап `node:22`, результат копируется в образ Nginx |
| Пользователь | `app` (UID 10001), без root |
| Точки входа | `api` (Gunicorn + Uvicorn workers), `worker`, `migrate`, `manage` |
| Метки | `org.opencontainers.image.version`, `revision`, `created` |
| Размер | до 400 МБ |
| Образы | `almi-license` (API и фоновый обработчик), `almi-license-console` (Nginx и статика консоли) |

### 7.2. Версии

| Артефакт | Схема | Пример |
|---|---|---|
| Сервер (образ) | SemVer `MAJOR.MINOR.PATCH` | `1.0.0`, `1.0.0-rc.1` |
| Модуль DL | SemVer, независимо от сервера | `1.0.0` |
| Протокол | Целое число в `ALMI-Protocol` | `1` |
| Формат файлов | Целое число в `version` | `1` |
| Каталог | Целое число в фикстуре | `1` |

Совместимость фиксирует матрица `docs/compatibility.md` (документ 17 комплекта): какие версии DL работают с какими версиями сервера.

## 8. Миграции БД

1. Миграции применяются отдельным запуском `migrate` до старта новых контейнеров API.
2. Каждая миграция обратима или помечена `irreversible` с обоснованием в запросе на слияние.
3. Удаление и переименование колонок — в два выпуска: в первом код перестаёт использовать колонку, во втором колонка удаляется.
4. Миграции данных объёмом больше 100 000 строк выполняются фоновой задачей, а не в миграции.
5. На `staging` перед выпуском миграции применяются к копии продуктивной БД с замером времени.

## 9. Комплект для изолированного контура

Собирается задачей `bundle-airgap` для каждого тега `v*`.

```
almi-license-local-1.0.0/
├── images/
│   ├── almi-license-1.0.0.tar          # docker save
│   ├── almi-license-console-1.0.0.tar
│   ├── postgres-17.tar
│   └── nginx-1.27.tar
├── docker-compose.yml                  # DEPLOYMENT_MODE=local
├── .env.example
├── install.sh                          # загрузка образов, генерация секретов, первый запуск
├── upgrade.sh                          # резервная копия, загрузка новых образов, миграции
├── backup.sh  restore.sh
├── check.sh                            # проверка состояния после установки
├── docs/                               # руководство по установке и эксплуатации (PDF)
├── SHA256SUMS
└── SHA256SUMS.sig                      # подпись ключом выпуска АЛМИ
```

Требования: установка на чистый хост с Docker 24+ без доступа в интернет за 30 минут; `check.sh` проверяет состояние сервисов, доступность API, срок пакета и свободное место; `upgrade.sh` откатывает обновление при ошибке миграции.

## 10. Порядок выпуска

| Шаг | Кто | Что | Результат |
|---|---|---|---|
| 1 | Технический лидер | Заморозка `stage1`, тег `v1.0.0-rc.1` | Предвыпускная версия |
| 2 | CI | Сборка, `deploy-staging`, E2E, нагрузка | Протоколы |
| 3 | QA | Ручные сценарии по матрице трассировки на `staging`, `test-local`, `test-airgap` | Протокол ручных тестов |
| 4 | Технический лидер, владелец продукта | Readiness gate (документ 1, раздел 15.7) | Протокол решения |
| 5 | Технический лидер | Слияние `stage1` → `main`, тег `v1.0.0` | Выпускная версия |
| 6 | DevOps | `deploy-prod` с подтверждением двумя участниками; проверка `/health`, `/ready` | Продуктив обновлён |
| 7 | DevOps | Публикация комплекта изолированного контура и DL для команд продуктов | Артефакты в хранилище выпусков |
| 8 | Оператор | Проверка входа в консоль, тестовая активация служебной лицензии | Запись в журнале выпуска |

Откат: предыдущий образ запускается командой `deploy/central/rollback.sh <версия>`; миграции этапа 1 обратимы, поэтому откат включает `migrate <приложение> <номер>`. Решение об откате принимает технический лидер, если в течение 2 часов после выпуска доля ошибок 5xx Product API выше 1 %.

## 11. Мониторинг стендов

| Что | Этап 1 | Этап 2 |
|---|---|---|
| Состояние | `/health`, `/ready`, внешняя проверка раз в минуту | Prometheus, Alertmanager |
| Метрики | `/metrics` (запросы, ошибки, длительность, очередь задач, возраст последнего резервного копирования) | Grafana-панели |
| Журналы | JSON в stdout, хранение на хосте 14 дней | Loki, передача в SIEM |
| Оповещения | Письмо и сообщение в рабочий чат: недоступность, 5xx больше 1 %, резервная копия старше 26 ч | Alertmanager, дежурства |

## 12. Доступы

| Ресурс | Разработчики | QA | DevOps | Технический лидер | Оператор |
|---|---|---|---|---|---|
| Репозиторий | Запись в ветки задач | Запись в ветки тестов | Запись | Администратор | — |
| CI, секреты CI | Просмотр | Просмотр | Администратор | Администратор | — |
| `dev`, `ci` | Полный | Полный | Полный | Полный | — |
| `test-*` консоль | Оператор | Оператор | Администратор | Администратор | — |
| `test-*` SSH | — | — | Да | Да | — |
| `staging` | Просмотр журналов | Оператор | Администратор | Администратор | Оператор |
| `prod` консоль | — | — | — | Администратор | Оператор |
| `prod` SSH | — | — | Да, с журналированием | По заявке | — |
| Корневые ключи `staging`, `prod` | — | — | Один из двух ответственных | Один из двух ответственных | — |
