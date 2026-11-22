import {api} from '../api/archive.js';
import {heading} from '../components/common/layout.js';
import {table} from '../components/common/table.js';
import {onForm} from '../hooks/forms.js';
import {canWrite} from '../stores/session.js';

export async function sleeves() {
  const rows = await api.sleeves();
  const form = `<section class="sheet tools"><h2>登记规格</h2><form id="sku-form">
      <label>规格编号<input name="code" required placeholder="SL-A3"></label><label>规格名称<input name="title" required></label>
      <label>张数 / 包<input name="pack_size" type="number" min="1" max="10000" required></label>
      <label>到货周期 / 周<input name="lead_weeks" type="number" min="1" max="8" required></label>
      <button type="submit">登记封套</button><p role="alert"></p></form></section>`;
  return {
    html: heading('规格账本', '单次领用以张计，备料按完整包装向上取整。') +
      `<div class="workarea"><section class="sheet"><h2>无酸与惰性材料</h2>${table(['规格编号','材料','张数 / 包','到货周期 / 周'], rows.map(x => [x.code,x.title,x.pack_size,x.lead_weeks]), '暂无封套规格。')}</section>${canWrite() ? form : ''}</div>`,
    bind(root, refresh) { onForm(root.querySelector('#sku-form'), async data => {
      await api.sleeves({...data, pack_size:Number(data.pack_size), lead_weeks:Number(data.lead_weeks)}); refresh();
    }); }
  };
}
