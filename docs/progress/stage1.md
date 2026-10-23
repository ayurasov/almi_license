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
- Реализовано: `sdk/cpp` — CMake (C++17), цели `license_module` (shared), `lm_tests` (GoogleTest), `lm-demo`; зависимости из vcpkg (`vcpkg.json`, `builtin-baseline`), статически; `include/license_module.h` байт в байт из раздела 15.1 документа 2; все `LM_*` возвращают `LM_ERR_NOT_INITIALIZED` (`LM_HasFeature`, `LM_GetMessageCount` → 0; `LM_GetAbiVersion` → `LM_ABI_VERSION`; `LM_GetVersion` — версия из CMake без инициализации); по решениям 8 и 9 в заголовок и раздел 15.1 документа 2 добавлены `LM_BUILDING_DLL` (экспорт на Windows) и `LM_GetVersion`; `src/platform/{win,linux}`; `LM_TRUST_ROOTS`; `LM_SANITIZE`; `.clang-format`, `.clang-tidy`; `make test-dl`, `make lint-dl`; задачи CI `test-dl` (Linux GCC, Windows MSVC, ASan/UBSan, артефакты) и `lint-dl`.
- Проверено локально (Linux, GCC 13): 11 тестов, в том числе под ASan/UBSan; `.so` экспортирует ровно 24 функции заголовка; clang-format и clang-tidy без замечаний и срабатывают на нарушения. Зависимости локально — системные пакеты Ubuntu через временные обёртки: прокси песочницы запрещает скачивание архивов исходников с GitHub (`codeload.github.com`, 403), поэтому сборка через vcpkg и MSVC проверяются только в CI.
- Ограничения: корни доверия до E00-04 не встраиваются (предупреждение CMake); тела `LM_*` без `try/catch`, пока не могут бросать.
- Разблокировано: E13-02 (`LeaseVerifier`), E13-11 (`lm-demo`, заглушка).
- Запрос на слияние: [ayurasov/almi_license#1](https://github.com/ayurasov/almi_license/pull/1).

### I1-01 — JSON Schema подписанных объектов (E00-03) — закрыта 23.10.2026
- Реализовано: 21 схема JSON Schema 2020-12 в `contracts/schemas` — `lease`, `policy`, `message`, `directive`, `problem`, `jws-header`, `alk-file`, `alk-req`, `alk-lic`, `alk-usage`, `package`, `cert`, `trust`, `receipt`, `config` и общие `product`, `os-info`, `instance`, `fingerprint`, `usage`, `license-state`; у каждой 1+ валидный и 2+ невалидных примера, каждый невалидный падает ровно по заявленной причине; `make contract-check` (`tools/contract_check.py`): метасхема, примеры, все 17 json-блоков документа 2 по назначенным схемам, совпадение 12 зеркальных схем с компонентами OpenAPI; задача CI `contract` вызывает `make contract-check`. Состав `cert`, `trust`, `receipt`, `alk-lic`, `package`, `alk-usage` — по решению 10; `license.transferred` в OpenAPI — по решению 11.
- Ограничения: сверка реализации с drf-spectacular — с появлением эндпоинтов Product API; тег `contract-v1.0.0` ставит технический лидер после E00-04 (критерий выхода I1).
- Разблокировано: I1-02 (векторы), I1-03, I1-05, E02-02/E02-03.
- Запрос на слияние: [ayurasov/almi_license#1](https://github.com/ayurasov/almi_license/pull/1).

### I1-02 — Эталонные векторы (E00-04) — закрыта 23.10.2026 (правила и `reasoning` подтверждены, вопрос 12)
- Реализовано: `tools/vectors/generate.py` (PyNaCl, фиксированные seed) — ключи `dev-root`, `dev-issuer`, `dev-local-server`, `dev-device`; 12 векторов `jws/` (все обязательные случаи промпта, у каждого ровно один дефект); 6 векторов `request-signature/`; 39 векторов `policy/`, посчитанных вручную, с `reasoning`; `contracts/vectors/README.md` (форматы, порядок проверок и коды результата, соглашения); `make vectors` и задача CI `vectors`.
- Проверено: независимая перепроверка вне репозитория — подписи и цепочки библиотекой `cryptography` (не PyNaCl), ожидания policy-векторов — одноразовой реализацией алгоритма раздела 7.2 (39 из 39 совпали); генератор воспроизводим байт в байт; утверждения аренд и сертификатов валидны по схемам I1-01; DL при `LM_TRUST_ROOTS=dev` встраивает `dev-root.pub`; `make up` использует `dev-issuer.key`.
- Ограничения: прогон векторов на сервере и в DL появится с E02-03, E04-01, E13-02; `policy/` расширены полями `license.type`, `license.capabilities`, `trial` (без них ожидание не вычисляется).
- Разблокировано: I1-04 (keytool сверяет результаты с векторами), I1-05 (LeaseVerifier), E02-02/E02-03, E04-01.

### I1-03 — Модель данных (E01-01) — закрыта 23.10.2026
- Реализовано: модели и миграции `catalog` (Metric, Product, Capability, Edition, PolicyProfile), `licensing` (Customer, License, LicenseKey, ExternalRef), `activation` (Activation, Lease), `packages` (LocalServer, Allocation, Package, UsageReport), `audit` (AuditEvent); первичные ключи UUID; `act_`/`srv_` — ULID в отдельном поле с уникальным индексом и проверкой формата в БД; частичный уникальный индекс «одна активная активация на лицензию и экземпляр»; индексы `Activation(status, last_seen_at)`, `License(status, valid_until)`, `LicenseKey(key_hash)`; перечисления и форматы — ограничения `CHECK`.
- Проверено: 41 тест сервера (ограничения, индексы, межмодульные внешние ключи, `migrate zero` и обратно); покрытие 90 %; тест границ модулей ловит запрещённый `ForeignKey` (проверено временной правкой).
- Ограничения: генерация ULID и значений времени — в доменных сервисах (E03-01, E09-01, через `Clock`); `CustomerGroup` — этап 2; фабрики `factory_boy` не добавлялись — хватило фикстур `server/conftest.py`.
- Разблокировано: E01-02…E01-08, E02-02, E03-01, E09-01, `seed-minimal`.

### I1-04 — Утилита `almi-keytool` (E02-01) — готова, ждёт ревью технического лидера (P7, «Криптография»)
- Реализовано: `tools/almi-keytool` (click + PyNaCl, без зависимости от `server/`): `init-root`, `issue-cert`, `revoke-cert`, `export-trust`, `verify`; корневой ключ — XChaCha20-Poly1305 с ключом из Argon2id (t=3, m=256 МиБ, p=1), прочие поля файла — связанные данные AEAD; журнал `keytool.log`; `make test-keytool`, `make lint-keytool` (mypy --strict), задача CI `keytool`.
- Проверено: 32 теста — сертификаты на dev-ключах совпадают с `contracts/vectors` байт в байт (ключ выпуска, истёкший, локального сервера); `verify` даёт ожидаемый результат на всех 12 векторах `jws/`; неверный пароль и изменённый файл — одно сообщение и код 2; повреждённый файл — отказ; полный сценарий церемонии при запрете сети; пароль не попадает в вывод и журнал; сценарии атаки P7 (сертификат от чужого корня, подмена листа цепочки, неизвестный kid). Ручной прогон с реальными параметрами Argon2id: файл ключа 0600, сертификат и пакет доверия валидны по схемам `cert`, `trust` и OpenAPI `TrustBundle`.
- Чек-лист P7 «Криптография» (раздел 8 документа 6): только libsodium через PyNaCl, своих примитивов нет — соблюдено; `alg` фиксирован `EdDSA`, `kid` — из файла ключа — соблюдено; подпись проверяется до разбора полезной нагрузки — соблюдено (`jws.py`, шаги 1–8); сравнение секретов в постоянное время — секреты не сравниваются, тег AEAD проверяет libsodium; размер входа — не ограничен (офлайн-утилита читает локальные файлы оператора).
- Ограничения: Python не обнуляет память — seed живёт до конца процесса (описано в README утилиты); `issue-cert` подписывает только корнем — сертификаты локальных серверов выпускает сервер (E09-02).
- Разблокировано: E02-02/E02-03 (сервер сверяется с теми же векторами), E17-04 (церемония), стенды `test-central`.

## Текущая итерация
I1 — контракты и основа. Выполнено: I1-01, I1-02, I1-03, I1-04 (ждёт ревью P7, вопрос 13). Следующая: I1-05 (проверка JWS в DL). I0: выполнены I0-01…I0-04; в CI сборка DL на Windows зелёная, на Linux исправлено отсутствие autotools для libsodium. Ветка `stage1` создана, запрос на слияние [ayurasov/almi_license#1](https://github.com/ayurasov/almi_license/pull/1); первый прогон CI (I0-01…I0-03) зелёный. Для выхода из I0 осталось: зелёный CI с задачами DL, слияние, защита веток `main` и `stage1`.

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
8. ~~`LM_API` при сборке DLL~~ — принято: `LM_BUILDING_DLL` → `dllexport` в заголовке и разделе 15.1 документа 2.
9. ~~`LM_GetVersion`~~ — принято: `LM_GetVersion(char*, int)` добавлена в конец ABI (v1+) в заголовке и разделе 15.1 документа 2.
10. ~~Состав объектов, не описанных в спецификации (E00-03)~~ — принято предложение: `cert`, `trust`, `receipt`, `alk-lic`, `package`, `alk-usage` в `contracts/schemas`; `typ` отчёта — `alm-usage+jws`; `iat`, `nbf`, `exp`, `server_time` — Unix, остальные даты — RFC 3339.
11. ~~`license.transferred` в `WebhookEvent`~~ — добавлено в OpenAPI.
12. ~~Проверка policy-векторов и правила вне раздела 7.2~~ — подтверждено руководителем проекта: правила `support`/`support_until`, TRIAL/UNLICENSED, `no_start`, `messages_ids`, `suspended`, коды и порядок проверки JWS, `sig` в base64url (README `contracts/vectors`).
13. **Ревью P7 `tools/almi-keytool` (область «Криптография»).** Обязательно по промпту I1-04: файлы `rootkey.py` (формат и защита корневого ключа), `jws.py` (порядок проверок), `certs.py`, `trust.py`. Решения для подтверждения: формат `root.key.json` (README утилиты); `revoke-cert` требует пароль корневого ключа; список отзыва и `seq` пакета доверия хранятся рядом с ключом; `verify` дополнительно сверяет неподписанные поля `trust.json` с подписанными (`bundle_mismatch`).

