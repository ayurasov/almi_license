# AGENTS.md — правила для ИИ-ассистентов и разработчиков

## Проект
Система лицензирования АЛМИ: сервер (Django), веб-консоль (Vue 3), модуль DL (C++).
Один образ работает в режимах DEPLOYMENT_MODE=central и DEPLOYMENT_MODE=local.
Источник истины — каталог contracts/ и документы docs/specs/01-architecture.md, docs/specs/02-interaction-spec.md.

## Стек и версии
- Python 3.13, Django 5.2 LTS, DRF 3.15, drf-spectacular, PostgreSQL 17, psycopg 3
- Vue 3.5, TypeScript 5 (strict), Vite 6, PrimeVue 4, Pinia, Vue Router 4, vue-i18n
- C++17, CMake 3.28, libsodium, libcurl, nlohmann/json, GoogleTest
- Тесты: pytest, hypothesis, vitest, Playwright, ctest, k6
- Не добавлять зависимости без согласования с техническим лидером (файл docs/dependencies.md).

## Команды
- make up — поднять окружение; make seed — тестовые данные
- make test — все тесты; make test-server; make test-console; make test-dl
- make lint — ruff, mypy, eslint, vue-tsc, clang-tidy
- make contract-check — сверка OpenAPI реализации с contracts/openapi-product-api-v1.yaml
- make vectors — прогон эталонных векторов на сервере и в DL
Перед тем как сообщить о завершении задачи, выполни make lint и make test для затронутых частей.

## Структура
server/apps/<модуль>/  domain/ (сервисы и правила), models.py, api/ (сериализаторы, представления), tests/
Модули: catalog, licensing, activation, policy, packages, signing, stats, audit, iam, outbox,
api_product, api_admin, api_sync, compat.
console/src/  views/, components/, stores/, api/ (сгенерирован из OpenAPI, руками не правится), i18n/
sdk/cpp/  include/license_module.h (публичный ABI), src/, tests/

## Жёсткие правила
1. Не изменять contracts/ — только по задаче с меткой contract и с ревью технического лидера.
2. Бизнес-логика только в domain/ модулей. Представления и сериализаторы ничего не решают.
3. Модуль не читает и не пишет таблицы другого модуля; только через его domain-сервис (проверяет import-linter).
4. Время только через infra.clock.Clock; datetime.now() и time.time() в коде запрещены.
5. PolicyEngine — чистая функция: без БД, сети, времени системы, случайности.
6. Изменение мест, лицензий и активаций — только в транзакции с select_for_update на строке лицензии.
7. Каждое изменение прав пишет событие аудита через audit.domain.record().
8. Секреты только из переменных окружения и Docker secrets. Никаких ключей, паролей, токенов в коде, тестах, фикстурах, журналах.
9. В журналы не попадают: полный ключ лицензии, аренда, подпись, nonce, хэши компонентов отпечатка, пароли.
10. Ошибки API — только application/problem+json с кодом из каталога docs/specs/02-interaction-spec.md раздел 16. Новые коды не придумывать.
11. Ответы Product API — только добавляющие изменения; поля не удаляются и не переименовываются.
12. Криптография только через infra.crypto.CryptoProvider (сервер) и crypto/ (DL). Не писать свою криптографию, не использовать random для секретов.
13. Миграции БД — обратимые; изменение существующих колонок — в два шага (добавить, перенести, удалить в следующем выпуске).
14. Консоль: компоненты PrimeVue, тексты только через i18n, клиент API только сгенерированный, состояние в Pinia.
15. C ABI (license_module.h) — только добавление функций и значений в конец перечислений.

## Как выполнять задачу
1. Прочитай задачу, ссылки на разделы docs/ и файлы contracts/.
2. Напиши тесты по критериям приёмки. Запусти — они должны падать.
3. Реализуй минимальный код, который проходит тесты.
4. Запусти make lint и make test. Исправь всё.
5. Обнови docs/ и CHANGELOG.md, если меняется поведение.
6. Опиши в запросе на слияние: что сделано, как проверено, что осталось, какие решения принял сам.
Если контракт неясен или противоречив — остановись и задай вопрос, не угадывай.

## Модули с обязательным ревью технического лидера
signing, infra/crypto, activation (учёт мест), policy, api_product/auth (подпись запросов),
packages (импорт и выпуск), audit, iam, compat (разбор входных данных),
sdk/cpp: LeaseVerifier, Transport, SecureStore, StateEvaluator, RollbackGuard, TrialTracker, OfflineFiles.
