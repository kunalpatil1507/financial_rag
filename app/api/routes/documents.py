from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.database import get_db
from app.models.document import Document, DocumentType
from app.models.user import User
from app.schemas.schemas import DocumentOut, DocumentSearch
from app.core.security import get_current_user, require_permission
from app.services.document_service import save_upload_file, delete_file

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/upload", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    title: str = Form(...),
    company_name: str = Form(...),
    document_type: DocumentType = Form(...),
    description: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a financial document (PDF, DOCX, or TXT).
    Requires: 'documents:upload' permission.
    """
    _check_upload_permission(current_user)

    file_path, original_name, file_size = await save_upload_file(file)

    doc = Document(
        title=title,
        company_name=company_name,
        document_type=document_type,
        description=description,
        file_path=file_path,
        file_name=original_name,
        file_size=file_size,
        mime_type=file.content_type,
        uploaded_by=current_user.id,
        is_indexed="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.get("", response_model=List[DocumentOut])
def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve all documents (with pagination)."""
    role_names = {r.name for r in current_user.roles}

    # Clients only see their own company documents
    if "Client" in role_names and "Admin" not in role_names:
        # A real system would filter by user's company_name stored on the user model
        # For now, clients can see all — refine when user profile is extended
        pass

    return db.query(Document).offset(skip).limit(limit).all()


@router.get("/search", response_model=List[DocumentOut])
def search_documents_by_metadata(
    title: Optional[str] = Query(None),
    company_name: Optional[str] = Query(None),
    document_type: Optional[DocumentType] = Query(None),
    uploaded_by: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Search documents by metadata fields."""
    q = db.query(Document)
    if title:
        q = q.filter(Document.title.ilike(f"%{title}%"))
    if company_name:
        q = q.filter(Document.company_name.ilike(f"%{company_name}%"))
    if document_type:
        q = q.filter(Document.document_type == document_type)
    if uploaded_by:
        q = q.filter(Document.uploaded_by == uploaded_by)
    return q.all()


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Retrieve a single document's details."""
    doc = _get_doc_or_404(db, document_id)
    return doc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a document and its file from disk.
    Requires: 'documents:delete' permission or document ownership.
    """
    doc = _get_doc_or_404(db, document_id)

    role_names = {r.name for r in current_user.roles}
    perm_names = {p.name for r in current_user.roles for p in r.permissions}

    if (
        "Admin" not in role_names
        and "documents:delete" not in perm_names
        and doc.uploaded_by != current_user.id
    ):
        raise HTTPException(status_code=403, detail="Not authorized to delete this document")

    delete_file(doc.file_path)
    db.delete(doc)
    db.commit()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_doc_or_404(db: Session, document_id: int) -> Document:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


def _check_upload_permission(user: User):
    role_names = {r.name for r in user.roles}
    perm_names = {p.name for r in user.roles for p in r.permissions}
    if (
        "Admin" not in role_names
        and "Analyst" not in role_names
        and "documents:upload" not in perm_names
    ):
        raise HTTPException(status_code=403, detail="Upload permission required")
