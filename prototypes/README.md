# Прототипы продуктов для ручных тестов сервера лицензирования

Три мини-продукта взаимодействуют с сервером так же, как настоящие:

| Прототип | Аналог | Как говорит с сервером | Субъект |
|---|---|---|---|
| [`mini-office`](mini-office/) | АльтерОфис Desktop | Модуль DL через публичный C ABI (`license_module.h`): Product API, подписанные запросы, аренды, офлайн-файлы | `device` |
| [`mini-web`](mini-web/mini_web.py) | АльтерОфис Web (Nextcloud) | Запрос приложения `support`: `POST /apps/zammad_organisation_management/api/query/subscription/{key}` | `server_instance` |
| [`mini-os`](mini-os/alteros-register.sh) | АльтерОС (`registration.sh`) | `GET /api/activate/?data=&host=&lic=` | `os_node` |

Назначение:
1. Ручная проверка сервера: консоль, политики, места, сроки, статистика.
2. Образец для переноса в настоящие продукты: каждый файл короткий, а вызовы и реакции на ответы подписаны комментариями со ссылками на разделы документов 2 и 5.

Прототипы не меняют контракт и не обходят проверки. `mini-office` собирается с dev-корнем и принимает только аренды пробного сервера: в окне «О программе» у него написано «Тестовая сборка».

## 1. Пробный сервер

Вариант А — центральный сервер на Ubuntu 24.04 по [docs/deployment.md](../docs/deployment.md), с публичными dev-ключами:

```sh
cd deploy/central && cp .env.example .env    # SERVER_NAME — имя хоста
DEV_ISSUER=1 ADMIN_USER=admin ./install.sh
(umask 077; docker compose run --rm -T api manage seed_minimal --trial --out - > seed-keys.json)
```

Вариант Б — окружение разработчика: `make up`, затем `make seed`, затем
`(umask 077; docker compose -f deploy/dev/docker-compose.yml exec -T api python manage.py seed_minimal --trial --out - > keys.json)`.

`seed_minimal` создаёт набор seed-minimal (документ 7, раздел 4): 3 тестовых заказчика и 10 лицензий. Полные ключи попадают только в файл `--out` (права 0600) или, при `--out -`, в stdout в виде JSON; в остальном выводе — маски. Храните файл ключей как секрет стенда.

| № | Продукт | Тип | Что проверять |
|---|---|---|---|
| 1 | desktop, standard | подписка, 3 места | активация, места, освобождение |
| 2 | desktop, professional | бессрочная | макросы, совместная работа |
| 3 | desktop, standard | пробная, 14 дней | `trial` |
| 4 | desktop, standard | срок через 10 дней | NOTICE, баннер и окно |
| 5 | desktop, standard | срок прошёл 5 дней назад | GRACE, затем RESTRICTED |
| 6 | desktop, professional | NFR, `monitor` | функции не ограничиваются |
| 7 | web, enterprise | 10 пользователей | лимит пользователей |
| 8 | web, enterprise | 5 активных, срок через 20 дней | `onlyCountActiveUsers`, предупреждение о сроке |
| 9 | alteros, workstation | 2 станции | регистрация, повтор |
| 10 | alteros, workstation | бесплатная | `free` |

Сертификат пробного сервера должен быть доверенным для клиента. Самоподписанный сертификат `install.sh` добавьте в системное хранилище машины с прототипом:

```sh
sudo cp tls/server.crt /usr/local/share/ca-certificates/almi-trial.crt && sudo update-ca-certificates
```

Для `mini-web` и `mini-os` вместо этого подойдут `--cafile` и `--cacert`. Модуль DL проверку TLS не отключает.

## 2. mini-office (АльтерОфис Desktop)

Сборка (Ubuntu 24.04 или Windows; зависимости модуля — через vcpkg, как для `sdk/cpp`):

```sh
make prototypes            # sdk/cpp/build-proto/bin/mini-office и mini-office-stub (каталог — DL_BUILD-proto)
sdk/cpp/build-proto/bin/mini-office --server https://license.test.local
```

