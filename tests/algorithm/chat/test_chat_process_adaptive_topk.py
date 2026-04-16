import pytest

from chat.components.process.adaptive_topk import (
    AdaptiveKComponent,
    _fit_by_budget,
    _moving_average,
    adaptive_k_select_from_nodes,
)


class DummyNode:
    def __init__(self, uid, text='text', score=0.0):
        self.uid = uid
        self.text = text
        self.relevance_score = score


def test_adaptive_topk_helpers_and_score_gap_selection():
    nodes = [
        DummyNode('a', score=0.95),
        DummyNode('b', score=0.90),
        DummyNode('c', score=0.40),
        DummyNode('d', score=0.39),
    ]

    assert _moving_average([1.0, 3.0, 5.0], 3) == pytest.approx([5 / 3, 3.0, 13 / 3])
    assert _fit_by_budget(nodes, lambda n: {'a': 4, 'b': 4, 'c': 4, 'd': 4}[n.uid], 9) == 2

    selected, k, diag = adaptive_k_select_from_nodes(
        nodes,
        get_score=lambda n: n.relevance_score,
        bias=0,
        k_min=1,
    )

    assert [node.uid for node in selected] == ['a', 'b']
    assert k == 2
    assert diag['argmax_idx'] == 1
    assert diag['k_before_budget'] == 2


def test_adaptive_topk_sorts_unsorted_nodes_and_applies_budget():
    nodes = [
        DummyNode('low', score=0.1, text='x' * 4),
        DummyNode('high', score=0.9, text='x' * 8),
        DummyNode('mid', score=0.5, text='x' * 8),
    ]

    selected, k, diag = adaptive_k_select_from_nodes(
        nodes,
        get_score=lambda n: n.relevance_score,
        get_token_len=lambda n: len(n.text) // 4,
        assume_sorted_desc=False,
        max_tokens=3,
        default_k=3,
        gap_tau=1.0,
    )

    assert [node.uid for node in selected] == ['high']
    assert k == 1
    assert diag['tokens_used'] == 2


def test_adaptive_k_component_forwards_kwargs():
    component = AdaptiveKComponent(get_score=lambda n: n.relevance_score, default_k=1, gap_tau=1.0)
    nodes = [DummyNode('a', score=0.3), DummyNode('b', score=0.2)]

    selected = component(nodes, k_min=2)

    assert [node.uid for node in selected] == ['a', 'b']
