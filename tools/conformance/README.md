# Проверка соответствия продукта (раздел 18 документа 2)

Продукт считается подключённым, когда подтверждены все 20 пунктов чек-листа. Проверка состоит из трёх уровней:

| Уровень | Что проверяет | Где | Запуск |
|---|---|---|---|
| Модуль | Поведение DL за C ABI: аренды, часы, директивы, коды, хранилище, время старта | `sdk/cpp/tests` (`ModuleTest.*`, `LeaseVerifierCases.*`, `ClockStateTest.*`, векторы `contracts/vectors`) | `make test-dl`, CI `test-dl` (Linux и Windows) |
| Продукт на стенде | Продукт с модулем против настоящего сервера по HTTPS: конфигурация, активации, состояния, функции, директивы из консоли, прокси | `tests/e2e/test_conformance.py`; продукт — `prototypes/mini-office` | `make e2e-stand`, CI `e2e-stand` |
| Встраивание | То, что делает установщик и интерфейс продукта: деинсталляция, отображение окон, свойства MSI | Ручной протокол по `prototypes/README.md` | Команда продукта |

Настоящий продукт проверяется так же, как прототип: тесты `test_conformance.py` управляют `mini-office` через stdin. Для АльтерОфис Desktop нужен такой же тестовый вход (командная строка или автоматизация интерфейса) либо ручной протокол по таблице ниже.

## Пункты и доказательства

| № | Проверка | Модуль | Продукт на стенде (`test_conformance.py`) |
|---|---|---|---|
| 1 | Адрес сервера из конфигурации | `LM_Config.server_url`, `config.json` | `test_01_…` — `ALMI_LICENSE_SERVER_URL` и `ALMI_LICENSE_KEY` без параметров запуска |
| 2 | `instance_id` создаётся один раз | `InstanceIdentity.*`, `SecureStoreTest.*` | `test_02_03_…` — перезапуск и повторная активация: та же активация и тот же `instance_id` |
| 3 | Онлайн и файлами, повтор без нового места | `OfflineRequestAndAnswerFile` | `test_02_03_…` — онлайн, повтор, портал `.alk-req` → `.alk-lic` |
| 4 | Проверка в фоне и по `next_check_at` | `BackgroundCheckRunsWhenDue`, `Transport.*` (повторы) | `test_04_…` — `refresh_now` из консоли выполняет фоновая проверка |
| 5 | Работа без сети по аренде | `CheckRenewsTheLeaseAndWorksWithoutNetworkAfterRestart` | `test_05_…` |
| 6 | Отклонение чужой или изменённой аренды | 15 векторов `jws/`, `LeaseVerifierCases.*`, `AnswerFileOfAnotherDeviceOrAnOldLeaseIsRefused` | `test_06_…` — повреждённое хранилище не принимается |
| 7 | Перевод часов назад | `ClockStateTest.*`, `ClockRollbackDoesNotMoveTheLicenseBack` | `test_07_…` — GRACE остаётся после возврата часов |
| 8 | Все состояния | 39 векторов политики, `ModuleHelpers.ModesAndFeatures` | `test_08_09_…` — NOTICE → GRACE → RESTRICTED; `test_10_…` — наблюдение |
| 9 | Функции только через `LM_HasFeature` | — | `test_08_09_…`, `test_09_…` — отключаемые функции профиля и функции вне редакции |
| 10 | `monitor` не ограничивает | Векторы политики | `test_10_…` |
| 11 | Откат блока при ближайшей проверке | Векторы политики | `test_11_…` — «Снять блок» в консоли |
| 12 | Директивы | `DirectivesRunOnce…`, `SetCheckInterval…`, `ShowMessage…`, `SetServerUrl…`, `UpdateTrust…` | `test_12_14_…`, `test_12_set_server_url` — из консоли |
| 13 | Неизвестные поля, директивы, коды без сбоя | `DirectivesRunOnce…` (неизвестный тип), `UnknownCodesFollowSection16`, поле `unknown_field_of_a_later_server` во всех ответах тестового сервера | — |
| 14 | Тексты сервера без изменений | `ShowMessageIsShownUntilMarked`, `DaysLeftOfTheMessages…` | `test_12_14_…` — текст `show_message` в баннере дословно |
| 15 | Освобождение при деинсталляции | `DeactivateReleasesAndForgetsTheLease` | `test_15_16_…` — `LM_Deactivate`; вызов из деинсталлятора — протокол команды продукта |
| 16 | Коды раздела 16 и неизвестные | `ServerErrorsMapToResultsWithTheUserMessage`, `UnknownCodesFollowSection16` | `test_15_16_…` — `seats_exhausted` с `user_message` сервера |
| 17 | Нет ключа, аренды, ключа устройства в журналах | `SecureStoreTest.ValuesAreNotStoredInTheClear` | `test_17_…` — вывод и файлы продукта |
| 18 | Старт ≤ 50 мс | `StartWithAStoredLeaseTakesAtMostFiftyMilliseconds` | `test_18_…` — процесс целиком меньше секунды |
| 19 | Системный прокси и корпоративный корень | — | `test_19_…` — через CONNECT-прокси (`https_proxy`) и CA стенда в системном хранилище |
| 20 | Центральный и локальный сервер без изменений | — | E2E 3 и 4 (`test_scenarios.py`, тот же модуль через `lm-demo`) |

Адаптеры других продуктов (`mini-web` — Nextcloud, `mini-os` — `registration.sh`): `test_web_and_os_adapters`, а также E2E 9 и 12.
