"""
main.py — Cloud Resume Screener v2 — Complete FastAPI backend
Features: JWT auth, NLP scoring, gap analysis, shortlisting,
          notes, search/filter, stats, PDF/CSV export, AWS S3
"""
import os, sys, logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.exc import OperationalError

sys.path.insert(0, os.path.dirname(__file__))
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, init_db, JobPosting, Resume, ScreeningSession, User
from nlp_engine import rank_resumes, SKILL_TAXONOMY
from pdf_parser import extract_text_from_bytes
from cloud_storage import upload_file, get_storage_status
from export_utils import generate_pdf_report, generate_csv_report
from auth import get_current_user, register_user, login_user, UserRegister, UserLogin


# ── Lifespan ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app):
    try:
        init_db()
    except Exception as ex:
        logger.error(f"DB init error (non-fatal): {ex}")
    yield


app = FastAPI(
    title="Cloud Resume Screener API",
    description="NLP resume screening — spaCy · TF-IDF · JWT · Neon PostgreSQL · AWS S3",
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


# ── Schemas ────────────────────────────────────────────────────────────────
class JobCreate(BaseModel):
    title: str
    company: Optional[str] = ""
    description: str
    job_type: Optional[str] = "Full-time"
    location: Optional[str] = ""
    min_experience: Optional[int] = 0
    max_experience: Optional[int] = 10

class ResumeNote(BaseModel):
    notes: str

class ShortlistUpdate(BaseModel):
    shortlisted: bool


# ── Auth ───────────────────────────────────────────────────────────────────
@app.post("/api/auth/register")
def register(data: UserRegister, db: Session = Depends(get_db)):
    return register_user(data, db)

@app.post("/api/auth/login")
def login(data: UserLogin, db: Session = Depends(get_db)):
    return login_user(data.email, data.password, db)

@app.get("/api/auth/me")
def me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "name": current_user.name, "email": current_user.email}


# ── Jobs ───────────────────────────────────────────────────────────────────
@app.get("/api/jobs")
def get_jobs(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        jobs = db.query(JobPosting)\
                 .filter(JobPosting.owner_id == current_user.id, JobPosting.is_active == True)\
                 .order_by(JobPosting.created_at.desc()).all()
        result = []
        for j in jobs:
            count = db.query(Resume).filter(Resume.job_id == j.id).count()
            d = {c.name: getattr(j, c.name) for c in j.__table__.columns}
            d["resume_count"] = count
            result.append(d)
        return result
    except OperationalError as ex:
        logger.error(f"DB error in get_jobs: {ex}")
        raise HTTPException(503, "Database temporarily unavailable. Please retry in a moment.")

@app.post("/api/jobs")
def create_job(job: JobCreate, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    try:
        db_job = JobPosting(**job.model_dump(), owner_id=current_user.id)
        db.add(db_job)
        db.commit()
        db.refresh(db_job)
        d = {c.name: getattr(db_job, c.name) for c in db_job.__table__.columns}
        d["resume_count"] = 0
        return d
    except OperationalError as ex:
        db.rollback()
        logger.error(f"DB error in create_job: {ex}")
        raise HTTPException(503, "Database temporarily unavailable. Please retry in a moment.")
    except Exception as ex:
        db.rollback()
        logger.error(f"Error in create_job: {ex}")
        raise HTTPException(500, f"Failed to create job: {str(ex)}")

@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id, JobPosting.owner_id == current_user.id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    try:
        db.delete(job); db.commit()
        return {"message": "Deleted"}
    except Exception as ex:
        db.rollback(); raise HTTPException(500, str(ex))

@app.get("/api/jobs/{job_id}/stats")
def job_stats(job_id: int, db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)):
    """Detailed stats for a single job posting."""
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id, JobPosting.owner_id == current_user.id).first()
    if not job: raise HTTPException(404, "Job not found")
    resumes = db.query(Resume).filter(Resume.job_id == job_id).all()
    if not resumes:
        return {"total": 0, "shortlisted": 0, "avg_score": 0, "score_buckets": {}}
    scores = [r.score for r in resumes]
    buckets = {"0-20":0,"21-40":0,"41-60":0,"61-80":0,"81-100":0}
    for s in scores:
        if s<=20: buckets["0-20"]+=1
        elif s<=40: buckets["21-40"]+=1
        elif s<=60: buckets["41-60"]+=1
        elif s<=80: buckets["61-80"]+=1
        else: buckets["81-100"]+=1
    from collections import Counter
    skill_counter = Counter()
    for r in resumes:
        for skills in (r.skills or {}).values():
            for s in skills: skill_counter[s] += 1
    return {
        "total": len(resumes),
        "shortlisted": sum(1 for r in resumes if r.shortlisted),
        "avg_score": round(sum(scores)/len(scores), 2),
        "top_score": round(max(scores), 2),
        "score_buckets": buckets,
        "top_skills": [{"skill":k,"count":v} for k,v in skill_counter.most_common(10)],
        "verdict_counts": {
            "Strong Match": sum(1 for r in resumes if r.verdict=="Strong Match"),
            "Good Match":   sum(1 for r in resumes if r.verdict=="Good Match"),
            "Partial Match":sum(1 for r in resumes if r.verdict=="Partial Match"),
            "Weak Match":   sum(1 for r in resumes if r.verdict=="Weak Match"),
        }
    }


