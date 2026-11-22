import {h} from '../../utils/html.js';
import {roles} from '../../constants/enums.js';
const menu = [['sleeves','规格账本'],['usage','领用周序列'],['analyze','滚动回测'],['reports','领用备料单']];
export function shell(body, page, user) {
  return `<header class="masthead"><a class="brand" href="#sleeves">槐页修复 <span>材料调度</span></a>
    <nav aria-label="业务模块">${menu.map(([link, label]) => `<a href="#${link}" ${page === link ? 'aria-current="page"' : ''}>${h(label)}</a>`).join('')}</nav>
    <div class="identity"><span>${h(roles[user.role])}</span><button class="secondary" id="logout">退出</button></div></header>
    <main>${body}<footer>槐页修复 · 档案材料账</footer></main>`;
}
export function heading(title, detail) { return `<div class="heading"><h1>${h(title)}</h1><p>${h(detail)}</p></div>`; }
