# Развёртывание сервера лицензирования на Ubuntu 24.04 (E17-02)

Руководство администратора. Описывает то, что есть в коде этой версии: комплекты `deploy/central` (центральный сервер АЛМИ) и `deploy/local` (локальный сервер заказчика), скрипты, переменные и проверки. Расхождения со спецификациями собраны в разделе 14.

## 1. Что разворачивается

| Сервер | Где | Комплект | Откуда образы | Ключ подписи аренд |
|---|---|---|---|---|
| Центральный | Контур АЛМИ, `license.alter-os.ru` (пробный — любое имя) | `deploy/central` в checkout репозитория | Собираются на хосте из репозитория | Ключ выпуска, сертифицированный корневым ключом на церемонии |
| Локальный | Сеть заказчика | Архив `almi-license-local-<версия>.tar.gz` (`make bundle-airgap`) или `deploy/local` | Из архива (`docker load`), без интернета | Ключ сервера, его создаёт мастер первого запуска; сертификат выдаёт центральный сервер |

Сервисы обоих комплектов одинаковые (один образ, режим задаёт `DEPLOYMENT_MODE`):

| Сервис | Образ | Назначение |
|---|---|---|
| `db` | `postgres:17` | База данных; том `db` |
| `migrate` | `almi-license` | Миграции владельцем таблиц `almi`, затем права роли приложения `almi_app`; завершается |
| `api` | `almi-license` | Product API, Admin API, Sync API, адаптеры совместимости; Gunicorn + Uvicorn на `:8000` внутри сети compose |
| `worker` | `almi-license` | Очередь задач: автоосвобождение, отчёты об использовании, обмен с центральным сервером |
| `console` | `almi-license-console` | Статика консоли (Nginx) |
| `gateway` | `nginx:1.27` | TLS на `:443` (`HTTPS_PORT`), маршруты `/api/`, `/apps/`, `/.well-known/`, `/health`, `/ready`, остальное — консоль |
| `backup` | `postgres:17` | Профиль `ops`: только по `./backup.sh` |

`/metrics` наружу не публикуется (раздел 10).

## 2. Требования к хосту

- Ubuntu Server 24.04 LTS, x86-64.
- Центральный сервер: 4 vCPU, 8 ГБ ОЗУ, 100 ГБ SSD. Нагрузочный тест этапа 1 — 100 `check`/с и 20 `activate`/с при p95 до 500 мс (`make load`). Локальный сервер: 2 vCPU, 4 ГБ ОЗУ, 40 ГБ.
- DNS-имя сервера и сертификат TLS для него. Для пробной установки `install.sh` создаст самоподписанный.
- Открытый входящий порт 443. Исходящий доступ:
  - центральному серверу — к реестрам Docker Hub, PyPI и npm на время сборки образов;
  - локальному серверу в режиме «онлайн» — к центральному серверу по 443.
- Точное время: `systemd-timesyncd` или chrony. Сроки аренд и подписи запросов проверяются по часам сервера, допуск ±5 минут.

## 3. Подготовка хоста

```sh
# Обновления и базовые пакеты
sudo apt update && sudo apt -y full-upgrade
sudo apt -y install ca-certificates curl git openssl gnupg ufw

# Время
timedatectl set-ntp true && timedatectl status   # "System clock synchronized: yes"

# Docker Engine и плагин compose из репозитория Docker (в Ubuntu 24.04 docker.io старее, плагина compose нет)
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu noble stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update && sudo apt -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
docker version --format '{{.Server.Version}}'    # 24 или новее
docker compose version
```

Журналы контейнеров хранятся на хосте 14 дней (раздел 11 документа 7). Docker ротирует их по размеру, поэтому ограничьте размер в `/etc/docker/daemon.json`:

```json
{ "log-driver": "json-file", "log-opts": { "max-size": "50m", "max-file": "10" } }
```

Затем выполните `sudo systemctl restart docker`.

Учётная запись и межсетевой экран:

```sh
sudo useradd -m -s /bin/bash -G docker almi   # администратор сервера; членство в docker равносильно root
sudo ufw allow OpenSSH && sudo ufw allow 443/tcp && sudo ufw enable
```

Docker публикует порты в обход правил ufw. Поэтому в compose наружу открыт только `gateway`; база и API доступны лишь внутри сети compose.

## 4. Центральный сервер

### Шаг 1. Код

