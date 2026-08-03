"""Network access: a small stateful client over the public metadata APIs.

Sources used (all free, no key required — a key/contact-email only improves
rate limits and politeness):

    OpenAlex        works, references, citers, metadata
    Crossref        metadata (primary hydration source)
    PubMed          metadata fallback (NCBI E-utilities)
    EuropePMC       metadata fallback
    OpenCitations   references/citers fallback when OpenAlex has none

The client caches every remote lookup for the lifetime of the run, so a
multi-hop traversal never fetches the same work twice.
"""

from __future__ import annotations

import logging
import time
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

import requests

from . import parse

log = logging.getLogger("doi2abstracts")

OPENALEX_BASE = "https://api.openalex.org"
CROSSREF_BASE = "https://api.crossref.org"
OPENCITATIONS_BASE = "https://opencitations.net/index/coci/api/v1"
PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
EUROPEPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def normalize_doi(doi: str) -> str:
    """Lower-case and strip a DOI to a bare `10.xxxx/...` form."""
    d = (doi or "").strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.lower().startswith(prefix):
            d = d[len(prefix):]
    return d.strip().lower()


class Client:
    def __init__(
        self,
        email: Optional[str] = None,
        openalex_api_key: Optional[str] = None,
        ncbi_api_key: Optional[str] = None,
        timeout: float = 15.0,
        min_abstract_chars: int = parse.DEFAULT_MIN_ABSTRACT_CHARS,
        sleep: float = 0.0,
        max_retries: int = 3,
        backoff: float = 1.0,
    ):
        self.email = (email or "").strip() or None
        self.openalex_api_key = (openalex_api_key or "").strip() or None
        self.ncbi_api_key = (ncbi_api_key or "").strip() or None
        self.timeout = timeout
        self.min_abstract_chars = min_abstract_chars
        self.sleep = sleep
        self.max_retries = max(0, max_retries)
        self.backoff = max(0.1, backoff)

        from . import __version__
        ua = f"doi2abstracts/{__version__} (https://github.com/thebustalab/doi2abstracts)"
        if self.email:
            ua += f" mailto:{self.email}"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": ua})

        self._work_cache: Dict[str, Optional[dict]] = {}
        self._ref_cache: Dict[str, List[str]] = {}
        self._cit_cache: Dict[str, List[str]] = {}

    # -- low-level --------------------------------------------------------

    # Transient statuses worth retrying: rate-limit and gateway/server hiccups.
    _RETRY_STATUS = (429, 500, 502, 503, 504)

    def _get(self, url: str, params: Optional[dict] = None) -> Optional[requests.Response]:
        backoff = self.backoff
        for attempt in range(self.max_retries + 1):
            if self.sleep:
                time.sleep(self.sleep)
            try:
                resp = self.session.get(url, params=params or {}, timeout=self.timeout)
            except Exception as exc:
                if attempt < self.max_retries:
                    log.warning("request error %s (%s) — retrying in %.1fs", url, exc, backoff)
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                log.warning("request failed %s: %s", url, exc)
                return None
            if resp.status_code == 200:
                return resp
            if resp.status_code in self._RETRY_STATUS and attempt < self.max_retries:
                # Honour a numeric Retry-After when the server sends one, else back off.
                ra = resp.headers.get("Retry-After", "")
                wait = float(ra) if ra.strip().isdigit() else backoff
                log.warning("HTTP %s for %s — retrying in %.1fs (attempt %d/%d)",
                            resp.status_code, url, wait, attempt + 1, self.max_retries)
                time.sleep(wait)
                backoff *= 2
                continue
            log.warning("HTTP %s for %s", resp.status_code, url)
            return None
        return None

    def _openalex_params(self, extra: Optional[dict] = None) -> dict:
        params: dict = {}
        if self.email:
            params["mailto"] = self.email
        if self.openalex_api_key:
            params["api_key"] = self.openalex_api_key
        if extra:
            params.update(extra)
        return params

    # -- OpenAlex works ---------------------------------------------------

    def openalex_work(self, doi: str) -> Optional[dict]:
        key = normalize_doi(doi)
        if key in self._work_cache:
            return self._work_cache[key]
        encoded = urllib.parse.quote(key, safe="")
        resp = self._get(f"{OPENALEX_BASE}/works/doi:{encoded}", self._openalex_params())
        data = resp.json() if resp is not None else None
        self._work_cache[key] = data
        return data

    def _resolve_openalex_ids(self, ids: List[str]) -> List[str]:
        cleaned = []
        for rid in ids:
            if not isinstance(rid, str):
                continue
            rid = rid.strip().replace("https://openalex.org/", "")
            if rid and rid.upper().startswith("W"):
                cleaned.append(rid)
        out: List[str] = []
        for i in range(0, len(cleaned), 50):
            batch = cleaned[i:i + 50]
            params = self._openalex_params({"filter": "openalex:" + "|".join(batch), "per-page": 100})
            resp = self._get(f"{OPENALEX_BASE}/works", params)
            if resp is None:
                continue
            for item in resp.json().get("results", []):
                doi = _doi_from_openalex_item(item)
                if doi:
                    out.append(doi)
        return out

    # -- references / citers ---------------------------------------------

    def references(self, doi: str) -> List[str]:
        """DOIs of works this paper cites. OpenAlex first, OpenCitations fallback."""
        key = normalize_doi(doi)
        if key in self._ref_cache:
            return self._ref_cache[key]
        refs: List[str] = []
        work = self.openalex_work(key)
        if work:
            refs = self._resolve_openalex_ids(work.get("referenced_works") or [])
        if not refs:
            refs = self._opencitations(key, "references", "cited")
        refs = _dedup(refs)
        self._ref_cache[key] = refs
        return refs

    def citers(self, doi: str) -> List[str]:
        """DOIs of works that cite this paper. OpenAlex first, OpenCitations fallback."""
        key = normalize_doi(doi)
        if key in self._cit_cache:
            return self._cit_cache[key]
        citers: List[str] = []
        work = self.openalex_work(key)
        cited_url = (work or {}).get("cited_by_api_url")
        if cited_url:
            cursor = "*"
            while cursor:
                resp = self._get(cited_url, self._openalex_params({"per-page": 200, "cursor": cursor}))
                if resp is None:
                    break
                data = resp.json()
                for item in data.get("results", []):
                    d = _doi_from_openalex_item(item)
                    if d:
                        citers.append(d)
                cursor = (data.get("meta") or {}).get("next_cursor")
        if not citers:
            citers = self._opencitations(key, "citations", "citing")
        citers = _dedup(citers)
        self._cit_cache[key] = citers
        return citers

    def _opencitations(self, doi: str, endpoint: str, field: str) -> List[str]:
        resp = self._get(f"{OPENCITATIONS_BASE}/{endpoint}/{urllib.parse.quote(doi)}")
        if resp is None:
            return []
        try:
            data = resp.json()
        except Exception:
            return []
        return [normalize_doi(item.get(field, "")) for item in data if (item.get(field) or "").strip()]

    # -- hydration --------------------------------------------------------

    def hydrate(self, doi: str) -> dict:
        """Fetch metadata for one DOI, walking Crossref → OpenAlex → PubMed →
        EuropePMC and stopping as soon as the record is complete."""
        key = normalize_doi(doi)
        mc = self.min_abstract_chars
        md: dict = {}
        md = parse.merge_metadata(md, parse.parse_crossref(self._crossref(key)), min_chars=mc)
        if parse.needs_more(md, mc):
            md = parse.merge_metadata(md, parse.parse_openalex_record(self.openalex_work(key)), min_chars=mc)
        if parse.needs_more(md, mc):
            md = parse.merge_metadata(md, parse.parse_pubmed(self._pubmed(key)), min_chars=mc)
        if parse.needs_more(md, mc):
            md = parse.merge_metadata(md, parse.parse_europe_pmc(self._europepmc(key)), min_chars=mc)
        md["doi"] = key
        return md

    def _crossref(self, doi: str) -> Optional[dict]:
        params = {"mailto": self.email} if self.email else {}
        resp = self._get(f"{CROSSREF_BASE}/works/{urllib.parse.quote(doi)}", params)
        if resp is None:
            return None
        try:
            return resp.json().get("message") or None
        except Exception:
            return None

    def _pubmed(self, doi: str) -> Optional[dict]:
        params = {"db": "pubmed", "term": f"{doi}[DOI]", "retmode": "xml"}
        if self.ncbi_api_key:
            params["api_key"] = self.ncbi_api_key
        resp = self._get(PUBMED_ESEARCH, params)
        if resp is None:
            return None
        try:
            root = ET.fromstring(resp.text)
        except Exception:
            return None
        ids = root.findall(".//IdList/Id")
        if not ids:
            return None
        pmid = ids[0].text
        fparams = {"db": "pubmed", "id": pmid, "retmode": "xml"}
        if self.ncbi_api_key:
            fparams["api_key"] = self.ncbi_api_key
        resp2 = self._get(PUBMED_EFETCH, fparams)
        if resp2 is None:
            return None
        try:
            return {"pmid": pmid, "xml": ET.fromstring(resp2.text)}
        except Exception:
            return None

    def _europepmc(self, doi: str) -> Optional[dict]:
        resp = self._get(EUROPEPMC_SEARCH, {"query": f"DOI:{doi}", "format": "json", "pageSize": 1})
        if resp is None:
            return None
        try:
            results = (resp.json().get("resultList") or {}).get("result") or []
        except Exception:
            return None
        return results[0] if results else None


def _doi_from_openalex_item(item: dict) -> str:
    ids_block = item.get("ids") or {}
    doi = ids_block.get("doi") or ids_block.get("DOI") or item.get("doi")
    return normalize_doi(doi) if doi else ""


def _dedup(dois: List[str]) -> List[str]:
    seen = set()
    out = []
    for d in dois:
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out
