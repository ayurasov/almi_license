# I4-01. Адаптер подписки Nextcloud (E11-01, E11-02)

```text
Истории E11-01 и E11-02. Реализуй compat/nextcloud: POST /apps/zammad_organisation_management/api/query/subscription/{subscription_key}.

Источники: раздел 11.1 docs/specs/02-interaction-spec.md; фикстуры tests/compat/nextcloud/*.json (записаны с реального приложения support в E00-09) — это эталон формы ответа.
1. Ключ подписки ищется как ключ лицензии продукта alteroffice-web.
2. Экземпляр: instanceId → activation.domain.activate() с subject_type=server_instance, instance_id = UUID v5(NAMESPACE_ALMI, instanceId); повтор — check(). Подпись запроса не требуется (продукт её не умеет) — компенсация: лимит частоты 10/мин на ключ, привязка ключа к первому instanceId, второй instanceId → занимает второе место по общим правилам.
3. userCount, activeUserCount, apps, version → usage активации.
4. Ответ: endDate (valid_until, для бессрочной — support_until), extendedSupport (support_until > now), amountOfUsers (лимит пользователей; в RESTRICTED — текущий userCount), onlyCountActiveUsers (из лицензии), accountManagerInfo (контакт менеджера заказчика или общей поддержки из настроек).
5. Нет ключа → 404 с телом как у оригинального сервиса (по фикстуре).
Тесты: все фикстуры — ответ совпадает по составу полей и типам; состояния ACTIVE, GRACE, RESTRICTED.
```
