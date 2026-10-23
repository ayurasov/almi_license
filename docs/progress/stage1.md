# Журнал этапа 1

## Закрытые истории

Формат записи:

```markdown
### E03-05 — Освобождение места — закрыта 21.10.2026
- Реализовано: release() с квитанцией JWS; идемпотентность; аудит.
- Ограничения: квитанция без цепочки для локального сервера — до E09-04.
- Разблокировано: E08-03, E14-07.
- Запрос на слияние: #42.
```

### E00-05 — Готовый репозиторий (I0-01, структура) — закрыта 23.10.2026
- Реализовано: каталоги по разделу 14 документа 1 (+ `deploy/dev`); `.editorconfig`, `.gitignore`, `.pre-commit-config.yaml` (ruff, ruff-format, eslint, clang-format, gitleaks); `Makefile` с целями раздела 5 документа 7; `README.md`; запись в `CHANGELOG.md`. `AGENTS.md` и `CODEOWNERS` уже совпадали с разделами 3 и 6 документа 6 — оставлены без изменений.
- Ограничения: все цели `Makefile` — заглушки `not implemented` (код 0); их наполняют I0-02 (`test-server`, `lint`), I0-03 (`up`, `down`, `seed`, `contract-check`), I0-04 (`test-dl`), E00-04 (`vectors`). Хук eslint начнёт работать после появления `console/package.json` (I2-07).
- Разблокировано: I0-02, I0-03, I0-04.
- Запрос на слияние: ветка `claude/happy-feynman-mea6mb`, запрос не создан.

### I0-02 — Каркас сервера (FS1) — закрыта 23.10.2026
- Реализовано: Django 5.2 в `server/` (uv, `pyproject.toml` с точными версиями, `uv.lock`); настройки `base`/`dev`/`ci`/`prod` только из окружения; проверка `DEPLOYMENT_MODE` при старте; 14 пустых модулей `apps/` (`domain/`, `models.py`, `api/`, `tests/`, `migrations/`); `infra.clock` (`Clock`, `SystemClock`, `FrozenClock`); протокол `infra.crypto.CryptoProvider`; `/health`, `/ready`; ruff, mypy, import-linter (4 контракта); `docs/dependencies.md`. 20 тестов.
- Ограничения: журналы пока не JSON (E15-05); `prod` не включает `SECURE_SSL_REDIRECT` — TLS завершается на Nginx (решить в E15-01/E15-07); конфигурация coverage для запуска из корня (`pytest server --cov`) не задана — в отчёт попадают тесты (I0-03, вместе с `tools/coverage_gate.py`).
- Передано в I0-03: задачам CI `lint-server` и `test-server` нужны `DEPLOYMENT_MODE` и `DATABASE_URL` (для `lint-server` достаточно `make lint-server`, он подставляет адрес-заглушку); mypy и import-linter читают конфигурацию из `server/`, поэтому CI вызывает их из `server/` или через `make lint-server`; исключение для тестовых ключей — в `.gitleaks.toml` (решение по вопросу 4).
- Разблокировано: I0-03, I1-03 (модель данных), E02-02 (`Ed25519Provider`).
- Запрос на слияние: ветка `claude/happy-feynman-mea6mb`, запрос не создан.

### I0-03 — Локальное окружение (E00-07) и каркас CI (E00-06) — закрыта 23.10.2026
- Реализовано: `deploy/Dockerfile` (`base`/`dev`/`runtime`, UID 10001, в `runtime` нет компиляторов и uv, 284 МБ); `deploy/dev/docker-compose.yml` и `nginx.conf`; `make up` / `up-local` / `down` / `seed` — холодный `make up` за 38 с; `.github/workflows/ci.yml` (8 задач); `.gitleaks.toml` (исключение `contracts/vectors/keys/`), `.gitleaksignore` (5 проверенных ложных срабатываний в примерах `docs/specs`); coverage без тестов и миграций.
- Проверено локально: `make up` поднимает все сервисы в состояние healthy, `/ready` через шлюз отвечает 200, в контейнере `uid=10001(app)`; команды каждой задачи CI проходят; actionlint без замечаний; закрытый ключ вне `contracts/vectors/keys/` валит gitleaks (код 1), в этом каталоге — нет (проверено во временном локальном клоне, в GitHub не отправлялось).
- Не проверено: прогон CI на GitHub — workflow запускается на `pull_request` и `push` в `stage1`/`main`, а ветки `stage1` и запроса на слияние ещё нет (вопрос 7).
- Ограничения: `signing_key` до E00-04 подставляется как `/dev/null`; `worker` в профиле `worker` до E12-01; контейнер консоли простаивает до I2-07; `seed-minimal` — после модели данных (I1-03); в `runtime` нет Gunicorn и точек входа (E15-01); `contract` проверяет только валидность YAML, сверка с drf-spectacular — с появлением Product API; пороги покрытия по модулям (`tools/coverage_gate.py`), `deps` (pip-audit, npm audit, osv-scanner), `vectors`, `compat`, `image` — в следующих историях E00-06 / E00-04 / E15-01.
- Разблокировано: I0-04 (задача `test-dl` включится сама с появлением `sdk/cpp/CMakeLists.txt`), I1-02, все истории сервера (CI).
- Запрос на слияние: ветка `claude/happy-feynman-mea6mb`, запрос не создан.

