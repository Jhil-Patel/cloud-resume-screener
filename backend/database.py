"""
database.py — SQLAlchemy ORM with User model for auth
"""
import os
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine, Column, Integer, String, Float,
    DateTime, Text, JSON, ForeignKey, Boolean
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./resume_screener.db"
)
# Fix URL scheme for psycopg2
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
if DATABASE_URL.startswith("postgresql://") and "+psycopg2" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args,
                        pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def _utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id              = Column(Integer, primary_key=True, index=True)
    name            = Column(String(200), nullable=False)
    email           = Column(String(200), unique=True, index=True, nullable=False)
    hashed_password = Column(String(500), nullable=False)
    created_at      = Column(DateTime(timezone=True), default=_utcnow)
    jobs            = relationship("JobPosting", back_populates="owner", cascade="all, delete-orphan")


class JobPosting(Base):
    __tablename__ = "job_postings"
    id              = Column(Integer, primary_key=True, index=True)
    owner_id        = Column(Integer, ForeignKey("users.id"), nullable=False)
    title           = Column(String(200), nullable=False)
    company         = Column(String(200), default="")
    description     = Column(Text, nullable=False)
    min_experience  = Column(Integer, default=0)
    created_at      = Column(DateTime(timezone=True), default=_utcnow)
    is_active       = Column(Boolean, default=True)
    owner           = relationship("User", back_populates="jobs")
    resumes         = relationship("Resume", back_populates="job", cascade="all, delete-orphan")


class Resume(Base):
    __tablename__ = "resumes"
    id               = Column(Integer, primary_key=True, index=True)
    job_id           = Column(Integer, ForeignKey("job_postings.id"), nullable=False)
    filename         = Column(String(300))
    candidate_name   = Column(String(200))
    email            = Column(String(200))
    phone            = Column(String(50))
    github           = Column(String(200))
    linkedin         = Column(String(200))
    skills           = Column(JSON, default=dict)
    education        = Column(JSON, default=list)
    experience_years = Column(Integer, default=0)
    raw_text         = Column(Text)
    storage_path     = Column(String(500))
    storage_type     = Column(String(20), default="local")
    score            = Column(Float, default=0.0)
    score_breakdown  = Column(JSON, default=dict)
    gap_analysis     = Column(JSON, default=dict)
    matched_keywords = Column(JSON, default=list)
    verdict          = Column(String(50))
    rank             = Column(Integer)
    uploaded_at      = Column(DateTime(timezone=True), default=_utcnow)
    job              = relationship("JobPosting", back_populates="resumes")


class ScreeningSession(Base):
    __tablename__ = "screening_sessions"
    id            = Column(Integer, primary_key=True, index=True)
    job_id        = Column(Integer, ForeignKey("job_postings.id"))
    total_resumes = Column(Integer, default=0)
    top_candidate = Column(String(200))
    avg_score     = Column(Float, default=0.0)
    created_at    = Column(DateTime(timezone=True), default=_utcnow)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)