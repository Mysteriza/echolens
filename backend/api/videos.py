import csv
import io
import re

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import async_session, get_db
from models.db import (
    Comment,
    CommentAnalysis,
    CommentAspect,
    Video,
    VideoLog,
    VideoReport,
)
from services.chat import ChatService
from services.embedding import GeminiEmbeddingService
from services.retrieval import RetrievalService
from services.youtube import YouTubeService, extract_video_id

router = APIRouter(prefix="/api/videos", tags=["videos"])

# Global set to track cancelled tasks
cancellation_tokens = set()


class ProcessVideoRequest(BaseModel):
    url: str
    limit: int = 300


class ChatRequest(BaseModel):
    question: str


async def add_log(db: AsyncSession, video_id: int, message: str, level: str = "INFO"):
    log = VideoLog(video_id=video_id, message=message, level=level)
    db.add(log)
    await db.commit()


async def process_video_background(video_id: int, youtube_id: str, limit: int):
    async with async_session() as db:
        try:
            video = await db.get(Video, video_id)
            if not video:
                return
            video.analysis_status = "collecting"
            await db.commit()

            await add_log(
                db, video_id, f"Started processing video: {video.title}", "INFO"
            )

            # 1. Fetch Comments
            if limit >= 99999:
                log_message = "Fetching all comments from YouTube API..."
            else:
                log_message = f"Fetching comments from YouTube API (Limited to {limit} comments)..."
                
            await add_log(
                db,
                video_id,
                log_message,
                "INFO",
            )
            yt_service = YouTubeService()
            comments_data = yt_service.get_comments(youtube_id, max_results=limit)

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
            import asyncio

            from services.nlp import IndoBERTService

            nlp_service = IndoBERTService()
            
            await add_log(
                db, video_id, "[Step 1] Loading Sentiment Analysis Model (IndoBERT)...", "INFO"
            )
            await asyncio.to_thread(nlp_service.load_indobert)
            

            embedding_service = GeminiEmbeddingService()

            # Insert comments and process them locally
            await add_log(
                db,
                video_id,
                f"[Step 2] Model ready! Starting batched comment classification (Batch Size: {nlp_service.batch_size})...",
                "INFO",
            )

            import datetime

            batch_size = nlp_service.batch_size

            for i in range(0, len(comments_data), batch_size):
                if video_id in cancellation_tokens:
                    try:
                        v = await db.get(Video, video_id)
                        if v:
                            await add_log(
                                db, video_id, "Process cancelled by user. Cleaning up...", "WARNING"
                            )
                            await db.delete(v)
                            await db.commit()
                    except Exception:
                        pass
                        
                    if video_id in cancellation_tokens:
                        cancellation_tokens.remove(video_id)
                    return

                chunk = comments_data[i : i + batch_size]

                # Spam Detection Logic (Regex for URLs, or repeating words)
                spam_pattern = re.compile(
                    r"(http[s]?://|www\.)|(.)\2{10,}|(\b\w+\b)(?:\s+\3){4,}",
                    re.IGNORECASE,
                )

                valid_chunk = []
                for c in chunk:
                    # Mark spam if it matches regex or is extremely short
                    if spam_pattern.search(c["text"]) or len(c["text"]) < 2:
                        c["is_spam"] = True
                    else:
                        c["is_spam"] = False
                        valid_chunk.append(c)

                # Batch predict only for non-spam comments
                valid_texts = [c["text"] for c in valid_chunk]
                sentiments = (
                    await asyncio.to_thread(nlp_service.analyze_sentiments_batch, valid_texts)
                    if valid_texts
                    else []
                )

                # Removed Zero-Shot Aspect Based Sentiment Analysis per user request
                aspects_list = [[] for _ in valid_texts] if valid_texts else []

                # Reconstruct chunk with assigned sentiments & aspects
                processed_chunk = []
                valid_idx = 0
                for c in chunk:
                    if c["is_spam"]:
                        processed_chunk.append(
                            (c, {"sentiment": "neutral", "confidence": 0.0}, [])
                        )
                    else:
                        processed_chunk.append(
                            (c, sentiments[valid_idx], aspects_list[valid_idx])
                        )
                        valid_idx += 1

                for c_data, sentiment_data, c_aspects in processed_chunk:
                    stmt = select(Comment).where(
                        Comment.youtube_id == c_data["youtube_id"]
                    )
                    existing_comment = (await db.execute(stmt)).scalar_one_or_none()

                    if not existing_comment:
                        pub_str = c_data["published_at"]
                        if pub_str.endswith("Z"):
                            pub_str = pub_str.replace("Z", "+00:00")
                        pub_dt = datetime.datetime.fromisoformat(pub_str)

                        db_comment = Comment(
                            youtube_id=c_data["youtube_id"],
                            video_id=video_id,
                            parent_id=c_data["parent_id"],
                            author_name=c_data["author_name"],
                            text=c_data["text"],
                            published_at=pub_dt,
                            like_count=c_data["like_count"],
                            is_reply=c_data["is_reply"],
                            is_spam=c_data["is_spam"],
                        )
                        db.add(db_comment)
                        await db.flush()

                        db_analysis = CommentAnalysis(
                            comment_id=db_comment.id,
                            sentiment=sentiment_data["sentiment"],
                            confidence=sentiment_data["confidence"],
                            language="id",
                            is_product_experience=False,
                            is_complaint=(sentiment_data["sentiment"] == "negative"),
                            is_praise=(sentiment_data["sentiment"] == "positive"),
                            is_question=False,
                            summary="",
                            analysis_version="indobert_v1",
                        )
                        db.add(db_analysis)

                        # Save detected aspects
                        for asp in c_aspects:
                            db_aspect = CommentAspect(
                                comment_id=db_comment.id,
                                aspect=asp,
                                sentiment=sentiment_data["sentiment"],
                            )
                            db.add(db_aspect)

                await db.commit()
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

            # Report generation was here, removed per user request.

            video.analysis_status = "completed"
            await db.commit()
            await add_log(
                db, video_id, "Analysis completed! Ready for AI Chat.", "SUCCESS"
            )

        except Exception as e:
            print(f"Error in background task: {e}")
            await add_log(
                db, video_id, f"Fatal error during processing: {e!s}", "ERROR"
            )
            video = await db.get(Video, video_id)
            if video:
                video.analysis_status = "failed"
                await db.commit()


