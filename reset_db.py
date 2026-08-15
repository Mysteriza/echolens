import asyncio
import sys
import os

# Add backend to path so we can import from database
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from database.session import engine
from sqlalchemy import text

async def main():
    async with engine.begin() as conn:
        # Cascade delete will remove associated comments, analysis, aspects, and logs
        await conn.execute(text('TRUNCATE TABLE videos CASCADE'))
        print('Database reset successful! All videos and comments have been cleared.')

if __name__ == "__main__":
    asyncio.run(main())
