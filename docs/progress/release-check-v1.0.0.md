# Сверка контракта и реализации перед v1.0.0 (I6-02)

Состояние на 25.10.2026, ветка v0.6.0; контракт `contracts/openapi-product-api-v1.yaml` 1.1.0. Разделы 1–6 — сверка как она была; исправления ветки v0.6.1 и повторная сверка с прототипами продуктов — раздел 7.

По промпту I6-02 этот отчёт ничего не исправляет. Два дефекта, найденные раньше, при подготовке прототипов (склонение `{days_left}` и остаток отсрочки в GRACE), исправлены в v0.6.0 до сверки.

## 1. OpenAPI реализации и контракт

**Как сверялось.** `manage.py spectacular --urlconf almi_license.urls` (drf-spectacular) выводит пути и методы. Схемы запросов и ответов Product API он вывести не может: представления — `APIView` без `extend_schema`. Генерация даёт 44 ошибки «unable to guess serializer» и 7 предупреждений о незарегистрированной аутентификации `ALMI-Signature`. Поэтому сверка пунктов разведена:

| Что | Чем проверяется | Результат |
|---|---|---|
| Пути и методы | `tests/test_contract_routes.py` (`make contract-check`, CI `contract`): каждая операция этапа 1 обслуживается с её методом; операции «(этап 2)» не обслуживаются; публичных маршрутов вне контракта нет | Совпадают: 15 операций этапа 1 |
| Схемы ответов | Ответы в тестах проверяются по компонентам OpenAPI и JSON Schema (`tests/contract.py`): `LeaseResponse` (4 теста), `ReleaseResponse`, `TrustBundle`, `Discovery`, `ServerRegisterResponse`, `AlkFile`, `Problem` (2); схемы `lease`, `alk-lic`, `alk-file`, `alk-usage`, `package`, `receipt`, `trust`, `cert` | Совпадают там, где проверяются |
| Схемы запросов | Тела строят тесты и DL по контракту; сервер проверяет их сериализаторами, а не схемой OpenAPI | Автоматической сверки нет |
| Коды ответов | Ниже | Расхождения |

**Расхождения:**

1. **`/api/activate/` (GET и POST, `legacyActivate*`).** Контракт: `200`, `429`. Реализация (`apps/compat/api/views.py`, `LEGACY_STATUS`): ещё `400` (неверные параметры), `403` (срок истёк), `404` (ключ не найден), `409` (нет мест) — по предварительным фикстурам E00-09. Нужно либо дописать коды в контракт (добавляющее изменение, задача с меткой contract), либо отвечать 200 с `success: false` — выбор зависит от записи реальных ответов ЛК (вопрос 16).
2. **Подписка Nextcloud (`nextcloudSubscription`).** Контракт: `200`, `404`, `429`. Реализация: ещё `400` (`{"message": "Bad request"}`) при теле без `instanceId`. Не описано в контракте.
3. **`activate`, код `422 unsupported_product_version`.** В контракте есть, сервер его не возвращает: ограничений версий продукта в лицензии нет (раздел 2).
4. **`activate`, код `426 upgrade_required`.** В контракте есть, сервер его не возвращает. Заголовок `ALMI-Protocol` («обязательно», раздел 4 документа 2) сервер не проверяет: запрос без него принимается. Модуль DL этот заголовок тоже не отправляет (`sdk/cpp/src` его не содержит). Если включить проверку на сервере без доработки DL, все запросы модуля будут отклонены.
5. **`offline/requests`.** В контракте тело `inline` (`multipart/form-data`) без компонента; реализация принимает поля `file`, `captcha_id`, `captcha_answer`. Совпадает с описанием операции, но схема не сверяется автоматически.
6. **Аутентификация.** Схема `ALMI-Signature` в контракте описана как заголовок; в схеме drf-spectacular её нет: не зарегистрировано расширение `OpenApiAuthenticationExtension`. На поведение не влияет.
7. **`getTrust`.** Контракт: только `200`. Реализация: `503 maintenance` с `Retry-After: 300`, если пакет доверия не задан или не проходит проверку (`TRUST_BUNDLE_FILE`). Реакция DL на 503 — работа по аренде; в контракте кода нет.
8. **Операции этапа 2** (`seats:*`, `/api/integration/v1/*`) не реализованы. Это проверяется тестом и соответствует контракту.