@router.post("")
async def process_video(
    request: ProcessVideoRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    # Security Hardening: Strict URL Validation
    url = request.url.strip()
    if not url.startswith("https://www.youtube.com/") and not url.startswith(
        "https://youtu.be/"
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid YouTube URL format. Must be a secure HTTPS YouTube link.",
        )

    try:
        youtube_id = extract_video_id(url)
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Could not extract video ID from URL"
        )

    stmt = select(Video).where(Video.youtube_id == youtube_id)
    existing_video = (await db.execute(stmt)).scalar_one_or_none()

    if existing_video:
        if existing_video.id in cancellation_tokens:
            # Race condition fix: User clicked 'Stop' and immediately re-analyzed before the background 
            # task had time to clean up. We aggressively delete it here so a fresh one can start.
            try:
                await db.delete(existing_video)
                await db.commit()
            except Exception:
                pass
            existing_video = None
        else:
            return {
                "message": "Video already processed or processing",
                "video_id": existing_video.id,
                "status": existing_video.analysis_status,
            }

    yt_service = YouTubeService()
    try:
        metadata = yt_service.get_video_metadata(youtube_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Video not found")

    new_video = Video(
        youtube_id=metadata["youtube_id"],
        title=metadata["title"],
        channel=metadata["channel"],
        thumbnail=metadata["thumbnail"],
        comment_count=metadata["comment_count"],
        analysis_status="pending",
    )
    db.add(new_video)
    await db.commit()
    await db.refresh(new_video)

    background_tasks.add_task(
        process_video_background, new_video.id, youtube_id, request.limit
    )

    return {
        "message": "Started processing video",
        "video_id": new_video.id,
        "status": "pending",
    }

@router.post("/reset-database")
async def reset_database(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("TRUNCATE TABLE videos CASCADE"))
        await db.commit()
        return {"status": "success", "message": "Database reset successful."}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/{video_id}/cancel")
async def cancel_video_processing(video_id: int, db: AsyncSession = Depends(get_db)):
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
        
    if video.analysis_status in ["completed", "failed"]:
        raise HTTPException(status_code=400, detail="Cannot cancel a completed or failed process")
        
    cancellation_tokens.add(video_id)
    return {"status": "success", "message": "Cancellation requested"}


@router.get("/{video_id}")
async def get_video(video_id: int, db: AsyncSession = Depends(get_db)):
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    stmt_comments = select(Comment.id).where(Comment.video_id == video_id)
    comments = (await db.execute(stmt_comments)).scalars().all()

    return {
        "id": video.id,
        "title": video.title,
        "channel": video.channel,
        "thumbnail": video.thumbnail,
        "status": video.analysis_status,
        "processed_comments": len(comments),
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
    video_id: int, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
):
    stmt = text("""
        SELECT c.id, c.author_name, c.text, c.like_count, c.is_spam,
               ca.sentiment, ca.summary, ca.is_complaint, ca.is_praise, ca.confidence,
               (SELECT string_agg(aspect, ', ') FROM comment_aspects WHERE comment_id = c.id) as aspect_str
        FROM comments c
        LEFT JOIN comment_analysis ca ON c.id = ca.comment_id
        WHERE c.video_id = :video_id
        ORDER BY c.like_count DESC
        OFFSET :skip LIMIT :limit
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
                "summary": row.summary,
                "is_complaint": row.is_complaint,
                "is_praise": row.is_praise,
                "aspects": [a.strip() for a in row.aspect_str.split(",")]
                if row.aspect_str
                else [],
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

    # Aspect Distribution removed
    aspect_dist = []

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
            timeline.append(
                {
                    "date": row.date.strftime("%Y-%m-%d"),
                    "positive": row.pos_count,
                    "negative": row.neg_count,
                    "neutral": row.neu_count,
                }
            )

    # Top Words (Simple heuristic for word cloud)
    words_stmt = text("""
        SELECT c.text 
        FROM comments c 
        WHERE c.video_id = :video_id AND c.is_spam = false
    """)
    words_res = await db.execute(words_stmt, {"video_id": video_id})

    word_counts = {}
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
        "aspect_distribution": aspect_dist,
        "timeline": timeline,
        "top_words": top_words,
    }


@router.post("/{video_id}/chat")
async def chat_video(
    video_id: int, request: ChatRequest, db: AsyncSession = Depends(get_db)
):
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    retrieval_service = RetrievalService(db)
    chat_service = ChatService()

    from sqlalchemy import func
    
    stmt_count = select(func.count(Comment.id)).where(Comment.video_id == video_id, Comment.is_spam == False)
    total_comments = (await db.execute(stmt_count)).scalar() or 0
    
    # Send 25% of relevant comments to AI, but cap at 100 to prevent rate limits or context bloat
    dynamic_limit = max(20, int(total_comments * 0.25))
    dynamic_limit = min(dynamic_limit, 100)

    retrieved_comments = await retrieval_service.search_similar_comments(
        video_id, request.question, limit=dynamic_limit
    )
    answer = chat_service.ask_question(request.question, retrieved_comments)

    try:
        # Gemini sometimes returns integers, strings, or even the index [1]. Let's safely match them.
        ai_ids = [str(x) for x in answer.get("supporting_comment_ids", [])]
        supporting_evidence = [c for c in retrieved_comments if str(c["id"]) in ai_ids]

        # Fallback: if Gemini fails to map IDs, just show the top 3 retrieved comments
        if not supporting_evidence and retrieved_comments:
            supporting_evidence = retrieved_comments[:3]
    except:
        supporting_evidence = retrieved_comments[:3]

    return {
        "answer": answer.get("answer"),
        "confidence": answer.get("confidence"),
        "relevant_aspects": answer.get("relevant_aspects"),
        "evidence": supporting_evidence,
    }


@router.get("/{video_id}/report")
async def get_video_report(video_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(VideoReport).where(VideoReport.video_id == video_id)
    report = (await db.execute(stmt)).scalar_one_or_none()
    if not report:
        return {"status": "not_ready"}

    return {
        "status": "ready",
        "overall_sentiment": report.overall_sentiment,
        "summary": report.summary,
        "top_complaints": report.top_complaints,
        "top_praises": report.top_praises,
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

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["Author", "Comment", "Likes", "Is Spam", "Sentiment", "Confidence Score"]
    )

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

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=echolens_export_{video_id}.csv"
        },
    )
