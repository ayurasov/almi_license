# Тексты сообщений пользователю и администратору

| Параметр | Значение |
|---|---|
| Документ | Тексты сообщений (документ 5 комплекта) |
| Версия | 1.0 |
| Дата | 14.10.2026 |
| Статус | Проект; согласование — владельцы продуктов, юрист, служба поддержки |
| Связанные документы | 2 — Спецификация (разделы 9, 15.4, 16); 4 — Каталог продуктов и функций |

## 1. Назначение

Документ содержит все тексты, которые видит пользователь продукта, администратор заказчика и оператор в связи с лицензированием: уведомления о сроках, диалоги активации, ошибки, окно «О программе», страницы портала офлайн-активации и письма.

Тексты двух видов:

| Вид | Где хранится | Как меняется |
|---|---|---|
| Серверные | Профиль политики на сервере (`messages[]`) | Оператором в консоли, без выпуска продукта |
| Встроенные | Ресурсы модуля DL и продукта | С выпуском продукта; используются, когда сервер не прислал текст (первая активация, нет связи, ошибка сети) |

Каждый текст ниже имеет идентификатор. Идентификатор серверного текста совпадает с полем `id` сообщения; идентификатор встроенного — с ключом ресурса.

## 2. Правила написания

1. Говорить, что произошло и что делать. Без обвинений, без слов «нарушение», «пиратство», «нелегальная копия».
2. Данные пользователя не под угрозой — сказать это явно в сообщениях о блокировке.
3. Длина: баннер — до 140 знаков, заголовок диалога — до 60, текст диалога — до 400, кнопка — до 24.
4. Без технических кодов в основном тексте. Код ошибки и `activation_id` показываются отдельной строкой «Для поддержки: …».
5. Даты — в формате `ДД.ММ.ГГГГ`, числа дней — с правильным склонением (функция модуля DL `plural_ru`).
6. Подстановки: `{days_left}`, `{valid_until}`, `{customer}`, `{used}`, `{limit}`, `{product}`, `{support_contact}`, `{server_url}`, `{code}`, `{activation_id}`.
7. Английская версия — для продуктов с английским интерфейсом; язык определяется языком интерфейса продукта, при отсутствии перевода — русский.

## 3. Сообщения о состоянии лицензии

Серверные сообщения по умолчанию для профилей класса `commercial`. Для класса `critical` используются те же тексты без упоминания блокировки (раздел 3.3).

### 3.1. АльтерОфис Desktop

| ID | Состояние и показ | Текст (ru) | Текст (en) | Кнопки |
|---|---|---|---|---|
| `trial.banner` | TRIAL; баннер, info, каждый запуск | Пробный период: осталось {days_left}. | Trial period: {days_left} left. | Ввести ключ |
| `trial.ending` | TRIAL, последние 5 дней; диалог, warning, ежедневно | Пробный период закончится через {days_left}. Чтобы продолжить работу без ограничений, введите ключ лицензии. | The trial period ends in {days_left}. Enter a license key to continue without limitations. | Ввести ключ / Позже |
| `unlicensed.start` | UNLICENSED; диалог, warning, каждый запуск | Пробный период закончился. Введите ключ лицензии или продолжите работу без ключа. Некоторые функции недоступны. | The trial period has ended. Enter a license key or continue without a key. Some features are unavailable. | Ввести ключ / Продолжить без ключа |
| `notice.banner` | NOTICE; баннер, info, ежедневно | Лицензия действует до {valid_until}. Осталось {days_left}. | License is valid until {valid_until}. {days_left} left. | Подробнее |
| `notice.7days` | NOTICE, 7 дней и меньше; диалог, warning, ежедневно | Лицензия {product} заканчивается {valid_until}. Обратитесь к администратору или в {support_contact}, чтобы продлить её. | The {product} license expires on {valid_until}. Contact your administrator or {support_contact} to renew it. | Понятно |
| `grace.banner` | GRACE; баннер, warning, каждый запуск | Срок лицензии истёк {valid_until}. Продукт работает без ограничений ещё {days_left}. | The license expired on {valid_until}. The product works without limitations for {days_left} more. | Подробнее |
| `grace.dialog` | GRACE; диалог, warning, ежедневно | Срок лицензии истёк. Через {days_left} будут отключены обновления, макросы и совместная работа. Документы и данные останутся доступны. | The license has expired. In {days_left}, updates, macros and collaboration will be disabled. Your documents and data remain available. | Понятно |
| `restricted.banner` | RESTRICTED; баннер, warning, каждый запуск | Лицензия не продлена. Обновления, макросы и совместная работа отключены. Документы доступны. | The license has not been renewed. Updates, macros and collaboration are disabled. Documents are available. | Подробнее |
| `restricted.feature` | RESTRICTED; подсказка у неактивной функции, info, при наведении | Функция недоступна: лицензия не продлена. | Not available: the license has not been renewed. | — |
| `blocked.read_only` | BLOCKED, `read_only`; диалог, critical, каждый запуск | Лицензия не действует. Продукт работает в режиме просмотра: документы можно открыть, распечатать и экспортировать, но не изменить. Для продления обратитесь к администратору или в {support_contact}. | The license is not valid. The product works in view-only mode: you can open, print and export documents but not edit them. Contact your administrator or {support_contact} to renew. | Ввести ключ / Продолжить в режиме просмотра |
| `blocked.no_start` | BLOCKED, `no_start`; диалог, critical, каждый запуск | Лицензия не действует, продукт не может быть запущен. Ваши документы не изменены и доступны в других программах. Обратитесь к администратору или в {support_contact}. | The license is not valid and the product cannot start. Your documents are unchanged and available in other applications. Contact your administrator or {support_contact}. | Ввести ключ / Закрыть |
| `revoked.dialog` | REVOKED; диалог, critical, каждый запуск | Лицензия отозвана владельцем. Продукт работает в режиме просмотра. Для уточнения обратитесь к администратору. | The license has been revoked by its owner. The product works in view-only mode. Contact your administrator for details. | Ввести ключ / Продолжить в режиме просмотра |
| `active.restored` | ACTIVE после блока; баннер, info, один раз | Лицензия продлена до {valid_until}. Все функции доступны. | The license has been renewed until {valid_until}. All features are available. | — |
| `monitor.over_limit` | Любое, режим `monitor`; баннер, info, ежедневно | Используется {used} лицензий из {limit}. Обратитесь к администратору, чтобы расширить лицензию. | {used} of {limit} licenses are in use. Contact your administrator to extend the license. | — |

