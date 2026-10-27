let csrf = '';
let current = null;
const titles = {models: '模型配置', edits: '批量改图', skills: '技能包', word: 'Word 路由'};
const sections = {
  models: ['BASEURL', 'APIKEY', 'IMAGE_MODEL', 'IMAGE_DEFAULT_RESOLUTION', 'IMAGE_MAX_RETRIES', 'IMAGE_PROBE_RETRIES', 'VALIDATOR_BASEURL', 'VALIDATOR_APIKEY', 'VALIDATOR_MODEL', 'VALIDATOR_MAX_RETRIES', 'VALIDATOR_RESPONSE_FORMAT', 'VALIDATOR_REASONING_EFFORT'],
  edits: ['IMAGE_EDIT_MODEL', 'IMAGE_EDIT_FALLBACK_MODEL', 'IMAGE_EDIT_DEFAULT_RESOLUTION', 'IMAGE_EDIT_MAX_RETRIES'],
  word: ['WORD_AUTHORING_SKILL'],
};

function status(message, error = false) {
  const node = document.getElementById('state');
  node.textContent = message;
  node.classList.toggle('error', error);
}

async function api(path, values) {
  const response = await fetch(path, values === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
    body: JSON.stringify(values),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '请求失败');
  return data;
}

function text(tag, value, className = '') {
  const element = document.createElement(tag);
  element.textContent = value;
  element.className = className;
  return element;
}

function item(title, detail, statusText, removable) {
  const row = text('div', '', 'row');
  const info = text('div', '', 'row-info');
  info.append(text('strong', title), text('small', detail));
  row.append(info, text('span', statusText, statusText === 'available' ? 'tag good' : 'tag warn'));
  if (removable) {
    const button = text('button', '删除', 'remove');
    button.type = 'button';
    button.title = `删除 ${title}`;
    button.addEventListener('click', async () => {
      if (!window.confirm(`删除本地技能包 ${title}？`)) return;
      await busy(async () => { await api('/api/skills/delete', {id: removable}); await refresh(); }, '已删除');
    });
    row.append(button);
  }
  return row;
}

function render(data) {
  current = data;
  csrf = data.csrf;
  const choice = document.getElementById('word-choice');
  choice.replaceChildren();
  const options = [['auto', '自动（当前规则）'], ['minimaxdocx', 'minimax-docx'], ['officecli', 'officecli'],
    ...data.skills.filter(s => s.status === 'available').map(s => [s.id, s.id])];
  for (const [value, label] of options) {
    const option = document.createElement('option');
    option.value = value; option.textContent = label; choice.append(option);
  }
  for (const field of document.querySelectorAll('[data-key]')) {
    field.value = data.settings.values[field.dataset.key] || '';
    if (field.type === 'password') field.value = '';
  }
  for (const field of document.querySelectorAll('[data-status]')) {
    field.textContent = data.settings.secrets[field.dataset.status] ? '已配置' : '未配置';
  }
  const installed = document.getElementById('installed');
  installed.replaceChildren(...(data.skills.length ? data.skills.map(s => item(s.id, `${s.url} · ${s.revision.slice(0, 9)}`, s.status, s.id)) : [text('p', '尚无本地安装的技能包', 'empty')]));
  const integrations = document.getElementById('integrations');
  integrations.replaceChildren(...data.integrations.map(s => item(s.name, `${s.type || 'unknown'} · 内置，不可删除`, s.status)));
  const word = data.office.word_backend;
  document.getElementById('word-health').textContent = `当前编写：${word.selected} · ${word.status} ｜ 公共校验：officecli ${data.office.officecli_status}`;
  status('已同步');
}

async function refresh() { render(await api('/api/state')); }

async function busy(action, success) {
  status('处理中...');
  try { await action(); status(success); }
  catch (error) { status(error.message, true); }
}

for (const button of document.querySelectorAll('.nav')) {
  button.addEventListener('click', () => {
    for (const node of document.querySelectorAll('.nav, .panel')) node.classList.toggle('active', node.dataset.tab === button.dataset.tab || node.id === button.dataset.tab);
    document.getElementById('page-title').textContent = titles[button.dataset.tab];
  });
}

for (const button of document.querySelectorAll('[data-save]')) {
  button.addEventListener('click', () => busy(async () => {
    const values = {};
    for (const key of sections[button.dataset.save]) {
      const field = document.querySelector(`[data-key="${key}"]`);
      if (field.type !== 'password' || field.value) values[key] = field.value.trim();
    }
    await api('/api/settings', {values});
    await refresh();
  }, '已保存'));
}

document.getElementById('install').addEventListener('click', () => busy(async () => {
  const field = document.getElementById('skill-url');
  await api('/api/skills/install', {url: field.value.trim()});
  field.value = '';
  await refresh();
}, '安装完成'));

refresh().catch(error => status(error.message, true));
