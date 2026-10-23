# I1-03. Модель данных (E01-01)

```text
История E01-01. Реализуй модели и миграции домена по разделу 7.1 docs/specs/01-architecture.md.

Модели по модулям:
- catalog: Product, Edition, Capability, Metric, PolicyProfile (версионируемый: code, version, params JSONB, created_at; уникальность code+version);
- licensing: Customer, License, LicenseKey (key_hash, key_mask, format: legacy|v1), ExternalRef;
- activation: Activation (instance_id, subject_type, fp_components JSONB с хэшами, device_pubkey, status: active|released|released_auto|revoked|conflict, in_reserve, last_seen_at, lease_seq, product_version, os JSONB), Lease (последняя выданная; seq, issued_at, exp, jws_hash);
- packages: LocalServer, Allocation, Package, UsageReport;
- audit: AuditEvent (actor, action, object_type, object_id, at, ip, data JSONB, prev_hash, hash).

Требования:
- первичные ключи UUID; внешние идентификаторы act_/srv_ — ULID в отдельном поле с уникальным индексом;
- уникальность (license, instance_id) для активных активаций — частичный уникальный индекс;
- индексы: Activation(status, last_seen_at), License(status, valid_until), LicenseKey(key_hash);
- модули не ссылаются на модели других модулей через ForeignKey, кроме licensing → catalog и activation → licensing (зафиксируй в docs/decisions.md);
- миграции применяются на пустую БД и откатываются (тест в CI: migrate → migrate zero).
Сначала тест на ограничения уникальности и откат миграций, затем модели.
```
