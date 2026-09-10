"""Structure-aware, token-based document chunking."""

from __future__ import annotations

import hashlib
import re

from app.schemas.rag import ChunkMetadata, DocumentChunk, PageDocument
from app.rag.tokenization import get_tokenizer


NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)[.)]?\s+(.{2,160})$")
TITLE_HEADING = re.compile(r"^(?:section|chapter)\s+\d+.*$", re.IGNORECASE)


def _title_heading(line: str) -> bool:
    words = line.replace("—", " ").split()
    return (
        1 <= len(words) <= 12
        and len(line) <= 160
        and not line.endswith((".", ",", ";", ":"))
        and line[:1].isupper()
        and sum(word[:1].isupper() for word in words if word[:1].isalpha()) >= max(1, len(words) // 2)
    )


def _heading(line: str) -> tuple[str | None, str | None]:
    line = line.strip()
    numbered = NUMBERED_HEADING.match(line)
    if numbered:
        number, title = numbered.groups()
        return (line, None) if number.count(".") == 0 else (None, line)
    if TITLE_HEADING.match(line) or (len(line.split()) <= 9 and line.isupper() and len(line) > 3):
        return line, None
    if _title_heading(line):
        return None, line
    return None, None


def _structured_blocks(page: PageDocument) -> list[tuple[str, str | None, str | None]]:
    section: str | None = None
    subsection: str | None = None
    blocks: list[tuple[str, str | None, str | None]] = []
    body: list[str] = []
    for paragraph in page.text.split("\n\n"):
        first_line = paragraph.splitlines()[0].strip()
        new_section, new_subsection = _heading(first_line)
        if new_section or new_subsection:
            if body:
                blocks.append(("\n\n".join(body), section, subsection))
                body = []
            if new_section:
                section, subsection = new_section, None
            else:
                if section is None:
                    section = new_subsection
                else:
                    subsection = new_subsection
            # Keep a heading with the following content when it has non-heading text.
            remainder = "\n".join(paragraph.splitlines()[1:]).strip()
            if remainder:
                body.append(remainder)
        else:
            body.append(paragraph)
    if body:
        blocks.append(("\n\n".join(body), section, subsection))
    return blocks


def _token_windows(text: str, chunk_size: int, overlap: int) -> list[str]:
    tokenizer = get_tokenizer()
    tokens = tokenizer.encode(text)
    if not tokens:
        return []
    step = chunk_size - overlap
    windows: list[str] = []
    for start in range(0, len(tokens), step):
        window_tokens = tokens[start : start + chunk_size]
        if not window_tokens:
            continue
        text_window = tokenizer.decode(window_tokens).strip()
        # Decoding then re-encoding can change boundary merges for some BPE tokenizers.
        while text_window and len(tokenizer.encode(text_window)) > chunk_size:
            window_tokens = window_tokens[:-1]
            text_window = tokenizer.decode(window_tokens).strip()
        if text_window:
            windows.append(text_window)
    return windows


def chunk_documents(
    pages: list[PageDocument], chunk_size: int, overlap: int, min_chunk_tokens: int = 24
) -> list[DocumentChunk]:
    """Chunk cleaned page text by tokens, retaining the detected section hierarchy."""
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    chunks: list[DocumentChunk] = []
    chunk_index = 0
    tokenizer = get_tokenizer()
    for page in pages:
        for block, section, subsection in _structured_blocks(page):
            prefix = "\n".join(value for value in (section, subsection) if value)
            prefix_tokens = len(tokenizer.encode(prefix)) if prefix else 0
            content_budget = chunk_size - prefix_tokens
            if content_budget < 1:
                continue
            for window in _token_windows(block, content_budget, min(overlap, max(content_budget - 1, 0))):
                text = f"{prefix}\n\n{window}" if prefix else window
                window_tokens = tokenizer.encode(window)
                while window_tokens and len(tokenizer.encode(text)) > chunk_size:
                    window_tokens = window_tokens[:-1]
                    window = tokenizer.decode(window_tokens).strip()
                    text = f"{prefix}\n\n{window}" if prefix else window
                if len(tokenizer.encode(text)) > chunk_size or len(tokenizer.encode(text)) < min_chunk_tokens:
                    continue
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                metadata = ChunkMetadata(
                    document_id=page.document_id,
                    source=page.source,
                    file_path=page.file_path,
                    page=page.page,
                    section=section,
                    subsection=subsection,
                    chunk_index=chunk_index,
                    content_hash=digest,
                    document_version=page.document_version,
                )
                identity = f"{page.document_id}:{page.page}:{chunk_index}:{digest}"
                chunk_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
                chunks.append(DocumentChunk(id=f"chunk_{chunk_id}", text=text, metadata=metadata))
                chunk_index += 1
    return chunks
