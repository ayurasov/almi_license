# Эталонные векторы v1 (E00-04)

Общий тест для сервера (Python: `signing`, `policy`, `api_product/auth`) и модуля DL (C++: `LeaseVerifier`, `StateEvaluator`, `Transport`). Оба обязаны давать на векторах один и тот же результат.

**Правило.** Векторы меняются только с ревью технического лидера. Если реализация расходится с вектором, ошибка ищется в реализации; «исправлять» вектор под код нельзя (P12, документ 10).

| Каталог | Что | Как получен |
|---|---|---|
| `keys/` | Тестовые ключи Ed25519 `dev-root`, `dev-issuer`, `dev-local-server`, `dev-device` | `tools/vectors/generate.py`, фиксированные seed |
| `jws/` | 12 векторов проверки аренды и цепочки | Генератор; дефект каждого вектора задан явно |
| `request-signature/` | 6 векторов подписи запроса (раздел 4.4 документа 2) | Генератор |
| `policy/` | 39 векторов `PolicyEngine` / `StateEvaluator` | Вручную; поле `reasoning` объясняет ожидание |

```sh
uv run --script tools/vectors/generate.py           # перегенерировать keys/, jws/, request-signature/
make vectors                                        # файлы совпадают с генератором, утверждения валидны по схемам
```

## Ключи

Seed ключа = `SHA-256("almi-license dev vectors v1|" + имя)`. `*.key` — seed (32 байта), `*.pub` — открытый ключ (32 байта); оба в base64url без `=` и с переводом строки в конце. Только для `dev` и тестов: в сборки, кроме `LM_TRUST_ROOTS=dev`, не попадают (раздел 3 документа 7). Исключение gitleaks для этого каталога — `.gitleaks.toml`.

| Ключ | kid | Роль |
|---|---|---|
| `dev-root` | `dev-root` | Корень доверия; подписывает сертификат ключа выпуска |
| `dev-issuer` | `dev-issuer-1` (действующий), `dev-issuer-0` (истёкший сертификат) | Ключ выпуска центрального сервера |
| `dev-local-server` | `srv_01JAB3K9M2N4P6Q8R0S2T4V6W8-1` | Ключ локального сервера, сертификат от ключа выпуска |
| `dev-device` | `device` | Ключ устройства: подпись запросов; отпечаток в аренде — RFC 7638 |

## Общие соглашения

- JWS — компактный, `base64url` без `=`; JSON заголовка и утверждений — UTF-8 без пробелов. Подпись Ed25519 — 64 байта.
- `device_key_thumbprint` — отпечаток RFC 7638 открытого ключа устройства: `base64url(SHA-256('{"crv":"Ed25519","kty":"OKP","x":"<pub>"}'))`.
- Время: в `jws/` и `request-signature/` — Unix (как `iat`, `nbf`, `exp` в утверждениях); в `policy/` — RFC 3339 UTC (как даты лицензии).
- Утверждения аренд и сертификатов валидны по `contracts/schemas/lease.schema.json` и `cert.schema.json` (проверяет `make vectors`).

## `jws/*.json`

```json
{"name": "…", "description": "…", "jws": "<компактный JWS аренды>",
 "trust_roots": [{"kid": "dev-root", "alg": "EdDSA", "pub": "…"}],
 "now": 1762071300,
 "context": {"product_code": "…", "instance_id": "…", "device_key_thumbprint": "…", "stored_seq": 16, "revoked_kids": []},
 "expected": {"valid": true, "error": null, "claims": {…}}}
```

`context` — состояние проверяющего: свой продукт, экземпляр и ключ устройства, `seq` последней применённой аренды, список отзыва. `claims` заполняется только для верных векторов.

Порядок проверок и код результата (первый сработавший):