Команды вводятся в приглашении `>` или подаются скриптом на stdin; `help` выводит список.

| Команда | Что делает | Вызовы модуля |
|---|---|---|
| `new`, `open Ф`, `show`, `type Т` | документ | `LM_HasFeature("create" / "view" / "edit")` |
| `save [Ф]`, `export Ф`, `print`, `macro`, `share` | функции редакции | `LM_HasFeature("save" / "export" / "print" / "macros" / "collaboration")` |
| `about` | окно «О программе» | `LM_GetStatusEx`, `LM_GetVersion`, сообщения `placement=about` |
| `messages` | окна и уведомления | `LM_GetMessage`, `LM_MarkMessageShown` |
| `license activate КЛЮЧ` | онлайн-активация | `LM_Activate(…, LM_ACT_ONLINE)` |
| `license offline-request КЛЮЧ Ф` → портал → `license apply Ф` | офлайн-активация | `LM_GenerateOfflineRequest`, `LM_ActivateFromFile` |
| `license renew-request Ф`, `license release-request Ф` | продление и освобождение файлами | `LM_GenerateRenewRequest`, `LM_GenerateReleaseRequest` |
| `license deactivate`, `license check`, `license hwid`, `license server URL` | — | `LM_Deactivate`, `LM_CheckNow`, `LM_GetHwid`, `LM_SetServerUrl` |
| `quit` | выход со счётчиками | `LM_ReportUsage`, `LM_Shutdown` |

Что ещё реализовано:
- Баннеры показываются перед каждым приглашением. Окна (`dialog`) — один раз, затем `LM_MarkMessageShown`.
- Смена состояния фоновой проверкой приходит через `LM_SetCallback`. Колбэк только ставит флаг, интерфейс перерисовывает основной цикл.
- Централизованная настройка (E14-06): `ALMI_LICENSE_SERVER_URL` и `ALMI_LICENSE_KEY`. Ключ активируется при первом запуске без участия пользователя; повторный запуск место не занимает; ключ не печатается.
- `mini-office-stub` — та же программа на заглушке модуля: `LM_STUB_MODE=GRACE LM_STUB_FEATURES=view,edit sdk/cpp/build-proto/bin/mini-office-stub`. Нужна, чтобы проверить интерфейс во всех состояниях без сервера.

Сценарии ручного теста:

1. Без ключа запускается пробный период с баннером «Пробный период: осталось 30 дней.».
2. `license activate <ключ 1>` — FULL. В консоли сервера, в разделе «Активации», появится запись с версией `0.1.0`.
3. `macro` на standard отказывает: «не входит в лицензию». На ключе 2 (professional) — работает.
4. Ключ 1 на четвёртом компьютере (другой `--data`): после 3 мест резерв, затем отказ `seats_exhausted`.
5. Ключ 4 — NOTICE: баннер и окно о сроке. Ключ 5 — GRACE: окно «Срок лицензии истёк…», затем `license check` после конца отсрочки — RESTRICTED: сохранение остаётся, макросы отключены (профиль `commercial`).
6. Отзыв лицензии в консоли и `license check` — REVOKED.
7. Офлайн: `license offline-request <ключ> req.alk-req`, загрузка на портале `https://SERVER/offline`, затем `license apply resp.alk-lic`.
8. `ALMI_LICENSE_KEY=<ключ> mini-office --data /tmp/pc9` — активация без участия пользователя; повторный запуск место не занимает.

## 3. mini-web (АльтерОфис Web)

Только стандартная библиотека Python 3.12 (есть в Ubuntu 24.04):

```sh
python3 prototypes/mini-web/mini_web.py --port 8088 --state /tmp/mini-web.json [--cafile ca.crt] [--enforce]
# http://127.0.0.1:8088/ → «Поддержка»: support.backend = https://SERVER, ключ подписки (лицензия 7 или 8)
python3 prototypes/mini-web/mini_web.py --state /tmp/mini-web.json --check    # одна проверка (cron), JSON
```

Что показывает:
- ответ сервера (`endDate`, `extendedSupport`, `amountOfUsers`, `onlyCountActiveUsers`, `accountManagerInfo`);
- предупреждения о сроке (за 30 дней), о превышении пользователей, об окончании расширенной поддержки.