### 3.2. АльтерОфис Web

На этапе 1 продукт показывает данные подписки средствами приложения поддержки Nextcloud; собственные тексты сервера в продукте не отображаются. Сервер управляет только данными, которые это приложение показывает:

| Поле подписки | Что видит администратор Web |
|---|---|
| `endDate` | Дата окончания подписки |
| `amountOfUsers` | Лимит пользователей |
| `onlyCountActiveUsers` | Считаются все или только активные пользователи |
| `accountManagerInfo.name`, `email`, `phone` | Контакт для продления: заполняется контактом менеджера заказчика или общей линией поддержки |

Тексты этапа 2 (приложение `alter_license`):

| ID | Состояние | Кому | Текст (ru) |
|---|---|---|---|
| `web.notice.admin` | NOTICE | Администратор | Лицензия АльтерОфис Web действует до {valid_until}. Используется {used} пользователей из {limit}. |
| `web.grace.admin` | GRACE | Администратор | Срок лицензии истёк {valid_until}. Через {days_left} будет запрещено создание новых пользователей и внешних ссылок. |
| `web.restricted.admin` | RESTRICTED | Администратор | Лицензия не продлена: создание пользователей, внешние ссылки и обновления приложений отключены. Работа пользователей продолжается. |
| `web.restricted.user` | RESTRICTED | Пользователь (только при попытке ограниченного действия) | Действие недоступно: лицензия сервера не продлена. Обратитесь к администратору. |
| `web.blocked.user` | BLOCKED | Пользователь | Сервер работает в режиме просмотра: файлы можно открыть и скачать, но не изменить. Обратитесь к администратору. |
| `web.limit.admin` | Превышение пользователей | Администратор | Пользователей: {used}, лимит лицензии: {limit}. Новые пользователи не создаются, пока лимит не будет увеличен. |

### 3.3. Класс `critical`

| ID | Отличие от `commercial` |
|---|---|
| `grace.dialog` | «Срок лицензии истёк. Через {days_left} будут отключены обновления. Работа продукта не будет ограничена.» |
| `restricted.banner` | «Лицензия не продлена. Обновления отключены. Работа продукта не ограничена.» |
| `blocked.*` | Не используются: профиль класса не переходит в BLOCKED |

### 3.4. АльтерОС

АльтерОС на этапе 1 не показывает сообщений о сроке. Скрипт `registration.sh` выводит ответ сервера как есть (раздел 6).

## 4. Активация

### 4.1. Диалог активации (Desktop)