## 2. Коды ошибок раздела 16 документа 2

Сервер выдаёт коды только через `infra/problems.py` (каталог совпадает с разделом 16). Места — где код возникает.

| Код | Где сервер его возвращает | Тест |
|---|---|---|
| `invalid_request` | `infra/problems.py` (ошибки разбора), сериализаторы Product API | `test_activate.py`, `test_check.py`, `test_captcha.py` и ещё 8 |
| `invalid_key_format` | `activation/domain/service.py:97` | `test_activate.py` |
| `captcha_required` | `api_product/api/views.py:327` | `test_captcha.py` |
| `signature_invalid` | `api_product/auth.py:77`, `api_sync/api/auth.py:46` | `test_request_signature.py`, `test_activate.py` и ещё 10 |
| `clock_skew` | `api_product/auth.py:79`, `api_sync/api/auth.py:73` | `test_request_signature.py` |
| `license_revoked` | `activation/domain/service.py:103,144`, `compat/domain/nextcloud.py:133` | `test_activate.py`, `test_check.py` |
| `license_expired` | `activation/domain/service.py:151` | `test_activate.py` |
| `product_mismatch` | `activation/domain/service.py:107,149` | `test_activate.py`, `security/test_key_enumeration.py` |
| `key_not_found` | `activation/domain/service.py:101` | `test_activate.py`, `test_key_enumeration.py`, `api_sync/test_usage.py` |
| `activation_not_found` | `activation/domain/check.py:56`, `release.py:64` | **нет** |
| `seats_exhausted` | `activation/domain/service.py:171` | `test_activate.py`, `test_seats_concurrency.py`, `api_sync/test_register.py` |
| `instance_conflict` | `activation/domain/service.py:238` | `test_activate.py` |
| `idempotency_conflict` | `api_product/api/views.py:143`, `packages/domain/usage.py:141` | `test_activate.py`, `api_sync/test_usage.py` |
| `activation_released` | `activation/domain/check.py:60` | `test_check.py` |
| `rebind_required` | `activation/domain/check.py:70` | `test_check.py` |
| `payload_too_large` | `activation/domain/events.py:36`, `packages/domain/usage.py:110`, `infra/problems.py:98` | `api_sync/test_usage.py` |
| `unsupported_product_version` | **не возвращается** (только в каталоге и в учёте отказов `stats/domain/denials.py`) | **нет** |
| `upgrade_required` | **не возвращается** (только в каталоге) | **нет** |
| `rate_limited` | `api_product/api/views.py:91`, `api_admin/api/views.py:86` | `test_rate_limits.py`, `api_admin/test_session.py` |
| `internal_error` | `infra/problems.py:148` (необработанное исключение) | `infra/test_problems.py` |
| `maintenance` | `api_product/api/views.py:421` (`getTrust` без пакета доверия) | `test_trust_discovery.py` |
| `validation_failed`, `not_authenticated`, `forbidden`, `not_found` (Admin API) | `infra/problems.py`, представления Admin API | `api_admin/test_problem_codes.py` и др. |

Коды без теста:

- `activation_not_found`. Через API почти недостижим: запрос `check` или `release` с неизвестной активацией отклоняется раньше, на проверке подписи (`401 signature_invalid`: ключ устройства ищется по активации). Реакция DL на оба кода одинаковая — повторная активация. Код возникает только при удалении активации между проверкой подписи и транзакцией.
- `unsupported_product_version` — не реализован.
- `upgrade_required` — не реализован.

