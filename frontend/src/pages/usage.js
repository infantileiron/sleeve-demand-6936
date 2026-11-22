import {api} from '../api/archive.js';
import {heading} from '../components/common/layout.js';
import {table} from '../components/common/table.js';
import {strip} from '../components/common/strip.js';
import {states} from '../constants/enums.js';
import {onForm} from '../hooks/forms.js';
import {canWrite} from '../stores/session.js';
import {h} from '../utils/html.js';

let selected = 'SL-A4';
export async function usage() {
  const skus = await api.sleeves();
  const chosen = skus.find(sku => sku.code === selected) || skus[0];
  if (!chosen) return {html:heading('领用周序列','先登记封套规格，再录入领用周。')};
  const rows = await api.usage(chosen.code);
  const missing = rows.filter(row => row.state === 'missing');
  const form = `<section class="sheet tools"><h2>登记或补报</h2><p>${h(chosen.title)}</p><form id="usage-form">
    <label>补报目标<select name="amend"><option value="">新周</option>${missing.map(row => `<option value="${row.id}">${h(row.week)}</option>`).join('')}</select></label>
    <label>周一日期<input name="week" type="date" required></label>
    <label>状态<select name="state"><option value="observed">已核</option><option value="missing">缺传</option></select></label>
    <label>领用张数<input name="units" type="number" min="0" max="10000"></label>
    <button type="submit">保存领用周</button><p role="alert"></p></form></section>`;
  return {
    html:heading('领用周序列', '核定零领用周填 0。缺传周保留空值；预测仅使用最新连续实收周。') +
      `<div class="workarea"><section class="sheet"><h2>领用收据</h2><label class="filter">封套规格<select id="sku">${skus.map(x => `<option value="${h(x.code)}" ${x.code===chosen.code?'selected':''}>${h(x.title)}</option>`).join('')}</select></label>
       ${strip(rows)}<div class="tall">${table(['周一日期','状态','领用量 / 张'], rows.map(x => [x.week,states[x.state],x.units ?? '缺传']), '本规格尚未录入领用。')}</div></section>${canWrite() ? form : ''}</div>`,
    bind(root, refresh) {
      root.querySelector('#sku').addEventListener('change', event => { selected = event.target.value; refresh(); });
      const form = root.querySelector('#usage-form');
      form?.elements.amend.addEventListener('change', event => {
        const row = missing.find(x => String(x.id) === event.target.value);
        if (row) form.elements.week.value = row.week;
        form.elements.week.readOnly = Boolean(row);
      });
      onForm(form, async data => {
        await api.recordUsage({sleeve_code:chosen.code, week:data.week, state:data.state, units:data.units === '' ? null : Number(data.units)}, data.amend);
        refresh();
      });
    }
  };
}
