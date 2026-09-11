import asyncio
import csv
import io
import logging
import re
from collections import Counter

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.cancellation import cancellations
from core.config import settings
from core.rate_limit import limiter
from core.validation import extract_video_id
from database.session import get_db, get_session_factory
from models.db import (
    Comment,
    Video,
    VideoLog,
)
from services.chat import ChatService
from services.pipeline import FETCH_ALL_SENTINEL, bulk_insert_classified, flag_spam
from services.retrieval import RetrievalService
from services.youtube import YouTubeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/videos", tags=["videos"])


class ProcessVideoRequest(BaseModel):
    url: str
    limit: int = Field(default=300, ge=1, le=2000)
    # Optional user-adjustable chat context (overrides server fraction default).
    chat_context_limit: int | None = Field(default=None, ge=5, le=100)
    chat_context_fraction: float | None = Field(default=None, ge=0.05, le=1.0)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    # Optional per-question override, clamped server-side to MAX_CHAT_CONTEXT.
    context_limit: int | None = Field(default=None, ge=5, le=100)


async def add_log(db: AsyncSession, video_id: int, message: str, level: str = "INFO"):
    log = VideoLog(video_id=video_id, message=message, level=level)
    db.add(log)
    await db.commit()


def require_admin(x_admin_token: str | None = None) -> None:
    """Protect destructive endpoints when ADMIN_TOKEN is configured."""
    if settings.ADMIN_TOKEN and x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Admin token required.")


def _resolve_process_limit(limit: int) -> int:
    """Clamp user limit to server cap; sentinel means 'fetch all'."""
    if limit >= FETCH_ALL_SENTINEL:
        return settings.MAX_PROCESS_LIMIT
    return max(1, min(limit, settings.MAX_PROCESS_LIMIT))


def _resolve_chat_limit(
    total_comments: int,
    override: int | None = None,
    fraction: float | None = None,
) -> int:
    """User-customizable chat context: explicit limit wins, else fraction."""
    if override is not None:
        return max(5, min(override, settings.MAX_CHAT_CONTEXT))
    frac = fraction if fraction is not None else settings.CHAT_CONTEXT_FRACTION
    frac = max(0.05, min(frac, 1.0))
    dynamic = max(settings.CHAT_CONTEXT_MIN, int(total_comments * frac))
    return min(dynamic, settings.MAX_CHAT_CONTEXT)


