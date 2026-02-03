import asyncpg

from ingest_api.settings import get_settings


async def create_pool() -> asyncpg.Pool:
    settings = get_settings()
    return await asyncpg.create_pool(dsn=settings.DB_DSN, min_size=1, max_size=5)
