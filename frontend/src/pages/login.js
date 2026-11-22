import {api} from '../api/archive.js';
import {onForm} from '../hooks/forms.js';
import {setSession} from '../stores/session.js';

export function login(root, refresh) {
  root.innerHTML = `<main class="login"><section class="envelope"><div class="tab">槐页修复</div>
    <div><h1>无酸封套<br>领用预测</h1><p>核对领用和缺传周，按到货周期生成备料单。</p></div></section>
    <section class="sheet signin"><h2>进入材料调度</h2><form id="login-form">
      <label>邮箱<input name="email" type="email" value="analyst@huaiye.demo" required autocomplete="username"></label>
      <label>密码<input name="password" type="password" value="Archive2026!" required autocomplete="current-password"></label>
      <button type="submit">登录</button><p role="alert"></p></form></section></main>`;
  onForm(root.querySelector('#login-form'), async data => { setSession(await api.login(data)); refresh(); });
}
