"""Pure metadata parsing and normalisation.

No network access and no state live here, so every function is trivially
testable offline. The per-source parsers turn a raw API record (Crossref,
OpenAlex, PubMed, EuropePMC) into a common metadata dict with these keys:

    title, authors, abstract, year, cited_by, ref_count, journal,
    volume, issue, pages, article_number

`authors` is a list of {"family", "given"} dicts (OpenAlex authorships are
normalised into that shape by ``format_authors``' callers upstream).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

# Minimum length for an abstract to be treated as substantive. Some sources
# return only the first sentence (~128-200 chars) or citation-export
# boilerplate; below this threshold we keep trying the other sources rather
# than accepting the stub.
DEFAULT_MIN_ABSTRACT_CHARS = 300

_TAG_RE = re.compile(r"<[^>]+>")

# Fields that participate in the only-if-empty merge across sources.
MERGE_FIELDS = [
    "title", "authors", "abstract", "year", "cited_by", "ref_count",
    "journal", "volume", "issue", "pages", "article_number",
]

# Fields whose absence forces the next source in the fallback chain.
_NEEDED_FIELDS = ["title", "authors", "abstract", "year", "cited_by", "ref_count", "journal"]


def clean_text(val) -> str:
    if not isinstance(val, str):
        return ""
    return " ".join(val.split()).strip()


def strip_tags(text) -> str:
    if not isinstance(text, str):
        return ""
    return clean_text(_TAG_RE.sub(" ", text))


def abstract_is_substantive(text, min_chars: int = DEFAULT_MIN_ABSTRACT_CHARS) -> bool:
    """True if `text` looks like a real abstract rather than boilerplate or a
    truncated first sentence.

    Guards two failure modes: a source returning citation-export boilerplate
    ("Share Add toView InAdd Full Text...") and a source returning only the
    first ~128-200 chars. Both are non-empty, so a bare truthiness check would
    accept them and short-circuit the remaining sources.
    """
    if not isinstance(text, str):
        return False
    cleaned = clean_text(text)
    if len(cleaned) < min_chars:
        return False
    compact = re.sub(r"\s+", "", cleaned).lower()
    boilerplate_markers = ("shareadd", "addtoview", "viewinadd", "addfulltext")
    if any(marker in compact[:80] for marker in boilerplate_markers):
        return False
    return True


def needs_more(md: dict, min_chars: int = DEFAULT_MIN_ABSTRACT_CHARS) -> bool:
    """True if `md` is still missing something a later source might supply."""
    for k in _NEEDED_FIELDS:
        v = md.get(k)
        if v in (None, "", [], {}):
            return True
    if not abstract_is_substantive(md.get("abstract", ""), min_chars):
        return True
    return False


def merge_metadata(base: dict, update: dict, fields: List[str] = MERGE_FIELDS,
                   min_chars: int = DEFAULT_MIN_ABSTRACT_CHARS) -> dict:
    """Fill empty fields of `base` from `update` (only-if-empty), with one
    exception: a substantive incoming abstract replaces a non-substantive one
    already in place (boilerplate / truncated stub), so a junk early abstract
    can't block the real text from a later source."""
    out = dict(base or {})
    for f in fields:
        if not out.get(f) and update.get(f):
            out[f] = update[f]
    upd_abstract = update.get("abstract")
    if (
        upd_abstract
        and abstract_is_substantive(upd_abstract, min_chars)
        and not abstract_is_substantive(out.get("abstract", ""), min_chars)
    ):
        out["abstract"] = upd_abstract
    return out


def format_authors(authors: list) -> List[str]:
    """Turn a list of {"family","given"} dicts into "Family, Given" strings.

    Already-formatted strings (as produced by ris.to_record) pass through, so
    this is safe to call on either the raw metadata form or a flat record."""
    out = []
    for a in authors or []:
        if isinstance(a, str):
            s = clean_text(a)
            if s:
                out.append(s)
            continue
        fam = clean_text(a.get("family", ""))
        giv = clean_text(a.get("given", ""))
        if fam and giv:
            out.append(f"{fam}, {giv}")
        elif fam:
            out.append(fam)
        elif giv:
            out.append(giv)
    return out


# ---------------------------------------------------------------------------
# Per-source parsers
# ---------------------------------------------------------------------------

def parse_crossref(md: dict) -> dict:
    out: dict = {}
    if not md:
        return out
    out["title"] = strip_tags(md.get("title", [""])[0] if md.get("title") else "")
    out["authors"] = md.get("author") or []
    out["abstract"] = strip_tags(md.get("abstract") or "")
    out["year"] = None
    dp = (md.get("issued") or {}).get("date-parts") or []
    if dp and dp[0]:
        out["year"] = dp[0][0]
    out["cited_by"] = md.get("is-referenced-by-count")
    out["ref_count"] = md.get("reference-count") or md.get("references-count")
    out["journal"] = strip_tags((md.get("container-title") or [""])[0] if md.get("container-title") else "")
    out["volume"] = clean_text(str(md.get("volume") or ""))
    out["issue"] = clean_text(str(md.get("issue") or ""))
    out["pages"] = clean_text(str(md.get("page") or ""))
    out["article_number"] = clean_text(str(md.get("article-number") or ""))
    return out


