## Лабораторная 4

JSON API доступно по адресу `/api`, интерактивная документация Swagger — `/api/docs`. Веб-сервис использует PostgreSQL для данных и Redis для серверных сессий. После успешного входа сервер возвращает HttpOnly cookie `radiocarbon_session`; идентификатор пользователя и время жизни сессии хранятся в Redis. Пароли в PostgreSQL хранятся только в виде PBKDF2-хеша.

Запуск локального окружения в активном виртуальном окружении: `pip install -r requirements.txt`, `docker compose up -d`, `alembic upgrade head`, затем `uvicorn main:app --reload --port 8002`. После запуска API откройте `http://127.0.0.1:8002/api/docs`.

| № | Метод | URL | Доступ и назначение |
| --- | --- | --- | --- |
| 1 | GET | `/api/remains?carbon_min=0&carbon_max=200&title=...` | Публичный список опубликованных останков с фильтрами по C‑14 и названию |
| 2 | GET | `/api/remains/feed` | Публичная лента: первая запись, запись по `remains_id` или следующая при `next=true` |
| 3 | GET | `/api/remains/draft` | Авторизованный исследователь получает свой черновик без ID в URL |
| 4 | POST | `/api/remains/draft` | Авторизованный исследователь создаёт черновик с `title`, `image_file`, `video_file`; файлы загружаются в MinIO |
| 5 | PUT | `/api/remains/{remain_id}/publish` | Автор публикует свой черновик, передав `description`, `analysis_time_days`, `carbon_14_pmc` |
| 6 | DELETE | `/api/remains/{remain_id}` | Автор логически удаляет свою опубликованную запись |
| 7 | POST | `/api/remains/{remain_id}/likes` | Авторизованный пользователь ставит или снимает лайк с помощью `liked: 1` или `liked: 0` |
| 8 | POST | `/api/researchers` | Регистрация: `username`, `full_name`, `password` |
| 9 | POST | `/api/researchers/auth` | Аутентификация: проверка пароля, создание Redis-сессии и установка cookie |
| 10 | POST | `/api/researchers/logout` | Удаление Redis-сессии и очистка cookie |

В Swagger сначала выполните `POST /api/researchers` для регистрации, затем `POST /api/researchers/auth`. Cookie устанавливается браузером автоматически; в Swagger cookie-схема `SessionCookie` также описана для защищённых методов. Публичные GET списка и ленты работают без авторизации. Черновик, публикация, лайк и удаление требуют сессию; публикация и удаление разрешены только создателю записи. После выхода прежняя cookie больше не авторизует запросы.

Redis запускается вместе с PostgreSQL и MinIO командой `docker compose up -d`. Проверить сессии можно так:

```shell
docker exec -it redis_session_store redis-cli --scan --pattern 'radiocarbon:session:*'
docker exec -it redis_session_store redis-cli HGETALL 'radiocarbon:session:<идентификатор-сессии>'
```

Для проверки гостевого доступа откройте Swagger в приватном окне и вызовите публичный GET, затем попробуйте защищённый PUT без cookie: сервер вернёт `401`. Выполните вход и повторите PUT для своего черновика.

В пользовательском интерфейсе три HTML-страницы: лента, добавление останков и плитка с фильтром. При создании черновика вводятся название и два файла. Перед публикацией заполняются только пустые поля: описание, время анализа в рабочих днях и содержание C‑14 в pMC. Уже сохранённые поля черновика доступны только для просмотра; их изменение отклоняется сервером. ID, статус, создатель и даты выставляются сервером. Файлы дерева по умолчанию находятся в проекте (`static/remains/wood.jpg`, `static/remains/wood-video.mp4`); загруженные через API файлы сохраняются в MinIO.

`likes_count` и `is_liked` вычисляются по `remains_likes`. Лайки принадлежат текущему исследователю из cookie-сессии. Для изменения данных используется SQLAlchemy ORM; удаление меняет статус на `deleted`, не удаляя строку.

Таблицы базы данных:

| Таблица | Поля |
| --- | --- |
| `researchers` | `id INTEGER PK`, `username VARCHAR(80) UNIQUE`, `full_name VARCHAR(160)`, `password VARCHAR(255)` — PBKDF2-хеш |
| `remains` | `id INTEGER PK`, `title VARCHAR(120)`, `description VARCHAR(2000)`, `status VARCHAR(16)`, `image_url VARCHAR(1024) NOT NULL`, `video_url VARCHAR(1024) NOT NULL`, `analysis_time_days INTEGER`, `carbon_14_pmc NUMERIC(7,3)`, `created_at TIMESTAMPTZ`, `creator_id INTEGER FK -> researchers.id`, `published_at TIMESTAMPTZ` |
| `remains_likes` | `id INTEGER PK`, `researcher_id INTEGER FK -> researchers.id`, `remains_id INTEGER FK -> remains.id`, unique pair (`researcher_id`, `remains_id`) |
