## Лабораторная 3

JSON API доступно по адресу `/api`.

| Метод | URL | Назначение |
| --- | --- | --- |
| GET | `/api/remains?carbon_min=0&carbon_max=200&title=...` | Список опубликованных останков с фильтрами по содержанию C-14 и названию; `is_mine` показывает владельца |
| GET | `/api/remains/{id}` | Одна опубликованная запись; удалённые и черновики возвращают 404 |
| GET | `/api/remains/feed` | Первая запись ленты; также принимает `remains_id` и `next=true` |
| GET | `/api/remains/draft` | Черновик фиксированного пользователя |
| POST | `/api/remains/draft` | Создание черновика с multipart-полями `title`, `image_file`, `video_file`; оба файла передаются в MinIO |
| PUT | `/api/remains/{id}/publish` | Публикация черновика с JSON-полями `description`, `analysis_time_days`, `carbon_14_pmc` |
| POST | `/api/remains/{id}/likes` | Установка/снятие лайка JSON-полем `liked` со значением `1` или `0` |
| DELETE | `/api/remains/{id}` | Мягкое удаление своей опубликованной записи: статус меняется на `deleted` |
| POST | `/api/researchers` | Регистрация исследователя; пароль хранится в виде PBKDF2-хеша |
| POST | `/api/researchers/auth` | Аутентификация |
| POST | `/api/researchers/logout` | Деавторизация |

Ответы каталога и ленты не содержат записей со статусом `deleted`. `is_liked` и `likes_count` вычисляются по таблице `remains_likes`. Значение `liked=0` удаляет лайк текущего пользователя; повторный `liked=1` не создаёт дублей.

Таблицы БД:

| Таблица | Поля |
| --- | --- |
| `researchers` | `id INTEGER PK`, `username VARCHAR(80) UNIQUE`, `full_name VARCHAR(160)`, `password VARCHAR(255)` |
| `remains` | `id INTEGER PK`, `title VARCHAR(120)`, `description VARCHAR(2000)`, `status VARCHAR(16)`, `image_url VARCHAR(1024) NOT NULL`, `video_url VARCHAR(1024) NOT NULL`, `analysis_time_days INTEGER`, `carbon_14_pmc NUMERIC(7,3)`, `created_at TIMESTAMPTZ`, `creator_id INTEGER FK -> researchers.id`, `published_at TIMESTAMPTZ` |
| `remains_likes` | `id INTEGER PK`, `researcher_id INTEGER FK -> researchers.id`, `remains_id INTEGER FK -> remains.id`, unique pair (`researcher_id`, `remains_id`) |
