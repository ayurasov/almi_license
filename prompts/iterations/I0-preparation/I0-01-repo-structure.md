# I0-01. Структура репозитория

```text
Создай структуру репозитория almi-license по разделу 14 docs/specs/01-architecture.md.

Сделай:
1. Каталоги: contracts/{schemas,vectors}, server/{almi_license,apps,infra,tests}, console, sdk/{cpp,php}, tools/{almi-keytool,conformance}, deploy/{central,local,dev,airgap-bundle}, docs/{adr,progress,specs}.
2. AGENTS.md — содержимое раздела 3 docs/specs/06-ai-rules.md без изменений.
3. CODEOWNERS по разделу 6 docs/specs/06-ai-rules.md.
4. .editorconfig, .gitignore (Python, Node, CMake, IDE), .pre-commit-config.yaml (ruff, ruff-format, eslint, clang-format, gitleaks).
5. Makefile с целями из раздела 5 docs/specs/07-environments.md; пока цели, для которых нет кода, печатают «not implemented» и завершаются с кодом 0.
6. README.md: назначение, ссылки на docs/specs, команды make.
7. docs/progress/stage1.md с разделами «Закрытые истории», «Текущая итерация», «Открытые вопросы».
8. CHANGELOG.md с разделом Unreleased.
Код приложений не пиши. Коммит: chore: repository skeleton (E00-05).
```
