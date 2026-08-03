# doi2abstracts

Give it one or more DOIs. It walks the citation graph — the papers your seeds
cite, the papers that cite them, as many hops out as you ask for — and collects
every paper's metadata and **abstract** into a single RIS or JSONL file.

No API keys and no language model required: it uses the free public metadata
APIs (OpenAlex, Crossref, PubMed, EuropePMC). The point is to give you a clean,
structured pile of abstracts you can then run your own experiments on.

## Install

```bash
pip install .
# or, straight from GitHub:
pip install git+https://github.com/thebustalab/doi2abstracts.git
```

The only dependency is `requests`. Python 3.9+.

## Use

```bash
# The seed paper plus everything it cites and everything that cites it:
doi2abstracts 10.1104/pp.18.01195 --hops 1 --email you@example.edu -o refs.ris

# Just the seed papers themselves, as JSONL:
doi2abstracts 10.1104/pp.18.01195 10.1093/plphys/kiaf146 --hops 0 --format jsonl -o seeds.jsonl

# Many seeds from a file, references only, two hops out:
doi2abstracts --doi-file seeds.txt --direction references --hops 2 --max-papers 2000 -o out.ris
```

### Options

| Option | What it does |
|--------|--------------|
| `--hops N` | Levels to walk. 0 = seeds only, 1 = direct neighbours, 2 = one further. Default 1. |
| `--direction` | `both` (default), `references` (papers the seed cites), or `citers` (papers citing the seed). |
| `--max-papers N` | Hard cap; traversal stops when reached. Default 5000. |
| `--estimate` | Report how many papers a run *would* collect, without fetching abstracts. |
| `--format` | `ris` (default), `jsonl`, or `csv`. |
| `--out FILE` / `-o` | Output file (default: stdout). |
| `--email` | Contact email for the API "polite pools" (or set `OPENALEX_MAILTO`). Recommended. |
| `--sleep` / `--max-retries` | Throttle requests / retry on rate limits. Retries use exponential backoff. |
| `--doi-file` | Read seed DOIs from a file, one per line. |

Every metadata source is public and free: no API keys are required. An
`--ncbi-api-key` / `--openalex-api-key` only raises your rate limits.

### A warning about hops — size it first

Citation graphs explode. A single paper can have hundreds of references and
citers; two hops can reach tens of thousands of papers. **Check the size before
you commit** with `--estimate`:

```bash
doi2abstracts 10.1104/pp.18.01195 --hops 2 --estimate --email you@example.edu
# -> "NNNN papers would be collected ... (estimate only — no abstracts fetched)"
```

Then start with `--hops 1` and a `--max-papers` cap, and only go wider once you
know the scale.

## Programmatic use

```python
from doi2abstracts import collect
records = collect(["10.1104/pp.18.01195"], hops=1, email="you@example.edu")
for r in records:
    print(r["title"], "—", r["abstract"][:200])
```

## Development

```bash
pip install -e ".[test]"
pytest tests/ -q
```

The test suite is fully offline (no network) — it stubs the API client and
exercises the parsing, RIS/CSV/JSONL rendering, traversal, and retry logic.

## License

MIT — see [LICENSE](LICENSE).
