import asyncio
import os
import subprocess
import sys
import unittest
from uuid import uuid4

import httpx
import psycopg
from psycopg import sql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from core.config import PROJECT_ROOT, settings


class Lab2Tests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_db = settings.DB_NAME
        cls.test_db = "radiocarbon_test_" + uuid4().hex[:12]
        cls.connection_options = {
            "host": settings.DB_HOST, "port": settings.DB_PORT,
            "user": settings.DB_USER, "password": settings.DB_PASSWORD,
        }
        with psycopg.connect(dbname="postgres", autocommit=True, **cls.connection_options) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {} ").format(sql.Identifier(cls.test_db)))
        cls.addClassCleanup(cls.remove_database)
        settings.DB_NAME = cls.test_db
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=PROJECT_ROOT, env={**os.environ, "DB_NAME": cls.test_db}, check=True, capture_output=True,
        )
        from main import app
        cls.app = app
        cls.seed = (PROJECT_ROOT / "db/seed.sql").read_text()

    @classmethod
    def remove_database(cls):
        settings.DB_NAME = cls.original_db
        if not cls.test_db.startswith("radiocarbon_test_"):
            raise RuntimeError("Refusing to drop a non-test database")
        with psycopg.connect(dbname="postgres", autocommit=True, **cls.connection_options) as connection:
            connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(cls.test_db)))

    async def asyncSetUp(self):
        self.assertEqual(settings.DB_NAME, self.test_db)
        with psycopg.connect(dbname=self.test_db, autocommit=True, **self.connection_options) as connection:
            connection.execute("TRUNCATE remains_likes, remains, researchers RESTART IDENTITY")
            connection.execute(self.seed)
        self.engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        sessions = async_sessionmaker(self.engine, expire_on_commit=False)

        async def test_session():
            async with sessions() as session:
                yield session

        from db.session import get_db
        self.app.dependency_overrides[get_db] = test_session
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        self.app.dependency_overrides.clear()
        await self.engine.dispose()

    async def query(self, statement, params=None):
        async with await psycopg.AsyncConnection.connect(dbname=self.test_db, **self.connection_options) as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(statement, params)
                if cursor.description:
                    return await cursor.fetchall()

    async def test_six_routes_and_filter_boundaries(self):
        from api.handlers import router
        routes = router.routes
        self.assertEqual(len(routes), 6)
        self.assertEqual(sum("GET" in route.methods for route in routes), 3)
        self.assertEqual(sum("POST" in route.methods for route in routes), 3)
        for threshold, count in [(0, 3), (1.385, 3), (1.386, 2), (34.45, 2), (34.451, 1), (73.338, 1), (73.339, 0), (200, 0)]:
            response = await self.client.get("/remains", params={"carbon_min": threshold})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.text.count('class="remains-card"'), count)
            self.assertNotIn('type="checkbox"', response.text)
            self.assertIn('name="carbon_min"', response.text)
        for threshold in ["-1", "201", "NaN", "Infinity", "word"]:
            self.assertEqual((await self.client.get("/remains", params={"carbon_min": threshold})).status_code, 422)

    async def test_feed_uses_next_existing_id(self):
        await self.query("UPDATE remains SET status = 'deleted' WHERE id IN (2, 3)")
        for new_id in [9, 10]:
            await self.query(
                "INSERT INTO remains (id, title, description, status, analysis_time_days, carbon_14_pmc, creator_id, published_at) "
                "VALUES (%s, 'Test', 'Sample', 'published', 14, 23.05, 999, now())", (new_id,),
            )
        for current, following in [(1, 9), (9, 10), (10, 1)]:
            response = await self.client.get("/remains/feed", params={"remains_id": current, "next": "true"})
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], f"/remains/feed?remains_id={following}")
        response = await self.client.get("/remains/feed?remains_id=1&expanded=true")
        self.assertIn('aria-expanded="true"', response.text)
        self.assertEqual(response.text.count('class="next-feed-button"'), 1)
        for remains_id in [2, 4, 5, 9999]:
            self.assertEqual((await self.client.get(f"/remains/feed?remains_id={remains_id}")).status_code, 404)

    async def test_draft_get_does_not_insert(self):
        before = await self.query("SELECT count(*) FROM remains")
        response = await self.client.get("/remains/draft")
        self.assertIn("Дерево", response.text)
        self.assertIn("Опубликовать", response.text)
        await self.query("UPDATE remains SET status='deleted' WHERE id=4")
        for _ in range(2):
            response = await self.client.get("/remains/draft")
            self.assertIn(">Далее</button>", response.text)
            self.assertNotIn('name="description"', response.text)
        self.assertEqual(before, await self.query("SELECT count(*) FROM remains"))

    async def test_create_then_publish_and_no_media_storage(self):
        await self.query("UPDATE remains SET status='deleted' WHERE id=4")
        response = await self.client.post("/remains/draft", data={"title": "  Лабораторный образец  ", "image_url": "http://bad/photo.jpg", "video_url": "http://bad/video.mp4", "creator_id": "1", "status": "published"})
        self.assertEqual(response.status_code, 303)
        rows = await self.query("SELECT id, title, status, image_url, video_url, creator_id, created_at, published_at FROM remains WHERE status='draft'")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        remains_id = row[0]
        self.assertEqual(row[1:6], ("Лабораторный образец", "draft", None, None, 999))
        self.assertIsNotNone(row[6])
        self.assertIsNone(row[7])
        response = await self.client.post(f"/remains/{remains_id}/publish", data={"title": row[1], "description": "Описание образца. Второе предложение.", "analysis_time_days": "12", "carbon_14_pmc": "23.05"})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], f"/remains/feed?remains_id={remains_id}")
        row = (await self.query("SELECT status, published_at, image_url, video_url FROM remains WHERE id=%s", (remains_id,)))[0]
        self.assertEqual(row[0], "published")
        self.assertIsNotNone(row[1])
        self.assertEqual(row[2:], (None, None))
        page = await self.client.get(response.headers["location"])
        self.assertIn('/static/images/default.jpg', page.text)
        self.assertIn('/static/videos/default.mp4', page.text)
        self.assertEqual((await self.client.post(f"/remains/{remains_id}/publish")).status_code, 404)

    async def test_validation_preserves_draft_and_escapes_input(self):
        for invalid in [{"description": " "}, {"analysis_time_days": "0"}, {"analysis_time_days": "2.5"}, {"carbon_14_pmc": "NaN"}, {"carbon_14_pmc": "201"}, {"carbon_14_pmc": "1.0001"}, {"title": " "}]:
            values = {"title": "<script>bad</script>", "description": "Описание", "analysis_time_days": "14", "carbon_14_pmc": "23.05", **invalid}
            response = await self.client.post("/remains/4/publish", data=values)
            self.assertEqual(response.status_code, 422)
            self.assertIn('role="alert"', response.text)
            self.assertNotIn("<script>bad</script>", response.text)
            self.assertEqual((await self.query("SELECT status FROM remains WHERE id=4"))[0][0], "draft")
        await self.query("UPDATE remains SET status='deleted' WHERE id=4")
        response = await self.client.post("/remains/draft", data={"title": " "})
        self.assertEqual(response.status_code, 422)
        self.assertEqual((await self.query("SELECT count(*) FROM remains WHERE status='draft'"))[0][0], 0)

    async def test_concurrent_creation_produces_one_draft(self):
        await self.query("UPDATE remains SET status='deleted' WHERE id=4")
        responses = await asyncio.gather(*(self.client.post("/remains/draft", data={"title": f"Образец {number}"}) for number in range(6)))
        self.assertTrue(all(response.status_code == 303 for response in responses))
        self.assertEqual((await self.query("SELECT count(*) FROM remains WHERE status='draft' AND creator_id=999"))[0][0], 1)

    async def test_cannot_publish_someone_elses_draft(self):
        await self.query("UPDATE remains SET creator_id=1 WHERE id=4")
        self.assertEqual((await self.client.post("/remains/4/publish")).status_code, 404)
        self.assertIn(">Далее</button>", (await self.client.get("/remains/draft")).text)

    async def test_soft_delete_preserves_row_likes_and_filter(self):
        likes_before = await self.query("SELECT count(*) FROM remains_likes WHERE remains_id=2")
        response = await self.client.post("/remains/2/delete", data={"carbon_min": "30"})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/remains?carbon_min=30")
        self.assertEqual((await self.query("SELECT status FROM remains WHERE id=2"))[0][0], "deleted")
        self.assertEqual(likes_before, await self.query("SELECT count(*) FROM remains_likes WHERE remains_id=2"))
        self.assertEqual((await self.client.get("/remains/feed?remains_id=2")).status_code, 404)
        self.assertEqual((await self.client.post("/remains/2/delete")).status_code, 404)
        self.assertEqual((await self.client.post("/remains/4/delete")).status_code, 404)

    async def test_adminer_changes_are_visible(self):
        await self.query("UPDATE remains SET analysis_time_days=18, carbon_14_pmc=100 WHERE id=1")
        await self.query("INSERT INTO remains_likes (researcher_id, remains_id) VALUES (999, 1)")
        response = await self.client.get("/remains/feed?remains_id=1")
        self.assertIn("18 раб. дней", response.text)
        self.assertIn("100 pMC", response.text)
        self.assertIn("13 отметок нравится", response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        await self.query("DELETE FROM remains_likes WHERE researcher_id=999 AND remains_id=1")
        self.assertIn("12 отметок нравится", (await self.client.get("/remains/feed?remains_id=1")).text)

    async def test_unavailable_media_and_local_assets(self):
        await self.query("UPDATE remains SET image_url=%s, video_url=%s WHERE id=1", (settings.MINIO_URL + "/missing-lab2.jpg", settings.MINIO_URL + "/missing-lab2.mp4"))
        response = await self.client.get("/remains/feed?remains_id=1")
        self.assertIn('src="/static/images/default.jpg"', response.text)
        self.assertIn('src="/static/videos/default.mp4"', response.text)
        await self.query("UPDATE remains SET image_url='http://[bad', video_url='http://untrusted.invalid/a.mp4' WHERE id=4")
        response = await self.client.get("/remains/draft")
        self.assertIn('src="/static/images/default.jpg"', response.text)
        self.assertIn('src="/static/videos/default.mp4"', response.text)
        for path in ["images/default.jpg", "videos/default.mp4", "icons/flask.png", "icons/watch.png", "icons/folder.webp", "icons/trash-2.svg"]:
            self.assertEqual((await self.client.get("/static/" + path)).status_code, 200)

    async def test_database_constraints(self):
        queries = [
            ("INSERT INTO remains (title, creator_id) VALUES ('Duplicate draft', 999)", psycopg.errors.UniqueViolation),
            ("INSERT INTO remains_likes (researcher_id, remains_id) VALUES (1, 1)", psycopg.errors.UniqueViolation),
            ("DELETE FROM researchers WHERE id=999", psycopg.errors.ForeignKeyViolation),
            ("DELETE FROM remains WHERE id=1", psycopg.errors.ForeignKeyViolation),
            ("UPDATE remains SET status='invalid' WHERE id=4", psycopg.errors.CheckViolation),
            ("UPDATE remains SET status='published' WHERE id=4", psycopg.errors.CheckViolation),
        ]
        for statement, error in queries:
            with self.assertRaises(error):
                await self.query(statement)


if __name__ == "__main__":
    unittest.main()
