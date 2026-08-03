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
```

## Use

```bash
# The seed paper plus everything it cites and everything that cites it:
doi2abstracts 10.1104/pp.18.01195 --hops 1 --email you@example.edu -o refs.ris

# Just the seed papers themselves, as JSONL:
doi2abstracts 10.1104/pp.18.01195 10.1093/plphys/kiaf146 --hops 0 --format jsonl -o seeds.jsonl

# Many seeds from a file, references only, two hops out:
doi2abstracts --doi-file seeds.txt --direction references --hops 2 --max-papers 2000 -o out.ris
```

Key options: `--hops` (0 = seeds only, 1 = direct neighbours, 2 = one level
further), `--direction` (`both` / `references` / `citers`), `--max-papers` (hard
cap — citation fan-out is large, so keep this sane), `--format` (`ris` / `jsonl`).

### A warning about hops

Citation graphs explode. A single paper can have hundreds of references and
citers; two hops can reach tens of thousands of papers. Start with `--hops 1`
and a `--max-papers` cap, and only go wider once you know the scale.

## Programmatic use

```python
from doi2abstracts import collect
records = collect(["10.1104/pp.18.01195"], hops=1, email="you@example.edu")
for r in records:
    print(r["title"], "—", r["abstract"][:200])
```

## License

MIT — see [LICENSE](LICENSE).