| ID | Элемент | Текст (ru) | Текст (en) |
|---|---|---|---|
| `act.title` | Заголовок | Активация {product} | Activate {product} |
| `act.key.label` | Поле | Ключ лицензии | License key |
| `act.key.hint` | Подсказка | Ключ указан в письме или сертификате лицензии: XXXX-XXXX-XXXX-XXXX | The key is in the license email or certificate: XXXX-XXXX-XXXX-XXXX |
| `act.server.label` | Поле (свёрнуто) | Сервер лицензирования | License server |
| `act.server.hint` | Подсказка | Оставьте пустым, если администратор не сообщил адрес сервера | Leave empty unless your administrator provided a server address |
| `act.button` | Кнопка | Активировать | Activate |
| `act.offline.link` | Ссылка | Нет доступа к сети? Активировать с помощью файла | No network access? Activate with a file |
| `act.progress` | Ожидание | Подключение к серверу лицензирования… | Connecting to the license server… |
| `act.success` | Успех | Продукт активирован. Лицензия: {customer}, до {valid_until}. | The product is activated. License: {customer}, valid until {valid_until}. |
| `act.success.perpetual` | Успех, бессрочная | Продукт активирован. Лицензия: {customer}, бессрочная. | The product is activated. License: {customer}, perpetual. |
| `act.key.format` | Проверка формата до отправки | Проверьте ключ: он состоит из 16 букв и цифр, разделённых дефисами. | Check the key: it consists of 16 letters and digits separated by hyphens. |

### 4.2. Мастер офлайн-активации (Desktop)

| ID | Шаг | Текст (ru) |
|---|---|---|
| `off.step1.title` | 1 | Создайте файл запроса |
| `off.step1.text` | 1 | Введите ключ лицензии и сохраните файл запроса. Перенесите его на компьютер с доступом в интернет или передайте администратору. |
| `off.step1.button` | 1 | Сохранить файл запроса |
| `off.step2.title` | 2 | Получите файл лицензии |
| `off.step2.text` | 2 | Откройте {server_url}/offline на компьютере с доступом к сети, загрузите файл запроса и скачайте файл лицензии. Если сеть закрыта, передайте файл запроса администратору. |
| `off.step3.title` | 3 | Загрузите файл лицензии |
| `off.step3.text` | 3 | Выберите полученный файл с расширением .alk-lic. |
| `off.step3.button` | 3 | Загрузить файл лицензии |
| `off.done` | Готово | Продукт активирован. Лицензия: {customer}, до {valid_until}. |
| `off.err.foreign` | Ошибка | Этот файл лицензии создан для другого компьютера. Создайте новый файл запроса на этом компьютере. |
| `off.err.damaged` | Ошибка | Файл повреждён или изменён. Получите файл лицензии повторно. |
| `off.err.old` | Ошибка | Этот файл лицензии старее уже установленного. Используйте последний полученный файл. |

### 4.3. Освобождение лицензии

| ID | Текст (ru) |
|---|---|
| `rel.confirm` | Освободить лицензию на этом компьютере? Продукт перейдёт в режим без ключа, а лицензию можно будет активировать на другом компьютере. |
| `rel.done` | Лицензия освобождена. |
| `rel.offline` | Нет связи с сервером. Сохраните файл подтверждения и передайте его администратору, чтобы лицензия освободилась на сервере. |
| `rel.uninstall` | Освободить лицензию перед удалением программы? Если не освободить, она освободится автоматически через {days} дн. без связи с сервером. |

## 5. Ошибки

Текст из поля `user_message` ответа сервера показывается как есть. Если его нет (нет связи, сбой), модуль DL использует встроенные тексты ниже. Под текстом всегда выводится строка «Для поддержки: код {code}, активация {activation_id}» (без `activation_id`, если активации ещё нет).

