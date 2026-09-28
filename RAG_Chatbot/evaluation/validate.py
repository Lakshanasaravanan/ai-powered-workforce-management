"""Static validation for the independently labeled Phase 21 benchmark."""
from __future__ import annotations

from collections.abc import Iterable

VALID_DIFFICULTIES = {"direct", "medium", "hard"}
VALID_TYPES = {"direct", "paraphrase", "typo_robustness", "hard_negative", "multi_document", "unanswerable"}


def validate(cases: Iterable[dict], records: dict[str, dict]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    corpus_sources = {item["metadata"]["source"] for item in records.values()}
    for item in cases:
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            errors.append(f"invalid or duplicate id: {identifier!r}")
        seen.add(identifier)
        if not isinstance(item.get("question"), str) or not item["question"].strip():
            errors.append(f"{identifier}: blank question")
        if not isinstance(item.get("category"), str) or not item["category"].strip():
            errors.append(f"{identifier}: missing category")
        if item.get("difficulty") not in VALID_DIFFICULTIES:
            errors.append(f"{identifier}: invalid difficulty")
        if item.get("question_type") not in VALID_TYPES:
            errors.append(f"{identifier}: invalid question type")
        answerable = item.get("answerable") is True
        chunks = item.get("relevant_chunk_ids", [])
        documents = item.get("relevant_documents", [])
        pages = item.get("relevant_pages", [])
        if answerable and (not chunks or not documents or not pages):
            errors.append(f"{identifier}: answerable item has no evidence")
        if not answerable and (chunks or documents or pages):
            errors.append(f"{identifier}: unanswerable item has evidence")
        for document in documents:
            if document not in corpus_sources:
                errors.append(f"{identifier}: document outside corpus")
        for chunk_id in chunks:
            record = records.get(chunk_id)
            if record is None:
                errors.append(f"{identifier}: invalid chunk identifier")
            elif record["metadata"]["source"] not in documents or record["metadata"]["page"] not in pages:
                errors.append(f"{identifier}: chunk metadata does not match label")
    return errors
