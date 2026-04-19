"""
Unit tests for ScoreAwareParentAggregator.

All tests use lightweight mock objects – no Milvus / OpenSearch / LLM needed.
Core invariants under test:
  - aggregated_score = max(child_scores) + hit_weight * hit_count
  - output is sorted descending by aggregated_score
  - edge cases: empty input, nodes already in target group, uid-string parents
"""
import types
from unittest.mock import MagicMock

from chat.components.process.score_aware_aggregator import ScoreAwareParentAggregator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_node(uid, group, parent=None, score=None):
    """Minimal stand-in for a lazyllm DocNode."""
    node = types.SimpleNamespace()
    node._uid = uid
    node._group = group
    node._parent = parent   # DocNode-like object or uid string
    node.similarity_score = score
    return node


def _make_document_mock(target_nodes):
    """Return a mock that behaves like document.find(group)(nodes)."""
    doc = MagicMock()
    doc.find.return_value = MagicMock(return_value=target_nodes)
    return doc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_empty_input_returns_empty():
    doc = _make_document_mock([])
    agg = ScoreAwareParentAggregator(doc, target_group='block')
    assert agg([]) == []


def test_already_in_target_group_returns_unchanged():
    """If the first node is already in the target group, skip aggregation."""
    block = _make_node('b1', 'block', score=0.9)
    doc = _make_document_mock([block])
    agg = ScoreAwareParentAggregator(doc, target_group='block')
    result = agg([block])
    assert result == [block]
    doc.find.assert_not_called()


def test_score_formula_single_child():
    """One child hit: aggregated = max_score + hit_weight * 1."""
    parent = _make_node('p1', 'block')
    child = _make_node('c1', 'line', parent=parent, score=0.8)

    doc = _make_document_mock([parent])
    agg = ScoreAwareParentAggregator(doc, target_group='block', hit_weight=0.05)
    result = agg([child])

    assert len(result) == 1
    assert abs(result[0].similarity_score - (0.8 + 0.05 * 1)) < 1e-9


def test_score_formula_multiple_children_same_parent():
    """Three children -> hit_count=3, max of their scores is used."""
    parent = _make_node('p1', 'block')
    c1 = _make_node('c1', 'line', parent=parent, score=0.5)
    c2 = _make_node('c2', 'line', parent=parent, score=0.9)
    c3 = _make_node('c3', 'line', parent=parent, score=0.7)

    doc = _make_document_mock([parent])
    agg = ScoreAwareParentAggregator(doc, target_group='block', hit_weight=0.05)
    result = agg([c1, c2, c3])

    expected = 0.9 + 0.05 * 3   # max_score=0.9, hits=3
    assert len(result) == 1
    assert abs(result[0].similarity_score - expected) < 1e-9


def test_sorting_descending_by_aggregated_score():
    """Block with more hits should rank above block with a higher single score."""
    p_many = _make_node('p_many', 'block')
    p_single = _make_node('p_single', 'block')

    # p_single: one child at 0.95 -> 0.95 + 0.05*1 = 1.00
    # p_many: five children at 0.85 each -> max 0.85 + 0.05*5 = 1.10 (hits pull it above)
    children = (
        [_make_node('c_single', 'line', parent=p_single, score=0.95)]
        + [_make_node(f'c_many_{i}', 'line', parent=p_many, score=0.85) for i in range(5)]
    )

    doc = _make_document_mock([p_many, p_single])
    agg = ScoreAwareParentAggregator(doc, target_group='block', hit_weight=0.05)
    result = agg(children)

    assert result[0]._uid == 'p_many'
    scores = [n.similarity_score for n in result]
    assert scores == sorted(scores, reverse=True)


def test_uid_string_parent_is_handled():
    """parent can be a uid string (remote / db-backed node); must not crash."""
    parent = _make_node('p1', 'block')
    # child._parent is just the uid string, not a DocNode object
    child = _make_node('c1', 'line', parent='p1', score=0.6)

    doc = _make_document_mock([parent])
    agg = ScoreAwareParentAggregator(doc, target_group='block', hit_weight=0.1)
    result = agg([child])

    assert len(result) == 1
    assert abs(result[0].similarity_score - (0.6 + 0.1 * 1)) < 1e-9


def test_none_similarity_score_treated_as_zero():
    """similarity_score=None must not crash; treated as 0.0."""
    parent = _make_node('p1', 'block')
    child = _make_node('c1', 'line', parent=parent, score=None)

    doc = _make_document_mock([parent])
    agg = ScoreAwareParentAggregator(doc, target_group='block', hit_weight=0.05)
    result = agg([child])

    assert abs(result[0].similarity_score - (0.0 + 0.05 * 1)) < 1e-9
