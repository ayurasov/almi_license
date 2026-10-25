# almi-keytool

Офлайн-утилита рабочего места церемонии ключей (раздел 9 документа 1, E02-01): корневой ключ АЛМИ, сертификаты ключей выпуска и локальных серверов, список отзыва, пакет доверия, проверка любого подписанного объекта по цепочке.

```sh
cd tools/almi-keytool
uv run almi-keytool init-root --out ./root --kid root-2026
uv run almi-keytool issue-cert --root ./root/root.key.json --subject-pub issuer.pub \
    --role issuer --kid c-2026-01 --valid-days 730 --out issuers/c-2026-01.jws
uv run almi-keytool revoke-cert --root ./root/root.key.json --kid srv_01H…-1
uv run almi-keytool export-trust --root ./root/root.key.json --issuers ./issuers --out trust.json
uv run almi-keytool verify trust.json --trust-root ./root/root.pub.json
```

Сертификат локального сервера: `--role local_server --customer <id> --products a,b --server-id srv_… [--quota license_id=места …]`. Обычно его выпускает центральный сервер ключом выпуска (E09-02); утилита — для стендов и аварийных случаев.

## Гарантии

- Сеть не используется (проверяется тестом с запретом сокетов).
- Пароль вводится без эха, при создании — дважды; не печатается и не пишется в журнал.
- Закрытый ключ хранится только зашифрованным: Argon2id (t=3, m=256 МиБ, p=1) → XChaCha20-Poly1305; все остальные поля файла — связанные данные AEAD. Неверный пароль и изменённый файл дают одно сообщение и код 2; повреждённый файл — отказ с кодом 2.
- `keytool.log` (`--log`): JSON-строка на операцию — время, команда, kid, отпечаток ключа `SHA256:…`, результат.
- Сертификаты на dev-ключах совпадают с `contracts/vectors` байт в байт; `verify` даёт ожидаемый результат на всех векторах `jws/` (порядок проверок и коды — `contracts/vectors/README.md`).

## Файлы

| Файл | Содержимое |
|---|---|
| `root.key.json` (права 0600) | `format: almi-root-key`, `version: 1`, `kid`, `pub`, `kdf` (`argon2id`, `opslimit`, `memlimit`, `parallelism`, `salt`), `cipher` (`xchacha20poly1305-ietf`, `nonce`, `ciphertext` — seed Ed25519) |
| `root.pub.json` | `{"kid", "alg": "EdDSA", "pub"}` — встраивается в продукты, передаётся в `verify --trust-root` |
| `revoked.json` | `{"revoked_kids": […]}` рядом с ключом; публикуется через `export-trust` |
| `trust-state.json` | Последний `seq` пакета доверия; каждый `export-trust` увеличивает его на 1 |
| `trust.json` | Ответ `/api/v1/trust`: `bundle` (`alm-trust+jws`), `roots`, `issuers`, `revoked_kids`, `seq` |

Открытый ключ субъекта (`--subject-pub`) — base64url (как `contracts/vectors/keys/*.pub`) или JSON с полем `pub`.

## Ограничения

Python не гарантирует обнуление памяти: seed после расшифровки живёт в объекте PyNaCl до завершения процесса. Поэтому утилита запускается на выделенном офлайн-рабочем месте и завершается после каждой операции.