| `code` | ID | Текст (ru) | Текст (en) |
|---|---|---|---|
| `invalid_key_format` | `err.invalid_key_format` | Ключ введён неверно. Проверьте его и попробуйте снова. | The key is incorrect. Check it and try again. |
| `key_not_found` | `err.key_not_found` | Ключ не найден. Проверьте ключ или обратитесь к поставщику лицензии. | The key was not found. Check it or contact your license supplier. |
| `license_expired` | `err.license_expired` | Срок действия этой лицензии истёк. Обратитесь к администратору для продления. | This license has expired. Contact your administrator to renew it. |
| `license_revoked` | `err.license_revoked` | Лицензия отозвана. Обратитесь к администратору. | The license has been revoked. Contact your administrator. |
| `license_suspended` | `err.license_suspended` | Лицензия приостановлена. Обратитесь к администратору. | The license is suspended. Contact your administrator. |
| `product_mismatch` | `err.product_mismatch` | Этот ключ предназначен для другого продукта или редакции. | This key is for a different product or edition. |
| `seats_exhausted` | `err.seats_exhausted` | Все лицензии по этому ключу уже используются ({used} из {limit}). Освободите лицензию на другом компьютере или обратитесь к администратору. | All licenses for this key are in use ({used} of {limit}). Release a license on another computer or contact your administrator. |
| `instance_conflict` | `err.instance_conflict` | Этот компьютер похож на копию уже активированного. Нажмите «Активировать заново», чтобы зарегистрировать его как новый. | This computer looks like a copy of an already activated one. Click "Activate again" to register it as a new computer. |
| `rebind_required` | `err.rebind_required` | Оборудование компьютера изменилось. Требуется повторная активация — она выполнится автоматически. | The computer hardware has changed. Reactivation is required and will run automatically. |
| `clock_skew` | `err.clock_skew` | Время на компьютере отличается от точного. Проверьте дату, время и часовой пояс. | The computer clock is wrong. Check the date, time and time zone. |
| `upgrade_required` | `err.upgrade_required` | Версия продукта устарела для сервера лицензирования. Установите обновление. Работа продолжается по текущей лицензии. | This product version is too old for the license server. Install the update. Work continues under the current license. |
| `unsupported_product_version` | `err.unsupported_version` | Эта версия продукта не входит в лицензию. Обратитесь к администратору. | This product version is not covered by the license. Contact your administrator. |
| `rate_limited` | `err.rate_limited` | Слишком много попыток. Повторите через {retry_after} мин. | Too many attempts. Try again in {retry_after} min. |
| `signature_invalid` | `err.signature_invalid` | Не удалось подтвердить подлинность запроса. Активируйте продукт заново. | The request could not be verified. Activate the product again. |
| `maintenance` | `err.maintenance` | Сервер лицензирования на обслуживании. Работа продолжается по текущей лицензии. Повторите позже. | The license server is under maintenance. Work continues under the current license. Try again later. |
| `internal_error` | `err.internal` | Сервер лицензирования временно недоступен. Работа продолжается по текущей лицензии. | The license server is temporarily unavailable. Work continues under the current license. |
| сеть | `err.network` | Сервер лицензирования недоступен. Проверьте подключение или активируйте продукт с помощью файла. | The license server is unreachable. Check your connection or activate with a file. |
| TLS | `err.tls` | Не удалось установить защищённое соединение с сервером лицензирования. Обратитесь к администратору. | A secure connection to the license server could not be established. Contact your administrator. |
| прочие | `err.unknown` | Не удалось выполнить операцию. Повторите позже или обратитесь в поддержку. | The operation failed. Try again later or contact support. |

## 6. АльтерОС: ответы `/api/activate/`

Тексты совпадают с текущим ЛК (сохраняются для совместимости со скриптом `registration.sh`). Фиксируются по фикстурам E00-09 бэклога.

| Ситуация | Текст (ru) |
|---|---|
| Успех | Лицензия успешно активирована |
| Повтор с того же узла | Лицензия уже активирована на этом компьютере |
| Нет мест | Превышено количество активаций для данной лицензии |
| Неверный ключ | Лицензия не найдена или недействительна |
| Срок истёк | Срок действия лицензии истёк |
| Перебор | Слишком много попыток, повторите позже |

Точная формулировка и разметка HTML-ответа берутся из текущей реализации; таблица выше — для понимания смысла.

## 7. Окно «О программе» (Desktop)

| ID | Поле | Пример значения |
|---|---|---|
| `about.state` | Состояние | Лицензия действует / Пробный период / Режим просмотра |
| `about.type` | Тип | Подписка / Бессрочная / Пробная |
| `about.valid` | Действует до | 31.12.2027 / Бессрочно |
| `about.support` | Поддержка до | 31.12.2027 |
| `about.customer` | Владелец лицензии | ООО «Пример» |
| `about.edition` | Редакция | Профессиональная |
| `about.server` | Сервер лицензирования | license.alter-os.ru / license.corp.local / Без сервера (файл) |
| `about.last_check` | Последняя проверка | 14.10.2026 09:30 |
| `about.activation` | Код активации | act_01JA… (кнопка «Копировать») |
| `about.buttons` | Кнопки | Ввести ключ · Активировать без сети · Освободить лицензию · Проверить сейчас |

