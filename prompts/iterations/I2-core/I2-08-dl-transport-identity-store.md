# I2-08. Транспорт, отпечаток и хранилище DL (E13-03, E13-04, E13-05)

```text
Истории E13-03, E13-04, E13-05 — три отдельные ветки, общая сессия планирования.

Transport (E13-03): libcurl; HTTPS с проверкой цепочки по системному хранилищу (Windows — CURLSSLOPT_NATIVE_CA, Linux — /etc/ssl/certs); системный прокси (WinHTTP на Windows, переменные окружения на Linux); таймауты connect 10 с, total 30 с; повторы только для 429/503 и сетевых ошибок, с Retry-After и экспоненциальной задержкой (максимум 3); подпись запросов по разделу 4.4 docs/specs/02-interaction-spec.md — проверка на векторах contracts/vectors/request-signature.

InstanceIdentity (E13-04): компоненты fp-v1 по разделу 2.4: Windows — HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid, SMBIOS UUID (GetSystemFirmwareTable), серийный номер системного диска (IOCTL_STORAGE_QUERY_PROPERTY), MAC первого физического адаптера; Linux — /etc/machine-id, /sys/class/dmi/id/product_uuid (если доступен без root), серийный номер корневого диска (/sys/block/*/device/serial или udev), MAC первого физического интерфейса. Хэш: base64url(SHA-256("almi-fp-v1|" + имя + "|" + значение)). Недоступный компонент — "unknown". Сырые значения не сохраняются и не журналируются. instance_id — UUID v4 при первом запуске, хранится в SecureStore.

SecureStore (E13-05): Windows — DPAPI CryptProtectData с CRYPTPROTECT_LOCAL_MACHINE, файл %ProgramData%\ALMI\License\<product>\store.bin; Linux — /var/lib/almi/license/<product>/store.bin с правами 0600, шифрование XChaCha20-Poly1305 ключом HKDF(machine-id, "almi-store-v1"); при отсутствии прав на системный каталог — каталог пользователя. Запись атомарная (временный файл + rename). Повреждённый файл — LM_ERR_STORE_CORRUPTED, продукт продолжает работу как без активации.

Тесты: Transport — против локального тестового сервера (cpp-httplib) с ответами 200/429/503/таймаут; InstanceIdentity — стабильность между вызовами, формат хэша; SecureStore — запись, чтение, повреждение, атомарность.
P7 обязательно для Transport и SecureStore.
```
