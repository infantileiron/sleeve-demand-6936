import {h} from '../../utils/html.js';
export function strip(rows) {
  const items = rows.slice(0,24).reverse();
  if (!items.length) return '';
  const max = Math.max(1, ...items.map(x => x.units || 0));
  return `<figure class="trend"><figcaption>最近 ${items.length} 条周记录 · 张</figcaption><div>${items.map(row => {
    const key = row.state === 'missing' ? '缺传' : row.units;
    return `<span class="${row.state === 'missing' ? 'gap' : 'bar'}" style="--ratio:${Number(row.units || 0) / max}" title="${h(`${row.week} ${key}`)}"></span>`;
  }).join('')}</div><small>${h(items[0].week)} — ${h(items.at(-1).week)}　橙色虚线为缺传</small></figure>`;
}
