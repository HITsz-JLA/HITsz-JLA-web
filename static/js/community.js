(() => {
  'use strict';
  const page = document.querySelector('[data-community-page]');
  if (!page) return;
  const notice = document.getElementById('community-notice');

  async function request(url, options = {}) {
    const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', ...options, signal: AbortSignal.timeout(20000) });
    let data;
    try { data = await response.json(); } catch { throw new Error('服务暂时不可用，请稍后重试。'); }
    if (!response.ok) {
      const error = new Error(data.message || '服务暂时不可用，请稍后重试。');
      error.status = response.status;
      error.fields = data.errors;
      throw error;
    }
    return data;
  }

  // Serialize initial cookie creation when dialogs are opened in quick succession.
  let tokenQueue = Promise.resolve();
  function getTokens() {
    const result = tokenQueue.then(() => request('/community/api/csrf/'));
    tokenQueue = result.catch(() => {});
    return result;
  }

  const composers = new Map();
  page.querySelectorAll('[data-community-form]').forEach(form => {
    const dialog = form.closest('dialog');
    const status = form.querySelector('[data-form-status]');
    const submitButton = form.querySelector('[type=submit]');
    const reconnect = form.querySelector('[data-reconnect]');
    const body = form.elements.namedItem('body');
    const count = form.querySelector('[data-body-count]');
    const kind = form.dataset.kind;
    const label = kind === 'song' ? '提交歌曲推荐' : '提交留言';
    let csrf = null;
    let receivedAt = 0;
    let requestId = crypto.randomUUID();
    let connecting = false;
    let submitting = false;
    const setStatus = (text, state = '') => { status.textContent = text; status.dataset.state = state; };
    body.addEventListener('input', () => { count.textContent = `${body.value.length} / 2000`; });

    async function connect() {
      if (connecting || submitting) return;
      connecting = true;
      submitButton.disabled = true;
      submitButton.textContent = '正在连接…';
      reconnect.hidden = true;
      try {
        csrf = await getTokens();
        receivedAt = Date.now();
        submitButton.disabled = false;
        submitButton.textContent = label;
        setStatus('');
      } catch {
        csrf = null;
        submitButton.textContent = '服务暂时不可用';
        setStatus('暂时无法连接投稿服务，填写内容已保留。请稍后重试。', 'error');
        reconnect.hidden = false;
      } finally {
        connecting = false;
      }
    }
    reconnect.addEventListener('click', connect);
    dialog.querySelector('[data-close-dialog]').addEventListener('click', () => dialog.close());
    composers.set(kind, () => {
      if (!dialog.open) dialog.showModal();
      if (!csrf || Date.now() - receivedAt > 3600000) connect();
    });

    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (submitting || !form.reportValidity() || !csrf) return;
      submitting = true;
      submitButton.disabled = true;
      submitButton.textContent = '正在提交…';
      setStatus('');
      const data = Object.fromEntries(new FormData(form).entries());
      data.consent = form.elements.namedItem('consent').checked;
      data.request_id = requestId;
      data.form_token = csrf.form_token;
      try {
        const wait = 2200 - (Date.now() - receivedAt);
        if (wait > 0) await new Promise(resolve => setTimeout(resolve, wait));
        await request(`/community/api/submissions/${kind}/`, {
          method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf.csrf_token }, body: JSON.stringify(data),
        });
        form.reset();
        count.textContent = '0 / 2000';
        requestId = crypto.randomUUID();
        notice.textContent = kind === 'song' ? '歌曲推荐已收到！审核后将进入候选曲目。' : '留言已收到！审核通过后会显示在下方留言区。';
        notice.dataset.state = 'success';
        if (dialog.open) dialog.close();
      } catch (error) {
        const fields = error.fields ? Object.entries(error.fields).map(([field, errors]) => {
          const labelText = form.elements.namedItem(field)?.labels?.[0]?.textContent || field;
          return `${labelText}：${errors[0].message}`;
        }).join('\n') : '';
        setStatus(fields || error.message || '网络连接中断，内容已保留，请重试。', 'error');
        if (error.status === 403) {
          csrf = null;
          reconnect.hidden = false;
        }
        if (dialog.open) status.focus();
      } finally {
        submitting = false;
        submitButton.disabled = !csrf;
        submitButton.textContent = label;
      }
    });
  });

  page.querySelectorAll('[data-compose]').forEach(button => {
    button.addEventListener('click', () => composers.get(button.dataset.compose)?.());
  });
  const initialComposer = new URLSearchParams(location.search).get('compose');
  // Only these known values can open a dialog from an old bookmarked URL.
  if (composers.has(initialComposer)) composers.get(initialComposer)();

  const list = document.getElementById('feedback-list');
  const next = document.getElementById('load-more');
  const retry = document.getElementById('retry-list');
  let currentPage = 0;
  let loading = false;
  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };
  function renderNote(item) {
    const article = node('article', 'community-note');
    const heading = node('div', 'community-note-header');
    heading.append(node('span', 'community-note-author', item.nickname));
    if (item.category) heading.append(node('span', 'community-note-tag', item.category));
    heading.append(node('time', 'community-note-date', item.date));
    article.append(heading, node('p', 'community-note-body', item.body));
    if (item.reply) {
      const reply = node('div', 'community-reply');
      reply.append(node('strong', '', '日语社回复'), document.createTextNode(item.reply));
      article.append(reply);
    }
    return article;
  }
  async function load() {
    if (loading) return;
    loading = true;
    next.disabled = true;
    retry.hidden = true;
    try {
      const data = await request(`/community/api/feedback/?page=${currentPage + 1}`);
      if (currentPage === 0) list.replaceChildren();
      data.items.forEach(item => list.append(renderNote(item)));
      if (!data.total) list.append(node('div', 'community-empty', '这里还没有公开留言。欢迎分享你的想法。'));
      document.getElementById('public-count').textContent = `${data.total} 条公开留言`;
      currentPage = data.page;
      next.hidden = !data.has_next;
    } catch {
      if (currentPage === 0) list.replaceChildren(node('div', 'community-empty', '暂时无法读取留言，请稍后再试。'));
      retry.hidden = false;
    } finally {
      loading = false;
      next.disabled = false;
    }
  }
  next.addEventListener('click', load);
  retry.addEventListener('click', load);
  load();
})();
