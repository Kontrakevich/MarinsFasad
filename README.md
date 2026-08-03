# Marins Facade Control Center v0.6.0

[![Открыть в GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/Kontrakevich/MarinsFasad?quickstart=1)

Чистая staged-сборка на базе интерфейса `Marins_EKB_Facade_OpenRouter_v0.5.5`.

## Основной процесс

```text
Source
→ Geometry
→ Approval
→ Environment
→ Approval / Final Lock
→ Branding
→ Approval
```

## Реализовано

- project manager;
- загрузка неизменяемого исходника;
- Perspective Grid с четырьмя перемещаемыми угловыми точками;
- внутренние пунктирные линии сетки;
- Undo / Redo / Reset;
- full-frame homography без crop по границе управляющей плоскости;
- сравнение Source / Corrected;
- отдельные approve/revise-циклы Geometry, Environment и Branding;
- сохранение всех версий и комментариев;
- Current / Revisions / History для каждого Skill;
- system prompt, скомпилированный из текущего Skill, показывается до AI-запуска;
- Environment запускается только из approved Geometry;
- Final автоматически фиксируется после approved Environment;
- интерактивное выделение зоны вывески;
- Branding запускается только из locked Final;
- OpenRouter image adapter;
- redacted provider diagnostics без ключей и base64-изображений;
- автоматический Codespaces startup и health-check.

## Запуск через GitHub

1. Нажмите **Открыть в GitHub Codespaces**.
2. Создайте Codespace на ветке `main`.
3. Codespaces автоматически распакует сборку, установит зависимости, выполнит тесты и запустит порт `8070`.
4. GitHub откроет панель в отдельной вкладке.

Для AI-генераций добавьте repository Codespaces secret:

```text
OPENROUTER_API_KEY
```

Путь в GitHub:

```text
Settings → Secrets and variables → Codespaces → New repository secret
```

После добавления секрета перезапустите Codespace.

## Ручной запуск в Codespaces

```bash
bash release/setup_v060.sh
bash release/start_v060.sh
```

Лог сервера:

```bash
cat /tmp/marins-facade-v060.log
```

## Сборочная проверка

Локально выполнены:

- `python -m compileall app`;
- 4 автоматических smoke/workflow tests;
- FastAPI health endpoint;
- локальный запуск Uvicorn.

Живой платный вызов OpenRouter не выполнялся.

## Release container

Полная сборка хранится в:

```text
release/MarinsFacade_v0.6.0.zip.b64
```

Codespaces декодирует её в:

```text
.runtime/MarinsFacade_v0.6.0
```