async def process_video_background(
    video_id: int,
    youtube_id: str,
    limit: int,
    chat_context_limit: int | None = None,
    chat_context_fraction: float | None = None,
):
    async with get_session_factory()() as db:
        try:
            video = await db.get(Video, video_id)
            if not video:
                await cancellations.clear(video_id)
                return
            # Persist user chat-context preference on the video row when given.
            if chat_context_limit is not None:
                video.chat_context_limit = max(
                    5, min(chat_context_limit, settings.MAX_CHAT_CONTEXT)
                )
            if chat_context_fraction is not None:
                video.chat_context_fraction = max(0.05, min(chat_context_fraction, 1.0))
            video.analysis_status = "collecting"
            await db.commit()

            await add_log(
                db, video_id, f"Started processing video: {video.title}", "INFO"
            )

            # 1. Fetch Comments (blocking SDK -> thread, with server-side cap)
            effective_limit = _resolve_process_limit(limit)
            if limit >= FETCH_ALL_SENTINEL:
                log_message = (
                    f"Fetching all comments from YouTube API "
                    f"(capped at {effective_limit} by server)..."
                )
            else:
                log_message = (
                    f"Fetching comments from YouTube API "
                    f"(Limited to {effective_limit} comments)..."
                )

            await add_log(
                db,
                video_id,
                log_message,
                "INFO",
            )
            yt_service = YouTubeService()
            comments_data = await asyncio.to_thread(
                yt_service.get_comments, youtube_id, effective_limit
            )

            if not comments_data:
                await add_log(
                    db,
                    video_id,
                    "No comments found or error fetching comments.",
                    "ERROR",
                )
                video.analysis_status = "failed"
                await db.commit()
                return

            await add_log(
                db,
                video_id,
                f"Successfully fetched {len(comments_data)} comments.",
                "SUCCESS",
            )

            video.analysis_status = "analyzing"
            await db.commit()

            # Use local IndoBERT for per-comment sentiment classification
            from services.nlp import IndoBERTService

            nlp_service = IndoBERTService()

            await add_log(
                db, video_id, "[Step 1] Loading Sentiment Analysis Model (IndoBERT)...", "INFO"
            )
            await asyncio.to_thread(nlp_service.load_indobert)

            # Insert comments and process them locally
            await add_log(
                db,
                video_id,
                f"[Step 2] Model ready! Starting batched comment classification (Batch Size: {nlp_service.batch_size})...",
                "INFO",
            )

            batch_size = nlp_service.batch_size

            for i in range(0, len(comments_data), batch_size):
                if await cancellations.is_cancelled(video_id):
                    try:
                        v = await db.get(Video, video_id)
                        if v:
                            await add_log(
                                db, video_id, "Process cancelled by user. Cleaning up...", "WARNING"
                            )
                            await db.delete(v)
                            await db.commit()
                    except Exception as cleanup_exc:  # noqa: BLE001
                        logger.warning("Cancel cleanup failed: %s", cleanup_exc)
                        await db.rollback()

                    await cancellations.clear(video_id)
                    return

                chunk = comments_data[i : i + batch_size]

                valid_chunk, spam_chunk = flag_spam(chunk)

                # Batch predict only for non-spam comments
                valid_texts = [c["text"] for c in valid_chunk]
                sentiments = (
                    await asyncio.to_thread(nlp_service.analyze_sentiments_batch, valid_texts)
                    if valid_texts
                    else []
                )

                classified: list[tuple[dict, dict]] = [
                    (c, {"sentiment": "neutral", "confidence": 0.0}) for c in spam_chunk
                ]
                classified.extend(zip(valid_chunk, sentiments))

                await bulk_insert_classified(db, video_id, classified)
                processed_count = min(i + batch_size, len(comments_data))
                await add_log(
                    db,
                    video_id,
                    f"Classified {processed_count}/{len(comments_data)} comments with IndoBERT...",
                    "INFO",
                )

            await add_log(
                db,
                video_id,
                f"Successfully classified all {len(comments_data)} comments.",
                "SUCCESS",
            )

            video.analysis_status = "completed"
            await db.commit()
            await add_log(
                db, video_id, "Analysis completed! Ready for AI Chat.", "SUCCESS"
            )
            await cancellations.clear(video_id)

        except Exception as exc:  # noqa: BLE001
            logger.exception("Error in background task for video %d", video_id)
            try:
                await add_log(
                    db, video_id, f"Fatal error during processing: {exc!s}", "ERROR"
                )
                video = await db.get(Video, video_id)
                if video:
                    video.analysis_status = "failed"
                    await db.commit()
            except Exception:  # noqa: BLE001
                await db.rollback()
            finally:
                await cancellations.clear(video_id)


