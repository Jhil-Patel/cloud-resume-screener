<div align="center">

# ☁️ Cloud Resume Screener

### NLP-powered recruitment intelligence platform

[![Live Demo](https://img.shields.io/badge/🚀_Live_Demo-cloud--resume--screener.onrender.com-6366f1?style=for-the-badge)](https://cloud-resume-screener.onrender.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![spaCy](https://img.shields.io/badge/spaCy-3.7+-09a3d5?style=for-the-badge&logo=spacy)](https://spacy.io)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-336791?style=for-the-badge&logo=postgresql)](https://neon.tech)
[![Python](https://img.shields.io/badge/Python-3.9--3.13-3776ab?style=for-the-badge&logo=python)](https://python.org)
[![Tests](https://img.shields.io/badge/Tests-32%20passed-22c55e?style=for-the-badge&logo=pytest)](tests/)
[![Deploy](https://img.shields.io/badge/Deployed_on-Render-46e3b7?style=for-the-badge&logo=render)](https://render.com)

<br/>

**Upload resumes → NLP extracts skills → TF-IDF ranks candidates → Live dashboard shows results**

[🚀 Live Demo](https://cloud-resume-screener.onrender.com) • [📖 API Docs](https://cloud-resume-screener.onrender.com/docs) • [🐛 Issues](https://github.com/Jhil-Patel/cloud-resume-screener/issues)

</div>

---

## ✨ Features

| Feature | Description |
|---|---|
| 🧠 **spaCy NLP Pipeline** | EntityRuler + sentencizer extracts candidate name, skills, education, experience from PDF/TXT |
| 📊 **TF-IDF Cosine Similarity** | sklearn TfidfVectorizer (1,2)-ngrams + cosine_similarity matches resumes to job descriptions |
| ⚡ **Competitive Re-ranking** | Every upload re-scores ALL candidates together — scores reflect the real competitive pool |
| 🔍 **Gap Analysis** | Shows exactly which required skills each candidate has vs is missing |
| 🔥 **Skill Heatmap** | Visual matrix of all candidates × all skill categories |
| 📤 **PDF & CSV Export** | Download professional ranked leaderboard reports via ReportLab |
| 🔑 **Keyword Highlighting** | JD keywords found in each resume highlighted in candidate detail view |
| 📡 **Batch Comparison** | Radar chart comparing top 3 candidates across all 4 scoring dimensions |
| ☁️ **Cloud Storage** | AWS S3 via boto3 with automatic local fallback — zero config to start |
| 🗄️ **PostgreSQL** | SQLAlchemy ORM on Neon PostgreSQL — survives redeploys, persistent data |
| 🔌 **REST API** | 12 FastAPI endpoints, auto-documented Swagger UI at `/docs` |
| 🧪 **32 Tests** | Full pytest suite covering all endpoints, NLP functions, and scoring logic |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     React Frontend (SPA)                        │
│  Jobs · Upload · Rankings · Gap Analysis · Heatmap · Analytics  │
└────────────────────────┬────────────────────────────────────────┘
                         │  REST API (fetch)
┌────────────────────────▼────────────────────────────────────────┐
│                    FastAPI Backend                               │
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │   spaCy NLP     │  │  sklearn TF-IDF │  │   AWS S3        │ │
│  │  EntityRuler    │  │  cosine_sim     │  │  boto3 upload   │ │
│  │  PERSON NER     │  │  (1,2)-ngrams   │  │  local fallback │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │         SQLAlchemy ORM → Neon PostgreSQL                 │   │
│  │     JobPosting · Resume · ScreeningSession tables        │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Local Development

```bash
# 1. Clone
git clone https://github.com/Jhil-Patel/cloud-resume-screener.git
cd cloud-resume-screener

# 2. Install (Python 3.9-3.13, no C compiler needed)
pip install -r requirements.txt

# 3. Run
python start.py
# → http://localhost:8000        (app)
# → http://localhost:8000/docs   (API docs)
```

### Run Tests

```bash
pytest tests/ -v
# → 32 passed
```

### Docker

```bash
docker-compose up --build
# Starts FastAPI + PostgreSQL
```

---

## 🧠 How Scoring Works

Each resume is scored against the job description using **4 weighted signals**:

```
Final Score = TF-IDF Similarity × 40%
            + Skill Match       × 35%
            + Experience Fit    × 15%
            + Education Fit     × 10%
```

| Signal | Method |
|---|---|
| **TF-IDF Similarity** | `sklearn.TfidfVectorizer` (1,2)-ngrams, sublinear TF, full-corpus IDF |
| **Skill Match** | Skill overlap ratio between resume skills and JD requirements |
| **Experience Fit** | Candidate years vs JD requirement (power-scaled) |
| **Education Fit** | Degree level scoring (BSc=2, MSc=3, PhD=4) vs JD requirement |

**Unique: Competitive IDF** — when multiple resumes are uploaded, IDF is computed across the full candidate pool, so scores reflect actual competition rather than absolute quality.

---

## 📁 Project Structure

```
cloud-resume-screener/
├── backend/
│   ├── main.py            ← FastAPI app, 12 REST endpoints
│   ├── nlp_engine.py      ← spaCy EntityRuler + sklearn TF-IDF scorer
│   ├── database.py        ← SQLAlchemy ORM (Job, Resume, Session)
│   ├── pdf_parser.py      ← pdfplumber + PyPDF2 text extraction
│   ├── cloud_storage.py   ← AWS S3 upload + local fallback
│   └── export_utils.py    ← ReportLab PDF + CSV export
├── frontend/
│   └── index.html         ← React 18 SPA + Chart.js
├── tests/
│   └── test_api.py        ← 32 pytest tests
├── sample_resumes/        ← 4 demo resumes
├── render.yaml            ← Render deployment config
├── docker-compose.yml     ← PostgreSQL + API container setup
├── Dockerfile
├── requirements.txt
└── start.py               ← One-click local launcher
```

---

## 🔌 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/jobs` | List all job postings |
| `POST` | `/api/jobs` | Create a new job posting |
| `DELETE` | `/api/jobs/{id}` | Delete job + all candidates |
| `POST` | `/api/jobs/{id}/upload` | Upload + parse + rank resumes |
| `GET` | `/api/jobs/{id}/resumes` | Get ranked candidates |
| `DELETE` | `/api/jobs/{id}/resumes/{rid}` | Remove candidate + re-rank |
| `GET` | `/api/jobs/{id}/heatmap` | Skill coverage heatmap data |
| `GET` | `/api/jobs/{id}/compare` | Top-N radar comparison data |
| `GET` | `/api/jobs/{id}/export/pdf` | Download PDF report |
| `GET` | `/api/jobs/{id}/export/csv` | Download CSV export |
| `GET` | `/api/analytics/overview` | Platform-wide analytics |

Full interactive docs: **[/docs](https://cloud-resume-screener.onrender.com/docs)**

---

## ⚙️ Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ Yes | PostgreSQL connection string (Neon recommended) |
| `AWS_ACCESS_KEY_ID` | No | AWS credentials for S3 storage |
| `AWS_SECRET_ACCESS_KEY` | No | AWS credentials for S3 storage |
| `AWS_REGION` | No | AWS region (default: `us-east-1`) |
| `S3_BUCKET_NAME` | No | S3 bucket name for resume storage |

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **API Framework** | FastAPI 0.110+ |
| **NLP** | spaCy 3.7+ (EntityRuler + sentencizer) |
| **ML Scoring** | scikit-learn (TfidfVectorizer + cosine_similarity) |
| **PDF Parsing** | pdfplumber + PyPDF2 |
| **ORM** | SQLAlchemy 2.0 |
| **Database** | Neon PostgreSQL (production) / SQLite (local) |
| **File Storage** | AWS S3 via boto3 + local fallback |
| **Frontend** | React 18 + Chart.js 4 |
| **Server** | Uvicorn (ASGI) |
| **Deployment** | Render (Web Service, always-on) |
| **Testing** | pytest (32 tests) |
| **PDF Export** | ReportLab |

---

## 📄 License

MIT License — feel free to use this project as a reference or starting point.

---

<div align="center">
Built with ❤️ by <a href="https://github.com/Jhil-Patel">Jhil Patel</a>
<br/>
<a href="https://cloud-resume-screener.onrender.com">🚀 Live Demo</a> •
<a href="https://cloud-resume-screener.onrender.com/docs">📖 API Docs</a>
</div>
