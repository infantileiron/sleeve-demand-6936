import {send} from './client.js';
export const api = {
  login: data => send('/auth/login', data),
  sleeves: input => send('/sleeves', input),
  usage: code => send('/usage' + (code ? `?sleeve_code=${encodeURIComponent(code)}` : '')),
  recordUsage: (input, id) => send(id ? `/usage/${id}/amend` : '/usage', input),
  analyses: input => send('/analyses', input),
  analysis: id => send(`/analyses/${id}`),
  publish: (id, note) => send(`/analyses/${id}/publish`, {note}),
  export: id => send(`/analyses/${id}/export`, undefined, true),
};
