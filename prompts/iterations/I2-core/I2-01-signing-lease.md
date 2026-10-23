# I2-01. Подпись и выпуск аренды (E02-02, E02-03)

```text
Истории E02-02 и E02-03 (выполняются последовательно в одной ветке, два запроса на слияние).

Часть 1 — infra/crypto: реализация CryptoProvider на библиотеке cryptography (Ed25519). Ключ выпуска читается из файла SIGNING_KEY_FILE (Docker secret) при старте; kid и сертификат — из SIGNING_CERT_FILE. Методы sign(payload: bytes) -> bytes, verify(pub, payload, sig) -> bool, kid, chain. Ключ не попадает в repr, журналы, исключения.

Часть 2 — signing.domain: issue_jws(typ, claims) -> str. Заголовок по разделу 6.1 docs/specs/02-interaction-spec.md; полезная нагрузка — канонический JSON (sort_keys, separators=(',',':'), ensure_ascii=False, UTF-8); chain — сертификат ключа выпуска.

Тесты:
- выпущенный JWS проходит проверку tools/vectors (независимая реализация на PyNaCl);
- выпущенный JWS проходит проверку модулем DL (тест в CI вызывает lm_tests с параметром файла);
- повторный выпуск тех же claims даёт тот же байтовый результат (детерминированность Ed25519 и канонизации).
P7 обязательно.
```
