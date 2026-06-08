import os
import uuid
from pathlib import Path
from typing import Tuple

from fastapi import UploadFile, HTTPException
from app.core.config import settings


ALLOWED_MIME_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
    "application/msword": ".doc",
}


def get_upload_dir() -> Path:
    upload_path = Path(settings.UPLOAD_DIR)
    upload_path.mkdir(parents=True, exist_ok=True)
    return upload_path


async def save_upload_file(file: UploadFile) -> Tuple[str, str, int]:
    """
    Save an uploaded file to disk.
    Returns (file_path, original_filename, file_size_bytes).
    """
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. "
                   f"Allowed: PDF, DOCX, TXT",
        )

    ext = ALLOWED_MIME_TYPES[file.content_type]
    unique_name = f"{uuid.uuid4().hex}{ext}"
    dest = get_upload_dir() / unique_name

    content = await file.read()
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max allowed: {settings.MAX_FILE_SIZE_MB} MB",
        )

    with open(dest, "wb") as f:
        f.write(content)

    return str(dest), file.filename, len(content)


def delete_file(file_path: str) -> None:
    """Remove a file from disk if it exists."""
    try:
        os.remove(file_path)
    except FileNotFoundError:
        pass


def extract_text_from_file(file_path: str, mime_type: str) -> str:
    """
    Extract raw text from a document file.
    Supports PDF, DOCX, and plain text.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if mime_type == "application/pdf":
        return _extract_pdf(file_path)
    elif mime_type in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ):
        return _extract_docx(file_path)
    else:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()


def _extract_pdf(file_path: str) -> str:
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text.strip())
    return "\n\n".join(pages)


def _extract_docx(file_path: str) -> str:
    from docx import Document

    doc = Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)