# ── Resumes ────────────────────────────────────────────────────────────────
@app.post("/api/jobs/{job_id}/upload")
async def upload_resumes(
    job_id: int,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id, JobPosting.owner_id == current_user.id).first()
    if not job: raise HTTPException(404, "Job not found")

    existing     = db.query(Resume).filter(Resume.job_id == job_id).all()
    exist_texts  = [r.raw_text for r in existing if r.raw_text]
    exist_fnames = [r.filename for r in existing if r.raw_text]

    new_texts, new_fnames, new_bytes = [], [], []
    for f in files:
        try:
            raw  = await f.read()
            text = extract_text_from_bytes(raw, f.filename)
            if text.strip():
                new_texts.append(text); new_fnames.append(f.filename); new_bytes.append((raw, f.filename))
        except Exception as ex:
            logger.warning(f"Failed to parse {f.filename}: {ex}")

    if not new_texts:
        raise HTTPException(400, "No readable text found in uploaded files. Please upload valid PDF or TXT files.")

    all_texts  = exist_texts + new_texts
    all_fnames = exist_fnames + new_fnames

    try:
        ranked = rank_resumes(all_texts, all_fnames, job.description)
    except Exception as ex:
        logger.error(f"Ranking error: {ex}")
        raise HTTPException(500, f"NLP ranking failed: {str(ex)}")

    try:
        # Preserve shortlist/notes from existing resumes
        existing_meta = {r.filename: {"shortlisted": r.shortlisted, "notes": r.notes} for r in existing}
        db.query(Resume).filter(Resume.job_id == job_id).delete()

        storage_map = {}
        for raw, fname in new_bytes:
            try:
                meta = upload_file(raw, fname)
                storage_map[fname] = meta
            except Exception as ex:
                logger.warning(f"Storage failed for {fname}: {ex}")
                storage_map[fname] = {"storage_type": "local", "storage_path": ""}

        for r in ranked:
            fname   = r["filename"]
            stor    = storage_map.get(fname, {"storage_type": "existing", "storage_path": ""})
            contact = r.get("contact") or {}
            meta    = existing_meta.get(fname, {})
            db.add(Resume(
                job_id=job_id,
                filename=fname,
                candidate_name=r.get("name","Unknown"),
                email=contact.get("email",""),
                phone=contact.get("phone",""),
                github=contact.get("github",""),
                linkedin=contact.get("linkedin",""),
                skills=r.get("skills",{}),
                education=r.get("education",[]),
                experience_years=r.get("experience_years",0),
                raw_text=all_texts[all_fnames.index(fname)],
                storage_path=stor.get("storage_path",""),
                storage_type=stor.get("storage_type","local"),
                score=r["score"],
                score_breakdown=r.get("score_breakdown",{}),
                gap_analysis=r.get("gap_analysis",{}),
                matched_keywords=r.get("matched_keywords",[]),
                verdict=r["verdict"],
                rank=r["rank"],
                notes=meta.get("notes",""),
                shortlisted=meta.get("shortlisted",False),
            ))

        scores = [r["score"] for r in ranked]
        db.add(ScreeningSession(
            job_id=job_id,
            total_resumes=len(ranked),
            top_candidate=ranked[0]["name"] if ranked else "",
            avg_score=round(sum(scores)/len(scores), 2) if scores else 0,
        ))
        db.commit()
    except Exception as ex:
        db.rollback()
        logger.error(f"DB save error: {ex}")
        raise HTTPException(500, f"Failed to save results: {str(ex)}")

    return {"message": f"Processed {len(new_texts)} new resume(s). Total: {len(ranked)}",
            "total": len(ranked), "new": len(new_texts)}