@router.post("")
@limiter.limit("10/minute")
async def process_video(
    request: Request,
    payload: ProcessVideoRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    # Strict allowlist validation (HTTPS + YouTube hosts + 11-char ID).
    try:
        youtube_id = extract_video_id(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Clamp user limit server-side (Pydantic already bounds, cap again here).
    request_limit = max(1, min(payload.limit, settings.MAX_PROCESS_LIMIT))

    stmt = select(Video).where(Video.youtube_id == youtube_id)
    existing_video = (await db.execute(stmt)).scalar_one_or_none()

    if existing_video:
        if await cancellations.is_cancelled(existing_video.id):
            # Race condition fix: User clicked 'Stop' and immediately re-analyzed
            # before the background task cleaned up. Delete so a fresh one starts.
            try:
                await db.delete(existing_video)
                await db.commit()
            except Exception as del_exc:  # noqa: BLE001
                logger.warning("Stale video cleanup failed: %s", del_exc)
                await db.rollback()
            existing_video = None
        else:
            return {
                "message": "Video already processed or processing",
                "video_id": existing_video.id,
                "status": existing_video.analysis_status,
            }

    try:
        yt_service = YouTubeService()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    try:
        metadata = await asyncio.to_thread(yt_service.get_video_metadata, youtube_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    new_video = Video(
        youtube_id=metadata["youtube_id"],
        title=metadata["title"],
        channel=metadata["channel"],
        thumbnail=metadata["thumbnail"],
        comment_count=metadata["comment_count"],
        analysis_status="pending",
        chat_context_limit=(
            max(5, min(payload.chat_context_limit, settings.MAX_CHAT_CONTEXT))
            if payload.chat_context_limit is not None
            else None
        ),
        chat_context_fraction=(
            max(0.05, min(payload.chat_context_fraction, 1.0))
            if payload.chat_context_fraction is not None
            else None
        ),
    )
    db.add(new_video)
    await db.commit()
    await db.refresh(new_video)

    background_tasks.add_task(
        process_video_background,
        new_video.id,
        youtube_id,
        request_limit,
        payload.chat_context_limit,
        payload.chat_context_fraction,
    )

    return {
        "message": "Started processing video",
        "video_id": new_video.id,
        "status": "pending",
    }


@router.post("/reset-database")
@limiter.limit("5/minute")
async def reset_database(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_admin_token: str | None = Header(default=None),
):
    require_admin(x_admin_token)
    try:
        from database.session import DB_BACKEND

        if DB_BACKEND == "sqlite":
            # SQLite has no TRUNCATE — DELETE is enough (CASCADE via FK).
            # sqlite_sequence may not exist (no AUTOINCREMENT) — ignore that.
            await db.execute(text("DELETE FROM videos"))
            try:
                await db.execute(text("DELETE FROM sqlite_sequence WHERE name='videos'"))
            except Exception:  # noqa: BLE001
                pass
        else:
            await db.execute(text("TRUNCATE TABLE videos CASCADE"))
        await db.commit()
        return {"status": "success", "message": "Database reset successful."}
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.exception("Database reset failed")
        raise HTTPException(status_code=500, detail="Database reset failed.") from exc



@router.post("/{video_id}/cancel")
async def cancel_video_processing(video_id: int, db: AsyncSession = Depends(get_db)):
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.analysis_status in ["completed", "failed"]:
        raise HTTPException(status_code=400, detail="Cannot cancel a completed or failed process")

    await cancellations.request(video_id)
    return {"status": "success", "message": "Cancellation requested"}


@router.get("/{video_id}")
async def get_video(video_id: int, db: AsyncSession = Depends(get_db)):
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # COUNT(*) instead of loading all IDs into Python.
    count_stmt = select(func.count(Comment.id)).where(Comment.video_id == video_id)
    processed = (await db.execute(count_stmt)).scalar() or 0

    return {
        "id": video.id,
        "title": video.title,
        "channel": video.channel,
        "thumbnail": video.thumbnail,
        "status": video.analysis_status,
        "processed_comments": processed,
        "chat_context_limit": video.chat_context_limit,
        "chat_context_fraction": video.chat_context_fraction,
    }


@router.get("/{video_id}/logs")
async def get_video_logs(video_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(VideoLog)
        .where(VideoLog.video_id == video_id)
        .order_by(VideoLog.created_at.asc())
    )
    logs = (await db.execute(stmt)).scalars().all()
    return [
        {"message": l.message, "level": l.level, "created_at": l.created_at.isoformat()}
        for l in logs
    ]


@router.get("/{video_id}/comments")
async def get_video_comments(
    video_id: int,
    skip: int = 0,
    limit: int = 15,
    db: AsyncSession = Depends(get_db),
):
    skip = max(0, skip)
    limit = max(1, min(limit, settings.MAX_COMMENT_PAGE_SIZE))
    stmt = text("""
        SELECT c.id, c.author_name, c.text, c.like_count, c.is_spam,
               ca.sentiment, ca.is_complaint, ca.is_praise, ca.confidence
        FROM comments c
        LEFT JOIN comment_analysis ca ON c.id = ca.comment_id
        WHERE c.video_id = :video_id
        ORDER BY c.like_count DESC
        LIMIT :limit OFFSET :skip
    """)
    result = await db.execute(
        stmt, {"video_id": video_id, "skip": skip, "limit": limit}
    )
    comments = []
    for row in result:
        comments.append(
            {
                "id": row.id,
                "author": row.author_name,
                "text": row.text,
                "likes": row.like_count,
                "is_spam": row.is_spam,
                "sentiment": row.sentiment,
                "confidence": row.confidence,
                "is_complaint": row.is_complaint,
                "is_praise": row.is_praise,
            }
        )
    return comments


@router.get("/{video_id}/stats")
async def get_video_stats(video_id: int, db: AsyncSession = Depends(get_db)):
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Sentiment Distribution
    sent_stmt = text("""
        SELECT ca.sentiment, count(*) as count 
        FROM comment_analysis ca 
        JOIN comments c ON ca.comment_id = c.id 
        WHERE c.video_id = :video_id AND c.is_spam = false
        GROUP BY ca.sentiment
    """)
    sent_res = await db.execute(sent_stmt, {"video_id": video_id})
    sentiment_dist = [
        {"name": row.sentiment or "neutral", "value": row.count} for row in sent_res
    ]


    # Timeline (by day)
    time_stmt = text("""
        SELECT DATE(c.published_at) as date, 
               SUM(CASE WHEN ca.sentiment = 'positive' THEN 1 ELSE 0 END) as pos_count,
               SUM(CASE WHEN ca.sentiment = 'negative' THEN 1 ELSE 0 END) as neg_count,
               SUM(CASE WHEN ca.sentiment = 'neutral' THEN 1 ELSE 0 END) as neu_count
        FROM comments c
        LEFT JOIN comment_analysis ca ON c.id = ca.comment_id
        WHERE c.video_id = :video_id AND c.is_spam = false
        GROUP BY DATE(c.published_at)
        ORDER BY date ASC
    """)
    time_res = await db.execute(time_stmt, {"video_id": video_id})
    timeline = []
    for row in time_res:
        if row.date:
            # Postgres returns date objects, SQLite returns strings.
            date_val = row.date
            if hasattr(date_val, "strftime"):
                date_str = date_val.strftime("%Y-%m-%d")
            else:
                date_str = str(date_val)[:10]
            timeline.append(
                {
                    "date": date_str,
                    "positive": row.pos_count,
                    "negative": row.neg_count,
                    "neutral": row.neu_count,
                }
            )

    # Top Words: bounded sample (newest 5000) so huge videos don't OOM Python.
    words_stmt = text("""
        SELECT c.text
        FROM comments c
        WHERE c.video_id = :video_id AND c.is_spam = false
        ORDER BY c.id DESC
        LIMIT 5000
    """)
    words_res = await db.execute(words_stmt, {"video_id": video_id})

    word_counts: Counter[str] = Counter()
    stop_words = {
        "dan",
        "di",
        "ke",
        "dari",
        "yang",
        "untuk",
        "pada",
        "dengan",
        "ini",
        "itu",
        "ada",
        "juga",
        "bisa",
        "kalau",
        "tapi",
        "karena",
        "saya",
        "aku",
        "kamu",
        "dia",
        "mereka",
        "kita",
        "kami",
        "sih",
        "nya",
        "aja",
        "udah",
        "belum",
        "tidak",
        "ya",
        "yg",
        "kalo",
        "buat",
        "sama",
        "kok",
        "kan",
        "gak",
        "ga",
    }

    for row in words_res:
        clean_text = re.sub(r"[^\w\s]", "", str(row.text).lower())
        for word in clean_text.split():
            if len(word) > 3 and word not in stop_words:
                word_counts[word] = word_counts.get(word, 0) + 1

    sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:30]
    top_words = [{"text": w[0], "value": w[1]} for w in sorted_words]

    total_comments = sum(item["value"] for item in sentiment_dist)

    return {
        "total_comments": total_comments,
        "sentiment_distribution": sentiment_dist,
        "timeline": timeline,
        "top_words": top_words,
    }


@router.post("/{video_id}/chat")
@limiter.limit("30/minute")
async def chat_video(
    request: Request,
    video_id: int,
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question must not be empty.")
    if len(question) > settings.MAX_QUESTION_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Question too long (max {settings.MAX_QUESTION_LENGTH} chars).",
        )

    try:
        retrieval_service = RetrievalService(db)
        chat_service = ChatService()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    stmt_count = select(func.count(Comment.id)).where(
        Comment.video_id == video_id, Comment.is_spam.is_(False)
    )
    total_comments = (await db.execute(stmt_count)).scalar() or 0

    # Priority: per-question override > saved video preference > server default.
    override = payload.context_limit
    fraction = None
    if override is None:
        override = video.chat_context_limit
        fraction = video.chat_context_fraction
    dynamic_limit = _resolve_chat_limit(total_comments, override, fraction)

    retrieved_comments = await retrieval_service.search_similar_comments(
        video_id, question, limit=dynamic_limit
    )
    answer = await asyncio.to_thread(chat_service.ask_question, question, retrieved_comments)

    # Gemini sometimes returns integers, strings, or indices. Match safely.
    try:
        ai_ids = {str(x) for x in answer.get("supporting_comment_ids", [])}
        supporting_evidence = [c for c in retrieved_comments if str(c["id"]) in ai_ids]

        # Fallback: if Gemini fails to map IDs, show the top 3 retrieved comments
        if not supporting_evidence and retrieved_comments:
            supporting_evidence = retrieved_comments[:3]
    except Exception:  # noqa: BLE001
        supporting_evidence = retrieved_comments[:3]

    return {
        "answer": answer.get("answer"),
        "confidence": answer.get("confidence"),
        "relevant_aspects": answer.get("relevant_aspects"),
        "evidence": supporting_evidence,
        "context_used": len(retrieved_comments),
        "context_limit": dynamic_limit,
    }


@router.get("/{video_id}/export")
async def export_video_comments(video_id: int, db: AsyncSession = Depends(get_db)):
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    stmt = text("""
        SELECT c.author_name, c.text, c.like_count, c.is_spam,
               ca.sentiment, ca.confidence
        FROM comments c
        LEFT JOIN comment_analysis ca ON c.id = ca.comment_id
        WHERE c.video_id = :video_id
        ORDER BY c.like_count DESC
    """)
    result = await db.execute(stmt, {"video_id": video_id})

    def generate():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            ["Author", "Comment", "Likes", "Is Spam", "Sentiment", "Confidence Score"]
        )
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)
        for row in result:
            conf_str = (
                f"{row.confidence * 100:.2f}%" if row.confidence is not None else "N/A"
            )
            writer.writerow(
                [
                    row.author_name,
                    row.text,
                    row.like_count,
                    "Yes" if row.is_spam else "No",
                    row.sentiment,
                    conf_str,
                ]
            )
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=echolens_export_{video_id}.csv"
        },
    )


class VideoSettingsRequest(BaseModel):
    chat_context_limit: int | None = Field(default=None, ge=5, le=100)
    chat_context_fraction: float | None = Field(default=None, ge=0.05, le=1.0)


@router.patch("/{video_id}/settings")
async def update_video_settings(
    video_id: int, payload: VideoSettingsRequest, db: AsyncSession = Depends(get_db)
):
    """User-adjustable per-video limits (chat context). Clamped server-side."""
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if payload.chat_context_limit is not None:
        video.chat_context_limit = max(
            5, min(payload.chat_context_limit, settings.MAX_CHAT_CONTEXT)
        )
    if payload.chat_context_fraction is not None:
        video.chat_context_fraction = max(
            0.05, min(payload.chat_context_fraction, 1.0)
        )
    await db.commit()
    return {
        "video_id": video.id,
        "chat_context_limit": video.chat_context_limit,
        "chat_context_fraction": video.chat_context_fraction,
        "server_caps": {
            "max_chat_context": settings.MAX_CHAT_CONTEXT,
            "max_comment_page_size": settings.MAX_COMMENT_PAGE_SIZE,
            "max_process_limit": settings.MAX_PROCESS_LIMIT,
        },
    }
