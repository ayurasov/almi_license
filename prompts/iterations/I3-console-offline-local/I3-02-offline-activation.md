# I3-02. Офлайн-активация (E08-01)

```text
История E08-01. Реализуй POST /api/v1/offline/requests (operationId=processOfflineRequest).

Раздел 10 docs/specs/02-interaction-spec.md; схемы contracts/schemas/alk-req.json и alk-lic.json.
Порядок:
1. Размер файла до 64 КБ — проверка до чтения тела целиком (Nginx client_max_body_size и проверка в представлении).
2. Разбор контейнера {format, version, payload}; format = alk-req, version = 1, иначе 400 invalid_request.
3. Проверка подписи payload ключом устройства из самого запроса (device_pubkey), затем разбор полезной нагрузки.
4. Тип запроса: activate → тот же доменный сервис activation.domain.activate(), что и онлайн (никакой копии логики); release → activation.domain.release().
5. Ответ — файл alk-lic, Content-Disposition: attachment; filename="<instance_id>.alk-lic".
Тесты: файл, созданный lm-demo offline-request, обрабатывается; изменённый байт — отказ; повтор того же файла — та же активация, место не занимается.
P7 обязательно (область «Разбор файлов и входа»).
```
