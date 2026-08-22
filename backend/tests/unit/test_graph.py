import uuid

import networkx as nx

from app.services.graph import ancestors, descendants


def _chain(*version_ids: uuid.UUID) -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_edges_from(zip(version_ids, version_ids[1:]))
    return graph


def test_descendants_of_root_include_full_transitive_chain():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    graph = _chain(a, b, c)
    assert descendants(graph, a) == {b, c}


def test_descendants_of_leaf_are_empty():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    graph = _chain(a, b, c)
    assert descendants(graph, c) == set()


def test_ancestors_of_leaf_include_full_transitive_chain():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    graph = _chain(a, b, c)
    assert ancestors(graph, c) == {a, b}


def test_version_not_in_graph_has_no_ancestors_or_descendants():
    graph = nx.DiGraph()
    lonely = uuid.uuid4()
    assert descendants(graph, lonely) == set()
    assert ancestors(graph, lonely) == set()


def test_descendants_of_diamond_dependency_include_both_branches():
    # a -> b -> d
    # a -> c -> d
    a, b, c, d = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    graph = nx.DiGraph()
    graph.add_edges_from([(a, b), (b, d), (a, c), (c, d)])
    assert descendants(graph, a) == {b, c, d}
    assert ancestors(graph, d) == {a, b, c}
