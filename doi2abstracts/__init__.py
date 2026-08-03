"""doi2abstracts — DOI(s) in, a structured file of abstracts out.

Give it one or more DOIs; it walks the citation graph (references and/or
citers, as many hops as you ask for) and collects every paper's metadata and
abstract from public APIs (OpenAlex, Crossref, PubMed, EuropePMC). No API keys
and no language-model server required.

Programmatic use:

    from doi2abstracts import collect
    records = collect(["10.1104/pp.18.01195"], hops=1, email="you@example.edu")
    for r in records:
        print(r["title"], "--", r["abstract"][:200])

`records` is a list of flat dicts (see ris.to_record). Use ris.write_ris or the
CLI for file output.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Optional

__version__ = "0.1.0"

from .client import Client, normalize_doi  # noqa: E402
from . import ris, traverse  # noqa: E402

log = logging.getLogger("doi2abstracts")

__all__ = ["collect", "Client", "normalize_doi", "ris", "traverse", "__version__"]


def collect(
    seeds: List[str],
    hops: int = 1,
    direction: str = "both",
    max_papers: int = 5000,
    email: Optional[str] = None,
    ncbi_api_key: Optional[str] = None,
    openalex_api_key: Optional[str] = None,
    workers: int = 4,
    client: Optional[Client] = None,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> List[dict]:
    """Traverse from `seeds`, hydrate every reached DOI, return flat records.

    Records come back in traversal order (seeds first). `progress`, if given, is
    called as progress(done, total, doi) after each paper is hydrated.
    """
    client = client or Client(
        email=email,
        ncbi_api_key=ncbi_api_key,
        openalex_api_key=openalex_api_key,
    )

    dois = traverse.traverse(client, seeds, hops=hops, direction=direction, max_papers=max_papers)
    total = len(dois)
    log.info("hydrating %d papers", total)

    hydrated: dict = {}
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futures = {ex.submit(client.hydrate, d): d for d in dois}
        for fut in as_completed(futures):
            d = futures[fut]
            try:
                md = fut.result()
            except Exception as exc:
                log.warning("hydration failed for %s: %s", d, exc)
                md = {"doi": d}
            hydrated[d] = md
            done += 1
            if progress:
                progress(done, total, d)
            else:
                log.info("hydrated %d/%d %s", done, total, d)

    # Preserve traversal order (seeds first); dict lookups keep it stable.
    return [ris.to_record(hydrated[d]) for d in dois if d in hydrated]
