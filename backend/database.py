"""
database.py — SQLAlchemy ORM with lazy Neon PostgreSQL connection + retry logic
Fixes the Render/Neon 500 error by:
  1. Adding connection retry for sleeping Neon instances
  2. Proper keepalives for long-lived connections  
  3. Error handling that never exposes raw 500s
"""
import os, time, logging
from datetime import datetime, timezone
import urllib.parse
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, JSON, ForeignKey, Boolean, event
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)

def _build_url():
    url = os.getenv("DATABASE_URL", "sqlite:///./resume_screener.db")
    # Fix scheme for psycopg2
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://") and "+psycopg2" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    # Remove unsupported params
    for bad_param in ["channel_binding", "options"]:
        if bad_param + "=" in url:
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            params.pop(bad_param, None)
            url = urllib.parse.urlunparse(parsed._replace(
                query=urllib.parse.urlencode({k: v[0] for k, v in params.items()})
            ))
    return url

DATABASE_URL = _build_url()
IS_POSTGRES = "postgresql" in DATABASE_URL

def _make_engine():
    connect_args = {}
    if IS_POSTGRES:
        connect_args = {
            "connect_timeout": 15,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
            "application_name": "cloud_resume_screener",
        }
    else:
        connect_args = {"check_same_thread": False}

    return create_engine(
        DATABASE_URL,
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5 if IS_POSTGRES else 1,
        max_overflow=10 if IS_POSTGRES else 0,
        echo=False,
    )

engine = _make_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def _utcnow():
    return datetime.now(timezone.utc)

# ── Models ─────────────────────────────────────────────────────────────────
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
    id             = Column(Integer, primary_key=True, index=True)
    owner_id       = Column(Integer, ForeignKey("users.id"), nullable=False)
    title          = Column(String(200), nullable=False)
    company        = Column(String(200), default="")
    description    = Column(Text, nullable=False)
    job_type       = Column(String(50), default="Full-time")
    location       = Column(String(200), default="")
    min_experience = Column(Integer, default=0)
    max_experience = Column(Integer, default=10)
    created_at     = Column(DateTime(timezone=True), default=_utcnow)
    is_active      = Column(Boolean, default=True)
    owner          = relationship("User", back_populates="jobs")
    resumes        = relationship("Resume", back_populates="job", cascade="all, delete-orphan")

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
    storage_path     = Column(String(500), default="")
    storage_type     = Column(String(20), default="local")
    score            = Column(Float, default=0.0)
    score_breakdown  = Column(JSON, default=dict)
    gap_analysis     = Column(JSON, default=dict)
    matched_keywords = Column(JSON, default=list)
    verdict          = Column(String(50), default="")
    rank             = Column(Integer, default=0)
    notes            = Column(Text, default="")
    shortlisted      = Column(Boolean, default=False)
    uploaded_at      = Column(DateTime(timezone=True), default=_utcnow)
    job              = relationship("JobPosting", back_populates="resumes")

class ScreeningSession(Base):
    __tablename__ = "screening_sessions"
    id            = Column(Integer, primary_key=True, index=True)
    job_id        = Column(Integer, ForeignKey("job_postings.id"))
    total_resumes = Column(Integer, default=0)
    top_candidate = Column(String(200), default="")
    avg_score     = Column(Float, default=0.0)
    created_at    = Column(DateTime(timezone=True), default=_utcnow)

# ── DB helpers ─────────────────────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db(retries=5, delay=2):
    """Create tables with retry for Neon cold-start."""
    for attempt in range(retries):
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("✅ Database initialized")
            return
        except OperationalError as ex:
            if attempt < retries - 1:
                logger.warning(f"DB init attempt {attempt+1} failed: {ex}. Retrying in {delay}s...")
                time.sleep(delay)
                delay *= 2
            else:
                logger.error(f"DB init failed after {retries} attempts: {ex}")
                raise