# I2-05. Проверка и продление (E03-04, E03-07)

```text
Истории E03-04 и E03-07. Реализуй activation.domain.check() и POST /api/v1/activations/{activation_id}/check.

Раздел 5.3 docs/specs/02-interaction-spec.md:
- обновить product_version, os, usage, last_seen_at; сохранить usage как отдельную запись для статистики (stats.domain.record_usage);
- отпечаток: сравнить компоненты с сохранёнными по правилу допуска раздела 2.4 (совпадение не менее 3 из 4 компонентов; недоступный не учитывается, тогда не менее 2 из 3 — ADR-005); вне допуска → 412 rebind_required;
- released / released_auto → 410 activation_released; revoked → 403 license_revoked с арендой состояния REVOKED;
- lease_seq из запроса больше серверного → событие аудита lease_seq_anomaly, ответ как обычно;
- выпуск новой аренды с seq = max(серверный, клиентский) + 1;
- директивы: из очереди активации (модель Directive) и профиля; исключить acked_directives; unsupported_directives записать в аудит;
- сообщения: из PolicyResult.message_ids → тексты профиля (документ 5, раздел 3).
Ответ — LeaseResponse. Тесты на каждую ветку; контрактный тест на схему ответа.
```
