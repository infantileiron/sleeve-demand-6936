import {api} from '../api/archive.js';
import {heading} from '../components/common/layout.js';
import {table} from '../components/common/table.js';
import {requisitionStates} from '../constants/enums.js';
import {onForm} from '../hooks/forms.js';
import {canWrite} from '../stores/session.js';
import {h} from '../utils/html.js';

function newKey() {
  return `req-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function lineRows(skus, focus) {
  return skus.map(sku => `<tr data-line>
    <td><select name="sleeve_code">${skus.map(x => `<option value="${h(x.code)}" ${x.code===focus?'selected':''}>${h(x.code)} · ${h(x.title)}</option>`).join('')}</select></td>
    <td><input name="units" type="number" min="1" max="10000" value="1" required></td>
    <td><button type="button" class="secondary" data-remove>移除</button></td></tr>`).join('');
}

function orderCard(order) {
  const lines = order.lines.map(line => {
    const allocation = line.allocation.length
      ? line.allocation.map(x => `${h(x.sleeve_code)} ${x.units}`).join(' + ') : '—';
    return `<tr><td>${h(line.sleeve_code)}</td><td>${line.requested_units}</td><td>${line.issued_units}</td>
      <td>${line.reserved_units}</td><td>${line.shortage_units}</td><td>${allocation}</td></tr>`;
  }).join('');
  const canIssue = order.status !== 'issued' && order.totals.reserved_units > 0;
  return `<article class="order" data-order="${order.id}">
    <header><h3>${h(order.workstation_title)} · 单 #${order.id}</h3><span class="state">${h(requisitionStates[order.status] || order.status)}</span></header>
    <p>领料周 ${h(order.week)} · 申请 ${order.totals.requested_units} 张 · 已发 ${order.totals.issued_units} 张
      · 已配料 ${order.totals.reserved_units} 张 · 缺口 ${order.totals.shortage_units} 张</p>
    <div class="scroll"><table><thead><tr><th>需求规格</th><th>申请</th><th>已发</th><th>配料</th><th>缺口</th><th>实发规格</th></tr></thead><tbody>${lines}</tbody></table></div>
    ${canWrite() && canIssue ? `<button type="button" data-issue="${order.id}">领取实发（配料占用）</button>` : ''}
  </article>`;
}

export async function fulfillment() {
  const data = await api.fulfillment();
  const skus = await api.sleeves();
  const stockRows = data.stock.map(row => [
    `${row.sleeve_code} · ${row.title}`, row.substitute_code || '只收原规格',
    row.on_hand, row.reserved, row.available < 0 ? `${row.available}（超占）` : row.available,
  ]);
  const stockTable = table(['规格', '代用规格', '现存', '已配料占用', '可用'], stockRows, '尚无库存，请先入库或盘点。');
  const orders = data.requisitions.map(orderCard).join('') || '<p class="empty">还没有领料单。</p>';
  const workstationOptions = data.workstations.map(x => `<option value="${h(x.code)}">${h(x.title)}</option>`).join('');

  const submitForm = canWrite() ? `<section class="sheet tools"><h2>新建领料单</h2>
    <form id="order-form">
      <input type="hidden" name="request_key" value="${newKey()}">
      <label>工位<select name="workstation_code" required>${workstationOptions}</select></label>
      <label>领料周（周一）<input name="week" type="date" required></label>
      <table class="lines"><thead><tr><th>规格</th><th>申请张数</th><th></th></tr></thead>
        <tbody id="line-body">${lineRows(skus, skus[0]?.code)}</tbody></table>
      <div class="row-actions"><button type="button" class="secondary" id="add-line">添加一行</button>
        <button type="submit">提交并配料</button></div>
      <p role="alert"></p>
    </form>
    <p class="notes">同一提交编号重试不会重复占用；提交后按库存重排，整单领不齐即列为缺口。</p></section>` : '';

  const stockForms = canWrite() ? `<section class="sheet tools"><h2>入库与盘点</h2>
    <div class="workarea split">
      <form id="receive-form"><h3>入库</h3><label>规格<select name="sleeve_code">${skus.map(x => `<option value="${h(x.code)}">${h(x.code)} · ${h(x.title)}</option>`).join('')}</select></label>
        <label>入库张数<input name="units" type="number" min="1" required></label><button type="submit">登记入库</button><p role="alert"></p></form>
      <form id="take-form"><h3>盘点校正</h3><label>规格<select name="sleeve_code">${skus.map(x => `<option value="${h(x.code)}">${h(x.code)} · ${h(x.title)}</option>`).join('')}</select></label>
        <label>实盘张数<input name="counted_units" type="number" min="0" required></label>
        <label>备注<input name="note"></label><button type="submit">盘点并重排未领</button><p role="alert"></p></form>
    </div></section>` : '';

  const reconcileForm = canWrite() ? `<section class="sheet tools"><h2>周核清</h2>
    <form id="reconcile-form"><label>领料周（周一）<input name="week" type="date" required></label>
      <label>核清说明<input name="note"></label><button type="submit">合并实发并核清该周</button><p role="alert"></p></form>
    <p class="notes">同一周同规格的实发记录合并为该周领用；未核清的周仍记为缺传。</p></section>` : '';

  return {
    html: heading('配料与缺口', '按库存把整单领齐；盘点后只重排未领部分，已发料不挪。旧单可查当前可领数量。') +
      `<div class="workarea"><section class="sheet"><h2>库存与占用</h2>${stockTable}
        <h3>按单号查询</h3><form id="lookup-form" class="inline"><input name="id" type="number" min="1" placeholder="领料单编号" required><button type="submit">查询</button></form>
        <div id="lookup"></div></section>
      <div class="stack">${submitForm}${stockForms}${reconcileForm}</div></div>
      <section class="sheet"><h2>各工位领料单</h2><div class="orders">${orders}</div></section>`,
    bind(root, refresh) {
      if (!canWrite()) return;
      const body = root.querySelector('#line-body');
      const template = body?.querySelector('[data-line]');
      root.querySelector('#add-line')?.addEventListener('click', () => {
        const clone = template.cloneNode(true);
        clone.querySelector('input[name=units]').value = 1;
        body.append(clone);
      });
      body?.addEventListener('click', event => {
        const button = event.target.closest('[data-remove]');
        if (!button) return;
        if (body.querySelectorAll('[data-line]').length <= 1) return;
        button.closest('[data-line]').remove();
      });
      onForm(root.querySelector('#order-form'), async form => {
        const lines = [...body.querySelectorAll('[data-line]')].map(row => ({
          sleeve_code: row.querySelector('[name=sleeve_code]').value,
          units: Number(row.querySelector('[name=units]').value),
        }));
        await api.submitRequisition({workstation_code:form.workstation_code, week:form.week,
          request_key:form.request_key || null, lines});
        refresh();
      });
      onForm(root.querySelector('#receive-form'), async form => {
        await api.receiveStock({sleeve_code:form.sleeve_code, units:Number(form.units)}); refresh();
      });
      onForm(root.querySelector('#take-form'), async form => {
        await api.takeStock({sleeve_code:form.sleeve_code, counted_units:Number(form.counted_units), note:form.note});
        refresh();
      });
      onForm(root.querySelector('#reconcile-form'), async form => {
        await api.reconcileWeek({week:form.week, note:form.note}); refresh();
      });
      root.querySelectorAll('[data-issue]').forEach(button => button.addEventListener('click', async () => {
        button.disabled = true;
        try { await api.issueRequisition(Number(button.dataset.issue)); }
        finally { refresh(); }
      }));
      root.querySelector('#lookup-form')?.addEventListener('submit', async event => {
        event.preventDefault();
        const target = root.querySelector('#lookup');
        try {
          const order = await api.requisition(Number(event.target.elements.id.value));
          target.innerHTML = orderCard(order);
          target.querySelectorAll('[data-issue]').forEach(button => button.addEventListener('click', async () => {
            button.disabled = true;
            try { await api.issueRequisition(Number(button.dataset.issue)); }
            finally { refresh(); }
          }));
        } catch (error) { target.innerHTML = `<p role="alert">${h(error.message)}</p>`; }
      });
    }
  };
}
