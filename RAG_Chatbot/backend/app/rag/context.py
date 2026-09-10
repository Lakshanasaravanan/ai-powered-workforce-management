"""Bounded, provenance-preserving context assembly."""

from __future__ import annotations

import hashlib

from app.schemas.rag import RetrievedChunk, SourceCitation
from app.rag.tokenization import get_tokenizer


def source_citations(chunks: list[RetrievedChunk]) -> list[SourceCitation]:
    seen: set[tuple[str, int, str | None, str | None]] = set()
    sources: list[SourceCitation] = []
    for chunk in chunks:
        key = (chunk.metadata.source, chunk.metadata.page, chunk.metadata.section, chunk.metadata.subsection)
        if key not in seen:
            seen.add(key)
            sources.append(
                SourceCitation(
                    document=chunk.metadata.source,
                    page=chunk.metadata.page,
                    section=chunk.metadata.section,
                    subsection=chunk.metadata.subsection,
                )
            )
    return sources


class ContextAssembler:
    def __init__(self, max_tokens: int) -> None:
        self.max_tokens = max_tokens

    def assemble(self, chunks: list[RetrievedChunk]) -> tuple[str, list[SourceCitation]]:
        """De-duplicate exact content and keep a bounded set of clearly labeled evidence."""
        used_tokens = 0
        tokenizer = get_tokenizer()
        seen_content: set[str] = set()
        accepted: list[RetrievedChunk] = []
        sections: list[str] = []
        for rank, chunk in enumerate(chunks, start=1):
            fingerprint = hashlib.sha256(" ".join(chunk.text.split()).encode("utf-8")).hexdigest()
            if fingerprint in seen_content:
                continue
            seen_content.add(fingerprint)
            labels = [
                f"[Source {rank}]",
                f"Document: {chunk.metadata.source}",
                f"Page: {chunk.metadata.page}",
            ]
            if chunk.metadata.section:
                labels.append(f"Section: {chunk.metadata.section}")
            if chunk.metadata.subsection:
                labels.append(f"Subsection: {chunk.metadata.subsection}")
            candidate = "\n".join(labels) + f"\n\n{chunk.text.strip()}"
            candidate_tokens = len(tokenizer.encode(candidate))
            remaining = self.max_tokens - used_tokens
            if remaining <= 0:
                break
            if candidate_tokens > remaining:
                candidate = tokenizer.decode(tokenizer.encode(candidate)[:remaining]).strip()
                candidate_tokens = len(tokenizer.encode(candidate))
            sections.append(candidate)
            accepted.append(chunk)
            used_tokens += candidate_tokens
            if used_tokens >= self.max_tokens:
                break
        return "\n\n---\n\n".join(sections), source_citations(accepted)
