"""
pdf_parser.py — Extract text from PDF and TXT files
"""
import os
import tempfile


def extract_text_from_bytes(file_bytes: bytes, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    try:
        return _extract(tmp_path, ext)
    finally:
        os.unlink(tmp_path)


def _extract(path: str, ext: str) -> str:
    if ext == ".txt":
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    # pdfplumber — best quality
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
        if text.strip():
            return text
    except Exception:
        pass

    # PyPDF2 fallback
    try:
        import PyPDF2
        text = ""
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += (page.extract_text() or "") + "\n"
        return text
    except Exception as e:
        return f"[PDF extraction error: {e}]"
