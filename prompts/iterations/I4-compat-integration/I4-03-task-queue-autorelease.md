# I4-03. Очередь задач и автоосвобождение (E12-01, E12-02)

```text
Истории E12-01 и E12-02.

E12-01: outbox.domain — очередь задач в PostgreSQL: таблица Task (id, kind, payload JSONB, run_at, attempts, last_error, status, locked_until). Обработчик manage.py run_worker: SELECT … FOR UPDATE SKIP LOCKED LIMIT 10; повтор с задержкой 2^attempts минут, максимум 8 попыток; задачи идемпотентны (повторное выполнение не меняет результат). Расписание: таблица Schedule с cron-выражениями (croniter), постановка задач раз в минуту одним обработчиком (pg_advisory_lock).
E12-02: задача release_stale_activations раз в час: активации status=active и last_seen_at < now − release_after_days (из профиля лицензии) → released_auto пакетами по 500 в отдельных транзакциях с блокировкой лицензии; событие аудита на каждую.
Тесты: два обработчика параллельно не берут одну задачу; падение задачи — повтор; FrozenClock для автоосвобождения; граница ровно в release_after_days.
P7 обязательно.
```
