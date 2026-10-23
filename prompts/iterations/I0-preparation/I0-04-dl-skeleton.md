# I0-04. Каркас модуля DL

```text
Создай каркас модуля DL в sdk/cpp по разделу 15 docs/specs/02-interaction-spec.md.

1. CMakeLists.txt: C++17; цели license_module (shared), lm_tests (GoogleTest), lm-demo; зависимости libsodium, libcurl, nlohmann/json через FetchContent или vcpkg с фиксацией версий; статическая линковка зависимостей.
2. include/license_module.h — заголовок из раздела 15.1 docs/specs/02-interaction-spec.md без изменений.
3. src/: пустые реализации всех функций LM_*, возвращающие LM_ERR_NOT_INITIALIZED (кроме LM_GetVersion).
4. src/platform/{win,linux}/ — пустые файлы для платформенного кода.
5. Опция сборки LM_TRUST_ROOTS = dev | ci | test | staging | prod; для dev подключается contracts/vectors/keys/dev-root.pub.
6. .clang-format, .clang-tidy по разделу 4.3 docs/specs/06-ai-rules.md.
7. Тест: LM_GetVersion возвращает версию из CMake.
Проверь сборку на Linux (GCC) и Windows (MSVC) в CI. Коммит: chore(dl): cmake skeleton and public header (E13-01).
```

**Критерии выхода I0.** `make up` и `make test` работают у каждого участника; CI зелёный; `AGENTS.md` и `docs/specs/` в репозитории; защита веток `main` и `stage1` включена.
