# Marins Facade Control Center v0.6.8

[![Открыть в GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/Kontrakevich/MarinsFasad?quickstart=1)

Стабильная staged-сборка системы управления генерацией и согласованием фасадных решений. Исходный runtime `v0.6.0` автоматически обновляется патчами до фактической версии `v0.6.8` при выполнении setup-скрипта.

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
- автоматический Codespaces startup и health-check;
- runtime patches `v0.6.1–v0.6.8`.

## Запуск через GitHub

1. Нажмите **Открыть в GitHub Codespaces**.
2. Создайте Codespace на ветке `main`.
3. Codespaces автоматически распакует базовую сборку, применит патчи до `v0.6.8`, установит зависимости, выполнит тесты и запустит порт `8070`.
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

Setup-скрипт выполняет:

- `python -m compileall app`;
- автоматические smoke/workflow tests;
- FastAPI health-check;
- запуск Uvicorn на порту `8070`.

Живой платный вызов OpenRouter требует настроенного `OPENROUTER_API_KEY`.

## Release architecture

Базовый архив `v0.6.0` хранится частями в:

```text
release/v060_xz
```

Codespaces разворачивает runtime в:

```text
.runtime/MarinsFacade_v0.6.0
```

После развёртывания setup-скрипт последовательно применяет патчи и формирует фактическую стабильную сборку `v0.6.8`.

## Текущая стабильная версия

```text
v0.6.8
```
