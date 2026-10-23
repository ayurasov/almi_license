# I2-03. Подпись запросов (E05-01)

```text
История E05-01. Реализуй проверку заголовка ALMI-Signature в server/apps/api_product/auth.py как DRF Authentication.

Строка подписи — строго по разделу 4.4 docs/specs/02-interaction-spec.md:
ALMI-REQ-V1\n<METHOD>\n<path с query>\n<created>\n<nonce>\n<base64url(sha256(сырое тело))>
- тело берётся из request.body в байтах до разбора JSON;
- created в пределах ±300 с от Clock.now(), иначе 401 clock_skew с server_time в ответе;
- nonce уникален в окне 600 с для keyid (таблица в PostgreSQL с индексом и очисткой фоновой задачей), повтор — 401 signature_invalid;
- keyid = activation_id → открытый ключ из Activation.device_pubkey; для activate (активации ещё нет) ключ берётся из тела device_pubkey, а запрос подписан этим же ключом;
- сравнения — hmac.compare_digest, проверка подписи — CryptoProvider.verify.
Тесты: все векторы contracts/vectors/request-signature; тест на повтор nonce; тест на изменение одного байта тела.
P7 обязательно.
```
