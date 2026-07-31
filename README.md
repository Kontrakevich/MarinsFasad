# Marins Fasad Control Center

[![Открыть в GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/Kontrakevich/MarinsFasad?quickstart=1)

Панель управления конвейером подготовки архитектурных изображений:

1. Коррекция геометрии исходника.
2. Ручное подтверждение или отправка на доработку.
3. Генерация окружения на базе подтвержденной геометрии.
4. Подтверждение результата и сохранение в `data/projects/<project>/final/`.
5. Размещение брендированной вывески по выделенной прямоугольной области.
6. Версионирование рабочих skill после подтверждения результата.

## Запуск прямо через GitHub

1. Нажмите кнопку **Открыть в GitHub Codespaces** выше.
2. Подтвердите создание Codespace.
3. Дождитесь установки зависимостей.
4. Сервер запустится автоматически на порту `8070`.
5. GitHub откроет панель в отдельной вкладке.

Для API-ключей откройте настройки Codespaces репозитория и добавьте секреты:

- `OPENROUTER_API_KEY`
- `TOKENROUTER_API_KEY`
- другие ключи провайдеров по мере подключения.

Порт панели имеет приватную видимость: доступ к нему получает только владелец Codespace.

## Запуск Windows

1. Скопируйте `.env.example` в `.env` и заполните ключи.
2. Запустите `01_INSTALL.bat`.
3. Запустите `02_RUN.bat`.
4. Откройте `http://127.0.0.1:8070`.

## API

- `POST /api/projects` — создать проект.
- `POST /api/projects/{id}/source` — загрузить исходник.
- `POST /api/projects/{id}/geometry/run` — выполнить коррекцию геометрии.
- `POST /api/projects/{id}/geometry/approve` — подтвердить геометрию.
- `POST /api/projects/{id}/geometry/revise` — отправить комментарий на доработку.
- `POST /api/projects/{id}/environment/run` — выполнить генерацию окружения.
- `POST /api/projects/{id}/environment/approve` — подтвердить окружение и записать `final`.
- `POST /api/projects/{id}/branding/run` — создать вариант с вывеской.
- `POST /api/projects/{id}/branding/approve` — подтвердить брендирование.

Текущая сборка содержит интерфейс, хранение проектов, этапы утверждения, журнал действий и версионирование skill. Внешние генераторы подключаются через адаптеры в `app/providers.py`.