Реакции DL на коды проверяет `ModuleTest.ServerErrorsMapToResultsWithTheUserMessage`. Неизвестный код 4xx, по разделу 16, обрабатывается как `invalid_request`, но отдельного теста на это нет.

## 3. Функции `LM_*` и тесты `sdk/cpp/tests`

Все 24 функции `license_module.h` вызываются в `abi_test.cpp`. Для 12 из них это единственная проверка через ABI — «не инициализировано» на заглушке (`AbiStub.ResultFunctionsReportNotInitialized`). Поведение проверяется на уровне `Module` (тонкая обёртка ABI, `src/license_module.cpp`) и в E2E через `lm-demo` (публичный ABI).

| Функция | ABI (`abi_test.cpp`) | Поведение (`module_test.cpp`) | E2E (`lm-demo`, прототипы) |
|---|---|---|---|
| `LM_Initialize`, `LM_InitializeEx`, `LM_Shutdown` | да (+ `CorruptedStoreIsReportedOnceAndReset`) | да | да |
| `LM_GetStatus`, `LM_GetStatusEx`, `LM_HasFeature` | да | да | `status`, `features`, mini-office |
| `LM_Activate` | да (триал без сервера) | да (10) | `activate` (8) |
| `LM_ActivateFromFile` | только «не инициализировано» | да (6) | `apply` (2) |
| `LM_ActivateByPhone` | `LM_ERR_UNSUPPORTED` (этап 2) | — | — |
| `LM_Deactivate` | только «не инициализировано» | да | `deactivate` |
| `LM_GenerateOfflineRequest` | только «не инициализировано» | да | `offline-request` |
| `LM_GetHwid` | да | — | — |
| `LM_CheckNow` | только «не инициализировано» | да (8) | `check` (7) |
| `LM_SetCallback` | только «не инициализировано» | да (1) | mini-office (вручную) |
| `LM_GetMessageCount`, `LM_GetMessage` | да | да (4) | `messages` |
| `LM_MarkMessageShown` | только «не инициализировано» | **нет** | `messages` (вызывается, результат не проверяется) |
| `LM_ReportUsage` | только «не инициализировано» | да (1) | mini-office (вручную) |
| `LM_GenerateRenewRequest` | только «не инициализировано» | да (1) | — |
| `LM_GenerateReleaseRequest` | только «не инициализировано» | **нет** | `release-request` |
| `LM_SetServerUrl` | только «не инициализировано» | **нет** | — |
| `LM_GetLastError` | только «не инициализировано» | да (9) | — |
| `LM_GetAbiVersion`, `LM_GetVersion` | да | — | `version` |

Функции без теста поведения:
- `LM_SetServerUrl` — нигде;
- `LM_MarkMessageShown` — правило повтора `repeat` после показа не проверяется;
- `LM_GenerateReleaseRequest` — только E2E.

## 4. Чек-лист раздела 18 документа 2 (АльтерОфис Desktop)

Каталог `tools/conformance`, упомянутый в разделе 18, пуст: набора тестов соответствия продукта нет. Ниже пункты подтверждены тестами модуля и E2E с `lm-demo` и `mini-office`, то есть для модуля, а не для АльтерОфис Desktop. Модуль в продукт ещё не встроен (E14-02…E14-04, вопрос 16).

