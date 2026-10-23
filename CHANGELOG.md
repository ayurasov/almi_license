# Изменения

## Unreleased
- Скелет репозитория по разделу 14 документа 1: каталоги, `Makefile` с целями-заглушками, `pre-commit`, `.editorconfig`, `.gitignore` (E00-05).
- Каркас сервера Django 5.2: настройки `base`/`dev`/`ci`/`prod` из переменных окружения; сервер не запускается без `DEPLOYMENT_MODE=central|local` (I0-02).
- `GET /health` (процесс жив) и `GET /ready` (есть соединение с БД, иначе 503) (I0-02).
- `infra.clock`: `Clock`, `SystemClock`, `FrozenClock`; `infra.crypto.CryptoProvider` — протокол без реализации (I0-02).
- `make lint` и `make test-server` работают для сервера: ruff, mypy, import-linter, pytest (I0-02).
- Локальное окружение `make up` / `up-local` / `down` / `seed`: PostgreSQL 17, API, консоль, Nginx на `http://localhost:8080` (E00-07).
- Образ сервера `deploy/Dockerfile` (этапы `base`, `dev`, `runtime`; пользователь `app`, UID 10001) (E00-07).
- CI GitHub Actions: `lint-server`, `contract`, `arch`, `secrets`, `test-server`, `test-dl`, `lint-console`, `test-console` (E00-06).
- Каркас модуля DL `sdk/cpp`: `license_module` (Windows и Linux), `lm_tests`, `lm-demo`; публичный заголовок `license_module.h` по разделу 15.1 документа 2; все `LM_*` пока возвращают `LM_ERR_NOT_INITIALIZED` (E13-01).
- `make test-dl`, `make lint-dl`; задачи CI `test-dl` (с ASan/UBSan на Linux и артефактами) и `lint-dl` (E13-01).
- `license_module.h`: `LM_GetVersion` (версия модуля) и `LM_BUILDING_DLL` для экспорта на Windows; раздел 15.1 документа 2 обновлён (E13-01).
- JSON Schema 2020-12 в `contracts/schemas` (аренда, политика, сообщения, директивы, ошибки, заголовок JWS, офлайн-файлы, `.alk-req`, `config.json`) с примерами; `make contract-check` проверяет схемы, примеры и все json-примеры документа 2 и сверяет схемы с OpenAPI (E00-03).
- JSON Schema сертификата ключа, пакета доверия, квитанции, ответа `.alk-lic`, пакета `.alk` и отчёта `.alk-usage`; тип JWS отчёта `alm-usage+jws`; в OpenAPI добавлен вебхук `license.transferred` (E00-03).
- Эталонные векторы v1 в `contracts/vectors`: тестовые ключи Ed25519, 12 векторов JWS, 6 векторов подписи запроса, 39 векторов `PolicyEngine`; генератор `tools/vectors/generate.py`, `make vectors` (E00-04).
- Модели и миграции домена: каталог, лицензии и ключи, активации и аренды, локальные серверы и пакеты, журнал аудита (E01-01).

