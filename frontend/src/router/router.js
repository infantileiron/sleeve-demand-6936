import {sleeves} from '../pages/sleeves.js';
import {usage} from '../pages/usage.js';
import {analyze} from '../pages/analyze.js';
import {reports} from '../pages/reports.js';
const routes = {sleeves, usage, analyze, reports};
export function route() {
  const [page, id] = location.hash.slice(1).split('/');
  if (Object.hasOwn(routes, page)) return [page, () => routes[page](/^\d+$/.test(id) ? Number(id) : null)];
  return ['sleeves', sleeves];
}
