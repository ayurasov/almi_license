# I1-01. JSON Schema подписанных объектов (E00-03)

```text
Создай JSON Schema (draft 2020-12) в contracts/schemas/ для объектов: lease, trust, cert, package, alk-req, alk-lic, alk-usage, receipt, problem, message, directive, policy.

Источник — разделы 6, 8, 9, 10, 13 и 16 docs/specs/02-interaction-spec.md и components/schemas в contracts/openapi-product-api-v1.yaml. Схемы должны совпадать с OpenAPI по полям и типам; где OpenAPI ссылается на объект, вынеси его в отдельную схему и сошлись через $ref.

Правила:
- additionalProperties: true на верхнем уровне полезной нагрузки (совместимость вперёд), false — в объектах с фиксированным составом (заголовок JWS);
- форматы дат — unix-время в утверждениях JWS, date-time в JSON API;
- для каждой схемы — минимум один валидный и два невалидных примера в contracts/schemas/examples/.

Добавь в make contract-check проверку: все примеры из docs/specs/02-interaction-spec.md (блоки json) валидируются соответствующей схемой.
Коммит: contract: json schemas v1 (E00-03).
```
