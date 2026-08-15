from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from models.db import Comment, CommentEmbedding
from services.embedding import GeminiEmbeddingService

class RetrievalService:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.embedding_service = GeminiEmbeddingService()

    async def search_similar_comments(self, video_id: int, query: str, limit: int = 50) -> list[dict]:
        # Since we disabled pgvector embeddings to save Gemini RPM quota, 
        # we will simply retrieve the top most relevant/liked comments for the LLM to read.
        # With a 1M token context window, Gemini 1.5 Flash can easily read 50-100 comments directly.
        stmt = text("""
            SELECT c.id, c.text, c.author_name, c.like_count, ca.sentiment, ca.is_complaint, ca.is_praise
            FROM comments c
            LEFT JOIN comment_analysis ca ON c.id = ca.comment_id
            WHERE c.video_id = :video_id
            ORDER BY c.like_count DESC, c.id ASC
            LIMIT :limit
        """)

        result = await self.db.execute(stmt, {
            "video_id": video_id,
            "limit": limit
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
                "similarity": 1.0 # Mock similarity
            })

        return comments
