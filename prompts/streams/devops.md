# 12.2. DevOps

| Задача | Промпт |
|---|---|
| Скрипт установки | «Напиши deploy/airgap-bundle/install.sh по разделу 9 docs/specs/07-environments.md: bash, set -euo pipefail, проверка версии Docker и свободного места, загрузка образов docker load, генерация секретов (openssl rand), запуск compose, ожидание /ready до 120 с, вывод следующего шага. Повторный запуск не ломает установленную систему. Проверка shellcheck.» |
| Резервное копирование | «Напиши deploy/central/backup.sh и restore.sh: pg_dump в формате custom, шифрование age открытым ключом из переменной, хранение 30 дней с удалением старых, проверка восстановимости pg_restore --list; restore — в новую БД с последующим переключением. Учебный сценарий восстановления — в docs/runbook.md.» |
| Конвейер выпуска | «Добавь .github/workflows/release.yml по разделам 6 и 10 docs/specs/07-environments.md: по тегу v*-rc* — сборка, deploy-staging, e2e, load; по тегу v* — bundle-airgap, публикация DL, deploy-prod с environment protection и двумя обязательными одобрениями.» |
