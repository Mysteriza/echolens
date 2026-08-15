from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()


class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    youtube_id = Column(String, unique=True, index=True, nullable=False)
    title = Column(String)
    channel = Column(String)
    thumbnail = Column(String)
    comment_count = Column(Integer)
    analysis_status = Column(
        String, default="pending"
    )  # pending, collecting, analyzing, completed, failed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    comments = relationship(
        "Comment", back_populates="video", cascade="all, delete-orphan"
    )


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    youtube_id = Column(String, unique=True, index=True, nullable=False)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False)
    parent_id = Column(String, index=True)  # youtube_id of the parent comment
    author_name = Column(String)
    text = Column(String, nullable=False)
    published_at = Column(DateTime(timezone=True))
    like_count = Column(Integer, default=0)
    is_reply = Column(Boolean, default=False)
    is_spam = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    video = relationship("Video", back_populates="comments")
    analysis = relationship(
        "CommentAnalysis",
        back_populates="comment",
        uselist=False,
        cascade="all, delete-orphan",
    )
    aspects = relationship(
        "CommentAspect", back_populates="comment", cascade="all, delete-orphan"
    )
    embedding = relationship(
        "CommentEmbedding",
        back_populates="comment",
        uselist=False,
        cascade="all, delete-orphan",
    )


class CommentAnalysis(Base):
    __tablename__ = "comment_analysis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    comment_id = Column(Integer, ForeignKey("comments.id"), unique=True, nullable=False)
    sentiment = Column(String)  # positive, neutral, negative, mixed, uncertain
    confidence = Column(Float)
    language = Column(String)
    is_product_experience = Column(Boolean)
    is_complaint = Column(Boolean)
    is_praise = Column(Boolean)
    is_question = Column(Boolean)
    summary = Column(String)
    analysis_version = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    comment = relationship("Comment", back_populates="analysis")


class CommentAspect(Base):
    __tablename__ = "comment_aspects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    comment_id = Column(Integer, ForeignKey("comments.id"), nullable=False)
    aspect = Column(String, index=True, nullable=False)
    sentiment = Column(String)  # positive, neutral, negative

    comment = relationship("Comment", back_populates="aspects")


class CommentEmbedding(Base):
    __tablename__ = "comment_embeddings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    comment_id = Column(Integer, ForeignKey("comments.id"), unique=True, nullable=False)
    embedding = Column(Vector(768))  # 768 dimensions for Gemini embeddings

    comment = relationship("Comment", back_populates="embedding")


class VideoLog(Base):
    __tablename__ = "video_logs"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    message = Column(Text, nullable=False)
    level = Column(String(50), default="INFO")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class VideoReport(Base):
    __tablename__ = "video_reports"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(
        Integer, ForeignKey("videos.id", ondelete="CASCADE"), index=True, unique=True
    )
    overall_sentiment = Column(String(50))
    summary = Column(Text)
    top_complaints = Column(Text)  # Stored as JSON string or text bullet points
    top_praises = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
