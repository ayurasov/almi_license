# Негативные тесты этапа 1 (E16-06, промпт I5-03)

Критерий 12 раздела 15.6 и раздел 13 документа 1. Реакции — по разделу 16 документа 2. Тесты живут рядом с кодом, который проверяют: серверные — в `server/tests` (прогон `make test-server`), тесты модуля — в `sdk/cpp/tests` (`make test-dl`), сквозные — в `tests/e2e` (`make e2e-stand`).

| Случай | Ожидаемая реакция сервера | Ожидаемая реакция DL | Тесты |
|---|---|---|---|
| Изменён байт полезной нагрузки аренды | — | `signature_invalid`, аренда не принята | векторы `contracts/vectors/jws` (`make vectors`); `sdk/cpp/tests/lease_verifier_test.cpp`; `ModuleTest.OfflineRequestAndAnswerFile` (испорченный `.alk-lic`) |
| Подпись от dev-ключа в продуктивной сборке | — | `chain_invalid` → `LM_ERR_INVALID_SIGNATURE`, режим не меняется | `ModuleTest.LeaseOfTheDevRootIsRefusedByAProductionBuild`; `TrustRootsText`, встроенные корни по `LM_TRUST_ROOTS` |
| `chain` от другого заказчика (сертификат локального сервера чужого заказчика) | — | `scope_mismatch` | `LeaseVerifierCases.LocalServerIsLimitedToItsScope` |
| Понижение `seq`, повтор старой аренды | аномалия `lease_seq_anomaly` в журнале; следующая аренда `max+1` | `seq_not_greater`, текущая аренда остаётся | `test_client_seq_ahead_of_the_server_is_an_anomaly`, `test_seq_always_grows` (`server/tests/api_product/test_check.py`); `LeaseVerifierCases.SubjectAndTime`; `ModuleTest.AnswerFileOfAnotherDeviceOrAnOldLeaseIsRefused` |
| Перевод часов на устройстве | событие `clock_rollback_detected` в журнале аудита | состояние не откатывается; одно событие на эпизод | `ClockStateTest.*` (`clock_state_test.cpp`), `ModuleTest.ClockRollbackDoesNotMoveTheLicenseBack`, `ModuleTest.QueuedEventsAreSentOnceAfterACheck`; сценарий 8 `tests/e2e` (триал) |
| Повтор `nonce` запроса | `401 signature_invalid` | повтор с новым `nonce` (`Transport`) | `test_nonce_replay_is_refused` (`server/apps/api_product/tests/test_request_signature.py`); `Transport.EveryAttemptIsSignedWithAFreshNonce` |
| Запрос с чужим `activation_id` | `401 signature_invalid` | — | `test_keyid_must_be_the_checked_activation`, `test_signature_by_another_key` (`test_check.py`); `test_signature_must_be_of_the_named_activation` (`test_events.py`) |
| `.alk-lic` другого устройства | — | файл не применяется, текущая аренда остаётся | `ModuleTest.AnswerFileOfAnotherDeviceOrAnOldLeaseIsRefused`; чужой `nonce` — `ModuleTest.OfflineRequestAndAnswerFile` |
| Файлы повышенного размера (`.alk-req`, `.alk-usage`, `.alk`) | `400 invalid_request` / `413` до разбора | `LM_ERR_INVALID_FILE` (64 КБ) | `test_oversized_files_are_refused_before_parsing` (`server/tests/security/test_files.py`); `test_size_limit` (импорт ЛК, 20 МБ) |
| Пакет локального сервера другого сервера или заказчика | отклоняется, прежний пакет остаётся | — | `test_package_of_another_local_server_is_refused` (`test_files.py`); `test_package_checks` (подделка, чужой корень, срок) |
| XLSX с формулами и внешними ссылками | формулы не вычисляются, ссылки не открываются; экспорт пишет такие значения как текст | — | `server/tests/security/test_spreadsheets.py`; CSV журнала — `test_audit.py` (защита от формул) |
| Перебор ключей | ответы «нет ключа», «отозвана», «другой продукт» за одинаковые два запроса; время различается не более чем на 20 % | — | `server/tests/security/test_key_enumeration.py`; лимиты частоты — `test_rate_limits.py`, капча портала — `test_captcha.py` |

## Найдено и исправлено в I5

- Экспорт статистики XLSX записывал имя заказчика вида `=HYPERLINK(...)` как формулу. Теперь строки всегда пишутся как текст.
- Ключ другого продукта отвечал вдвое дольше неизвестного: перед ответом блокировалась лицензия и загружались её условия. Теперь отзыв и продукт проверяются до транзакции, одним запросом по ключу (`key_facts`); под блокировкой проверка повторяется.
- Модуль DL отправлял `Content-Type` дважды, и онлайн-запросы получали 400. Метка триала лежала в `data_dir`, поэтому переустановка начинала триал заново. Оба дефекта найдены сквозными сценариями, см. `docs/decisions.md`.
