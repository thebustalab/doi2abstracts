"""Offline tests for the BFS traversal, using a stub client (no network)."""

from doi2abstracts import traverse


class StubClient:
    """Stands in for Client: canned references/citers, DOIs already normalised."""

    def __init__(self, refs=None, citers=None):
        self._refs = refs or {}
        self._citers = citers or {}

    def references(self, doi):
        return list(self._refs.get(doi, []))

    def citers(self, doi):
        return list(self._citers.get(doi, []))


def test_hops_zero_returns_seeds_only():
    client = StubClient(refs={"a": ["b"]})
    assert traverse.traverse(client, ["A"], hops=0) == ["a"]


def test_hops_one_both_directions():
    client = StubClient(refs={"a": ["b", "c"]}, citers={"a": ["d"]})
    out = traverse.traverse(client, ["a"], hops=1, direction="both")
    assert out[0] == "a"
    assert set(out) == {"a", "b", "c", "d"}


def test_direction_references_only():
    client = StubClient(refs={"a": ["b"]}, citers={"a": ["d"]})
    out = traverse.traverse(client, ["a"], hops=1, direction="references")
    assert set(out) == {"a", "b"}


def test_two_hops_expands_frontier():
    client = StubClient(refs={"a": ["b"], "b": ["c"]})
    out = traverse.traverse(client, ["a"], hops=2, direction="references")
    assert out == ["a", "b", "c"]


def test_max_papers_caps_and_keeps_seed_first():
    client = StubClient(refs={"a": ["b", "c", "d", "e"]})
    out = traverse.traverse(client, ["a"], hops=1, direction="references", max_papers=3)
    assert len(out) == 3
    assert out[0] == "a"


def test_cycle_is_safe():
    # a -> b -> a should not loop forever.
    client = StubClient(refs={"a": ["b"], "b": ["a"]})
    out = traverse.traverse(client, ["a"], hops=5, direction="references")
    assert set(out) == {"a", "b"}


def test_seeds_normalised():
    client = StubClient()
    assert traverse.traverse(client, ["https://doi.org/10.1/AbC"], hops=0) == ["10.1/abc"]
