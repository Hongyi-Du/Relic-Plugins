// Relic App page. The window bar on top has the sidebar switch, back and forward, the menus and the right-side panes
// (installed as an application, it is the title bar). The sidebar lists organizations by name with the open one's chats
// (group chat, secretary, members); the middle shows a chat; the right side shows the organization, a member's
// workspace, a file or a thread. Data comes from /api/...; changes arrive on /api/events (server-sent events).
(() => {
  'use strict';

  // writes carry the server's token; a restarted server has a new one, which only this page's origin can read
  let TOKEN = document.querySelector('meta[name="relic-token"]').content;
  const $ = (sel, root) => (root || document).querySelector(sel);
  const HUMAN = 'human';
  const enc = encodeURIComponent;

  // ------------------------------------------------------------------ dom helpers
  function append(node, kids) {
    for (const kid of kids) {
      if (kid == null || kid === false) continue;
      if (Array.isArray(kid)) { append(node, kid); continue; }
      node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
  }
  function h(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') n.className = v;
      else if (k === 'style') n.style.cssText = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? '' : String(v));
    }
    append(n, kids);
    return n;
  }
  const ICONS = {
    plus: 'M12 5v14M5 12h14',
    search: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4',
    up: 'M12 19V5M5 12l7-7 7 7',
    panel: 'M4 5h16v14H4zM15 5v14',
    card: 'M4 6h16v12H4zM8 10h4M8 14h8',
    trace: 'M4 6h10M4 12h16M4 18h12',
    stop: 'M7 7h10v10H7z',
    x: 'M6 6l12 12M18 6L6 18',
    bell: 'M6 16V11a6 6 0 0 1 12 0v5l2 2H4l2-2zM10 20h4',
    gear: 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z',
    chev: 'M9 6l6 6-6 6',
    down: 'M6 9l6 6 6-6',
    edit: 'M4 20h4L19 9l-4-4L4 16zM14 6l4 4',
    neworg: 'M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z',
    hash: 'M5 9h14M5 15h14M10 3L8 21M16 3l-2 18',
    mic: 'M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3',
    quote: 'M7 7h4v4H8c0 2 1 3 3 3v2c-3 0-5-2-5-5zM14 7h4v4h-3c0 2 1 3 3 3v2c-3 0-5-2-5-5z',
    thread: 'M4 5h16v10H9l-5 4z',
    copy: 'M8 8h11v11H8zM5 16V5h11',
    user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 20c1.5-4 5-5 8-5s6.5 1 8 5',
    palette: 'M12 3a9 9 0 1 0 0 18c1 0 1.5-.6 1.5-1.4 0-.9-.7-1.3-.7-2.1 0-.8.7-1.5 1.6-1.5H17a4 4 0 0 0 4-4c0-5-4-9-9-9zM7.5 11.5h.01M10 7.5h.01M15 7.5h.01',
    globe: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c2.5 2.7 3.5 6 3.5 9s-1 6.3-3.5 9c-2.5-2.7-3.5-6-3.5-9s1-6.3 3.5-9z',
    plug: 'M9 7V3M15 7V3M7 7h10v4a5 5 0 0 1-10 0zM12 16v5',
    info: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 11v6M12 7.5h.01',
    folder: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
    sec: 'M12 3l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.4 6.8 19.1l1-5.8-4.3-4.1 5.9-.9z',
    check: 'M5 12l5 5 9-10',
    file: 'M6 3h8l4 4v14H6zM14 3v4h4',
    lang: 'M4 5h8M8 3v2M6 5c0 4 3 7 6 8M10 5c-1 4-4 7-6 8M13 21l4-9 4 9M14.5 18h5',
    sparkle: 'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z',
    back: 'M15 6l-6 6 6 6',
    fwd: 'M9 6l6 6-6 6',
    sidebar: 'M4 5h16v14H4zM9 5v14',
    work: 'M4 7h16v12H4zM9 7V5h6v2',
    download: 'M12 4v11M7 10l5 5 5-5M5 20h14',
    open: 'M14 4h6v6M20 4l-9 9M18 14v6H4V6h6',
    org: 'M4 21V8l8-5 8 5v13M9 21v-6h6v6M8.5 11h.01M15.5 11h.01',
  };
  function icon(name, size = 18) {
    const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    s.setAttribute('viewBox', '0 0 24 24');
    s.setAttribute('width', size);
    s.setAttribute('height', size);
    s.setAttribute('aria-hidden', 'true');
    const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    p.setAttribute('d', ICONS[name] || ICONS.info);
    p.setAttribute('fill', 'none');
    p.setAttribute('stroke', 'currentColor');
    p.setAttribute('stroke-width', '1.7');
    p.setAttribute('stroke-linecap', 'round');
    p.setAttribute('stroke-linejoin', 'round');
    s.append(p);
    return s;
  }

  // ------------------------------------------------------------------ formatting
  function hue(name) {
    let n = 7;
    for (const ch of String(name)) n = (n * 31 + ch.codePointAt(0)) >>> 0;
    const hues = [18, 30, 42, 205, 222, 248, 272, 300, 330, 350, 190, 12];
    return hues[n % hues.length];
  }
  function initial(text) {
    const s = String(text || '?').trim();
    const first = [...s][0] || '?';
    return /[a-z]/i.test(first) ? first.toUpperCase() : first;
  }
  const toDate = (iso) => { if (!iso) return null; const d = new Date(iso); return isNaN(d) ? null : d; };
  const pad = (n) => String(n).padStart(2, '0');
  function dayLabel(d) {
    const today = new Date(); const y = new Date(); y.setDate(today.getDate() - 1);
    if (d.toDateString() === today.toDateString()) return '今天';
    if (d.toDateString() === y.toDateString()) return '昨天';
    return (d.getFullYear() !== today.getFullYear() ? d.getFullYear() + '年' : '') + (d.getMonth() + 1) + '月' + d.getDate() + '日';
  }
  function clock(iso) { const d = toDate(iso); return d ? pad(d.getHours()) + ':' + pad(d.getMinutes()) : ''; }
  function shortWhen(iso) {
    const d = toDate(iso); if (!d) return '';
    const label = dayLabel(d);
    return label === '今天' ? clock(iso) : label === '昨天' ? '昨天' : (d.getMonth() + 1) + '/' + d.getDate();
  }
  function ago(iso) {
    const d = toDate(iso); if (!d) return '';
    const s = (Date.now() - d.getTime()) / 1000;
    if (s < 60) return '刚刚';
    if (s < 3600) return Math.floor(s / 60) + ' 分钟前';
    if (s < 86400) return Math.floor(s / 3600) + ' 小时前';
    return dayLabel(d);
  }
  const clip = (s, n) => { s = String(s || '').replace(/\s+/g, ' ').trim(); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
  const STATE_LABEL = { running: '运行中', working: '工作中', active: '刚有动作', waiting: '等你批准', starting: '启动中', error: '出错',
    idle: '空闲', vacant: '还没有会话' };
  const TASK_LABEL = { open: '待办', working: '进行中', blocked: '受阻', done: '完成', dropped: '放弃' };

  // an absolute path in a message opens in the file preview on the right (files in a member's workspace only)
  const PATH_RE = /^[A-Za-z]:[\\/]/;
  function pathLink(t) {
    const m = /^(.*?)(?::(\d+))?(?::\d+)?$/.exec(t);
    return h('a', { class: 'path', href: '#', title: '在右侧预览', onclick: (e) => { e.preventDefault(); openFile(m[1], m[2] ? Number(m[2]) : 0); } }, t);
  }
  function inline(text) {
    const out = [];
    const re = /(`[^`\n]+`|\*\*[^*\n]+\*\*|https?:\/\/[^\s<>)）\]]+|\b[A-Za-z]:[\\/][^\s<>"'|*?，。；：、（）)\]【】「」《》“”]+)/g;
    let last = 0, m;
    while ((m = re.exec(text))) {
      if (m.index > last) out.push(text.slice(last, m.index));
      const t = m[0];
      if (t[0] === '`') { const c = t.slice(1, -1); out.push(h('code', null, PATH_RE.test(c) ? pathLink(c) : c)); }
      else if (t.startsWith('**')) out.push(h('b', null, t.slice(2, -2)));
      else if (PATH_RE.test(t)) { const core = t.replace(/[.,;:!?]+$/, ''); out.push(pathLink(core)); if (core.length < t.length) out.push(t.slice(core.length)); }
      else out.push(h('a', { href: t, target: '_blank', rel: 'noopener noreferrer' }, t));
      last = m.index + t.length;
    }
    if (last < text.length) out.push(text.slice(last));
    return out;
  }
  function rich(text) {
    const nodes = [];
    String(text || '').split('```').forEach((part, i) => {
      if (i % 2 === 1) {
        const lines = part.split('\n');
        if (/^[\w+.-]*$/.test(lines[0])) lines.shift();
        nodes.push(h('pre', null, h('code', null, lines.join('\n').replace(/\n$/, ''))));
        return;
      }
      for (const block of part.split(/\n{2,}/)) {
        // a block can mix lines of text, list items, quotes, headings and a table: each run becomes its own element
        let run = [], kind = null;
        const flush = () => { if (run.length) nodes.push(mdRun(kind, run)); run = []; };
        for (const l of block.split('\n')) {
          if (!l.trim()) continue;
          let k = /^\s*>/.test(l) ? 'quote' : /^\s*([-*•+]|\d+[.)])\s+/.test(l) ? 'list' : /^#{1,6}\s/.test(l) ? 'head' : /^\s*\|.*\|\s*$/.test(l) ? 'table' : 'text';
          if (k === 'text' && kind === 'list' && /^\s{2,}\S/.test(l)) k = 'list';  // a list item's continued line
          if (k !== kind || k === 'head') { flush(); kind = k; }
          run.push(l);
        }
        flush();
      }
    });
    return nodes;
  }
  function mdRun(kind, lines) {
    if (kind === 'quote') return quoteBlock(lines.map((l) => l.replace(/^\s*>\s?/, '')).join('\n'));
    if (kind === 'head') return h('h4', null, inline(lines[0].replace(/^#+\s*/, '')));
    if (kind === 'list') {
      const first = /^\s*(\d+)[.)]/.exec(lines[0]);
      const list = h(first ? 'ol' : 'ul', first && first[1] !== '1' ? { start: first[1] } : null);
      let li = null;
      for (const l of lines) {
        const m = /^(\s*)([-*•+]|\d+[.)])\s+(.*)$/.exec(l);
        if (m) { li = h('li', m[1].length >= 2 ? { class: 'sub' } : null, inline(m[3])); list.append(li); }
        else if (li) { li.append(h('br')); append(li, inline(l.trim())); }
      }
      return list;
    }
    if (kind === 'table') {
      const rule = (l) => /^\s*\|?\s*:?-{2,}/.test(l);
      const head = lines.length > 1 && rule(lines[1]);
      const table = h('table');
      lines.filter((l) => !rule(l)).forEach((l, i) => table.append(h('tr', null,
        l.trim().replace(/^\||\|$/g, '').split('|').map((c) => h(head && i === 0 ? 'th' : 'td', null, inline(c.trim()))))));
      return h('div', { class: 'table-wrap' }, table);
    }
    const p = h('p');
    lines.forEach((l, j) => { if (j) p.append(h('br')); append(p, inline(l)); });
    return p;
  }
  function quoteBlock(text) {
    const m = /^([^\n：:]{1,40})[：:]\s?([\s\S]*)$/.exec(text);
    return h('div', { class: 'quote' }, m ? [h('b', null, m[1] + '：'), m[2]] : text);
  }

  // ------------------------------------------------------------------ storage
  function load(key, fallback) { try { const v = localStorage.getItem(key); return v == null ? fallback : JSON.parse(v); } catch (e) { return fallback; } }
  function save(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* not kept */ } }

  // ------------------------------------------------------------------ api
  async function get(path) {
    const r = await fetch(path, { cache: 'no-store' });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || r.statusText);
    return d;
  }
  async function freshToken() {
    const page = await (await fetch('/', { cache: 'no-store' })).text();
    const m = /name="relic-token" content="([^"]+)"/.exec(page);
    if (m) TOKEN = m[1];
    return !!m;
  }
  async function post(path, body, again = true) {
    const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Relic-Token': TOKEN },
      body: JSON.stringify(body || {}) });
    const d = await r.json().catch(() => ({}));
    if (r.status === 403 && d.error === 'missing token' && again && await freshToken().catch(() => false)) return post(path, body, false);
    if (!r.ok) throw new Error(d.error || r.statusText);
    return d;
  }
  function toast(text, ms = 3600) {
    const t = h('div', { class: 'toast', role: 'status' }, text);
    document.body.append(t);
    setTimeout(() => t.remove(), ms);
  }

  // ------------------------------------------------------------------ preferences
  let PREFS = { theme: 'system', accent: 'clay', font: 'medium', density: 'comfortable', name: '', lang: '', notify: true, voice: 'browser', auto_names: true, paths: {} };
  function lang() { return PREFS.lang || navigator.language || 'zh-CN'; }
  function applyPrefs() {
    const root = document.documentElement;
    root.dataset.theme = PREFS.theme === 'system' ? '' : PREFS.theme;
    if (!root.dataset.theme) delete root.dataset.theme;
    root.dataset.accent = PREFS.accent || 'clay';
    root.dataset.font = PREFS.font || 'medium';
    root.dataset.density = PREFS.density || 'comfortable';
    const dark = PREFS.theme === 'dark' || (PREFS.theme === 'system' && matchMedia('(prefers-color-scheme: dark)').matches);
    document.querySelectorAll('meta[name="theme-color"]').forEach((m) => { m.content = dark ? '#191918' : '#F8F7F5'; m.removeAttribute('media'); });
    renderMe();
  }
  async function loadPrefs() {
    try { PREFS = Object.assign(PREFS, await get('/api/prefs')); } catch (e) { /* defaults */ }
    applyPrefs();
  }
  async function setPrefs(changes) {
    Object.assign(PREFS, changes);
    applyPrefs();
    try { Object.assign(PREFS, await post('/api/prefs', changes)); } catch (e) { toast('设置没存上：' + e.message); }
  }

  // ------------------------------------------------------------------ state
  const S = {
    orgs: [], orgId: load('relic.org', null), snap: null, harnesses: null,
    view: { kind: 'group', member: null }, chat: null, convo: null, live: {}, thread: null, threadData: null,
    search: '', to: ['all'], quote: null, panelOpen: load('relic.panel', true), collapsed: false, seen: {},
    mode: load('relic.mode', 'direct'),
    pane: load('relic.pane', 'org'), sideOpen: load('relic.side', true), hist: [], histIdx: -1, file: null, workMember: null,
    plain: {}, plainPending: new Set(), plainFailed: new Set(), plainOne: new Set(), plainMode: false,
    digest: null, digestPending: false, digestOpen: false,
  };
  if (!['org', 'work', 'file'].includes(S.pane)) S.pane = 'org';
  S.lastPane = S.pane;
  if (window.innerWidth <= 1180) S.panelOpen = false;  // narrow windows: the right side opens over the chat when asked for
  const plainOn = () => !!load('relic.plain.' + S.orgId, false);
  const orgPath = (rest) => '/api/org/' + enc(S.orgId) + (rest || '');
  const member = (name) => (S.snap && S.snap.members.find((m) => m.name === name)) || null;
  const secretaryName = () => S.snap && S.snap.org.secretary;
  const chatKey = () => S.view.kind === 'group' ? 'group' : 'member:' + S.view.member;
  const myName = () => PREFS.name || '你';
  function dname(name) {
    if (name === HUMAN) return myName();
    const m = member(name);
    return m ? m.display || name : name;
  }
  // a member named after the title it holds (负责人, 秘书) is shown by its id next to that title
  function roleName(name, title) { const d = dname(name); return d === title ? name : d; }

  // ------------------------------------------------------------------ avatars
  function avatar(name, opts = {}) {
    const size = opts.size ? ' ' + opts.size : '';
    if (name === HUMAN) {
      const a = h('div', { class: 'avatar human' + size, title: myName() }, PREFS.avatar ? h('img', { src: PREFS.avatar, alt: '' }) : initial(myName()));
      return a;
    }
    const m = member(name);
    const label = m ? m.display || name : name;
    const a = h('div', { class: 'avatar' + size + (opts.click !== false && m ? ' clickable' : ''), style: '--h:' + hue(name), title: label },
      m && m.avatar ? h('img', { src: m.avatar, alt: '' }) : initial(label));
    if (opts.dot && m && m.state !== 'idle') a.append(h('span', { class: 'dot ' + m.state }));
    if (opts.click !== false && m) a.addEventListener('click', (e) => { e.stopPropagation(); openCard(name, a); });
    return a;
  }
  function secAvatar(size) {
    const sec = member(secretaryName());
    const a = h('div', { class: 'avatar sec' + (size ? ' ' + size : '') }, sec && sec.avatar ? h('img', { src: sec.avatar, alt: '' }) : icon('sec', 16));
    if (sec && sec.state !== 'idle') a.append(h('span', { class: 'dot ' + sec.state }));
    return a;
  }
  function groupAvatar(size) { return h('div', { class: 'avatar group' + (size ? ' ' + size : '') }, icon('hash', size === 'sm' ? 14 : 17)); }

  // ------------------------------------------------------------------ loading
  async function loadOrgs() {
    S.orgs = await get('/api/orgs');
    if (!S.orgId || !S.orgs.some((o) => o.id === S.orgId)) S.orgId = S.orgs[0] ? S.orgs[0].id : null;
    renderSide();
  }
  // the address names the open chat: #/org/<id>, #/org/<id>/secretary, #/org/<id>/member/<name>
  function readHash() {
    const p = location.hash.replace(/^#\/?/, '').split('/').map((x) => { try { return decodeURIComponent(x); } catch (e) { return x; } });
    if (p[0] !== 'org' || !p[1]) return null;
    const view = p[2] === 'secretary' ? { kind: 'secretary', member: null } : p[2] === 'member' && p[3] ? { kind: 'member', member: p[3] } : { kind: 'group', member: null };
    return { org: p[1], view };
  }
  function writeHash() {
    if (!S.orgId) return;
    const v = S.view;
    const tail = v.kind === 'group' ? '' : v.kind === 'secretary' ? '/secretary' : '/member/' + enc(v.member);
    history.replaceState(null, '', '#/org/' + enc(S.orgId) + tail);
  }
  async function openOrg(id, wanted, fromHist) {
    S.orgId = id; save('relic.org', id);
    S.seen = load('relic.seen.' + id, {});
    S.live = {}; S.chat = null; S.convo = null; S.snap = null; S.thread = null; S.collapsed = false; S.quote = null;
    S.plain = {}; S.plainPending = new Set(); S.plainFailed = new Set(); S.plainOne = new Set(); S.plainMode = plainOn();
    S.digest = null; S.digestPending = false; S.digestOpen = !!load('relic.digest.' + id, false); S.workMember = null;
    if (S.pane === 'thread') S.pane = S.lastPane || 'org';
    renderSide();
    await refreshSnap();
    const v = wanted || load('relic.view.' + id, null);
    const sec = secretaryName();
    if (v && v.kind === 'secretary' && sec) S.view = { kind: 'secretary', member: sec };
    else if (v && (v.kind === 'group' || (v.kind === 'member' && member(v.member)))) S.view = { kind: v.kind, member: v.member || null };
    else S.view = { kind: 'group', member: null };
    writeHash();
    if (!fromHist) pushHist();
    renderAll(true);
    await loadChat(true);
    if (S.digestOpen && S.view.kind === 'group') loadDigest(false);
  }
  let lastAlert = null;
  async function refreshSnap() {
    if (!S.orgId) return;
    S.snap = await get(orgPath('?lang=' + enc(lang())));
    document.title = 'Relic · ' + S.snap.org.name;
    notifyChanges();
    renderSide(); renderPanel(true); renderHead(); renderAppbar();
  }
  async function loadChat(scrollEnd) {
    if (!S.orgId || !S.snap) return;
    const view = S.view;
    const keep = !scrollEnd && nearBottom();
    try {
      if (view.kind === 'group') {
        S.chat = await get(orgPath('/chat?kind=group&limit=1000'));
        S.convo = null;
      } else {
        const m = member(view.member);
        const [chat, convo, live] = await Promise.all([
          get(orgPath('/chat?kind=private&member=' + enc(view.member) + '&limit=1000')),
          m && m.has_transcript ? get(orgPath('/convo?member=' + enc(view.member))) : Promise.resolve(null),
          m && m.embedded ? get(orgPath('/live?member=' + enc(view.member))) : Promise.resolve(null)]);
        S.chat = chat; S.convo = convo;
        if (live) {
          const slot = liveSlot(view.member);
          live.items.forEach((it) => slot.items.set(it.seq, it));
          slot.status = live.status;
        }
      }
    } catch (e) {
      S.chat = { items: [], error: e.message };
    }
    if (view !== S.view) return;
    markSeen();
    renderStream(scrollEnd || keep);
    if (view.kind === 'group' && S.digestOpen) renderBanner();
    if (S.thread) loadThread();
  }
  function markSeen() {
    const head = S.snap && S.snap.chats && S.snap.chats[chatKey()];
    if (head && head.last) { S.seen[chatKey()] = head.last.id; save('relic.seen.' + S.orgId, S.seen); }
  }
  function unreadOf(key) {
    const head = S.snap && S.snap.chats && S.snap.chats[key];
    if (!head) return 0;
    const seen = S.seen[key] || 0;
    return head.ids.filter(([id, from]) => id > seen && from !== HUMAN).length;
  }
  let refreshTimer = 0;
  function scheduleRefresh() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(async () => {
      try { await refreshSnap(); await loadChat(false); } catch (e) { /* the next change retries */ }
    }, 400);
  }

  // ------------------------------------------------------------------ desktop notifications
  function notifyChanges() {
    if (!S.snap) return;
    const decisions = S.snap.decisions.length;
    let unread = 0;
    for (const key of Object.keys(S.snap.chats || {})) if (key !== 'group') unread += unreadOf(key);
    const now = { decisions, unread, org: S.orgId };
    if (lastAlert && lastAlert.org === S.orgId && PREFS.notify && document.hidden && 'Notification' in window && Notification.permission === 'granted') {
      if (decisions > lastAlert.decisions) new Notification('Relic · ' + S.snap.org.name, { body: '有 ' + decisions + ' 件事需要你决定', icon: '/static/icon-192.png' });
      else if (unread > lastAlert.unread) new Notification('Relic · ' + S.snap.org.name, { body: '有新消息发给你', icon: '/static/icon-192.png' });
    }
    lastAlert = now;
  }

  // ------------------------------------------------------------------ events
  function liveSlot(name) { return S.live[name] || (S.live[name] = { items: new Map(), status: null }); }
  function connect() {
    const es = new EventSource('/api/events');
    es.onmessage = (e) => {
      let ev; try { ev = JSON.parse(e.data); } catch (x) { return; }
      if (ev.type === 'orgs') { loadOrgs(); return; }
      if (ev.type === 'prefs') { loadPrefs().then(renderAll); return; }
      if (ev.type === 'install') { onInstall(ev); return; }
      if (ev.org !== S.orgId) return;
      if (ev.type === 'org' || ev.type === 'decision') scheduleRefresh();
      if (ev.type === 'plain') {
        gotPlain(ev.items || {}, (ev.ids || []).map(Number));
        if (ev.error) toast('翻译没成功：' + ev.error, 6000);
      }
      if (ev.type === 'digest') {
        S.digestPending = false;
        if (ev.error) toast('解读没成功：' + ev.error, 6000); else S.digest = ev.digest;
        if (S.view.kind === 'group') renderBanner();
      }
      if (ev.type === 'live') {
        const slot = liveSlot(ev.member);
        if (ev.item) slot.items.set(ev.item.seq, ev.item);
        if ('status' in ev) {
          slot.status = ev.status;
          const m = member(ev.member);
          if (m && ev.status) { m.state = ev.status.state; m.detail = ev.status.detail; m.doing = ev.status.doing || m.doing; }
          renderSide();
        }
        if (S.view.member === ev.member && S.view.kind !== 'group') renderLive(true);
      }
    };
    es.onerror = () => { /* the browser reconnects by itself */ };
    let opened = false;
    es.onopen = () => {  // back after the server restarted: new token, new embedded sessions, maybe missed changes
      if (opened) {
        S.live = {};
        freshToken().catch(() => {});
        loadOrgs().then(() => refreshSnap()).then(() => loadChat(false)).catch(() => {});
      }
      opened = true;
    };
  }

  // ------------------------------------------------------------------ sidebar
  function lastLine(head) {
    if (!head || !head.last) return '';
    const l = head.last;
    return (l.type === 'receipt' ? '[回执] ' : '') + dname(l.from) + '：' + clip(l.body.replace(/^\[Relic auto-receipt\]\s*/, '').replace(/^>.*\n+/gm, ''), 70);
  }
  function chatRow({ key, avatarNode, name, tags, sub, at, unread, on, onclick, title }) {
    return h('button', { class: 'chat-row' + (on ? ' on' : ''), type: 'button', onclick, 'data-key': key, title },
      avatarNode,
      h('div', { class: 'main' }, h('div', { class: 'name' }, h('span', { class: 'ellipsis' }, name), tags), sub ? h('div', { class: 'sub ellipsis' }, sub) : null),
      h('div', { class: 'side-info' }, at ? h('span', { class: 'time' }, shortWhen(at)) : null, unread ? h('span', { class: 'badge' }, unread > 99 ? '99+' : unread) : null));
  }
  function renderSide() {
    const tree = $('#tree'); tree.textContent = '';
    const q = S.search.trim().toLowerCase();
    tree.append(h('div', { class: 'sec-label' }, h('span', null, '组织'), h('span', null, S.orgs.length || '')));
    for (const o of S.orgs) {
      const active = o.id === S.orgId;
      const orgHit = !q || o.name.toLowerCase().includes(q) || (o.purpose || '').toLowerCase().includes(q);
      const memberHits = active && S.snap ? S.snap.members.filter((m) => !q || (m.display || '').toLowerCase().includes(q) || m.name.toLowerCase().includes(q) || (m.role || '').toLowerCase().includes(q)) : [];
      if (q && !orgHit && !memberHits.length) continue;
      const open = active && (!S.collapsed || q);
      const row = h('button', { class: 'org-row' + (active ? ' on' : '') + (open ? ' open' : ''), type: 'button', title: o.name + (o.purpose ? '\n' + o.purpose : ''),
        onclick: () => { if (active) { S.collapsed = !S.collapsed; renderSide(); } else openOrg(o.id); } },
        h('span', { class: 'chev' }, icon('chev', 14)),
        h('span', { class: 'org-badge', style: 'background:hsl(' + hue(o.id) + ' 40% 90%);color:hsl(' + hue(o.id) + ' 38% 34%)' }, initial(o.name)),
        h('span', { class: 'org-name' }, o.name),
        h('span', { class: 'meta' }, active ? '' : shortWhen(o.last_at)));
      tree.append(row);
      if (!open || !S.snap) continue;
      const kids = h('div', { class: 'kids' });
      const heads = S.snap.chats || {};
      const view = S.view;
      if (!q || '群聊'.includes(q) || orgHit) {
        kids.append(chatRow({ key: 'group', avatarNode: groupAvatar('sm'), name: '群聊', sub: lastLine(heads.group) || '成员之间的全部通信',
          at: heads.group && heads.group.last.at, unread: view.kind === 'group' ? 0 : unreadOf('group'), on: view.kind === 'group',
          onclick: () => go({ kind: 'group' }) }));
      }
      const sec = secretaryName();
      const secM = sec && member(sec);
      if (!q || '秘书'.includes(q) || (secM && memberHits.includes(secM))) {
        kids.append(chatRow({ key: 'secretary', avatarNode: secAvatar('sm'), name: sec ? '秘书' : '设置秘书',
          tags: secM ? [h('span', { class: 'tag sec' }, roleName(sec, '秘书'))] : null,
          sub: sec ? (lastLine(heads['member:' + sec]) || (secM.doing || secM.detail || '')) : '让一个会话做你和组织之间的联络人',
          at: sec && heads['member:' + sec] && heads['member:' + sec].last.at, unread: view.kind === 'secretary' ? 0 : (sec ? unreadOf('member:' + sec) : 0),
          on: view.kind === 'secretary', onclick: () => sec ? go({ kind: 'secretary', member: sec }) : openSecretarySetup() }));
      }
      for (const m of memberHits) {
        if (m.secretary) continue;
        const key = 'member:' + m.name;
        const isOn = view.kind === 'member' && view.member === m.name;
        const tags = [];
        if (m.leader) tags.push(h('span', { class: 'tag lead' }, '负责人'));
        kids.append(chatRow({ key, avatarNode: avatar(m.name, { size: 'sm', dot: true, click: false }), name: m.display || m.name, tags,
          title: m.name + (m.role ? ' · ' + m.role : ''),
          sub: m.doing ? '在做：' + m.doing : (lastLine(heads[key]) || m.role || STATE_LABEL[m.state] || ''),
          at: heads[key] ? heads[key].last.at : m.doing_at, unread: isOn ? 0 : unreadOf(key), on: isOn,
          onclick: () => go({ kind: 'member', member: m.name }) }));
      }
      kids.append(h('button', { class: 'add-row', type: 'button', onclick: () => memberDialog() }, icon('plus', 14), '添加成员'));
      tree.append(kids);
    }
    if (!S.orgs.length) tree.append(h('div', { class: 'empty', style: 'padding:8px 10px' }, '还没有组织。'));
  }
  function renderMe() {
    const me = $('#me'); if (!me) return;
    me.textContent = '';
    append(me, [avatar(HUMAN, { size: 'sm', click: false }), h('div', { class: 'main', style: 'min-width:0;display:grid' },
      h('span', { class: 'who ellipsis' }, myName()), h('span', { class: 'what ellipsis' }, '个人资料与设置'))]);
  }
  // back and forward go through the chats opened in this window, like Codex and Claude Code
  function pushHist() {
    const entry = { org: S.orgId, view: { kind: S.view.kind, member: S.view.member } };
    const last = S.hist[S.histIdx];
    if (last && last.org === entry.org && last.view.kind === entry.view.kind && last.view.member === entry.view.member) return;
    S.hist = S.hist.slice(0, S.histIdx + 1).concat([entry]).slice(-80);
    S.histIdx = S.hist.length - 1;
    renderAppbar();
  }
  async function goHist(delta) {
    const i = S.histIdx + delta;
    if (i < 0 || i >= S.hist.length) return;
    S.histIdx = i;
    const e = S.hist[i];
    if (e.org !== S.orgId) { if (S.orgs.some((o) => o.id === e.org)) await openOrg(e.org, e.view, true); }
    else if (e.view.kind === 'group' || member(e.view.member)) go(e.view, true);
    renderAppbar();
  }
  function toggleSide(force) {
    S.sideOpen = force != null ? !!force : !S.sideOpen;
    save('relic.side', S.sideOpen);
    $('#app').classList.toggle('no-side', !S.sideOpen);
    renderAppbar();
  }
  function go(view, fromHist) {
    S.view = { kind: view.kind, member: view.member || null };
    save('relic.view.' + S.orgId, S.view);
    writeHash();
    if (!fromHist) pushHist();
    S.to = ['all']; S.chat = null; S.convo = null; S.quote = null;
    renderAll(true);
    loadChat(true);
    if (S.view.kind === 'group' && S.digestOpen && !S.digest && !S.digestPending) loadDigest(false);
  }
  function renderAll(scrollEnd) { renderSide(); renderHead(); renderBanner(); renderStream(scrollEnd); renderComposer(); renderPanel(); renderAppbar(); }

  // ------------------------------------------------------------------ chat header and banner
  function renderHead() {
    const head = $('#chat-head'); head.textContent = '';
    if (!S.snap) { head.append(h('div', { class: 'title' }, h('h2', null, 'Relic'))); return; }
    if (S.view.kind === 'group') {
      const on = S.plainMode;
      append(head, [groupAvatar('sm'), h('div', { class: 'title' },
        h('h2', null, h('span', { class: 'ellipsis' }, '群聊'), h('span', { class: 'dim', style: 'font-weight:400' }, S.snap.members.length + ' 位成员')),
        h('div', { class: 'meta ellipsis' }, S.snap.org.name + ' · 成员之间的全部通信 · 自动唤醒' + (S.snap.org.auto_wake ? '开' : '关'))),
        h('div', { class: 'actions' },
          h('button', { class: 'chip-btn' + (on ? ' on' : ''), type: 'button', title: '把成员之间的话改写成不了解上下文也能看懂的话（Ctrl+Shift+L）', onclick: togglePlain }, icon('lang', 15), on ? '人话：开' : '翻译成人话'),
          h('button', { class: 'chip-btn' + (S.digestOpen ? ' on' : ''), type: 'button', title: '用几句话讲清群里最近在干什么', onclick: toggleDigest }, icon('sparkle', 15), '解读'),
          h('button', { class: 'icon-btn', title: '任务', 'aria-label': '任务', onclick: () => openDetails('tasks') }, icon('check')))]);
      return;
    }
    const m = member(S.view.member);
    const sec = S.view.kind === 'secretary';
    const name = m ? m.display || m.name : S.view.member;
    const titleKids = [h('span', { class: 'ellipsis' }, sec ? '秘书 · ' + roleName(S.view.member, '秘书') : name)];
    if (m && m.display && m.display !== m.name) titleKids.push(h('span', { class: 'dim mono', style: 'font-weight:400' }, m.name));
    if (m && m.leader) titleKids.push(h('span', { class: 'tag lead' }, '负责人'));
    const meta = m ? [S.snap.org.name, m.harness_label, m.surface_label, m.model, STATE_LABEL[m.state]].filter(Boolean).join(' · ') : S.snap.org.name;
    append(head, [sec ? secAvatar('sm') : avatar(S.view.member, { size: 'sm', dot: true }),
      h('div', { class: 'title' }, h('h2', null, titleKids), h('div', { class: 'meta ellipsis' }, meta)),
      h('div', { class: 'actions' },
        m && m.embedded && ['running', 'waiting'].includes(m.state) ? h('button', { class: 'icon-btn', title: '停止这一轮', 'aria-label': '停止这一轮',
          onclick: () => post(orgPath('/cancel'), { member: S.view.member }).catch((e) => toast(e.message)) }, icon('stop')) : null,
        h('button', { class: 'icon-btn', title: '名片', 'aria-label': '名片', onclick: (e) => openCard(S.view.member, e.currentTarget) }, icon('card')),
        h('button', { class: 'icon-btn', title: '上下文和轨迹', 'aria-label': '上下文和轨迹', onclick: () => openDetails('trace', { member: S.view.member }) }, icon('trace')),
        m && m.surface !== 'chat' ? h('button', { class: 'icon-btn', title: '它的工作区', 'aria-label': '它的工作区', onclick: () => { S.workMember = S.view.member; setPane('work'); } }, icon('work')) : null)]);
  }
  function renderBanner() {
    const box = $('#banner'); box.textContent = '';
    if (!S.snap) return;
    if (S.view.kind === 'group') { if (S.digestOpen) box.append(digestCard()); return; }
    const m = member(S.view.member);
    if (!m) return;
    let text = null, cls = 'banner';
    if (m.embedded) text = m.harness_label + ' 会话在 Relic App 里内嵌运行：你的消息直接进入它的会话，回复实时显示在这里。';
    else if (m.surface === 'subagent') { text = '这是 ' + (m.parent ? dname(m.parent) + ' 会话里的' : '') + ' subagent：这里显示它自己的完整记录。你发的消息会留在它的收件箱，等它下次调用工具时读到。'; cls += ' amber'; }
    else if (m.state === 'vacant') { text = '这个席位还没有会话，消息会一直等到有会话坐进来。'; cls += ' amber'; }
    else if (m.has_transcript) text = '这里显示它自己会话里的全部对话（动作默认折叠）。你在这里发的消息经 Relic 送到它的收件箱：它下一次调用工具时读到；席位配置了会话时会被自动唤醒。';
    else text = '你的消息经 Relic 送到它的收件箱：它下一次调用工具时读到；席位配置了会话时会被自动唤醒。';
    box.append(h('div', { class: cls }, icon('info', 15), h('span', null, text)));
  }

  // ------------------------------------------------------------------ stream
  function nearBottom() { const s = $('#stream'); return s.scrollHeight - s.scrollTop - s.clientHeight < 120; }
  function renderStream(scrollEnd) {
    const stream = $('#stream');
    const inner = $('#stream-inner');
    inner.textContent = '';
    if (plainObs) plainObs.disconnect();
    S.plainMode = plainOn();
    if (!S.snap) { inner.append(placeholder()); return; }
    if (!S.chat) { inner.append(h('div', { class: 'notice' }, h('span', null, '正在读取…'))); return; }
    if (S.chat.error) { inner.append(h('div', { class: 'notice' }, h('span', null, '读取失败：' + S.chat.error))); return; }
    const items = S.view.kind === 'group' ? S.chat.items : memberItems();
    if (!items.length && !liveItems().length) {
      inner.append(h('div', { class: 'notice', style: 'margin-top:40px' }, h('span', null, S.view.kind === 'group' ? '群里还没有消息' : '还没有对话，说点什么吧')));
    }
    let prev = null, lastDay = '';
    for (const it of items) {
      const d = toDate(it.at);
      const day = d ? d.toDateString() : '';
      if (day && day !== lastDay) { inner.append(h('div', { class: 'day' }, dayLabel(d) + ' ' + clock(it.at))); lastDay = day; prev = null; }
      else if (prev && d && toDate(prev.at) && d - toDate(prev.at) > 20 * 60000) { inner.append(h('div', { class: 'day' }, clock(it.at))); prev = null; }
      inner.append(renderItem(it, prev));
      prev = it.type === 'acts' ? prev : it;
    }
    inner.append(h('div', { id: 'live' }));
    renderLive(false);
    if (scrollEnd) stream.scrollTop = stream.scrollHeight;
  }
  // ------------------------------------------------------------------ 人话: what the agents say, rewritten for the person
  // Only messages the person scrolls to are explained; one Claude call (Sonnet) explains a batch and the server keeps
  // the results, so each message is explained once.
  let plainObs = null, plainTimer = 0;
  const plainQueue = new Set();
  function watchPlain(node) {
    if (!plainObs) {
      plainObs = new IntersectionObserver((entries) => {
        for (const e of entries) if (e.isIntersecting) { plainQueue.add(Number(e.target.dataset.id)); plainObs.unobserve(e.target); }
        clearTimeout(plainTimer);
        plainTimer = setTimeout(() => { const ids = [...plainQueue]; plainQueue.clear(); requestPlain(ids); }, 400);
      }, { root: $('#stream'), rootMargin: '300px 0px' });
    }
    plainObs.observe(node);
  }
  function plainState(id) {
    if (S.plainPending.has(id)) return h('span', { class: 'plain-wait' }, h('i', { class: 'spin' }), '正在翻译成人话…');
    if (S.plainFailed.has(id)) return h('button', { class: 'plain-wait retry', type: 'button', onclick: () => requestPlain([id]) }, '没翻译出来 · 重试');
    return h('span', { class: 'plain-wait' }, '等翻译…');
  }
  async function requestPlain(ids) {
    const fresh = ids.filter((i) => i && !S.plainPending.has(i) && !(i in S.plain));
    if (!fresh.length) return;
    fresh.forEach((i) => { S.plainPending.add(i); S.plainFailed.delete(i); });
    updatePlain(fresh);
    try {
      const r = await post(orgPath('/plain'), { ids: fresh });
      gotPlain(r.items || {}, Object.keys(r.items || {}).map(Number));
    } catch (e) {
      fresh.forEach((i) => { S.plainPending.delete(i); S.plainFailed.add(i); });
      updatePlain(fresh);
      toast('翻译没成功：' + e.message);
    }
  }
  // results for `ids`; an id this window asked for that came back without a text was skipped
  function gotPlain(items, ids) {
    for (const [k, v] of Object.entries(items)) S.plain[k] = v;
    for (const i of ids) if (S.plainPending.delete(i) && !(i in S.plain)) S.plainFailed.add(i);
    updatePlain(ids);
  }
  function updatePlain(ids) {
    for (const id of ids) {
      document.querySelectorAll('.msg[data-id="' + id + '"]').forEach((node) => {
        const ctx = RENDERED.get(node);
        if (ctx) node.replaceWith(renderItem(ctx.it, ctx.prev, ctx.where));
      });
    }
  }
  function togglePlain() {
    const on = !plainOn();
    save('relic.plain.' + S.orgId, on);
    S.plainMode = on;
    renderHead();
    renderStream(nearBottom());
    if (on) toast('只翻译你看到的消息：一批用一次 Claude 调用，翻好的会存下来。', 5000);
  }
  function togglePlainOne(id) {
    if (S.plainOne.has(id)) { S.plainOne.delete(id); updatePlain([id]); return; }
    S.plainOne.add(id);
    if (id in S.plain) updatePlain([id]); else requestPlain([id]);
  }
  // 解读: a few sentences on what the group has been doing, at the top of the group chat
  function toggleDigest() {
    S.digestOpen = !S.digestOpen;
    save('relic.digest.' + S.orgId, S.digestOpen);
    renderHead(); renderBanner();
    if (S.digestOpen && !S.digest && !S.digestPending) loadDigest(false);
  }
  async function loadDigest(refresh) {
    S.digestPending = true;
    if (S.view.kind === 'group') renderBanner();
    try {
      const r = await post(orgPath('/digest'), { refresh: !!refresh });
      if (r.digest) S.digest = r.digest;
      S.digestPending = !!r.pending;
      if (refresh && !r.pending) toast('之后没有新消息，解读已经是最新的。');
    } catch (e) { S.digestPending = false; toast('解读没成功：' + e.message); }
    if (S.view.kind === 'group') renderBanner();
  }
  function digestCard() {
    const d = S.digest;
    const newer = d && S.chat && S.chat.items ? S.chat.items.filter((x) => typeof x.id === 'number' && x.id > (d.last_id || 0)).length : 0;
    return h('div', { class: 'digest' },
      h('div', { class: 'digest-h' }, icon('sparkle', 15), h('b', null, '群里在干什么'),
        d ? h('span', { class: 'dim' }, '读了最近 ' + (d.count || 0) + ' 条 · ' + ago(new Date(d.at * 1000).toISOString()) + (newer ? ' · 之后又有 ' + newer + ' 条' : '')) : null,
        h('div', { style: 'flex:1' }),
        S.digestPending ? h('span', { class: 'plain-wait' }, h('i', { class: 'spin' }), '正在解读…') : h('button', { class: 'btn sm ghost', type: 'button', onclick: () => loadDigest(true) }, d ? '更新' : '解读'),
        secretaryName() ? h('button', { class: 'btn sm ghost', type: 'button', title: '在私聊里让秘书详细讲', onclick: askSecretary }, '问秘书') : null,
        h('button', { class: 'icon-btn', style: 'width:24px;height:24px', type: 'button', title: '收起', 'aria-label': '收起', onclick: toggleDigest }, icon('x', 14))),
      d ? h('div', { class: 'md' }, rich(d.text)) : h('div', { class: 'dim', style: 'font-size:12.5px' }, S.digestPending ? '正在读群里最近的消息，大约半分钟…' : '还没有解读。'));
  }
  async function askSecretary() {
    const sec = secretaryName();
    if (!sec) return;
    try {
      await post(orgPath('/send'), { to: [sec], channel: 'private',
        body: '请用我能看懂的话讲讲群聊最近在做什么：谁在做什么、为什么、做到哪一步了，有没有需要我决定或注意的事。' });
      go({ kind: 'secretary', member: sec });
    } catch (e) { toast(e.message); }
  }

  function placeholder() {
    return h('div', { class: 'placeholder', style: 'height:70vh' }, h('div', null, h('h2', null, '还没有组织'),
      h('p', null, '点左上方「新建组织」，或者在 Claude Code / Codex 里让 agent 用 Relic 组建组织。')));
  }
  function renderItem(it, prev, where) {
    if (it.type === 'notice') return h('div', { class: 'notice' }, h('span', null, it.text));
    if (it.type === 'acts') return actsBlock(it);
    if (it.type === 'receipt') {
      const text = it.body.replace(/^\[Relic auto-receipt\]\s*/, '');
      return h('div', { class: 'msg' }, avatar(it.from), h('div', { class: 'body' },
        h('div', { class: 'who' }, h('b', null, dname(it.from)), h('span', null, '自动回执 → ' + it.to.map(dname).join('、')), h('span', null, clock(it.at))),
        h('details', { class: 'receipt' }, h('summary', null, clip(text, 90)), h('pre', null, text))));
    }
    const mine = it.from === HUMAN;
    const cont = prev && prev.type === 'message' && prev.from === it.from && JSON.stringify(prev.to) === JSON.stringify(it.to) &&
      toDate(it.at) && toDate(prev.at) && toDate(it.at) - toDate(prev.at) < 3 * 60000 && !prev.thread;
    const who = h('div', { class: 'who' });
    if (!cont) {
      who.append(h('b', null, it.fromLabel || dname(it.from)));
      const m = member(it.from);
      if (m && (where || S.view.kind) === 'group') who.append(h('span', { class: 'mono', style: 'font-size:11px' }, m.name));
      if ((where || S.view.kind) === 'group' && it.to) {
        const all = S.snap.members.map((x) => x.name).filter((n) => n !== it.from);
        const toAll = all.length && all.every((n) => it.to.includes(n));
        who.append(h('span', null, '→ ' + (toAll ? '全体' : it.to.map(dname).join('、'))));
      }
      who.append(h('span', null, clock(it.at)));
    }
    const bubble = h('div', { class: 'bubble', 'data-from': it.from }, rich(it.body));
    const kids = [cont ? null : who];
    const explainable = !mine && typeof it.id === 'number';
    const groupPlain = S.plainMode && S.view.kind === 'group' && where !== 'thread';
    const wantPlain = explainable && (groupPlain || S.plainOne.has(it.id));
    if (wantPlain && S.plain[it.id]) {
      kids.push(h('div', { class: 'bubble plain', 'data-from': it.from }, h('div', { class: 'plain-h' }, icon('lang', 13), '人话'), rich(S.plain[it.id])),
        h('details', { class: 'orig' }, h('summary', null, '原文'), bubble));
    } else {
      kids.push(bubble);
      if (wantPlain) kids.push(plainState(it.id));
    }
    if (mine && it.read_by && it.to) {
      const others = it.to.filter((n) => n !== HUMAN);
      const read = it.read_by.filter((n) => others.includes(n));
      kids.push(h('div', { class: 'read' }, others.length === 1 ? (read.length ? '已读' : '未读') : (read.length + '/' + others.length + ' 已读')));
    }
    if (it.thread && where !== 'thread') {
      kids.push(h('button', { class: 'thread-link', type: 'button', onclick: () => openThread(it.id) },
        h('span', { class: 'faces' }, it.thread.people.slice(0, 3).map((p) => avatar(p, { size: 'xs', click: false }))),
        it.thread.count + ' 条回复', h('span', { class: 'dim' }, '· 最后回复 ' + shortWhen(it.thread.last_at))));
    }
    const acts = h('div', { class: 'hover-acts' },
      explainable && !groupPlain ? h('button', { type: 'button', title: S.plainOne.has(it.id) ? '收起人话' : '翻译成人话', onclick: () => togglePlainOne(it.id) }, icon('lang', 14), S.plainOne.has(it.id) ? '原文' : '人话') : null,
      h('button', { type: 'button', title: '引用', onclick: () => setQuote(it.fromLabel || dname(it.from), stripQuote(it.body)) }, icon('quote', 14), '引用'),
      it.id && typeof it.id === 'number' && where !== 'thread' ? h('button', { type: 'button', title: '在话题里回复', onclick: () => openThread(it.id) }, icon('thread', 14), '回复') : null,
      h('button', { type: 'button', title: '复制', onclick: () => copyText(it.body) }, icon('copy', 14)));
    const avatarNode = mine ? avatar(HUMAN) : (it.fromParent ? avatar(it.fromParent) : avatar(it.from));
    const node = h('div', { class: 'msg' + (mine ? ' mine' : '') + (cont ? ' cont' : '') + (it.from === secretaryName() && S.view.kind === 'group' ? ' sec' : ''), 'data-id': it.id || '' },
      avatarNode, h('div', { class: 'body' }, kids), acts);
    RENDERED.set(node, { it, prev, where });
    if (wantPlain && groupPlain && !(it.id in S.plain) && !S.plainPending.has(it.id) && !S.plainFailed.has(it.id)) watchPlain(node);
    return node;
  }
  const RENDERED = new WeakMap();  // message node -> what it shows, to redraw one message in place
  function stripQuote(body) { return String(body || '').replace(/^(>.*\n?)+\n*/, '').trim(); }
  function copyText(text) { navigator.clipboard.writeText(text).then(() => toast('已复制'), () => toast('复制失败')); }

  // a member's chat: its own session's whole conversation (all messages, actions folded) and what was written through Relic
  const APP_PREFIX = '[Relic App] The person (human) writes to you directly:';
  function memberItems() {
    const m = member(S.view.member);
    const steps = (S.convo && S.convo.steps) || [];
    const cut = liveTurnStart();
    const out = [];
    let acts = null;
    const flush = () => { if (acts) { out.push(acts); acts = null; } };
    for (const s of steps) {
      if (cut && toDate(s.at) && toDate(s.at) >= cut) continue;
      if (s.role === 'tool_call' || s.role === 'tool_result') {
        if (!acts) acts = { type: 'acts', at: s.at, steps: [], member: S.view.member };
        acts.steps.push(s);
        continue;
      }
      flush();
      const text = s.text || '';
      if (s.role === 'user') {
        if (text.startsWith(APP_PREFIX)) out.push({ type: 'message', from: HUMAN, to: [S.view.member], body: text.slice(APP_PREFIX.length).replace(/\n\nReply in this conversation;[\s\S]*$/, '').trim(), at: s.at });
        else if (text.startsWith('[Relic auto-wake]')) out.push({ type: 'notice', text: '被组织里的消息自动唤醒', at: s.at });
        else if (text.startsWith('You now hold the seat')) out.push({ type: 'notice', text: '入座说明', at: s.at });
        else if (m && m.agent) out.push({ type: 'message', from: m.parent || S.view.member, fromParent: m.parent, fromLabel: (m.parent ? dname(m.parent) : '父会话') + '（交给它的任务）', to: [S.view.member], body: text, at: s.at });
        else out.push({ type: 'message', from: HUMAN, to: [S.view.member], body: text, at: s.at });
      } else if (s.role === 'assistant') {
        out.push({ type: 'message', from: S.view.member, to: [HUMAN], body: text, at: s.at });
      }
    }
    flush();
    if (!m || !m.embedded || !S.convo) {
      for (const it of (S.chat ? S.chat.items : [])) out.push(it);
    }
    return out.map((it, i) => [it, i]).sort((a, b) => ((toDate(a[0].at) || 0) - (toDate(b[0].at) || 0)) || a[1] - b[1]).map((x) => x[0]);
  }
  function toolName(t) { return String(t || 'tool').replace(/^mcp__plugin_relic_org__|^mcp__relic_org__/, 'Relic ').replace(/^mcp__/, ''); }
  function stepArg(s) {
    let arg = s.text || '';
    try {
      const v = JSON.parse(arg);
      arg = v.command || v.cmd || v.file_path || v.pattern || v.url || v.query || v.description || v.prompt || v.path || v.body || JSON.stringify(v);
    } catch (e) { /* plain text */ }
    return clip(arg, 120);
  }
  function actsBlock(g) {
    // calls made in parallel come before their results: each result belongs to the oldest call still waiting
    const rows = [], waiting = [];
    for (const s of g.steps) {
      if (s.role === 'tool_call') { const row = { call: s, result: null }; rows.push(row); waiting.push(row); }
      else if (waiting.length) waiting.shift().result = s;
      else rows.push({ call: null, result: s });
    }
    const counts = {};
    rows.forEach((r) => { if (r.call) { const n = toolName(r.call.tool); counts[n] = (counts[n] || 0) + 1; } });
    const summary = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([n, c]) => n + (c > 1 ? ' ×' + c : '')).join(' · ');
    const failed = rows.filter((r) => r.result && r.result.error).length;
    const list = h('div', { class: 'list' });
    const box = h('details', { class: 'acts' }, h('summary', null, h('span', { class: 'chev' }, icon('chev', 13)),
      h('b', null, rows.length + ' 个动作'), h('span', { class: 'ellipsis' }, summary), failed ? h('span', { class: 'chip bad' }, failed + ' 个失败') : null,
      h('span', { style: 'margin-left:auto' }, clock(g.at))), list);
    box.addEventListener('toggle', () => {
      if (!box.open || list.childNodes.length) return;
      for (const { call, result } of rows) list.append(stepRow(g.member, call, result));
    }, { once: false });
    return h('div', { class: 'msg cont' }, h('div'), h('div', { class: 'body' }, box));
  }
  function stepRow(who, call, result) {
    const cls = 'step' + (result ? (result.error ? ' err' : ' ok') : '');
    const io = h('div', { class: 'io' });
    const row = h('details', { class: cls }, h('summary', null, h('span', { class: 'bullet' }),
      h('span', { class: 'tool' }, call ? toolName(call.tool) : '结果'), h('span', { class: 'arg ellipsis' }, call ? stepArg(call) : clip(result.text, 120)),
      h('span', { class: 'state' }, clock((call || result).at))), io);
    row.addEventListener('toggle', async () => {
      if (!row.open || io.childNodes.length) return;
      for (const s of [call, result]) {
        if (!s) continue;
        const pre = h('pre', null, s.text || '');
        io.append(pre);
        if (s.cut && s.i != null && who) {
          try { const full = await get(orgPath('/step?member=' + enc(who) + '&i=' + s.i)); pre.textContent = full.text || pre.textContent; } catch (e) { /* the short text stays */ }
        }
      }
    });
    return row;
  }

  // live items of an embedded session: the reply as it is written, tool calls, permission requests
  function liveTurnStart() {
    const m = member(S.view.member);
    const slot = S.live[S.view.member];
    if (!m || !m.embedded || !slot || !slot.status || !['running', 'waiting', 'starting'].includes(slot.status.state)) return null;
    const first = [...slot.items.values()].sort((a, b) => b.seq - a.seq).find((it) => it.start);
    return first ? toDate(first.at) : null;
  }
  function liveItems() {
    if (S.view.kind === 'group') return [];
    const slot = S.live[S.view.member];
    if (!slot) return [];
    const busy = slot.status && ['running', 'waiting', 'starting'].includes(slot.status.state);
    const all = [...slot.items.values()].sort((a, b) => a.seq - b.seq);
    let start = 0;
    for (let i = all.length - 1; i >= 0; i--) { if (all[i].start) { start = i; break; } }
    const pending = all.filter((it) => it.type === 'permission' && S.snap && S.snap.decisions.some((d) => d.kind === 'permission' && d.id === it.id));
    return busy ? all.slice(start) : pending;
  }
  function renderLive(keepScroll) {
    const box = $('#live');
    if (!box) return;
    const atEnd = nearBottom();
    box.textContent = '';
    const slot = S.live[S.view.member];
    const items = liveItems();
    if (!items.length) return;
    const who = S.view.member;
    const m = member(who);
    const prompt = items.find((it) => it.type === 'prompt');
    if (prompt && m && m.embedded && m.has_transcript) {
      box.append(h('div', { class: 'msg mine' }, avatar(HUMAN), h('div', { class: 'body' }, h('div', { class: 'bubble' }, rich(prompt.text)))));
    }
    const steps = h('div', { class: 'list' });
    let text = '';
    for (const it of items) {
      if (it.type === 'assistant') text = it.text;
      else if (it.type === 'tool') {
        steps.append(h('details', { class: 'step' + (it.status === 'completed' ? ' ok' : it.status === 'failed' ? ' err' : '') },
          h('summary', null, h('span', { class: 'bullet' }), h('span', { class: 'tool' }, clip(it.title, 60)),
            h('span', { class: 'state' }, { pending: '等待', in_progress: '进行中', completed: '完成', failed: '失败' }[it.status] || it.status || '')),
          it.text ? h('div', { class: 'io' }, h('pre', null, it.text)) : null));
      } else if (it.type === 'permission') {
        steps.append(permissionCard(it));
      } else if (it.type === 'error') {
        steps.append(h('div', { class: 'notice' }, h('span', { style: 'color:var(--red)' }, it.text)));
      }
    }
    const running = slot && slot.status && slot.status.state === 'running';
    box.append(h('div', { class: 'msg' }, avatar(who), h('div', { class: 'body' },
      h('div', { class: 'who' }, h('b', null, dname(who)), h('span', null, running ? '正在回复…' : (slot && slot.status ? STATE_LABEL[slot.status.state] || '' : ''))),
      steps.childNodes.length ? h('details', { class: 'acts', open: true }, h('summary', null, h('span', { class: 'chev' }, icon('chev', 13)), h('b', null, '这一轮的动作')), steps) : null,
      text ? h('div', { class: 'bubble' }, rich(text)) : (running ? h('div', { class: 'typing' }, h('i'), h('i'), h('i')) : null))));
    if (keepScroll && atEnd) { const s = $('#stream'); s.scrollTop = s.scrollHeight; }
  }
  function permissionCard(it) {
    return h('div', { class: 'decision-card' }, h('div', { class: 'k' }, icon('bell', 14), '需要你决定：允许这个操作吗？'),
      h('div', null, it.title), h('div', { class: 'row-acts' }, (it.options || []).map((o) =>
        h('button', { class: 'btn sm' + (String(o.kind).startsWith('allow') ? ' primary' : ''), type: 'button', onclick: () => decide(it.id, o.id) }, o.name || o.kind))));
  }
  async function decide(id, option) {
    try { await post('/api/permission/' + enc(id), { option }); scheduleRefresh(); } catch (e) { toast(e.message); }
  }

  // ------------------------------------------------------------------ quote: select any text, or a whole message
  function setQuote(who, text) {
    text = String(text || '').trim();
    if (!text) return;
    S.quote = { who, text: text.length > 1200 ? text.slice(0, 1200) + '…' : text };
    renderComposer();
    if (S.thread && S.pane === 'thread') renderPanel();
    const ta = $('#compose'); if (ta) ta.focus();
  }
  function quotedBody(text) {
    if (!S.quote) return text;
    const lines = S.quote.text.split('\n');
    lines[0] = S.quote.who + '：' + lines[0];
    return lines.map((l) => '> ' + l).join('\n') + '\n\n' + text;
  }
  let selBar = null;
  function closeSelBar() { if (selBar) { selBar.remove(); selBar = null; } }
  document.addEventListener('mouseup', (e) => {
    if (selBar && selBar.contains(e.target)) return;
    setTimeout(() => {
      closeSelBar();
      const sel = window.getSelection();
      const text = sel ? sel.toString().trim() : '';
      if (!text || !sel.rangeCount) return;
      const node = sel.anchorNode && (sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement);
      const bubble = node && node.closest('.bubble, .step pre, .receipt');
      if (!bubble) return;
      const from = (bubble.closest('.bubble') || {}).dataset ? bubble.dataset.from : null;
      const rect = sel.getRangeAt(0).getBoundingClientRect();
      selBar = h('div', { class: 'sel-bar', style: 'left:' + Math.max(8, rect.left + rect.width / 2 - 70) + 'px;top:' + Math.max(8, rect.top - 40) + 'px' },
        h('button', { type: 'button', onmousedown: (ev) => { ev.preventDefault(); setQuote(from ? dname(from) : '引用', text); closeSelBar(); sel.removeAllRanges(); } }, icon('quote', 14), '引用'),
        h('button', { type: 'button', onmousedown: (ev) => { ev.preventDefault(); copyText(text); closeSelBar(); } }, icon('copy', 14), '复制'));
      document.body.append(selBar);
    }, 0);
  });

  // ------------------------------------------------------------------ voice input (Edge speech recognition)
  const Voice = {
    rec: null, btn: null,
    supported() { return !!(window.SpeechRecognition || window.webkitSpeechRecognition); },
    stop() { if (this.rec) { try { this.rec.stop(); } catch (e) { /* stopped */ } } },
    toggle(target, btn) {
      if (this.rec) { const same = this.btn === btn; this.stop(); if (same) return; }
      if (PREFS.voice === 'off') { toast('语音输入已在设置里关闭。'); return; }
      if (!this.supported()) { toast('这个窗口用不了语音识别：可以按 Win+H 用 Windows 语音输入，或用微信输入法的语音输入。', 6000); return; }
      const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
      const rec = new Rec();
      rec.lang = lang(); rec.interimResults = true; rec.continuous = true;
      const start = target.selectionStart != null ? target.selectionStart : target.value.length;
      const before = target.value.slice(0, start), after = target.value.slice(target.selectionEnd != null ? target.selectionEnd : start);
      let finalText = '';
      rec.onresult = (e) => {
        let interim = '';
        for (let i = e.resultIndex; i < e.results.length; i++) {
          if (e.results[i].isFinal) finalText += e.results[i][0].transcript; else interim += e.results[i][0].transcript;
        }
        target.value = before + finalText + interim + after;
        const caret = (before + finalText + interim).length;
        try { target.setSelectionRange(caret, caret); } catch (x) { /* inputs without selection */ }
        target.dispatchEvent(new Event('input', { bubbles: true }));
      };
      rec.onerror = (e) => {
        const why = { 'not-allowed': '没有麦克风权限：在窗口地址栏左侧允许使用麦克风。', network: '连不上语音识别服务。', 'no-speech': '没听到声音。', 'audio-capture': '没找到麦克风。' }[e.error];
        if (why) toast(why);
      };
      rec.onend = () => { btn.classList.remove('on'); if (this.rec === rec) { this.rec = null; this.btn = null; } target.focus(); };
      this.rec = rec; this.btn = btn;
      btn.classList.add('on');
      try { rec.start(); } catch (e) { btn.classList.remove('on'); this.rec = null; toast('语音识别没能启动：' + e.message); }
    },
  };
  function micButton(target, cls) {
    const b = h('button', { class: cls || 'mic', type: 'button', title: '语音输入（再点一次停止）', 'aria-label': '语音输入' }, icon('mic', 17));
    b.addEventListener('mousedown', (e) => e.preventDefault());
    b.addEventListener('click', () => Voice.toggle(target, b));
    return b;
  }
  function field(input) {
    const wrap = h('div', { class: 'field' }, input);
    if (PREFS.voice !== 'off') wrap.append(micButton(input));
    return wrap;
  }

  // ------------------------------------------------------------------ composer
  function composerBox({ placeholder, draftKey, onSend, picker, quote }) {
    const ta = h('textarea', { rows: 1, placeholder });
    const sendBtn = h('button', { class: 'send', type: 'button', title: '发送（Enter）', 'aria-label': '发送' }, icon('up', 17));
    const box = h('div', { class: 'composer-box' });
    if (quote && S.quote) {
      box.append(h('div', { class: 'quote-chip' }, h('div', { class: 'txt' }, h('b', null, '引用 ' + S.quote.who + '：'), S.quote.text),
        h('button', { class: 'icon-btn', style: 'width:22px;height:22px', type: 'button', title: '取消引用', onclick: () => { S.quote = null; renderComposer(); if (S.thread && S.pane === 'thread') renderPanel(); } }, icon('x', 14))));
    }
    box.append(ta, h('div', { class: 'bar' }, picker || null, h('div', { class: 'grow' }), PREFS.voice !== 'off' ? micButton(ta) : null, sendBtn));
    const fit = () => { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 260) + 'px'; sendBtn.disabled = !ta.value.trim() && !(quote && S.quote); };
    ta.addEventListener('input', () => { fit(); if (draftKey) save(draftKey, ta.value); if (picker) mentionCheck(ta); });
    ta.addEventListener('keydown', (e) => {
      if (mentionKey(e, ta)) return;
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229) { e.preventDefault(); doSend(); }
    });
    async function doSend() {
      const text = ta.value.trim();
      if ((!text && !(quote && S.quote)) || sendBtn.disabled) return;
      sendBtn.disabled = true;
      Voice.stop();
      try {
        await onSend(quote ? quotedBody(text) : text);
        ta.value = ''; if (draftKey) save(draftKey, '');
        if (quote) S.quote = null;
      } catch (e) {
        toast('没发出去：' + e.message);
      } finally {
        fit();
      }
    }
    sendBtn.addEventListener('click', doSend);
    if (draftKey) ta.value = load(draftKey, '');
    setTimeout(fit, 0);
    return { box, ta };
  }
  function renderComposer() {
    const wrap = $('#composer'); wrap.textContent = '';
    if (!S.snap || (S.view.kind !== 'group' && !member(S.view.member))) return;
    const group = S.view.kind === 'group';
    const { box, ta } = composerBox({
      placeholder: group ? '在群里说点什么，用 @ 点名成员' : '发消息给 ' + dname(S.view.member),
      draftKey: 'relic.draft.' + S.orgId + '.' + chatKey(), quote: true, picker: group ? toPicker() : null,
      onSend: async (body) => {
        let to = [S.view.member];
        if (group) {
          const mentioned = S.snap.members.filter((m) => body.includes('@' + (m.display || m.name)) || body.includes('@' + m.name)).map((m) => m.name);
          to = S.to.includes('all') ? (mentioned.length ? mentioned : ['all']) : S.to;
        }
        await post(orgPath('/send'), { to, body, channel: group ? 'group' : 'private' });
        S.to = ['all'];
        renderComposer();
        await refreshSnap(); await loadChat(true);
      },
    });
    ta.id = 'compose';
    wrap.append(box);
  }
  function toPicker() {
    const label = S.to.includes('all') ? '全体' : S.to.map(dname).join('、');
    const btn = h('button', { class: 'chip-btn', type: 'button' }, '发给：' + clip(label, 24), icon('down', 14));
    btn.addEventListener('click', () => {
      const items = [{ key: 'all', label: '全体成员' }].concat(S.snap.members.map((m) => ({ key: m.name, label: m.display || m.name, sub: m.name })));
      openMenu(btn, items.map((it) => {
        const checked = it.key === 'all' ? S.to.includes('all') : !S.to.includes('all') && S.to.includes(it.key);
        const box = h('input', { type: 'checkbox' }); box.checked = checked;
        return h('button', { class: 'item', type: 'button', onclick: () => {
          if (it.key === 'all') S.to = ['all'];
          else { const set = new Set(S.to.filter((x) => x !== 'all')); set.has(it.key) ? set.delete(it.key) : set.add(it.key); S.to = set.size ? [...set] : ['all']; }
          closeMenu(); renderComposer();
        } }, box, it.key === 'all' ? groupAvatar('xs') : avatar(it.key, { size: 'xs', click: false }), h('span', null, it.label), it.sub && it.sub !== it.label ? h('span', { class: 'dim mono' }, it.sub) : null);
      }));
    });
    return btn;
  }
  // @ mentions in the group composer
  let mention = null;
  function mentionCheck(ta) {
    closeMention();
    if (S.view.kind !== 'group') return;
    const upto = ta.value.slice(0, ta.selectionStart);
    const m = /@([^\s@]*)$/.exec(upto);
    if (!m) return;
    const q = m[1].toLowerCase();
    const options = S.snap.members.filter((x) => (x.display || '').toLowerCase().startsWith(q) || x.name.toLowerCase().startsWith(q)).slice(0, 8);
    if (!options.length) return;
    const rect = ta.getBoundingClientRect();
    const box = h('div', { class: 'menu', style: 'left:' + rect.left + 'px;bottom:' + (window.innerHeight - rect.top + 8) + 'px' });
    options.forEach((o, i) => box.append(h('button', { class: 'item' + (i === 0 ? ' on' : ''), type: 'button', onmousedown: (e) => { e.preventDefault(); pickMention(ta, o, m[1]); } },
      avatar(o.name, { size: 'xs', click: false }), o.display || o.name, h('span', { class: 'dim mono' }, o.name))));
    document.body.append(box);
    mention = { box, options, index: 0, q: m[1] };
  }
  function pickMention(ta, o, q) {
    const pos = ta.selectionStart;
    const before = ta.value.slice(0, pos - q.length) + (o.display || o.name) + ' ';
    ta.value = before + ta.value.slice(pos);
    ta.selectionStart = ta.selectionEnd = before.length;
    const set = new Set(S.to.filter((x) => x !== 'all')); set.add(o.name); S.to = [...set];
    closeMention(); ta.focus();
    const btn = ta.closest('.composer-box').querySelector('.chip-btn');
    if (btn) btn.firstChild.textContent = '发给：' + clip(S.to.map(dname).join('、'), 24);
  }
  function mentionKey(e, ta) {
    if (!mention) return false;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      mention.index = (mention.index + (e.key === 'ArrowDown' ? 1 : -1) + mention.options.length) % mention.options.length;
      [...mention.box.children].forEach((b, i) => b.classList.toggle('on', i === mention.index));
      return true;
    }
    if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); pickMention(ta, mention.options[mention.index], mention.q); return true; }
    if (e.key === 'Escape') { closeMention(); return true; }
    return false;
  }
  function closeMention() { if (mention) { mention.box.remove(); mention = null; } }

  // menus
  let menuEl = null;
  function closeMenu() { if (menuEl) { menuEl.remove(); menuEl = null; } document.querySelectorAll('.ab-menu.on').forEach((b) => b.classList.remove('on')); }
  function openMenu(anchor, items) {
    closeMenu();
    const r = anchor.getBoundingClientRect();
    menuEl = h('div', { class: 'menu', style: 'left:' + Math.min(r.left, window.innerWidth - 260) + 'px;bottom:' + (window.innerHeight - r.top + 6) + 'px' }, items);
    document.body.append(menuEl);
  }
  document.addEventListener('mousedown', (e) => {
    if (menuEl && !menuEl.contains(e.target) && !e.target.closest('.ab-menu')) closeMenu();
    if (cardEl && !cardEl.contains(e.target) && !e.target.closest('.scrim')) closeCard();
    if (selBar && !selBar.contains(e.target)) closeSelBar();
  });

  // ------------------------------------------------------------------ threads (like Slack / WeCom)
  async function openThread(root) {
    S.thread = root; S.threadData = null;
    setPane('thread');
    await loadThread(true);
  }
  async function loadThread(force) {
    if (!S.thread) return;
    const ids = (d) => (d && d.replies ? d.replies.map((r) => r.id).join(',') : null);
    const before = ids(S.threadData);
    try { S.threadData = await get(orgPath('/thread?root=' + S.thread)); } catch (e) { S.threadData = { error: e.message }; }
    if (S.pane !== 'thread' || !S.panelOpen || (!force && before === ids(S.threadData))) return;
    const typing = document.activeElement && document.activeElement.matches && document.activeElement.matches('#panel textarea');
    renderPanel();
    const ta = typing && $('#panel textarea');
    if (ta) { ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); }
  }
  function closeThread() { S.thread = null; S.threadData = null; setPane(S.lastPane || 'org'); }
  function renderThread(body) {
    const data = S.threadData || {};
    if (data.error || !data.root) { body.append(h('div', { class: 'block empty' }, data.error ? '读取失败：' + data.error : '正在读取…')); return; }
    body.classList.add('thread-pane');
    body.append(h('div', { class: 'root' }, renderItem(data.root, null, 'thread')));
    body.append(h('div', { class: 'count' }, data.replies.length ? data.replies.length + ' 条回复' : '还没有回复'));
    const list = h('div', { class: 'replies' });
    let prev = null;
    for (const r of data.replies) { list.append(renderItem(r, prev, 'thread')); prev = r; }
    body.append(list);
    const { box } = composerBox({ placeholder: '在话题里回复…', quote: true, draftKey: 'relic.draft.' + S.orgId + '.thread.' + S.thread,
      onSend: async (text) => {
        await post(orgPath('/send'), { body: text, reply_to: S.thread, channel: S.view.kind === 'group' ? 'group' : 'private' });
        await loadThread(true); scheduleRefresh();
      } });
    body.append(h('div', { class: 'composer', style: 'padding:10px 0 14px' }, box));
  }

  // ------------------------------------------------------------------ right side: organization, workspace, file, thread
  const PANES = [['org', '概况', 'org'], ['work', '工作区', 'work'], ['file', '文件', 'file']];
  function setPane(p) {
    S.pane = p;
    if (p !== 'thread') { S.lastPane = p; save('relic.pane', p); }
    S.panelOpen = true;
    if (window.innerWidth > 1180) save('relic.panel', true);
    renderPanel(); renderAppbar();
  }
  function togglePanel(force) {
    S.panelOpen = force != null ? !!force : !S.panelOpen;
    if (window.innerWidth > 1180) save('relic.panel', S.panelOpen);
    renderPanel(); renderAppbar();
  }
  const panelKey = () => 'relic.panelw.' + (S.pane === 'file' ? 'file' : 'side');
  function applyPanelWidth() {
    const w = load(panelKey(), S.pane === 'file' ? 520 : 340);
    $('#app').style.setProperty('--panel-w', Math.round(Math.max(280, Math.min(w, window.innerWidth * 0.6))) + 'px');
  }
  function startResize(e) {
    e.preventDefault();
    const app = $('#app');
    const x0 = e.clientX, w0 = $('#panel').getBoundingClientRect().width, key = panelKey();
    let w = w0;
    document.body.classList.add('resizing');
    const move = (ev) => { w = Math.round(Math.max(280, Math.min(w0 + x0 - ev.clientX, window.innerWidth * 0.6))); app.style.setProperty('--panel-w', w + 'px'); };
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); document.body.classList.remove('resizing'); save(key, w); };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  }
  function renderPanel(soft) {
    const box = $('#panel');
    $('#app').classList.toggle('no-panel', !S.panelOpen);
    if (!S.panelOpen) { box.textContent = ''; delete box.dataset.pane; return; }
    if (soft && S.pane !== 'org' && box.dataset.pane === S.pane) return;  // the workspace, a file and a thread keep their state
    applyPanelWidth();
    const old = box.querySelector('.pane-body');
    const keep = old && box.dataset.pane === S.pane ? old.scrollTop : 0;
    box.textContent = '';
    box.dataset.pane = S.pane;
    const tabs = PANES.concat(S.thread ? [['thread', '话题', 'thread']] : []);
    box.append(h('div', { class: 'pane-head' },
      h('div', { class: 'pane-tabs', role: 'tablist' }, tabs.map(([k, label, ic]) => h('button', { class: S.pane === k ? 'on' : '', type: 'button', role: 'tab',
        'aria-selected': S.pane === k ? 'true' : 'false', onclick: () => setPane(k) }, icon(ic, 15), label,
        k === 'thread' ? h('span', { class: 'x', title: '关闭话题', onclick: (e) => { e.stopPropagation(); closeThread(); } }, icon('x', 12)) : null))),
      h('button', { class: 'icon-btn', type: 'button', title: '收起右侧栏（Ctrl+Alt+B）', 'aria-label': '收起右侧栏', onclick: () => togglePanel(false) }, icon('x', 16))));
    const body = h('div', { class: 'pane-body' });
    box.append(body, h('div', { class: 'pane-resize', title: '拖动调整宽度', onpointerdown: startResize }));
    if (S.pane === 'org') renderOrgPane(body);
    else if (S.pane === 'work') renderWork(body);
    else if (S.pane === 'file') renderFile(body);
    else renderThread(body);
    if (keep) body.scrollTop = keep;
  }

  // a member's workspace: its folder, git changes, the files it changed lately, and its files
  const HIDE_DIRS = new Set(['.git', 'node_modules', '__pycache__', '.venv', '.mypy_cache', '.pytest_cache']);
  async function renderWork(body) {
    if (!S.snap) return;
    const people = S.snap.members.filter((m) => m.surface !== 'chat');
    const viewing = S.view.kind !== 'group' ? member(S.view.member) : null;
    if (!S.workMember || !member(S.workMember)) S.workMember = viewing && viewing.surface !== 'chat' ? viewing.name : (people[0] ? people[0].name : null);
    body.append(h('div', { class: 'block' }, h('div', { class: 'block-h' }, h('span', null, '谁的工作区')),
      h('div', { class: 'who-pick' }, people.map((m) => h('button', { class: 'who' + (m.name === S.workMember ? ' on' : ''), type: 'button', title: m.name + (m.role ? ' · ' + m.role : ''),
        onclick: () => { S.workMember = m.name; renderPanel(); } }, avatar(m.name, { size: 'xs', click: false }), h('span', { class: 'ellipsis' }, m.display || m.name))))));
    if (!S.workMember) { body.append(h('div', { class: 'block empty' }, '没有能看工作区的成员（聊天成员没有工作区）。')); return; }
    const who = S.workMember;
    const slot = h('div', null, h('div', { class: 'block empty' }, '正在读取…'));
    body.append(slot);
    let ws;
    try { ws = await get(orgPath('/workspace?member=' + enc(who))); } catch (e) { slot.textContent = ''; slot.append(h('div', { class: 'block empty' }, '读取失败：' + e.message)); return; }
    slot.textContent = '';
    if (!ws.folder) { slot.append(h('div', { class: 'block empty' }, dname(who) + ' 还没有工作目录：它的会话还没开始，或者它只是一个聊天。')); return; }
    slot.append(h('div', { class: 'block' }, h('div', { class: 'block-h' }, h('span', null, '工作目录'),
        h('button', { class: 'link', type: 'button', onclick: () => post('/api/fs/open', { path: ws.folder }).catch((e) => toast(e.message)) }, icon('open', 12), '在资源管理器里打开')),
      h('div', { class: 'path-line' }, ws.folder), ws.exists ? null : h('div', { class: 'empty' }, '这个目录现在不存在。')));
    if (!ws.exists) return;
    const base = ((ws.git && ws.git.root) || ws.folder).replace(/\\/g, '/').replace(/\/$/, '');
    const rel = (p) => { const a = String(p).replace(/\\/g, '/'); return a.toLowerCase().startsWith(base.toLowerCase() + '/') ? a.slice(base.length + 1) : p; };
    if (ws.git) {
      const g = h('div', { class: 'block' }, h('div', { class: 'block-h' }, h('span', null, 'Git 改动' + (ws.git.branch ? ' · ' + ws.git.branch : '')),
        h('span', null, ws.git.changes.length ? ws.git.changes.length + ' 个文件' : '')));
      if (!ws.git.changes.length) g.append(h('div', { class: 'empty' }, '没有未提交的改动。'));
      for (const c of ws.git.changes.slice(0, 60)) {
        const code = c.status === '??' ? 'new' : c.status[0];
        g.append(h('button', { class: 'frow', type: 'button', title: c.path, disabled: c.status.includes('D') ? true : null, onclick: () => openFile(c.path) },
          h('span', { class: 'st st-' + code, title: c.status }, code === 'new' ? 'U' : code), h('span', { class: 'ellipsis' }, rel(c.path))));
      }
      if (ws.git.changes.length > 60) g.append(h('div', { class: 'empty' }, '还有 ' + (ws.git.changes.length - 60) + ' 个…'));
      slot.append(g);
    }
    if (ws.recent.length) {
      const r = h('div', { class: 'block' }, h('div', { class: 'block-h' }, h('span', null, '它最近改过的文件')));
      for (const f of ws.recent.slice(0, 15)) {
        const shown = String(rel(f.path)).replace(/\\/g, '/');
        const cut = shown.lastIndexOf('/');
        r.append(h('button', { class: 'frow', type: 'button', title: f.path, onclick: () => openFile(f.path) }, icon('file', 14),
          h('span', { class: 'ellipsis' }, h('span', null, shown.slice(cut + 1)), cut > 0 ? h('span', { class: 'dim' }, '  ' + shown.slice(0, cut)) : null),
          h('span', { class: 'when' }, ago(f.at))));
      }
      slot.append(r);
    }
    slot.append(h('div', { class: 'block' }, h('div', { class: 'block-h' }, h('span', null, '文件')), fileTree(ws.folder)));
  }
  function fileTree(root) {
    const box = h('div', { class: 'ftree' });
    const pad = (depth, extra) => 'padding-left:' + (depth * 14 + (extra || 4)) + 'px';
    async function fill(node, path, depth) {
      let r;
      try { r = await get('/api/fs/list?path=' + enc(path)); } catch (e) { node.append(h('div', { class: 'empty', style: pad(depth, 26) }, e.message)); return; }
      const entries = r.entries.filter((x) => !(x.dir && HIDE_DIRS.has(x.name)));
      if (!entries.length) node.append(h('div', { class: 'empty', style: pad(depth, 26) }, '（空）'));
      for (const x of entries) {
        const row = h('button', { class: 'frow' + (x.dir ? ' dir' : ''), type: 'button', title: x.path, style: pad(depth) },
          x.dir ? icon('chev', 12) : h('span', { class: 'sp' }), icon(x.dir ? 'folder' : 'file', 14), h('span', { class: 'ellipsis' }, x.name));
        node.append(row);
        if (!x.dir) { row.addEventListener('click', () => openFile(x.path)); continue; }
        const kids = h('div', { hidden: true });
        node.append(kids);
        let loaded = false;
        row.addEventListener('click', () => {
          kids.hidden = !kids.hidden;
          row.classList.toggle('open', !kids.hidden);
          if (!kids.hidden && !loaded) { loaded = true; fill(kids, x.path, depth + 1); }
        });
      }
      if (r.more) node.append(h('div', { class: 'empty', style: pad(depth, 26) }, '只列出前 800 项'));
    }
    fill(box, root, 0);
    return box;
  }

  // file preview: text with line numbers, Markdown, JSON, images
  async function openFile(path, line) {
    S.file = { path, line: line || 0, data: null, mode: null };
    setPane('file');
    let data;
    try { data = await get('/api/fs/read?path=' + enc(path)); } catch (e) { data = { error: e.message }; }
    if (!S.file || S.file.path !== path) return;
    S.file.data = data;
    if (S.pane === 'file' && S.panelOpen) renderPanel();
  }
  function sizeLabel(n) { return n < 1024 ? n + ' B' : n < 1048576 ? (n / 1024).toFixed(1) + ' KB' : (n / 1048576).toFixed(1) + ' MB'; }
  function renderFile(body) {
    const f = S.file;
    if (!f) { body.append(h('div', { class: 'block empty' }, '在「工作区」里，或者在消息里的文件路径上点一下，文件就在这里预览。')); return; }
    const name = f.path.split(/[\\/]/).pop();
    const d = f.data;
    body.append(h('div', { class: 'file-head' }, icon('file', 16), h('div', { class: 't' }, h('b', { class: 'ellipsis' }, name), h('span', { class: 'ellipsis', title: f.path }, f.path)),
      h('button', { class: 'icon-btn', type: 'button', title: '复制路径', 'aria-label': '复制路径', onclick: () => copyText(f.path) }, icon('copy', 15)),
      h('button', { class: 'icon-btn', type: 'button', title: '用系统默认程序打开', 'aria-label': '用系统默认程序打开', onclick: () => post('/api/fs/open', { path: f.path }).catch((e) => toast(e.message)) }, icon('open', 15))));
    if (!d) { body.append(h('div', { class: 'block empty' }, '正在读取…')); return; }
    if (d.error) { body.append(h('div', { class: 'block empty' }, '打不开：' + d.error)); return; }
    const meta = h('div', { class: 'file-meta' }, h('span', null, sizeLabel(d.size)), h('span', null, '改于 ' + ago(new Date(d.mtime * 1000).toISOString())), d.truncated ? h('span', null, '只显示前 2 MB') : null);
    body.append(meta);
    if (d.kind === 'image') { body.append(h('div', { class: 'file-img' }, h('img', { src: d.url, alt: name }))); return; }
    if (d.kind === 'binary') { body.append(h('div', { class: 'block empty' }, '这是二进制文件，没法在这里预览；可以点右上角用系统程序打开。')); return; }
    if (d.kind === 'markdown') {
      const mode = f.mode || 'preview';
      meta.append(h('div', { style: 'flex:1' }), segControl([['preview', '预览'], ['source', '源码']], mode, (k) => { f.mode = k; renderPanel(); }));
      if (mode === 'preview') { body.append(h('div', { class: 'md file-md' }, rich(d.text))); return; }
    }
    let text = d.text;
    if (d.kind === 'json') { try { text = JSON.stringify(JSON.parse(text), null, 2); } catch (e) { /* shown as it is */ } }
    body.append(codeView(text, f.line));
  }
  function codeView(text, line) {
    const lines = text.replace(/\r\n?/g, '\n').split('\n');
    const max = 6000;
    const pre = h('pre', { class: 'code-view' });
    lines.slice(0, max).forEach((l, i) => pre.append(h('span', { class: 'ln' + (i + 1 === line ? ' hi' : ''), 'data-n': i + 1 }, l)));
    if (line) setTimeout(() => { const hi = pre.querySelector('.hi'); if (hi) hi.scrollIntoView({ block: 'center' }); }, 0);
    return h('div', null, pre, lines.length > max ? h('div', { class: 'file-meta' }, '只显示前 ' + max + ' 行，共 ' + lines.length + ' 行') : null);
  }

  // ------------------------------------------------------------------ organization pane
  function renderOrgPane(box) {
    if (!S.snap) return;
    const { org, members, tasks, protocols, episodes, decisions } = S.snap;
    const autoWake = h('input', { type: 'checkbox', class: 'toggle' });
    autoWake.checked = !!org.auto_wake;
    autoWake.addEventListener('change', () => post(orgPath('/auto_wake'), { on: autoWake.checked }).then(scheduleRefresh).catch((e) => toast(e.message)));
    const purpose = h('div', { class: 'purpose', title: '点击展开' }, org.purpose || '（没有写目标）');
    purpose.addEventListener('click', () => purpose.classList.toggle('open'));
    const seg = h('div', { class: 'seg', role: 'group', 'aria-label': '组织给你看多少' }, [['direct', '直接'], ['transparent', '透明'], ['liaison', '秘书优先']].map(([k, label]) =>
      h('button', { class: S.mode === k ? 'on' : '', type: 'button', onclick: () => { S.mode = k; save('relic.mode', k); renderPanel(); if (k === 'liaison' && secretaryName()) go({ kind: 'secretary', member: secretaryName() }); } }, label)));
    box.append(h('div', { class: 'block' },
      h('div', { class: 'block-h' }, h('span', null, '组织'), seg),
      h('h3', { class: 'org-title' }, org.name), purpose,
      h('div', { class: 'chips' }, h('span', { class: 'chip' }, org.governance === 'peer' ? '同侪制' : '领导制'), org.leader ? h('span', { class: 'chip' }, '负责人：' + roleName(org.leader, '负责人')) : null,
        h('span', { class: 'chip' }, members.length + ' 位成员'), org.secretary ? h('span', { class: 'chip sec' }, '秘书：' + roleName(org.secretary, '秘书')) : null),
      h('label', { class: 'switch' }, autoWake, '自动唤醒：成员收到消息时自动开一轮')));

    box.append(h('div', { class: 'block' }, h('div', { class: 'block-h' }, h('span', null, '需要你决定'), decisions.length ? h('span', { class: 'badge' }, decisions.length) : null),
      decisions.length ? decisions.map(decisionCard) : h('div', { class: 'empty' }, '现在没有需要你决定的事。')));

    const brief = S.mode === 'liaison';
    const open = tasks.filter((t) => !['done', 'dropped'].includes(t.status));
    const done = tasks.filter((t) => t.status === 'done');
    const work = h('div', { class: 'block' }, h('div', { class: 'block-h' },
      h('button', { class: 'link', type: 'button', onclick: () => openDetails('tasks', { filter: 'open' }) }, '当前工作', icon('chev', 12)),
      h('button', { class: 'link', type: 'button', onclick: () => openDetails('tasks', { filter: 'done' }) }, '已完成 ' + done.length, icon('chev', 12))));
    if (!tasks.length) work.append(h('div', { class: 'empty' }, '还没有任务。'));
    else if (!open.length) work.append(h('div', { class: 'empty' }, '没有进行中的任务，已完成 ' + done.length + ' 个。'));
    for (const t of open.slice(0, 8)) {
      work.append(h('button', { class: 'item-row click', type: 'button', onclick: () => openDetails('tasks', { task: t.id }) },
        t.owner ? avatar(t.owner, { size: 'xs', click: false }) : h('span'),
        h('div', { class: 't' }, h('b', { class: 'ellipsis' }, t.title), h('span', { class: 'ellipsis' }, t.id + ' · ' + (t.owner ? dname(t.owner) : '没人负责'))),
        h('span', { class: 'chip ' + ({ blocked: 'bad', working: 'warn' }[t.status] || '') }, TASK_LABEL[t.status] || t.status)));
    }
    if (open.length > 8) work.append(h('button', { class: 'link', style: 'border:0;background:none;color:var(--ink-3);text-align:left;padding:0', type: 'button', onclick: () => openDetails('tasks', { filter: 'open' }) }, '还有 ' + (open.length - 8) + ' 个…'));
    const recentDone = done.filter((t) => t.report).sort((a, b) => String(b.done_at || '').localeCompare(String(a.done_at || ''))).slice(0, 3);
    if (recentDone.length) {
      work.append(h('div', { class: 'block-h', style: 'margin-top:4px' }, h('span', null, '最近完成')));
      for (const t of recentDone) {
        work.append(h('button', { class: 'item-row click', type: 'button', onclick: () => openDetails('tasks', { task: t.id }) },
          t.owner ? avatar(t.owner, { size: 'xs', click: false }) : h('span'),
          h('div', { class: 't' }, h('b', { class: 'ellipsis' }, t.title), h('span', { class: 'ellipsis' }, clip(t.report.replace(/[#*`>|_-]+/g, ' '), 80))),
          h('span', { class: 'chip ok' }, '报告')));
      }
    }
    box.append(work);

    if (!brief) {
      const people = h('div', { class: 'block' }, h('div', { class: 'block-h' }, h('span', null, '成员'),
        h('button', { class: 'link', type: 'button', onclick: () => memberDialog() }, icon('plus', 13), '添加')));
      for (const m of members) {
        people.append(h('button', { class: 'item-row click', type: 'button', onclick: (e) => openCard(m.name, e.currentTarget) }, avatar(m.name, { size: 'sm', dot: true, click: false }),
          h('div', { class: 't' }, h('b', { class: 'ellipsis' }, m.secretary ? roleName(m.name, '秘书') + ' · 秘书' : (m.display || m.name)), h('span', { class: 'ellipsis' }, m.doing || m.detail || STATE_LABEL[m.state])),
          h('span', { class: 'chip' + (['running', 'working'].includes(m.state) ? ' ok' : m.state === 'waiting' ? ' warn' : m.state === 'error' ? ' bad' : '') }, STATE_LABEL[m.state] || m.state)));
      }
      box.append(people);
      const live = protocols.filter((p) => ['active', 'proposed'].includes(p.status));
      const pro = h('div', { class: 'block' }, h('div', { class: 'block-h' },
        h('button', { class: 'link', type: 'button', onclick: () => openDetails('protocols') }, '协议', icon('chev', 12)),
        h('span', null, protocols.filter((p) => p.status === 'active').length + ' 条生效')));
      if (!live.length) pro.append(h('div', { class: 'empty' }, '还没有生效的协议：协议来自成员实际遇到的摩擦。'));
      for (const p of live) {
        pro.append(h('button', { class: 'item-row click', type: 'button', onclick: () => openDetails('protocols') }, h('span', { class: 'chip ' + (p.strength === 'strong' ? 'bad' : '') }, p.strength === 'strong' ? '强' : '弱'),
          h('div', { class: 't' }, h('b', { class: 'ellipsis' }, p.id + ' ' + p.title), h('span', null, p.status === 'proposed' ? '投票中（' + p.votes + ' 票）' : '生效 · 用过 ' + p.uses + ' 次')), h('span')));
      }
      box.append(pro);
      const eps = h('div', { class: 'block' }, h('div', { class: 'block-h' }, h('span', null, 'Episode')));
      const openEps = episodes.filter((e) => e.status === 'open');
      const recent = episodes.filter((e) => e.status === 'closed').slice(-3).reverse();
      if (!episodes.length) eps.append(h('div', { class: 'empty' }, '还没有 episode。'));
      for (const e of openEps.concat(recent)) {
        eps.append(h('div', { class: 'item-row' }, h('span', { class: 'chip ' + (e.status === 'open' ? 'warn' : e.outcome === 'success' ? 'ok' : '') }, e.status === 'open' ? '进行中' : ({ success: '成功', failure: '失败', partial: '部分', cancelled: '取消' }[e.outcome] || e.outcome)),
          h('div', { class: 't' }, h('b', { class: 'ellipsis' }, e.id + ' ' + e.title), h('span', null, '反思 ' + e.reflections + '/' + e.participants)), h('span')));
      }
      box.append(eps);
    }
    box.append(h('div', { class: 'block' }, brief ? h('div', { class: 'empty' }, '秘书优先：组织内部的细节按需展开。') : null,
      h('button', { class: 'btn', type: 'button', onclick: () => openDetails('trace') }, icon('trace', 16), '组织详情：上下文、轨迹、任务、协议、文档')));
  }
  function decisionCard(d) {
    if (d.kind === 'permission') {
      return h('div', { class: 'decision' }, h('b', null, dname(d.member) + ' 想要：' + d.title), d.detail ? h('div', { class: 'dim ellipsis' }, d.detail) : null,
        h('div', { class: 'row-acts' }, (d.options || []).map((o) => h('button', { class: 'btn sm' + (String(o.kind).startsWith('allow') ? ' primary' : ''), type: 'button', onclick: () => decide(d.id, o.id) }, o.name || o.kind))));
    }
    if (d.kind === 'trajectory') {
      const answer = (decision) => post(orgPath('/trajectory_answer'), { request_id: d.id, decision }).then(scheduleRefresh).catch((e) => toast(e.message));
      const whose = d.requester === d.member ? '自己席位' : dname(d.member) + ' 席位';
      const which = d.carrier ? '往前第 ' + d.carrier + ' 任会话' : '当前会话';
      return h('div', { class: 'decision' }, h('b', null, dname(d.requester) + ' 想读' + whose + '的' + which + '的轨迹'), h('div', null, '理由：' + (d.reason || '—')),
        h('div', { class: 'row-acts' }, h('button', { class: 'btn sm primary', type: 'button', onclick: () => answer('approve') }, '同意（脱敏导出）'), h('button', { class: 'btn sm', type: 'button', onclick: () => answer('deny') }, '拒绝')));
    }
    if (d.kind === 'wake') {
      return h('div', { class: 'decision' }, h('b', null, '自动唤醒 ' + dname(d.member) + ' 失败'), h('div', { class: 'dim' }, clip(d.error, 140)),
        h('div', { class: 'row-acts' }, h('button', { class: 'btn sm', type: 'button', onclick: () => go({ kind: 'member', member: d.member }) }, '打开私聊')));
    }
    if (d.kind === 'task') {
      return h('div', { class: 'decision' }, h('b', null, '任务受阻：' + d.id + ' ' + d.title), h('div', { class: 'dim' }, '负责人 ' + (d.member ? dname(d.member) : '—')),
        h('div', { class: 'row-acts' }, h('button', { class: 'btn sm', type: 'button', onclick: () => openDetails('tasks', { task: d.id }) }, '看任务'),
          d.member ? h('button', { class: 'btn sm', type: 'button', onclick: () => go({ kind: 'member', member: d.member }) }, '问问 ' + dname(d.member)) : null));
    }
    return h('div', { class: 'decision' }, JSON.stringify(d));
  }

  // ------------------------------------------------------------------ name card: rename, avatar, model
  let cardEl = null;
  function closeCard() { if (cardEl) { cardEl.remove(); cardEl = null; } }
  function identity(c) {
    if (c.state === 'vacant') return (c.harness_label ? c.harness_label + ' 的' : '') + '席位，还没有会话坐进来';
    if (c.surface === 'subagent') return c.harness_label + ' 的 subagent' + (c.parent ? '，由 ' + dname(c.parent) + ' 的会话启动' : '');
    if (c.surface === 'acp') return c.harness_label + ' 会话，在 Relic App 里内嵌运行（ACP）';
    if (c.surface === 'chat') return c.harness_label + ' 里的一个聊天';
    return [c.harness_label, c.surface_label].filter(Boolean).join(' ') + ' 里的一个会话';
  }
  function pickImage() {
    return new Promise((resolve) => {
      const input = h('input', { type: 'file', accept: 'image/png,image/jpeg,image/webp,image/gif' });
      input.addEventListener('change', () => {
        const file = input.files && input.files[0];
        if (!file) return resolve(null);
        if (file.size > 2 * 1024 * 1024) { toast('图片不能超过 2 MB。'); return resolve(null); }
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.readAsDataURL(file);
      });
      input.click();
    });
  }
  async function openCard(name, anchor) {
    closeCard();
    const m = member(name);
    if (!m) return;
    const rect = anchor.getBoundingClientRect();
    const card = h('div', { class: 'card', role: 'dialog', 'aria-label': (m.display || name) + ' 的名片' });
    card.style.left = Math.min(Math.max(12, rect.right + 8), window.innerWidth - 356) + 'px';
    card.style.top = Math.min(Math.max(12, rect.top - 12), window.innerHeight - 520) + 'px';
    let editingName = false, editingModel = false;
    const fill = (c) => {
      card.textContent = '';
      const av = h('div', { class: 'avatar-wrap', title: '更换头像' }, avatar(name, { size: 'lg', dot: true, click: false }), h('span', { class: 'change' }, '更换头像'));
      av.addEventListener('click', async () => {
        const data = await pickImage(); if (!data) return;
        try { await post('/api/avatar', { org: S.orgId, member: name, data }); toast('头像换好了'); await refreshSnap(); fill(Object.assign(c, member(name))); renderStream(false); } catch (e) { toast(e.message); }
      });
      const tags = [];
      if (c.leader) tags.push(h('span', { class: 'tag lead' }, '负责人'));
      if (c.secretary) tags.push(h('span', { class: 'tag sec' }, '秘书'));
      let titleRow;
      if (editingName) {
        const input = h('input', { value: c.display_custom ? c.display : '', placeholder: c.display || '新名字', maxlength: 40 });
        const saveName = async () => {
          try {
            const r = await post(orgPath('/rename'), { member: name, name: input.value.trim() });
            toast(input.value.trim() ? '改好了。' + (r.note ? ' ' + r.note : '') : '已恢复默认名字。', 5000);
            editingName = false; await refreshSnap(); fill(Object.assign(c, member(name))); renderStream(false);
          } catch (e) { toast(e.message); }
        };
        input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.isComposing) saveName(); if (e.key === 'Escape') { editingName = false; fill(c); } });
        titleRow = h('div', { class: 'rename' }, field(input), h('button', { class: 'btn sm primary', type: 'button', onclick: saveName }, '保存'));
        setTimeout(() => input.focus(), 0);
      } else {
        titleRow = h('h3', null, c.display || name, tags, h('button', { class: 'icon-btn', style: 'width:24px;height:24px', type: 'button', title: '重命名（也会改到它自己的会话）', onclick: () => { editingName = true; fill(c); } }, icon('edit', 14)));
      }
      card.append(h('div', { class: 'top' }, av, h('div', { style: 'min-width:0' }, titleRow, h('div', { class: 'id mono' }, name + (c.display_custom ? '' : ' · 名字按职责自动起')))));
      const kv = h('dl', { class: 'kv' });
      const row = (k, v) => { if (v) append(kv, [h('dt', null, k), h('dd', null, v)]); };
      row('职责', c.role || '（没有写）');
      row('身份', identity(c));
      const modelText = [c.model || '默认模型', c.effort].filter(Boolean).join(' · ');
      const modelCell = h('div', null, h('span', null, modelText), ' ',
        c.model_editable ? h('button', { class: 'btn sm ghost', type: 'button', onclick: () => { editingModel = !editingModel; fill(c); } }, editingModel ? '收起' : '更换') : null,
        !c.model_editable && c.model_note ? h('div', { class: 'dim', style: 'font-size:11.5px;margin-top:2px' }, c.model_note) : null);
      if (editingModel && c.model_editable) {
        const ms = h('select', null, h('option', { value: '' }, '默认模型'), (c.models || []).map((x) => h('option', { value: x, selected: x === c.model ? true : null }, x)));
        const es = h('select', null, h('option', { value: '' }, '默认推理强度'), (c.efforts || []).map((x) => h('option', { value: x, selected: x === c.effort ? true : null }, x)));
        modelCell.append(h('div', { class: 'model-edit' }, ms, es, h('div', { class: 'dim', style: 'font-size:11.5px' }, c.model_note),
          h('button', { class: 'btn sm primary', type: 'button', onclick: async () => {
            try { const r = await post(orgPath('/model'), { member: name, model: ms.value, effort: es.value }); toast(r.applied === 'now' ? '已切换。' : '已保存，下一轮起生效。'); editingModel = false; await refreshSnap(); fill(Object.assign(c, member(name))); } catch (e) { toast(e.message); }
          } }, '保存模型')));
      }
      row('模型', modelCell);
      row('状态', h('span', null, h('span', { class: 'chip' + (['running', 'working'].includes(c.state) ? ' ok' : c.state === 'waiting' ? ' warn' : c.state === 'error' ? ' bad' : '') }, STATE_LABEL[c.state] || c.state),
        c.detail && c.detail !== STATE_LABEL[c.state] ? ' ' + c.detail : ''));
      row('在做', c.doing ? c.doing + (c.doing_at ? '（' + ago(c.doing_at) + '）' : '') : '');
      const tasks = (c.tasks || []).filter((t) => !['done', 'dropped'].includes(t.status));
      row('负责', tasks.length ? h('div', null, tasks.map((t) => h('div', { class: 'ellipsis' }, t.id + ' ' + t.title))) : ((c.tasks || []).length ? '已完成 ' + c.tasks.length + ' 个任务' : ''));
      row('会话', c.agent ? h('span', null, 'subagent ', h('span', { class: 'mono', title: c.agent }, c.agent.slice(0, 12)), c.parent ? '（在 ' + dname(c.parent) + ' 的会话里）' : '') :
        c.session ? h('span', { class: 'mono', title: c.session }, c.session.slice(0, 18) + (c.session.length > 18 ? '…' : '')) : '');
      row('目录', c.cwd ? h('span', { class: 'mono' }, clip(c.cwd, 64)) : '');
      row('加入', c.joined_at ? dayLabel(toDate(c.joined_at)) + ' ' + clock(c.joined_at) + (c.carriers > 1 ? ' · 第 ' + c.carriers + ' 任' : '') : '');
      if (c.recent && c.recent.length) row('最近', h('div', null, c.recent.slice(0, 4).map((r) => h('div', { class: 'ellipsis dim' }, ago(new Date(r.at * 1000).toISOString()) + ' ' + toolName(r.tool) + ' ' + clip(r.summary, 50)))));
      card.append(kv, h('div', { class: 'acts-row' },
        h('button', { class: 'btn primary', type: 'button', onclick: () => { closeCard(); go({ kind: c.secretary ? 'secretary' : 'member', member: name }); } }, '发消息'),
        h('button', { class: 'btn', type: 'button', onclick: () => { closeCard(); openDetails('trace', { member: name }); } }, '上下文和轨迹')));
    };
    fill(m);
    document.body.append(card);
    cardEl = card;
    try { const full = await get(orgPath('/member/' + enc(name))); if (cardEl === card) fill(full); } catch (e) { /* the snapshot card stays */ }
  }

  // ------------------------------------------------------------------ dialogs
  function closeLayer() { $('#layer').textContent = ''; Voice.stop(); }
  function scrim(content) {
    closeLayer();
    const s = h('div', { class: 'scrim', onmousedown: (e) => { if (e.target === s) closeLayer(); } }, content);
    $('#layer').append(s);
    return s;
  }
  async function harnessList(fresh) {
    if (!S.harnesses || fresh) S.harnesses = await get('/api/harnesses');
    return S.harnesses;
  }
  async function memberDialog({ secretary } = {}) {
    if (!S.snap) return;
    const list = await harnessList();
    const err = h('div', { class: 'err' });
    const name = h('input', { value: secretary ? 'secretary' : '', placeholder: '英文短名，例如 reviewer（不含空格）' });
    const role = h('input', { placeholder: secretary ? '秘书：组织与人之间的联络人' : '它负责什么，例如：前端、测试、文档' });
    const model = h('input', { placeholder: '留空用默认模型' });
    const folder = h('input', { placeholder: '留空用 ~/.relic/workspaces/<组织>/<名字>' });
    const sec = h('input', { type: 'checkbox', class: 'toggle' }); sec.checked = !!secretary;
    let picked = (list.find((x) => x.available) || {}).id;
    const choices = h('div', { class: 'choices' }, list.filter((x) => !x.later).map((x) => {
      const radio = h('input', { type: 'radio', name: 'harness', value: x.id, disabled: !x.available });
      radio.checked = x.id === picked;
      radio.addEventListener('change', () => { picked = x.id; });
      return h('label', { class: 'choice' + (x.available ? '' : ' off') }, radio, h('div', null, h('b', null, x.title), ' ', h('span', { class: 'dim' }, x.vendor),
        h('div', { class: 'dim', style: 'font-size:12px' }, x.available ? '已连接 · ' + (x.program ? clip(x.program, 48) : '') : x.problem)));
    }));
    const later = list.filter((x) => x.later);
    if (later.length) choices.append(h('div', { class: 'later' }, '以后通过 ACP 接入：', later.map((x) => h('span', { class: 'chip', title: x.vendor + ' · ' + x.launch }, x.title))));
    const submit = h('button', { class: 'btn primary', type: 'button' }, secretary ? '创建秘书' : '创建成员');
    const dialog = h('div', { class: 'dialog', role: 'dialog' }, h('h3', null, secretary ? '新建内嵌秘书' : '添加成员'),
      h('div', { class: 'dim', style: 'font-size:12.5px' }, '成员在 Relic App 里以 ACP 会话运行，用你本机已登录的 Claude Code / Codex。它会坐进席位、读一遍组织，然后等任务。'),
      h('div', { class: 'form' }, h('label', null, '名字（成员 id）', field(name)), h('label', null, '职责', field(role)),
        h('div', null, h('div', { class: 'dim', style: 'margin-bottom:6px;font-size:12.5px' }, 'Harness'), choices),
        h('label', null, '模型', field(model)), h('label', null, '工作目录', field(folder)), h('label', { class: 'switch' }, sec, '设为这个组织的秘书')), err,
      h('div', { class: 'acts-row' }, h('button', { class: 'btn', type: 'button', onclick: closeLayer }, '取消'), submit));
    submit.addEventListener('click', async () => {
      err.textContent = '';
      if (!name.value.trim()) { err.textContent = '写一个名字。'; return; }
      if (!picked) { err.textContent = '先在设置里连好一个 harness。'; return; }
      submit.disabled = true;
      try {
        await post(orgPath('/members'), { name: name.value.trim(), role: role.value.trim(), harness: picked, model: model.value.trim(), folder: folder.value.trim(), secretary: sec.checked });
        closeLayer(); toast('正在启动 ' + name.value.trim() + ' 的会话…');
        await refreshSnap();
        go({ kind: sec.checked ? 'secretary' : 'member', member: name.value.trim() });
      } catch (e) { err.textContent = e.message; submit.disabled = false; }
    });
    scrim(dialog);
    setTimeout(() => name.focus(), 0);
  }
  function openSecretarySetup() {
    const mains = S.snap.members.filter((m) => m.state !== 'vacant' && m.surface !== 'subagent' && m.surface !== 'chat');
    scrim(h('div', { class: 'dialog', role: 'dialog' }, h('h3', null, '给组织设一个秘书'),
      h('div', { class: 'dim', style: 'font-size:12.5px' }, '秘书是你和组织之间的联络人：把组织的状态整理给你，把你的意图转成组织里的任务和消息。'),
      mains.length ? h('div', { class: 'choices' }, mains.map((m) => h('button', { class: 'choice', type: 'button', onclick: async () => {
        try { await post(orgPath('/secretary'), { member: m.name }); closeLayer(); await refreshSnap(); go({ kind: 'secretary', member: m.name }); } catch (e) { toast(e.message); }
      } }, avatar(m.name, { size: 'sm', click: false }), h('div', null, h('b', null, '让 ' + (m.display || m.name) + ' 当秘书'), h('div', { class: 'dim', style: 'font-size:12px' }, [m.harness_label, m.surface_label].filter(Boolean).join(' · ')))))) : null,
      h('div', { class: 'acts-row' }, h('button', { class: 'btn', type: 'button', onclick: closeLayer }, '取消'), h('button', { class: 'btn primary', type: 'button', onclick: () => memberDialog({ secretary: true }) }, '新建内嵌秘书'))));
  }
  function orgDialog() {
    const err = h('div', { class: 'err' });
    const name = h('input', { placeholder: '组织名字' });
    const purpose = h('textarea', { rows: 3, placeholder: '这个组织要做成什么' });
    const gov = h('select', null, h('option', { value: 'leader' }, '领导制：第一个成员当负责人'), h('option', { value: 'peer' }, '同侪制：多数决'));
    const submit = h('button', { class: 'btn primary', type: 'button' }, '创建组织');
    submit.addEventListener('click', async () => {
      if (!name.value.trim()) { err.textContent = '写一个名字。'; return; }
      submit.disabled = true;
      try {
        const r = await post('/api/orgs', { name: name.value.trim(), purpose: purpose.value.trim(), governance: gov.value });
        closeLayer(); await loadOrgs(); await openOrg(r.org_id); memberDialog({ secretary: true });
      } catch (e) { err.textContent = e.message; submit.disabled = false; }
    });
    const purposeWrap = h('div', { class: 'field' }, purpose, PREFS.voice !== 'off' ? micButton(purpose) : null);
    scrim(h('div', { class: 'dialog', role: 'dialog' }, h('h3', null, '新建组织'),
      h('div', { class: 'form' }, h('label', null, '名字', field(name)), h('label', null, '目标', purposeWrap), h('label', null, '治理方式', gov)), err,
      h('div', { class: 'acts-row' }, h('button', { class: 'btn', type: 'button', onclick: closeLayer }, '取消'), submit)));
    setTimeout(() => name.focus(), 0);
  }

  // ------------------------------------------------------------------ details: context and trajectory, tasks, protocols, documents
  async function openDetails(tab, opts = {}) {
    if (!S.snap) return;
    closeCard();
    const panel = h('div', { class: 'details', role: 'dialog', 'aria-label': '组织详情' });
    const tabs = h('div', { class: 'tabs' });
    const content = h('div', { class: 'content' });
    const show = (t) => { [...tabs.children].forEach((b) => b.classList.toggle('on', b.dataset.t === t)); render(t); };
    [['trace', '上下文和轨迹'], ['tasks', '任务'], ['protocols', '协议'], ['docs', '共享文档']].forEach(([t, label]) =>
      tabs.append(h('button', { type: 'button', 'data-t': t, onclick: () => show(t) }, label)));
    panel.append(h('div', { class: 'bar' }, h('h3', null, S.snap.org.name), tabs, h('button', { class: 'icon-btn', 'aria-label': '关闭', onclick: closeLayer }, icon('x'))), content);
    scrim(panel);
    let current = opts.member || (S.view.member) || (S.snap.members[0] && S.snap.members[0].name);
    let taskFilter = opts.filter || (opts.task ? 'all' : 'open');
    async function render(t) {
      content.textContent = ''; content.className = 'content' + (t === 'trace' || t === 'docs' ? '' : ' one');
      if (t === 'trace') {
        const left = h('div', { class: 'left' }); const right = h('div', { class: 'right' });
        content.append(left, right);
        for (const m of S.snap.members) {
          left.append(h('button', { class: 'chat-row' + (m.name === current ? ' on' : ''), type: 'button', onclick: () => { current = m.name; render('trace'); } },
            avatar(m.name, { size: 'sm', dot: true, click: false }), h('div', { class: 'main' }, h('div', { class: 'name' }, h('span', { class: 'ellipsis' }, m.display || m.name)), h('div', { class: 'sub ellipsis' }, [m.harness_label, m.surface_label].filter(Boolean).join(' · '))), h('div')));
        }
        await traceView(right, current);
      } else if (t === 'tasks') {
        const right = h('div', { class: 'right' }); content.append(right);
        const filters = h('div', { class: 'seg' }, [['open', '进行中'], ['blocked', '受阻'], ['done', '已完成'], ['all', '全部']].map(([k, label]) =>
          h('button', { class: taskFilter === k ? 'on' : '', type: 'button', onclick: () => { taskFilter = k; render('tasks'); } }, label + ' ' + countTasks(k))));
        right.append(h('div', { class: 'filters' }, filters));
        const list = S.snap.tasks.filter((x) => taskFilter === 'all' || (taskFilter === 'open' ? !['done', 'dropped'].includes(x.status) : x.status === taskFilter)).slice().reverse();
        if (!list.length) right.append(h('div', { class: 'empty' }, '没有这类任务。'));
        for (const task of list) {
          const d = h('details', { class: 'task' + (opts.task === task.id ? ' hi' : ''), open: opts.task === task.id ? true : null },
            h('summary', null, task.owner ? avatar(task.owner, { size: 'sm', click: false }) : h('span'),
              h('div', { style: 'min-width:0' }, h('div', { class: 'tt ellipsis' }, task.title), h('div', { class: 'sub' }, task.id + ' · ' + (task.owner ? dname(task.owner) : '没人负责') + (task.at ? ' · 更新于 ' + dayLabel(toDate(task.at)) + ' ' + clock(task.at) : ''))),
              h('span', { class: 'chips' }, task.status === 'done' && task.report ? h('span', { class: 'chip accent' }, '有报告') : null,
                h('span', { class: 'chip ' + ({ done: 'ok', blocked: 'bad', working: 'warn' }[task.status] || '') }, TASK_LABEL[task.status] || task.status))),
            h('div', { class: 'inner' }, h('div', null, h('span', { class: 'dim' }, '标题：'), task.title),
              task.created_by ? h('div', null, h('span', { class: 'dim' }, '建立者：'), dname(task.created_by)) : null,
              task.status === 'done' && task.report ? reportBlock(task) : null,
              h('div', null, h('span', { class: 'dim' }, '证据：'), (task.evidence || []).length ? h('ul', { class: 'ev' }, task.evidence.map((ev) => h('li', null, inline(ev)))) : '（还没有）'),
              task.owner ? h('div', { class: 'row-acts' }, h('button', { class: 'btn sm', type: 'button', onclick: () => { closeLayer(); go({ kind: 'member', member: task.owner }); } }, '问问 ' + dname(task.owner))) : null));
          right.append(d);
          if (opts.task === task.id) setTimeout(() => d.scrollIntoView({ block: 'center' }), 0);
        }
      } else if (t === 'protocols') {
        const right = h('div', { class: 'right' }); content.append(right);
        if (!S.snap.protocols.length) right.append(h('div', { class: 'empty' }, '还没有协议。'));
        for (const p of S.snap.protocols.slice().reverse()) {
          right.append(h('div', { class: 'task' }, h('div', { class: 'inner' },
            h('b', null, p.id + ' ' + p.title + '（' + (p.strength === 'strong' ? '强' : '弱') + '协议 · ' + ({ active: '生效', proposed: '提案中', rejected: '被否决', superseded: '被新版替换', retired: '已废止', enacted: '已执行' }[p.status] || p.status) + '）'),
            p.retire_target ? h('div', null, h('span', { class: 'dim' }, '废止：'), p.retire_target) : null,
            p.trigger ? h('div', null, h('span', { class: 'dim' }, '适用：'), p.trigger) : null,
            p.guidance ? h('div', { style: 'white-space:pre-wrap' }, p.guidance) : null,
            p.rules && p.rules.length ? h('pre', { class: 'doc-body' }, JSON.stringify(p.rules, null, 2)) : null,
            h('div', { class: 'dim' }, '提案人 ' + dname(p.author) + ' · ' + p.votes + ' 票 · 用过 ' + p.uses + ' 次'))));
        }
      } else if (t === 'docs') {
        const left = h('div', { class: 'left' }); const right = h('div', { class: 'right' });
        content.append(left, right);
        if (!S.snap.documents.length) right.append(h('div', { class: 'empty' }, '还没有共享文档。'));
        for (const d of S.snap.documents) {
          left.append(h('button', { class: 'chat-row', type: 'button', onclick: async () => {
            right.textContent = '';
            const doc = await get(orgPath('/document?key=' + enc(d.key)));
            right.append(h('h3', { style: 'margin:0 0 4px' }, d.key + ' · 第 ' + doc.revision + ' 版'), h('div', { class: 'dim', style: 'margin-bottom:10px;font-size:12.5px' }, dname(doc.author) + ' 写于 ' + dayLabel(toDate(doc.at)) + ' ' + clock(doc.at)), h('div', { class: 'doc-body' }, doc.body));
          } }, h('div', { class: 'avatar sm group' }, icon('folder', 14)), h('div', { class: 'main' }, h('div', { class: 'name' }, d.key), h('div', { class: 'sub' }, '第 ' + d.revision + ' 版 · ' + dname(d.author))), h('div')));
        }
      }
    }
    function countTasks(k) { return S.snap.tasks.filter((x) => k === 'all' || (k === 'open' ? !['done', 'dropped'].includes(x.status) : x.status === k)).length; }
    show(tab || 'trace');
  }
  function reportBlock(task) {
    return h('div', { class: 'report' }, h('div', { class: 'report-h' }, icon('check', 14), h('b', null, '完成报告'),
      task.done_at ? h('span', { class: 'dim' }, dayLabel(toDate(task.done_at)) + ' ' + clock(task.done_at)) : null),
      h('div', { class: 'md' }, rich(task.report)));
  }
  async function traceView(box, name) {
    const m = member(name);
    box.textContent = '';
    if (!m) return;
    box.append(h('h3', { style: 'margin:0 0 2px' }, (m.display || name) + ' 的上下文和轨迹'),
      h('div', { class: 'dim', style: 'margin-bottom:12px;font-size:12.5px' }, [name, m.harness_label, m.surface_label, m.model, m.agent ? 'subagent ' + m.agent.slice(0, 12) + (m.parent ? '（在 ' + dname(m.parent) + ' 的会话里）' : '') : m.session ? '会话 ' + m.session.slice(0, 12) : ''].filter(Boolean).join(' · ')));
    const filter = { role: 'all', q: '' };
    const filters = h('div', { class: 'filters' });
    const list = h('div');
    let data = null;
    const seg = h('div', { class: 'seg' }, [['all', '全部'], ['talk', '对话'], ['tools', '动作']].map(([k, label]) => h('button', { class: k === 'all' ? 'on' : '', type: 'button', 'data-k': k, onclick: () => {
      filter.role = k; [...seg.children].forEach((b) => b.classList.toggle('on', b.dataset.k === k)); draw(); } }, label)));
    const q = h('input', { type: 'search', class: 'input', placeholder: '搜索这段记录', style: 'width:220px;height:30px' });
    q.addEventListener('input', () => { filter.q = q.value.toLowerCase(); draw(); });
    filters.append(seg, field(q));
    const older = h('button', { class: 'more', type: 'button' }, '加载更早的步骤');
    box.append(filters, older, list);
    async function fetchMore(before) {
      const r = await get(orgPath('/transcript?member=' + enc(name) + '&limit=400' + (before != null ? '&before=' + before : '')));
      data = data ? Object.assign({}, r, { steps: r.steps.concat(data.steps) }) : r;
      older.hidden = !data.start;
      draw();
    }
    older.addEventListener('click', () => fetchMore(data.start));
    function draw() {
      list.textContent = '';
      if (data && data.missing) { list.append(h('div', { class: 'empty' }, '这个席位还没有会话记录。')); return; }
      const steps = (data ? data.steps : []).filter((s) => (filter.role === 'all' || (filter.role === 'talk' ? ['user', 'assistant'].includes(s.role) : ['tool_call', 'tool_result'].includes(s.role))) &&
        (!filter.q || (s.text || '').toLowerCase().includes(filter.q)));
      if (!steps.length) list.append(h('div', { class: 'empty' }, data ? '没有符合条件的步骤。' : '正在读取…'));
      const wrap = h('div', { class: 'acts', style: 'max-width:none' }, h('div', { class: 'list', style: 'border-top:0' }));
      for (const s of steps) {
        const label = { user: '用户', assistant: '回复', tool_call: toolName(s.tool), tool_result: '结果', thinking: '思考', context: '注入的上下文' }[s.role] || s.role;
        wrap.firstChild.append(h('details', { class: 'step' + (s.error ? ' err' : s.role === 'tool_result' ? ' ok' : ''), open: ['user', 'assistant'].includes(s.role) ? true : null },
          h('summary', null, h('span', { class: 'bullet' }), h('span', { class: 'tool' }, label), h('span', { class: 'arg ellipsis' }, s.role === 'tool_call' ? stepArg(s) : clip(s.text, 120)), h('span', { class: 'state' }, clock(s.at))),
          h('div', { class: 'io' }, h('pre', null, s.text))));
      }
      if (steps.length) list.append(wrap);
      if (data && data.total) list.append(h('div', { class: 'dim', style: 'font-size:12px;margin-top:8px' }, '共 ' + data.total + ' 步' + (data.path ? ' · ' + data.path : '')));
    }
    await fetchMore(null);
  }

  // ------------------------------------------------------------------ settings (like Claude Code / Codex)
  const SECTIONS = [['profile', '个人资料', 'user'], ['appearance', '外观', 'palette'], ['language', '语言与命名', 'globe'], ['voice', '语音输入', 'mic'],
    ['notify', '通知', 'bell'], ['harness', 'Harness 连接', 'plug'], ['about', '数据与关于', 'info']];
  const installLogs = {};
  let settingsPane = null;
  function openSettings(section) {
    let current = section || 'profile';
    const nav = h('nav', null, h('h3', null, '设置'));
    const pane = h('div', { class: 'pane' });
    const box = h('div', { class: 'settings', role: 'dialog', 'aria-label': '设置' }, nav, pane);
    SECTIONS.forEach(([k, label, ic]) => nav.append(h('button', { type: 'button', 'data-k': k, onclick: () => { current = k; draw(); } }, icon(ic, 16), label)));
    function draw() {
      [...nav.querySelectorAll('button')].forEach((b) => b.classList.toggle('on', b.dataset.k === current));
      pane.textContent = '';
      pane.append(h('button', { class: 'icon-btn close', 'aria-label': '关闭', onclick: () => { settingsPane = null; closeLayer(); } }, icon('x')));
      settingsPane = { draw, current };
      ({ profile: drawProfile, appearance: drawAppearance, language: drawLanguage, voice: drawVoice, notify: drawNotify, harness: drawHarness, about: drawAbout })[current](pane);
    }
    scrim(box);
    draw();
  }
  function setRow(title, desc, control) {
    return h('div', { class: 'set-row' }, h('div', { class: 'l' }, h('b', null, title), desc ? h('span', null, desc) : null), h('div', { class: 'r' }, control));
  }
  function segControl(options, value, onPick) {
    return h('div', { class: 'seg' }, options.map(([k, label]) => h('button', { class: value === k ? 'on' : '', type: 'button', onclick: () => onPick(k) }, label)));
  }
  function toggleControl(value, onChange) {
    const t = h('input', { type: 'checkbox', class: 'toggle' }); t.checked = !!value;
    t.addEventListener('change', () => onChange(t.checked));
    return t;
  }
  function redraw() { if (settingsPane) settingsPane.draw(); }
  function drawProfile(pane) {
    pane.append(h('h4', null, '个人资料'));
    const name = h('input', { class: 'input', value: PREFS.name || '', placeholder: '你', style: 'width:220px' });
    const saveName = () => setPrefs({ name: name.value.trim() }).then(() => { renderAll(false); });
    name.addEventListener('change', saveName);
    name.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.isComposing) name.blur(); });
    const av = avatar(HUMAN, { size: 'lg', click: false });
    pane.append(setRow('头像', '显示在你发的每条消息旁边。', h('div', { style: 'display:flex;align-items:center;gap:10px' }, av,
      h('button', { class: 'btn sm', type: 'button', onclick: async () => {
        const data = await pickImage(); if (!data) return;
        try { const r = await post('/api/avatar', { data }); PREFS.avatar = r.avatar; applyPrefs(); renderAll(false); redraw(); } catch (e) { toast(e.message); }
      } }, '更换'),
      PREFS.avatar ? h('button', { class: 'btn sm ghost', type: 'button', onclick: async () => { await post('/api/avatar', { data: '' }); PREFS.avatar = null; applyPrefs(); renderAll(false); redraw(); } }, '移除') : null)));
    pane.append(setRow('名字', 'App 里怎么称呼你（成员看到的发件人仍是 human）。', field(name)));
  }
  function drawAppearance(pane) {
    pane.append(h('h4', null, '外观'));
    pane.append(setRow('主题', null, segControl([['system', '跟随系统'], ['light', '浅色'], ['dark', '深色']], PREFS.theme, (k) => { setPrefs({ theme: k }); redraw(); })));
    const colors = { clay: '#C8643F', ink: '#3A3936', indigo: '#5B61D6', blue: '#2F6BD8', rose: '#C4456C', amber: '#B9821D' };
    pane.append(setRow('强调色', '按钮、链接、你的气泡和选中项用这个颜色。', h('div', { class: 'swatches' }, Object.entries(colors).map(([k, c]) =>
      h('button', { class: 'swatch' + (PREFS.accent === k ? ' on' : ''), type: 'button', title: k, style: 'background:' + c, onclick: () => { setPrefs({ accent: k }); redraw(); } })))));
    pane.append(setRow('字号', null, segControl([['small', '小'], ['medium', '中'], ['large', '大']], PREFS.font, (k) => { setPrefs({ font: k }); redraw(); })));
    pane.append(setRow('消息间距', null, segControl([['comfortable', '舒适'], ['compact', '紧凑']], PREFS.density, (k) => { setPrefs({ density: k }); redraw(); })));
  }
  function drawLanguage(pane) {
    pane.append(h('h4', null, '语言与命名'));
    const sel = h('select', { class: 'input', style: 'width:200px' }, [['', '跟随系统（' + (navigator.language || '') + '）'], ['zh-CN', '简体中文'], ['zh-TW', '繁體中文'], ['en-US', 'English'], ['ja-JP', '日本語']].map(([v, l]) =>
      h('option', { value: v, selected: (PREFS.lang || '') === v ? true : null }, l)));
    sel.addEventListener('change', () => setPrefs({ lang: sel.value }).then(scheduleRefresh));
    pane.append(setRow('语言', '成员的默认名字、语音输入都用这个语言。', sel));
    pane.append(setRow('成员按职责自动起名', '没改过名字的成员，用它负责的事情起名（必要时用一次很小的 Claude 调用翻译）。', toggleControl(PREFS.auto_names, (v) => setPrefs({ auto_names: v }).then(scheduleRefresh))));
  }
  function drawVoice(pane) {
    pane.append(h('h4', null, '语音输入'));
    pane.append(setRow('语音输入', '每个输入框旁边的麦克风：点一下开始说，再点一下停止。', segControl([['browser', 'Edge 语音识别'], ['off', '关闭']], PREFS.voice, (k) => { setPrefs({ voice: k }).then(() => { renderAll(false); redraw(); }); })));
    const test = h('textarea', { class: 'input', rows: 2, placeholder: '在这里试一下语音输入' });
    pane.append(setRow('试一试', Voice.supported() ? '用的是 Edge 自带的语音识别（微软的在线服务）。' : '这个窗口用不了浏览器语音识别。', h('div', { class: 'field', style: 'width:300px' }, test, micButton(test))));
    pane.append(h('div', { class: 'dim', style: 'font-size:12.5px;line-height:1.7;margin-top:10px' },
      '微信自带的语音转文字没有给第三方 App 用的公开接口。想要微信那样的识别效果：装「微信输入法」，它的语音输入在任何输入框里都能用，包括 Relic App。也可以按 Win+H 用 Windows 自带的语音输入。'));
  }
  function drawNotify(pane) {
    pane.append(h('h4', null, '通知'));
    pane.append(setRow('桌面通知', '窗口不在前台时，有需要你决定的事或有人给你发消息就提醒你。', toggleControl(PREFS.notify, async (v) => {
      if (v && 'Notification' in window && Notification.permission !== 'granted') await Notification.requestPermission();
      setPrefs({ notify: v });
    })));
    pane.append(setRow('测试一下', null, h('button', { class: 'btn sm', type: 'button', onclick: async () => {
      if (!('Notification' in window)) { toast('这个窗口不支持桌面通知。'); return; }
      if (Notification.permission !== 'granted') await Notification.requestPermission();
      if (Notification.permission === 'granted') new Notification('Relic', { body: '通知已经打开。', icon: '/static/icon-192.png' }); else toast('没有通知权限。');
    } }, '发一条测试通知')));
  }
  async function drawHarness(pane) {
    pane.append(h('h4', null, 'Harness 连接'));
    pane.append(h('div', { class: 'dim', style: 'font-size:12.5px;margin-bottom:12px' }, 'Relic App 通过 Agent Client Protocol（ACP）连接各家 coding harness：每个内嵌成员是一个 ACP 会话，成员之间的消息走 Relic。'));
    const list = await harnessList(true);
    for (const x of list.filter((y) => !y.later)) {
      const path = h('input', { class: 'input mono', value: (PREFS.paths || {})[x.id] || '', placeholder: x.program || '自动查找', style: 'font-size:12px' });
      const log = h('div', { class: 'log', hidden: !installLogs[x.id] }, (installLogs[x.id] || []).join('\n'));
      const kv = h('dl', { class: 'kv' });
      const row = (k, v) => append(kv, [h('dt', null, k), h('dd', null, v)]);
      row('状态', x.available ? h('span', { class: 'chip ok' }, '已连接') : h('span', { class: 'chip bad' }, x.problem || '没连上'));
      row('程序', h('div', { style: 'display:flex;gap:6px' }, path, h('button', { class: 'btn sm', type: 'button', onclick: () => setPrefs({ paths: Object.assign({}, PREFS.paths, { [x.id]: path.value.trim() }) }).then(() => { toast('已保存程序路径。'); redraw(); }) }, '保存')));
      row('ACP 适配器', x.adapter_installed ? x.adapter + '（' + x.adapter_version + '）' : '没安装：' + x.adapter);
      row('Node.js', x.node || '没找到');
      row('默认模式', x.mode || '适配器默认' + (x.note ? '（' + x.note + '）' : ''));
      if (x.models && x.models.length) row('可选模型', x.models.join('、'));
      const install = h('button', { class: 'btn sm', type: 'button', onclick: async () => {
        installLogs[x.id] = ['$ ' + x.install]; log.hidden = false; log.textContent = installLogs[x.id].join('\n');
        try { await post('/api/harnesses/' + x.id + '/install', {}); } catch (e) { toast(e.message); }
      } }, x.adapter_installed ? '重新安装适配器' : '安装适配器');
      pane.append(h('div', { class: 'harness', 'data-id': x.id }, h('div', { class: 'h' }, h('b', null, x.title), h('span', { class: 'dim' }, x.vendor), h('div', { style: 'flex:1' }), install), kv, log));
    }
    pane.append(h('h4', { style: 'margin-top:12px;font-size:15px' }, '以后接入'));
    pane.append(h('div', { class: 'later-list' }, list.filter((y) => y.later).map((x) => h('div', { class: 'it' }, h('span', null, h('b', null, x.title), ' ', h('span', { class: 'dim' }, x.vendor)), h('span', { class: 'mono dim' }, x.launch)))));
    pane.append(h('div', { class: 'dim', style: 'font-size:12px;margin-top:8px' }, '这些 harness 都在 ACP 官方注册表里（agentclientprotocol.com）；接一个是在 app/harness.py 里加一条启动方式。'));
  }
  function onInstall(ev) {
    const lines = installLogs[ev.id] || (installLogs[ev.id] = []);
    if (ev.line) lines.push(ev.line);
    if ('done' in ev) { lines.push(ev.done === 0 ? '安装完成。' : '安装失败（退出码 ' + ev.done + '）。'); S.harnesses = null; toast(ev.done === 0 ? '适配器装好了。' : '适配器没装上，看设置里的日志。'); }
    const log = document.querySelector('.harness[data-id="' + ev.id + '"] .log');
    if (log) { log.hidden = false; log.textContent = lines.slice(-200).join('\n'); log.scrollTop = log.scrollHeight; }
    if ('done' in ev && settingsPane && settingsPane.current === 'harness') setTimeout(redraw, 300);
  }
  function drawAbout(pane) {
    pane.append(h('h4', null, '数据与关于'));
    const open = (what) => post('/api/open', { what }).catch((e) => toast(e.message));
    pane.append(setRow('数据目录', PREFS.data || '~/.relic', h('button', { class: 'btn sm', type: 'button', onclick: () => open('data') }, '打开')));
    pane.append(setRow('运行日志', '自动唤醒和成员会话的日志。', h('button', { class: 'btn sm', type: 'button', onclick: () => open('logs') }, '打开')));
    pane.append(setRow('本机服务', '只有这台电脑能访问：127.0.0.1:' + (PREFS.port || ''), h('span', { class: 'chip' }, 'v' + (PREFS.version || ''))));
    pane.append(setRow('装成独立应用', isApp() ? '现在就是装好的 Relic 应用。' : '装好后 Relic 有自己的窗口、任务栏图标和开始菜单入口；顶上没有浏览器边框，窗口栏就是 Relic 自己的工具栏。',
      isApp() ? h('span', { class: 'chip ok' }, '已安装') : h('button', { class: 'btn sm', type: 'button', onclick: () => { settingsPane = null; closeLayer(); installApp(); } }, '安装…')));
  }

  // ------------------------------------------------------------------ window bar (after Codex and Claude Code)
  let installEvent = null, installUI = null;
  const isApp = () => /[?&]source=pwa\b/.test(location.search) || matchMedia('(display-mode: window-controls-overlay)').matches;
  const MENUS = [['file', '文件'], ['edit', '编辑'], ['view', '视图'], ['help', '帮助']];
  function abBtn(ic, title, onclick, opts = {}) {
    return h('button', { class: 'ab-btn' + (opts.on ? ' on' : '') + (opts.cls ? ' ' + opts.cls : ''), type: 'button', title, 'aria-label': title,
      disabled: opts.disabled ? true : null, onmousedown: (e) => e.preventDefault(), onclick }, icon(ic, 16), opts.badge ? h('span', { class: 'ab-badge' }, opts.badge) : null);
  }
  function renderAppbar() {
    const bar = $('#appbar');
    if (!bar) return;
    bar.textContent = '';
    const v = S.view;
    const title = !S.snap ? 'Relic' : S.snap.org.name + ' · ' + (v.kind === 'group' ? '群聊' : v.kind === 'secretary' ? '秘书' : dname(v.member));
    const n = S.snap ? S.snap.decisions.length : 0;
    const openBar = menuEl && menuEl.dataset.bar;
    append(bar, [
      h('div', { class: 'ab-left' },
        h('img', { class: 'ab-logo', src: '/static/icon.svg', alt: '' }),
        abBtn('sidebar', (S.sideOpen ? '收起' : '展开') + '侧边栏（Ctrl+B）', () => toggleSide()),
        abBtn('back', '后退（Alt+←）', () => goHist(-1), { disabled: S.histIdx <= 0 }),
        abBtn('fwd', '前进（Alt+→）', () => goHist(1), { disabled: S.histIdx >= S.hist.length - 1 }),
        h('nav', { class: 'ab-menus', 'aria-label': '菜单' }, MENUS.map(([k, label]) => h('button', { class: 'ab-menu' + (openBar === k ? ' on' : ''), type: 'button', 'data-menu': k,
          onmousedown: (e) => e.preventDefault(), onclick: (e) => openAppMenu(k, e.currentTarget),
          onmouseenter: (e) => { if (menuEl && menuEl.dataset.bar && menuEl.dataset.bar !== k) openAppMenu(k, e.currentTarget); } }, label)))),
      h('div', { class: 'ab-title ellipsis', title }, title),
      h('div', { class: 'ab-right' },
        isApp() ? null : h('button', { class: 'ab-install', type: 'button', title: '装成独立应用：自己的窗口和任务栏图标，没有浏览器边框', onmousedown: (e) => e.preventDefault(), onclick: installApp }, icon('download', 14), '安装'),
        abBtn('bell', n ? n + ' 件事需要你决定' : '现在没有需要你决定的事', () => { setPane('org'); const b = $('#panel .pane-body'); if (b) b.scrollTop = 0; }, { badge: n || null, cls: n ? 'alert' : '' }),
        h('span', { class: 'ab-sep' }),
        PANES.map(([k, label, ic], i) => abBtn(ic, label + '（Alt+' + (i + 1) + '）', () => (S.panelOpen && S.pane === k ? togglePanel(false) : setPane(k)), { on: S.panelOpen && S.pane === k })))]);
  }
  function openAppMenu(k, anchor) {
    if (menuEl && menuEl.dataset.bar === k) { closeMenu(); return; }
    closeMenu();
    const r = anchor.getBoundingClientRect();
    menuEl = h('div', { class: 'menu bar-menu', 'data-bar': k, role: 'menu', style: 'left:' + Math.max(4, Math.min(r.left, window.innerWidth - 270)) + 'px;top:' + (r.bottom + 4) + 'px' }, appMenu(k));
    document.body.append(menuEl);
    anchor.classList.add('on');
  }
  function menuItem(label, opts = {}) {
    return h('button', { class: 'item', type: 'button', role: 'menuitem', disabled: opts.disabled ? true : null, onmousedown: (e) => e.preventDefault(),
      onclick: () => { closeMenu(); if (opts.run) opts.run(); } },
      h('span', { class: 'ck' }, opts.check ? icon('check', 14) : null), h('span', { class: 'lb' }, label), opts.key ? h('kbd', null, opts.key) : null);
  }
  const menuSep = () => h('div', { class: 'sep' });
  const toGroup = (fn) => () => { if (S.view.kind !== 'group') go({ kind: 'group' }); fn(); };
  function appMenu(k) {
    const sec = S.snap && secretaryName();
    if (k === 'file') {
      return [menuItem('新建组织…', { run: orgDialog }),
        menuItem('添加成员…', { run: () => memberDialog(), disabled: !S.snap }),
        menuItem(sec ? '打开秘书' : '设置秘书…', { run: () => (sec ? go({ kind: 'secretary', member: sec }) : openSecretarySetup()), disabled: !S.snap }),
        menuSep(),
        menuItem('组织详情…', { run: () => openDetails('trace'), disabled: !S.snap }),
        menuItem('打开数据目录', { run: () => post('/api/open', { what: 'data' }).catch((e) => toast(e.message)) }),
        menuItem('打开运行日志', { run: () => post('/api/open', { what: 'logs' }).catch((e) => toast(e.message)) }),
        menuSep(),
        isApp() ? null : menuItem('安装为独立应用…', { run: installApp }),
        menuItem('设置…', { key: 'Ctrl+,', run: () => openSettings() })];
    }
    if (k === 'edit') {
      return [menuItem('撤销', { key: 'Ctrl+Z', run: () => document.execCommand('undo') }),
        menuItem('重做', { key: 'Ctrl+Y', run: () => document.execCommand('redo') }),
        menuSep(),
        menuItem('剪切', { key: 'Ctrl+X', run: () => document.execCommand('cut') }),
        menuItem('复制', { key: 'Ctrl+C', run: () => document.execCommand('copy') }),
        menuItem('粘贴', { key: 'Ctrl+V', run: pasteText }),
        menuItem('全选', { key: 'Ctrl+A', run: () => document.execCommand('selectAll') }),
        menuSep(),
        menuItem('引用选中的文字', { run: quoteSelection }),
        menuItem('搜索组织和成员', { key: 'Ctrl+K', run: focusSearch })];
    }
    if (k === 'view') {
      return [menuItem('侧边栏', { key: 'Ctrl+B', check: S.sideOpen, run: () => toggleSide() }),
        menuItem('右侧栏', { key: 'Ctrl+Alt+B', check: S.panelOpen, run: () => togglePanel() }),
        menuSep(),
        PANES.map(([p, label], i) => menuItem('右侧：' + label, { key: 'Alt+' + (i + 1), check: S.panelOpen && S.pane === p, run: () => setPane(p) })),
        menuSep(),
        menuItem('群聊翻译成人话', { key: 'Ctrl+Shift+L', check: S.plainMode, disabled: !S.snap, run: toGroup(togglePlain) }),
        menuItem('群聊解读', { check: S.digestOpen, disabled: !S.snap, run: toGroup(toggleDigest) }),
        menuSep(),
        [['system', '跟随系统'], ['light', '浅色'], ['dark', '深色']].map(([t, label]) => menuItem('主题：' + label, { check: PREFS.theme === t, run: () => setPrefs({ theme: t }) })),
        [['small', '小'], ['medium', '中'], ['large', '大']].map(([f, label]) => menuItem('字号：' + label, { check: PREFS.font === f, run: () => setPrefs({ font: f }) })),
        menuSep(),
        menuItem('重新载入', { key: 'Ctrl+R', run: () => location.reload() })];
    }
    return [menuItem('快捷键', { run: shortcutsDialog }),
      menuItem('语音输入', { run: () => openSettings('voice') }),
      menuItem('Harness 连接', { run: () => openSettings('harness') }),
      menuSep(),
      menuItem('关于 Relic App', { run: () => openSettings('about') })];
  }
  function focusSearch() { if (!S.sideOpen) toggleSide(true); const s = $('#search'); s.focus(); s.select(); }
  async function pasteText() {
    const el = document.activeElement;
    if (!el || !/^(TEXTAREA|INPUT)$/.test(el.tagName)) { toast('先点一下要粘贴进去的输入框。'); return; }
    try { const text = await navigator.clipboard.readText(); el.focus(); document.execCommand('insertText', false, text); } catch (e) { toast('读不了剪贴板：直接按 Ctrl+V。'); }
  }
  function quoteSelection() {
    const sel = window.getSelection();
    const text = sel ? sel.toString().trim() : '';
    if (!text) { toast('先在消息里选中一段文字。'); return; }
    const node = sel.anchorNode && (sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement);
    const bubble = node && node.closest('.bubble');
    setQuote(bubble && bubble.dataset.from ? dname(bubble.dataset.from) : '引用', text);
    sel.removeAllRanges();
  }
  function shortcutsDialog() {
    const rows = [['Ctrl+B', '收起 / 展开侧边栏'], ['Ctrl+Alt+B', '收起 / 展开右侧栏'], ['Alt+1 / 2 / 3', '右侧栏：概况 / 工作区 / 文件'], ['Alt+← / Alt+→', '后退 / 前进'],
      ['Ctrl+K', '搜索组织和成员'], ['Ctrl+Shift+L', '群聊翻译成人话'], ['Ctrl+,', '设置'], ['Enter / Shift+Enter', '发送 / 换行'], ['@', '在群里点名成员'], ['Esc', '关闭弹窗和菜单']];
    scrim(h('div', { class: 'dialog', role: 'dialog' }, h('h3', null, '快捷键'),
      h('dl', { class: 'keys' }, rows.map(([key, what]) => [h('dt', null, h('kbd', null, key)), h('dd', null, what)])),
      h('div', { class: 'acts-row' }, h('button', { class: 'btn primary', type: 'button', onclick: closeLayer }, '好'))));
  }
  function shortcut(e) {
    if (e.isComposing) return;
    const ctrl = e.ctrlKey || e.metaKey;
    const k = (e.key || '').toLowerCase();
    let hit = true;
    if (ctrl && e.altKey && !e.shiftKey && k === 'b') togglePanel();
    else if (ctrl && !e.altKey && !e.shiftKey && k === 'b') toggleSide();
    else if (e.altKey && !ctrl && !e.shiftKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) goHist(e.key === 'ArrowLeft' ? -1 : 1);
    else if (e.altKey && !ctrl && !e.shiftKey && /^[123]$/.test(e.key)) { const p = PANES[Number(e.key) - 1][0]; if (S.panelOpen && S.pane === p) togglePanel(false); else setPane(p); }
    else if (ctrl && !e.altKey && !e.shiftKey && k === 'k') focusSearch();
    else if (ctrl && !e.altKey && k === ',') openSettings();
    else if (ctrl && e.shiftKey && !e.altKey && k === 'l') { if (S.snap) toGroup(togglePlain)(); }
    else hit = false;
    if (hit) e.preventDefault();
  }

  // installing the App as an application: Edge offers it in a normal window; app windows started with --app cannot
  async function installApp() {
    if (installEvent) {
      const ev = installEvent;
      ev.prompt();
      const choice = await ev.userChoice.catch(() => null);
      if (choice && choice.outcome === 'accepted') installEvent = null;
      renderAppbar();
      return;
    }
    scrim(h('div', { class: 'dialog', role: 'dialog' }, h('h3', null, '把 Relic 装成独立应用'),
      h('p', { class: 'lead' }, '装好后 Relic 有自己的窗口、任务栏图标和开始菜单入口；顶上没有浏览器边框，这条窗口栏就是标题栏。'),
      h('ol', { class: 'steps' }, h('li', null, '点「在 Edge 里打开」，会开一个普通的 Edge 窗口。'),
        h('li', null, '在那个窗口里点「安装 Relic」（或地址栏右侧的「应用可用」图标），再点「安装」。'),
        h('li', null, '装好后关掉那个 Edge 窗口。以后打开 Relic App 会直接用装好的应用。')),
      h('div', { class: 'acts-row' }, h('button', { class: 'btn', type: 'button', onclick: closeLayer }, '以后再说'),
        h('button', { class: 'btn primary', type: 'button', onclick: async () => {
          try { await post('/api/install-window', {}); closeLayer(); toast('已经打开 Edge 窗口，在那里点「安装 Relic」。', 6000); } catch (e) { toast(e.message); }
        } }, '在 Edge 里打开'))));
  }
  function installPage() {
    const btn = h('button', { class: 'btn primary', type: 'button', onclick: installApp }, icon('download', 15), '安装 Relic');
    const note = h('div', { class: 'dim', style: 'font-size:12.5px;line-height:1.7' });
    installUI = () => {
      btn.disabled = !installEvent;
      note.textContent = installEvent ? '点「安装 Relic」，再在 Edge 弹出的框里点「安装」。'
        : '正在等 Edge 准备好安装……按钮一直是灰的话：点地址栏右侧的「应用可用」图标，或者 Edge 菜单「…」→「应用」→「将此站点作为应用安装」。已经装过的话，地址栏右侧会显示「在应用中打开」。';
    };
    installUI();
    scrim(h('div', { class: 'dialog', role: 'dialog' }, h('h3', null, '安装 Relic App'),
      h('p', { class: 'lead' }, '装好后 Relic 有自己的窗口、任务栏图标和开始菜单入口；顶上没有浏览器边框，窗口栏就是 Relic 自己的工具栏：侧边栏开关、前进后退、菜单、右侧分区。'),
      note, h('div', { class: 'acts-row' }, h('button', { class: 'btn', type: 'button', onclick: closeLayer }, '关闭'), btn)));
  }

  // ------------------------------------------------------------------ boot
  function wire() {
    $('#btn-new-org').append(icon('neworg', 17), h('span', null, '新建组织'));
    $('#btn-new-org').addEventListener('click', orgDialog);
    $('#btn-settings').append(icon('gear', 18));
    $('#btn-settings').addEventListener('click', () => openSettings());
    $('#me').addEventListener('click', () => openSettings('profile'));
    $('#search-icon').append(icon('search', 15));
    const search = $('#search');
    search.addEventListener('input', (e) => { S.search = e.target.value; renderSide(); });
    if (PREFS.voice !== 'off') search.parentElement.append(micButton(search, 'mic'));
    window.addEventListener('resize', () => { closeMention(); closeMenu(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closeCard(); closeMention(); closeMenu(); closeSelBar(); if (!$('#layer').firstChild) return; settingsPane = null; closeLayer(); } });
    window.addEventListener('hashchange', () => {
      const w = readHash();
      if (!w) return;
      if (w.org !== S.orgId) { if (S.orgs.some((o) => o.id === w.org)) openOrg(w.org, w.view); return; }
      const sec = secretaryName();
      const view = w.view.kind === 'secretary' ? { kind: 'secretary', member: sec } : w.view;
      if ((view.kind !== S.view.kind || view.member !== S.view.member) && (view.kind === 'group' || member(view.member))) go(view);
    });
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyPrefs);
    if (navigator.windowControlsOverlay) {
      const wco = () => document.body.classList.toggle('wco', navigator.windowControlsOverlay.visible);
      navigator.windowControlsOverlay.addEventListener('geometrychange', wco); wco();
    }
    document.addEventListener('keydown', shortcut);
    $('#app').classList.toggle('no-side', !S.sideOpen);
    renderAppbar();
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {});
    window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); installEvent = e; renderAppbar(); if (installUI) installUI(); });
    window.addEventListener('appinstalled', () => {
      installEvent = null;
      if (installUI) { installUI = null; closeLayer(); }
      toast('装好了：以后从开始菜单或任务栏打开 Relic。', 6000);
      renderAppbar();
    });
  }
  (async () => {
    const wantInstall = location.hash === '#install';
    await loadPrefs();
    wire();
    try {
      const wanted = readHash();
      if (wanted) S.orgId = wanted.org;
      await loadOrgs();
      if (S.orgId) await openOrg(S.orgId, wanted && wanted.org === S.orgId ? wanted.view : null);
      else renderAll(true);
    } catch (e) {
      $('#stream-inner').append(h('div', { class: 'notice' }, h('span', null, '读取组织失败：' + e.message)));
    }
    connect();
    if (wantInstall) installPage();
  })();
})();