@app.get("/api/jobs/{job_id}/resumes")
def get_resumes(
    job_id: int,
    search: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None),
    shortlisted_only: Optional[bool] = Query(False),
    verdict: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id, JobPosting.owner_id == current_user.id).first()
    if not job: raise HTTPException(404, "Job not found")

    q = db.query(Resume).filter(Resume.job_id == job_id)
    if shortlisted_only: q = q.filter(Resume.shortlisted == True)
    if min_score is not None: q = q.filter(Resume.score >= min_score)
    if verdict: q = q.filter(Resume.verdict == verdict)
    resumes = q.order_by(Resume.rank).all()

    result = []
    for r in resumes:
        d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
        d.pop("raw_text", None)
        d["total_skills"] = sum(len(v) for v in (d.get("skills") or {}).values())
        # Apply search filter
        if search:
            sl = search.lower()
            name_match = sl in (r.candidate_name or "").lower()
            skill_match = any(sl in s.lower() for skills in (r.skills or {}).values() for s in skills)
            if not name_match and not skill_match:
                continue
        result.append(d)
    return result


@app.patch("/api/jobs/{job_id}/resumes/{resume_id}/shortlist")
def toggle_shortlist(job_id: int, resume_id: int, body: ShortlistUpdate,
                     db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id, JobPosting.owner_id == current_user.id).first()
    if not job: raise HTTPException(404, "Job not found")
    r = db.query(Resume).filter(Resume.id == resume_id, Resume.job_id == job_id).first()
    if not r: raise HTTPException(404, "Resume not found")
    r.shortlisted = body.shortlisted
    db.commit()
    return {"id": r.id, "shortlisted": r.shortlisted}


@app.patch("/api/jobs/{job_id}/resumes/{resume_id}/notes")
def update_notes(job_id: int, resume_id: int, body: ResumeNote,
                 db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id, JobPosting.owner_id == current_user.id).first()
    if not job: raise HTTPException(404, "Job not found")
    r = db.query(Resume).filter(Resume.id == resume_id, Resume.job_id == job_id).first()
    if not r: raise HTTPException(404, "Resume not found")
    r.notes = body.notes
    db.commit()
    return {"id": r.id, "notes": r.notes}


@app.delete("/api/jobs/{job_id}/resumes/{resume_id}")
def delete_resume(job_id: int, resume_id: int,
                  db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id, JobPosting.owner_id == current_user.id).first()
    if not job: raise HTTPException(404, "Job not found")
    r = db.query(Resume).filter(Resume.id == resume_id, Resume.job_id == job_id).first()
    if not r: raise HTTPException(404, "Resume not found")
    db.delete(r)
    for i, res in enumerate(db.query(Resume).filter(Resume.job_id == job_id)
                               .order_by(Resume.score.desc()).all()):
        res.rank = i + 1
    db.commit()
    return {"message": "Deleted and re-ranked"}


# ── Unique features ────────────────────────────────────────────────────────
@app.get("/api/jobs/{job_id}/heatmap")
def skill_heatmap(job_id: int, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id, JobPosting.owner_id == current_user.id).first()
    if not job: raise HTTPException(404, "Job not found")
    resumes = db.query(Resume).filter(Resume.job_id == job_id).order_by(Resume.rank).all()
    categories = list(SKILL_TAXONOMY.keys())
    matrix = []
    for r in resumes:
        row = {"name": r.candidate_name, "rank": r.rank}
        for cat in categories:
            row[cat] = len((r.skills or {}).get(cat, []))
        matrix.append(row)
    return {"categories": categories, "matrix": matrix}


@app.get("/api/jobs/{job_id}/compare")
def compare_top(job_id: int, top: int = 3,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id, JobPosting.owner_id == current_user.id).first()
    if not job: raise HTTPException(404, "Job not found")
    resumes = db.query(Resume).filter(Resume.job_id == job_id)\
                .order_by(Resume.rank).limit(top).all()
    return [{"name": r.candidate_name, "rank": r.rank, "score": r.score,
             "breakdown": r.score_breakdown, "gap": r.gap_analysis} for r in resumes]


