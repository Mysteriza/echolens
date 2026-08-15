import asyncio
import sys
import os

# Add the backend directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.session import init_db

async def main():
    print("Testing database connection...")
    try:
        await init_db()
        print("Successfully connected and initialized the database schema!")
    except Exception as e:
        print(f"Failed to connect to the database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
