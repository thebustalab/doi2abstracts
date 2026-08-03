"""Render hydrated metadata dicts to RIS, and a plain-dict form for JSON output.

RIS is the interchange format every reference manager (Zotero, EndNote,
Mendeley, ...) imports, and it keeps the abstract inline in the `AB` field —
which is the whole point here: a student can open the file in a reference
manager, or parse the `AB` fields straight into their own pipeline.
"""

from __future__ import annotations

import csv
import json
import re
from typing import Dict, List, TextIO

from .parse import clean_text, format_authors

# Column order for CSV output. `authors` is joined with "; ".
CSV_COLUMNS = [
    "doi", "title", "authors", "year", "journal", "volume", "issue",
    "pages", "article_number", "cited_by", "ref_count", "abstract",
]


def ris_entry(md: dict) -> str:
    doi = clean_text(md.get("doi", ""))
    lines = ["TY  - JOUR"]
    title = clean_text(md.get("title", ""))
    if title:
        lines.append(f"TI  - {title}")
    for au in format_authors(md.get("authors", [])):
        lines.append(f"AU  - {au}")
    year = md.get("year")
    if year:
        lines.append(f"PY  - {year}")
    journal = clean_text(md.get("journal", ""))
    if journal:
        lines.append(f"T2  - {journal}")
    volume = clean_text(str(md.get("volume") or ""))
    if volume:
        lines.append(f"VL  - {volume}")
    issue = clean_text(str(md.get("issue") or ""))
    if issue:
        lines.append(f"IS  - {issue}")
    pages = clean_text(str(md.get("pages") or ""))
    article_number = clean_text(str(md.get("article_number") or ""))
    if pages:
        parts = re.split(r"\s*[-–—]\s*", pages, maxsplit=1)
        sp = parts[0].strip()
        ep = parts[1].strip() if len(parts) > 1 else ""
        if sp:
            lines.append(f"SP  - {sp}")
        if ep:
            lines.append(f"EP  - {ep}")
    elif article_number:
        lines.append(f"SP  - {article_number}")
    abstract = clean_text(md.get("abstract", ""))
    if abstract:
        lines.append(f"AB  - {abstract}")
    cited_by = md.get("cited_by")
    if cited_by not in (None, ""):
        lines.append(f"CI  - {cited_by}")
    ref_count = md.get("ref_count")
    if ref_count not in (None, ""):
        lines.append(f"RC  - {ref_count}")
    if doi:
        lines.append(f"DO  - {doi}")
    lines.append("ER  - ")
    return "\n".join(lines)


def write_ris(records: List[dict], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for md in records:
            f.write(ris_entry(md) + "\n\n")


def write_stream(records: List[dict], stream: TextIO, fmt: str = "ris") -> None:
    """Write records to an open stream in `ris`, `jsonl`, or `csv` form.

    Records may be flat dicts (from to_record, authors as a list of strings) or
    raw metadata dicts — ris_entry handles both.
    """
    if fmt == "ris":
        for r in records:
            stream.write(ris_entry(r) + "\n\n")
    elif fmt == "jsonl":
        for r in records:
            stream.write(json.dumps(r, ensure_ascii=False) + "\n")
    elif fmt == "csv":
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            row = dict(r)
            if isinstance(row.get("authors"), list):
                row["authors"] = "; ".join(row["authors"])
            writer.writerow(row)
    else:
        raise ValueError(f"unknown format {fmt!r}")


def to_record(md: dict) -> Dict:
    """A flat, JSON-friendly view of one paper (used for JSONL/CSV output)."""
    return {
        "doi": clean_text(md.get("doi", "")),
        "title": clean_text(md.get("title", "")),
        "authors": format_authors(md.get("authors", [])),
        "year": md.get("year"),
        "journal": clean_text(md.get("journal", "")),
        "volume": clean_text(str(md.get("volume") or "")),
        "issue": clean_text(str(md.get("issue") or "")),
        "pages": clean_text(str(md.get("pages") or "")),
        "article_number": clean_text(str(md.get("article_number") or "")),
        "cited_by": md.get("cited_by"),
        "ref_count": md.get("ref_count"),
        "abstract": clean_text(md.get("abstract", "")),
    }
