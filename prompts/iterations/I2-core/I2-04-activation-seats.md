# I2-04. Активация и учёт мест (E03-01, E03-02, E03-03)

```text
Истории E03-01, E03-02, E03-03. Реализуй activation.domain.activate() и POST /api/v1/activations (operationId=activate).

Алгоритм — раздел 5.2 docs/specs/02-interaction-spec.md, правила учёта мест — раздел 7.4 docs/specs/01-architecture.md.
1. Нормализация ключа, поиск по key_hash. Нет ключа → 404 key_not_found (время ответа не зависит от существования ключа: всегда вычисляется хэш и выполняется один запрос).
2. transaction.atomic; License select_for_update.
3. Проверки по порядку: статус лицензии (revoked → 403 license_revoked), продукт и редакция (403 product_mismatch), срок через PolicyEngine (новая активация после окончания отсрочки → 403 license_expired).
4. Повтор: активная активация с тем же instance_id и тем же device_pubkey → вернуть новую аренду, 200, место не занимать.
5. Тот же instance_id с другим device_pubkey и отпечатком вне допуска → 409 instance_conflict, Activation со статусом conflict, событие аудита.
6. Подсчёт занятых мест (status=active) в той же транзакции; лимит + ceil(limit × reserve_pct / 100); в пределах резерва — in_reserve = true; сверх — 409 seats_exhausted с used и limit в data.
7. Создание Activation, выпуск аренды (signing.domain), запись Lease, событие аудита activation.created; 201.

Тесты:
- каждый пункт алгоритма;
- E03-02: 50 параллельных запросов (pytest-xdist или threading с отдельными соединениями) на лицензию с limit=10, reserve_pct=3 → ровно 11 успешных, 39 seats_exhausted; запускается против настоящего PostgreSQL;
- Idempotency-Key обрабатывается слоем E05-02 (если он ещё не готов — тест помечается xfail со ссылкой на E05-02).
P7 обязательно.
```
