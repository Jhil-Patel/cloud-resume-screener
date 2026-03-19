FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for pdfplumber
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpoppler-cpp-dev poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY sample_resumes/ ./sample_resumes/
COPY frontend/ ./frontend/

RUN mkdir -p uploads

EXPOSE 8000

ENV DATABASE_URL=sqlite:///./resume_screener.db

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
