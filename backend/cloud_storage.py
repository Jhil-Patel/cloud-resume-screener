"""
cloud_storage.py — AWS S3 upload with local fallback
"""
import os
import uuid
from datetime import datetime, timezone

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _s3_configured() -> bool:
    return bool(
        os.getenv("AWS_ACCESS_KEY_ID") and
        os.getenv("AWS_SECRET_ACCESS_KEY") and
        os.getenv("S3_BUCKET_NAME")
    )


def _get_s3():
    try:
        import boto3
        return boto3.client(
            "s3",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("AWS_REGION", "us-east-1"),
        )
    except ImportError:
        return None


def upload_file(file_bytes: bytes, filename: str) -> dict:
    """Upload file — returns storage metadata."""
    uid = uuid.uuid4().hex[:8]
    safe = f"{uid}_{filename.replace(' ', '_')}"
    ts   = datetime.now(timezone.utc).isoformat()

    if _s3_configured():
        try:
            s3     = _get_s3()
            bucket = os.getenv("S3_BUCKET_NAME")
            key    = f"resumes/{safe}"
            s3.put_object(
                Bucket=bucket, Key=key, Body=file_bytes,
                ContentType="application/pdf",
                Metadata={"original-name": filename, "uploaded-at": ts}
            )
            url = f"https://{bucket}.s3.amazonaws.com/{key}"
            return {"storage_type": "s3", "storage_path": url, "key": key}
        except Exception as e:
            print(f"S3 upload failed: {e}, falling back to local")

    # Local fallback
    path = os.path.join(UPLOAD_DIR, safe)
    with open(path, "wb") as f:
        f.write(file_bytes)
    return {"storage_type": "local", "storage_path": path}


def get_storage_status() -> dict:
    s3_ok = _s3_configured()
    local_files = len([f for f in os.listdir(UPLOAD_DIR) if not f.endswith('.json')])
    return {
        "s3_configured": s3_ok,
        "storage_mode": "AWS S3" if s3_ok else "Local (SQLite)",
        "bucket": os.getenv("S3_BUCKET_NAME", "Not configured"),
        "local_files": local_files,
    }
