"""Spam detection + bulk classification helpers for the analysis pipeline."""
import datetime
import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.db import Comment, CommentAnalysis

logger = logging.getLogger(__name__)

# Compiled once at import: URLs, long char repeats, repeated-word spam.
SPAM_PATTERN = re.compile(
    r"(http[s]?://|www\.)|(.)\2{10,}|(\b\w+\b)(?:\s+\3){4,}",
    re.IGNORECASE,
)

# "Fetch everything" sentinel shared by backend + frontend settings UI.
FETCH_ALL_SENTINEL = 99999


def flag_spam(comments: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split chunk into (valid, spam). Mutates is_spam flags in place."""
    valid, spam = [], []
    for c in comments:
        text = c.get("text") or ""
        is_spam = bool(SPAM_PATTERN.search(text)) or len(text) < 2
        c["is_spam"] = is_spam
        (spam if is_spam else valid).append(c)
    return valid, spam


def parse_published_at(raw: str) -> datetime.datetime | None:
    try:
        pub_str = (raw or "").strip()
        if pub_str.endswith("Z"):
            pub_str = pub_str.replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(pub_str)
    except Exception:  # noqa: BLE001
        return None


async def bulk_insert_classified(
    db: AsyncSession,
    video_id: int,
    classified: list[tuple[dict, dict]],
) -> int:
    """Insert new comments + analyses in bulk. Returns inserted count."""
    if not classified:
        return 0
    # De-duplicate within the chunk itself, then against the DB.
    unique: dict[str, tuple[dict, dict]] = {}
    for c_data, sentiment in classified:
        unique.setdefault(c_data["youtube_id"], (c_data, sentiment))
    items = list(unique.values())
    youtube_ids = [c["youtube_id"] for c, _ in items]
    existing = set(
        (
            await db.execute(
                select(Comment.youtube_id).where(Comment.youtube_id.in_(youtube_ids))
            )
        )
        .scalars()
        .all()
    )
    fresh = [(c, s) for c, s in items if c["youtube_id"] not in existing]
    if not fresh:
        return 0
    comment_rows = [
        Comment(
            youtube_id=c_data["youtube_id"],
            video_id=video_id,
            parent_id=c_data.get("parent_id"),
            author_name=c_data.get("author_name"),
            text=c_data.get("text", ""),
            published_at=parse_published_at(c_data.get("published_at", "")),
            like_count=c_data.get("like_count", 0),
            is_reply=bool(c_data.get("is_reply", False)),
            is_spam=bool(c_data.get("is_spam", False)),
        )
        for c_data, _ in fresh
    ]
    db.add_all(comment_rows)
    await db.flush()  # populate PKs for the analysis rows below
    db.add_all(
        [
            CommentAnalysis(
                comment_id=comment.id,
                sentiment=sentiment.get("sentiment", "neutral"),
                confidence=float(sentiment.get("confidence", 0.0) or 0.0),
                language="id",
                is_product_experience=False,
                is_complaint=(sentiment.get("sentiment") == "negative"),
                is_praise=(sentiment.get("sentiment") == "positive"),
                is_question=False,
                summary="",
                analysis_version="indobert_v1",
            )
            for comment, (_, sentiment) in zip(comment_rows, fresh)
        ]
    )
    await db.commit()
    return len(comment_rows)
