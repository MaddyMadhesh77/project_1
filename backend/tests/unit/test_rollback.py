import uuid

import networkx as nx

from app.services.rollback import (
    OUTCOME_KEPT,
    OUTCOME_REMOVED,
    OUTCOME_REVERTED,
    NodeOutcome,
    _is_tainted,
    classify_outcome,
    processing_order,
)


def test_kept_when_independent_support_exists():
    assert classify_outcome(has_independent_support=True, has_prior_version=True) == OUTCOME_KEPT
    assert classify_outcome(has_independent_support=True, has_prior_version=False) == OUTCOME_KEPT


def test_reverted_when_no_support_but_prior_version_exists():
    assert classify_outcome(has_independent_support=False, has_prior_version=True) == OUTCOME_REVERTED


def test_removed_when_no_support_and_no_prior_version():
    assert classify_outcome(has_independent_support=False, has_prior_version=False) == OUTCOME_REMOVED


def _outcome(outcome: str) -> NodeOutcome:
    return NodeOutcome(
        version_id=uuid.uuid4(),
        memory_id=uuid.uuid4(),
        text="x",
        outcome=outcome,
        new_version_id=uuid.uuid4(),
        trust_score=0.0,
        reason="",
    )


def test_poisoned_version_itself_is_always_tainted():
    poisoned = uuid.uuid4()
    assert _is_tainted(poisoned, poisoned, {}) is True


def test_untouched_parent_is_not_tainted():
    poisoned, other = uuid.uuid4(), uuid.uuid4()
    assert _is_tainted(other, poisoned, {}) is False


def test_removed_parent_taints_its_children():
    poisoned, parent = uuid.uuid4(), uuid.uuid4()
    outcomes = {parent: _outcome(OUTCOME_REMOVED)}
    assert _is_tainted(parent, poisoned, outcomes) is True


def test_kept_or_reverted_parent_does_not_taint_children():
    poisoned, parent_a, parent_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    outcomes = {parent_a: _outcome(OUTCOME_KEPT), parent_b: _outcome(OUTCOME_REVERTED)}
    assert _is_tainted(parent_a, poisoned, outcomes) is False
    assert _is_tainted(parent_b, poisoned, outcomes) is False


def test_processing_order_is_topological_for_a_chain():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    graph = nx.DiGraph()
    graph.add_edges_from([(a, b), (b, c)])
    order = processing_order(graph, a, {b, c})
    assert order.index(a) < order.index(b) < order.index(c)
    assert set(order) == {a, b, c}


def test_processing_order_respects_diamond_dependency():
    # a -> b -> d
    # a -> c -> d
    a, b, c, d = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    graph = nx.DiGraph()
    graph.add_edges_from([(a, b), (b, d), (a, c), (c, d)])
    order = processing_order(graph, a, {b, c, d})
    assert order.index(a) < order.index(b)
    assert order.index(a) < order.index(c)
    assert order.index(b) < order.index(d)
    assert order.index(c) < order.index(d)


def test_processing_order_includes_isolated_root_with_no_descendants():
    lonely = uuid.uuid4()
    order = processing_order(nx.DiGraph(), lonely, set())
    assert order == [lonely]
