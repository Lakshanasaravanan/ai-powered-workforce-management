"""Rank-based reciprocal-rank fusion for dense and lexical candidates."""

from app.schemas.rag import RetrievedChunk


def reciprocal_rank_fusion(lists: list[list[RetrievedChunk]], rrf_k: int, limit: int) -> list[RetrievedChunk]:
    merged: dict[str, RetrievedChunk] = {}
    scores: dict[str, float] = {}
    for candidates in lists:
        for rank, candidate in enumerate(candidates, start=1):
            scores[candidate.id] = scores.get(candidate.id, 0.0) + 1.0 / (rrf_k + rank)
            existing = merged.get(candidate.id)
            if existing is None:
                merged[candidate.id] = candidate
            else:
                merged[candidate.id] = existing.model_copy(
                    update={
                        "dense_score": existing.dense_score if existing.dense_score is not None else candidate.dense_score,
                        "sparse_score": existing.sparse_score if existing.sparse_score is not None else candidate.sparse_score,
                    }
                )
    ordered = sorted(merged, key=lambda chunk_id: (-scores[chunk_id], chunk_id))[:limit]
    return [merged[chunk_id].model_copy(update={"fusion_score": scores[chunk_id], "score": scores[chunk_id]}) for chunk_id in ordered]
