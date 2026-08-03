"""Offline unit tests for the pure parsing/normalisation layer."""

from doi2abstracts import parse
from doi2abstracts.client import normalize_doi


def test_normalize_doi_strips_prefixes_and_lowercases():
    assert normalize_doi("https://doi.org/10.1/AbC") == "10.1/abc"
    assert normalize_doi("doi:10.1/AbC") == "10.1/abc"
    assert normalize_doi("  10.1/AbC  ") == "10.1/abc"


def test_abstract_is_substantive():
    assert parse.abstract_is_substantive("word " * 100) is True
    assert parse.abstract_is_substantive("too short") is False
    # Boilerplate prefix is rejected even when long.
    boiler = "Share Add toView InAdd Full Text " + "x" * 400
    assert parse.abstract_is_substantive(boiler) is False


def test_needs_more_flags_missing_and_stub_abstract():
    complete = {
        "title": "t", "authors": [{"family": "A"}], "abstract": "word " * 100,
        "year": 2020, "cited_by": 1, "ref_count": 2, "journal": "J",
    }
    assert parse.needs_more(complete) is False
    stub = dict(complete, abstract="short")
    assert parse.needs_more(stub) is True
    missing = dict(complete)
    del missing["journal"]
    assert parse.needs_more(missing) is True


def test_merge_metadata_only_if_empty_but_substantive_abstract_wins():
    base = {"title": "keep", "abstract": "short stub"}
    upd = {"title": "ignored", "abstract": "real " * 100, "year": 2021}
    out = parse.merge_metadata(base, upd)
    assert out["title"] == "keep"          # existing non-empty preserved
    assert out["year"] == 2021             # empty field filled
    assert out["abstract"].startswith("real")  # stub replaced by substantive text


def test_format_authors_handles_dicts_and_strings():
    dicts = [{"family": "Busta", "given": "Lucas"}, {"family": "Doe"}]
    assert parse.format_authors(dicts) == ["Busta, Lucas", "Doe"]
    # Already-formatted strings pass through unchanged.
    assert parse.format_authors(["Busta, Lucas"]) == ["Busta, Lucas"]


def test_parse_crossref_strips_tags():
    raw = {
        "title": ["A <i>gene</i> study"],
        "author": [{"family": "X", "given": "Y"}],
        "abstract": "<jats:p>Hello</jats:p>",
        "issued": {"date-parts": [[2019, 5]]},
        "container-title": ["Plant Physiology"],
    }
    out = parse.parse_crossref(raw)
    assert out["title"] == "A gene study"
    assert out["abstract"] == "Hello"
    assert out["year"] == 2019
    assert out["journal"] == "Plant Physiology"


def test_parse_openalex_reconstructs_inverted_index_and_authors():
    raw = {
        "display_name": "T",
        "abstract_inverted_index": {"Hello": [0], "world": [1], "again": [2]},
        "authorships": [{"author": {"display_name": "Lucas Busta"}}],
        "publication_year": 2022,
    }
    out = parse.parse_openalex_record(raw)
    assert out["abstract"] == "Hello world again"
    assert out["authors"] == [{"family": "Busta", "given": "Lucas"}]
