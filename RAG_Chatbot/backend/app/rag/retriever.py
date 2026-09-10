"""Dense retrieval backed only by the VectorStore interface."""

from app.rag.embeddings import EmbeddingService
from app.schemas.rag import MetadataFilter, RetrievedChunk
from app.services.vector_store import VectorStore


class DenseRetriever:
    def __init__(self, vector_store: VectorStore, embeddings: EmbeddingService, top_k: int) -> None:
        self.vector_store = vector_store
        self.embeddings = embeddings
        self.top_k = top_k

    def retrieve(
        self, query: str, top_k: int | None = None, metadata_filter: MetadataFilter | None = None
    ) -> list[RetrievedChunk]:
        if not query.strip() or self.vector_store.count() == 0:
            return []
        return self.retrieve_vector(self.embeddings.encode([query])[0], top_k, metadata_filter)

    def retrieve_vector(
        self, query_vector, top_k: int | None = None, metadata_filter: MetadataFilter | None = None
    ) -> list[RetrievedChunk]:
        if self.vector_store.count() == 0:
            return []
        limit = top_k or self.top_k
        candidates = self.vector_store.search(query_vector, min(self.vector_store.count(), limit * 5), metadata_filter)
        unique: list[RetrievedChunk] = []
        seen_content: set[str] = set()
        for candidate in candidates:
            if candidate.metadata.content_hash in seen_content:
                continue
            seen_content.add(candidate.metadata.content_hash)
            unique.append(candidate)
            if len(unique) == limit:
                break
        return unique
