import uuid

import networkx as nx

from app.services.rollback import (
    OUTCOME_KEPT,
    OUTCOME_REMOVED,
    OUTCOME_REVERTED,
    ParentRef,
    classify_outcome,
    processing_order,
    valid_sources,
)


def test_kept_when_independent_support_exists():
    assert classify_outcome(has_independent_support=True, has_prior_version=True) == OUTCOME_KEPT
    assert classify_outcome(has_independent_support=True, has_prior_version=False) == OUTCOME_KEPT


def test_reverted_when_no_support_but_prior_version_exists():
    assert classify_outcome(has_independent_support=False, has_prior_version=True) == OUTCOME_REVERTED


def test_removed_when_no_support_and_no_prior_version():
    assert classify_outcome(has_independent_support=False, has_prior_version=False) == OUTCOME_REMOVED


def _ref(memory_id: uuid.UUID, version_number: int) -> ParentRef:
    return ParentRef(version_id=uuid.uuid4(), memory_id=memory_id, version_number=version_number)


def test_poisoned_version_itself_is_never_valid_support():
    poisoned = _ref(uuid.uuid4(), 1)
    assert valid_sources([poisoned], poisoned.version_id, set()) == []


def test_untouched_parent_is_valid_support():
    poisoned_id, other = uuid.uuid4(), _ref(uuid.uuid4(), 1)
    assert valid_sources([other], poisoned_id, set()) == [other]


def test_parent_from_a_removed_memory_is_not_valid_support():
    poisoned_id, parent = uuid.uuid4(), _ref(uuid.uuid4(), 1)
    assert valid_sources([parent], poisoned_id, {parent.memory_id}) == []


def test_copied_edge_on_a_newer_version_does_not_count_as_support():
    # carry_forward_edges copies the poisoned v2's edge onto v3 of the same
    # memory; the child was derived from v2, so v3 must not rescue it.
    memory_id = uuid.uuid4()
    poisoned, newer_copy = _ref(memory_id, 2), _ref(memory_id, 3)
    assert valid_sources([poisoned, newer_copy], poisoned.version_id, set()) == []


def test_child_derived_before_the_poisoned_version_keeps_its_support():
    # Derived from legit v1; v2 (poisoned) and v3 only carry copies of that edge.
    memory_id = uuid.uuid4()
    original, poisoned, newer_copy = _ref(memory_id, 1), _ref(memory_id, 2), _ref(memory_id, 3)
    assert valid_sources([newer_copy, poisoned, original], poisoned.version_id, set()) == [original]


def test_one_source_per_memory_plus_independent_memories():
    poisoned_memory, other_memory = uuid.uuid4(), uuid.uuid4()
    poisoned = _ref(poisoned_memory, 1)
    independent = _ref(other_memory, 1)
    assert valid_sources([poisoned, _ref(poisoned_memory, 2), independent], poisoned.version_id, set()) == [independent]


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
