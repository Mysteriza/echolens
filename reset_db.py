"""Local dev helper: TRUNCATE videos CASCADE. Prefer the API endpoint in prod."""
import argparse
import asyncio
import os
import sys

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
    parser = argparse.ArgumentParser(description="Reset Echolens database (TRUNCATE videos CASCADE).")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
    args = parser.parse_args()
    if not args.yes and os.environ.get("APP_ENV", "development") == "production":
        print("Refusing to reset without --yes in production.")
        sys.exit(1)
    if not args.yes:
        answer = input("Delete ALL videos/comments? Type 'yes' to confirm: ").strip().lower()
        if answer != "yes":
            print("Aborted.")
            sys.exit(0)
    asyncio.run(main())
