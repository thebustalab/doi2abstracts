"""Breadth-first citation-graph traversal.

Starting from one or more seed DOIs, walk outward `hops` levels. At each level
every frontier paper contributes its references (papers it cites) and/or its
citers (papers that cite it), depending on `direction`. A hard `max_papers`
cap stops the set from exploding — citation fan-out is brutal, and two hops can
reach tens of thousands of papers.

`hops` semantics:
    0  → just the seed DOIs themselves
    1  → seeds + their direct references/citers
    2  → the above + the references/citers of everything found at hop 1
"""

from __future__ import annotations

import logging
from typing import List, Set

from .client import Client, normalize_doi

log = logging.getLogger("doi2abstracts")

DIRECTIONS = ("both", "references", "citers")


def _neighbors(client: Client, doi: str, direction: str) -> List[str]:
    out: List[str] = []
    if direction in ("both", "references"):
        out += client.references(doi)
    if direction in ("both", "citers"):
        out += client.citers(doi)
    return out


def traverse(
    client: Client,
    seeds: List[str],
    hops: int = 1,
    direction: str = "both",
    max_papers: int = 5000,
) -> List[str]:
    """Return the deduplicated list of DOIs reachable within `hops` levels.

    Seeds always come first in the returned order. When `max_papers` is hit the
    traversal stops early and logs how many were dropped.
    """
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {DIRECTIONS}, got {direction!r}")

    seed_keys = _dedup([normalize_doi(s) for s in seeds if s and s.strip()])
    if not seed_keys:
        return []

    collected: List[str] = list(seed_keys)
    seen: Set[str] = set(seed_keys)
    frontier: List[str] = list(seed_keys)

    capped = False
    for hop in range(1, hops + 1):
        if capped:
            break
        next_frontier: List[str] = []
        for i, doi in enumerate(frontier, 1):
            log.info("hop %d: expanding %d/%d %s", hop, i, len(frontier), doi)
            for n in _neighbors(client, doi, direction):
                if n in seen:
                    continue
                seen.add(n)
                collected.append(n)
                next_frontier.append(n)
                if len(collected) >= max_papers:
                    capped = True
                    break
            if capped:
                break
        log.info("hop %d complete: %d papers total (frontier for next hop: %d)",
                 hop, len(collected), len(next_frontier))
        frontier = next_frontier
        if not frontier:
            break

    if capped:
        log.warning("max_papers=%d reached — traversal stopped early; some papers were not collected",
                    max_papers)
    return collected


def _dedup(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out
