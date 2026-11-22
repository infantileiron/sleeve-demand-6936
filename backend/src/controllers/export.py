import csv
import io
from fastapi import HTTPException, Response


def safe(value):
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def export(item):
    if not item.result:
        raise HTTPException(409, '预测结果尚未完成')
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['备料单', '状态', '结论'])
    writer.writerow([safe(item.title), item.status, safe(item.result['summary'])])
    for key, value in item.result['metrics'].items():
        writer.writerow([key, value])
    rows = item.result['rows']
    if rows:
        writer.writerow([])
        columns = ['首个预测周', '实际领用', 'SBA', '移动平均', 'SBA 误差', '移动平均误差']
        writer.writerow(columns)
        writer.writerows([safe(row[key]) for key in columns] for row in rows)
    return Response(content='\ufeff' + stream.getvalue(), media_type='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="sleeve-{item.id}.csv"'})
