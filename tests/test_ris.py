"""Offline tests for RIS/JSONL/CSV rendering."""

import csv
import io
import json

from doi2abstracts import ris


SAMPLE = {
    "doi": "10.1/abc",
    "title": "A study",
    "authors": [{"family": "Busta", "given": "Lucas"}],
    "year": 2020,
    "journal": "Plant Physiology",
    "volume": "178",
    "issue": "4",
    "pages": "1507-1521",
    "cited_by": 31,
    "ref_count": 67,
    "abstract": "The abstract text.",
}


def test_ris_entry_splits_page_range_and_ends_with_ER():
    out = ris.ris_entry(SAMPLE)
    assert "TY  - JOUR" in out
    assert "AU  - Busta, Lucas" in out
    assert "SP  - 1507" in out
    assert "EP  - 1521" in out
    assert "DO  - 10.1/abc" in out
    assert out.rstrip().endswith("ER  -")


def test_ris_entry_article_number_fallback_when_no_pages():
    md = dict(SAMPLE, pages="", article_number="e00205")
    out = ris.ris_entry(md)
    assert "SP  - e00205" in out
    assert "EP  - " not in out


def test_to_record_flattens_authors_and_keeps_article_number():
    rec = ris.to_record(dict(SAMPLE, article_number="e1"))
    assert rec["authors"] == ["Busta, Lucas"]
    assert rec["article_number"] == "e1"


def test_write_stream_csv_joins_authors():
    rec = ris.to_record(SAMPLE)
    buf = io.StringIO()
    ris.write_stream([rec], buf, "csv")
    buf.seek(0)
    rows = list(csv.DictReader(buf))
    assert rows[0]["authors"] == "Busta, Lucas"
    assert rows[0]["doi"] == "10.1/abc"


def test_write_stream_jsonl_roundtrips():
    rec = ris.to_record(SAMPLE)
    buf = io.StringIO()
    ris.write_stream([rec], buf, "jsonl")
    parsed = json.loads(buf.getvalue().strip())
    assert parsed["title"] == "A study"


def test_ris_entry_works_on_flat_record_authors():
    # A flat record (authors already strings) must not crash ris_entry.
    rec = ris.to_record(SAMPLE)
    out = ris.ris_entry(rec)
    assert "AU  - Busta, Lucas" in out
