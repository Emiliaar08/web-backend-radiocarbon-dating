## Лабораторная 3

JSON API доступно по адресу `/api`.

Всего 10 методов: 3 GET, 5 POST, 1 PUT и 1 DELETE. Пользователь фиксируется функцией `current_researcher_id()` в `api/remains_api.py`: `CURRENT_RESEARCHER_ID = 1`. Авторизация и Redis в этой лабораторной не используются.

| Метод | URL | Назначение |
| --- | --- | --- |
| GET | `/api/remains?carbon_min=0&carbon_max=200&title=...` | Список опубликованных останков с фильтрами по содержанию C-14 и названию; `is_mine` показывает владельца |
| GET | `/api/remains/feed` | Первая запись ленты; `?remains_id=9` открывает запись 9, `?remains_id=9&next=true` возвращает следующую опубликованную запись |
| GET | `/api/remains/draft` | Черновик фиксированного пользователя |
| POST | `/api/remains/draft` | Создание черновика с multipart-полями `title`, `image_file`, `video_file`; оба файла передаются в MinIO |
| PUT | `/api/remains/{id}/publish` | Публикация черновика с JSON-полями `description`, `analysis_time_days`, `carbon_14_pmc` |
| POST | `/api/remains/{id}/likes` | Установка/снятие лайка JSON-полем `liked` со значением `1` или `0` |
| DELETE | `/api/remains/{id}` | Мягкое удаление своей опубликованной записи: статус меняется на `deleted` |
| POST | `/api/researchers` | Регистрация исследователя; пароль хранится в виде PBKDF2-хеша |
| POST | `/api/researchers/auth` | Заглушка аутентификации для лабораторной 4 |
| POST | `/api/researchers/logout` | Заглушка деавторизации для лабораторной 4 |

Ответы каталога и ленты не содержат записей со статусом `deleted`. `is_liked` и `likes_count` вычисляются по таблице `remains_likes`. Значение `liked=0` удаляет лайк текущего пользователя; повторный `liked=1` не создаёт дублей.

Лента возвращает только 5 полей: `id`, `title`, `video_url`, `is_liked`, `likes_count`. Следующая запись выбирается запросом к БД по существующему ID, а не прибавлением единицы к ID.

Создание черновика принимает только название и два файла. Публикация заполняет описание и два поля по теме; название и медиа уже созданного черновика не редактируются. Заполненные поля черновика нельзя перезаписать. Статусы, создатель и даты задаются сервером.

Коллекция `remains-api.postman_collection.json` содержит все 10 методов. Для проверки перехода к следующей записи добавьте `remains_id` и `next=true` к запросу ленты. HTML-интерфейс использует только три шаблона: ленту, добавление и плитку. Четвёртая страница авторизации предусмотрена только на диаграмме; Swagger относится к лабораторной 4 и здесь отключён.

Таблицы БД:

| Таблица | Поля |
| --- | --- |
| `researchers` | `id INTEGER PK`, `username VARCHAR(80) UNIQUE`, `full_name VARCHAR(160)`, `password VARCHAR(255)` |
| `remains` | `id INTEGER PK`, `title VARCHAR(120)`, `description VARCHAR(2000)`, `status VARCHAR(16)`, `image_url VARCHAR(1024) NOT NULL`, `video_url VARCHAR(1024) NOT NULL`, `analysis_time_days INTEGER`, `carbon_14_pmc NUMERIC(7,3)`, `created_at TIMESTAMPTZ`, `creator_id INTEGER FK -> researchers.id`, `published_at TIMESTAMPTZ` |
| `remains_likes` | `id INTEGER PK`, `researcher_id INTEGER FK -> researchers.id`, `remains_id INTEGER FK -> remains.id`, unique pair (`researcher_id`, `remains_id`) |