# ── Export ─────────────────────────────────────────────────────────────────
@app.get("/api/jobs/{job_id}/export/pdf")
def export_pdf(job_id: int, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id, JobPosting.owner_id == current_user.id).first()
    if not job: raise HTTPException(404, "Job not found")
    resumes = db.query(Resume).filter(Resume.job_id == job_id).order_by(Resume.rank).all()
    job_dict = {c.name: getattr(job, c.name) for c in job.__table__.columns}
    resume_list = []
    for r in resumes:
        d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
        d["total_skills"] = sum(len(v) for v in (d.get("skills") or {}).values())
        resume_list.append(d)
    try:
        pdf_bytes = generate_pdf_report(job_dict, resume_list)
    except Exception as ex:
        raise HTTPException(500, f"PDF generation failed: {str(ex)}")
    fname = f"screening_{job.title.replace(' ','_')}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={fname}"})


@app.get("/api/jobs/{job_id}/export/csv")
def export_csv(job_id: int, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id, JobPosting.owner_id == current_user.id).first()
    if not job: raise HTTPException(404, "Job not found")
    resumes = db.query(Resume).filter(Resume.job_id == job_id).order_by(Resume.rank).all()
    job_dict = {c.name: getattr(job, c.name) for c in job.__table__.columns}
    resume_list = [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in resumes]
    csv_str = generate_csv_report(job_dict, resume_list)
    fname = f"screening_{job.title.replace(' ','_')}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return Response(content=csv_str.encode(), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={fname}"})


# ── Analytics ──────────────────────────────────────────────────────────────
@app.get("/api/analytics/overview")
def analytics_overview(db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    try:
        user_job_ids = [j.id for j in db.query(JobPosting.id)
                        .filter(JobPosting.owner_id == current_user.id).all()]
        total_jobs    = len(user_job_ids)
        total_resumes = db.query(Resume).filter(Resume.job_id.in_(user_job_ids)).count() if user_job_ids else 0
        shortlisted   = db.query(Resume).filter(Resume.job_id.in_(user_job_ids), Resume.shortlisted==True).count() if user_job_ids else 0
        sessions      = db.query(ScreeningSession).filter(
            ScreeningSession.job_id.in_(user_job_ids)).all() if user_job_ids else []
        avg_score = round(sum(s.avg_score for s in sessions)/len(sessions), 2) if sessions else 0
        recent = sorted(sessions, key=lambda s: s.created_at or datetime.min, reverse=True)[:5]
        return {
            "total_jobs":           total_jobs,
            "total_resumes":        total_resumes,
            "total_shortlisted":    shortlisted,
            "total_sessions":       len(sessions),
            "avg_score_across_all": avg_score,
            "recent_activity": [
                {"job_id": s.job_id, "resumes": s.total_resumes,
                 "top_candidate": s.top_candidate, "avg_score": s.avg_score,
                 "at": s.created_at.isoformat() if s.created_at else ""}
                for s in recent
            ],
        }
    except OperationalError as ex:
        raise HTTPException(503, "Database temporarily unavailable. Please retry.")

@app.get("/api/analytics/skills")
def analytics_skills(db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    from collections import Counter
    user_job_ids = [j.id for j in db.query(JobPosting.id)
                    .filter(JobPosting.owner_id == current_user.id).all()]
    counter = Counter()
    for r in db.query(Resume).filter(Resume.job_id.in_(user_job_ids)).all():
        for skills in (r.skills or {}).values():
            for s in skills: counter[s] += 1
    return {"top_skills": [{"skill":k,"count":v} for k,v in counter.most_common(20)]}

@app.get("/api/analytics/score-distribution")
def score_distribution(db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    user_job_ids = [j.id for j in db.query(JobPosting.id)
                    .filter(JobPosting.owner_id == current_user.id).all()]
    buckets = {"0-20":0,"21-40":0,"41-60":0,"61-80":0,"81-100":0}
    for r in db.query(Resume).filter(Resume.job_id.in_(user_job_ids)).all():
        s = r.score
        if s<=20: buckets["0-20"]+=1
        elif s<=40: buckets["21-40"]+=1
        elif s<=60: buckets["41-60"]+=1
        elif s<=80: buckets["61-80"]+=1
        else: buckets["81-100"]+=1
    return {"distribution": buckets}


# ── Misc ───────────────────────────────────────────────────────────────────
@app.get("/api/storage/status")
def storage_status(current_user: User = Depends(get_current_user)):
    return get_storage_status()

@app.get("/api/skill-taxonomy")
def skill_taxonomy():
    return SKILL_TAXONOMY

@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(__import__('sqlalchemy').text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "error"
    return {"status": "ok", "version": "2.0.0", "db": db_status,
            "timestamp": datetime.now(timezone.utc).isoformat()}


# ── Serve React frontend ───────────────────────────────────────────────────
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)