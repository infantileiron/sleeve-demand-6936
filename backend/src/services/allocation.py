"""按库存配料：在「大一号代用」约束下，让尽可能多的领料单整单领齐。

需求模型
--------
每张领料单包含若干行 ``(规格, 数量)``。一行需求只能由本规格，或由该规格登记的
「大一号」代用规格来满足；未登记代用规格的材料只收原规格。

求解思路
--------
1. 先用最大流判断一组领料单能否全部满足（每行需求可选原规格或代用规格）。
2. 在领料单集合上做分支定界：优先让更多领料单整单领齐；数量相同时，让整单
   领齐的需求总量更大；仍相同时按提交先后（编号小者优先）稳定取舍。
3. 整单领齐的集合确定后，剩余库存按提交先后顺序部分配给尚未领齐的单据，
   形成缺口，供旧单查询「现在能领什么」。实发时优先原规格，原规格不足才用
   登记的大一号代用规格。

算法只依赖标准库，便于单元测试；输入输出均为普通 dict。
"""

from collections import deque
from functools import lru_cache

_INF = 10 ** 15
# 超过该规模时退回贪心，避免分支定界在异常数据上失控。
_MAX_EXACT = 16
_FLOW_BUDGET = 20000


class _TooComplex(Exception):
    pass


class _Dinic:
    def __init__(self, size):
        self.size = size
        self.graph = [[] for _ in range(size)]

    def add(self, source, target, capacity):
        forward = [target, capacity, len(self.graph[target])]
        backward = [source, 0, len(self.graph[source])]
        self.graph[source].append(forward)
        self.graph[target].append(backward)

    def _levels(self, source, sink):
        self.level = [-1] * self.size
        self.level[source] = 0
        queue = deque([source])
        while queue:
            node = queue.popleft()
            for target, capacity, _ in self.graph[node]:
                if capacity > 0 and self.level[target] < 0:
                    self.level[target] = self.level[node] + 1
                    queue.append(target)
        return self.level[sink] >= 0

    def _augment(self, node, sink, limit):
        if node == sink:
            return limit
        while self.cursor[node] < len(self.graph[node]):
            edge = self.graph[node][self.cursor[node]]
            target, capacity, reverse = edge
            if capacity > 0 and self.level[target] == self.level[node] + 1:
                pushed = self._augment(target, sink, min(limit, capacity))
                if pushed:
                    edge[1] -= pushed
                    self.graph[target][reverse][1] += pushed
                    return pushed
            self.cursor[node] += 1
        return 0

    def max_flow(self, source, sink):
        total = 0
        while self._levels(source, sink):
            self.cursor = [0] * self.size
            while True:
                pushed = self._augment(source, sink, _INF)
                if not pushed:
                    break
                total += pushed
        return total


def choices(code, substitutes):
    """一行需求可用的规格：本规格优先，其次登记的大一号规格。"""
    substitute = substitutes.get(code)
    return [code] if not substitute or substitute == code else [code, substitute]


def _flow_alloc(lines, stock, substitutes):
    """在给定库存下为一组需求行求最大流分配。

    返回 ``({行下标: {规格: 数量}}, 已分配总量)``，行下标与 ``lines`` 对应。
    """
    specs = sorted({spec for code, _ in lines for spec in choices(code, substitutes)
                    if stock.get(spec, 0) > 0})
    index = {spec: i for i, spec in enumerate(specs)}
    line_count = len(lines)
    source = 0
    line_base = 1
    spec_base = line_base + line_count
    sink = spec_base + len(specs)
    network = _Dinic(sink + 1)
    spec_edges = {}
    for position, (code, units) in enumerate(lines):
        network.add(source, line_base + position, units)
        for spec in choices(code, substitutes):
            if spec in index:
                network.add(line_base + position, spec_base + index[spec], _INF)
                spec_edges[(position, spec)] = len(network.graph[line_base + position]) - 1
    for spec in specs:
        network.add(spec_base + index[spec], sink, int(stock[spec]))
    network.max_flow(source, sink)

    # 反向边残留容量即该边通过的正向流量。
    flow = {}
    used = 0
    for (position, spec), edge_index in spec_edges.items():
        target, _, reverse = network.graph[line_base + position][edge_index]
        shipped = network.graph[target][reverse][1]
        if shipped:
            flow.setdefault(position, {})[spec] = shipped
            used += shipped
    _prefer_original(lines, flow, stock, substitutes)
    return flow, used


def _prefer_original(lines, flow, stock, substitutes):
    """在不改变可行性的前提下，把可代用部分的实发规格换回本规格。"""
    shipped_per_spec = {}
    for per_spec in flow.values():
        for spec, units in per_spec.items():
            shipped_per_spec[spec] = shipped_per_spec.get(spec, 0) + units
    for position, (code, _) in enumerate(lines):
        substitute = substitutes.get(code)
        if not substitute or substitute == code:
            continue
        per_spec = flow.get(position, {})
        on_substitute = per_spec.get(substitute, 0)
        if not on_substitute:
            continue
        free = stock.get(code, 0) - shipped_per_spec.get(code, 0)
        moved = min(on_substitute, max(free, 0))
        if moved:
            per_spec[code] = per_spec.get(code, 0) + moved
            shipped_per_spec[code] = shipped_per_spec.get(code, 0) + moved
            per_spec[substitute] = on_substitute - moved
            shipped_per_spec[substitute] -= moved
            if not per_spec[substitute]:
                del per_spec[substitute]


