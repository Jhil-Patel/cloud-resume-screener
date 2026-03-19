# 🚀 Deployment Guide — Render + Neon PostgreSQL

## Step 1 — Push to GitHub

```bash
git init
git add .
git commit -m "Cloud Resume Screener v2 — FastAPI + spaCy + Neon + Render"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/cloud-resume-screener.git
git push -u origin main
```

## Step 2 — Deploy on Render

1. Go to [render.com](https://render.com) → Sign in with GitHub
2. Click **"New +"** → **"Web Service"**
3. Connect your `cloud-resume-screener` repository
4. Render auto-detects `render.yaml` — click **"Apply"**
5. Your app deploys in ~3 minutes

**Your live URL:** `https://cloud-resume-screener.onrender.com`

## Step 3 — Verify deployment

```bash
curl https://cloud-resume-screener.onrender.com/api/health
# → {"status":"ok","version":"2.0.0"}
```

Open the app in browser — the React frontend loads automatically from `/`.

## Environment Variables (already in render.yaml)

| Variable | Value |
|---|---|
| `DATABASE_URL` | Your Neon PostgreSQL URL (already set) |
| `AWS_ACCESS_KEY_ID` | Add in Render dashboard when ready |
| `AWS_SECRET_ACCESS_KEY` | Add in Render dashboard when ready |
| `AWS_REGION` | `ap-south-1` (Mumbai) |
| `S3_BUCKET_NAME` | Your bucket name |

## Local development

```bash
pip install -r requirements.txt
python backend/main.py
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger API docs)
```

## What's live

- **Frontend**: `https://your-app.onrender.com/` — React dashboard
- **API docs**: `https://your-app.onrender.com/docs` — Swagger UI
- **Database**: Neon PostgreSQL (persistent, survives redeploys)
- **Storage**: Local filesystem on Render (add S3 for permanent file storage)