```sh
sudo mkdir -p /opt/almi && sudo chown almi: /opt/almi
sudo -iu almi
git clone https://github.com/ayurasov/almi_license.git /opt/almi/almi_license
cd /opt/almi/almi_license && git checkout v1.0.0     # тег выпуска; для пробы — нужная ветка
cd deploy/central
```

### Шаг 2. Настройки

Скопируйте `.env.example` в `.env` (иначе это сделает `install.sh`) и задайте:

| Переменная | Значение |
|---|---|
| `ALMI_VERSION` | Тег образов, например `1.0.0`; показывается в `/.well-known/almi-license` |
| `SERVER_NAME` | Публичное имя: `LEASE_ISSUER = https://SERVER_NAME`, `ALLOWED_HOSTS`, CSRF |
| `HTTPS_PORT` | 443 |
| `TRUST_ROOTS` | Открытые корневые ключи АЛМИ `kid:pub` через запятую — из `root.pub.json` церемонии |
| `TRUST_BUNDLE_FILE` | `/etc/almi/trust/trust.json` — файл кладётся в `./trust/` |
| `WEB_CONCURRENCY`, `DATABASE_POOL_MAX_SIZE` | Процессы API и соединения каждого (по умолчанию 2 и 10; сумма с обработчиком меньше `max_connections` = 100) |
| `LOG_LEVEL` | `INFO` |

Остальные параметры имеют значения по умолчанию из `server/almi_license/settings/base.py`:
- лимиты частоты: `RATE_LIMIT_*`, раздел 4.7 документа 2;
- `OFFLINE_CAPTCHA_AFTER` — капча портала офлайн-активации.

Их можно добавить в `environment` сервиса в `docker-compose.override.yml`.

### Шаг 3. Первый запуск `install.sh` — ключ выпуска

```sh
./install.sh
```

Скрипт:
- проверяет Docker;
- создаёт секреты в `secrets/` (каталог 0700): пароли `almi` и `almi_app`, ключ Django, пароль резервных копий;
- собирает образы `almi-license:$ALMI_VERSION` и `almi-license-console:$ALMI_VERSION`;
- создаёт ключ выпуска: `keys/issuer.key` и `keys/issuer.pub`.

Закрытая часть создаётся на этом хосте генератором ОС и его не покидает.

Затем скрипт останавливается с сообщением, что нет сертификата.

### Шаг 4. Сертификат ключа выпуска (церемония)

На офлайн-рабочем месте церемонии (`tools/almi-keytool/README.md`; продуктивный корень — только на церемонии E17-04, двойной контроль):

```sh
uv run almi-keytool issue-cert --root ./root/root.key.json --subject-pub issuer.pub \
    --role issuer --kid c-2026-01 --valid-days 730 --out issuers/c-2026-01.jws
uv run almi-keytool export-trust --root ./root/root.key.json --issuers ./issuers --out trust.json
```

На сервер переносятся только открытые файлы:
- `issuers/c-2026-01.jws` → `keys/issuer.cert.jws`;
- `trust.json` → `trust/trust.json`;
- `kid` и `pub` из `root.pub.json` → `TRUST_ROOTS=root-2026:<pub>` в `.env`.

Корневой ключ и его пароль на сервер не попадают никогда.

**Пробный сервер без церемонии:** `DEV_ISSUER=1 ./install.sh` берёт публичные dev-ключи репозитория. Такой сервер:
- подписывает аренды, которые принимают только сборки DL с `LM_TRUST_ROOTS=dev`: `lm-demo`, прототипы из `prototypes/`;
- не годится для продуктива — закрытый dev-ключ опубликован.

### Шаг 5. TLS

Положите сертификат (с промежуточными) и ключ в `tls/server.crt` и `tls/server.key`. Иначе будет создан самоподписанный сертификат на 825 дней — только для проб: DL проверяет сертификат по системному хранилищу и не отключает проверку.

Let's Encrypt (если сервер доступен из интернета):

```sh
sudo apt -y install certbot
sudo certbot certonly --standalone -d "$SERVER_NAME" --pre-hook "docker compose -f /opt/almi/almi_license/deploy/central/docker-compose.yml stop gateway" \
  --post-hook "cp /etc/letsencrypt/live/$SERVER_NAME/fullchain.pem /opt/almi/almi_license/deploy/central/tls/server.crt && cp /etc/letsencrypt/live/$SERVER_NAME/privkey.pem /opt/almi/almi_license/deploy/central/tls/server.key && chmod 644 /opt/almi/almi_license/deploy/central/tls/* && docker compose -f /opt/almi/almi_license/deploy/central/docker-compose.yml start gateway"
```

