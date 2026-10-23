# I2-02. PolicyEngine (E04-01, E04-02)

```text
История E04-01. Реализуй server/apps/policy/domain/engine.py.

def evaluate(policy: PolicyParams, license: LicenseFacts, now: datetime, last_success_at: datetime | None) -> PolicyResult
PolicyResult: state, capabilities (frozenset), message_ids (tuple), lease_exp (datetime | None), next_check_at.

Правила — раздел 8 docs/specs/01-architecture.md и раздел 7.2 docs/specs/02-interaction-spec.md. Функция чистая: нет импорта django, БД, сети, datetime.now, random. PolicyParams и LicenseFacts — frozen dataclass.

Порядок работы:
1. Тест test_vectors.py: параметризован по всем contracts/vectors/policy/*.json; сейчас падает.
2. Реализация до прохождения всех векторов. Если вектор кажется тебе неверным — НЕ меняй вектор и не подгоняй код: выпиши номер вектора, своё рассуждение и рассуждение из поля reasoning; задай вопрос (P12).
3. История E04-02: property-тесты hypothesis — при фиксированной лицензии и политике состояние монотонно не улучшается с ростом now (ACTIVE → NOTICE → GRACE → RESTRICTED → BLOCKED); capabilities при RESTRICTED ⊆ capabilities при ACTIVE; view всегда в capabilities.
Покрытие модуля policy — не ниже 95 %.
P7 обязательно.
```
