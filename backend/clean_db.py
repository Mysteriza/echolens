import asyncio
from database.session import engine
from sqlalchemy import text

async def main():
    async with engine.begin() as conn:
        await conn.execute(text('DELETE FROM video_logs'))
        await conn.execute(text('DELETE FROM video_reports'))
        await conn.execute(text('DELETE FROM comment_analysis'))
        await conn.execute(text('DELETE FROM comments'))
        await conn.execute(text('DELETE FROM videos'))
        print('Database cleared!')

if __name__ == "__main__":
    asyncio.run(main())