## 8. Портал офлайн-активации

Страница `https://<сервер>/offline` для администратора заказчика.

| ID | Элемент | Текст (ru) |
|---|---|---|
| `portal.title` | Заголовок | Офлайн-активация продуктов АЛМИ |
| `portal.intro` | Пояснение | Загрузите файл запроса (.alk-req), созданный продуктом на компьютере без доступа к сети. Вы получите файл лицензии (.alk-lic), который нужно загрузить в продукт. |
| `portal.upload` | Кнопка | Выбрать файл запроса |
| `portal.done` | Успех | Файл лицензии готов. Срок: до {valid_until}. Использовано {used} из {limit}. |
| `portal.download` | Кнопка | Скачать файл лицензии |
| `portal.release.done` | Освобождение | Лицензия освобождена. Использовано {used} из {limit}. |
| `portal.err.format` | Ошибка | Это не файл запроса продукта АЛМИ или файл повреждён. |
| `portal.err.size` | Ошибка | Файл слишком большой. Размер файла запроса — не более 64 КБ. |
| `portal.captcha` | Защита | Подтвердите, что вы не робот |

## 9. Консоль: уведомления оператору

| ID | Событие | Текст (ru) |
|---|---|---|
| `op.over_limit` | Использование сверх лимита (в резерве) | {customer}: лицензия {external_ref} использует {used} из {limit} (резерв). |
| `op.threshold` | 90 % использования | {customer}: использовано 90 % лицензии {external_ref}. |
| `op.conflict` | Конфликт экземпляра | {customer}: обнаружена копия экземпляра {activation_id}. Проверьте активации. |
| `op.rollback` | Перевод часов | {customer}: на устройстве {activation_id} обнаружен перевод часов назад. |
| `op.package_expiring` | Срок пакета | Пакет локального сервера {server_id} ({customer}) действует до {valid_until}. Подготовьте новый пакет. |
| `op.usage_overdue` | Нет отчёта | Локальный сервер {server_id} ({customer}) не присылал отчёт {days} дн. |
| `op.import_done` | Импорт ЛК | Импорт завершён: создано {created}, обновлено {updated}, пропущено {skipped}. |
| `op.audit_broken` | Нарушена цепочка аудита | Критично: нарушена целостность журнала аудита начиная с записи {id}. |

## 10. Письма (этап 2)

Отправляются сервером при включённом SMTP. Получатели — контакты заказчика из ЛК и оператор.

| ID | Когда | Тема | Текст (кратко) |
|---|---|---|---|
| `mail.expiring` | За `notify_before_days` и за 7 дней | Лицензия {product} заканчивается {valid_until} | Лицензия {external_ref} для {customer} действует до {valid_until}. Используется {used} из {limit}. Для продления обратитесь к менеджеру: {support_contact}. |
| `mail.expired` | В день окончания | Срок лицензии {product} истёк | Срок лицензии истёк {valid_until}. Продукт работает без ограничений до {grace_until}, затем отключатся: {restricted_list}. Данные пользователей не затрагиваются. |
| `mail.restored` | После продления | Лицензия {product} продлена | Лицензия продлена до {valid_until}. Продукты получат новые права при ближайшей проверке. |
| `mail.threshold` | 90 % и 100 % | Лицензия {product} почти исчерпана | Используется {used} из {limit}. |
| `mail.package` | Пакет локального сервера готов | Новый пакет лицензий для {server_id} | Пакет до {valid_until} доступен в консоли. Загрузите его на локальный сервер. |

## 11. Встроенные тексты модуля DL

Модуль DL поставляется с ресурсами `ru` и `en` для всех ID разделов 3.1, 4, 5 и 7. Серверный текст с тем же ID заменяет встроенный. Порядок выбора текста:

1. Сообщение из последней аренды для текущего состояния и места.
2. `user_message` из ответа сервера (для ошибок).
3. Встроенный текст модуля DL на языке интерфейса.
4. Встроенный текст на русском.

## 12. Согласование

| Раздел | Согласует |
|---|---|
| 3, 4, 7 | Владелец продукта, UX-дизайнер продукта |
| 3.1 (`blocked.*`, `revoked.*`), 10 | Юрист — на соответствие лицензионному соглашению |
| 5, 8 | Служба поддержки — на понятность и наличие инструкции для каждой ошибки |
| 6 | Владелец продукта АльтерОС — без изменений относительно текущего ЛК |
| 9 | Оператор лицензий |