### I0-04 — Каркас модуля DL (E13-01) — готова к ревью 23.10.2026
- Реализовано: `sdk/cpp` — CMake (C++17), цели `license_module` (shared), `lm_tests` (GoogleTest), `lm-demo`; зависимости из vcpkg (`vcpkg.json`, `builtin-baseline`), статически; `include/license_module.h` байт в байт из раздела 15.1 документа 2; все `LM_*` возвращают `LM_ERR_NOT_INITIALIZED` (`LM_HasFeature`, `LM_GetMessageCount` → 0; `LM_GetAbiVersion` → `LM_ABI_VERSION`); `src/platform/{win,linux}`; `LM_TRUST_ROOTS`; `LM_SANITIZE`; `.clang-format`, `.clang-tidy`; `make test-dl`, `make lint-dl`; задачи CI `test-dl` (Linux GCC, Windows MSVC, ASan/UBSan, артефакты) и `lint-dl`.
- Проверено локально (Linux, GCC 13): 7 тестов, в том числе под ASan/UBSan; `.so` экспортирует ровно 23 функции заголовка; clang-format и clang-tidy без замечаний и срабатывают на нарушения. Зависимости локально — системные пакеты Ubuntu через временные обёртки: прокси песочницы запрещает скачивание архивов исходников с GitHub (`codeload.github.com`, 403), поэтому сборка через vcpkg и MSVC проверяются только в CI.
- Ограничения: версия модуля проверяется внутренней `lm::Version()`, а не `LM_GetVersion` (вопрос 9); экспорт DLL через `.def` и подавленное C4273 (вопрос 8); корни доверия до E00-04 не встраиваются (предупреждение CMake); тела `LM_*` без `try/catch`, пока не могут бросать.
- Разблокировано: E13-02 (`LeaseVerifier`), E13-11 (`lm-demo`, заглушка).
- Запрос на слияние: [ayurasov/almi_license#1](https://github.com/ayurasov/almi_license/pull/1).

## Текущая итерация
I0 — подготовка. Выполнено: I0-01, I0-02, I0-03, I0-04 (ждёт CI с задачами DL). Ветка `stage1` создана, запрос на слияние [ayurasov/almi_license#1](https://github.com/ayurasov/almi_license/pull/1); первый прогон CI (I0-01…I0-03) зелёный. Для выхода из I0 осталось: зелёный CI с задачами DL, слияние, защита веток `main` и `stage1`.

## Открытые вопросы

Решённые (23.10.2026, ответы руководителя проекта; подробности в `docs/decisions.md`):
1. ~~`api_integration`~~ — на этапе 1 не создаётся, добавляется в процессе.
2. ~~`docs/dependencies.md`~~ — создан в I0-02.
3. ~~Объём `CODEOWNERS`~~ — обязательное ревью владельцев кода убрано, изменения контролирует руководитель проекта.
4. ~~Тестовые закрытые ключи и gitleaks~~ — исключение в `.gitleaks.toml` для каталога тестовых ключей (выполняется в I0-03 / E00-04).

5. ~~Версия DRF~~ — 3.16.1 подтверждена, `AGENTS.md` исправлен; в разделе 3 документа 6 осталось «3.15».

Открытые:
6. **Раздел «Модули с обязательным ревью технического лидера» в `AGENTS.md`.** После решения по вопросу 3 он расходится с процессом. Оставить как перечень модулей для чек-листа P7 или переформулировать?
7. **Защита веток.** `stage1` и запрос на слияние созданы, CI запускается. После слияния — защита веток `main` и `stage1` (раздел 6.3 документа 7, критерий выхода I0) в настройках репозитория.
8. **`LM_API` при сборке DLL.** Заголовок раздела 15.1 на Windows объявляет `LM_API` только как `__declspec(dllimport)`; при сборке самой библиотеки нужен `dllexport`. Сейчас экспорт задан `src/license_module.def`, предупреждение C4273 подавлено. Предложение: добавить в заголовок ветку `#ifdef LM_BUILDING_DLL → __declspec(dllexport)` (не меняет ABI) и поправить раздел 15.1 документа 2.
9. **`LM_GetVersion`.** Промпт I0-04 требует `LM_GetVersion`, в заголовке раздела 15.1 её нет (есть `LM_GetAbiVersion`). Версия из CMake сейчас проверяется внутренней `lm::Version()`. Предложение: добавить `LM_API LM_Result LM_GetVersion(char* buffer, int buffer_size);` в конец заголовка как v1+ (правило 15) и в документ 2.