| Шаг | Проверка | `error` |
|---|---|---|
| 1 | Три сегмента, строгий base64url, заголовок — JSON-объект | `malformed` |
| 2 | `alg` = `EdDSA` | `alg_unsupported` |
| 3 | Подпись — ровно 64 байта | `malformed` |
| 4 | `typ` = `alm-lease+jws` | `typ_invalid` |
| 5 | `chain` проверяется до встроенного корня: каждый сертификат подписан следующим или корнем; `kid` листа = `kid` заголовка | `chain_invalid` |
| 6 | Ни один `kid` цепочки и подписи не в `revoked_kids` | `kid_revoked` |
| 7 | `now` в пределах `nbf`…`exp` каждого сертификата | `cert_expired` |
| 8 | Подпись аренды ключом листа цепочки (до разбора полезной нагрузки) | `signature_invalid` |
| 9 | Полезная нагрузка — JSON-объект, `ver` = 1, `exp` (если есть) — целое; истёкший `exp` аренду не отклоняет, а влияет на состояние (раздел 7.2 документа 2) | `malformed` |
| 10 | Для ключа `local_server`: продукт и заказчик аренды в `scope` сертификата | `scope_mismatch` |
| 11 | `aud` = свой продукт | `audience_mismatch` |
| 12 | `subject.instance_id` и `device_key_thumbprint` — свои | `subject_mismatch` |
| 13 | `seq` > `stored_seq` | `seq_not_greater` |
| 14 | `nbf` ≤ `now` + 24 ч | `not_yet_valid` |

Коды — словарь результата проверки (сервер и `LeaseVerifier`), а не коды ошибок API раздела 16; модуль DL отображает любой из них в `LM_ERR_INVALID_SIGNATURE`.

## `request-signature/*.json`

```json
{"name": "…", "description": "…", "public_key": "<pub dev-device>", "server_now": 1762071300,
 "request": {"method": "POST", "path": "<путь, на который отправлен запрос>", "body": "<тело как строка UTF-8>"},
 "signed": {"keyid": "act_…", "alg": "ed25519", "created": 1762071300, "nonce": "…", "path": "<подписанный путь>"},
 "expected": {"body_sha256": "…", "signing_string": "…", "signature": "…", "header": "…", "valid": true, "error": null}}
```

`signing_string` — строка раздела 4.4 документа 2 для `signed` (строки через `\n`), `body_sha256` — `base64url(SHA-256(байты UTF-8 тела))`, `signature` — Ed25519 в base64url, `header` — значение `ALMI-Signature`. Сервер проверяет `request` против `signed` и `server_now`; коды ошибок — из раздела 16: `nonce` не 16 байт и изменённый путь → `signature_invalid`, `created` вне ±300 с → `clock_skew`.

## `policy/*.json`

```json
{"name": "…", "reasoning": "…", "policy": {…раздел 6.4…},
 "license": {"type": "subscription", "status": "active", "valid_until": "…", "support_until": "…", "capabilities": […]},
 "trial": {"first_launch": "…", "product_capabilities": […]},
 "now": "…", "last_success_at": "…",
 "expected": {"state": "…", "capabilities": […], "messages_ids": […], "lease_exp": "…"}}
```

`license` = `null` и `trial` — только для случаев без аренды. Алгоритм — раздел 7.2 документа 2; дополнительные правила (решение 12, `docs/progress/stage1.md`):

1. `exp` аренды = `last_success_at` + `offline_grace_days`; `lease_exp` — `exp` новой аренды, выпускаемой в `now`: `now` + `offline_grace_days` или `null`.
2. `support` доступна, пока `now` < `support_until` (`null` — без срока); для бессрочной лицензии после `support_until` снимается и `updates`, если она в `restricted_caps`. В `monitor` функции не меняются.
3. Без аренды (`TRIAL`, `UNLICENSED`) — все функции продукта, кроме `support`.
4. `BLOCKED` и `REVOKED`: `read_only_caps`, при `hard_block_mode = no_start` — пусто.
5. `messages_ids` — сообщения раздела 3.1 документа 5 для состояния; `notice.7days` — при ≤ 7 днях до `valid_until`, `trial.ending` — при ≤ 5 днях триала (дни округляются вверх). `active.restored` и `monitor.over_limit` зависят от истории и счётчиков и в векторах не участвуют.
6. Статус `suspended` алгоритм не выделяет: состояние считается по датам.