| № | Проверка | Статус | Доказательство |
|---|---|---|---|
| 1 | Адрес сервера задаётся конфигурацией | Частично | `LM_Config.server_url` (все тесты модуля), `lm-demo --server`, `ALMI_LICENSE_SERVER_URL` в mini-office (E2E 12). Чтение `config.json` тестом не покрыто |
| 2 | `instance_id` создаётся один раз и сохраняется | Да | `InstanceIdentity.InstanceIdIsRandomUuidV4`, `SecureStoreTest.SaveAndLoad`, `CheckRenewsTheLeaseAndWorksWithoutNetworkAfterRestart` |
| 3 | Активация онлайн и файлами, повтор без нового места | Да | E2E 1, 2; `test_repeat_activation_takes_no_seat`; mini-os (E2E 12) |
| 4 | Проверка при старте в фоне и по `next_check_at` с повторами | **Не подтверждено** | Повторы транспорта — `Transport.*`. Фоновая проверка во всех тестах модуля отключена (`background_check = false`) |
| 5 | Работа без сети по аренде | Да | E2E 1 (сервер недоступен — FULL), `CheckRenewsTheLeaseAndWorksWithoutNetworkAfterRestart` |
| 6 | Отклонение аренды: подпись, чужой `aud`/`instance_id`, меньший `seq` | Да | 12 векторов `jws/`, `LeaseVerifierCases.*`, `AnswerFileOfAnotherDeviceOrAnOldLeaseIsRefused` |
| 7 | Перевод часов назад | Да | `ClockStateTest.*`, `ClockRollbackDoesNotMoveTheLicenseBack`, E2E 8 |
| 8 | Все состояния раздела 7 отображаются по разделу 15.4 | Для модуля — да | `ModuleHelpers.ModesAndFeatures`, 39 векторов политики. Отображение в продукте — mini-office вручную |
| 9 | Ограничение функций только через `LM_HasFeature` | Требование к продукту | mini-office — образец; в продукте не проверено |
| 10 | `monitor` не ограничивает функции | Да | E2E 7, векторы политики |
| 11 | Откат блока при ближайшей проверке | Да | E2E 6 («Снять блок»), векторы |
| 12 | Директивы | **Частично** | Модуль выполняет `refresh_now`, `set_check_interval`, `release`, `rebind`. `update_trust`, `show_message`, `set_server_url` он сообщает серверу как неподдерживаемые (`unsupported_directives`) и не выполняет |
| 13 | Неизвестные поля, директивы, состояния, функции — без сбоя | Частично | Неизвестные директивы — `unsupported_directives`. Отдельного теста на неизвестные поля и состояния аренды нет |
| 14 | Тексты сервера без изменений | Да | `TrialWithoutLeaseThenOnlineActivation`, `DaysLeftOfTheMessages…` (подстановки) |
| 15 | Освобождение при деинсталляции | **Не подтверждено** | Требование к установщику продукта; модуль даёт `LM_Deactivate` |
| 16 | Все коды раздела 16 и неизвестные | Частично | `ServerErrorsMapToResultsWithTheUserMessage`; неизвестный 4xx — без теста |
| 17 | В журналах нет ключа, аренды, ключа устройства | Да | E2E 14 (журналы сервера); `SecureStoreTest.ValuesAreNotStoredInTheClear`. Журналов продукта ещё нет |
| 18 | Проверка при запуске ≤ 50 мс | **Не подтверждено** | Замера нет |
| 19 | Системный прокси и корпоративный корневой сертификат | **Не подтверждено** | `platform::SystemProxy`, `SystemTlsTrust` реализованы; тестов и ручного протокола нет (стенды Windows — вопрос 28) |
| 20 | Центральный и локальный сервер без изменений продукта | Да | E2E 3, 4 (тот же `lm-demo`) |

## 5. TODO, FIXME, xfail, skip

| Где | Что | История |
|---|---|---|
| `sdk/cpp/tests/secure_store_test.cpp:123` | `GTEST_SKIP` на Windows: нет прав POSIX; хранилище защищено DPAPI и ACL | E13-05; на Windows проверяется `MachineSealerRoundTrip` |
| `sdk/cpp/tests/secure_store_test.cpp:134` | `GTEST_SKIP` без `/etc/machine-id` | E13-05; в CI идентификатор есть |
| `server/tests/api_product/test_lm_demo_offline.py:26` | `skipif` без `LM_DEMO` | E08-01; в CI выполняется задачей `offline-e2e` |
| `tests/e2e/conftest.py:30`, `tests/e2e/test_prototypes.py:33` | `skip` без переменных стенда | E16-04; в CI выполняются задачей `e2e-stand` |

