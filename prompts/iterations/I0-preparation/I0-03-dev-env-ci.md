# I0-03. Локальное окружение и CI

```text
Реализуй локальное окружение и CI по разделам 5 и 6 docs/specs/07-environments.md.

1. deploy/Dockerfile: этапы base, dev, runtime; пользователь app UID 10001; runtime без компиляторов.
2. deploy/dev/docker-compose.yml и deploy/dev/nginx.conf по разделу 5; make up / down / seed работают.
3. .github/workflows/ci.yml: задачи lint-server, contract (пока проверяет только валидность contracts/openapi-product-api-v1.yaml), arch (import-linter), secrets (gitleaks), test-server с PostgreSQL 17, test-dl (Linux и Windows, пока сборка пустой библиотеки и одного теста), lint-console и test-console пропускаются, если console/ пуст.
4. Кэш зависимостей uv и npm.
Проверь: make up поднимается за 2 минуты; CI зелёный на пустом проекте; намеренно добавленный секрет в тестовой ветке валит задачу secrets (после проверки удали).
Коммиты: build: dockerfile and dev compose (E00-07); ci: pipeline skeleton (E00-06).
```
