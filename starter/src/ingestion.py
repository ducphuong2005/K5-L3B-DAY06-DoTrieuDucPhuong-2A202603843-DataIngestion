"""Read and normalize source data while preserving source/page traceability and logging anomalies."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from .models import DocumentPage

CHAPTER_HEADINGS: dict[str, tuple[str, str]] = {
    "CHAPTER ONE": ("chapter_1", "CHAPTER ONE: THE BOY WHO LIVED"),
    "CHAPTER TWO": ("chapter_2", "CHAPTER TWO: THE VANISHING GLASS"),
    "CHAPTER THREE": ("chapter_3", "CHAPTER THREE: THE LETTERS FROM NO ONE"),
    "CHAPTER FOUR": ("chapter_4", "CHAPTER FOUR: THE KEEPER OF THE KEYS"),
}


def normalize_text(text: str) -> str:
    """Normalize Unicode (NFC), clean PDF horizontal tab word-spacing, rejoin drop-caps, and preserve paragraphs."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFC", text)
    norm = norm.replace("\r\n", "\n").replace("\r", "\n")
    norm = norm.replace("\t", " ")
    # Rejoin detached drop-cap letter if raw extract_text() was passed directly
    norm = re.sub(
        r"^([A-Z])\s*\n+\s*(CHAPTER\s+[A-Z]+)\s*\n+\s*([^\n]+)\s*\n+\s*([a-zA-Z])",
        r"\2\n\n\3\n\n\1\4",
        norm.strip(),
    )
    lines = [re.sub(r" +", " ", line).strip() for line in norm.split("\n")]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_structured_page_text(page: Any) -> str:
    """Extract page text using PDF text-matrix coordinates to preserve true paragraph breaks and drop-caps."""
    items: list[tuple[float, float, float, str]] = []

    def visitor(text: str, cm: Any, tm: Any, font_dict: Any, font_size: float) -> None:
        t = text.strip()
        if t:
            items.append((round(float(tm[4]), 1), round(float(tm[5]), 1), round(float(font_size), 1), t))

    page.extract_text(visitor_text=visitor)
    if not items:
        return ""

    drop_cap = ""
    paragraphs: list[str] = []
    current: list[str] = []
    prev_y: float | None = None

    for x, y, fs, raw_line in items:
        t_clean = unicodedata.normalize("NFC", re.sub(r"[\t ]+", " ", raw_line).strip())
        if fs >= 50.0 and len(t_clean) == 1:
            drop_cap = t_clean
            continue
        if fs != 20.0:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            paragraphs.append(t_clean)
            prev_y = None
            continue
        if drop_cap:
            t_clean = drop_cap + t_clean
            drop_cap = ""
            if current:
                paragraphs.append(" ".join(current))
                current = []
            current.append(t_clean)
            prev_y = y
            continue
        is_new_para = prev_y is not None and (y - prev_y > 32.0 or abs(x - 20.0) < 3.0)
        if is_new_para and current:
            paragraphs.append(" ".join(current))
            current = [t_clean]
        else:
            current.append(t_clean)
        prev_y = y

    if current:
        paragraphs.append(" ".join(current))

    return normalize_text("\n\n".join(paragraphs))


def load_pdf(
    path: Path,
    document_id: str,
    source: str,
    max_physical_page: int = 61,
    log_out: list[dict[str, Any]] | None = None,
) -> list[DocumentPage]:
    """Extract physical pages from PDF, filter and log empty/front-matter pages, and attach chapter metadata."""
    reader = PdfReader(str(path))
    limit = min(len(reader.pages), max_physical_page)

    pages: list[DocumentPage] = []
    current_section = "front_matter"
    current_chapter_title = "FRONT MATTER"

    for page_num in range(1, limit + 1):
        pdf_page = reader.pages[page_num - 1]
        raw_text = pdf_page.extract_text() or ""
        structured_text = _extract_structured_page_text(pdf_page)

        # Detect chapter transitions from heading text on the page
        for heading_prefix, (sec_id, sec_title) in CHAPTER_HEADINGS.items():
            if heading_prefix in structured_text and page_num >= 12:
                current_section = sec_id
                current_chapter_title = sec_title
                break

        if len( structured_text) == 0:
            if log_out is not None:
                log_out.append({
                    "document_id": document_id,
                    "source": source,
                    "page": page_num,
                    "status": "excluded",
                    "reason": "empty_or_image_only_cover_page",
                    "raw_char_count": len(raw_text),
                    "normalized_char_count": 0,
                })
            continue

        if page_num <= 11 or "CONTENTS" in structured_text[:40]:
            reason = "table_of_contents" if ("CONTENTS" in structured_text or page_num == 11) else "dedication_page_under_200_chars"
            if log_out is not None:
                log_out.append({
                    "document_id": document_id,
                    "source": source,
                    "page": page_num,
                    "status": "excluded",
                    "reason": reason,
                    "raw_char_count": len(raw_text),
                    "normalized_char_count": len(structured_text),
                })
            continue

        metadata = {
            "page_id": f"{document_id}_p{page_num:03d}",
            "section": current_section,
            "chapter_title": current_chapter_title,
            "book_number": 1,
            "language": "en",
            "char_count": len(structured_text),
        }
        pages.append(
            DocumentPage(
                document_id=document_id,
                source=source,
                page=page_num,
                text=structured_text,
                metadata=metadata,
            )
        )
        if log_out is not None:
            log_out.append({
                "document_id": document_id,
                "source": source,
                "page": page_num,
                "status": "valid_content_page",
                "section": current_section,
                "raw_char_count": len(raw_text),
                "normalized_char_count": len(structured_text),
            })

    return pages
