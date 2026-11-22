import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.services.allocation import plan


def demand(order_id, *lines):
    return {'id': order_id, 'lines': list(lines)}


def test_all_orders_filled_when_abundant():
    demands = [demand(1, ('A', 4)), demand(2, ('B', 6))]
    allocations, remaining = plan(demands, {'A': 10, 'B': 10}, {})
    assert allocations[1] == {'A': {'A': 4}}
    assert allocations[2] == {'B': {'B': 6}}
    assert remaining == {'A': 6, 'B': 4}


def test_two_workstations_competing_no_oversell():
    # 库存 A 只有 5；两张单各要 5，只有一张能整单领齐。
    demands = [demand(1, ('A', 5)), demand(2, ('A', 5))]
    allocations, remaining = plan(demands, {'A': 5}, {})
    assert allocations[1] == {'A': {'A': 5}}
    assert allocations[2] == {'A': {}}
    assert remaining['A'] == 0


def test_substitute_chain_not_followed_twice():
    # A 可代用 A，但 B 只收原规格，不因 A 可代用而借用 B。
    allocations, _ = plan([demand(1, ('B', 3))], {'A': 10, 'B': 0}, {'A': 'B'})
    assert allocations[1]['B'] == {}
