import {api} from '../api/archive.js';
import {heading} from '../components/common/layout.js';
import {states} from '../constants/enums.js';
import {onForm} from '../hooks/forms.js';
import {canWrite} from '../stores/session.js';
import {h} from '../utils/html.js';

export async function analyze() {
  const [skus, runs] = await Promise.all([api.sleeves(), api.analyses()]);
  return {
    html: heading('滚动回测', '按相同交货周期比较 Croston-SBA 和移动平均，展示每个起点的来源与误差。') +
      `<div class="workarea reverse"><section class="sheet"><h2>新建备料测算</h2>${canWrite() ? `
      <form id="analysis-form"><label>单据标题<input name="title" required value="修复组下批封套备料"></label>
      <label>封套规格<select name="sleeve_code">${skus.map(x => `<option value="${h(x.code)}" ${x.code==='SL-A4'?'selected':''}>${h(x.title)}（${x.lead_weeks} 周）</option>`).join('')}</select></label>
      <label>SBA 平滑系数<input name="alpha" type="number" min=".05" max=".5" step=".01" value=".2" required></label>
      <label>移动平均窗口 / 周<input name="baseline_weeks" type="number" min="4" max="16" value="8" required></label>
      <button type="submit">锁定快照并回测</button><p role="alert"></p></form>` : '<p>观察员可查看测算记录。</p>'}</section>
      <section class="sheet"><h2>最近测算</h2><ul class="runs">${runs.map(x => `<li><a href="#reports/${x.id}">${h(x.title)}</a><span>${h(states[x.status])}</span></li>`).join('') || '<li>首次回测后会出现记录。</li>'}</ul></section></div>`,
    bind(root) { onForm(root.querySelector('#analysis-form'), async data => {
      const run = await api.analyses({...data, alpha:Number(data.alpha), baseline_weeks:Number(data.baseline_weeks)});
      location.hash = `reports/${run.id}`;
    }); }
  };
}