Продление выполняет таймер `certbot.timer` с теми же хуками.

### Шаг 6. Второй запуск — установка

```sh
ADMIN_USER=admin ./install.sh
```

Пароль администратора вводится без отображения; длина — не меньше 12 символов. Пользователям, созданным на экране «Пользователи», консоль выдаёт временный пароль и требует сменить его при первом входе.

Скрипт запускает:
- `migrate`;
- `api`, `worker`, `console`, `gateway` (ожидание готовности до 10 минут);
- загрузку каталога (`manage.py loadcatalog`);
- `check.sh`.

### Шаг 7. Учётные записи и данные

- Дополнительные учётные записи создаются на экране «Пользователи» консоли или командой `docker compose run --rm api manage create_account --username <имя> --role operator|admin|customer_viewer`.
- Лицензии из ЛК загружаются в консоли: «Импорт», сначала предпросмотр, затем применение (E06).
- Профили политики проверяются в разделе «Профили»: на выпуске все в `monitor` (критерий I6).

### Шаг 8. Проверка

```sh
./check.sh
curl -fsS https://$SERVER_NAME/.well-known/almi-license   # discovery: версия, протокол, URL
curl -fsS https://$SERVER_NAME/ready
```

`check.sh` проверяет:
- службы;
- готовность API;
- ответ шлюза;
- пакет доверия;
- заполнение диска (предупреждение с 80 %, ошибка с 90 %);
- возраст последней копии.

Код возврата 1 означает, что нужно вмешательство. Затем выполните тестовую активацию (раздел 9).

## 5. Локальный сервер заказчика

Подробная инструкция для заказчика — `docs/operations/airgap-install.md`. Кратко:

1. Комплект собирается в АЛМИ: `VERSION=1.0.0 TRUST_ROOTS=root-2026:<pub> tools/build_airgap_bundle.sh out/`. Результат — архив с образами, скриптами и `SHA256SUMS`.
2. На хосте Ubuntu 24.04 нужен Docker (раздел 3). Без интернета пакеты Docker переносятся вместе с комплектом: `.deb` из `download.docker.com/linux/ubuntu/dists/noble/pool/stable/amd64/` ставятся командой `sudo apt install ./*.deb`.
3. Распакуйте комплект в `/opt/almi`, задайте `SERVER_NAME` и `HTTPS_PORT` в `.env`, положите TLS в `tls/` и выполните `./install.sh`.
4. Создайте администратора: `docker compose run --rm api manage create_account --username admin --role admin`.
5. На центральном сервере оператор создаёт локальный сервер (консоль → «Серверы»: заказчик, лицензии, места) и передаёт код регистрации.
6. В консоли локального сервера мастер первого запуска принимает код. Обмен:
   - онлайн: адрес центрального сервера, пакет приходит сам;
   - файлами: `.alk-req` уходит оператору, пакет `.alk` загружается на экране «Пакет».

Продукты заказчика указывают адрес локального сервера. Если он задан централизованно, это свойство MSI `LICENSE_SERVER_URL` или переменная `ALMI_LICENSE_SERVER_URL`.

## 6. Резервные копии

`./backup.sh` создаёт копию в `backups/`:
- `pg_dump -Fc`, зашифрованный gpg (AES-256);
- сумма SHA-256 рядом;
- метка `last-success`, её видит метрика `almi_backup_age_seconds`.

Хранится 30 дней (`BACKUP_KEEP_DAYS`).

Расписание (crontab пользователя `almi`):

```cron
17 2 * * * /opt/almi/almi_license/deploy/central/backup.sh >> /opt/almi/backup.log 2>&1
```

Обязательно:
- копируйте `backups/` за пределы хоста (rsync или restic на другой сервер);
- храните `secrets/backup_passphrase` отдельно от копий: без него копию не восстановить;
- раз в квартал проводите учение восстановления (`docs/operations/backup.md`, `make backup-drill`).

Что ещё сохранить вне копий БД:
- `keys/issuer.key` центрального сервера — в сейфе, как секрет; при утрате ключ выпуска перевыпускается на церемонии;
- `.env`, `tls/`;
- у локального сервера — ключ сервера: `backup.sh` копирует его отдельно и зашифрованно.

