"""Implement fixed-size and structure-aware (paragraph-based) chunking."""
from __future__ import annotations

import re
from .models import Chunk, DocumentPage


def fixed_size(page: DocumentPage, size: int = 500, overlap: int = 50) -> list[Chunk]:
    """Split page text into fixed-size character windows with overlap and retain page metadata."""
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must satisfy 0 <= overlap < size")

    text = page.text
    if not text.strip():
        return []

    step = size - overlap
    chunks: list[Chunk] = []
    idx = 0
    for start in range(0, len(text), step):
        window = text[start : start + size]
        if not window.strip():
            continue
        chunk_id = f"{page.document_id}_p{page.page:03d}_fixed_{idx:02d}"
        meta = dict(page.metadata)
        meta.update({
            "chunk_index": idx,
            "chunking_method": "fixed_size",
            "char_start": start,
            "char_end": min(len(text), start + size),
            "chunk_char_len": len(window),
        })
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                document_id=page.document_id,
                source=page.source,
                page=page.page,
                text=window,
                metadata=meta,
            )
        )
        idx += 1
        if start + size >= len(text):
            break

    return chunks


def _split_oversized_paragraph(paragraph: str, max_size: int) -> list[str]:
    """Split an oversized paragraph along sentence boundaries when possible, falling back to max_size windows."""
    if len(paragraph) <= max_size:
        return [paragraph]

    sentences = re.split(r"(?<=[.!?…”\"])\s+", paragraph)
    pieces: list[str] = []
    current = ""
    for sent in sentences:
        if not sent:
            continue
        if not current:
            if len(sent) <= max_size:
                current = sent
            else:
                for i in range(0, len(sent), max_size):
                    pieces.append(sent[i : i + max_size])
        elif len(current) + 1 + len(sent) <= max_size:
            current = f"{current} {sent}"
        else:
            pieces.append(current)
            if len(sent) <= max_size:
                current = sent
            else:
                for i in range(0, len(sent), max_size):
                    pieces.append(sent[i : i + max_size])
                current = ""
    if current:
        pieces.append(current)
    return pieces


def by_paragraph(page: DocumentPage, max_size: int = 900) -> list[Chunk]:
    """Group whole paragraphs up to max_size, split oversized paragraphs cleanly, and retain metadata."""
    if max_size <= 0:
        raise ValueError("max_size must be positive")

    raw_paragraphs = [p.strip() for p in page.text.split("\n\n") if p.strip()]
    if not raw_paragraphs:
        return []

    units: list[str] = []
    for para in raw_paragraphs:
        units.extend(_split_oversized_paragraph(para, max_size))

    grouped_texts: list[str] = []
    current = ""
    for unit in units:
        if not current:
            current = unit
        elif len(current) + 2 + len(unit) <= max_size:
            current = f"{current}\n\n{unit}"
        else:
            grouped_texts.append(current)
            current = unit
    if current:
        grouped_texts.append(current)

    chunks: list[Chunk] = []
    cursor = 0
    for idx, chunk_text in enumerate(grouped_texts):
        pos = page.text.find(chunk_text[:40], cursor)
        char_start = pos if pos != -1 else cursor
        char_end = char_start + len(chunk_text)
        cursor = max(cursor, char_start)

        chunk_id = f"{page.document_id}_p{page.page:03d}_para_{idx:02d}"
        meta = dict(page.metadata)
        meta.update({
            "chunk_index": idx,
            "chunking_method": "by_paragraph",
            "char_start": char_start,
            "char_end": char_end,
            "chunk_char_len": len(chunk_text),
        })
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                document_id=page.document_id,
                source=page.source,
                page=page.page,
                text=chunk_text,
                metadata=meta,
            )
        )

    return chunks
