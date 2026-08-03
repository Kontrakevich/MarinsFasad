# Marins Facade v0.6.0 release

`MarinsFacade_v0.6.0.zip.b64` — полная проверенная сборка в Base64-контейнере.

Codespaces автоматически:

1. декодирует архив;
2. распаковывает его в `.runtime/MarinsFacade_v0.6.0`;
3. устанавливает зависимости;
4. запускает 4 smoke/workflow tests;
5. запускает FastAPI на порту `8070`;
6. выполняет health-check.

Ручной запуск внутри Codespaces:

```bash
bash release/setup_v060.sh
bash release/start_v060.sh
```

Лог сервера:

```bash
cat /tmp/marins-facade-v060.log
```

Сборка содержит:

- UI на базе `Marins_EKB_Facade_OpenRouter_v0.5.5`;
- project manager;
- perspective grid с четырьмя draggable-точками;
- undo/redo/reset;
- full-frame homography без crop по границе сетки;
- approve/revise state machine;
- current/history/revisions для Skills;
- prompt preview перед AI-запуском;
- OpenRouter image adapter для Environment и Branding;
- final lock;
- интерактивную зону вывески;
- журнал событий и redacted provider diagnostics.

Живой платный вызов OpenRouter при сборочной проверке не выполнялся.
