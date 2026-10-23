# Эталонный экран «Заказчики» (E07-03)

Образец для остальных экранов консоли. Новый экран повторяет его части, имена и тесты; отличия — только в полях и правилах предметной области.

## Из чего состоит

| Часть | Файл | Что делает |
|---|---|---|
| Схема Admin API | `src/api/admin-api.yaml` | Выгружается с сервера: `make admin-schema` (drf-spectacular, `server/apps/api_admin/api`) |
| Типы клиента | `src/api/generated/admin.ts` | `npm run gen:api` (openapi-typescript); руками не правится, CI сверяет с сервером |
| Клиент | `src/api/client.ts` | openapi-fetch: cookie сессии, `X-CSRFToken` для изменений, `problem+json` → `ApiError`, сеть → `NetworkError`, глобальные слушатели `onProblem` |
| Ошибки | `src/api/problem.ts`, `src/App.vue` | `ApiError.fieldErrors` — ошибки полей (`data.fields`) для формы; прочие ошибки — toast с `user_message`; 401 — переход на вход |
| Хранилище | `src/stores/customers.ts` | `useCustomersStore`: `items`, `total`, `loading`, `failed`; методы `list(query)`, `get(id)`, `create(values)`, `update(id, values)`. Вид не вызывает API сам |
| Экран | `src/views/CustomersView.vue` | `DataTable` `lazy` с пагинацией и сортировкой на сервере; фильтры и страница — в query-параметрах URL (`page`, `page_size`, `ordering`, фильтры); пустое состояние, загрузка, ошибка сети с кнопкой «Повторить» |
| Форма | `src/components/CustomerDialog.vue` | `Dialog`; проверка zod до отправки, затем ошибки сервера по полям; toast об успехе |
| Проверка формы | `src/lib/customerSchema.ts`, `src/lib/inn.ts` | Схема zod; сообщения — ключи i18n; правило ИНН совпадает с сервером |
| Тексты | `src/i18n/ru.ts`, `en.ts` | Все строки интерфейса; `en` типизирован по `ru`, пропуск ключа — ошибка `vue-tsc`; голые строки в шаблоне запрещены eslint |
| Маршрут | `src/router/index.ts` | Раздел в `SECTIONS`, страница — ленивый импорт; без сессии — переход на `/login?next=…` |
| Тесты | `src/stores/customers.spec.ts`, `src/lib/*.spec.ts`, `src/api/client.spec.ts`, `e2e/customers.spec.ts` | vitest: хранилище (запросы и состояние), проверки, клиент; Playwright: сценарий «создать и найти фильтром» против настоящего сервера |

На сервере экрану соответствуют: представления `apps/api_admin/api/views.py` (только разбор и ответ), доменный сервис `apps/licensing/domain/customers.py` (проверки, уникальность, аудит), тесты `server/tests/api_admin/`.

## Как сделать новый экран (например, «Лицензии»)

1. Сервер: доменный сервис `apps/<модуль>/domain/<сущность>.py` (`list_…` с фильтрами, сортировкой из белого списка и страницей ≤ 100; `create_…`/`update_…` с `DomainError("invalid_request", data={"fields": …})` и `audit.domain.record`); представления в `apps/api_admin/api/views.py` с `extend_schema(operation_id=…)`; тесты в `server/tests/api_admin/test_<сущность>.py`.
2. `make admin-schema` — схема и типы консоли обновляются; оба файла входят в коммит.
3. Хранилище `src/stores/<сущность>.ts`: `use<Сущность>Store` с `items`, `total`, `loading`, `failed` и методами `list/get/create/update`; запрос — `<Сущность>Query` с `DEFAULT_QUERY`.
4. Экран `src/views/<Сущность>View.vue`: копия структуры `CustomersView.vue` — `fromUrl`/`navigate` для query-параметров, `watch(query, …, { immediate: true })`, `lazy` `DataTable`, слоты `#empty`, `Message` при `failed === 'network'`.
5. Форма `src/components/<Сущность>Dialog.vue` и схема `src/lib/<сущность>Schema.ts`: сначала zod, затем `ApiError.fieldErrors`; сообщения клиента — ключи i18n.
6. Тексты в `ru.ts` и `en.ts` (раздел `<сущность>`), маршрут — замена заглушки в `src/router/index.ts`.
7. Тесты: `<сущность>.spec.ts` для хранилища (подмена `api.GET/POST/PATCH` через `vi.spyOn`), схемы и чистых функций; один сценарий Playwright на основной путь.
8. `npm run lint`, `npm run test`, `npm run e2e` (нужен PostgreSQL в `DATABASE_URL`).

## Правила

- Компоненты — только PrimeVue; состояние — Pinia; клиент — только сгенерированный (правило 14 `AGENTS.md`).
- Фильтры, сортировка и страница живут в URL: ссылку на отфильтрованный список можно переслать.
- Ошибка сервера с полями не показывается toast-ом, а остаётся в форме; без полей — toast с `user_message` и `request_id`.