Восстановление: `./restore.sh backups/almi-<время>.dump.gpg`. Скрипт:
- останавливает API, обработчик и шлюз;
- проверяет сумму;
- восстанавливает базу;
- снова выдаёт права `almi_app`;
- проверяет цепочку журнала аудита (`verify_audit`);
- запускает сервисы.

## 7. Обновление и откат

Центральный сервер:

```sh
cd /opt/almi/almi_license && git fetch --tags && git checkout v1.0.1
cd deploy/central && NEW_VERSION=1.0.1 ./upgrade.sh
```

`upgrade.sh`:
1. снимает копию и сохраняет `.env` и имя копии в `previous/`;
2. собирает новые образы;
3. меняет `ALMI_VERSION`;
4. применяет миграции (`migrate`). Если миграция не прошла, сам выполняет `rollback.sh`;
5. запускает сервисы, загружает каталог, выполняет `check.sh`.

`./rollback.sh` возвращает предыдущую версию:
- образы предыдущей версии и прежний `.env`;
- базу из копии, снятой перед обновлением. Схема очищается до восстановления, чтобы таблицы новых миграций не мешали.

Изменения после обновления теряются. Решение об откате — у технического лидера: например, если в первые 2 часа доля 5xx Product API выше 1 %.

Локальный сервер: `./upgrade.sh /путь/к/новому/комплекту`, `./rollback.sh` (`docs/operations/airgap-install.md`).

## 8. Перевыпуск ключей

| Ключ | Срок | Как |
|---|---|---|
| Ключ выпуска центрального сервера | 2 года (`--valid-days 730`); по документу 1 — ежегодно | 1. Удалите `keys/issuer.*`. 2. Выполните `./install.sh` — он создаст новый ключ. 3. Сертифицируйте `keys/issuer.pub` на церемонии. 4. Выполните `export-trust` с обоими издателями и замените `trust/trust.json`. 5. Положите сертификат и выполните `docker compose up -d`. Аренды, подписанные старым ключом, остаются действительными до их `exp`, пока сертификат старого ключа не отозван. |
| Отзыв ключа | Немедленно | `almi-keytool revoke-cert`, затем `export-trust`; новый `trust.json` раздаётся продуктам по `/api/v1/trust` |
| Сертификат локального сервера | Срок пакета | Продлевается новым пакетом с центрального сервера |
| TLS | По сроку сертификата | Замените `tls/*`, выполните `docker compose restart gateway` |

## 9. Проверка после установки — тестовая активация

С пробным сервером (`DEV_ISSUER=1`) удобно проверять прототипами продуктов (`prototypes/README.md`):

```sh
# на машине разработчика, сборка DL с dev-корнем
cmake -S sdk/cpp -B build-dev -DLM_TRUST_ROOTS=dev && cmake --build build-dev --target lm-demo
build-dev/bin/lm-demo --server https://$SERVER_NAME --product <код продукта> activate <ключ из консоли>
build-dev/bin/lm-demo --server https://$SERVER_NAME status
```

Для продуктивного сервера — служебная лицензия и выпускная сборка продукта (шаг 8 порядка выпуска, документ 7).

## 10. Мониторинг

- Внешняя проверка раз в минуту: `https://SERVER_NAME/ready` даёт 200, если база доступна. Ключ подписи проверяется при старте: с негодным ключом `api` не запускается.
- `/metrics` доступен только внутри сети compose. Метрики:
  - запросы, ошибки и длительность по маршрутам;
  - `almi_task_queue_due`, `almi_task_failed`;
  - `almi_backup_age_seconds`;
  - повторы `Idempotency-Key`.

  Для Prometheus на этом же хосте опубликуйте API на loopback в `docker-compose.override.yml`:

  ```yaml
  services:
    api:
      ports: ["127.0.0.1:8000:8000"]
  ```

  Цель сбора — `127.0.0.1:8000/metrics`.
- Оповещения (раздел 11 документа 7):
  - недоступность;
  - 5xx больше 1 %;
  - `almi_backup_age_seconds > 93600`;
  - `almi_task_failed > 0`.

  Без Prometheus подойдёт задание cron `check.sh || <отправка письма>` раз в 5 минут.
- Журналы — JSON в stdout: `docker compose logs -f api worker`. Ключи, аренды, подписи, nonce и пароли в журналы не пишутся (AGENTS.md, правило 9).

## 11. Безопасность хоста