def parse_openalex_record(md: dict) -> dict:
    out: dict = {}
    if not md:
        return out
    out["title"] = strip_tags(md.get("display_name", ""))
    out["authors"] = _openalex_authors(md.get("authorships") or [])
    inv = md.get("abstract_inverted_index") or {}
    if inv:
        pairs = []
        for word, positions in inv.items():
            for pos in positions:
                pairs.append((pos, word))
        pairs.sort(key=lambda x: x[0])
        out["abstract"] = strip_tags(" ".join(w for _, w in pairs))
    else:
        out["abstract"] = ""
    out["year"] = md.get("publication_year")
    out["cited_by"] = md.get("cited_by_count")
    out["ref_count"] = len(md.get("referenced_works") or [])
    out["journal"] = strip_tags((md.get("host_venue") or {}).get("display_name", ""))
    biblio = md.get("biblio") or {}
    out["volume"] = clean_text(str(biblio.get("volume") or ""))
    out["issue"] = clean_text(str(biblio.get("issue") or ""))
    fp = clean_text(str(biblio.get("first_page") or ""))
    lp = clean_text(str(biblio.get("last_page") or ""))
    if fp and lp:
        out["pages"] = f"{fp}-{lp}"
    elif fp:
        out["pages"] = fp
    return out


def _openalex_authors(authorships: list) -> List[dict]:
    """OpenAlex authorships carry a single `display_name`; split into
    family/given so the RIS writer emits `Family, Given` consistently."""
    out = []
    for a in authorships or []:
        author = a.get("author") or {}
        name = clean_text(author.get("display_name", ""))
        if not name:
            continue
        parts = name.rsplit(" ", 1)
        if len(parts) == 2:
            given, family = parts
        else:
            given, family = "", name
        out.append({"family": family, "given": given})
    return out


def parse_pubmed(data: dict) -> dict:
    out: dict = {}
    if not data:
        return out
    root = data.get("xml")
    if root is None:
        return out
    abstract_elems = root.findall(".//Abstract/AbstractText")
    if abstract_elems:
        out["abstract"] = strip_tags(" ".join(ae.text or "" for ae in abstract_elems if ae.text))
    title_elem = root.find(".//ArticleTitle")
    if title_elem is not None and title_elem.text:
        out["title"] = strip_tags(title_elem.text)
    journal_elem = root.find(".//Journal/Title")
    if journal_elem is not None and journal_elem.text:
        out["journal"] = strip_tags(journal_elem.text)
    vol_elem = root.find(".//JournalIssue/Volume")
    if vol_elem is not None and vol_elem.text:
        out["volume"] = clean_text(vol_elem.text)
    issue_elem = root.find(".//JournalIssue/Issue")
    if issue_elem is not None and issue_elem.text:
        out["issue"] = clean_text(issue_elem.text)
    pgn_elem = root.find(".//Pagination/MedlinePgn")
    if pgn_elem is not None and pgn_elem.text:
        out["pages"] = clean_text(pgn_elem.text)
    year_elem = root.find(".//PubDate/Year")
    if year_elem is not None and year_elem.text:
        out["year"] = int(year_elem.text) if year_elem.text.isdigit() else year_elem.text
    authors = []
    for a in root.findall(".//AuthorList/Author"):
        last = clean_text(a.findtext("LastName", default=""))
        first = clean_text(a.findtext("ForeName", default=""))
        if last or first:
            authors.append({"family": last, "given": first})
    if authors:
        out["authors"] = authors
    return out


def parse_europe_pmc(data: dict) -> dict:
    out: dict = {}
    if not data:
        return out
    if data.get("title"):
        out["title"] = strip_tags(data.get("title", ""))
    if data.get("journalTitle"):
        out["journal"] = strip_tags(data.get("journalTitle", ""))
    if data.get("journalVolume"):
        out["volume"] = clean_text(str(data.get("journalVolume")))
    if data.get("issue"):
        out["issue"] = clean_text(str(data.get("issue")))
    if data.get("pageInfo"):
        out["pages"] = clean_text(str(data.get("pageInfo")))
    if data.get("pubYear"):
        try:
            out["year"] = int(data["pubYear"])
        except Exception:
            out["year"] = data["pubYear"]
    if data.get("abstractText"):
        out["abstract"] = strip_tags(data.get("abstractText", ""))
    authors = []
    for a in (data.get("authorList", {}) or {}).get("author", []) or []:
        last = clean_text(a.get("lastName", ""))
        first = clean_text(a.get("firstName", ""))
        if last or first:
            authors.append({"family": last, "given": first})
    if authors:
        out["authors"] = authors
    return out