TODO и FIXME в коде нет; `xfail` нет. Совпадения `XXXX` в `keys.py`, `management.py`, `test_captcha.py` — это формат ключа и неверный ответ капчи, а не пометки.

## 6. Итог для readiness gate

- Контракт и реализация совпадают по путям и методам; схемы ответов проверяются тестами. Расхождения 1–4 и 7 раздела 1 — предмет решения: контракт (метка contract) или реализация.
- Нереализованные коды: `unsupported_product_version`, `upgrade_required` (вместе с проверкой `ALMI-Protocol`).
- DL: нет тестов поведения `LM_SetServerUrl` и `LM_MarkMessageShown`; не подтверждены пункты 4, 15, 18, 19 чек-листа; директивы `update_trust`, `show_message`, `set_server_url` не выполняются.
- Набор `tools/conformance` отсутствует. Встраивание в АльтерОфис Desktop не начато (вопрос 16).

## 7. Исправления v0.6.1 и повторная сверка с прототипами (26.10.2026)

### 7.1. Что исправлено по разделам 1–6

| Находка | Исправление | Проверка |
|---|---|---|
| Раздел 1, расхождения 1, 2, 7: коды `/api/activate/` (400/403/404/409), Nextcloud (400), `getTrust` (503) | Добавлены в контракт — 1.2.0, добавляющее изменение (метка contract, решение руководителя проекта) | `test_status_codes_of_the_adapters_and_trust_are_in_the_contract` |
| Раздел 1, расхождение 3; раздел 2: `422 unsupported_product_version` не возвращается | Поле лицензии «Версии продукта до» (`max_product_version`: `3` — все 3.x, `3.2` — все 3.2.x); активация более новой версии — 422 с `max_product_version` | `api_product/test_product_version.py`, `api_admin` (настройки лицензии), консоль |
| Раздел 1, расхождение 4; раздел 2: `426 upgrade_required`, `ALMI-Protocol` | DL отправляет `ALMI-Protocol: 1` в каждом запросе. Сервер отвечает 426 на другое значение, а запрос без заголовка принимает, считает (`almi_product_requests_without_protocol_total`) и пишет в журнал — чтобы не отклонить модули до 1.0 | `api_product/test_protocol.py` (8), `EveryRequestCarriesTheProtocolVersion` |
| Раздел 3: нет тестов `LM_SetServerUrl`, `LM_MarkMessageShown`, `LM_GenerateReleaseRequest` | Тесты поведения | `SetServerUrlMovesTheModuleAndEmptyReturnsToTheConfiguredOne`, `MarkMessageShownFollowsTheRepeatOfTheLease`, `ReleaseRequestFileNamesTheActivation` |
| Раздел 4, пункт 12: директивы `update_trust`, `show_message`, `set_server_url` не выполнялись | DL выполняет все 7 директив v1, каждую один раз (по `id`). `set_server_url` — только https, с возвратом на прежний адрес через 14 дней молчания нового. Консоль отправляет команды активации и всем активациям лицензии | `DirectivesRunOnceAndAreReportedAtTheNextCheck` и ещё 8 в `module_test.cpp`; `api_admin/test_directives.py` (9); conformance 12–14 |
| Раздел 4, пункты 4, 13, 16, 18, 19 | Тесты добавлены, см. 7.3 | См. 7.3 |
| Раздел 4: каталог `tools/conformance` пуст | Набор соответствия продукта: `tests/e2e/test_conformance.py`, описание — `tools/conformance/README.md` | `make e2e-stand` |

Остались без изменений: расхождения 5, 6 и 8 раздела 1 (не влияют на поведение), код `activation_not_found` без теста через API (раздел 2), пункт 15 (требование к установщику).

### 7.2. Дефекты, найденные повторной сверкой с прототипами

