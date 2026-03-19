"""
main.py — FastAPI backend with full JWT authentication
Each user sees only their own jobs and resumes.
"""
import os, sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional

sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
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
from auth import (
    get_current_user, register_user, login_user,
    UserRegister, UserLogin
)

@asynccontextmanager
async def lifespan(app):
    init_db()
    print("✅ Database initialized")
    yield

app = FastAPI(
    title="Cloud Resume Screener API",
    description="NLP resume screening — spaCy · TF-IDF · JWT Auth · Neon PostgreSQL",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Auth endpoints ─────────────────────────────────────────────────────────────
@app.post("/api/auth/register")
def register(data: UserRegister, db: Session = Depends(get_db)):
    return register_user(data, db)

@app.post("/api/auth/login")
def login(data: UserLogin, db: Session = Depends(get_db)):
    return login_user(data.email, data.password, db)

@app.get("/api/auth/me")
def me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "name": current_user.name, "email": current_user.email}

# ── Job endpoints (scoped to current user) ─────────────────────────────────────
class JobCreate(BaseModel):
    title: str
    company: Optional[str] = ""
    description: str
    min_experience: Optional[int] = 0

@app.get("/api/jobs")
def get_jobs(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
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

@app.post("/api/jobs")
def create_job(job: JobCreate, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    db_job = JobPosting(**job.model_dump(), owner_id=current_user.id)
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    d = {c.name: getattr(db_job, c.name) for c in db_job.__table__.columns}
    d["resume_count"] = 0
    return d

@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id, JobPosting.owner_id == current_user.id
    ).first()
    if not job:
        raise HTTPException(404, "Job not found")
    db.delete(job)
    db.commit()
    return {"message": "Deleted"}

# ── Resume upload ──────────────────────────────────────────────────────────────
@app.post("/api/jobs/{job_id}/upload")
async def upload_resumes(
    job_id: int,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id, JobPosting.owner_id == current_user.id
    ).first()
    if not job:
        raise HTTPException(404, "Job not found")

    existing     = db.query(Resume).filter(Resume.job_id == job_id).all()
    exist_texts  = [r.raw_text for r in existing if r.raw_text]
    exist_fnames = [r.filename for r in existing if r.raw_text]

    new_texts, new_fnames, new_bytes_list = [], [], []
    for f in files:
        raw  = await f.read()
        text = extract_text_from_bytes(raw, f.filename)
        if text.strip():
            new_texts.append(text)
            new_fnames.append(f.filename)
            new_bytes_list.append((raw, f.filename))

    if not new_texts:
        raise HTTPException(400, "No readable text found in uploaded files")

    all_texts  = exist_texts + new_texts
    all_fnames = exist_fnames + new_fnames
    ranked     = rank_resumes(all_texts, all_fnames, job.description)

    db.query(Resume).filter(Resume.job_id == job_id).delete()

    storage_map = {}
    for raw, fname in new_bytes_list:
        meta = upload_file(raw, fname)
        storage_map[fname] = meta

    for r in ranked:
        fname   = r["filename"]
        stor    = storage_map.get(fname, {"storage_type": "existing", "storage_path": ""})
        contact = r.get("contact", {}) or {}
        db.add(Resume(
            job_id=job_id,
            filename=fname,
            candidate_name=r.get("name", "Unknown"),
            email=contact.get("email"),
            phone=contact.get("phone"),
            github=contact.get("github"),
            linkedin=contact.get("linkedin"),
            skills=r.get("skills", {}),
            education=r.get("education", []),
            experience_years=r.get("experience_years", 0),
            raw_text=all_texts[all_fnames.index(fname)],
            storage_path=stor["storage_path"],
            storage_type=stor["storage_type"],
            score=r["score"],
            score_breakdown=r["score_breakdown"],
            gap_analysis=r.get("gap_analysis", {}),
            matched_keywords=r.get("matched_keywords", []),
            verdict=r["verdict"],
            rank=r["rank"],
        ))

    scores = [r["score"] for r in ranked]
    db.add(ScreeningSession(
        job_id=job_id,
        total_resumes=len(ranked),
        top_candidate=ranked[0]["name"] if ranked else "",
        avg_score=round(sum(scores)/len(scores), 2) if scores else 0,
    ))
    db.commit()

    return {"message": f"Processed {len(new_texts)} new resume(s). Total: {len(ranked)}",
            "total": len(ranked), "new": len(new_texts)}

@app.get("/api/jobs/{job_id}/resumes")
def get_resumes(job_id: int, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    # Verify ownership
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id, JobPosting.owner_id == current_user.id
    ).first()
    if not job:
        raise HTTPException(404, "Job not found")
    resumes = db.query(Resume).filter(Resume.job_id == job_id).order_by(Resume.rank).all()
    result = []
    for r in resumes:
        d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
        d.pop("raw_text", None)
        d["total_skills"] = sum(len(v) for v in (d.get("skills") or {}).values())
        result.append(d)
    return result

@app.delete("/api/jobs/{job_id}/resumes/{resume_id}")
def delete_resume(job_id: int, resume_id: int, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id, JobPosting.owner_id == current_user.id
    ).first()
    if not job:
        raise HTTPException(404, "Job not found")
    r = db.query(Resume).filter(Resume.id == resume_id, Resume.job_id == job_id).first()
    if not r:
        raise HTTPException(404, "Resume not found")
    db.delete(r)
    remaining = db.query(Resume).filter(Resume.job_id == job_id)\
                  .order_by(Resume.score.desc()).all()
    for i, res in enumerate(remaining):
        res.rank = i + 1
    db.commit()
    return {"message": "Deleted and re-ranked"}

# ── Unique features ────────────────────────────────────────────────────────────
@app.get("/api/jobs/{job_id}/heatmap")
def skill_heatmap(job_id: int, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id, JobPosting.owner_id == current_user.id
    ).first()
    if not job:
        raise HTTPException(404, "Job not found")
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
def compare_top(job_id: int, top: int = 3, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id, JobPosting.owner_id == current_user.id
    ).first()
    if not job:
        raise HTTPException(404, "Job not found")
    resumes = db.query(Resume).filter(Resume.job_id == job_id)\
                .order_by(Resume.rank).limit(top).all()
    return [{"name": r.candidate_name, "rank": r.rank, "score": r.score,
             "breakdown": r.score_breakdown, "gap": r.gap_analysis} for r in resumes]

@app.get("/api/jobs/{job_id}/export/pdf")
def export_pdf(job_id: int, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id, JobPosting.owner_id == current_user.id
    ).first()
    if not job:
        raise HTTPException(404, "Job not found")
    resumes = db.query(Resume).filter(Resume.job_id == job_id).order_by(Resume.rank).all()
    job_dict = {c.name: getattr(job, c.name) for c in job.__table__.columns}
    resume_list = []
    for r in resumes:
        d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
        d["total_skills"] = sum(len(v) for v in (d.get("skills") or {}).values())
        resume_list.append(d)
    pdf_bytes = generate_pdf_report(job_dict, resume_list)
    fname = f"screening_{job.title.replace(' ','_')}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={fname}"})

