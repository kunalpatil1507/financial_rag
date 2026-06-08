from typing import List, Optional, Dict, Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as rest

from app.core.config import settings


def get_client() -> QdrantClient:
    return QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)


def ensure_collection(client: QdrantClient, collection_name: str, vector_size: int):
    existing = client.get_collections().collections
    names = [c.name for c in existing]
    if collection_name in names:
        return

    client.recreate_collection(
        collection_name=collection_name,
        vectors_config=rest.VectorParams(size=vector_size, distance=rest.Distance.COSINE),
        optimizers_config=rest.OptimizersConfig(deleted_threshold=0.2),
    )


def upsert_points(client: QdrantClient, collection_name: str, points: List[Dict[str, Any]]):
    # points: list of {"id": str/int, "vector": [...], "payload": {...}}
    client.upsert(collection_name=collection_name, points=points)


def search_vectors(
    client: QdrantClient,
    collection_name: str,
    query_vector,
    top: int = 10,
    query_filter: Optional[rest.Filter] = None,
):
    return client.search(
        collection_name=collection_name,
        query_vector=query_vector,
        limit=top,
        query_filter=query_filter,
    )
