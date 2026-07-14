import os
import re
from pathlib import Path

from google.cloud import storage


GCS_BUCKET = os.getenv("GCS_BUCKET")

# This remains as a fallback for local development when GCS_BUCKET is not set.
LOCAL_UPLOAD_DIR = Path("uploads")
LOCAL_UPLOAD_DIR.mkdir(exist_ok=True)

_storage_client = storage.Client() if GCS_BUCKET else None


def _safe_filename(filename: str) -> str:
    """Remove directory components and unsafe filename characters."""
    basename = filename.replace("\\", "/").split("/")[-1]
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", basename)
    return cleaned or "upload.bin"


def save_upload(
    case_id: int,
    item_id: int,
    filename: str,
    content: bytes,
    content_type: str | None = None,
) -> str:
    """
    Save an uploaded document.

    In GCP, files are saved to Cloud Storage.
    During local development, files fall back to the local uploads directory.
    """
    safe_name = f"{item_id}_{_safe_filename(filename)}"

    if GCS_BUCKET:
        object_name = f"cases/{case_id}/{safe_name}"

        bucket = _storage_client.bucket(GCS_BUCKET)
        blob = bucket.blob(object_name)

        blob.upload_from_string(
            content,
            content_type=content_type or "application/octet-stream",
        )

        return f"gs://{GCS_BUCKET}/{object_name}"

    case_dir = LOCAL_UPLOAD_DIR / str(case_id)
    case_dir.mkdir(parents=True, exist_ok=True)

    file_path = case_dir / safe_name
    file_path.write_bytes(content)

    return str(file_path)