@app.get("/api/jobs/{job_id}/export/csv")
def export_csv(job_id: int, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id, JobPosting.owner_id == current_user.id
    ).first()
    if not job:
        raise HTTPException(404, "Job not found")
    resumes = db.query(Resume).filter(Resume.job_id == job_id).order_by(Resume.rank).all()
    job_dict = {c.name: getattr(job, c.name) for c in job.__table__.columns}
    resume_list = [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in resumes]
    csv_str = generate_csv_report(job_dict, resume_list)
    fname = f"screening_{job.title.replace(' ','_')}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return Response(content=csv_str.encode(), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={fname}"})

# ── Analytics (user-scoped) ────────────────────────────────────────────────────
@app.get("/api/analytics/overview")
def analytics_overview(db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    user_job_ids = [j.id for j in db.query(JobPosting.id)
                    .filter(JobPosting.owner_id == current_user.id).all()]
    total_jobs    = len(user_job_ids)
    total_resumes = db.query(Resume).filter(Resume.job_id.in_(user_job_ids)).count() if user_job_ids else 0
    sessions      = db.query(ScreeningSession).filter(
        ScreeningSession.job_id.in_(user_job_ids)
    ).all() if user_job_ids else []
    avg_score = sum(s.avg_score for s in sessions) / len(sessions) if sessions else 0
    recent    = sorted(sessions, key=lambda s: s.created_at or datetime.min, reverse=True)[:5]
    return {
        "total_jobs":           total_jobs,
        "total_resumes":        total_resumes,
        "total_sessions":       len(sessions),
        "avg_score_across_all": round(avg_score, 2),
        "recent_activity": [
            {"job_id": s.job_id, "resumes": s.total_resumes,
             "top_candidate": s.top_candidate, "avg_score": s.avg_score,
             "at": s.created_at.isoformat() if s.created_at else ""}
            for s in recent
        ],
    }

@app.get("/api/analytics/skills")
def analytics_skills(db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    from collections import Counter
    user_job_ids = [j.id for j in db.query(JobPosting.id)
                    .filter(JobPosting.owner_id == current_user.id).all()]
    counter = Counter()
    for r in db.query(Resume).filter(Resume.job_id.in_(user_job_ids)).all():
        for skills in (r.skills or {}).values():
            for s in skills:
                counter[s] += 1
    return {"top_skills": [{"skill": k, "count": v} for k, v in counter.most_common(20)]}

@app.get("/api/analytics/score-distribution")
def score_distribution(db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    user_job_ids = [j.id for j in db.query(JobPosting.id)
                    .filter(JobPosting.owner_id == current_user.id).all()]
    buckets = {"0-20":0,"21-40":0,"41-60":0,"61-80":0,"81-100":0}
    for r in db.query(Resume).filter(Resume.job_id.in_(user_job_ids)).all():
        s = r.score
        if   s<=20: buckets["0-20"]  +=1
        elif s<=40: buckets["21-40"] +=1
        elif s<=60: buckets["41-60"] +=1
        elif s<=80: buckets["61-80"] +=1
        else:       buckets["81-100"]+=1
    return {"distribution": buckets}

@app.get("/api/storage/status")
def storage_status(current_user: User = Depends(get_current_user)):
    return get_storage_status()

@app.get("/api/skill-taxonomy")
def skill_taxonomy():
    return SKILL_TAXONOMY

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "2.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat()}

# ── Serve React frontend ───────────────────────────────────────────────────────
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)