Без связи с сервером действует последний ответ, как в приложении `support`.

Этап 1 — только уведомления (документ 2, раздел 11.1). Флаг `--enforce` показывает поведение для переноса в продукт на следующем этапе:
- после достижения лимита не создаются новые пользователи;
- после `endDate` — только чтение.

Сценарии ручного теста:
- добавьте 11 пользователей при лимите 10 — предупреждение; в консоли сервера в статистике лицензии превышение пользователей;
- выключите часть пользователей на лицензии 8 — считаются только активные;
- отзовите лицензию — «Подписка не найдена»;
- новый `instanceId` (удалите файл состояния) — вторая активация; на лицензии с одним экземпляром второй экземпляр займёт резерв, если он есть в профиле. Адаптер отвечает по правилам приложения `support`: отказ в месте он не показывает как ошибку, смотрите активации в консоли.

## 4. mini-os (АльтерОС)

```sh
ALMI_LICENSE_KEY=<ключ 9> prototypes/mini-os/alteros-register.sh --server https://SERVER --state /tmp/os register
prototypes/mini-os/alteros-register.sh --state /tmp/os status
ENFORCE=1 prototypes/mini-os/alteros-register.sh --state /tmp/os-none update
```

Как устроены параметры:
- `data` — MD5 от `/etc/machine-id`;
- `host` — имя хоста;
- ключ берётся из `ALMI_LICENSE_KEY` или запрашивается без эха. Аргументом он не передаётся; в состояние пишутся только последние 4 символа.

`--html` разбирает HTML-страницу ЛК вместо JSON.

Этап 1 — режим наблюдения: отказ регистрации не мешает ОС (`update` разрешает обновления). `ENFORCE=1` показывает будущее поведение — без регистрации обновлений нет.

Сценарии ручного теста:
- повторная регистрация того же компьютера отвечает «уже активирована» и место не занимает;
- на лицензии 9 (2 станции) третий компьютер займёт резерв — `ceil(2 × 3 / 100) = 1` место профиля `commercial`; «Превышено количество активаций» получит четвёртый;
- 11-й запрос за час с одним ключом получает «Слишком много попыток» (10 в час на ключ); с разными ключами — 21-й запрос с одного IP (лимиты ЛК 2.0).

Ключ передаётся curl через stdin (`lic@-`) и не виден в списке процессов; `--server` принимает только `https://`.

## 5. Перенос в настоящие продукты

| Что | Где в прототипе | Куда в продукте |
|---|---|---|
| Инициализация, адрес сервера, ключ администратора | `mini-office/src/main.cpp`: `main`, `ActivateConfigured` | Запуск приложения; MSI `LICENSE_SERVER_URL`/`LICENSE_KEY`, DEB/RPM `ALMI_LICENSE_*` |
| Проверка функции перед действием | `Editor::Allowed` | Каждая команда меню и кнопка (список функций — `catalog-v1.json`) |
| Баннер, окна, «О программе» | `ShowMessages`, `About` | Панель уведомлений, модальные окна, окно «О программе» (документ 5) |
| Диалог «Лицензия» | `License` | Окно лицензии: ключ, файлы, освобождение |
| Колбэк состояния | `OnLicenseEvent` | Поток интерфейса через очередь событий |
| Подписка Nextcloud | `mini_web.py`: `check_subscription`, `evaluate` | Приложение `support` (меняется только на этапе 2) |
| Регистрация ОС | `alteros-register.sh`: `register` | `registration.sh`; на этапе 2 — агент `almi-license-agent` |

Подробные правила подключения — в [docs/integration/product-guide.md](../docs/integration/product-guide.md).

## 6. Проверки в CI

- `make prototypes` собирает `mini-office` и `mini-office-stub`, прогоняет сценарий на заглушке и линтеры `mini-web` и `mini-os`.
- `make e2e-stand`, сценарий 12 (`tests/e2e/test_prototypes.py`): все три прототипа работают против HTTPS-стенда.