- SSH только по ключам, `PasswordAuthentication no`; доступ к хосту — по списку раздела 12 документа 7.
- Автоматические обновления безопасности: `sudo apt -y install unattended-upgrades`.
- `secrets/`, `keys/`, `tls/` и `backups/` не покидают хост, кроме копий из раздела 6; в git они исключены (`.gitignore`).
- Роль приложения `almi_app` не может изменить или очистить журнал аудита (вопрос 38); миграции и копии работают от имени `almi`.
- Проверка перед выпуском — `docs/security/review-stage1.md`.

## 12. Типовые неисправности

| Признак | Причина | Что делать |
|---|---|---|
| `install.sh`: `no keys/issuer.cert.jws` | Ключ выпуска ещё не сертифицирован | Шаг 4 |
| `api` не становится healthy, в журнале `SIGNING_KEY_FILE` / `SIGNING_CERT_FILE` | Сертификат не от этого ключа или повреждён | Сверьте `keys/issuer.pub` с `pub` в сертификате (`almi-keytool verify`) |
| `api`: `DJANGO_ALLOWED_HOSTS` / 400 Bad Request | `SERVER_NAME` не совпадает с именем в запросе | Исправьте `.env`, `docker compose up -d` |
| Консоль: 403 CSRF при входе | Открыта по другому имени или порту | Открывайте `https://SERVER_NAME[:HTTPS_PORT]/` |
| Продукт: `LM_ERR_NETWORK`, хотя сервер отвечает в браузере | Самоподписанный или неполный сертификат: TLS-ошибки модуль не обходит | Полная цепочка в `tls/server.crt` |
| Продукт: `LM_ERR_INVALID_SIGNATURE` | DL собран с другим корнем (`dev` против продуктивного) | Сборка продукта и `TRUST_ROOTS` сервера — от одного корня |
| Сервер отвечает `401 clock_skew` | Часы хоста расходятся с клиентом больше 5 минут (модуль сам поправляет подпись один раз) | `timedatectl` на хосте |
| `check.sh`: `no trust bundle` | Нет `trust/trust.json` | Шаг 4, `export-trust` |
| `too many connections` в журнале `db` | `WEB_CONCURRENCY × DATABASE_POOL_MAX_SIZE` больше 100 | Уменьшите пул или процессы |
| `restore.sh`: `sha256` не совпадает | Копия повреждена | Возьмите предыдущую копию |
| Диск заполнен | Копии, журналы, старые образы | `docker image prune`, перенос копий, лимиты журналов (раздел 3) |

## 13. Справочник файлов `deploy/central`

| Файл | Назначение |
|---|---|
| `docker-compose.yml` | Сервисы раздела 1; `api`, `worker` — роль `almi_app`; `migrate` — `almi` |
| `.env.example` | Настройки раздела 4, шаг 2 |
| `install.sh` | Секреты, образы, ключ выпуска, TLS, запуск, каталог, первый администратор |
| `check.sh` | Состояние; коды 0 и 1 |
| `backup.sh`, `restore.sh` | Копии (`deploy/ops/*.sh` в контейнере `postgres:17`) |
| `upgrade.sh`, `rollback.sh` | Обновление и откат |
| `secrets/`, `keys/`, `tls/`, `trust/`, `backups/`, `previous/` | Создаются на хосте, в git не попадают |

## 14. Расхождения со спецификациями

1. Документ 7, раздел 10: «`rollback.sh <версия>` и `migrate <приложение> <номер>`». В коде откат возвращается к версии до последнего обновления и восстанавливает базу из копии, снятой перед ним. Обратные миграции не применяются: так проще и одинаково для local и central, но изменения после обновления теряются.
2. Документ 7, раздел 6: задачи `deploy-staging` и `deploy-prod` в CI отсутствуют, стенды `test-*` и `staging` не созданы (вопрос 28, отложено). Центральный сервер разворачивается вручную по этому руководству. В CI задача `central-install` проверяет установку, копию, обновление и откат.
3. Документ 7, раздел 9: в комплекте нет `docs/` в PDF и подписи `SHA256SUMS.sig`. Подпись ставится на церемонии ключом выпуска; инструкции — Markdown в репозитории.
4. Документ 7, раздел 7.1: базовый образ запуска — `python:3.13-slim` (вариант спецификации), не distroless.
5. Документ 1, раздел 9: ключ выпуска перевыпускается ежегодно. В примере утилиты `--valid-days 730`, срок задаёт церемония.
6. Ключ выпуска создаётся на хосте сервера скриптом `install.sh` (решение v0.6.0). В спецификации место создания ключа выпуска не указано.
