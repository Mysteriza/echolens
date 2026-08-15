from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, desc
from typing import List, Dict

from database.session import get_db, async_session
from models.db import Video, Comment, CommentAnalysis, CommentAspect, CommentEmbedding, VideoLog, VideoReport
from services.youtube import YouTubeService, extract_video_id
from services.analysis import VideoReportService
from services.embedding import GeminiEmbeddingService
from services.retrieval import RetrievalService
from services.chat import ChatService
from pydantic import BaseModel
import asyncio

router = APIRouter(prefix="/api/videos", tags=["videos"])

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
            await add_log(db, video_id, f"Started processing video: {youtube_id}", "INFO")
            
            video = await db.get(Video, video_id)
            if not video:
                return
            video.analysis_status = "collecting"
            await db.commit()

            # 1. Fetch Comments
            limit_str = "All" if limit >= 99999 else str(limit)
            await add_log(db, video_id, f"Fetching comments from YouTube API (Limited to {limit_str})...", "INFO")
            yt_service = YouTubeService()
            comments_data = yt_service.get_comments(youtube_id, max_results=limit) 
            
            if not comments_data:
                await add_log(db, video_id, "No comments found or error fetching comments.", "ERROR")
                video.analysis_status = "failed"
                await db.commit()
                return
                
            await add_log(db, video_id, f"Successfully fetched {len(comments_data)} comments.", "SUCCESS")
            
            video.analysis_status = "analyzing"
            await db.commit()

            # Use local IndoBERT for per-comment sentiment classification
            from services.nlp import IndoBERTService
            nlp_service = IndoBERTService()
            embedding_service = GeminiEmbeddingService()

            # Insert comments and process them locally
            await add_log(db, video_id, f"Running local IndoBERT model for sentiment classification in batches (Batch Size: {nlp_service.batch_size})...", "INFO")
            
            import datetime
            batch_size = nlp_service.batch_size
            
            for i in range(0, len(comments_data), batch_size):
                chunk = comments_data[i:i + batch_size]
                chunk_texts = [c['text'] for c in chunk]
                
                # Batch predict
                sentiments = nlp_service.analyze_sentiments_batch(chunk_texts)
                
                for c_data, sentiment_data in zip(chunk, sentiments):
                    stmt = select(Comment).where(Comment.youtube_id == c_data['youtube_id'])
                    existing_comment = (await db.execute(stmt)).scalar_one_or_none()
                    
                    if not existing_comment:
                        pub_str = c_data['published_at']
                        if pub_str.endswith('Z'):
                            pub_str = pub_str.replace('Z', '+00:00')
                        pub_dt = datetime.datetime.fromisoformat(pub_str)
                        
                        db_comment = Comment(
                            youtube_id=c_data['youtube_id'],
                            video_id=video_id,
                            parent_id=c_data['parent_id'],
                            author_name=c_data['author_name'],
                            text=c_data['text'],
                            published_at=pub_dt,
                            like_count=c_data['like_count'],
                            is_reply=c_data['is_reply']
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
                            analysis_version="indobert_v1"
                        )
                        db.add(db_analysis)
                        
                await db.commit()
                processed_count = min(i + batch_size, len(comments_data))
                await add_log(db, video_id, f"Classified {processed_count}/{len(comments_data)} comments with IndoBERT...", "INFO")
                
            await add_log(db, video_id, f"Successfully classified all {len(comments_data)} comments.", "SUCCESS")
            
            # Report generation was here, removed per user request.

            video.analysis_status = "completed"
            await db.commit()
            await add_log(db, video_id, "Analysis completed! Ready for AI Chat.", "SUCCESS")

        except Exception as e:
            print(f"Error in background task: {e}")
            await add_log(db, video_id, f"Fatal error during processing: {str(e)}", "ERROR")
            video = await db.get(Video, video_id)
            if video:
                video.analysis_status = "failed"
                await db.commit()

@router.post("")
async def process_video(request: ProcessVideoRequest, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    # Security Hardening: Strict URL Validation
    url = request.url.strip()
    if not url.startswith("https://www.youtube.com/") and not url.startswith("https://youtu.be/"):
        raise HTTPException(status_code=400, detail="Invalid YouTube URL format. Must be a secure HTTPS YouTube link.")
        
    try:
        youtube_id = extract_video_id(url)
    except ValueError:
        raise HTTPException(status_code=400, detail="Could not extract video ID from URL")

    stmt = select(Video).where(Video.youtube_id == youtube_id)
    existing_video = (await db.execute(stmt)).scalar_one_or_none()
    
    if existing_video:
        return {"message": "Video already processed or processing", "video_id": existing_video.id, "status": existing_video.analysis_status}

    yt_service = YouTubeService()
    try:
        metadata = yt_service.get_video_metadata(youtube_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Video not found")

    new_video = Video(
        youtube_id=metadata['youtube_id'],
        title=metadata['title'],
        channel=metadata['channel'],
        thumbnail=metadata['thumbnail'],
        comment_count=metadata['comment_count'],
        analysis_status="pending"
    )
    db.add(new_video)
    await db.commit()
    await db.refresh(new_video)

    background_tasks.add_task(process_video_background, new_video.id, youtube_id, request.limit)

    return {"message": "Started processing video", "video_id": new_video.id, "status": "pending"}

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
        "processed_comments": len(comments)
    }

@router.get("/{video_id}/logs")
async def get_video_logs(video_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(VideoLog).where(VideoLog.video_id == video_id).order_by(VideoLog.created_at.asc())
    logs = (await db.execute(stmt)).scalars().all()
    return [{"message": l.message, "level": l.level, "created_at": l.created_at.isoformat()} for l in logs]

@router.get("/{video_id}/comments")
async def get_video_comments(video_id: int, db: AsyncSession = Depends(get_db)):
    stmt = text("""
        SELECT c.id, c.author_name, c.text, c.like_count, 
               ca.sentiment, ca.summary, ca.is_complaint, ca.is_praise
        FROM comments c
        LEFT JOIN comment_analysis ca ON c.id = ca.comment_id
        WHERE c.video_id = :video_id
        ORDER BY c.like_count DESC
    """)
    result = await db.execute(stmt, {"video_id": video_id})
    comments = []
    for row in result:
        comments.append({
            "id": row.id,
            "author": row.author_name,
            "text": row.text,
            "likes": row.like_count,
            "sentiment": row.sentiment,
            "summary": row.summary,
            "is_complaint": row.is_complaint,
            "is_praise": row.is_praise
        })
    return comments

@router.post("/{video_id}/chat")
async def chat_video(video_id: int, request: ChatRequest, db: AsyncSession = Depends(get_db)):
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
        
    retrieval_service = RetrievalService(db)
    chat_service = ChatService()

    retrieved_comments = await retrieval_service.search_similar_comments(video_id, request.question, limit=20)
    answer = chat_service.ask_question(request.question, retrieved_comments)
    
    try:
        # Gemini sometimes returns integers, strings, or even the index [1]. Let's safely match them.
        ai_ids = [str(x) for x in answer.get('supporting_comment_ids', [])]
        supporting_evidence = [c for c in retrieved_comments if str(c['id']) in ai_ids]
        
        # Fallback: if Gemini fails to map IDs, just show the top 3 retrieved comments
        if not supporting_evidence and retrieved_comments:
            supporting_evidence = retrieved_comments[:3]
    except:
        supporting_evidence = retrieved_comments[:3]

    return {
        "answer": answer.get("answer"),
        "confidence": answer.get("confidence"),
        "relevant_aspects": answer.get("relevant_aspects"),
        "evidence": supporting_evidence
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
        "top_praises": report.top_praises
    }
