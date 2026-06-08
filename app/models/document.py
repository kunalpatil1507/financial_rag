from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.db.database import Base


class DocumentType(str, enum.Enum):
    invoice = "invoice"
    report = "report"
    contract = "contract"
    agreement = "agreement"
    other = "other"


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    company_name = Column(String(255), nullable=False)
    document_type = Column(Enum(DocumentType), nullable=False)
    file_path = Column(String(1000), nullable=False)
    file_name = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=True)  # bytes
    mime_type = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # RAG indexing status
    is_indexed = Column(String(20), default="pending")  # pending, indexed, failed

    uploaded_by_user = relationship("User", back_populates="documents")
