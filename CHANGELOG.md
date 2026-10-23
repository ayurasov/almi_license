# Изменения

## Unreleased
- Скелет репозитория по разделу 14 документа 1: каталоги, `Makefile` с целями-заглушками, `pre-commit`, `.editorconfig`, `.gitignore` (E00-05).
- Каркас сервера Django 5.2: настройки `base`/`dev`/`ci`/`prod` из переменных окружения; сервер не запускается без `DEPLOYMENT_MODE=central|local` (I0-02).
- `GET /health` (процесс жив) и `GET /ready` (есть соединение с БД, иначе 503) (I0-02).
- `infra.clock`: `Clock`, `SystemClock`, `FrozenClock`; `infra.crypto.CryptoProvider` — протокол без реализации (I0-02).
- `make lint` и `make test-server` работают для сервера: ruff, mypy, import-linter, pytest (I0-02).
