from __future__ import annotations

"""
RAG Service
===========
Handles:
  - Text chunking (semantic-aware, with overlap)
  - Embedding generation (sentence-transformers)
  - Vector DB operations (Qdrant)
  - Semantic search with reranking (cross-encoder)
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from app.core.config import settings

logger = logging.getLogger(__name__)

# ─── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class DocumentChunk:
    document_id: int
    chunk_index: int
    text: str
    metadata: Dict[str, Any]


@dataclass
class SearchResult:
    document_id: int
    chunk_index: int
    chunk_text: str
    score: float
    document_title: str
    company_name: str
    document_type: str


# ─── Chunking ─────────────────────────────────────────────────────────────────

class FinancialTextChunker:
    """
    Semantic chunker optimised for financial documents.
    Uses paragraph-aware splitting with a sliding window overlap.
    """

    CHUNK_SIZE = 512      # tokens (approximate via characters / 4)
    CHUNK_OVERLAP = 64    # tokens overlap between consecutive chunks

    # Financial section headers — used as preferred split points
    SECTION_MARKERS = [
        "executive summary", "financial highlights", "balance sheet",
        "income statement", "cash flow", "notes to financial",
        "risk factors", "management discussion", "audit report",
        "revenue", "expenses", "liabilities", "assets",
    ]

    def chunk(self, text: str, document_id: int, metadata: dict) -> List[DocumentChunk]:
        """Split text into semantically meaningful chunks."""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: List[DocumentChunk] = []
        current_tokens: List[str] = []
        current_len = 0
        chunk_idx = 0

        def _flush():
            nonlocal chunk_idx, current_tokens, current_len
            if not current_tokens:
                return
            chunk_text = " ".join(current_tokens).strip()
            if chunk_text:
                chunks.append(
                    DocumentChunk(
                        document_id=document_id,
                        chunk_index=chunk_idx,
                        text=chunk_text,
                        metadata={**metadata, "chunk_index": chunk_idx},
                    )
                )
                chunk_idx += 1
            # Keep overlap
            overlap_tokens = current_tokens[-self.CHUNK_OVERLAP :]
            current_tokens.clear()
            current_tokens.extend(overlap_tokens)
            current_len = len(" ".join(overlap_tokens))

        for para in paragraphs:
            words = para.split()
            para_len = len(words)

            # Force a split at financial section boundaries
            is_section_start = any(
                marker in para.lower() for marker in self.SECTION_MARKERS
            )
            if is_section_start and current_len > self.CHUNK_OVERLAP:
                _flush()

            current_tokens.extend(words)
            current_len += para_len

            if current_len >= self.CHUNK_SIZE:
                _flush()

        _flush()  # final flush
        return chunks


# ─── Embedding Model ──────────────────────────────────────────────────────────

class EmbeddingModel:
    """Wraps sentence-transformers for financial-domain embeddings."""

    _instance: Optional["EmbeddingModel"] = None

    def __init__(self):
        from sentence_transformers import SentenceTransformer

        logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}")
        self.model = SentenceTransformer(settings.EMBEDDING_MODEL)
        self.dimension = self.model.get_sentence_embedding_dimension()
        logger.info(f"Embedding dimension: {self.dimension}")

    @classmethod
    def get(cls) -> "EmbeddingModel":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def embed(self, texts: List[str]) -> List[List[float]]:
        return self.model.encode(texts, convert_to_numpy=True).tolist()

    def embed_one(self, text: str) -> List[float]:
        return self.embed([text])[0]


# ─── Reranker ─────────────────────────────────────────────────────────────────

class FinancialReranker:
    """
    Cross-encoder reranker for financial relevance.
    Falls back to score pass-through if the model is unavailable.
    """

    _instance: Optional["FinancialReranker"] = None
    MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def __init__(self):
        try:
            from sentence_transformers import CrossEncoder

            self.model = CrossEncoder(self.MODEL_NAME)
            self.available = True
            logger.info("Cross-encoder reranker loaded.")
        except Exception as e:
            logger.warning(f"Reranker unavailable: {e}. Using score pass-through.")
            self.model = None
            self.available = False

    @classmethod
    def get(cls) -> "FinancialReranker":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def rerank(self, query: str, results: List[SearchResult], top_k: int = 5) -> List[SearchResult]:
        """Rerank results using the cross-encoder; return top_k."""
        if not self.available or not results:
            return results[:top_k]

        pairs = [(query, r.chunk_text) for r in results]
        scores = self.model.predict(pairs)

        for result, score in zip(results, scores):
            result.score = float(score)

        reranked = sorted(results, key=lambda x: x.score, reverse=True)
        return reranked[:top_k]


# ─── Qdrant Vector Store ──────────────────────────────────────────────────────

class VectorStore:
    """Manages Qdrant operations for financial document chunks."""

    _instance: Optional["VectorStore"] = None

    def __init__(self):
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        self.client = QdrantClient(
            host=settings.QDRANT_HOST, port=settings.QDRANT_PORT
        )
        self.collection = settings.QDRANT_COLLECTION
        self._ensure_collection()

    @classmethod
    def get(cls) -> "VectorStore":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _ensure_collection(self):
        from qdrant_client.models import Distance, VectorParams

        dim = EmbeddingModel.get().dimension
        existing = [c.name for c in self.client.get_collections().collections]
        if self.collection not in existing:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
            logger.info(f"Created Qdrant collection: {self.collection}")

    def upsert_chunks(self, chunks: List[DocumentChunk]):
        """Embed and upsert document chunks into Qdrant."""
        from qdrant_client.models import PointStruct

        texts = [c.text for c in chunks]
        vectors = EmbeddingModel.get().embed(texts)

        points = [
            PointStruct(
                id=self._chunk_id(c.document_id, c.chunk_index),
                vector=vector,
                payload={
                    "document_id": c.document_id,
                    "chunk_index": c.chunk_index,
                    "text": c.text,
                    **c.metadata,
                },
            )
            for c, vector in zip(chunks, vectors)
        ]

        self.client.upsert(collection_name=self.collection, points=points)
        logger.info(f"Upserted {len(points)} chunks for document {chunks[0].document_id}")

    def delete_document(self, document_id: int):
        """Remove all chunks for a given document."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        self.client.delete(
            collection_name=self.collection,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id),
                    )
                ]
            ),
        )
        logger.info(f"Deleted Qdrant vectors for document {document_id}")

    def search(
        self,
        query: str,
        top_k: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Perform cosine similarity search, return top_k raw results."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        query_vector = EmbeddingModel.get().embed_one(query)

        qdrant_filter = None
        if filters:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filters.items()
                if v is not None
            ]
            if conditions:
                qdrant_filter = Filter(must=conditions)

        hits = self.client.search(
            collection_name=self.collection,
            query_vector=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
        )

        results = []
        for hit in hits:
            p = hit.payload
            results.append(
                SearchResult(
                    document_id=p["document_id"],
                    chunk_index=p["chunk_index"],
                    chunk_text=p["text"],
                    score=hit.score,
                    document_title=p.get("title", ""),
                    company_name=p.get("company_name", ""),
                    document_type=p.get("document_type", ""),
                )
            )
        return results

    def get_document_chunks(self, document_id: int) -> List[str]:
        """Retrieve all stored chunks for a document, ordered by index."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        results, _ = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id),
                    )
                ]
            ),
            limit=1000,
            with_payload=True,
        )

        sorted_results = sorted(results, key=lambda p: p.payload.get("chunk_index", 0))
        return [r.payload["text"] for r in sorted_results]

    @staticmethod
    def _chunk_id(document_id: int, chunk_index: int) -> int:
        """Generate a stable unique integer ID for a chunk."""
        return document_id * 100_000 + chunk_index


# ─── RAG Pipeline ─────────────────────────────────────────────────────────────

class RAGPipeline:
    """
    Orchestrates the full RAG pipeline:
      Document → Extract → Chunk → Embed → Qdrant
      Query → Embed → Search (top-20) → Rerank → Top-5
    """

    def __init__(self):
        self.chunker = FinancialTextChunker()
        self.vector_store = VectorStore.get()
        self.reranker = FinancialReranker.get()

    def index_document(
        self,
        document_id: int,
        text: str,
        metadata: dict,
    ) -> int:
        """Process and index a document. Returns chunk count."""
        chunks = self.chunker.chunk(text, document_id, metadata)
        if not chunks:
            raise ValueError("No text could be extracted from document")
        self.vector_store.upsert_chunks(chunks)
        return len(chunks)

    def remove_document(self, document_id: int):
        """Remove all embeddings for a document."""
        self.vector_store.delete_document(document_id)

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """
        Full retrieval pipeline:
          1. Dense vector search (top 20)
          2. Cross-encoder reranking (top_k)
        """
        raw_results = self.vector_store.search(query, top_k=20, filters=filters)
        if not raw_results:
            return []
        return self.reranker.rerank(query, raw_results, top_k=top_k)

    def get_document_context(self, document_id: int) -> List[str]:
        return self.vector_store.get_document_chunks(document_id)


# Singleton
_pipeline: Optional[RAGPipeline] = None


def get_rag_pipeline() -> RAGPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = RAGPipeline()
    return _pipeline
