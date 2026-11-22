from datetime import date, timedelta
from math import ceil
from statistics import mean


def croston_sba(values, alpha):
    first = next((i for i, units in enumerate(values) if units > 0), None)
    if first is None:
        return 0.0
    size, spacing, last = values[first], first + 1, first
    for i in range(first + 1, len(values)):
        if values[i] > 0:
            size += alpha * (values[i] - size)
            spacing += alpha * (i - last - spacing)
            last = i
    return (1 - alpha / 2) * size / spacing


def contiguous(records):
    if not records:
        raise ValueError('请先录入该规格的领用周')
    by_week = {date.fromisoformat(row['week']): row for row in records}
    week = max(by_week)
    if by_week[week]['state'] != 'observed':
        raise ValueError('最近一周缺传，补齐后才能预测')
    recent = []
    while week in by_week and by_week[week]['state'] == 'observed':
        recent.append(by_week[week]['units'])
        week -= timedelta(days=7)
    return recent[::-1], max(by_week)


def analyze(records, config):
    values, last_week = contiguous(records)
    horizon, width = config['lead_weeks'], config['baseline_weeks']
    minimum_train = max(12, width)
    if len(values) < minimum_train + horizon + 5 or sum(units > 0 for units in values[:minimum_train]) < 2:
        raise ValueError('缺传后历史不足。至少需 6 个可回测起点，且首个训练窗口至少有 2 周正领用量')
    rows, errors = [], {'SBA': [], '移动平均': []}
    for origin in range(minimum_train, len(values)-horizon+1):
        train, actual = values[:origin], sum(values[origin:origin+horizon])
        sba = croston_sba(train, config['alpha']) * horizon
        naive = mean(train[-width:]) * horizon
        errors['SBA'].append(sba - actual)
        errors['移动平均'].append(naive - actual)
        origin_begin = last_week - timedelta(weeks=len(values)-origin-1)
        rows.append({'首个预测周': origin_begin.isoformat(), '实际领用': actual, 'SBA': round(sba,2),
                     '移动平均': round(naive,2), 'SBA 误差': round(sba-actual,2), '移动平均误差': round(naive-actual,2)})
    mae = {key: mean(map(abs, values)) for key, values in errors.items()}
    winner = min(mae, key=mae.get)
    weekly = croston_sba(values, config['alpha']) if winner == 'SBA' else mean(values[-width:])
    total = horizon * weekly
    packs = ceil(total / config['pack_size'])
    return {'summary': f'本次采用{winner}。从 {(last_week+timedelta(weeks=1)).isoformat()} 起覆盖 {horizon} 周，预计领用 {total:.2f} 张，按 {config["pack_size"]} 张/包备 {packs} 包。',
            'metrics': {'连续周数': len(values), '周均预测（张）': round(weekly,3), '建议备料（包）': packs,
                        'SBA MAE': round(mae['SBA'],3), '移动平均 MAE': round(mae['移动平均'],3)},
            'rows': rows[::-1], 'notes': ['每个回测起点只用更早的周记录，比较交货周期内总领用 MAE。',
                       '历史相邻窗口可能重叠。本表使用点预测，备料量未扣现存库存或在途。']}
