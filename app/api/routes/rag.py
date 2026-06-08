
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.orm import Session
from typing import Optional

from app.db.database import get_db
from app.models.document import Document
from app.models.user import User
from app.schemas.schemas import (
    SemanticSearchRequest,
    SemanticSearchResponse,
    ChunkResult,
    DocumentContextResponse,
)
from app.core.security import get_current_user
from app.services.document_service import extract_text_from_file
from app.services.rag_service import get_rag_pipeline

router = APIRouter(prefix="/rag", tags=["RAG / Semantic Search"])


@router.post("/index-document", status_code=status.HTTP_202_ACCEPTED)
def index_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate embeddings for a document and store them in the vector DB.
    Indexing runs as a background task to avoid blocking the response.
    """
    doc = _get_doc_or_404(db, document_id)
    _check_index_permission(current_user, doc)

    doc.is_indexed = "processing"
    db.commit()

    background_tasks.add_task(_run_indexing, document_id, db)
    return {"message": "Indexing started", "document_id": document_id}


def _run_indexing(document_id: int, db: Session):
    """Background task: extract text, chunk, embed, store."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        return

    try:
        text = extract_text_from_file(doc.file_path, doc.mime_type)
        if not text.strip():
            raise ValueError("Document contains no extractable text")

        metadata = {
            "title": doc.title,
            "company_name": doc.company_name,
            "document_type": doc.document_type.value,
            "uploaded_by": doc.uploaded_by,
        }

        pipeline = get_rag_pipeline()
        chunk_count = pipeline.index_document(document_id, text, metadata)

        doc.is_indexed = "indexed"
        db.commit()
    except Exception as e:
        doc.is_indexed = "failed"
        db.commit()
        raise e


@router.delete("/remove-document/{document_id}", status_code=status.HTTP_200_OK)
def remove_document_embeddings(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove all embeddings for a document from the vector DB."""
    doc = _get_doc_or_404(db, document_id)
    _check_index_permission(current_user, doc)

    pipeline = get_rag_pipeline()
    pipeline.remove_document(document_id)

    doc.is_indexed = "pending"
    db.commit()
    return {"message": f"Embeddings removed for document {document_id}"}


@router.post("/search", response_model=SemanticSearchResponse)
def semantic_search(
    request: SemanticSearchRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Perform semantic search over financial documents.

    Pipeline:
      Query → Embedding → Vector Search (top-20) → Reranking → Top-k Results

    Example body:
    ```json
    {
      "query": "financial risk related to high debt ratio",
      "top_k": 5
    }
    ```
    """
    filters = {}
    if request.document_type:
        filters["document_type"] = request.document_type.value
    if request.company_name:
        filters["company_name"] = request.company_name

    pipeline = get_rag_pipeline()
    raw_results = pipeline.search(
        query=request.query,
        top_k=request.top_k,
        filters=filters if filters else None,
    )

    chunk_results = [
        ChunkResult(
            document_id=r.document_id,
            chunk_text=r.chunk_text,
            score=round(r.score, 4),
            chunk_index=r.chunk_index,
            document_title=r.document_title,
            company_name=r.company_name,
            document_type=r.document_type,
        )
        for r in raw_results
    ]

    return SemanticSearchResponse(
        query=request.query,
        results=chunk_results,
        total_results=len(chunk_results),
    )


@router.get("/context/{document_id}", response_model=DocumentContextResponse)
def get_document_context(
    document_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Retrieve all stored vector chunks for a document.
    Useful for inspecting what was indexed.
    """
    doc = _get_doc_or_404(db, document_id)
    if doc.is_indexed != "indexed":
        raise HTTPException(
            status_code=400,
            detail=f"Document is not indexed (status: {doc.is_indexed}). "
                   f"Use POST /rag/index-document first.",
        )

    pipeline = get_rag_pipeline()
    chunks = pipeline.get_document_context(document_id)

    return DocumentContextResponse(
        document_id=doc.id,
        title=doc.title,
        company_name=doc.company_name,
        document_type=doc.document_type.value,
        chunks=chunks,
        total_chunks=len(chunks),
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_doc_or_404(db: Session, document_id: int) -> Document:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


def _check_index_permission(user: User, doc: Document):
    role_names = {r.name for r in user.roles}
    perm_names = {p.name for r in user.roles for p in r.permissions}
    if (
        "Admin" not in role_names
        and "documents:index" not in perm_names
        and doc.uploaded_by != user.id
    ):
        raise HTTPException(status_code=403, detail="Not authorized to index this document")