Набор соответствия гоняет mini-office (C ABI, как АльтерОфис Desktop) на стенде с настоящими сервером, консолью и прокси. Он нашёл дефекты, которые тесты модуля с поддельным сервером не видели:

| № | Где | Дефект | Исправление |
|---|---|---|---|
| 1 | DL | `user_message` ошибок сервера в контракте — объект по языкам, модуль ждал строку. Пользователь не видел текстов отказа сервера | `UserMessage()`: язык, затем `ru`, затем строка; поддельный сервер тестов отвечает объектом |
| 2 | DL | Директива `release` вызывала обработчик событий под блокировкой состояния. Обработчик продукта, читающий состояние, зависал навсегда | Уведомление вне блокировки; тест `ReleaseDirectiveFreesTheSeatAndNotifies` |
| 3 | DL | `update_trust` при ответе 503 с `Retry-After: 300` повторял запрос минутами и держал проверку | Без повторов; тест `UnavailableTrustBundleDoesNotHoldTheCheck` |
| 4 | DL | `refresh_now` не будил фоновую проверку: она ждала прежнего срока | `WakeBackground()`; тест `BackgroundCheckRunsWhenDue` |
| 5 | Сервер | Сообщение «Нет свободных мест (2 из 1)» при лимите 1: число мест без резерва | В тексте — лимит с резервом |
| 6 | Комплекты | Консоль на порту, отличном от 443 (центральный), и на 443 (локальный): вход отклонялся проверкой CSRF | Доверенные источники — с портом и без; вход проверяется в CI `central-install` |
| 7 | Комплект локального | Мастер первого запуска падал с `PermissionError`: каталог ключа сервера в томе принадлежал root | Каталог `/var/lib/almi` создаётся в образе с владельцем `app`; `check.sh` проверяет запись |
| 8 | Консоль | Шрифт без кириллицы в части систем, шаги импорта без номеров, пустые названия в статистике | Системный шрифт, шаги 1–5, «не сообщается» |

### 7.3. Чек-лист раздела 18 после исправлений

| № | Было | Стало | Доказательство |
|---|---|---|---|
| 1 | Частично | Да | conformance 01: адрес из переменной окружения продукта |
| 4 | Не подтверждено | Да | conformance 04 (`refresh_now` будит фоновую проверку), `BackgroundCheckRunsWhenDue` |
| 12 | Частично | Да | Все 7 директив: conformance 12–14 из консоли, тесты модуля |
| 13 | Частично | Да | Поддельный сервер отвечает неизвестными полями; неизвестные директивы — `unsupported_directives` |
| 16 | Частично | Да | `UnknownCodesFollowSection16` (объект, строка, 5xx), conformance 15–16 |
| 18 | Не подтверждено | Да | `StartWithAStoredLeaseTakesAtMostFiftyMilliseconds`, conformance 18 |
| 19 | Не подтверждено | Да на Linux | conformance 19: системный прокси (`https_proxy`) и корпоративный CA в системном хранилище. Windows — после стендов (вопрос 28) |
| 15 | Не подтверждено | Без изменений | Требование к установщику продукта |

Пункты 8 и 9 по-прежнему подтверждены для mini-office, а не для АльтерОфис Desktop (E14-*, вопрос 16).

### 7.4. Итог

- Тесты: сервер 552, ctest 116, сквозные 30 (из них 17 — соответствие продукта), vitest 61. Все проходят на стенде; CI — на PR ветки v0.6.1.
- Из итога раздела 6 закрыты: расхождения кодов (контракт 1.2.0), 422 и 426, тесты трёх функций DL, директивы, `tools/conformance`, пункты 4, 12, 13, 16, 18, 19.
- Остаются: пункт 15 (установщик), встраивание в АльтерОфис Desktop (вопрос 16), проверка на Windows (вопрос 28). Тег `contract-v1.2.0` ставит руководитель проекта.