def _combine(demands, subset):
    combined = []
    mapping = []
    for demand_index in subset:
        for code, units in demands[demand_index]['lines']:
            combined.append((code, units))
            mapping.append(demand_index)
    return combined, mapping


def _feasible(demands, subset, stock, substitutes):
    combined, _ = _combine(demands, subset)
    _, used = _flow_alloc(combined, stock, substitutes)
    return used == sum(units for _, units in combined)


def _selected_allocation(demands, subset, stock, substitutes):
    chosen = sorted(subset)
    combined, mapping = _combine(demands, chosen)
    allocation, _ = _flow_alloc(combined, stock, substitutes)
    result = {index: {} for index in chosen}
    per_spec_used = {}
    for position, demand_index in enumerate(mapping):
        code = combined[position][0]
        per_spec = allocation.get(position, {})
        if not per_spec:
            continue
        result[demand_index][code] = dict(per_spec)
        for spec, units in per_spec.items():
            per_spec_used[spec] = per_spec_used.get(spec, 0) + units
    return result, per_spec_used


def _exact_selection(demands, stock, substitutes):
    count = len(demands)
    best = {'set': None}
    calls = [0]

    @lru_cache(maxsize=None)
    def feasible(subset):
        calls[0] += 1
        if calls[0] > _FLOW_BUDGET:
            raise _TooComplex
        return _feasible(demands, subset, stock, substitutes)

    def better(candidate, current):
        """优先整单数更多；同数时按提交先后（字典序更小的子集）先到先得。"""
        if current is None:
            return True
        if len(candidate) != len(current):
            return len(candidate) > len(current)
        return candidate < current

    def visit(index, chosen):
        # 即使余下全部选上也凑不出更多整单，剪枝。
        if best['set'] is not None and len(chosen) + (count - index) < len(best['set']):
            return
        if index == count:
            candidate = tuple(chosen)
            if better(candidate, best['set']):
                best['set'] = candidate
            return
        candidate = tuple(chosen + [index])
        if feasible(candidate):
            visit(index + 1, chosen + [index])
        visit(index + 1, chosen)

    visit(0, [])
    return best['set'] or ()


def _greedy_selection(demands, stock, substitutes):
    chosen = []
    remaining = dict(stock)
    for index, demand in enumerate(demands):
        allocation, used = _flow_alloc(demand['lines'], remaining, substitutes)
        requested = sum(units for _, units in demand['lines'])
        if used == requested:
            chosen.append(index)
            for per_spec in allocation.values():
                for spec, units in per_spec.items():
                    remaining[spec] = remaining.get(spec, 0) - units
    return chosen


def plan(demands, stock, substitutes):
    """为领料单生成配料方案。

    ``demands``：按提交先后排列的 ``[{'id': ..., 'lines': [(规格, 剩余数量), ...]}]``。
    ``stock``：``{规格: 可用数量}``。
    ``substitutes``：``{规格: 大一号代用规格}``。

    返回 ``(allocations, remaining)``：
    ``allocations[id] = {需求规格: {实发规格: 数量}}``，``remaining`` 为配料后的库存。
    """
    if not demands:
        return {}, dict(stock)
    if len(demands) > _MAX_EXACT:
        selected = _greedy_selection(demands, stock, substitutes)
    else:
        try:
            selected = _exact_selection(demands, stock, substitutes)
        except _TooComplex:
            selected = _greedy_selection(demands, stock, substitutes)

    allocations = {demand['id']: {code: {} for code, _ in demand['lines']} for demand in demands}
    allocated, used = _selected_allocation(demands, selected, stock, substitutes)
    chosen = set(selected)
    remaining = dict(stock)
    for spec, units in used.items():
        remaining[spec] = remaining.get(spec, 0) - units
    for demand_index in selected:
        for code, per_spec in allocated[demand_index].items():
            allocations[demands[demand_index]['id']][code] = dict(per_spec)

    # 剩余库存按提交先后部分配给未领齐的单据，缺口即未覆盖部分。
    for index, demand in enumerate(demands):
        if index in chosen:
            continue
        partial, _ = _flow_alloc(demand['lines'], remaining, substitutes)
        for position, (code, _) in enumerate(demand['lines']):
            per_spec = partial.get(position, {})
            if not per_spec:
                continue
            allocations[demand['id']][code] = dict(per_spec)
            for spec, units in per_spec.items():
                remaining[spec] = remaining.get(spec, 0) - units
    return allocations, remaining
