"""Command-line entry point for doi2abstracts."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import List

from . import __version__, collect
from . import ris


def _read_doi_file(path: str) -> List[str]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                out.append(line)
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="doi2abstracts",
        description="Walk the citation graph from one or more DOIs and collect "
                    "every paper's abstract into a RIS or JSONL file.",
    )
    p.add_argument("dois", nargs="*", help="One or more seed DOIs.")
    p.add_argument("--doi-file", help="Path to a file of seed DOIs, one per line (# comments allowed).")
    p.add_argument("--hops", type=int, default=1,
                   help="How many citation-graph levels to walk. 0=just the seeds, "
                        "1=seeds + their direct references/citers, 2=one level further. Default 1.")
    p.add_argument("--direction", choices=("both", "references", "citers"), default="both",
                   help="Walk references (papers the seed cites), citers (papers that cite the seed), "
                        "or both. Default both.")
    p.add_argument("--max-papers", type=int, default=5000,
                   help="Hard cap on the number of papers collected; traversal stops when reached. "
                        "Citation fan-out is large — keep this sane. Default 5000.")
    p.add_argument("--format", choices=("ris", "jsonl"), default="ris",
                   help="Output format. Default ris.")
    p.add_argument("--out", "-o", help="Output file. Defaults to stdout.")
    p.add_argument("--email", help="Contact email for the API 'polite pools' (recommended by OpenAlex/"
                                   "Crossref). Falls back to the OPENALEX_MAILTO env var.")
    p.add_argument("--ncbi-api-key", help="Optional NCBI API key for higher PubMed rate limits. "
                                          "Falls back to the NCBI_API_KEY env var.")
    p.add_argument("--openalex-api-key", help="Optional OpenAlex API key. Falls back to OPENALEX_API_KEY.")
    p.add_argument("--workers", type=int, default=4, help="Concurrent hydration workers. Default 4.")
    p.add_argument("-v", "--verbose", action="store_true", help="Log progress to stderr.")
    p.add_argument("-q", "--quiet", action="store_true", help="Suppress all logging.")
    p.add_argument("--version", action="version", version=f"doi2abstracts {__version__}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    level = logging.WARNING
    if args.verbose:
        level = logging.INFO
    if args.quiet:
        level = logging.CRITICAL + 1
    # Logs go to stderr so stdout stays clean for piped output.
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s",
                        datefmt="%H:%M:%S", stream=sys.stderr)

    seeds: List[str] = list(args.dois)
    if args.doi_file:
        seeds += _read_doi_file(args.doi_file)
    if not seeds:
        print("error: no DOIs given (pass them as arguments or via --doi-file)", file=sys.stderr)
        return 2

    email = args.email or os.getenv("OPENALEX_MAILTO") or os.getenv("DOI2ABSTRACTS_EMAIL")
    if not email:
        print("note: no --email/OPENALEX_MAILTO set — APIs still work, but a contact email "
              "gets you the faster 'polite pool'.", file=sys.stderr)

    records = collect(
        seeds,
        hops=args.hops,
        direction=args.direction,
        max_papers=args.max_papers,
        email=email,
        ncbi_api_key=args.ncbi_api_key or os.getenv("NCBI_API_KEY"),
        openalex_api_key=args.openalex_api_key or os.getenv("OPENALEX_API_KEY"),
        workers=args.workers,
    )

    with_abstract = sum(1 for r in records if r.get("abstract"))
    logging.getLogger("doi2abstracts").info(
        "collected %d papers (%d with abstracts)", len(records), with_abstract)

    out = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout
    try:
        if args.format == "ris":
            for md in records:
                out.write(ris.ris_entry(md) + "\n\n")
        else:  # jsonl
            for r in records:
                out.write(json.dumps(r, ensure_ascii=False) + "\n")
    finally:
        if args.out:
            out.close()

    if args.out:
        print(f"wrote {len(records)} papers ({with_abstract} with abstracts) to {args.out}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
