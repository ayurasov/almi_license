# I1-04. Утилита `almi-keytool` (E02-01)

```text
История E02-01. Реализуй tools/almi-keytool — консольную утилиту на Python (click), без зависимости от server/.

Команды:
- init-root --out <dir>: пара Ed25519; закрытый ключ шифруется паролем (Argon2id, параметры: t=3, m=256 MiB, p=1; XChaCha20-Poly1305 из PyNaCl); пароль вводится дважды, без эха;
- issue-cert --root <file> --subject-pub <file> --role issuer|local_server --kid <kid> --valid-days <n> [--customer <id>] [--products a,b]: сертификат alm-cert+jws по разделу 6 docs/specs/02-interaction-spec.md;
- revoke-cert --root <file> --kid <kid>: добавляет kid в список отзыва;
- export-trust --root <file> --issuers <dir> --out trust.json: пакет доверия по схеме contracts/schemas/trust.json;
- verify <file>: проверка любого объекта по цепочке.
Требования: работа без сети; секреты не печатаются; каждая команда пишет журнал операций в keytool.log (что, когда, отпечаток ключа).
Тесты: результаты на dev-ключах совпадают с векторами contracts/vectors/jws; неверный пароль — отказ без утечки информации; повреждённый файл ключа — отказ.
Ревью технического лидера обязательно (P7, область «Криптография»).
```
