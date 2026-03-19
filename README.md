# ☁️ Cloud Resume Screener v2

> **NLP-powered recruitment intelligence platform** — FastAPI · spaCy · sklearn TF-IDF · React · PostgreSQL · AWS S3

---

## 📌 Resume Bullet Points (Accurate)

```
Cloud Resume Screener | Python • spaCy • FastAPI • sklearn • AWS S3 • React • PostgreSQL  Sep 2025 – Dec 2025

▸ Built a rule-based NLP pipeline using spaCy (EntityRuler + sentencizer) to extract candidate 
  name, skills, education, experience years, and contact info from uploaded PDF/TXT resumes.

▸ Implemented TF-IDF cosine similarity (sklearn TfidfVectorizer, (1,2)-ngrams, sublinear TF) to 
  match resumes against job descriptions; combined with weighted skill-match, experience-fit, and 
  education-fit scores to produce a final ranked candidate leaderboard.

▸ Built a REST API with FastAPI (10+ endpoints) connected to a PostgreSQL-compatible SQLAlchemy 
  database; integrated AWS S3 (boto3) for resume file storage with automatic local fallback.

▸ Developed a React single-page frontend with Chart.js visualizations (bar, radar, doughnut), 
  real-time drag-and-drop upload, candidate detail modals, multi-job management, and live analytics.
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     React Frontend                          │
│   Upload → Jobs → Rankings → Analytics → Storage → About   │
└────────────────────┬────────────────────────────────────────┘
                     │  HTTP REST (fetch API)
┌────────────────────▼────────────────────────────────────────┐
│                  FastAPI Backend                            │
│  /api/jobs  /api/jobs/{id}/upload  /api/analytics/*        │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  NLP Engine  │  │  TF-IDF      │  │  Cloud Storage   │  │
│  │  spaCy rules │  │  sklearn     │  │  AWS S3 / local  │  │
│  │  + regex     │  │  cosine sim  │  │  boto3           │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  SQLAlchemy ORM → SQLite (dev) / PostgreSQL (prod)  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Run (one command)
```bash
python start.py
```
This starts the FastAPI server at `http://localhost:8000` and opens the frontend automatically.

**Or manually:**
```bash
# Terminal 1 — Backend
cd backend
python main.py

# Terminal 2 — Frontend (just open in browser)
open frontend/index.html
```

### 3. Explore the API docs
```
http://localhost:8000/docs      ← Swagger UI
http://localhost:8000/redoc     ← ReDoc
```

---

## 🔑 Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | No | PostgreSQL URL (default: SQLite) |
| `AWS_ACCESS_KEY_ID` | No | AWS credentials for S3 |
| `AWS_SECRET_ACCESS_KEY` | No | AWS credentials for S3 |
| `AWS_REGION` | No | AWS region (default: us-east-1) |
| `S3_BUCKET_NAME` | No | S3 bucket for resume storage |

### Switch to PostgreSQL
```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/resume_screener"
python start.py
```

### Enable AWS S3
```bash
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_REGION=ap-south-1
export S3_BUCKET_NAME=your-bucket-name
python start.py
```

---

## 📁 Project Structure

```
resume-screener/
├── backend/
│   ├── main.py            ← FastAPI app, all API endpoints
│   ├── database.py        ← SQLAlchemy models (Job, Resume, Session)
│   ├── nlp_engine.py      ← spaCy pipeline + sklearn TF-IDF scorer
│   ├── pdf_parser.py      ← pdfplumber + PyPDF2 text extraction
│   └── cloud_storage.py   ← AWS S3 upload + local fallback
├── frontend/
│   └── index.html         ← React SPA (Chart.js, drag-drop, modals)
├── sample_resumes/        ← 4 sample resumes for demo
│   ├── arjun_mehta.txt
│   ├── sneha_patel.txt
│   ├── priya_sharma.txt
│   └── rohan_verma.txt
├── uploads/               ← Local resume file storage
├── requirements.txt
├── start.py               ← One-click launcher
└── README.md
```

---

## 🧠 How It Works

### NLP Pipeline (spaCy)
1. **Text extraction** — pdfplumber extracts text from PDFs (PyPDF2 fallback)
2. **Name detection** — spaCy sentencizer + heuristic line analysis
3. **Skill extraction** — Rule-based matching against 120+ skills in 7 categories
4. **Education parsing** — Keyword matching with degree-level scoring (BSc=2, MSc=3, PhD=4)
5. **Experience detection** — Regex patterns + job title heuristics
6. **Contact extraction** — Regex for email, phone, GitHub, LinkedIn

### Scoring Engine (sklearn)
| Component | Weight | Method |
|---|---|---|
| TF-IDF Similarity | 40% | sklearn TfidfVectorizer (1,2)-ngrams + cosine_similarity |
| Skill Match | 35% | Skill overlap ratio vs JD skill requirements |
| Experience Fit | 15% | Years vs JD requirement (power-scaled) |
| Education Fit | 10% | Degree level vs JD requirements |

### Unique Features
- **Competitive re-ranking**: Every upload re-computes IDF across the full candidate pool — scores reflect actual competition, not just absolute quality
- **Real-time analytics**: Score distribution, top skills in pool, session history
- **Multi-job management**: Create multiple jobs, switch between them — data persists in DB
- **Delete & re-rank**: Remove a candidate and the rest automatically re-rank
- **Live storage status**: Detects whether S3 is configured and shows connection status

---

## 🔌 API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/jobs` | List all job postings |
| POST | `/api/jobs` | Create a new job |
| DELETE | `/api/jobs/{id}` | Delete job + all resumes |
| POST | `/api/jobs/{id}/upload` | Upload + parse + score resumes |
| GET | `/api/jobs/{id}/resumes` | Get ranked candidates |
| GET | `/api/jobs/{id}/resumes/{rid}` | Candidate detail |
| DELETE | `/api/jobs/{id}/resumes/{rid}` | Remove candidate + re-rank |
| GET | `/api/analytics/overview` | Platform analytics |
| GET | `/api/analytics/skills` | Top skills across pool |
| GET | `/api/analytics/score-distribution` | Score histogram |
| GET | `/api/storage/status` | S3 / local storage status |
| GET | `/api/skill-taxonomy` | Full skill taxonomy |

---

## ☁️ Deployment Guide

### Deploy on AWS EC2 (Free Tier)
```bash
# 1. Launch EC2 t2.micro (Amazon Linux 2)
# 2. SSH into instance
ssh -i your-key.pem ec2-user@your-ec2-ip

# 3. Install Python & dependencies
sudo yum install python3-pip -y
git clone your-repo
cd resume-screener
pip3 install -r requirements.txt

# 4. Set environment variables
export DATABASE_URL="postgresql://..."
export AWS_ACCESS_KEY_ID="..."
# ...

# 5. Run with gunicorn for production
pip install gunicorn
cd backend && gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

### Deploy Frontend
Upload `frontend/index.html` to S3 static website hosting, or serve via Nginx alongside the API.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI 0.115 |
| NLP | spaCy 3.8 (rule-based EntityRuler + sentencizer) |
| ML Scoring | scikit-learn 1.5 (TfidfVectorizer + cosine_similarity) |
| PDF Parsing | pdfplumber + PyPDF2 |
| ORM | SQLAlchemy 2.0 |
| Database | SQLite (dev) / PostgreSQL (prod) |
| File Storage | AWS S3 (boto3) + local fallback |
| Frontend | React 18 (CDN) + Chart.js 4 |
| Server | Uvicorn (ASGI) |
