import asyncio
from sqlalchemy import text
from database.session import engine

async def add_is_spam_column():
    async with engine.begin() as conn:
        try:
            # Check if column exists
            result = await conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='comments' AND column_name='is_spam';
            """))
            if not result.scalar():
                print("Adding is_spam column to comments table...")
                await conn.execute(text("ALTER TABLE comments ADD COLUMN is_spam BOOLEAN DEFAULT FALSE;"))
                print("Success!")
            else:
                print("is_spam column already exists.")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(add_is_spam_column())
