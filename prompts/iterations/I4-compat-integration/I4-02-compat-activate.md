# I4-02. Адаптер `/api/activate/` (E11-03)

```text
История E11-03. Реализуй compat/legacy_activate: GET и POST /api/activate/ (параметры data, host, lic, format).

Источники: раздел 12.1 docs/specs/02-interaction-spec.md; фикстуры tests/compat/registration/*; поведение текущего ЛК — описание в разделе 3.1 docs/specs/08-lk-tz.md.
- Проверка параметров: data — 32 hex (MD5), host до 128 символов, lic — формат ключа legacy или v1.
- instance_id = UUID v5(NAMESPACE_ALMI_OS, data.lower()); subject_type = os_node; вызов activation.domain.activate() — без отдельной логики учёта мест.
- Повтор того же data — успех без занятия места.
- Ответ: HTML по умолчанию, JSON при format=json или Accept: application/json; тексты — раздел 6 docs/specs/05-messages.md; разметка HTML — как в фикстурах (тот же набор элементов и текстов).
- Ограничения частоты как в ЛК 2.0: 20/ч на IP, 10/ч на lic, блокировка IP на 900 с после 10 ошибок.
Тесты: все фикстуры; сравнение HTML — по извлечённому тексту и статусу, а не побайтно.
```
