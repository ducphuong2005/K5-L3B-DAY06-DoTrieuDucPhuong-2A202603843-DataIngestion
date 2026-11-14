"""Evaluate retrieved evidence and preserve per-query traces."""
from __future__ import annotations

import re
import unicodedata
from typing import Any


def _clean_for_match(text: str) -> str:
    norm = unicodedata.normalize("NFC", text or "")
    norm = re.sub(r"\s+", " ", norm).strip()
    return norm


def _is_evidence_hit(hit: dict[str, Any], question: dict[str, Any]) -> bool:
    """Return True if hit comes from gold source + gold page and contains the full gold evidence quote."""
    gold_source = question["gold_source_id"]
    gold_page = int(question["gold_page"])

    hit_doc = hit.get("document_id") or hit.get("metadata", {}).get("document_id")
    hit_source = hit.get("source") or hit.get("metadata", {}).get("source")
    hit_page = int(hit.get("page") or hit.get("metadata", {}).get("page") or -1)

    source_ok = (hit_doc == gold_source) or (hit_source == gold_source)
    page_ok = hit_page == gold_page
    if not (source_ok and page_ok):
        return False

    chunk_text_clean = _clean_for_match(hit.get("text", ""))
    valid_quotes = [question["evidence_quote"]]
    if question.get("alternative_evidence_quotes"):
        valid_quotes.extend(question["alternative_evidence_quotes"])

    for quote in valid_quotes:
        if _clean_for_match(quote) in chunk_text_clean:
            return True
    return False


def _is_page_only_hit(hit: dict[str, Any], question: dict[str, Any]) -> bool:
    """Return True if hit matches gold source and gold page (used to detect split-evidence errors)."""
    gold_source = question["gold_source_id"]
    gold_page = int(question["gold_page"])
    hit_doc = hit.get("document_id") or hit.get("metadata", {}).get("document_id")
    hit_source = hit.get("source") or hit.get("metadata", {}).get("source")
    hit_page = int(hit.get("page") or hit.get("metadata", {}).get("page") or -1)
    return ((hit_doc == gold_source) or (hit_source == gold_source)) and (hit_page == gold_page)


def _check_metadata_valid(hit: dict[str, Any]) -> bool:
    meta = hit.get("metadata") or {}
    doc_id = hit.get("document_id") or meta.get("document_id")
    source = hit.get("source") or meta.get("source")
    page = hit.get("page") or meta.get("page")
    section = meta.get("section")
    return bool(doc_id and source and isinstance(page, int) and page >= 12 and section in {
        "chapter_1", "chapter_2", "chapter_3", "chapter_4"
    })


def _check_filter_compliant(hit: dict[str, Any], q_filter: dict[str, Any] | None) -> bool:
    if not q_filter:
        return True
    meta = hit.get("metadata") or {}
    for k, v in q_filter.items():
        if str(meta.get(k)) != str(v):
            return False
    return True


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Check source/page and enough gold evidence; keep hit@1, evidence_hit@3, and full top-3 trace."""
    top3 = hits[:3]
    hit_flags = [_is_evidence_hit(h, question) for h in top3]
    page_flags = [_is_page_only_hit(h, question) for h in top3]
    meta_valid_flags = [_check_metadata_valid(h) for h in top3]
    q_filter = question.get("filter")
    filter_flags = [_check_filter_compliant(h, q_filter) for h in top3]

    hit_at_1 = bool(hit_flags[0]) if hit_flags else False
    evidence_hit_at_3 = any(hit_flags)
    page_hit_at_3 = any(page_flags)

    # Check if the gold page was retrieved in top-3, or if joining top-3 chunks from the gold page reconstructs the quote
    combined_gold_page_text = _clean_for_match(
        " ".join(h.get("text", "") for h, pf in zip(top3, page_flags) if pf)
    )
    quote_clean = _clean_for_match(question["evidence_quote"])
    evidence_split_across_chunks = (not evidence_hit_at_3) and page_hit_at_3

    annotated_hits: list[dict[str, Any]] = []
    for idx, h in enumerate(top3):
        annotated_hits.append({
            "rank": idx + 1,
            "chunk_id": h.get("chunk_id"),
            "document_id": h.get("document_id"),
            "source": h.get("source"),
            "page": h.get("page"),
            "score": h.get("score"),
            "cosine_distance": h.get("cosine_distance"),
            "metadata": h.get("metadata"),
            "is_evidence_hit": hit_flags[idx],
            "is_gold_page_hit": page_flags[idx],
            "metadata_complete_and_valid": meta_valid_flags[idx],
            "filter_compliant": filter_flags[idx],
            "text": h.get("text"),
        })

    return {
        "question_id": question["id"],
        "split": question["split"],
        "type": question.get("type", "unknown"),
        "question": question["question"],
        "expected_answer": question["expected_answer"],
        "gold_source_id": question["gold_source_id"],
        "gold_page": int(question["gold_page"]),
        "evidence_quote": question["evidence_quote"],
        "filter": q_filter,
        "hit_at_1": hit_at_1,
        "evidence_hit_at_3": evidence_hit_at_3,
        "gold_page_in_top_3": page_hit_at_3,
        "evidence_split_across_chunks": evidence_split_across_chunks,
        "multi_chunk_combined_hit": quote_clean in combined_gold_page_text if page_hit_at_3 else False,
        "metadata_valid_count": sum(1 for x in meta_valid_flags if x),
        "metadata_checked_count": len(top3),
        "filter_compliant_top3": all(filter_flags) if q_filter else None,
        "top_3_hits": annotated_hits,
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate Hit@1 and Evidence Hit@3 by strategy and dev/test split with n/N fractions and percentages."""
    by_group: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for t in traces:
        strat = str(t.get("strategy", "unknown"))
        split = str(t.get("split", "unknown"))
        by_group.setdefault((strat, split), []).append(t)
        by_group.setdefault((strat, "all"), []).append(t)

    summary: dict[str, dict[str, Any]] = {}
    for (strat, split), items in sorted(by_group.items()):
        total = len(items)
        h1 = sum(1 for x in items if x["hit_at_1"])
        h3 = sum(1 for x in items if x["evidence_hit_at_3"])
        split_err = sum(1 for x in items if x.get("evidence_split_across_chunks"))
        meta_valid = sum(int(x.get("metadata_valid_count", 0)) for x in items)
        meta_total = sum(int(x.get("metadata_checked_count", 0)) for x in items)

        filter_items = [x for x in items if x.get("filter")]
        filter_total = len(filter_items)
        filter_ok = sum(1 for x in filter_items if x.get("filter_compliant_top3") is True)

        summary.setdefault(strat, {})[split] = {
            "count": total,
            "hit_at_1_count": h1,
            "hit_at_1_fraction": f"{h1}/{total}",
            "hit_at_1_rate": round(h1 / total, 4) if total else 0.0,
            "evidence_hit_at_3_count": h3,
            "evidence_hit_at_3_fraction": f"{h3}/{total}",
            "evidence_hit_at_3_rate": round(h3 / total, 4) if total else 0.0,
            "split_evidence_error_count": split_err,
            "metadata_valid_fraction": f"{meta_valid}/{meta_total}",
            "metadata_valid_rate": round(meta_valid / meta_total, 4) if meta_total else 0.0,
            "filter_compliance_fraction": f"{filter_ok}/{filter_total}" if filter_total > 0 else "N/A",
            "filter_compliance_rate": round(filter_ok / filter_total, 4) if filter_total > 0 else None,
        }

    return summary
