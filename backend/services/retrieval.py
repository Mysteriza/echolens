import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class RetrievalService:
    """Top-liked retrieval for chat context.

    Vector search was intentionally removed to save Gemini quota,
    so this returns the most-liked non-spam comments. The embedding service
    is no longer instantiated here (dead dependency removed).
    """

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def search_similar_comments(self, video_id: int, query: str, limit: int = 50) -> list[dict]:
        # Vector search removed to save Gemini quota; retrieve the top
        # most-liked non-spam comments for the LLM to read.
        stmt = text("""
            SELECT c.id, c.text, c.author_name, c.like_count, ca.sentiment, ca.is_complaint, ca.is_praise
            FROM comments c
            LEFT JOIN comment_analysis ca ON c.id = ca.comment_id
            WHERE c.video_id = :video_id AND c.is_spam = false
            ORDER BY c.like_count DESC, c.id ASC
            LIMIT :limit
        """)

        result = await self.db.execute(stmt, {
            "video_id": video_id,
            "limit": max(1, min(limit, 200)),
        })

        comments = []
        for row in result:
            comments.append({
                "id": row.id,
                "text": row.text,
                "author": row.author_name,
                "likes": row.like_count,
                "sentiment": row.sentiment,
                "is_complaint": row.is_complaint,
                "is_praise": row.is_praise,
                "similarity": 1.0  # Mock similarity (vector search disabled)
            })

        logger.debug(
            "Retrieved %d comments for video %d (query=%.40s)",
            len(comments),
            video_id,
            query,
        )
        return comments
