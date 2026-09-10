"""Deterministic cleanup for common, non-semantic PDF extraction artifacts."""

from __future__ import annotations

import re
from collections import Counter

from app.schemas.rag import PageDocument


PAGE_NUMBER = re.compile(r"^(?:page\s+)?\d+(?:\s+of\s+\d+)?$", re.IGNORECASE)
MULTI_SPACE = re.compile(r"[ \t]+")


def _normalise_line(line: str) -> str:
    return MULTI_SPACE.sub(" ", line).strip()


def _looks_like_heading(line: str) -> bool:
    """Conservatively retain short title lines as their own structural paragraph."""
    words = line.replace("—", " ").split()
    return (
        1 <= len(words) <= 12
        and len(line) <= 160
        and not line.endswith((".", ",", ";", ":"))
        and line[:1].isupper()
        and sum(word[:1].isupper() for word in words if word[:1].isalpha()) >= max(1, len(words) // 2)
    )


def clean_text(text: str, repeated_lines: set[str] | None = None) -> str:
    """Preserve paragraph boundaries while removing extraction-only spacing artifacts."""
    repeated_lines = repeated_lines or set()
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs: list[str] = []
    for raw_paragraph in re.split(r"\n\s*\n+", text):
        lines = [_normalise_line(line) for line in raw_paragraph.split("\n")]
        lines = [line for line in lines if line and line not in repeated_lines and not PAGE_NUMBER.match(line)]
        body: list[str] = []
        for line in lines:
            if _looks_like_heading(line):
                if body:
                    paragraphs.append(" ".join(body))
                    body = []
                paragraphs.append(line)
            else:
                body.append(line)
        if body:
            # Join wrapped visual lines inside a paragraph, retaining semantic paragraph breaks.
            paragraphs.append(" ".join(body))
    return "\n\n".join(paragraphs)


def _repeated_margin_lines(pages: list[PageDocument]) -> set[str]:
    """Detect repeated first/last lines, avoiding removal of ordinary body text."""
    candidates: Counter[str] = Counter()
    for page in pages:
        lines = [_normalise_line(line) for line in page.text.splitlines() if _normalise_line(line)]
        if lines:
            candidates[lines[0]] += 1
            if len(lines) > 1:
                candidates[lines[-1]] += 1
    return {line for line, count in candidates.items() if count >= 2 and len(line) <= 160}


def clean_documents(pages: list[PageDocument]) -> list[PageDocument]:
    """Clean a document batch while preserving page-level provenance."""
    by_document: dict[str, list[PageDocument]] = {}
    for page in pages:
        by_document.setdefault(page.document_id, []).append(page)

    cleaned: list[PageDocument] = []
    for document_pages in by_document.values():
        repeated_lines = _repeated_margin_lines(document_pages)
        for page in document_pages:
            text = clean_text(page.text, repeated_lines)
            if text:
                cleaned.append(page.model_copy(update={"text": text}))
    return cleaned
