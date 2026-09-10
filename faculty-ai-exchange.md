---
title: Retrieving a literature corpus for LLM analysis
summary: One command turns a few seed DOIs into thousands of abstracts, so students can run their own language model experiments on real literature without API keys, a GPU, or a scraping project.
faculty: Lucas Busta
department: Chemistry and Biochemistry
department_id: chemistry-and-biochemistry
audience: Faculty that do computational work on scientific literature, and anyone assembling a corpus for text analysis
use_case: Research and teaching infrastructure
tools:
  - Claude Code
  - Any language model the student chooses
tags:
  - literature
  - corpus
  - text mining
  - python
image: /assets/images/example.svg
repository_url: https://github.com/thebustalab/doi2abstracts
---

## What faculty used it for

Anyone who wants to try a language model on scientific literature must overcome a barrier before they get anywhere near working with the model: acquiring literature. Most folks have a PDF folder, or a reference manager export of citations, or a plan to scrape a publisher's website (which will likely not survive contact with the publisher). This tool closes that gap. Give it one or more DOIs and it walks the citation graph (the papers the seeds cite, the papers citing them, as many hops out as the user asks) and collects every paper's metadata and abstract into a single RIS, JSONL or CSV file, ready for language model analysis.

```bash
doi2abstracts 10.1104/pp.18.01195 --hops 1 --email you@example.edu -o refs.ris
```

The line above is the whole setup. It uses the free public metadata APIs (OpenAlex, Crossref, PubMed, Europe PMC) so there are no API keys, no institutional subscription, and no login. Start with the one-line install and a seed paper from a project, and twenty minutes later you have a few thousand abstracts to work on.

## Why it was useful

**There is no AI in this tool, on purpose.** It is perhaps tempting, when building something like this, to involve a language model in the literature fetching, and the parsing, and the deduplication. Every one of those is a place where a model can, in a way that is difficult to detect, invent a paper that does not exist or modify the language used by the original authors. A fabricated citation in a corpus is a truly bad outcome because it is very hard to catch downstream and it can poison whatever analysis comes after. So, the retrieval path used here relies only on deterministic API calls end to end, with a documented fallback chain when one source has no abstract. If the tool cannot find something, it says so rather than filling the hole.

Literature in hand, anyone can then point whatever model they like at the resulting file: clustering, screening for relevance, extracting reported values, summarizing a subfield, etc. Importantly, splitting the retrieval and model processing makes the boundary legible: the corpus is ground truth that a machine assembled from public records, and the model's output is a claim about that corpus that can be checked against that same corpus.

Two honest limits, both of which turn out to be teachable. First, this tool collects abstracts, not full text. This is enough for screening, clustering, and triage, but not enough for extracting methods detail, and noticing that distinction is itself worth a conversation. Second, citation graphs explode: one paper can have hundreds of references and citers, and two hops can reach tens of thousands of papers. The tool ships an `--estimate` flag that reports how big a run would be before you commit to it, which is the first thing anyone using this tool should learn.

## Materials to adapt

- **The tool**: <https://github.com/thebustalab/doi2abstracts>. Python 3.9+, MIT licensed, one dependency (`requests`). `pip install git+https://github.com/thebustalab/doi2abstracts.git`
- **A seed DOI or two** from whatever the student is actually working on. Their own project's papers work far better than a generic example.
- **Nothing else.** No keys, no accounts, no institutional access. An `--email` flag puts you in the APIs' polite pools and is worth setting.
- **A first exercise that works well**: run `--estimate` at one and two hops on the same seed and have students explain the difference before running anything for real.
- There is a Python entry point as well as the command line (`from doi2abstracts import collect`), which is the easier on-ramp if your students are already working in notebooks.
