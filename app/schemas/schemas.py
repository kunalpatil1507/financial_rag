from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List
from datetime import datetime
from app.models.document import DocumentType


# ─── Auth / User Schemas ──────────────────────────────────────────────────────

class UserRegister(BaseModel):
    email: EmailStr
    username: str
    password: str
    full_name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str


class UserOut(BaseModel):
    id: int
    email: str
    username: str
    full_name: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Role / Permission Schemas ────────────────────────────────────────────────

class PermissionOut(BaseModel):
    id: int
    name: str
    description: Optional[str]

    class Config:
        from_attributes = True


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    permission_names: List[str] = []


class RoleOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    permissions: List[PermissionOut] = []

    class Config:
        from_attributes = True


class AssignRoleRequest(BaseModel):
    user_id: int
    role_name: str


# ─── Document Schemas ─────────────────────────────────────────────────────────

class DocumentOut(BaseModel):
    id: int
    title: str
    company_name: str
    document_type: DocumentType
    file_name: str
    file_size: Optional[int]
    description: Optional[str]
    uploaded_by: int
    is_indexed: str
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class DocumentSearch(BaseModel):
    title: Optional[str] = None
    company_name: Optional[str] = None
    document_type: Optional[DocumentType] = None
    uploaded_by: Optional[int] = None


# ─── RAG Schemas ──────────────────────────────────────────────────────────────

class SemanticSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    document_type: Optional[DocumentType] = None
    company_name: Optional[str] = None


class ChunkResult(BaseModel):
    document_id: int
    chunk_text: str
    score: float
    chunk_index: int
    document_title: str
    company_name: str
    document_type: str


class SemanticSearchResponse(BaseModel):
    query: str
    results: List[ChunkResult]
    total_results: int


class DocumentContextResponse(BaseModel):
    document_id: int
    title: str
    company_name: str
    document_type: str
    chunks: List[str]
    total_chunks: int
