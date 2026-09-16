from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import settings
from models.db import Base

# Set True once init_db succeeds. Endpoints return 503 while False so the
# API can still boot (and report status) when the database is unreachable.
DB_READY = False
# Which backend is active: "postgres" or local "sqlite" fallback.
DB_BACKEND = "postgres"
DB_ERROR = ""

_LOCAL_SQLITE_URL = "sqlite+aiosqlite:///./echolens_local.db"


def _make_engine(url: str):
    if url.startswith("sqlite"):
        return create_async_engine(url, echo=False)
    return create_async_engine(
        url,
        echo=False,
        connect_args={"prepared_statement_cache_size": 0, "statement_cache_size": 0},
    )


engine = _make_engine(settings.DATABASE_URL)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    if not DB_READY:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable. Check DATABASE_URL and database status.",
        )
    async with async_session() as session:
        yield session


def get_session_factory():
    """Return the current session factory (follows SQLite fallback swap)."""
    return async_session


async def _create_schema(conn) -> None:
    await conn.run_sync(Base.metadata.create_all)
    # Enforce RLS on Postgres so Supabase Security Advisor stays clean.
    # Explicit DENY policy for anon/authenticated documents the intent and
    # silences "RLS Enabled No Policy"; the backend connects with a
    # privileged role that bypasses RLS, so the app is unaffected.
    if DB_BACKEND != "sqlite":
        for table in Base.metadata.tables:
            try:
                await conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
                await conn.execute(text(f"DROP POLICY IF EXISTS deny_public ON {table}"))
                await conn.execute(
                    text(
                        f"CREATE POLICY deny_public ON {table} "
                        f"FOR ALL TO anon, authenticated USING (false) WITH CHECK (false)"
                    )
                )
            except Exception:  # noqa: BLE001
                pass
    # Lightweight forward-migration for existing DBs (create_all won't
    # ALTER tables or backfill indexes). Covering FK indexes silence the
    # "Unindexed foreign keys" advisor item; dropping the write-only
    # parent_id index silences "Unused Index".
    try:
        if DB_BACKEND == "sqlite":
            await conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_comments_video_id ON comments (video_id)")
            )
            await conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_video_logs_video_id ON video_logs (video_id)")
            )
            await conn.execute(text("DROP INDEX IF EXISTS ix_comments_parent_id"))
            await conn.execute(text("DROP INDEX IF EXISTS ix_video_logs_id"))
        else:
            await conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_comments_video_id ON comments (video_id)")
            )
            await conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_video_logs_video_id ON video_logs (video_id)")
            )
            await conn.execute(text("DROP INDEX IF EXISTS ix_comments_parent_id"))
            await conn.execute(text("DROP INDEX IF EXISTS ix_video_logs_id"))
    except Exception:  # noqa: BLE001
        pass
    # Lightweight forward-migration for existing DBs (create_all won't
    # ALTER tables). New nullable columns for per-video chat preferences.
    # SQLite lacks IF NOT EXISTS for ADD COLUMN on old versions — probe first.
    try:
        if DB_BACKEND == "sqlite":
            cols = [r[1] for r in (await conn.execute(text("PRAGMA table_info(videos)"))).all()]
            if "chat_context_limit" not in cols:
                await conn.execute(text("ALTER TABLE videos ADD COLUMN chat_context_limit INTEGER"))
            if "chat_context_fraction" not in cols:
                await conn.execute(text("ALTER TABLE videos ADD COLUMN chat_context_fraction FLOAT"))
        else:
            await conn.execute(
                text("ALTER TABLE videos ADD COLUMN IF NOT EXISTS chat_context_limit INTEGER")
            )
            await conn.execute(
                text(
                    "ALTER TABLE videos ADD COLUMN IF NOT EXISTS chat_context_fraction FLOAT"
                )
            )
    except Exception:  # noqa: BLE001
        pass


async def init_db():
    """Connect to Postgres; fall back to local SQLite so the app always runs."""
    global DB_READY, DB_BACKEND, DB_ERROR, engine, async_session
    try:
        async with engine.begin() as conn:
            await _create_schema(conn)
        DB_BACKEND = "postgres"
        DB_READY = True
        return
    except Exception as exc:  # noqa: BLE001
        DB_ERROR = str(exc)[:300]

    # Fallback: local SQLite file so development/testing always works.
    import logging

    logging.getLogger(__name__).warning(
        "Postgres unreachable (%s). Falling back to local SQLite.", DB_ERROR
    )
    engine = _make_engine(_LOCAL_SQLITE_URL)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await _create_schema(conn)
    DB_BACKEND = "sqlite"
    DB_READY = True
