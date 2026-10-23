# I1-02. Эталонные векторы (E00-04)

```text
Создай эталонные векторы в contracts/vectors/. Они — общий тест для сервера (Python) и DL (C++), поэтому генерировать их нужно независимо от будущей реализации сервера.

1. tools/vectors/generate.py — отдельный скрипт на PyNaCl (не cryptography и не код server/): фиксированные seed для ключей dev-root, dev-issuer, dev-local-server, dev-device; результат — keys/*.pub, keys/*.key (только dev).
2. jws/*.json: 12 векторов. Каждый: {"name","description","jws","trust_roots","now","expected":{"valid":bool,"error":code|null,"claims":{…}|null}}. Обязательные случаи: верная аренда; верная аренда локального сервера (цепочка из 3 звеньев); чужая подпись; изменённая полезная нагрузка; отозванный kid; истёкший сертификат ключа выпуска; seq меньше текущего; seq равен текущему; неизвестный alg; alg none; неверный typ; лишние байты в base64url.
3. policy/*.json: 36 векторов PolicyEngine. Каждый: {"name","policy":{…},"license":{"valid_until","support_until","status"},"now","last_success_at","expected":{"state","capabilities","messages_ids","lease_exp"}}. Покрой: каждое состояние раздела 8.1 docs/specs/01-architecture.md; границы (ровно в момент valid_until, за секунду до, через секунду); notify_before_days = 0; grace_days = 0; restricted_days = null и число; expiry_action none/restrict/block; enforcement monitor; offline_grace_days null и 3; бессрочная лицензия; отозванная; часовые пояса (valid_until в 21:00 UTC = полночь МСК).
4. request-signature/*.json: 6 векторов строки подписи запроса по разделу 4.4 docs/specs/02-interaction-spec.md (GET без тела, POST с телом, юникод в теле, неверный nonce, просроченное время, изменённый путь).
5. README.md: формат векторов и правило — векторы меняются только с ревью технического лидера.

Ожидаемые значения policy-векторов рассчитай вручную по таблицам раздела 8 docs/specs/01-architecture.md и раздела 7 docs/specs/02-interaction-spec.md, а не кодом. Для каждого вектора добавь поле "reasoning" — одна фраза, почему ожидается такое состояние.
Коммит: contract: reference vectors v1 (E00-04).
```

После генерации технический лидер проверяет все `reasoning` в policy-векторах вручную: это единственная точка, где ошибка ассистента потом тиражируется в сервер и DL.
