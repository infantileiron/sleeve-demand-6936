import pytest

from src.services.allocation import plan


def run(demands, stock, substitutes):
    return plan(demands, stock, substitutes)


def test_original_only_when_no_substitute():
    allocations, remaining = run([{'id': 1, 'lines': [('C', 5)]}], {'C': 0, 'D': 100}, {})
    assert allocations[1]['C'] == {}
    assert remaining['D'] == 100


def test_substitute_fills_shortfall():
    allocations, remaining = run([{'id': 1, 'lines': [('A', 5)]}], {'A': 2, 'B': 10}, {'A': 'B'})
    assert allocations[1]['A'] == {'A': 2, 'B': 3}
    assert remaining == {'A': 0, 'B': 7}


def test_prefers_original_when_available():
    allocations, _ = run([{'id': 1, 'lines': [('A', 4)]}], {'A': 10, 'B': 10}, {'A': 'B'})
    assert allocations[1]['A'] == {'A': 4}


def test_maximises_whole_orders_over_partial():
    # A 需要 10（可用 A5+B5），B 单只需 B5。整单只能保一张，取需求量大的 A 单。
    allocations, remaining = run(
        [{'id': 1, 'lines': [('A', 10)]}, {'id': 2, 'lines': [('B', 5)]}],
        {'A': 5, 'B': 5}, {'A': 'B'})
    assert allocations[1]['A'] == {'A': 5, 'B': 5}
    assert allocations[2]['B'] == {}
    assert remaining == {'A': 0, 'B': 0}


def test_everyone_can_be_filled_when_stock_sufficient():
    allocations, remaining = run(
        [{'id': 1, 'lines': [('A', 10)]}, {'id': 2, 'lines': [('B', 5)]}],
        {'A': 10, 'B': 5}, {})
    assert allocations[1]['A'] == {'A': 10}
    assert allocations[2]['B'] == {'B': 5}
    assert remaining == {'A': 0, 'B': 0}


def test_tie_prefers_earlier_order():
    # 同为一整单，先提交的单优先。
    allocations, _ = run(
        [{'id': 7, 'lines': [('A', 5)]}, {'id': 9, 'lines': [('A', 5)]}],
        {'A': 5}, {})
    assert allocations[7]['A'] == {'A': 5}
    assert allocations[9]['A'] == {}


def test_partial_allocation_goes_to_unfilled_orders_in_order():
    allocations, _ = run(
        [{'id': 1, 'lines': [('A', 10)]}, {'id': 2, 'lines': [('A', 4)]}],
        {'A': 6}, {})
    # 1 整单需要 10，库存只有 6；2 需要 4。整单优先 2，剩余 2 给 1。
    assert allocations[2]['A'] == {'A': 4}
    assert allocations[1]['A'] == {'A': 2}


def test_multiline_order_partial():
    allocations, _ = run(
        [{'id': 1, 'lines': [('A', 5), ('B', 5)]}], {'A': 5, 'B': 0}, {})
    assert allocations[1]['A'] == {'A': 5}
    assert allocations[1]['B'] == {}


def test_no_mutation_of_input_stock():
    stock = {'A': 5}
    plan([{'id': 1, 'lines': [('A', 5)]}], stock, {})
    assert stock == {'A': 5}
