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
    cc: 'M4 6h16v12H4zM4 7l8 6 8-6',
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
    minus: 'M5 12h14',
    fit: 'M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5',
    chart: 'M9 3h6v5H9zM3 16h6v5H3zM15 16h6v5h-6zM12 8v4M6 16v-4h12v4',
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
    if (d.toDateString() === today.toDateString()) return t('time.today');
    if (d.toDateString() === y.toDateString()) return t('time.yesterday');
    return new Intl.DateTimeFormat(uiLang(), d.getFullYear() !== today.getFullYear() ? { year: 'numeric', month: 'long', day: 'numeric' } : { month: 'long', day: 'numeric' }).format(d);
  }
  function clock(iso) { const d = toDate(iso); return d ? pad(d.getHours()) + ':' + pad(d.getMinutes()) : ''; }
  function shortWhen(iso) {
    const d = toDate(iso); if (!d) return '';
    const today = new Date(); const y = new Date(); y.setDate(today.getDate() - 1);
    return d.toDateString() === today.toDateString() ? clock(iso) : d.toDateString() === y.toDateString() ? t('time.yesterday') : new Intl.DateTimeFormat(uiLang(), { month: 'numeric', day: 'numeric' }).format(d);
  }
  function ago(iso) {
    const d = toDate(iso); if (!d) return '';
    const s = (Date.now() - d.getTime()) / 1000;
    if (s < 60) return t('time.just_now');
    if (s < 3600) return t('time.minutes_ago', { n: Math.floor(s / 60) });
    if (s < 86400) return t('time.hours_ago', { n: Math.floor(s / 3600) });
    return dayLabel(d);
  }
  const clip = (s, n) => { s = String(s || '').replace(/\s+/g, ' ').trim(); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
  function stateLabel(s) {
    return ({ running: t('state.running'), working: t('state.working'), active: t('state.active'), waiting: t('state.waiting'), starting: t('state.starting'),
      error: t('state.error'), idle: t('state.idle'), vacant: t('state.vacant') })[s] || s;
  }
  function taskLabel(s) { return ({ open: t('task.open'), working: t('task.working'), blocked: t('task.blocked'), done: t('task.done'), dropped: t('task.dropped') })[s] || s; }

  // an absolute path in a message opens in the file preview on the right (files in a member's workspace only)
  const PATH_RE = /^[A-Za-z]:[\\/]/;
  function pathLink(text) {
    const m = /^(.*?)(?::(\d+))?(?::\d+)?$/.exec(text);
    return h('a', { class: 'path', href: '#', title: t('chat.path_preview'), onclick: (e) => { e.preventDefault(); openFile(m[1], m[2] ? Number(m[2]) : 0); } }, text);
  }
  function inline(text) {
    const out = [];
    // the \u escapes are the full-width punctuation that ends a link or a path: parentheses, comma, full stop,
    // semicolon, colon, enumeration comma, lenticular brackets, corner and title quotes
    const re = /(`[^`\n]+`|\*\*[^*\n]+\*\*|https?:\/\/[^\s<>)\uff09\]]+|\b[A-Za-z]:[\\/][^\s<>"'|*?\uff0c\u3002\uff1b\uff1a\u3001\uff08\uff09)\]\u3010\u3011\u300c\u300d\u300a\u300b“”]+)/g;
    let last = 0, m;
    while ((m = re.exec(text))) {
      if (m.index > last) out.push(text.slice(last, m.index));
      const tok = m[0];
      if (tok[0] === '`') { const c = tok.slice(1, -1); out.push(h('code', null, PATH_RE.test(c) ? pathLink(c) : c)); }
      else if (tok.startsWith('**')) out.push(h('b', null, tok.slice(2, -2)));
      else if (PATH_RE.test(tok)) { const core = tok.replace(/[.,;:!?]+$/, ''); out.push(pathLink(core)); if (core.length < tok.length) out.push(tok.slice(core.length)); }
      else out.push(h('a', { href: tok, target: '_blank', rel: 'noopener noreferrer' }, tok));
      last = m.index + tok.length;
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
    const m = /^([^\n\uff1a:]{1,40})[\uff1a:]\s?([\s\S]*)$/.exec(text);  // \uff1a is the full-width colon
    return h('div', { class: 'quote' }, m ? [h('b', null, t('chat.quote_from', { name: m[1] })), m[2]] : text);
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
    const box = h('div', { class: 'toast', role: 'status' }, text);
    document.body.append(box);
    setTimeout(() => box.remove(), ms);
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
    try { Object.assign(PREFS, await post('/api/prefs', changes)); } catch (e) { toast(t('prefs.save_failed', { error: e.message })); }
  }

  // ------------------------------------------------------------------ language
  // Every word the page shows comes from the word list of the person's language (relic_core/locales/<code>.json),
  // served by /api/i18n with what the list lacks filled in from English. t('key') gives a text; t('key', { n: 3 })
  // fills {n} in it (a number named n also picks the plural form; an array reads as a list in the language, by its
  // list.* texts; "a, b, and c" in English). tn() gives texts and nodes, for a sentence that holds an element. A language
  // without a word list shows the nearest one (or English); members are still named and explained in it (lang() above).
  const L = { lang: 'en-US', strings: {}, languages: [], loaded: false, missing: new Set(), plural: new Intl.PluralRules('en') };
  const uiLang = () => L.lang;
  function tget(key, args) {
    let v = L.strings[key];
    if (v == null) {
      if (L.loaded && !L.missing.has(key)) { L.missing.add(key); console.warn('Relic: no text for', key); }
      return key;
    }
    if (typeof v === 'object') {
      const n = args && typeof args.n === 'number' ? args.n : NaN;
      v = (!isNaN(n) && v[L.plural.select(n)]) || v.other || '';
    }
    return String(v);
  }
  function targ(v) {
    if (!Array.isArray(v)) return v == null ? '' : String(v);
    const items = v.map(String);
    const join = (key, a, b) => (L.strings[key] || '{a}, {b}').replace('{a}', () => a).replace('{b}', () => b);
    if (items.length < 2) return items[0] || '';
    if (items.length === 2) return join('list.pair', items[0], items[1]);
    let text = join('list.end', items[items.length - 2], items[items.length - 1]);
    for (let i = items.length - 3; i >= 0; i--) text = join('list.middle', items[i], text);
    return text;
  }
  function t(key, args) {
    const v = tget(key, args);
    return args ? v.replace(/\{(\w+)\}/g, (m, k) => (k in args ? targ(args[k]) : m)) : v;
  }
  function tn(key, args) {
    const v = tget(key, args), out = [];
    let at = 0;
    for (const m of v.matchAll(/\{(\w+)\}/g)) {
      out.push(v.slice(at, m.index));
      const a = args ? args[m[1]] : undefined;
      out.push(a instanceof Node ? a : a === undefined ? m[0] : targ(a));
      at = m.index + m[0].length;
    }
    out.push(v.slice(at));
    return out.filter((x) => x !== '');
  }
  async function loadLang() {
    try {
      const r = await get('/api/i18n?lang=' + enc(lang()));
      Object.assign(L, { lang: r.lang || L.lang, strings: r.strings || {}, languages: r.languages || [] });
    } catch (e) { /* the page shows the keys */ }
    L.loaded = true;
    try { L.plural = new Intl.PluralRules(L.lang); } catch (e) { /* English plural rules */ }
    document.documentElement.lang = L.lang;
    // the page's own markup (index.html): data-i18n holds the key of its text, data-i18n-title (-placeholder,
    // -aria-label) the key of that attribute
    document.querySelectorAll('[data-i18n]').forEach((n) => { n.textContent = t(n.dataset.i18n); });
    for (const attr of ['title', 'placeholder', 'aria-label']) {
      document.querySelectorAll('[data-i18n-' + attr + ']').forEach((n) => n.setAttribute(attr, t(n.getAttribute('data-i18n-' + attr))));
    }
  }

  // ------------------------------------------------------------------ state
  const S = {
    orgs: [], orgId: load('relic.org', null), snap: null, harnesses: null,
    view: { kind: 'group', member: null }, chat: null, convo: null, live: {}, thread: null, threadData: null,
    search: '', to: ['all'], quote: null, panelOpen: load('relic.panel', true), folded: new Set(load('relic.folded', [])), seen: {},
    mode: load('relic.mode', 'direct'),
    pane: load('relic.pane', 'org'), sideOpen: load('relic.side', true), hist: [], histIdx: -1, file: null, workMember: null,
    plain: {}, plainPending: new Set(), plainFailed: new Set(), plainOne: new Set(), plainMode: false,
    digest: null, digestPending: false, digestOpen: false,
    cc: { items: [], unread: 0, loaded: false },  // copies sent to the person, from every organization
  };
  if (!['org', 'work', 'file'].includes(S.pane)) S.pane = 'org';
  S.lastPane = S.pane;
  if (window.innerWidth <= 1180) S.panelOpen = false;  // narrow windows: the right side opens over the chat when asked for
  const plainOn = () => !!load('relic.plain.' + S.orgId, false);
  const orgPath = (rest) => '/api/org/' + enc(S.orgId) + (rest || '');
  const member = (name) => (S.snap && S.snap.members.find((m) => m.name === name)) || null;
  const secretaryName = () => S.snap && S.snap.org.secretary;
  const chatKey = () => S.view.kind === 'group' ? 'group' : 'member:' + S.view.member;
  const myName = () => PREFS.name || t('common.you');
  function dname(name) {
    if (name === HUMAN) return myName();
    // a member of another organization, named "<org id>/<member>": shown with its organization's name
    const away = /^([^\/]+)\/(.+)$/.exec(String(name || ''));
    if (away) {
      const o = S.orgs.find((x) => x.id === away[1]);
      return t('common.member_of_org', { member: away[2], org: o ? o.name : away[1] });
    }
    const m = member(name);
    return m ? m.display || name : name;
  }
  // a member named after the title it holds (leader, secretary) is shown by its id next to that title
  function roleName(name, title) { const d = dname(name); return d === title ? name : d; }

  // ------------------------------------------------------------------ avatars
  function avatar(name, opts = {}) {
    const size = opts.size ? ' ' + opts.size : '';
    if (name === HUMAN) {
      const a = h('div', { class: 'avatar human' + size, title: myName() }, PREFS.avatar ? h('img', { src: PREFS.avatar, alt: '' }) : initial(myName()));
      return a;
    }
    const m = member(name);
    const label = m ? m.display || name : dname(name);
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
  // an organization's initial: a subgroup's badge is dashed, the secretariat's ringed
  function orgBadge(o) {
    return h('span', { class: 'org-badge' + (o.kind === 'subgroup' ? ' sub' : '') + (o.cabinet ? ' cab' : ''),
      style: 'background:hsl(' + hue(o.id) + ' 40% 90%);color:hsl(' + hue(o.id) + ' 38% 34%)' }, initial(o.name));
  }

  // ------------------------------------------------------------------ loading
  async function loadOrgs({ follow } = {}) {
    const before = S.snap ? S.orgId : null;
    S.orgs = await get('/api/orgs');
    if (!S.orgId || !S.orgs.some((o) => o.id === S.orgId)) S.orgId = S.orgs[0] ? S.orgs[0].id : null;
    renderSide();
    // follow: the list changed elsewhere. When the open organization is no longer the one shown (the first one was
    // founded in Claude Code or Codex, or the open one went away), open it fully: snapshot, chat and composer.
    if (follow && S.orgId && S.orgId !== before) await openOrg(S.orgId);
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
    const reveal = id !== S.orgId || S.reveal === id;  // opened from elsewhere: shown, with the organizations above it
    S.reveal = null;
    S.orgId = id; save('relic.org', id);
    S.seen = load('relic.seen.' + id, {});
    S.live = {}; S.chat = null; S.convo = null; S.snap = null; S.thread = null; S.quote = null;
    if (reveal) unfoldTo(id);
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
      if (decisions > lastAlert.decisions) new Notification('Relic · ' + S.snap.org.name, { body: t('notify.decisions', { n: decisions }), icon: '/static/icon-192.png' });
      else if (unread > lastAlert.unread) new Notification('Relic · ' + S.snap.org.name, { body: t('notify.new_messages'), icon: '/static/icon-192.png' });
    }
    lastAlert = now;
  }

  // ------------------------------------------------------------------ events
  function liveSlot(name) { return S.live[name] || (S.live[name] = { items: new Map(), status: null }); }
  function connect() {
    const es = new EventSource('/api/events');
    es.onmessage = (e) => {
      let ev; try { ev = JSON.parse(e.data); } catch (x) { return; }
      if (['orgs', 'org', 'decision'].includes(ev.type)) reloadChart();
      if (['orgs', 'org', 'cc'].includes(ev.type)) scheduleCc();
      if (ev.type === 'orgs') { loadOrgs({ follow: true }).catch(() => {}); return; }
      if (ev.type === 'prefs') { loadPrefs().then(renderAll); return; }
      if (ev.type === 'install') { onInstall(ev); return; }
      if (ev.org !== S.orgId) return;
      if (ev.type === 'org' || ev.type === 'decision') scheduleRefresh();
      if (ev.type === 'plain') {
        gotPlain(ev.items || {}, (ev.ids || []).map(Number));
        if (ev.error) toast(t('plain.failed', { error: ev.error }), 6000);
      }
      if (ev.type === 'digest') {
        S.digestPending = false;
        if (ev.error) toast(t('digest.failed', { error: ev.error }), 6000); else S.digest = ev.digest;
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
        scheduleCc();
      }
      opened = true;
    };
  }

  // ------------------------------------------------------------------ sidebar
  function lastLine(head) {
    if (!head || !head.last) return '';
    const l = head.last;
    const args = { name: dname(l.from), text: clip(l.body.replace(/^\[Relic auto-receipt\]\s*/, '').replace(/^>.*\n+/gm, ''), 70) };
    return l.type === 'receipt' ? t('side.last_receipt', args) : t('side.last_line', args);
  }
  function chatRow({ key, avatarNode, name, tags, sub, at, unread, on, onclick, title }) {
    return h('button', { class: 'chat-row' + (on ? ' on' : ''), type: 'button', onclick, 'data-key': key, title },
      avatarNode,
      h('div', { class: 'main' }, h('div', { class: 'name' }, h('span', { class: 'ellipsis' }, name), tags), sub ? h('div', { class: 'sub ellipsis' }, sub) : null),
      h('div', { class: 'side-info' }, at ? h('span', { class: 'time' }, shortWhen(at)) : null, unread ? h('span', { class: 'badge' }, unread > 99 ? '99+' : unread) : null));
  }
  // the organizations as a tree: each one right under the organization above it, the most recent first on each level
  function orgTree() {
    const ids = new Set(S.orgs.map((o) => o.id));
    const out = [], seen = new Set();
    const walk = (id, depth) => {
      for (const o of S.orgs) {
        if ((o.parent && ids.has(o.parent) ? o.parent : null) !== id || seen.has(o.id)) continue;
        seen.add(o.id);
        out.push([o, depth]);
        walk(o.id, depth + 1);
      }
    };
    walk(null, 0);
    return out;
  }
  // folding in the sidebar: a folded organization hides what is under it, its own chats and members and every
  // organization below it. Which ones are folded is kept in this browser.
  function setFolded(id, on) {
    if (on) S.folded.add(id); else S.folded.delete(id);
    save('relic.folded', [...S.folded]);
  }
  function unfoldTo(id) {  // the organization being opened is shown: it and the organizations above it unfold
    const byId = new Map(S.orgs.map((o) => [o.id, o]));
    let changed = S.folded.delete(id);
    for (let o = byId.get(id), n = 0; o && o.parent && n < 64; o = byId.get(o.parent), n++) changed = S.folded.delete(o.parent) || changed;
    if (changed) save('relic.folded', [...S.folded]);
  }
  function renderSide() {
    const tree = $('#tree'); tree.textContent = '';
    const q = S.search.trim().toLowerCase();
    tree.append(h('div', { class: 'sec-label' }, h('span', null, t('page.tree')), h('span', null, S.orgs.length || '')));
    const ids = new Set(S.orgs.map((o) => o.id));
    const hasKids = new Set(S.orgs.filter((o) => o.parent && ids.has(o.parent)).map((o) => o.parent));
    let hideDeeper = Infinity;  // below a folded organization: the depth under which rows are hidden
    for (const [o, depth] of orgTree()) {
      if (depth > hideDeeper) continue;
      hideDeeper = Infinity;
      const active = o.id === S.orgId;
      const orgHit = !q || o.name.toLowerCase().includes(q) || (o.purpose || '').toLowerCase().includes(q);
      const memberHits = active && S.snap ? S.snap.members.filter((m) => !q || (m.display || '').toLowerCase().includes(q) || m.name.toLowerCase().includes(q) || (m.role || '').toLowerCase().includes(q)) : [];
      if (q && !orgHit && !memberHits.length) continue;
      const folded = !q && S.folded.has(o.id);  // a search shows every match
      if (folded) hideDeeper = depth;
      const foldable = active || hasKids.has(o.id);
      const open = active && !folded;
      const row = h('button', { class: 'org-row' + (active ? ' on' : '') + (foldable && !folded ? ' open' : '') + (o.status && o.status !== 'active' ? ' ended' : ''), type: 'button', title: o.name + (o.purpose ? '\n' + o.purpose : ''),
        style: depth ? 'padding-left:' + (8 + depth * 16) + 'px' : null, 'aria-expanded': foldable ? String(!folded) : null,
        // the arrow folds and unfolds; the name opens an organization, or folds the open one
        onclick: (e) => {
          const onArrow = !!(e.target.closest && e.target.closest('.chev'));
          if (foldable && (active || onArrow)) { setFolded(o.id, !S.folded.has(o.id)); renderSide(); } else openOrg(o.id);
        } },
        h('span', { class: 'chev' }, icon('chev', 14)),
        orgBadge(o),
        h('span', { class: 'org-name' }, o.name),
        h('span', { class: 'meta' }, active ? '' : shortWhen(o.last_at)));
      row.addEventListener('contextmenu', (e) => openContextMenu(e, [
        menuItem(t('appmenu.org_chart'), { icon: 'chart', run: () => openChart(o.id) })]));
      tree.append(row);
      if (!open || !S.snap) continue;
      const kids = h('div', { class: 'kids' });
      const heads = S.snap.chats || {};
      const view = S.view;
      if (!q || t('common.group_chat').toLowerCase().includes(q) || orgHit) {
        kids.append(chatRow({ key: 'group', avatarNode: groupAvatar('sm'), name: t('common.group_chat'), sub: lastLine(heads.group) || t('side.group_sub'),
          at: heads.group && heads.group.last.at, unread: view.kind === 'group' ? 0 : unreadOf('group'), on: view.kind === 'group',
          onclick: () => go({ kind: 'group' }) }));
      }
      const sec = secretaryName();
      const secM = sec && member(sec);
      if (!q || t('common.secretary').toLowerCase().includes(q) || (secM && memberHits.includes(secM))) {
        kids.append(chatRow({ key: 'secretary', avatarNode: secAvatar('sm'), name: sec ? t('common.secretary') : t('side.set_secretary'),
          tags: secM ? [h('span', { class: 'tag sec' }, roleName(sec, t('common.secretary')))] : null,
          sub: sec ? (lastLine(heads['member:' + sec]) || (secM.doing || secM.detail || '')) : t('side.secretary_hint'),
          at: sec && heads['member:' + sec] && heads['member:' + sec].last.at, unread: view.kind === 'secretary' ? 0 : (sec ? unreadOf('member:' + sec) : 0),
          on: view.kind === 'secretary', onclick: () => sec ? go({ kind: 'secretary', member: sec }) : openSecretarySetup() }));
      }
      for (const m of memberHits) {
        if (m.secretary) continue;
        const key = 'member:' + m.name;
        const isOn = view.kind === 'member' && view.member === m.name;
        const tags = [];
        if (m.leader) tags.push(h('span', { class: 'tag lead' }, t('common.leader')));
        kids.append(chatRow({ key, avatarNode: avatar(m.name, { size: 'sm', dot: true, click: false }), name: m.display || m.name, tags,
          title: m.name + (m.role ? ' · ' + m.role : ''),
          sub: m.doing ? t('side.doing', { doing: m.doing }) : (lastLine(heads[key]) || m.role || stateLabel(m.state) || ''),
          at: heads[key] ? heads[key].last.at : m.doing_at, unread: isOn ? 0 : unreadOf(key), on: isOn,
          onclick: () => go({ kind: 'member', member: m.name }) }));
      }
      kids.append(h('button', { class: 'add-row', type: 'button', onclick: () => memberDialog() }, icon('plus', 14), t('common.add_member')));
      tree.append(kids);
    }
    if (!S.orgs.length) tree.append(h('div', { class: 'empty', style: 'padding:8px 10px' }, t('side.no_orgs')));
  }
  function renderMe() {
    const me = $('#me'); if (!me) return;
    me.textContent = '';
    append(me, [avatar(HUMAN, { size: 'sm', click: false }), h('div', { class: 'main', style: 'min-width:0;display:grid' },
      h('span', { class: 'who ellipsis' }, myName()), h('span', { class: 'what ellipsis' }, t('side.profile')))]);
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
        h('h2', null, h('span', { class: 'ellipsis' }, t('common.group_chat')), h('span', { class: 'dim', style: 'font-weight:400' }, t('common.members', { n: S.snap.members.length }))),
        h('div', { class: 'meta ellipsis' }, S.snap.org.auto_wake ? t('chat.group_meta_on', { org: S.snap.org.name }) : t('chat.group_meta_off', { org: S.snap.org.name }))),
        h('div', { class: 'actions' },
          h('button', { class: 'chip-btn' + (on ? ' on' : ''), type: 'button', title: t('chat.plain_title'), onclick: togglePlain }, icon('lang', 15), on ? t('chat.plain_on') : t('common.plain_words')),
          h('button', { class: 'chip-btn' + (S.digestOpen ? ' on' : ''), type: 'button', title: t('chat.digest_title'), onclick: toggleDigest }, icon('sparkle', 15), t('chat.digest')),
          h('button', { class: 'icon-btn', title: t('common.tasks'), 'aria-label': t('common.tasks'), onclick: () => openDetails('tasks') }, icon('check')))]);
      return;
    }
    const m = member(S.view.member);
    const sec = S.view.kind === 'secretary';
    const name = m ? m.display || m.name : S.view.member;
    const titleKids = [h('span', { class: 'ellipsis' }, sec ? t('chat.secretary_title', { name: roleName(S.view.member, t('common.secretary')) }) : name)];
    if (m && m.display && m.display !== m.name) titleKids.push(h('span', { class: 'dim mono', style: 'font-weight:400' }, m.name));
    if (m && m.leader) titleKids.push(h('span', { class: 'tag lead' }, t('common.leader')));
    const meta = m ? [S.snap.org.name, m.harness_label, m.surface_label, m.model, stateLabel(m.state)].filter(Boolean).join(' · ') : S.snap.org.name;
    append(head, [sec ? secAvatar('sm') : avatar(S.view.member, { size: 'sm', dot: true }),
      h('div', { class: 'title' }, h('h2', null, titleKids), h('div', { class: 'meta ellipsis' }, meta)),
      h('div', { class: 'actions' },
        m && m.embedded && ['running', 'waiting'].includes(m.state) ? h('button', { class: 'icon-btn', title: t('chat.stop_turn'), 'aria-label': t('chat.stop_turn'),
          onclick: () => post(orgPath('/cancel'), { member: S.view.member }).catch((e) => toast(e.message)) }, icon('stop')) : null,
        h('button', { class: 'icon-btn', title: t('chat.card'), 'aria-label': t('chat.card'), onclick: (e) => openCard(S.view.member, e.currentTarget) }, icon('card')),
        h('button', { class: 'icon-btn', title: t('common.context_trace'), 'aria-label': t('common.context_trace'), onclick: () => openDetails('trace', { member: S.view.member }) }, icon('trace')),
        m && m.surface !== 'chat' ? h('button', { class: 'icon-btn', title: t('chat.workspace'), 'aria-label': t('chat.workspace'), onclick: () => { S.workMember = S.view.member; setPane('work'); } }, icon('work')) : null)]);
  }
  function renderBanner() {
    const box = $('#banner'); box.textContent = '';
    if (!S.snap) return;
    if (S.view.kind === 'group') { if (S.digestOpen) box.append(digestCard()); return; }
    const m = member(S.view.member);
    if (!m) return;
    let text = null, cls = 'banner';
    if (m.embedded) text = t('banner.embedded', { harness: m.harness_label });
    else if (m.surface === 'subagent') { text = m.parent ? t('banner.subagent_in', { parent: dname(m.parent) }) : t('banner.subagent'); cls += ' amber'; }
    else if (m.state === 'vacant') { text = t('banner.vacant'); cls += ' amber'; }
    else if (m.has_transcript) text = t('banner.transcript');
    else text = t('banner.inbox');
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
    if (!S.chat) { inner.append(h('div', { class: 'notice' }, h('span', null, t('common.loading')))); return; }
    if (S.chat.error) { inner.append(h('div', { class: 'notice' }, h('span', null, t('common.load_failed', { error: S.chat.error })))); return; }
    const items = S.view.kind === 'group' ? S.chat.items : memberItems();
    if (!items.length && !liveItems().length) {
      inner.append(h('div', { class: 'notice', style: 'margin-top:40px' }, h('span', null, S.view.kind === 'group' ? t('chat.empty_group') : t('chat.empty_private'))));
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
  // ------------------------------------------------------------------ plain words: what the agents say, rewritten for the person
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
    if (S.plainPending.has(id)) return h('span', { class: 'plain-wait' }, h('i', { class: 'spin' }), t('plain.pending'));
    if (S.plainFailed.has(id)) return h('button', { class: 'plain-wait retry', type: 'button', onclick: () => requestPlain([id]) }, t('plain.retry'));
    return h('span', { class: 'plain-wait' }, t('plain.waiting'));
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
      toast(t('plain.failed', { error: e.message }));
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
    if (on) toast(t('plain.on_hint'), 5000);
  }
  function togglePlainOne(id) {
    if (S.plainOne.has(id)) { S.plainOne.delete(id); updatePlain([id]); return; }
    S.plainOne.add(id);
    if (id in S.plain) updatePlain([id]); else requestPlain([id]);
  }
  // the digest: a few sentences on what the group has been doing, at the top of the group chat
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
      if (refresh && !r.pending) toast(t('digest.up_to_date'));
    } catch (e) { S.digestPending = false; toast(t('digest.failed', { error: e.message })); }
    if (S.view.kind === 'group') renderBanner();
  }
  function digestCard() {
    const d = S.digest;
    const newer = d && S.chat && S.chat.items ? S.chat.items.filter((x) => typeof x.id === 'number' && x.id > (d.last_id || 0)).length : 0;
    const read = d && { n: d.count || 0, when: ago(new Date(d.at * 1000).toISOString()), newer };
    return h('div', { class: 'digest' },
      h('div', { class: 'digest-h' }, icon('sparkle', 15), h('b', null, t('digest.title')),
        d ? h('span', { class: 'dim' }, newer ? t('digest.read_newer', read) : t('digest.read', read)) : null,
        h('div', { style: 'flex:1' }),
        S.digestPending ? h('span', { class: 'plain-wait' }, h('i', { class: 'spin' }), t('digest.pending')) : h('button', { class: 'btn sm ghost', type: 'button', onclick: () => loadDigest(true) }, d ? t('digest.update') : t('chat.digest')),
        secretaryName() ? h('button', { class: 'btn sm ghost', type: 'button', title: t('digest.ask_title'), onclick: askSecretary }, t('digest.ask')) : null,
        h('button', { class: 'icon-btn', style: 'width:24px;height:24px', type: 'button', title: t('common.collapse'), 'aria-label': t('common.collapse'), onclick: toggleDigest }, icon('x', 14))),
      d ? h('div', { class: 'md' }, rich(d.text)) : h('div', { class: 'dim', style: 'font-size:12.5px' }, S.digestPending ? t('digest.reading') : t('digest.none')));
  }
  async function askSecretary() {
    const sec = secretaryName();
    if (!sec) return;
    try {
      await post(orgPath('/send'), { to: [sec], channel: 'private',
        body: t('digest.ask_message') });
      go({ kind: 'secretary', member: sec });
    } catch (e) { toast(e.message); }
  }

  function placeholder() {
    return h('div', { class: 'placeholder', style: 'height:70vh' }, h('div', null, h('h2', null, t('chat.no_orgs')),
      h('p', null, t('chat.no_orgs_hint'))));
  }
  function renderItem(it, prev, where) {
    if (it.type === 'notice') return h('div', { class: 'notice' }, h('span', null, it.text));
    if (it.type === 'acts') return actsBlock(it);
    if (it.type === 'receipt') {
      const text = it.body.replace(/^\[Relic auto-receipt\]\s*/, '');
      return h('div', { class: 'msg' }, avatar(it.from), h('div', { class: 'body' },
        h('div', { class: 'who' }, h('b', null, dname(it.from)), h('span', null, t('msg.auto_receipt_to', { names: it.to.map(dname) })), h('span', null, clock(it.at))),
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
        who.append(h('span', null, t('msg.to', { names: toAll ? t('msg.everyone') : it.to.map(dname) })));
      }
      who.append(h('span', null, clock(it.at)));
    }
    const bubble = h('div', { class: 'bubble', 'data-from': it.from }, rich(it.body));
    const kids = [cont ? null : who];
    const explainable = !mine && typeof it.id === 'number';
    const groupPlain = S.plainMode && S.view.kind === 'group' && where !== 'thread';
    const wantPlain = explainable && (groupPlain || S.plainOne.has(it.id));
    if (wantPlain && S.plain[it.id]) {
      kids.push(h('div', { class: 'bubble plain', 'data-from': it.from }, h('div', { class: 'plain-h' }, icon('lang', 13), t('msg.plain')), rich(S.plain[it.id])),
        h('details', { class: 'orig' }, h('summary', null, t('msg.original')), bubble));
    } else {
      kids.push(bubble);
      if (wantPlain) kids.push(plainState(it.id));
    }
    if (mine && it.read_by && it.to) {
      const others = it.to.filter((n) => n !== HUMAN);
      const read = it.read_by.filter((n) => others.includes(n));
      kids.push(h('div', { class: 'read' }, others.length === 1 ? (read.length ? t('msg.read') : t('msg.unread')) : t('msg.read_count', { read: read.length, total: others.length })));
    }
    if (it.thread && where !== 'thread') {
      kids.push(h('button', { class: 'thread-link', type: 'button', onclick: () => openThread(it.id) },
        h('span', { class: 'faces' }, it.thread.people.slice(0, 3).map((p) => avatar(p, { size: 'xs', click: false }))),
        t('thread.replies', { n: it.thread.count }), h('span', { class: 'dim' }, t('thread.last_reply', { when: shortWhen(it.thread.last_at) }))));
    }
    const acts = h('div', { class: 'hover-acts' },
      explainable && !groupPlain ? h('button', { type: 'button', title: S.plainOne.has(it.id) ? t('msg.hide_plain') : t('common.plain_words'), onclick: () => togglePlainOne(it.id) }, icon('lang', 14), S.plainOne.has(it.id) ? t('msg.original') : t('msg.plain')) : null,
      h('button', { type: 'button', title: t('common.quote'), onclick: () => setQuote(it.fromLabel || dname(it.from), stripQuote(it.body)) }, icon('quote', 14), t('common.quote')),
      it.id && typeof it.id === 'number' && where !== 'thread' ? h('button', { type: 'button', title: t('msg.reply_in_thread'), onclick: () => openThread(it.id) }, icon('thread', 14), t('common.reply')) : null,
      h('button', { type: 'button', title: t('common.copy'), onclick: () => copyText(it.body) }, icon('copy', 14)));
    const avatarNode = mine ? avatar(HUMAN) : (it.fromParent ? avatar(it.fromParent) : avatar(it.from));
    const node = h('div', { class: 'msg' + (mine ? ' mine' : '') + (cont ? ' cont' : '') + (it.from === secretaryName() && S.view.kind === 'group' ? ' sec' : ''), 'data-id': it.id || '' },
      avatarNode, h('div', { class: 'body' }, kids), acts);
    RENDERED.set(node, { it, prev, where });
    if (wantPlain && groupPlain && !(it.id in S.plain) && !S.plainPending.has(it.id) && !S.plainFailed.has(it.id)) watchPlain(node);
    return node;
  }
  const RENDERED = new WeakMap();  // message node -> what it shows, to redraw one message in place
  function stripQuote(body) { return String(body || '').replace(/^(>.*\n?)+\n*/, '').trim(); }
  function copyText(text) { navigator.clipboard.writeText(text).then(() => toast(t('msg.copied')), () => toast(t('msg.copy_failed'))); }

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
        else if (text.startsWith('[Relic auto-wake]')) out.push({ type: 'notice', text: t('msg.auto_woken'), at: s.at });
        else if (text.startsWith('You now hold the seat')) out.push({ type: 'notice', text: t('msg.seat_briefing'), at: s.at });
        else if (m && m.agent) out.push({ type: 'message', from: m.parent || S.view.member, fromParent: m.parent, fromLabel: t('msg.task_from', { name: m.parent ? dname(m.parent) : t('msg.parent_session') }), to: [S.view.member], body: text, at: s.at });
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
  function toolName(name) { return String(name || 'tool').replace(/^mcp__plugin_relic_org__|^mcp__relic_org__/, 'Relic ').replace(/^mcp__/, ''); }
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
      h('b', null, t('step.actions', { n: rows.length })), h('span', { class: 'ellipsis' }, summary), failed ? h('span', { class: 'chip bad' }, t('step.failed', { n: failed })) : null,
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
      h('span', { class: 'tool' }, call ? toolName(call.tool) : t('common.result')), h('span', { class: 'arg ellipsis' }, call ? stepArg(call) : clip(result.text, 120)),
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
            h('span', { class: 'state' }, { pending: t('live.pending'), in_progress: t('task.working'), completed: t('task.done'), failed: t('common.failed') }[it.status] || it.status || '')),
          it.text ? h('div', { class: 'io' }, h('pre', null, it.text)) : null));
      } else if (it.type === 'permission') {
        steps.append(permissionCard(it));
      } else if (it.type === 'error') {
        steps.append(h('div', { class: 'notice' }, h('span', { style: 'color:var(--red)' }, it.text)));
      }
    }
    const running = slot && slot.status && slot.status.state === 'running';
    box.append(h('div', { class: 'msg' }, avatar(who), h('div', { class: 'body' },
      h('div', { class: 'who' }, h('b', null, dname(who)), h('span', null, running ? t('live.replying') : (slot && slot.status ? stateLabel(slot.status.state) || '' : ''))),
      steps.childNodes.length ? h('details', { class: 'acts', open: true }, h('summary', null, h('span', { class: 'chev' }, icon('chev', 13)), h('b', null, t('live.turn_actions'))), steps) : null,
      text ? h('div', { class: 'bubble' }, rich(text)) : (running ? h('div', { class: 'typing' }, h('i'), h('i'), h('i')) : null))));
    if (keepScroll && atEnd) { const s = $('#stream'); s.scrollTop = s.scrollHeight; }
  }
  function permissionCard(it) {
    return h('div', { class: 'decision-card' }, h('div', { class: 'k' }, icon('bell', 14), t('perm.ask')),
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
    lines[0] = t('sel.quote_line', { who: S.quote.who, text: lines[0] });
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
        h('button', { type: 'button', onmousedown: (ev) => { ev.preventDefault(); setQuote(from ? dname(from) : t('common.quote'), text); closeSelBar(); sel.removeAllRanges(); } }, icon('quote', 14), t('common.quote')),
        h('button', { type: 'button', onmousedown: (ev) => { ev.preventDefault(); copyText(text); closeSelBar(); } }, icon('copy', 14), t('common.copy')));
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
      if (PREFS.voice === 'off') { toast(t('composer.voice_off')); return; }
      if (!this.supported()) { toast(t('composer.voice_unsupported'), 6000); return; }
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
        const why = { 'not-allowed': t('composer.voice_denied'), network: t('composer.voice_network'), 'no-speech': t('composer.voice_no_speech'), 'audio-capture': t('composer.voice_no_mic') }[e.error];
        if (why) toast(why);
      };
      rec.onend = () => { btn.classList.remove('on'); if (this.rec === rec) { this.rec = null; this.btn = null; } target.focus(); };
      this.rec = rec; this.btn = btn;
      btn.classList.add('on');
      try { rec.start(); } catch (e) { btn.classList.remove('on'); this.rec = null; toast(t('composer.voice_start_failed', { error: e.message })); }
    },
  };
  function micButton(target, cls) {
    const b = h('button', { class: cls || 'mic', type: 'button', title: t('composer.voice_title'), 'aria-label': t('common.voice_input') }, icon('mic', 17));
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
    const sendBtn = h('button', { class: 'send', type: 'button', title: t('composer.send_title'), 'aria-label': t('common.send') }, icon('up', 17));
    const box = h('div', { class: 'composer-box' });
    if (quote && S.quote) {
      box.append(h('div', { class: 'quote-chip' }, h('div', { class: 'txt' }, h('b', null, t('composer.quoting', { who: S.quote.who })), S.quote.text),
        h('button', { class: 'icon-btn', style: 'width:22px;height:22px', type: 'button', title: t('composer.cancel_quote'), onclick: () => { S.quote = null; renderComposer(); if (S.thread && S.pane === 'thread') renderPanel(); } }, icon('x', 14))));
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
      const typed = ta.value;
      // the draft goes first: sending redraws the composer (the new message arrives meanwhile), and a redraw takes
      // its text from the draft
      if (draftKey) save(draftKey, '');
      try {
        await onSend(quote ? quotedBody(text) : text);
        ta.value = '';
        if (quote) S.quote = null;
      } catch (e) {
        if (draftKey) save(draftKey, typed);
        if (!ta.isConnected) { renderComposer(); if (S.thread && S.pane === 'thread') renderPanel(); }  // redrawn meanwhile: bring the unsent text back
        toast(t('composer.send_failed', { error: e.message }));
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
      placeholder: group ? t('composer.group_placeholder') : t('composer.dm_placeholder', { name: dname(S.view.member) }),
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
    const label = S.to.includes('all') ? t('msg.everyone') : targ(S.to.map(dname));
    const btn = h('button', { class: 'chip-btn', type: 'button' }, t('composer.send_to', { to: clip(label, 24) }), icon('down', 14));
    btn.addEventListener('click', () => {
      const items = [{ key: 'all', label: t('composer.all_members') }].concat(S.snap.members.map((m) => ({ key: m.name, label: m.display || m.name, sub: m.name })));
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
    if (btn) btn.firstChild.textContent = t('composer.send_to', { to: clip(targ(S.to.map(dname)), 24) });
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
  // a right-click menu at the pointer; opened from the keyboard (no pointer position), under the element
  function openContextMenu(e, items) {
    e.preventDefault();
    closeMenu();
    let x = e.clientX, y = e.clientY;
    if (!x && !y && e.currentTarget && e.currentTarget.getBoundingClientRect) { const r = e.currentTarget.getBoundingClientRect(); x = r.left + 24; y = r.bottom; }
    menuEl = h('div', { class: 'menu ctx', role: 'menu' }, items);
    document.body.append(menuEl);
    menuEl.style.left = Math.max(4, Math.min(x, window.innerWidth - menuEl.offsetWidth - 4)) + 'px';
    menuEl.style.top = Math.max(4, Math.min(y, window.innerHeight - menuEl.offsetHeight - 4)) + 'px';
    const first = menuEl.querySelector('.item:not([disabled])');
    if (first) first.focus({ preventScroll: true });
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
    if (data.error || !data.root) { body.append(h('div', { class: 'block empty' }, data.error ? t('common.load_failed', { error: data.error }) : t('common.loading'))); return; }
    body.classList.add('thread-pane');
    body.append(h('div', { class: 'root' }, renderItem(data.root, null, 'thread')));
    body.append(h('div', { class: 'count' }, data.replies.length ? t('thread.replies', { n: data.replies.length }) : t('thread.no_replies')));
    const list = h('div', { class: 'replies' });
    let prev = null;
    for (const r of data.replies) { list.append(renderItem(r, prev, 'thread')); prev = r; }
    body.append(list);
    const { box } = composerBox({ placeholder: t('thread.reply_placeholder'), quote: true, draftKey: 'relic.draft.' + S.orgId + '.thread.' + S.thread,
      onSend: async (text) => {
        await post(orgPath('/send'), { body: text, reply_to: S.thread, channel: S.view.kind === 'group' ? 'group' : 'private' });
        await loadThread(true); scheduleRefresh();
      } });
    body.append(h('div', { class: 'composer', style: 'padding:10px 0 14px' }, box));
  }

  // ------------------------------------------------------------------ right side: organization, workspace, file, thread
  function panes() { return [['org', t('panel.overview'), 'org'], ['work', t('panel.workspace'), 'work'], ['file', t('common.file'), 'file']]; }
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
    const keep = old && box.dataset.pane === S.pane && box.dataset.org === (S.orgId || '') ? old.scrollTop : 0;  // another organization starts at the top
    box.textContent = '';
    box.dataset.pane = S.pane;
    box.dataset.org = S.orgId || '';
    const tabs = panes().concat(S.thread ? [['thread', t('panel.thread'), 'thread']] : []);
    box.append(h('div', { class: 'pane-head' },
      h('div', { class: 'pane-tabs', role: 'tablist' }, tabs.map(([k, label, ic]) => h('button', { class: S.pane === k ? 'on' : '', type: 'button', role: 'tab',
        'aria-selected': S.pane === k ? 'true' : 'false', onclick: () => setPane(k) }, icon(ic, 15), label,
        k === 'thread' ? h('span', { class: 'x', title: t('panel.close_thread'), onclick: (e) => { e.stopPropagation(); closeThread(); } }, icon('x', 12)) : null))),
      h('button', { class: 'icon-btn', type: 'button', title: t('panel.hide_title'), 'aria-label': t('panel.hide'), onclick: () => togglePanel(false) }, icon('x', 16))));
    const body = h('div', { class: 'pane-body' });
    box.append(body, h('div', { class: 'pane-resize', title: t('panel.resize'), onpointerdown: startResize }));
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
    body.append(h('div', { class: 'block' }, h('div', { class: 'block-h' }, h('span', null, t('work.whose'))),
      h('div', { class: 'who-pick' }, people.map((m) => h('button', { class: 'who' + (m.name === S.workMember ? ' on' : ''), type: 'button', title: m.name + (m.role ? ' · ' + m.role : ''),
        onclick: () => { S.workMember = m.name; renderPanel(); } }, avatar(m.name, { size: 'xs', click: false }), h('span', { class: 'ellipsis' }, m.display || m.name))))));
    if (!S.workMember) { body.append(h('div', { class: 'block empty' }, t('work.no_members'))); return; }
    const who = S.workMember;
    const slot = h('div', null, h('div', { class: 'block empty' }, t('common.loading')));
    body.append(slot);
    let ws;
    try { ws = await get(orgPath('/workspace?member=' + enc(who))); } catch (e) { slot.textContent = ''; slot.append(h('div', { class: 'block empty' }, t('common.load_failed', { error: e.message }))); return; }
    slot.textContent = '';
    if (!ws.folder) { slot.append(h('div', { class: 'block empty' }, t('work.no_folder', { name: dname(who) }))); return; }
    slot.append(h('div', { class: 'block' }, h('div', { class: 'block-h' }, h('span', null, t('common.work_folder')),
        h('button', { class: 'link', type: 'button', onclick: () => post('/api/fs/open', { path: ws.folder }).catch((e) => toast(e.message)) }, icon('open', 12), t('work.open_in_explorer'))),
      h('div', { class: 'path-line' }, ws.folder), ws.exists ? null : h('div', { class: 'empty' }, t('work.folder_missing'))));
    if (!ws.exists) return;
    const base = ((ws.git && ws.git.root) || ws.folder).replace(/\\/g, '/').replace(/\/$/, '');
    const rel = (p) => { const a = String(p).replace(/\\/g, '/'); return a.toLowerCase().startsWith(base.toLowerCase() + '/') ? a.slice(base.length + 1) : p; };
    if (ws.git) {
      const g = h('div', { class: 'block' }, h('div', { class: 'block-h' }, h('span', null, t('work.git_changes') + (ws.git.branch ? ' · ' + ws.git.branch : '')),
        h('span', null, ws.git.changes.length ? t('work.file_count', { n: ws.git.changes.length }) : '')));
      if (!ws.git.changes.length) g.append(h('div', { class: 'empty' }, t('work.no_changes')));
      for (const c of ws.git.changes.slice(0, 60)) {
        const code = c.status === '??' ? 'new' : c.status[0];
        g.append(h('button', { class: 'frow', type: 'button', title: c.path, disabled: c.status.includes('D') ? true : null, onclick: () => openFile(c.path) },
          h('span', { class: 'st st-' + code, title: c.status }, code === 'new' ? 'U' : code), h('span', { class: 'ellipsis' }, rel(c.path))));
      }
      if (ws.git.changes.length > 60) g.append(h('div', { class: 'empty' }, t('common.more_items', { n: ws.git.changes.length - 60 })));
      slot.append(g);
    }
    if (ws.recent.length) {
      const r = h('div', { class: 'block' }, h('div', { class: 'block-h' }, h('span', null, t('work.recent_files'))));
      for (const f of ws.recent.slice(0, 15)) {
        const shown = String(rel(f.path)).replace(/\\/g, '/');
        const cut = shown.lastIndexOf('/');
        r.append(h('button', { class: 'frow', type: 'button', title: f.path, onclick: () => openFile(f.path) }, icon('file', 14),
          h('span', { class: 'ellipsis' }, h('span', null, shown.slice(cut + 1)), cut > 0 ? h('span', { class: 'dim' }, '  ' + shown.slice(0, cut)) : null),
          h('span', { class: 'when' }, ago(f.at))));
      }
      slot.append(r);
    }
    slot.append(h('div', { class: 'block' }, h('div', { class: 'block-h' }, h('span', null, t('work.files'))), fileTree(ws.folder)));
  }
  function fileTree(root) {
    const box = h('div', { class: 'ftree' });
    const pad = (depth, extra) => 'padding-left:' + (depth * 14 + (extra || 4)) + 'px';
    async function fill(node, path, depth) {
      let r;
      try { r = await get('/api/fs/list?path=' + enc(path)); } catch (e) { node.append(h('div', { class: 'empty', style: pad(depth, 26) }, e.message)); return; }
      const entries = r.entries.filter((x) => !(x.dir && HIDE_DIRS.has(x.name)));
      if (!entries.length) node.append(h('div', { class: 'empty', style: pad(depth, 26) }, t('work.empty_dir')));
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
      if (r.more) node.append(h('div', { class: 'empty', style: pad(depth, 26) }, t('work.list_limit')));
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
    if (!f) { body.append(h('div', { class: 'block empty' }, t('file.empty'))); return; }
    const name = f.path.split(/[\\/]/).pop();
    const d = f.data;
    body.append(h('div', { class: 'file-head' }, icon('file', 16), h('div', { class: 't' }, h('b', { class: 'ellipsis' }, name), h('span', { class: 'ellipsis', title: f.path }, f.path)),
      h('button', { class: 'icon-btn', type: 'button', title: t('file.copy_path'), 'aria-label': t('file.copy_path'), onclick: () => copyText(f.path) }, icon('copy', 15)),
      h('button', { class: 'icon-btn', type: 'button', title: t('file.open_default'), 'aria-label': t('file.open_default'), onclick: () => post('/api/fs/open', { path: f.path }).catch((e) => toast(e.message)) }, icon('open', 15))));
    if (!d) { body.append(h('div', { class: 'block empty' }, t('common.loading'))); return; }
    if (d.error) { body.append(h('div', { class: 'block empty' }, t('file.open_failed', { error: d.error }))); return; }
    const meta = h('div', { class: 'file-meta' }, h('span', null, sizeLabel(d.size)), h('span', null, t('file.modified', { when: ago(new Date(d.mtime * 1000).toISOString()) })), d.truncated ? h('span', null, t('file.truncated')) : null);
    body.append(meta);
    if (d.kind === 'image') { body.append(h('div', { class: 'file-img' }, h('img', { src: d.url, alt: name }))); return; }
    if (d.kind === 'binary') { body.append(h('div', { class: 'block empty' }, t('file.binary'))); return; }
    if (d.kind === 'markdown') {
      const mode = f.mode || 'preview';
      meta.append(h('div', { style: 'flex:1' }), segControl([['preview', t('file.preview')], ['source', t('file.source')]], mode, (k) => { f.mode = k; renderPanel(); }));
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
    return h('div', null, pre, lines.length > max ? h('div', { class: 'file-meta' }, t('file.lines_shown', { max, total: lines.length })) : null);
  }

  // ------------------------------------------------------------------ organization pane
  function renderOrgPane(box) {
    if (!S.snap) return;
    const { org, members, tasks, protocols, episodes, decisions } = S.snap;
    const autoWake = h('input', { type: 'checkbox', class: 'toggle' });
    autoWake.checked = !!org.auto_wake;
    autoWake.addEventListener('change', () => post(orgPath('/auto_wake'), { on: autoWake.checked }).then(scheduleRefresh).catch((e) => toast(e.message)));
    const purpose = h('div', { class: 'purpose', title: t('org.click_expand') }, org.purpose || t('org.no_purpose'));
    purpose.addEventListener('click', () => purpose.classList.toggle('open'));
    const seg = h('div', { class: 'seg', role: 'group', 'aria-label': t('org.view_mode') }, [['direct', t('org.mode_direct')], ['transparent', t('org.mode_transparent')], ['liaison', t('org.mode_liaison')]].map(([k, label]) =>
      h('button', { class: S.mode === k ? 'on' : '', type: 'button', onclick: () => { S.mode = k; save('relic.mode', k); renderPanel(); if (k === 'liaison' && secretaryName()) go({ kind: 'secretary', member: secretaryName() }); } }, label)));
    // what kind of organization this is: formal or a subgroup, the secretariat (its leader is the secretary-general),
    // closed or dissolved (the record stays)
    const ended = !!org.status && org.status !== 'active';
    const leaderName = org.leader ? roleName(org.leader, t('common.leader')) : '';
    box.append(h('div', { class: 'block' },
      h('div', { class: 'block-h' }, h('span', null, t('org.heading')), seg),
      h('h3', { class: 'org-title' }, org.name), purpose,
      h('div', { class: 'chips' }, org.cabinet ? h('span', { class: 'chip cab' }, t('org.cabinet_chip')) : null,
        h('span', { class: 'chip' }, org.kind === 'subgroup' ? t('org.kind_subgroup') : t('org.kind_formal')),
        ended ? h('span', { class: 'chip bad' }, org.status === 'closed' ? t('org.status_closed') : t('org.status_dissolved')) : null,
        h('span', { class: 'chip' }, org.governance === 'peer' ? t('org.gov_peer') : t('org.gov_leader')),
        org.leader ? h('span', { class: 'chip' }, org.cabinet ? t('org.secretary_general_chip', { name: leaderName }) : t('org.leader_chip', { name: leaderName })) : null,
        h('span', { class: 'chip' }, t('common.members', { n: members.length })), org.secretary ? h('span', { class: 'chip sec' }, t('org.secretary_chip', { name: roleName(org.secretary, t('common.secretary')) })) : null),
      ended ? h('div', { class: 'hier-note' }, org.status === 'closed' ? t('org.ended_closed') : t('org.ended_dissolved')) : null,
      h('label', { class: 'switch' }, autoWake, t('org.auto_wake'))));

    box.append(h('div', { class: 'block' }, h('div', { class: 'block-h' }, h('span', null, t('decision.title')), decisions.length ? h('span', { class: 'badge' }, decisions.length) : null),
      decisions.length ? decisions.map(decisionCard) : h('div', { class: 'empty' }, t('decision.none'))));
    box.append(hierarchyBlock(org, members));

    const brief = S.mode === 'liaison';
    const open = tasks.filter((task) => !['done', 'dropped'].includes(task.status));
    const done = tasks.filter((task) => task.status === 'done');
    const work = h('div', { class: 'block' }, h('div', { class: 'block-h' },
      h('button', { class: 'link', type: 'button', onclick: () => openDetails('tasks', { filter: 'open' }) }, t('org.current_work'), icon('chev', 12)),
      h('button', { class: 'link', type: 'button', onclick: () => openDetails('tasks', { filter: 'done' }) }, t('org.done_count', { n: done.length }), icon('chev', 12))));
    if (!tasks.length) work.append(h('div', { class: 'empty' }, t('org.no_tasks')));
    else if (!open.length) work.append(h('div', { class: 'empty' }, t('org.nothing_open', { n: done.length })));
    for (const task of open.slice(0, 8)) {
      work.append(h('button', { class: 'item-row click', type: 'button', onclick: () => openDetails('tasks', { task: task.id }) },
        task.owner ? avatar(task.owner, { size: 'xs', click: false }) : h('span'),
        h('div', { class: 't' }, h('b', { class: 'ellipsis' }, task.title), h('span', { class: 'ellipsis' }, task.id + ' · ' + (task.owner ? dname(task.owner) : t('org.no_owner')))),
        h('span', { class: 'chip ' + ({ blocked: 'bad', working: 'warn' }[task.status] || '') }, taskLabel(task.status) || task.status)));
    }
    if (open.length > 8) work.append(h('button', { class: 'link', style: 'border:0;background:none;color:var(--ink-3);text-align:left;padding:0', type: 'button', onclick: () => openDetails('tasks', { filter: 'open' }) }, t('common.more_items', { n: open.length - 8 })));
    const recentDone = done.filter((task) => task.report).sort((a, b) => String(b.done_at || '').localeCompare(String(a.done_at || ''))).slice(0, 3);
    if (recentDone.length) {
      work.append(h('div', { class: 'block-h', style: 'margin-top:4px' }, h('span', null, t('org.recently_done'))));
      for (const task of recentDone) {
        work.append(h('button', { class: 'item-row click', type: 'button', onclick: () => openDetails('tasks', { task: task.id }) },
          task.owner ? avatar(task.owner, { size: 'xs', click: false }) : h('span'),
          h('div', { class: 't' }, h('b', { class: 'ellipsis' }, task.title), h('span', { class: 'ellipsis' }, clip(task.report.replace(/[#*`>|_-]+/g, ' '), 80))),
          h('span', { class: 'chip ok' }, t('org.report'))));
      }
    }
    box.append(work);

    if (!brief) {
      const people = h('div', { class: 'block' }, h('div', { class: 'block-h' }, h('span', null, t('org.members')),
        h('button', { class: 'link', type: 'button', onclick: () => memberDialog() }, icon('plus', 13), t('org.add'))));
      for (const m of members) {
        people.append(h('button', { class: 'item-row click', type: 'button', onclick: (e) => openCard(m.name, e.currentTarget) }, avatar(m.name, { size: 'sm', dot: true, click: false }),
          h('div', { class: 't' }, h('b', { class: 'ellipsis' }, m.secretary ? t('org.member_secretary', { name: roleName(m.name, t('common.secretary')) }) : (m.display || m.name)),
            h('span', { class: 'ellipsis' }, [m.ex_officio ? t('card.ex_officio', { org: m.ex_officio.org_name }) : '', m.doing || m.detail || stateLabel(m.state)].filter(Boolean).join(' · '))),
          h('span', { class: 'chip' + (['running', 'working'].includes(m.state) ? ' ok' : m.state === 'waiting' ? ' warn' : m.state === 'error' ? ' bad' : '') }, stateLabel(m.state) || m.state)));
      }
      box.append(people);
      const live = protocols.filter((p) => ['active', 'proposed'].includes(p.status));
      const pro = h('div', { class: 'block' }, h('div', { class: 'block-h' },
        h('button', { class: 'link', type: 'button', onclick: () => openDetails('protocols') }, t('org.protocols'), icon('chev', 12)),
        h('span', null, t('org.protocols_active', { n: protocols.filter((p) => p.status === 'active').length }))));
      const inherited = S.snap.inherited_protocols || [];
      const replaced = S.snap.replaced_protocols || [];
      if (!live.length && !inherited.length && !replaced.length) pro.append(h('div', { class: 'empty' }, t('org.no_protocols')));
      const strength = (p, cls) => h('span', { class: 'chip ' + (cls != null ? cls : p.strength === 'strong' ? 'bad' : '') }, p.strength === 'strong' ? t('common.strong') : t('common.weak'));
      const proRow = (p, notes, ended) => h('button', { class: 'item-row click' + (ended ? ' ended' : ''), type: 'button', onclick: () => openDetails('protocols') }, strength(p, ended ? '' : null),
        h('div', { class: 't' }, h('b', { class: 'ellipsis' + (ended ? ' struck' : '') }, p.id + ' ' + p.title), h('span', { class: 'ellipsis' }, notes.filter(Boolean).join(' · '))), h('span'));
      for (const p of live) {
        pro.append(proRow(p, [p.issued_by ? t('org.issued_by', { name: p.issued_by.name }) : p.status === 'proposed' ? t('org.protocol_voting', { n: p.votes }) : t('org.protocol_used', { n: p.uses }),
          p.replaces_above && p.supersedes ? t('org.protocol_overrides', { ref: protoName(p.supersedes) }) : '', p.inherit ? t('org.protocol_inherits') : '', p.check ? t('org.protocol_check') : '']));
      }
      // protocols that bind this organization from the organizations above, and the ones above that this organization
      // or one between overrode or stopped
      for (const p of inherited) {
        pro.append(proRow(p, [t('org.inherited_from', { name: p.from }), p.issued_by && p.issued_by.name ? t('org.issued_by', { name: p.issued_by.name }) : '', p.check ? t('org.protocol_check') : '']));
      }
      for (const r of replaced) {
        pro.append(proRow(r, [r.how === 'retired' ? t('org.protocol_retired', { from: r.from, at: r.at, by: r.by }) : t('org.protocol_overridden', { from: r.from, at: r.at, by: r.by })], true));
      }
      box.append(pro);
      const eps = h('div', { class: 'block' }, h('div', { class: 'block-h' }, h('span', null, 'Episode')));
      const openEps = episodes.filter((e) => e.status === 'open');
      const recent = episodes.filter((e) => e.status === 'closed').slice(-3).reverse();
      if (!episodes.length) eps.append(h('div', { class: 'empty' }, t('org.no_episodes')));
      for (const e of openEps.concat(recent)) {
        eps.append(h('div', { class: 'item-row' }, h('span', { class: 'chip ' + (e.status === 'open' ? 'warn' : e.outcome === 'success' ? 'ok' : '') }, e.status === 'open' ? t('task.working') : ({ success: t('org.episode_success'), failure: t('common.failed'), partial: t('org.episode_partial'), cancelled: t('org.episode_cancelled') }[e.outcome] || e.outcome)),
          h('div', { class: 't' }, h('b', { class: 'ellipsis' }, e.id + ' ' + e.title), h('span', null, t('org.episode_reflections', { reflections: e.reflections, participants: e.participants }))), h('span')));
      }
      box.append(eps);
    }
    box.append(h('div', { class: 'block' }, brief ? h('div', { class: 'empty' }, t('org.liaison_note')) : null,
      h('button', { class: 'btn wrap', type: 'button', onclick: () => openDetails('trace') }, icon('trace', 16), t('org.details'))));
  }
  // the organization above this one, its leader and whether it is the secretariat (the person changes these here, at
  // once), the organizations right below it and its subgroups (closed ones grayed); a subgroup can be closed here
  function hierarchyBlock(org, members) {
    const active = !org.status || org.status === 'active';
    const below = new Set();
    (function walk(id) { for (const o of S.orgs) if (o.parent === id && !below.has(o.id)) { below.add(o.id); walk(o.id); } })(org.id);
    const above = org.parent ? org.parent.id : null;
    const parentSel = h('select', { class: 'input', 'aria-label': t('org.parent_label'), disabled: active ? null : true },
      [h('option', { value: '' }, t('org.parent_none'))].concat(S.orgs.filter((o) => o.id !== org.id && !below.has(o.id) &&
        (o.id === above || (o.status === 'active' && (org.kind === 'subgroup' || o.kind !== 'subgroup')))).map((o) =>
        h('option', { value: o.id, selected: o.id === above ? true : null }, o.name))));
    parentSel.addEventListener('change', () => post(orgPath('/parent'), { parent: parentSel.value || null })
      .then(() => loadOrgs()).then(scheduleRefresh).catch((e) => { toast(t('org.parent_failed', { error: e.message })); renderPanel(); }));
    const block = h('div', { class: 'block' }, h('div', { class: 'block-h' }, h('span', null, t('org.hierarchy')),
      h('button', { class: 'link', type: 'button', onclick: () => openChart(S.orgId) }, t('chart.title'), icon('chev', 12))),
      h('label', { class: 'field-row' }, h('span', null, t('org.parent_label')), parentSel));
    if (org.governance !== 'peer') {
      const leaderSel = h('select', { class: 'input', 'aria-label': t('common.leader'), disabled: active && members.length ? null : true },
        org.leader ? null : h('option', { value: '', selected: true, disabled: true }, t('org.leader_unset')),
        members.map((m) => h('option', { value: m.name, selected: m.name === org.leader ? true : null }, m.display || m.name)));
      leaderSel.addEventListener('change', async () => {
        const name = leaderSel.value, m = member(name), shown = m ? m.display || name : name;
        if (!name || !confirm(t('org.leader_confirm', { name: shown, org: org.name }))) { renderPanel(); return; }
        try { await post(orgPath('/leader'), { member: name }); toast(t('org.leader_changed', { name: shown })); await loadOrgs(); scheduleRefresh(); }
        catch (e) { toast(t('org.leader_failed', { error: e.message }), 6000); renderPanel(); }
      });
      block.append(h('label', { class: 'field-row' }, h('span', null, t('common.leader')), leaderSel));
    }
    if (org.kind === 'subgroup') {
      const home = S.orgs.find((o) => o.id === org.home);
      block.append(h('div', { class: 'hier-note' }, t('org.subgroup_note', { name: home ? home.name : org.parent ? org.parent.name : '-' })));
    } else {
      const other = S.orgs.find((o) => o.cabinet && o.id !== org.id);
      const cab = h('input', { type: 'checkbox', class: 'toggle', disabled: active ? null : true });
      cab.checked = !!org.cabinet;
      cab.addEventListener('change', () => post(orgPath('/cabinet'), { on: cab.checked }).then(() => loadOrgs()).then(scheduleRefresh)
        .catch((e) => { toast(t('org.cabinet_failed', { error: e.message }), 6000); renderPanel(); }));
      block.append(h('label', { class: 'switch' }, cab, t('org.cabinet_toggle')),
        h('div', { class: 'hier-note' }, org.cabinet ? t('org.cabinet_on_hint') : other ? t('org.cabinet_elsewhere', { name: other.name }) : t('org.cabinet_hint')));
    }
    block.append(h('div', { class: 'hier-note' }, t('org.parent_hint')));
    const row = (o, sub, ended) => h('button', { class: 'item-row click' + (ended ? ' ended' : ''), type: 'button', onclick: () => openOrg(o.id) },
      orgBadge(o), h('div', { class: 't' }, h('b', { class: 'ellipsis' }, o.name), h('span', { class: 'ellipsis' }, sub)), h('span'));
    const stats = (c) => t('org.child_stats', { decisions: c.decisions, blocked: c.blocked, working: c.working });
    const formal = (org.children || []).filter((c) => c.kind !== 'subgroup');
    if (formal.length) {
      block.append(h('div', { class: 'hier-sub' }, t('org.children')));
      for (const c of formal) block.append(row(c, stats(c)));
    }
    const groups = org.subgroups || [];
    if (groups.length) {
      block.append(h('div', { class: 'hier-sub' }, t('org.subgroups')));
      for (const g of groups) {
        const c = (org.children || []).find((x) => x.id === g.id);
        const open = g.status === 'active';
        const sub = open ? [g.leader ? t('org.leader_chip', { name: g.leader }) : '', c ? stats(c) : ''].filter(Boolean).join(' · ')
          : (g.status === 'closed' ? t('org.status_closed') : t('org.status_dissolved')) + (g.ended_at ? ' · ' + shortWhen(g.ended_at) : '');
        block.append(row(Object.assign({ kind: 'subgroup' }, g), sub, !open));
      }
    }
    if (org.kind === 'subgroup' && active) {
      block.append(h('div', { class: 'row-acts' }, h('button', { class: 'btn sm danger', type: 'button', onclick: async () => {
        if (!confirm(t('org.close_group_confirm', { name: org.name }))) return;
        try { await post(orgPath('/close'), {}); toast(t('org.group_closed', { name: org.name })); await loadOrgs(); scheduleRefresh(); }
        catch (e) { toast(t('org.close_group_failed', { error: e.message }), 6000); }
      } }, t('org.close_group'))));
    }
    return block;
  }
  function decisionCard(d) {
    if (d.kind === 'permission') {
      return h('div', { class: 'decision' }, h('b', null, t('decision.permission', { name: dname(d.member), what: d.title })), d.detail ? h('div', { class: 'dim ellipsis' }, d.detail) : null,
        h('div', { class: 'row-acts' }, (d.options || []).map((o) => h('button', { class: 'btn sm' + (String(o.kind).startsWith('allow') ? ' primary' : ''), type: 'button', onclick: () => decide(d.id, o.id) }, o.name || o.kind))));
    }
    if (d.kind === 'trajectory') {
      const answer = (decision) => post(orgPath('/trajectory_answer'), { request_id: d.id, decision }).then(scheduleRefresh).catch((e) => toast(e.message));
      const whose = d.requester === d.member ? t('decision.own_seat') : t('decision.member_seat', { name: dname(d.member) });
      const which = d.carrier ? t('decision.earlier_session', { n: d.carrier }) : t('decision.current_session');
      return h('div', { class: 'decision' }, h('b', null, t('decision.trajectory', { requester: dname(d.requester), whose, which })), h('div', null, t('decision.reason', { reason: d.reason || '—' })),
        h('div', { class: 'row-acts' }, h('button', { class: 'btn sm primary', type: 'button', onclick: () => answer('approve') }, t('decision.approve_redacted')), h('button', { class: 'btn sm', type: 'button', onclick: () => answer('deny') }, t('decision.deny'))));
    }
    if (d.kind === 'approval') {
      // a member's change to a formal organization, kept in the secretariat (or, without one, in the member's
      // organization): the person decides it here; the secretary-general can decide it too
      const yes = h('button', { class: 'btn sm primary', type: 'button' }, t('decision.approve'));
      const no = h('button', { class: 'btn sm', type: 'button' }, t('decision.deny'));
      const answer = async (decision) => {
        yes.disabled = no.disabled = true;
        try {
          const r = await post('/api/org/' + enc(d.org) + '/request', { request_id: d.id, decision });
          toast(r.status === 'failed' ? t('decision.approval_failed', { id: d.id, error: r.error || '' }) : r.status === 'denied' ? t('decision.denied', { id: d.id }) : t('decision.approved', { id: d.id }), 6000);
          await loadOrgs(); scheduleRefresh();
        } catch (e) { yes.disabled = no.disabled = false; toast(e.message, 6000); }
      };
      yes.addEventListener('click', () => answer('approve'));
      no.addEventListener('click', () => answer('deny'));
      const who = !d.requester ? '-' : d.requester_org && d.requester_org !== S.orgId ? t('common.member_of_org', { member: d.requester, org: d.requester_org_name || d.requester_org }) : dname(d.requester);
      const cab = S.orgs.find((o) => o.cabinet);
      const sg = cab && cab.leader ? (cab.id === S.orgId ? dname(cab.leader) : cab.leader) : '';
      const note = d.approver === 'secretary-general' ? (sg ? t('decision.approval_sg', { name: sg }) : '') : d.approver === 'human' ? t('decision.approval_human') : '';
      return h('div', { class: 'decision' }, h('b', null, t('decision.approval', { requester: who, what: d.label || d.text || d.request, id: d.id })),
        d.reason ? h('div', null, t('decision.reason', { reason: d.reason })) : null,
        h('div', { class: 'dim', style: 'font-size:12px' }, [shortWhen(d.at), note].filter(Boolean).join(' · ')),
        h('div', { class: 'row-acts' }, yes, no));
    }
    if (d.kind === 'wake') {
      return h('div', { class: 'decision' }, h('b', null, t('decision.wake_failed', { name: dname(d.member) })), h('div', { class: 'dim' }, clip(d.error, 140)),
        h('div', { class: 'row-acts' }, h('button', { class: 'btn sm', type: 'button', onclick: () => go({ kind: 'member', member: d.member }) }, t('decision.open_chat'))));
    }
    if (d.kind === 'task') {
      return h('div', { class: 'decision' }, h('b', null, t('decision.task_blocked', { id: d.id, title: d.title })), h('div', { class: 'dim' }, t('decision.task_owner', { name: d.member ? dname(d.member) : '—' })),
        h('div', { class: 'row-acts' }, h('button', { class: 'btn sm', type: 'button', onclick: () => openDetails('tasks', { task: d.id }) }, t('decision.view_task')),
          d.member ? h('button', { class: 'btn sm', type: 'button', onclick: () => go({ kind: 'member', member: d.member }) }, t('decision.ask', { name: dname(d.member) })) : null));
    }
    return h('div', { class: 'decision' }, JSON.stringify(d));
  }

  // ------------------------------------------------------------------ copies (next to the bell): protocols sent to the person
  // A strong protocol with a check program the members wrote takes effect by their vote alone; the person gets a copy
  // with a note in their language. A card says what the protocol does, who proposed it and when it took effect, how its
  // program has answered so far, and folds away the code and examples the members reviewed. "Got it" marks a copy read;
  // "Retire" stops the protocol at once, in the organizations below that inherit it too. Data: GET /api/cc.
  let ccBox = null, ccTimer = 0, ccAsked = 0;
  function scheduleCc() { clearTimeout(ccTimer); ccTimer = setTimeout(() => loadCc().catch(() => {}), 1200); }
  async function loadCc() {
    const asked = ++ccAsked;
    const r = await get('/api/cc');
    if (asked !== ccAsked) return;  // a later load is on its way; an older answer must not overwrite it
    const was = S.cc.loaded ? S.cc.unread : null;
    S.cc = { items: r.items || [], unread: r.unread || 0, loaded: true };
    const fresh = S.cc.items.find((c) => !c.read);
    if (was !== null && S.cc.unread > was && fresh && PREFS.notify && document.hidden && 'Notification' in window && Notification.permission === 'granted') {
      new Notification('Relic · ' + t('cc.title'), { body: t('cc.notify', { org: fresh.org_name, id: fresh.protocol_id, title: fresh.title }), icon: '/static/icon-192.png' });
    }
    renderAppbar();
    if (ccBox && ccBox.isConnected) drawCopies();
  }
  function openCopies() {
    closeCard(); closeMenu();
    ccBox = h('div', { class: 'dialog cc-panel', role: 'dialog', 'aria-label': t('cc.title') });
    scrim(ccBox);
    drawCopies();
    loadCc().catch((e) => toast(t('common.load_failed', { error: e.message })));
  }
  function drawCopies() {
    const box = ccBox;
    const keep = box.scrollTop;
    const unfolded = new Set([...box.querySelectorAll('.cc-card > details[open]')].map((d) => d.parentNode.dataset.id));
    box.textContent = '';
    box.append(h('div', { class: 'cc-head' }, icon('cc', 18), h('h3', null, t('cc.title')),
      S.cc.unread ? h('span', { class: 'badge' }, S.cc.unread) : null, h('div', { style: 'flex:1' }),
      h('button', { class: 'icon-btn', type: 'button', title: t('common.close'), 'aria-label': t('common.close'), onclick: closeLayer }, icon('x'))),
      h('p', { class: 'lead' }, t('cc.intro')));
    const list = h('div', { class: 'cc-list' });
    if (!S.cc.items.length) list.append(h('div', { class: 'empty' }, S.cc.loaded ? t('cc.empty') : t('common.loading')));
    for (const c of S.cc.items) list.append(copyCard(c, unfolded.has(String(c.id))));
    box.append(list);
    box.scrollTop = keep;
  }
  function copyState(c) {
    if (c.org_status && c.org_status !== 'active') return [t('cc.status_ended'), ''];
    if (c.status === 'active') return [t('cc.status_active'), 'ok'];
    if (c.status === 'retired' && c.retired_by === HUMAN) return [t('cc.status_retired_person'), 'bad'];
    if (c.status === 'superseded') return [t('cc.status_superseded', { id: c.superseded_by || '' }), ''];
    return [t('cc.status_retired'), ''];
  }
  function copyCard(c, unfolded) {
    const live = c.status === 'active' && (!c.org_status || c.org_status === 'active');
    const [state, cls] = copyState(c);
    const o = S.orgs.find((x) => x.id === c.org) || { id: c.org, name: c.org_name };
    const s = c.stats || {};
    const meta = [c.issued_by && c.issued_by.member ? t('cc.issued_by', { name: c.author_display }) : t('cc.proposed_by', { name: c.author_display }),
      (c.approved_display || []).length ? t('cc.approved_by', { names: c.approved_display }) : '',
      c.activated_at ? t('cc.effective', { when: dayLabel(toDate(c.activated_at)) + ' ' + clock(c.activated_at) }) : '',
      c.supersedes ? t('cc.replaces', { id: c.supersedes }) : ''].filter(Boolean).join(' · ');
    const ack = h('button', { class: 'btn sm', type: 'button', onclick: () => ackCopy(c, ack) }, icon('check', 14), t('cc.ack'));
    const retire = h('button', { class: 'btn sm danger', type: 'button', onclick: () => retireCopy(c, retire) }, t('cc.retire'));
    return h('div', { class: 'cc-card' + (c.read ? '' : ' unread') + (live ? '' : ' ended'), 'data-id': c.id },
      h('div', { class: 'cc-top' }, orgBadge(o),
        h('div', { class: 't' }, h('span', { class: 'org ellipsis' }, c.org_name), h('b', null, h('span', { class: 'mono' }, c.protocol_id), ' ', c.title)),
        h('div', { class: 'chips' }, c.read ? null : h('span', { class: 'chip accent' }, t('cc.unread')),
          c.supersedes ? h('span', { class: 'chip' }, t('cc.revision')) : null, h('span', { class: 'chip' + (cls ? ' ' + cls : '') }, state))),
      h('div', { class: 'cc-summary md' }, rich(c.summary)),
      h('div', { class: 'cc-meta' }, meta),
      h('div', { class: 'cc-meta' }, s.total ? t('cc.stats', { n: s.total, allow: s.allow || 0, deny: s.deny || 0, review: s.review || 0, error: s.error || 0 }) : t('cc.stats_none')),
      checkRulesView(c.rules, unfolded),
      c.read && !live ? null : h('div', { class: 'row-acts' }, c.read ? null : ack, live ? retire : null));
  }
  // a protocol's check rules as the members reviewed them, folded: what each runs on, what happens when its program
  // fails, its code and its examples
  function checkRulesView(rules, unfolded) {
    const checks = (rules || []).filter((r) => r.effect === 'check');
    if (!checks.length) return null;
    const decide = { allow: t('cc.decision_allow'), deny: t('cc.decision_deny'), review: t('cc.decision_review') };
    return h('details', { class: 'cc-code', open: unfolded ? true : null }, h('summary', null, icon('chev', 13), t('cc.code')),
      checks.map((r) => h('div', { class: 'cc-rule' },
        h('div', { class: 'cc-meta' }, t('cc.scope', { what: ruleScope(r) })),
        h('div', { class: 'cc-meta' }, r.on_error === 'deny' ? t('cc.on_error_deny') : t('cc.on_error_allow')),
        h('pre', null, r.code || ''),
        r.code_sha256 ? h('div', { class: 'cc-meta mono' }, 'sha256 ' + r.code_sha256.slice(0, 16) + '…') : null,
        (r.examples || []).length ? h('div', { class: 'cc-examples' }, h('div', { class: 'cc-meta' }, t('cc.examples')),
          r.examples.map((ex) => h('div', { class: 'cc-example' },
            h('span', { class: 'chip ' + ({ allow: 'ok', deny: 'bad', review: 'warn' }[ex.expect] || '') }, decide[ex.expect] || ex.expect),
            h('code', { class: 'ellipsis', title: JSON.stringify(ex.call || {}, null, 2) }, exampleText(ex.call || {})),
            ex.note ? h('span', { class: 'note' }, ex.note) : null))) : null)));
  }
  function ruleScope(r) {
    const parts = [(r.tools || []).join(' / ')];
    if (r.path_glob) parts.push(t('cc.scope_path', { glob: r.path_glob }));
    if ((r.input_contains || []).length) parts.push(t('cc.scope_contains', { words: r.input_contains }));
    const who = (r.roles || []).concat(r.members || []), except = (r.except_roles || []).concat(r.except_members || []);
    if (who.length) parts.push(t('cc.scope_who', { names: who }));
    if (except.length) parts.push(t('cc.scope_except', { names: except }));
    return parts.join(' · ');
  }
  function exampleText(call) {
    const input = call.input || {};
    const arg = input.command || input.file_path || input.path || (Object.keys(input).length ? JSON.stringify(input) : '');
    return clip([call.tool, arg].filter(Boolean).join(' '), 160);
  }
  // check rules without their code and examples, for the JSON of a protocol's rules (checkRulesView shows those)
  function plainRules(rules) {
    return (rules || []).map((r) => (r.effect === 'check' ? Object.fromEntries(Object.entries(r).filter(([k]) => !['code', 'examples', 'code_sha256'].includes(k))) : r));
  }
  async function ackCopy(c, btn) {
    btn.disabled = true;
    ccAsked++;  // a load already on its way was asked before this: its answer is older than what the page shows next
    try {
      await post('/api/cc/' + c.id + '/read', {});
      c.read = true; S.cc.unread = Math.max(0, S.cc.unread - 1);
      renderAppbar(); drawCopies();
    } catch (e) { btn.disabled = false; toast(e.message); }
  }
  async function retireCopy(c, btn) {
    if (!confirm(t('cc.retire_confirm', { org: c.org_name, id: c.protocol_id, title: c.title }))) return;
    btn.disabled = true;
    try {
      await post('/api/cc/' + c.id + '/retire', {});
      toast(t('cc.retired', { id: c.protocol_id, title: c.title }), 5000);
      await loadCc();
      scheduleRefresh();
    } catch (e) { btn.disabled = false; toast(t('cc.retire_failed', { error: e.message }), 6000); }
  }

  // ------------------------------------------------------------------ name card: rename, avatar, model
  let cardEl = null;
  function closeCard() { if (cardEl) { cardEl.remove(); cardEl = null; } }
  function identity(c) {
    if (c.state === 'vacant') return c.harness_label ? t('card.identity_vacant_harness', { harness: c.harness_label }) : t('card.identity_vacant');
    if (c.surface === 'subagent') return c.parent ? t('card.identity_subagent_parent', { harness: c.harness_label, parent: dname(c.parent) }) : t('card.identity_subagent', { harness: c.harness_label });
    if (c.surface === 'acp') return t('card.identity_acp', { harness: c.harness_label });
    if (c.surface === 'chat') return t('card.identity_chat', { harness: c.harness_label });
    return t('card.identity_session', { where: [c.harness_label, c.surface_label].filter(Boolean).join(' ') });
  }
  function pickImage() {
    return new Promise((resolve) => {
      const input = h('input', { type: 'file', accept: 'image/png,image/jpeg,image/webp,image/gif' });
      input.addEventListener('change', () => {
        const file = input.files && input.files[0];
        if (!file) return resolve(null);
        if (file.size > 2 * 1024 * 1024) { toast(t('card.image_too_large')); return resolve(null); }
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
    const card = h('div', { class: 'card', role: 'dialog', 'aria-label': t('card.aria', { name: m.display || name }) });
    card.style.left = Math.min(Math.max(12, rect.right + 8), window.innerWidth - 356) + 'px';
    card.style.top = Math.min(Math.max(12, rect.top - 12), window.innerHeight - 520) + 'px';
    let editingName = false, editingModel = false;
    const fill = (c) => {
      card.textContent = '';
      const av = h('div', { class: 'avatar-wrap', title: t('card.change_avatar') }, avatar(name, { size: 'lg', dot: true, click: false }), h('span', { class: 'change' }, t('card.change_avatar')));
      av.addEventListener('click', async () => {
        const data = await pickImage(); if (!data) return;
        try { await post('/api/avatar', { org: S.orgId, member: name, data }); toast(t('card.avatar_changed')); await refreshSnap(); fill(Object.assign(c, member(name))); renderStream(false); } catch (e) { toast(e.message); }
      });
      const tags = [];
      if (c.leader) tags.push(h('span', { class: 'tag lead' }, t('common.leader')));
      if (c.secretary) tags.push(h('span', { class: 'tag sec' }, t('common.secretary')));
      if (c.ex_officio) tags.push(h('span', { class: 'tag' }, t('card.ex_officio_tag')));
      let titleRow;
      if (editingName) {
        const input = h('input', { value: c.display_custom ? c.display : '', placeholder: c.display || t('card.new_name'), maxlength: 40 });
        const saveName = async () => {
          try {
            const r = await post(orgPath('/rename'), { member: name, name: input.value.trim() });
            toast(input.value.trim() ? t('card.renamed') + (r.note ? ' ' + r.note : '') : t('card.name_reset'), 5000);
            editingName = false; await refreshSnap(); fill(Object.assign(c, member(name))); renderStream(false);
          } catch (e) { toast(e.message); }
        };
        input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.isComposing) saveName(); if (e.key === 'Escape') { editingName = false; fill(c); } });
        titleRow = h('div', { class: 'rename' }, field(input), h('button', { class: 'btn sm primary', type: 'button', onclick: saveName }, t('common.save')));
        setTimeout(() => input.focus(), 0);
      } else {
        titleRow = h('h3', null, c.display || name, tags, h('button', { class: 'icon-btn', style: 'width:24px;height:24px', type: 'button', title: t('card.rename_hint'), onclick: () => { editingName = true; fill(c); } }, icon('edit', 14)));
      }
      card.append(h('div', { class: 'top' }, av, h('div', { style: 'min-width:0' }, titleRow, h('div', { class: 'id mono' }, name + (c.display_custom ? '' : ' · ' + t('card.auto_named'))))));
      const kv = h('dl', { class: 'kv' });
      const row = (k, v) => { if (v) append(kv, [h('dt', null, k), h('dd', null, v)]); };
      row(t('common.role'), c.role || t('card.no_role'));
      row(t('card.identity'), identity(c));
      // a seat held because its session leads another organization, and the session's seats in other organizations
      if (c.ex_officio) row(t('card.seat_origin'), h('div', { class: 'also' }, h('button', { type: 'button', onclick: () => { closeCard(); openOrg(c.ex_officio.org); } }, t('card.ex_officio', { org: c.ex_officio.org_name }))));
      if ((c.also_in || []).length) {
        row(t('card.also_in'), h('div', { class: 'also' }, c.also_in.map((x) => h('button', { type: 'button', title: x.role || null,
          onclick: () => { closeCard(); openOrg(x.org, { kind: 'member', member: x.member }); } },
          h('span', { class: 'ellipsis' }, t('card.also_in_item', { org: x.org_name, member: x.member })), x.main ? h('span', { class: 'tag' }, t('card.main_seat')) : null))));
      }
      const modelText = [c.model || t('common.default_model'), c.effort].filter(Boolean).join(' · ');
      const modelCell = h('div', null, h('span', null, modelText), ' ',
        c.model_editable ? h('button', { class: 'btn sm ghost', type: 'button', onclick: () => { editingModel = !editingModel; fill(c); } }, editingModel ? t('common.collapse') : t('common.change')) : null,
        !c.model_editable && c.model_note ? h('div', { class: 'dim', style: 'font-size:11.5px;margin-top:2px' }, c.model_note) : null);
      if (editingModel && c.model_editable) {
        const ms = h('select', null, h('option', { value: '' }, t('common.default_model')), (c.models || []).map((x) => h('option', { value: x, selected: x === c.model ? true : null }, x)));
        const es = h('select', null, h('option', { value: '' }, t('common.default_effort')), (c.efforts || []).map((x) => h('option', { value: x, selected: x === c.effort ? true : null }, x)));
        modelCell.append(h('div', { class: 'model-edit' }, ms, es, h('div', { class: 'dim', style: 'font-size:11.5px' }, c.model_note),
          h('button', { class: 'btn sm primary', type: 'button', onclick: async () => {
            try { const r = await post(orgPath('/model'), { member: name, model: ms.value, effort: es.value }); toast(r.applied === 'now' ? t('card.model_switched') : t('card.model_next_turn')); editingModel = false; await refreshSnap(); fill(Object.assign(c, member(name))); } catch (e) { toast(e.message); }
          } }, t('card.save_model'))));
      }
      row(t('common.model'), modelCell);
      row(t('common.status'), h('span', null, h('span', { class: 'chip' + (['running', 'working'].includes(c.state) ? ' ok' : c.state === 'waiting' ? ' warn' : c.state === 'error' ? ' bad' : '') }, stateLabel(c.state) || c.state),
        c.detail && c.detail !== stateLabel(c.state) ? ' ' + c.detail : ''));
      row(t('card.doing'), c.doing ? (c.doing_at ? t('card.doing_since', { doing: c.doing, ago: ago(c.doing_at) }) : c.doing) : '');
      const tasks = (c.tasks || []).filter((task) => !['done', 'dropped'].includes(task.status));
      row(t('card.owns'), tasks.length ? h('div', null, tasks.map((task) => h('div', { class: 'ellipsis' }, task.id + ' ' + task.title))) : ((c.tasks || []).length ? t('card.tasks_done', { n: c.tasks.length }) : ''));
      row(t('common.session'), c.agent ? h('span', null, 'subagent ', h('span', { class: 'mono', title: c.agent }, c.agent.slice(0, 12)), c.parent ? t('card.in_parent_session', { parent: dname(c.parent) }) : '') :
        c.session ? h('span', { class: 'mono', title: c.session }, c.session.slice(0, 18) + (c.session.length > 18 ? '…' : '')) : '');
      row(t('card.folder'), c.cwd ? h('span', { class: 'mono' }, clip(c.cwd, 64)) : '');
      row(t('card.joined'), c.joined_at ? dayLabel(toDate(c.joined_at)) + ' ' + clock(c.joined_at) + (c.carriers > 1 ? ' · ' + t('card.session_nth', { n: c.carriers }) : '') : '');
      if (c.recent && c.recent.length) row(t('card.recent'), h('div', null, c.recent.slice(0, 4).map((r) => h('div', { class: 'ellipsis dim' }, ago(new Date(r.at * 1000).toISOString()) + ' ' + toolName(r.tool) + ' ' + clip(r.summary, 50)))));
      card.append(kv, h('div', { class: 'acts-row' },
        h('button', { class: 'btn primary', type: 'button', onclick: () => { closeCard(); go({ kind: c.secretary ? 'secretary' : 'member', member: name }); } }, t('card.message')),
        h('button', { class: 'btn', type: 'button', onclick: () => { closeCard(); openDetails('trace', { member: name }); } }, t('common.context_trace'))));
      // the seat itself: where its sessions run and which one holds it
      const own = !['chat', 'subagent'].includes(c.surface);
      const hosted = own && !c.embedded && ((c.config && c.config.harness) || c.surface === 'cli' || c.surface === 'desktop');
      const seatBtn = (label, onclick, title) => h('button', { class: 'btn sm ghost', type: 'button', title, onclick }, label);
      const acts = [
        own && (c.embedded || hosted) ? seatBtn(t('card.new_session'), () => seatAction('fresh', name, c.session ? t('card.new_session_confirm', { name: c.display || name }) : ''), t('card.new_session_hint')) : null,
        hosted && c.session ? seatBtn(t('card.open_session'), () => seatAction('open_session', name), t('card.open_session_hint')) : null,
        hosted ? seatBtn(t('card.edit_setup'), () => { closeCard(); memberDialog({ edit: name }); }, t('card.edit_setup_hint')) : null,
        c.harness === 'chatgpt' ? seatBtn(c.waiting_replies ? t('card.forward_reply_waiting', { n: c.waiting_replies }) : t('card.forward_reply'), () => { closeCard(); forwardDialog(name); }, t('card.forward_reply_hint')) : null,
        c.session ? seatBtn(t('card.leave_seat'), () => seatAction('unbind', name, t('card.leave_seat_confirm', { name: c.display || name })), t('card.leave_seat_hint')) : null,
      ].filter(Boolean);
      if (acts.length) card.append(h('div', { class: 'seat-acts' }, acts));
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
  // A member runs one of three ways, all from here: in the App (an ACP session the App hosts), in Claude Code or Codex
  // itself (command line or desktop app, started and woken by Relic), or as a session that already exists on this computer.
  function runModes() { return [['app', t('member.run_app')], ['host', t('member.run_host')], ['existing', t('member.run_existing')]]; }
  function runNotes() {
    return {
      app: t('member.note_app'),
      host: t('member.note_host'),
      existing: t('member.note_existing'),
    };
  }
  function hostKinds() { return [['claude-code', 'cli', t('member.harness_cli', { harness: 'Claude Code' })], ['claude-code', 'gui', t('member.harness_gui', { harness: 'Claude Code' })], ['codex', 'cli', t('member.harness_cli', { harness: 'Codex' })], ['codex', 'gui', t('member.harness_gui', { harness: 'Codex' })]]; }
  const HARNESS_TITLE = { 'claude-code': 'Claude Code', codex: 'Codex', chatgpt: 'ChatGPT', 'claude-chat': 'Claude' };
  async function seatOptions() {
    if (!S.seatOptions) S.seatOptions = await get('/api/seat-options');
    return S.seatOptions;
  }
  async function memberDialog({ secretary, edit, mode } = {}) {
    if (!S.snap) return;
    const list = await harnessList();
    const opts = await seatOptions().catch(() => ({ efforts: [''], claude_modes: ['auto'], codex_sandboxes: ['workspace-write'], claude_models: [''] }));
    const card = edit ? await get(orgPath('/member/' + enc(edit))).catch(() => member(edit)) : null;
    const conf = (card && card.config) || {};
    let run = edit ? 'host' : (secretary ? 'app' : (mode || 'app'));
    const err = h('div', { class: 'err' });
    const name = h('input', { value: edit || (secretary ? 'secretary' : ''), placeholder: t('member.name_placeholder'), disabled: edit ? true : null });
    const role = h('input', { value: card ? card.role || '' : '', placeholder: secretary ? t('member.role_placeholder_secretary') : t('member.role_placeholder') });
    const sec = h('input', { type: 'checkbox', class: 'toggle' }); sec.checked = !!secretary;
    // in the App
    const model = h('input', { placeholder: t('member.model_placeholder') });
    const folder = h('input', { placeholder: t('member.folder_placeholder') });
    let picked = (list.find((x) => x.available && !x.later) || {}).id;
    const choices = h('div', { class: 'choices' }, list.filter((x) => !x.later).map((x) => {
      const radio = h('input', { type: 'radio', name: 'harness', value: x.id, disabled: !x.available });
      radio.checked = x.id === picked;
      radio.addEventListener('change', () => { picked = x.id; });
      return h('label', { class: 'choice' + (x.available ? '' : ' off') }, radio, h('div', null, h('b', null, x.title), ' ', h('span', { class: 'dim' }, x.vendor),
        h('div', { class: 'dim', style: 'font-size:12px' }, x.available ? t('member.connected', { program: x.program ? clip(x.program, 48) : '' }) : x.problem)));
    }));
    const later = list.filter((x) => x.later);
    if (later.length) choices.append(h('div', { class: 'later' }, t('member.later_acp'), later.map((x) => h('span', { class: 'chip', title: x.vendor + ' · ' + x.launch }, x.title))));
    // in Claude Code or Codex itself
    let kind = (conf.harness || 'claude-code') + '/' + (conf.surface === 'gui' ? 'gui' : 'cli');
    const hModel = h('input', { value: conf.model || '', placeholder: t('member.model_placeholder'), list: 'relic-claude-models' });
    const models = h('datalist', { id: 'relic-claude-models' }, (opts.claude_models || []).filter(Boolean).map((x) => h('option', { value: x })));
    const effort = h('select', null, (opts.efforts || ['']).map((x) => h('option', { value: x, selected: x === (conf.effort || '') ? true : null }, x || t('common.default_effort'))));
    const hFolder = h('input', { value: conf.folder || '', placeholder: t('member.host_folder_placeholder') });
    const env = h('select', null, h('option', { value: 'local' }, t('member.env_local')), h('option', { value: 'worktree', selected: conf.environment === 'worktree' ? true : null }, t('member.env_worktree')));
    const perm = h('select');
    const fillPerm = () => {
      const allowed = kind.startsWith('claude-code') ? opts.claude_modes : opts.codex_sandboxes;
      perm.textContent = '';
      allowed.forEach((x) => perm.append(h('option', { value: x, selected: x === conf.permission ? true : null }, x)));
    };
    fillPerm();
    const envText = h('textarea', { rows: 3, class: 'mono', placeholder: t('member.env_placeholder') });
    envText.value = Object.entries(conf.env || {}).map(([k, v]) => k + '=' + v).join('\n');
    const start = h('input', { type: 'checkbox', class: 'toggle' }); start.checked = true;
    const kinds = h('div', { class: 'choices two' }, hostKinds().map(([hn, sf, label]) => {
      const radio = h('input', { type: 'radio', name: 'host-kind', value: hn + '/' + sf });
      radio.checked = kind === hn + '/' + sf;
      radio.addEventListener('change', () => { kind = radio.value; fillPerm(); });
      return h('label', { class: 'choice' }, radio, h('b', null, label));
    }));
    // a session that already exists
    let chosen = null, sessions = null;
    const search = h('input', { type: 'search', placeholder: t('member.session_search') });
    const seatName = h('input', { placeholder: t('member.seat_placeholder'), list: 'relic-seat-names' });
    const seatNames = h('datalist', { id: 'relic-seat-names' }, S.snap.members.map((m) => h('option', { value: m.name }, m.display || m.name)));
    const listBox = h('div', { class: 'session-list' }, h('div', { class: 'dim' }, t('member.finding_sessions')));
    const drawSessions = () => {
      listBox.textContent = '';
      if (!sessions) { listBox.append(h('div', { class: 'dim' }, t('member.finding_sessions'))); return; }
      const q = search.value.trim().toLowerCase();
      const rows = sessions.sessions.filter((s) => !q || [s.title, s.cwd, s.id].join(' ').toLowerCase().includes(q)).slice(0, 80);
      if (!rows.length) listBox.append(h('div', { class: 'dim' }, q ? t('member.no_match') : t('member.no_sessions')));
      rows.forEach((s) => listBox.append(h('button', { class: 'session-row' + (chosen === s ? ' on' : ''), type: 'button', onclick: () => { chosen = s; drawSessions(); } },
        h('span', { class: 'chip' }, s.surface === 'gui' ? t('member.harness_gui', { harness: HARNESS_TITLE[s.harness] || s.harness }) : s.surface === 'cli' ? t('member.harness_cli', { harness: HARNESS_TITLE[s.harness] || s.harness }) : (HARNESS_TITLE[s.harness] || s.harness)),
        h('span', { class: 'ellipsis' }, s.title || s.id), h('span', { class: 'dim ellipsis mono' }, clip(s.cwd || '', 40)),
        h('span', { class: 'dim' }, s.updated ? ago(new Date(s.updated * 1000).toISOString()) : ''))));
      if (sessions.problems && sessions.problems.length) listBox.append(h('div', { class: 'dim', style: 'font-size:11.5px' }, sessions.problems.join(t('member.problem_sep'))));
    };
    search.addEventListener('input', drawSessions);
    const loadSessions = async () => {
      if (sessions) return;
      try { sessions = await get('/api/sessions'); } catch (e) { sessions = { sessions: [], problems: [e.message] }; }
      drawSessions();
    };
    const submit = h('button', { class: 'btn primary', type: 'button' });
    const note = h('div', { class: 'dim', style: 'font-size:12.5px' });
    const form = h('div', { class: 'form' });
    const tabs = h('div');
    const draw = () => {
      note.textContent = edit ? t('member.edit_note') : runNotes()[run];
      form.textContent = '';
      tabs.textContent = '';
      if (!edit && !secretary) tabs.append(segControl(runModes(), run, (k) => { run = k; draw(); }));
      if (run === 'existing') {
        form.append(h('label', null, t('common.session'), field(search)), listBox, h('label', null, t('member.which_seat'), field(seatName)), seatNames, h('label', null, t('member.role_new'), field(role)));
        submit.textContent = t('member.bind');
        loadSessions();
        return;
      }
      form.append(h('label', null, t('member.name_label'), field(name)), h('label', null, t('common.role'), field(role)));
      if (run === 'app') {
        form.append(h('div', null, h('div', { class: 'dim', style: 'margin-bottom:6px;font-size:12.5px' }, 'Harness'), choices),
          h('label', null, t('common.model'), field(model)), h('label', null, t('common.work_folder'), field(folder)), h('label', { class: 'switch' }, sec, t('member.make_secretary')));
        submit.textContent = secretary ? t('member.create_secretary') : t('member.create_member');
      } else {
        form.append(h('div', null, h('div', { class: 'dim', style: 'margin-bottom:6px;font-size:12.5px' }, t('member.where_run')), kinds),
          h('div', { class: 'row2' }, h('label', null, t('common.model'), field(hModel)), h('label', null, t('member.effort'), effort)), models,
          h('label', null, t('member.work_folder'), field(hFolder)), h('div', { class: 'row2' }, h('label', null, t('member.environment'), env), h('label', null, t('member.permission'), perm)),
          h('label', null, t('member.env_vars'), envText), edit ? null : h('label', { class: 'switch' }, start, t('member.start_now')));
        submit.textContent = edit ? t('common.save') : (start.checked ? t('member.create_start') : t('member.create_seat_only'));
        start.onchange = () => { submit.textContent = start.checked ? t('member.create_start') : t('member.create_seat_only'); };
      }
    };
    const dialog = h('div', { class: 'dialog wide', role: 'dialog' }, h('h3', null, edit ? t('member.edit_title', { name: card.display || edit }) : secretary ? t('secretary.new_embedded') : t('common.add_member')),
      tabs, note, form, err, h('div', { class: 'acts-row' }, h('button', { class: 'btn', type: 'button', onclick: closeLayer }, t('common.cancel')), submit));
    submit.addEventListener('click', async () => {
      err.textContent = '';
      submit.disabled = true;
      try {
        if (run === 'existing') {
          if (!chosen) throw new Error(t('member.pick_session'));
          if (!seatName.value.trim()) throw new Error(t('member.need_seat_name'));
          await post(orgPath('/bind'), { session: chosen, member: seatName.value.trim(), role: role.value.trim() });
          closeLayer(); toast(t('member.bound', { name: seatName.value.trim() }));
          await refreshSnap();
          go({ kind: 'member', member: seatName.value.trim() });
          return;
        }
        if (!name.value.trim()) throw new Error(t('member.need_name'));
        if (run === 'app') {
          if (!picked) throw new Error(t('member.need_harness'));
          await post(orgPath('/members'), { name: name.value.trim(), role: role.value.trim(), harness: picked, model: model.value.trim(), folder: folder.value.trim(), secretary: sec.checked });
          closeLayer(); toast(t('member.starting', { name: name.value.trim() }));
        } else {
          const [harness, surface] = kind.split('/');
          await post(orgPath('/seat'), { name: name.value.trim(), role: role.value.trim(), harness, surface, model: hModel.value.trim(), effort: effort.value,
            folder: hFolder.value.trim(), environment: env.value, permission: perm.value, env: envText.value, start: !edit && start.checked, edit: !!edit });
          closeLayer(); toast(edit ? t('member.edit_saved') : start.checked ? t('member.starting_first', { name: name.value.trim() }) : t('member.seat_created'));
        }
        await refreshSnap();
        if (!edit) go({ kind: sec.checked && run === 'app' ? 'secretary' : 'member', member: name.value.trim() });
      } catch (e) { err.textContent = e.message; submit.disabled = false; }
    });
    draw();
    scrim(dialog);
    setTimeout(() => (run === 'existing' ? search : (edit ? role : name)).focus(), 0);
  }
  async function forwardDialog(who) {
    const info = await get(orgPath('/waiting') + '?member=' + enc(who)).catch(() => ({ waiting: [], members: [] }));
    const first = (info.waiting || [])[0];
    const err = h('div', { class: 'err' });
    const to = h('input', { value: first ? first.to.join(',') : info.members.join(','), placeholder: t('forward.to_placeholder') });
    const body = h('textarea', { rows: 10, placeholder: t('forward.body_placeholder') });
    const submit = h('button', { class: 'btn primary', type: 'button' }, t('common.send'));
    submit.addEventListener('click', async () => {
      const text = body.value.trim();
      if (!text) { err.textContent = t('forward.need_body'); return; }
      if (text.startsWith('\u3010Relic') && submit.dataset.sure !== '1') { err.textContent = t('forward.not_reply', { prefix: '\u3010Relic' }); submit.dataset.sure = '1'; return; }
      submit.disabled = true;
      try {
        await post(orgPath('/forward'), { member: who, to: to.value, body: text });
        closeLayer(); toast(t('forward.sent', { name: dname(who) })); await refreshSnap();
      } catch (e) { err.textContent = e.message; submit.disabled = false; }
    });
    scrim(h('div', { class: 'dialog wide', role: 'dialog' }, h('h3', null, t('forward.title', { name: dname(who) })),
      h('div', { class: 'dim', style: 'font-size:12.5px' }, first ? t('forward.waiting', { name: dname(who), n: info.waiting.length, ids: first.ids.join(',') })
        : t('forward.how', { name: dname(who) })),
      h('div', { class: 'form' }, h('label', null, t('forward.to'), field(to)), h('label', null, t('common.reply'), body)), err,
      h('div', { class: 'acts-row' }, h('button', { class: 'btn', type: 'button', onclick: closeLayer }, t('common.cancel')), submit)));
    setTimeout(() => body.focus(), 0);
  }
  async function seatAction(what, who, ask) {
    if (ask && !confirm(ask)) return;
    try {
      await post(orgPath('/' + what), { member: who });
      toast({ fresh: t('seat.fresh', { name: dname(who) }), unbind: t('seat.unbind', { name: dname(who) }), open_session: t('seat.open_session', { name: dname(who) }) }[what] || t('seat.done'));
      closeCard(); await refreshSnap();
    } catch (e) { toast(e.message, 6000); }
  }
  function openSecretarySetup() {
    const mains = S.snap.members.filter((m) => m.state !== 'vacant' && m.surface !== 'subagent' && m.surface !== 'chat');
    scrim(h('div', { class: 'dialog', role: 'dialog' }, h('h3', null, t('secretary.setup_title')),
      h('div', { class: 'dim', style: 'font-size:12.5px' }, t('secretary.setup_intro')),
      mains.length ? h('div', { class: 'choices' }, mains.map((m) => h('button', { class: 'choice', type: 'button', onclick: async () => {
        try { await post(orgPath('/secretary'), { member: m.name }); closeLayer(); await refreshSnap(); go({ kind: 'secretary', member: m.name }); } catch (e) { toast(e.message); }
      } }, avatar(m.name, { size: 'sm', click: false }), h('div', null, h('b', null, t('secretary.make', { name: m.display || m.name })), h('div', { class: 'dim', style: 'font-size:12px' }, [m.harness_label, m.surface_label].filter(Boolean).join(' · ')))))) : null,
      h('div', { class: 'acts-row' }, h('button', { class: 'btn', type: 'button', onclick: closeLayer }, t('common.cancel')), h('button', { class: 'btn primary', type: 'button', onclick: () => memberDialog({ secretary: true }) }, t('secretary.new_embedded')))));
  }
  function orgDialog() {
    const err = h('div', { class: 'err' });
    const name = h('input', { placeholder: t('neworg.name_placeholder') });
    const purpose = h('textarea', { rows: 3, placeholder: t('neworg.purpose_placeholder') });
    const gov = h('select', null, h('option', { value: 'leader' }, t('neworg.gov_leader')), h('option', { value: 'peer' }, t('neworg.gov_peer')));
    const submit = h('button', { class: 'btn primary', type: 'button' }, t('neworg.create'));
    submit.addEventListener('click', async () => {
      if (!name.value.trim()) { err.textContent = t('neworg.need_name'); return; }
      submit.disabled = true;
      try {
        const r = await post('/api/orgs', { name: name.value.trim(), purpose: purpose.value.trim(), governance: gov.value });
        closeLayer(); await loadOrgs(); await openOrg(r.org_id); memberDialog({ secretary: true });
      } catch (e) { err.textContent = e.message; submit.disabled = false; }
    });
    const purposeWrap = h('div', { class: 'field' }, purpose, PREFS.voice !== 'off' ? micButton(purpose) : null);
    scrim(h('div', { class: 'dialog', role: 'dialog' }, h('h3', null, t('common.new_org')),
      h('div', { class: 'form' }, h('label', null, t('common.name'), field(name)), h('label', null, t('neworg.purpose'), purposeWrap), h('label', null, t('neworg.governance'), gov)), err,
      h('div', { class: 'acts-row' }, h('button', { class: 'btn', type: 'button', onclick: closeLayer }, t('common.cancel')), submit)));
    setTimeout(() => name.focus(), 0);
  }

  // ------------------------------------------------------------------ details: context and trajectory, tasks, protocols, documents
  async function openDetails(tab, opts = {}) {
    if (!S.snap) return;
    closeCard();
    const panel = h('div', { class: 'details', role: 'dialog', 'aria-label': t('details.dialog') });
    const tabs = h('div', { class: 'tabs' });
    const content = h('div', { class: 'content' });
    const show = (which) => { [...tabs.children].forEach((b) => b.classList.toggle('on', b.dataset.t === which)); render(which); };
    [['trace', t('common.context_trace')], ['tasks', t('common.tasks')], ['protocols', t('details.tab_protocols')], ['docs', t('details.tab_docs')]].forEach(([key, label]) =>
      tabs.append(h('button', { type: 'button', 'data-t': key, onclick: () => show(key) }, label)));
    panel.append(h('div', { class: 'bar' }, h('h3', null, S.snap.org.name), tabs, h('button', { class: 'icon-btn', 'aria-label': t('common.close'), onclick: closeLayer }, icon('x'))), content);
    scrim(panel);
    let current = opts.member || (S.view.member) || (S.snap.members[0] && S.snap.members[0].name);
    let taskFilter = opts.filter || (opts.task ? 'all' : 'open');
    async function render(which) {
      content.textContent = ''; content.className = 'content' + (which === 'trace' || which === 'docs' ? '' : ' one');
      if (which === 'trace') {
        const left = h('div', { class: 'left' }); const right = h('div', { class: 'right' });
        content.append(left, right);
        for (const m of S.snap.members) {
          left.append(h('button', { class: 'chat-row' + (m.name === current ? ' on' : ''), type: 'button', onclick: () => { current = m.name; render('trace'); } },
            avatar(m.name, { size: 'sm', dot: true, click: false }), h('div', { class: 'main' }, h('div', { class: 'name' }, h('span', { class: 'ellipsis' }, m.display || m.name)), h('div', { class: 'sub ellipsis' }, [m.harness_label, m.surface_label].filter(Boolean).join(' · '))), h('div')));
        }
        await traceView(right, current);
      } else if (which === 'tasks') {
        const right = h('div', { class: 'right' }); content.append(right);
        const filters = h('div', { class: 'seg' }, [['open', t('task.working')], ['blocked', t('task.blocked')], ['done', t('details.filter_done')], ['all', t('common.all')]].map(([k, label]) =>
          h('button', { class: taskFilter === k ? 'on' : '', type: 'button', onclick: () => { taskFilter = k; render('tasks'); } }, label + ' ' + countTasks(k))));
        right.append(h('div', { class: 'filters' }, filters));
        const list = S.snap.tasks.filter((x) => taskFilter === 'all' || (taskFilter === 'open' ? !['done', 'dropped'].includes(x.status) : x.status === taskFilter)).slice().reverse();
        if (!list.length) right.append(h('div', { class: 'empty' }, t('details.no_tasks')));
        for (const task of list) {
          const d = h('details', { class: 'task' + (opts.task === task.id ? ' hi' : ''), open: opts.task === task.id ? true : null },
            h('summary', null, task.owner ? avatar(task.owner, { size: 'sm', click: false }) : h('span'),
              h('div', { style: 'min-width:0' }, h('div', { class: 'tt ellipsis' }, task.title), h('div', { class: 'sub' }, task.id + ' · ' + (task.owner ? dname(task.owner) : t('details.no_owner')) + (task.at ? ' · ' + t('details.updated', { when: dayLabel(toDate(task.at)) + ' ' + clock(task.at) }) : ''))),
              h('span', { class: 'chips' }, task.status === 'done' && task.report ? h('span', { class: 'chip accent' }, t('details.has_report')) : null,
                h('span', { class: 'chip ' + ({ done: 'ok', blocked: 'bad', working: 'warn' }[task.status] || '') }, taskLabel(task.status) || task.status))),
            h('div', { class: 'inner' }, h('div', null, h('span', { class: 'dim' }, t('details.label_title')), task.title),
              task.created_by ? h('div', null, h('span', { class: 'dim' }, t('details.label_created_by')), dname(task.created_by)) : null,
              task.status === 'done' && task.report ? reportBlock(task) : null,
              h('div', null, h('span', { class: 'dim' }, t('details.label_evidence')), (task.evidence || []).length ? h('ul', { class: 'ev' }, task.evidence.map((ev) => h('li', null, inline(ev)))) : t('details.no_evidence')),
              task.owner ? h('div', { class: 'row-acts' }, h('button', { class: 'btn sm', type: 'button', onclick: () => { closeLayer(); go({ kind: 'member', member: task.owner }); } }, t('details.ask', { name: dname(task.owner) }))) : null));
          right.append(d);
          if (opts.task === task.id) setTimeout(() => d.scrollIntoView({ block: 'center' }), 0);
        }
      } else if (which === 'protocols') {
        const right = h('div', { class: 'right' }); content.append(right);
        const inherited = S.snap.inherited_protocols || [], replaced = S.snap.replaced_protocols || [];
        if (!S.snap.protocols.length && !inherited.length && !replaced.length) right.append(h('div', { class: 'empty' }, t('details.no_protocols')));
        for (const p of S.snap.protocols.slice().reverse()) {
          right.append(h('div', { class: 'task' }, h('div', { class: 'inner' },
            h('b', null, t('details.protocol_head', { id: p.id, title: p.title, kind: p.strength === 'strong' ? t('details.strong_protocol') : t('details.weak_protocol'), status: { active: t('details.status_active'), proposed: t('details.status_proposed'), rejected: t('details.status_rejected'), superseded: t('details.status_superseded'), retired: t('details.status_retired'), enacted: t('details.status_enacted') }[p.status] || p.status })),
            p.retire_target ? h('div', null, h('span', { class: 'dim' }, t('details.label_retires')), protoName(p.retire_target)) : null,
            p.supersedes ? h('div', null, h('span', { class: 'dim' }, t('details.label_supersedes')), protoName(p.supersedes)) : null,
            p.inherit ? h('div', { class: 'dim' }, t('org.protocol_inherits')) : null,
            p.trigger ? h('div', null, h('span', { class: 'dim' }, t('details.label_applies')), p.trigger) : null,
            p.guidance ? h('div', { style: 'white-space:pre-wrap' }, p.guidance) : null,
            p.summary_for_person ? h('div', { class: 'cc-summary md' }, h('div', { class: 'dim' }, t('details.label_summary')), rich(p.summary_for_person)) : null,
            p.rules && p.rules.length ? h('pre', { class: 'doc-body' }, JSON.stringify(plainRules(p.rules), null, 2)) : null,
            checkRulesView(p.rules),
            h('div', { class: 'dim' }, [t('details.proposed_by', { name: dname(p.author) }), t('details.votes', { n: p.votes }), t('details.uses', { n: p.uses }),
              p.retired_by_person ? t('details.retired_by_person') : ''].filter(Boolean).join(' · ')))));
        }
        // protocols that bind here from the organizations above, and the ones above that were overridden or stopped
        if (inherited.length) right.append(h('h4', { class: 'pro-h' }, t('details.inherited_title')));
        for (const p of inherited) {
          right.append(h('div', { class: 'task' }, h('div', { class: 'inner' },
            h('b', null, t('details.protocol_head', { id: p.id, title: p.title, kind: p.strength === 'strong' ? t('details.strong_protocol') : t('details.weak_protocol'), status: t('details.status_active') })),
            h('div', { class: 'dim' }, [t('org.inherited_from', { name: p.from }), p.issued_by && p.issued_by.name ? t('org.issued_by', { name: p.issued_by.name }) : ''].filter(Boolean).join(' · ')),
            p.trigger ? h('div', null, h('span', { class: 'dim' }, t('details.label_applies')), p.trigger) : null,
            p.guidance ? h('div', { style: 'white-space:pre-wrap' }, p.guidance) : null,
            p.summary_for_person ? h('div', { class: 'cc-summary md' }, h('div', { class: 'dim' }, t('details.label_summary')), rich(p.summary_for_person)) : null,
            p.rules && p.rules.length ? h('pre', { class: 'doc-body' }, JSON.stringify(plainRules(p.rules), null, 2)) : null,
            checkRulesView(p.rules))));
        }
        if (replaced.length) right.append(h('h4', { class: 'pro-h' }, t('details.replaced_title')));
        for (const r of replaced) {
          right.append(h('div', { class: 'task ended' }, h('div', { class: 'inner' }, h('b', { class: 'struck' }, r.id + ' ' + r.title),
            h('div', { class: 'dim' }, r.how === 'retired' ? t('org.protocol_retired', { from: r.from, at: r.at, by: r.by }) : t('org.protocol_overridden', { from: r.from, at: r.at, by: r.by })))));
        }
      } else if (which === 'docs') {
        const left = h('div', { class: 'left' }); const right = h('div', { class: 'right' });
        content.append(left, right);
        if (!S.snap.documents.length) right.append(h('div', { class: 'empty' }, t('details.no_docs')));
        for (const d of S.snap.documents) {
          left.append(h('button', { class: 'chat-row', type: 'button', onclick: async () => {
            right.textContent = '';
            const doc = await get(orgPath('/document?key=' + enc(d.key)));
            right.append(h('h3', { style: 'margin:0 0 4px' }, d.key + ' · ' + t('details.revision', { n: doc.revision })), h('div', { class: 'dim', style: 'margin-bottom:10px;font-size:12.5px' }, t('details.written', { name: dname(doc.author), when: dayLabel(toDate(doc.at)) + ' ' + clock(doc.at) })), h('div', { class: 'doc-body' }, doc.body));
          } }, h('div', { class: 'avatar sm group' }, icon('folder', 14)), h('div', { class: 'main' }, h('div', { class: 'name' }, d.key), h('div', { class: 'sub' }, t('details.revision', { n: d.revision }) + ' · ' + dname(d.author))), h('div')));
        }
      }
    }
    function countTasks(k) { return S.snap.tasks.filter((x) => k === 'all' || (k === 'open' ? !['done', 'dropped'].includes(x.status) : x.status === k)).length; }
    show(tab || 'trace');
  }
  function reportBlock(task) {
    return h('div', { class: 'report' }, h('div', { class: 'report-h' }, icon('check', 14), h('b', null, t('report.title')),
      task.done_at ? h('span', { class: 'dim' }, dayLabel(toDate(task.done_at)) + ' ' + clock(task.done_at)) : null),
      h('div', { class: 'md' }, rich(task.report)));
  }
  async function traceView(box, name) {
    const m = member(name);
    box.textContent = '';
    if (!m) return;
    box.append(h('h3', { style: 'margin:0 0 2px' }, t('trace.title', { name: m.display || name })),
      h('div', { class: 'dim', style: 'margin-bottom:12px;font-size:12.5px' }, [name, m.harness_label, m.surface_label, m.model, m.agent ? 'subagent ' + m.agent.slice(0, 12) + (m.parent ? t('trace.in_session', { name: dname(m.parent) }) : '') : m.session ? t('trace.session', { id: m.session.slice(0, 12) }) : ''].filter(Boolean).join(' · ')));
    const filter = { role: 'all', q: '' };
    const filters = h('div', { class: 'filters' });
    const list = h('div');
    let data = null;
    const seg = h('div', { class: 'seg' }, [['all', t('common.all')], ['talk', t('trace.filter_talk')], ['tools', t('trace.filter_actions')]].map(([k, label]) => h('button', { class: k === 'all' ? 'on' : '', type: 'button', 'data-k': k, onclick: () => {
      filter.role = k; [...seg.children].forEach((b) => b.classList.toggle('on', b.dataset.k === k)); draw(); } }, label)));
    const q = h('input', { type: 'search', class: 'input', placeholder: t('trace.search'), style: 'width:220px;height:30px' });
    q.addEventListener('input', () => { filter.q = q.value.toLowerCase(); draw(); });
    filters.append(seg, field(q));
    const older = h('button', { class: 'more', type: 'button' }, t('trace.load_older'));
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
      if (data && data.missing) { list.append(h('div', { class: 'empty' }, t('trace.no_session'))); return; }
      const steps = (data ? data.steps : []).filter((s) => (filter.role === 'all' || (filter.role === 'talk' ? ['user', 'assistant'].includes(s.role) : ['tool_call', 'tool_result'].includes(s.role))) &&
        (!filter.q || (s.text || '').toLowerCase().includes(filter.q)));
      if (!steps.length) list.append(h('div', { class: 'empty' }, data ? t('trace.no_steps') : t('common.loading')));
      const wrap = h('div', { class: 'acts', style: 'max-width:none' }, h('div', { class: 'list', style: 'border-top:0' }));
      for (const s of steps) {
        const label = { user: t('trace.user'), assistant: t('common.reply'), tool_call: toolName(s.tool), tool_result: t('common.result'), thinking: t('trace.thinking'), context: t('trace.injected') }[s.role] || s.role;
        wrap.firstChild.append(h('details', { class: 'step' + (s.error ? ' err' : s.role === 'tool_result' ? ' ok' : ''), open: ['user', 'assistant'].includes(s.role) ? true : null },
          h('summary', null, h('span', { class: 'bullet' }), h('span', { class: 'tool' }, label), h('span', { class: 'arg ellipsis' }, s.role === 'tool_call' ? stepArg(s) : clip(s.text, 120)), h('span', { class: 'state' }, clock(s.at))),
          h('div', { class: 'io' }, h('pre', null, s.text))));
      }
      if (steps.length) list.append(wrap);
      if (data && data.total) list.append(h('div', { class: 'dim', style: 'font-size:12px;margin-top:8px' }, t('trace.total', { n: data.total }) + (data.path ? ' · ' + data.path : '')));
    }
    await fetchMore(null);
  }

  // ------------------------------------------------------------------ settings (like Claude Code / Codex)
  function sections() { return [['profile', t('settings.profile'), 'user'], ['appearance', t('settings.appearance'), 'palette'], ['language', t('settings.language.title'), 'globe'], ['voice', t('common.voice_input'), 'mic'],
    ['notify', t('settings.notify'), 'bell'], ['harness', t('common.harness'), 'plug'], ['about', t('settings.about'), 'info']]; }
  const installLogs = {};
  let settingsPane = null;
  function openSettings(section) {
    let current = section || 'profile';
    const nav = h('nav', null, h('h3', null, t('common.settings')));
    const pane = h('div', { class: 'pane' });
    const box = h('div', { class: 'settings', role: 'dialog', 'aria-label': t('common.settings') }, nav, pane);
    sections().forEach(([k, label, ic]) => nav.append(h('button', { type: 'button', 'data-k': k, onclick: () => { current = k; draw(); } }, icon(ic, 16), label)));
    function draw() {
      [...nav.querySelectorAll('button')].forEach((b) => b.classList.toggle('on', b.dataset.k === current));
      pane.textContent = '';
      pane.append(h('button', { class: 'icon-btn close', 'aria-label': t('common.close'), onclick: () => { settingsPane = null; closeLayer(); } }, icon('x')));
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
    const box = h('input', { type: 'checkbox', class: 'toggle' }); box.checked = !!value;
    box.addEventListener('change', () => onChange(box.checked));
    return box;
  }
  function redraw() { if (settingsPane) settingsPane.draw(); }
  function drawProfile(pane) {
    pane.append(h('h4', null, t('settings.profile')));
    const name = h('input', { class: 'input', value: PREFS.name || '', placeholder: t('common.you'), style: 'width:220px' });
    const saveName = () => setPrefs({ name: name.value.trim() }).then(() => { renderAll(false); });
    name.addEventListener('change', saveName);
    name.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.isComposing) name.blur(); });
    const av = avatar(HUMAN, { size: 'lg', click: false });
    pane.append(setRow(t('settings.avatar'), t('settings.avatar_hint'), h('div', { style: 'display:flex;align-items:center;gap:10px' }, av,
      h('button', { class: 'btn sm', type: 'button', onclick: async () => {
        const data = await pickImage(); if (!data) return;
        try { const r = await post('/api/avatar', { data }); PREFS.avatar = r.avatar; applyPrefs(); renderAll(false); redraw(); } catch (e) { toast(e.message); }
      } }, t('common.change')),
      PREFS.avatar ? h('button', { class: 'btn sm ghost', type: 'button', onclick: async () => { await post('/api/avatar', { data: '' }); PREFS.avatar = null; applyPrefs(); renderAll(false); redraw(); } }, t('settings.remove')) : null)));
    pane.append(setRow(t('common.name'), t('settings.name_hint'), field(name)));
  }
  function drawAppearance(pane) {
    pane.append(h('h4', null, t('settings.appearance')));
    pane.append(setRow(t('settings.theme'), null, segControl([['system', t('common.theme_system')], ['light', t('common.theme_light')], ['dark', t('common.theme_dark')]], PREFS.theme, (k) => { setPrefs({ theme: k }); redraw(); })));
    const colors = { clay: '#C8643F', ink: '#3A3936', indigo: '#5B61D6', blue: '#2F6BD8', rose: '#C4456C', amber: '#B9821D' };
    pane.append(setRow(t('settings.accent'), t('settings.accent_hint'), h('div', { class: 'swatches' }, Object.entries(colors).map(([k, c]) =>
      h('button', { class: 'swatch' + (PREFS.accent === k ? ' on' : ''), type: 'button', title: k, style: 'background:' + c, onclick: () => { setPrefs({ accent: k }); redraw(); } })))));
    pane.append(setRow(t('settings.font_size'), null, segControl([['small', t('common.size_small')], ['medium', t('common.size_medium')], ['large', t('common.size_large')]], PREFS.font, (k) => { setPrefs({ font: k }); redraw(); })));
    pane.append(setRow(t('settings.density'), null, segControl([['comfortable', t('settings.density_comfortable')], ['compact', t('settings.density_compact')]], PREFS.density, (k) => { setPrefs({ density: k }); redraw(); })));
  }
  function drawLanguage(pane) {
    pane.append(h('h4', null, t('settings.language.title')));
    // every language with a word list, each in its own name; a language chosen before its list went away stays listed
    const options = [['', t('settings.language.system', { lang: navigator.language || '' })]].concat(L.languages.map((l) => [l.code, l.name]));
    if (PREFS.lang && !options.some(([v]) => v === PREFS.lang)) options.push([PREFS.lang, PREFS.lang]);
    const sel = h('select', { class: 'input', style: 'width:200px' }, options.map(([v, l]) =>
      h('option', { value: v, selected: (PREFS.lang || '') === v ? true : null }, l)));
    sel.addEventListener('change', async () => {
      await setPrefs({ lang: sel.value });
      try { sessionStorage.setItem('relic.reopen', 'language'); } catch (e) { /* Settings stays closed */ }
      location.reload();
    });
    pane.append(setRow(t('settings.language.label'), t('settings.language.hint'), sel));
    pane.append(setRow(t('settings.auto_names.label'), t('settings.auto_names.hint'), toggleControl(PREFS.auto_names, (v) => setPrefs({ auto_names: v }).then(scheduleRefresh))));
  }
  function drawVoice(pane) {
    pane.append(h('h4', null, t('common.voice_input')));
    pane.append(setRow(t('common.voice_input'), t('settings.voice_hint'), segControl([['browser', t('settings.voice_edge')], ['off', t('settings.voice_off')]], PREFS.voice, (k) => { setPrefs({ voice: k }).then(() => { renderAll(false); redraw(); }); })));
    const test = h('textarea', { class: 'input', rows: 2, placeholder: t('settings.voice_try_here') });
    pane.append(setRow(t('settings.voice_try'), Voice.supported() ? t('settings.voice_supported') : t('settings.voice_unsupported'), h('div', { class: 'field', style: 'width:300px' }, test, micButton(test))));
    pane.append(h('div', { class: 'dim', style: 'font-size:12.5px;line-height:1.7;margin-top:10px' },
      t('settings.voice_wechat')));
  }
  function drawNotify(pane) {
    pane.append(h('h4', null, t('settings.notify')));
    pane.append(setRow(t('settings.desktop_notify'), t('settings.desktop_notify_hint'), toggleControl(PREFS.notify, async (v) => {
      if (v && 'Notification' in window && Notification.permission !== 'granted') await Notification.requestPermission();
      setPrefs({ notify: v });
    })));
    pane.append(setRow(t('settings.notify_test'), null, h('button', { class: 'btn sm', type: 'button', onclick: async () => {
      if (!('Notification' in window)) { toast(t('settings.notify_unsupported')); return; }
      if (Notification.permission !== 'granted') await Notification.requestPermission();
      if (Notification.permission === 'granted') new Notification('Relic', { body: t('settings.notify_on'), icon: '/static/icon-192.png' }); else toast(t('settings.notify_denied'));
    } }, t('settings.notify_send_test'))));
  }
  async function drawHarness(pane) {
    pane.append(h('h4', null, t('common.harness')));
    pane.append(h('div', { class: 'dim', style: 'font-size:12.5px;margin-bottom:12px' }, t('settings.harness_intro')));
    const list = await harnessList(true);
    for (const x of list.filter((y) => !y.later)) {
      const path = h('input', { class: 'input mono', value: (PREFS.paths || {})[x.id] || '', placeholder: x.program || t('settings.auto_find'), style: 'font-size:12px' });
      const log = h('div', { class: 'log', hidden: !installLogs[x.id] }, (installLogs[x.id] || []).join('\n'));
      const kv = h('dl', { class: 'kv' });
      const row = (k, v) => append(kv, [h('dt', null, k), h('dd', null, v)]);
      row(t('common.status'), x.available ? h('span', { class: 'chip ok' }, t('settings.connected')) : h('span', { class: 'chip bad' }, x.problem || t('settings.not_connected')));
      row(t('settings.program'), h('div', { style: 'display:flex;gap:6px' }, path, h('button', { class: 'btn sm', type: 'button', onclick: () => setPrefs({ paths: Object.assign({}, PREFS.paths, { [x.id]: path.value.trim() }) }).then(() => { toast(t('settings.path_saved')); redraw(); }) }, t('common.save'))));
      row(t('settings.adapter'), x.adapter_installed ? t('settings.adapter_version', { adapter: x.adapter, version: x.adapter_version }) : t('settings.adapter_missing', { adapter: x.adapter }));
      row('Node.js', x.node || t('settings.not_found'));
      row(t('settings.default_mode'), x.mode || (x.note ? t('settings.adapter_default_note', { note: x.note }) : t('settings.adapter_default')));
      if (x.models && x.models.length) row(t('settings.models'), x.models.join(t('settings.models_sep')));
      const install = h('button', { class: 'btn sm', type: 'button', onclick: async () => {
        installLogs[x.id] = ['$ ' + x.install]; log.hidden = false; log.textContent = installLogs[x.id].join('\n');
        try { await post('/api/harnesses/' + x.id + '/install', {}); } catch (e) { toast(e.message); }
      } }, x.adapter_installed ? t('settings.reinstall_adapter') : t('settings.install_adapter'));
      pane.append(h('div', { class: 'harness', 'data-id': x.id }, h('div', { class: 'h' }, h('b', null, x.title), h('span', { class: 'dim' }, x.vendor), h('div', { style: 'flex:1' }), install), kv, log));
    }
    pane.append(h('h4', { style: 'margin-top:12px;font-size:15px' }, t('settings.later')));
    pane.append(h('div', { class: 'later-list' }, list.filter((y) => y.later).map((x) => h('div', { class: 'it' }, h('span', null, h('b', null, x.title), ' ', h('span', { class: 'dim' }, x.vendor)), h('span', { class: 'mono dim' }, x.launch)))));
    pane.append(h('div', { class: 'dim', style: 'font-size:12px;margin-top:8px' }, t('settings.later_hint')));
  }
  function onInstall(ev) {
    const lines = installLogs[ev.id] || (installLogs[ev.id] = []);
    if (ev.line) lines.push(ev.line);
    if ('done' in ev) { lines.push(ev.done === 0 ? t('settings.install_done') : t('settings.install_failed', { code: ev.done })); S.harnesses = null; toast(ev.done === 0 ? t('settings.adapter_installed') : t('settings.adapter_install_failed')); }
    const log = document.querySelector('.harness[data-id="' + ev.id + '"] .log');
    if (log) { log.hidden = false; log.textContent = lines.slice(-200).join('\n'); log.scrollTop = log.scrollHeight; }
    if ('done' in ev && settingsPane && settingsPane.current === 'harness') setTimeout(redraw, 300);
  }
  function drawAbout(pane) {
    pane.append(h('h4', null, t('settings.about')));
    const open = (what) => post('/api/open', { what }).catch((e) => toast(e.message));
    pane.append(setRow(t('settings.data_folder'), PREFS.data || '~/.relic', h('button', { class: 'btn sm', type: 'button', onclick: () => open('data') }, t('common.open'))));
    pane.append(setRow(t('settings.logs'), t('settings.logs_hint'), h('button', { class: 'btn sm', type: 'button', onclick: () => open('logs') }, t('common.open'))));
    pane.append(setRow(t('settings.local_server'), t('settings.local_server_hint', { port: PREFS.port || '' }), h('span', { class: 'chip' }, 'v' + (PREFS.version || ''))));
    pane.append(setRow(t('settings.install_app'), isApp() ? t('settings.install_app_done') : t('settings.install_app_hint'),
      isApp() ? h('span', { class: 'chip ok' }, t('settings.installed')) : h('button', { class: 'btn sm', type: 'button', onclick: () => { settingsPane = null; closeLayer(); installApp(); } }, t('settings.install'))));
  }

  // ------------------------------------------------------------------ organization chart
  // Every organization as a tree by parent: formal organizations in solid frames, subgroups in dashed ones, closed and
  // dissolved ones grayed, the secretariat highlighted; each with its leader, members and what waits on the person. A
  // session that holds seats in several organizations links them with a thin dashed line and marks them "also
  // elsewhere"; pointing at an organization brings its lines forward. Wide windows draw the tree top-down, narrow ones
  // list it indented; both scroll. Clicking an organization opens it. Data: GET /api/orgchart.
  let chart = null, chartFrame = 0;
  const OC = { w: 236, h: 80, gx: 22, gy: 46, pad: 24, bulge: 40, indent: 20, narrow: 620 };
  function svgEl(tag, attrs) {
    const n = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v != null) n.setAttribute(k, String(v));
    return n;
  }
  // "<org id>/<P#>", a protocol of an organization above, by that organization's name
  function protoName(ref) {
    const m = /^([^\/]+)\/(.+)$/.exec(String(ref || ''));
    if (!m) return String(ref || '');
    const o = S.orgs.find((x) => x.id === m[1]);
    return t('org.protocol_ref', { org: o ? o.name : m[1], id: m[2] });
  }
  const chartLive = () => !!(chart && chart.box.isConnected);
  // focus: the id of the organization it is opened from; the chart first shows that organization and the ones below it
  function openChart(focus) {
    closeCard(); closeMenu();
    const canvas = h('div', { class: 'oc-canvas', tabindex: '0' });
    const pick = (key) => {
      const box = h('input', { type: 'checkbox', class: 'toggle' });
      box.checked = !!load(key, true);
      box.addEventListener('change', () => { save(key, box.checked); drawChart(); });
      return box;
    };
    const closed = pick('relic.chart.closed'), links = pick('relic.chart.links');
    const swatch = (cls, label) => h('span', null, h('i', { class: cls }), label);
    const tool = (ic, label, run) => h('button', { class: 'icon-btn', type: 'button', title: label, 'aria-label': label, onclick: run }, icon(ic, 16));
    const pct = h('button', { class: 'oc-pct', type: 'button', title: t('chart.zoom_actual'), onclick: () => zoomBy(1 / chart.view.s) }, '100%');
    const box = h('div', { class: 'details oc', role: 'dialog', 'aria-label': t('chart.title') },
      h('div', { class: 'bar' }, h('h3', null, t('chart.title')),
        h('div', { class: 'oc-zoom' }, tool('minus', t('chart.zoom_out'), () => zoomBy(1 / 1.25)), pct,
          tool('plus', t('chart.zoom_in'), () => zoomBy(1.25)), tool('fit', t('chart.fit'), () => fitChart('all'))),
        h('label', { class: 'switch' }, closed, t('chart.show_closed')), h('label', { class: 'switch' }, links, t('chart.show_links')),
        h('button', { class: 'icon-btn', type: 'button', 'aria-label': t('common.close'), onclick: closeLayer }, icon('x'))),
      h('div', { class: 'oc-legend' }, swatch('', t('org.kind_formal')), swatch('sub', t('org.kind_subgroup')), swatch('cab', t('org.cabinet_chip')),
        swatch('ended', t('chart.legend_ended')), swatch('link', t('chart.legend_shared')), h('span', { class: 'oc-hint' }, t('chart.pan_hint'))),
      canvas);
    scrim(box);
    chart = { box, canvas, closed, links, pct, data: null, first: true, timer: null, focus: typeof focus === 'string' ? focus : '', view: null };
    wireChart(canvas);
    loadChart();
  }
  // ---- the tree view of the chart: the plane is moved and scaled as a whole (view: x, y, s); at first, and until it is
  // moved or zoomed, it is fitted to the window: the organization it was opened from with those below it, or everything
  const OCZ = { min: 0.15, max: 2, margin: 28, keep: 80 };
  function applyView() {
    const c = chart;
    if (!c || !c.plane || !c.view) return;
    const v = c.view;
    c.plane.style.transform = 'translate(' + Math.round(v.x) + 'px,' + Math.round(v.y) + 'px) scale(' + v.s + ')';
    c.pct.textContent = Math.round(v.s * 100) + '%';
  }
  function clampView() {  // some of the chart stays in the window
    const c = chart, v = c.view, cw = c.canvas.clientWidth, ch = c.canvas.clientHeight;
    v.x = Math.min(cw - OCZ.keep, Math.max(OCZ.keep - c.size.w * v.s, v.x));
    v.y = Math.min(ch - OCZ.keep, Math.max(OCZ.keep - c.size.h * v.s, v.y));
  }
  function fitChart(target) {  // target: 'focus' (the organization opened from and those below it) or 'all'
    const c = chart;
    if (!chartLive() || !c.plane) return;
    const want = target === 'focus' && c.focusBox ? 'focus' : 'all';
    const b = want === 'focus' ? c.focusBox : c.allBox;
    const cw = c.canvas.clientWidth, ch = c.canvas.clientHeight, m = OCZ.margin;
    const s = Math.max(OCZ.min, Math.min(1, (cw - 2 * m) / b.w, (ch - 2 * m) / b.h));
    c.view = { s, x: (cw - b.w * s) / 2 - b.x * s, y: Math.max(m, (ch - b.h * s) / 2) - b.y * s, auto: want };
    applyView();
  }
  function zoomAt(f, px, py) {  // (px, py): the point of the canvas that stays where it is
    const c = chart;
    if (!chartLive() || !c.plane || !c.view) return;
    const v = c.view, s = Math.min(OCZ.max, Math.max(OCZ.min, v.s * f));
    if (Math.abs(s - v.s) < 1e-4) return;
    v.x = px - (px - v.x) * s / v.s; v.y = py - (py - v.y) * s / v.s; v.s = s; v.auto = null;
    clampView(); applyView();
  }
  function zoomBy(f) { if (chartLive() && chart.view) zoomAt(f, chart.canvas.clientWidth / 2, chart.canvas.clientHeight / 2); }
  function panBy(dx, dy) {
    const v = chart.view;
    v.x += dx; v.y += dy; v.auto = null;
    clampView(); applyView();
  }
  // drag to move (one finger or the mouse), pinch or scroll to zoom, double-click empty space to fit; keys + - 0 and arrows
  function wireChart(canvas) {
    const pts = new Map();
    let drag = null, pinch = null;
    const on = () => chartLive() && chart.canvas === canvas && canvas.classList.contains('pan') && chart.view;
    const at = (x, y) => { const r = canvas.getBoundingClientRect(); return [x - r.left, y - r.top]; };
    canvas.addEventListener('wheel', (e) => {
      if (!on()) return;
      e.preventDefault();
      const dy = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaMode === 2 ? e.deltaY * 400 : e.deltaY;
      zoomAt(Math.exp(-dy * 0.0015), ...at(e.clientX, e.clientY));
    }, { passive: false });
    canvas.addEventListener('pointerdown', (e) => {
      if (!on() || (e.pointerType === 'mouse' && e.button !== 0)) return;
      pts.set(e.pointerId, [e.clientX, e.clientY]);
      if (pts.size === 1) drag = { id: e.pointerId, x: e.clientX, y: e.clientY, vx: chart.view.x, vy: chart.view.y, moved: false };
      else if (pts.size === 2) {
        const [a, b] = [...pts.values()];
        pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, s: chart.view.s };
        drag = null;
      }
    });
    canvas.addEventListener('pointermove', (e) => {
      if (!pts.has(e.pointerId) || !on()) return;
      pts.set(e.pointerId, [e.clientX, e.clientY]);
      if (pinch && pts.size === 2) {
        const [a, b] = [...pts.values()];
        zoomAt(pinch.s * Math.hypot(a[0] - b[0], a[1] - b[1]) / pinch.d / chart.view.s, ...at((a[0] + b[0]) / 2, (a[1] + b[1]) / 2));
        return;
      }
      if (!drag || drag.id !== e.pointerId) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (!drag.moved) {
        if (Math.hypot(dx, dy) < 4) return;
        drag.moved = true;
        canvas.setPointerCapture(e.pointerId);
        canvas.classList.add('dragging');
      }
      chart.view.x = drag.vx + dx; chart.view.y = drag.vy + dy; chart.view.auto = null;
      clampView(); applyView();
    });
    const end = (e) => {
      if (!pts.delete(e.pointerId)) return;
      if (pts.size < 2) pinch = null;
      if (drag && drag.id === e.pointerId) {
        if (drag.moved && chartLive()) chart.dragged = Date.now();
        drag = null;
        canvas.classList.remove('dragging');
      }
    };
    canvas.addEventListener('pointerup', end);
    canvas.addEventListener('pointercancel', end);
    // the click that ends a drag does not open the organization it started on
    canvas.addEventListener('click', (e) => {
      if (chartLive() && chart.dragged && Date.now() - chart.dragged < 500) { chart.dragged = 0; e.stopPropagation(); e.preventDefault(); }
    }, true);
    canvas.addEventListener('dblclick', (e) => { if (on() && !e.target.closest('.oc-node')) fitChart('all'); });
    canvas.addEventListener('keydown', (e) => {
      if (!on() || e.target !== canvas || e.ctrlKey || e.metaKey || e.altKey) return;
      const step = 60;
      if (e.key === '+' || e.key === '=') zoomBy(1.25);
      else if (e.key === '-' || e.key === '_') zoomBy(1 / 1.25);
      else if (e.key === '0') fitChart('all');
      else if (e.key === 'ArrowLeft') panBy(step, 0);
      else if (e.key === 'ArrowRight') panBy(-step, 0);
      else if (e.key === 'ArrowUp') panBy(0, step);
      else if (e.key === 'ArrowDown') panBy(0, -step);
      else return;
      e.preventDefault();
    });
  }
  async function loadChart() {
    if (!chartLive()) return;
    const c = chart;
    try { c.data = await get('/api/orgchart'); } catch (e) {
      if (!c.data) { c.canvas.textContent = ''; c.canvas.append(h('div', { class: 'empty oc-empty' }, t('chart.load_failed', { error: e.message }))); }
      return;
    }
    if (chart === c) drawChart();
  }
  function reloadChart() {
    if (!chartLive()) return;
    clearTimeout(chart.timer);
    chart.timer = setTimeout(loadChart, 600);
  }
  function redrawChart() {
    if (!chartLive()) return;
    cancelAnimationFrame(chartFrame);
    chartFrame = requestAnimationFrame(drawChart);
  }
  function drawChart() {
    if (!chartLive() || !chart.data) return;
    const { canvas, data } = chart;
    const keep = [canvas.scrollLeft, canvas.scrollTop];
    canvas.textContent = '';
    const orgs = data.orgs.filter((o) => chart.closed.checked || o.status === 'active');
    if (!orgs.length) { canvas.append(h('div', { class: 'empty oc-empty' }, t('chart.empty'))); return; }
    const byId = new Map(orgs.map((o) => [o.id, o]));
    // siblings: the secretariat first, formal organizations before subgroups, open before closed, then oldest first
    const rank = (o) => (o.cabinet ? 0 : 4) + (o.kind === 'subgroup' ? 2 : 0) + (o.status === 'active' ? 0 : 1);
    const kids = new Map();
    for (const o of orgs) {
      const up = o.parent && o.parent !== o.id && byId.has(o.parent) ? o.parent : '';
      if (!kids.has(up)) kids.set(up, []);
      kids.get(up).push(o);
    }
    for (const list of kids.values()) list.sort((a, b) => rank(a) - rank(b));
    const order = [], roots = [], seen = new Set();
    const walk = (o, depth) => {
      if (seen.has(o.id)) return null;
      seen.add(o.id);
      const node = { o, depth, kids: [] };
      order.push(node);
      for (const k of kids.get(o.id) || []) { const child = walk(k, depth + 1); if (child) node.kids.push(child); }
      return node;
    };
    for (const o of (kids.get('') || []).concat(orgs)) { const n = walk(o, 0); if (n) roots.push(n); }  // a loop of parents: drawn as roots
    // sessions in two or more of these organizations: per organization, its members that sit elsewhere too; per pair
    // of organizations, the members whose sessions link them
    const elsewhere = new Map(), pairs = new Map();
    for (const s of data.shared || []) {
      const seats = s.seats.filter((x) => byId.has(x.org));
      if (seats.length < 2) continue;
      for (const x of seats) {
        if (!elsewhere.has(x.org)) elsewhere.set(x.org, []);
        elsewhere.get(x.org).push(t('chart.shared_tip', { member: x.member, orgs: seats.filter((y) => y.org !== x.org).map((y) => byId.get(y.org).name) }));
      }
      for (let i = 0; i < seats.length; i++) {
        for (let j = i + 1; j < seats.length; j++) {
          const [a, b] = [seats[i], seats[j]].sort((p, q) => (p.org < q.org ? -1 : 1));
          const key = a.org + ' ' + b.org;
          if (!pairs.has(key)) pairs.set(key, { a: a.org, b: b.org, tips: [] });
          pairs.get(key).tips.push(t('chart.link_tip', { member: a.member === b.member ? a.member : a.member + ' / ' + b.member, a: byId.get(a.org).name, b: byId.get(b.org).name }));
        }
      }
    }
    // positions: top-down, each leaf in a column of its own and each parent over its children; or listed, indented
    const narrow = canvas.clientWidth < OC.narrow;
    const pos = new Map();
    let width, height;
    if (narrow) {
      order.forEach((n, i) => {
        const x = OC.pad + n.depth * OC.indent;
        pos.set(n.o.id, { x, y: OC.pad + i * (OC.h + 12), w: Math.max(170, canvas.clientWidth - x - OC.pad - OC.bulge) });
      });
      width = Math.max(...[...pos.values()].map((p) => p.x + p.w)) + OC.bulge + OC.pad;
      height = OC.pad * 2 + order.length * (OC.h + 12) - 12;
    } else {
      let slot = 0;
      const place = (n) => {
        let x;
        if (!n.kids.length) { x = slot * (OC.w + OC.gx); slot += 1; }
        else { n.kids.forEach(place); x = (pos.get(n.kids[0].o.id).x + pos.get(n.kids[n.kids.length - 1].o.id).x) / 2; }
        pos.set(n.o.id, { x, y: n.depth * (OC.h + OC.gy), w: OC.w });
      };
      roots.forEach((r, i) => { if (i) slot += 0.4; place(r); });
      const span = slot * (OC.w + OC.gx) - OC.gx;
      const left = OC.pad;  // fitting the view centers it
      for (const p of pos.values()) { p.x += left; p.y += OC.pad; }
      width = left + span + OC.bulge + OC.pad;
      height = OC.pad * 2 + (Math.max(...order.map((n) => n.depth)) + 1) * (OC.h + OC.gy) - OC.gy;
    }
    const plane = h('div', { class: 'oc-plane', style: 'width:' + width + 'px;height:' + height + 'px' });
    const lines = svgEl('svg', { class: 'oc-lines', width, height, viewBox: '0 0 ' + width + ' ' + height });
    plane.append(lines);
    for (const n of order) {  // parent to child: an elbow down from the parent, or along its left edge when listed
      const p = pos.get(n.o.id);
      for (const k of n.kids) {
        const c = pos.get(k.o.id);
        const d = narrow ? 'M' + (p.x + 12) + ',' + (p.y + OC.h) + 'V' + (c.y + OC.h / 2) + 'H' + c.x
          : 'M' + (p.x + OC.w / 2) + ',' + (p.y + OC.h) + 'V' + (p.y + OC.h + OC.gy / 2) + 'H' + (c.x + OC.w / 2) + 'V' + c.y;
        lines.append(svgEl('path', { d, class: 'edge' + (k.o.status === 'active' ? '' : ' ended') }));
      }
    }
    const linkEls = [];
    if (chart.links.checked) {
      for (const pr of pairs.values()) {
        const a = pos.get(pr.a), b = pos.get(pr.b);
        const ay = a.y + OC.h / 2, by = b.y + OC.h / 2;
        let d;
        if (!narrow && Math.abs(a.x - b.x) >= OC.w) {  // side by side: between the edges that face each other
          const [l, r, ly, ry] = a.x < b.x ? [a, b, ay, by] : [b, a, by, ay];
          const x1 = l.x + l.w, x2 = r.x, mid = (x1 + x2) / 2;
          d = 'M' + x1 + ',' + ly + 'C' + mid + ',' + ly + ' ' + mid + ',' + ry + ' ' + x2 + ',' + ry;
        } else {  // one above the other: out of the right edges and back
          const x1 = a.x + a.w, x2 = b.x + b.w, out = Math.max(x1, x2) + OC.bulge * 0.8;
          d = 'M' + x1 + ',' + ay + 'C' + out + ',' + ay + ' ' + out + ',' + by + ' ' + x2 + ',' + by;
        }
        const path = svgEl('path', { d, class: 'link', 'data-a': pr.a, 'data-b': pr.b });
        const tip = svgEl('title');
        tip.textContent = pr.tips.join('\n');
        path.append(tip);
        lines.append(path);
        linkEls.push(path);
      }
    }
    const nodes = new Map();
    const hot = (id, on) => {
      for (const l of linkEls) {
        const a = l.getAttribute('data-a'), b = l.getAttribute('data-b'), mine = a === id || b === id;
        l.classList.toggle('hot', on && mine);
        l.classList.toggle('dim', on && !mine);
        const other = mine ? nodes.get(a === id ? b : a) : null;
        if (other) other.classList.toggle('peer', on);
      }
    };
    for (const n of order) {
      const o = n.o, p = pos.get(o.id), ended = o.status !== 'active';
      const who = o.leader_display || o.leader;
      const lead = o.governance === 'peer' ? t('org.gov_peer') : !o.leader ? t('chart.no_leader')
        : o.cabinet ? t('org.secretary_general_chip', { name: who }) : t('org.leader_chip', { name: who });
      const here = elsewhere.get(o.id) || [];
      const node = h('button', { class: 'oc-node' + (o.kind === 'subgroup' ? ' sub' : '') + (o.cabinet ? ' cab' : '') + (ended ? ' ended' : '') + (o.id === S.orgId ? ' cur' : ''),
        type: 'button', style: 'left:' + p.x + 'px;top:' + p.y + 'px;width:' + p.w + 'px;height:' + OC.h + 'px',
        title: [t('chart.open_hint', { name: o.name }), lead, o.purpose || ''].concat(here).filter(Boolean).join('\n'),
        'aria-current': o.id === S.orgId ? 'true' : null,
        onclick: () => { closeLayer(); if (o.id !== S.orgId) openOrg(o.id); } },
        h('span', { class: 'nm' }, orgBadge(o), h('b', null, o.name),
          o.cabinet ? h('span', { class: 'chip cab' }, t('org.cabinet_chip')) : null,
          o.kind === 'subgroup' ? h('span', { class: 'chip' }, t('org.kind_subgroup')) : null,
          ended ? h('span', { class: 'chip' }, o.status === 'closed' ? t('org.status_closed') : t('org.status_dissolved')) : null),
        h('span', { class: 'ln' }, h('span', null, lead)),
        h('span', { class: 'ln' }, h('span', null, t('common.members', { n: o.members })),
          h('span', { class: 'chip' + (o.decisions ? ' warn' : '') }, t('chart.decisions', { n: o.decisions })),
          here.length ? h('span', { class: 'chip sec' }, t('chart.shared', { n: here.length })) : null));
      node.addEventListener('mouseenter', () => hot(o.id, true));
      node.addEventListener('mouseleave', () => hot(o.id, false));
      node.addEventListener('focus', () => hot(o.id, true));
      node.addEventListener('blur', () => hot(o.id, false));
      nodes.set(o.id, node);
      plane.append(node);
    }
    canvas.append(plane);
    canvas.classList.toggle('pan', !narrow);
    chart.box.classList.toggle('list', narrow);
    if (narrow) {  // listed: scrolled, with the organization it was opened from (or the open one) in view at first
      chart.plane = null;
      if (chart.first) {
        chart.first = false;
        const cur = pos.get(chart.focus || S.orgId);
        if (cur) canvas.scrollTop = Math.max(0, cur.y + OC.h / 2 - canvas.clientHeight / 2);
      } else { canvas.scrollLeft = keep[0]; canvas.scrollTop = keep[1]; }
      return;
    }
    canvas.scrollLeft = 0; canvas.scrollTop = 0;
    const bounds = (list, bulge) => {  // bulge: room on the right for the shared-seat lines that leave the right edges
      const ps = list.map((n) => pos.get(n.o.id));
      const x = Math.min(...ps.map((p) => p.x)), y = Math.min(...ps.map((p) => p.y));
      return { x, y, w: Math.max(...ps.map((p) => p.x + p.w)) - x + bulge, h: Math.max(...ps.map((p) => p.y + OC.h)) - y };
    };
    const below = (n) => [n].concat(...n.kids.map(below));
    const from = chart.focus && order.find((n) => n.o.id === chart.focus);
    chart.plane = plane;
    chart.size = { w: width, h: height };
    chart.allBox = bounds(order, linkEls.length ? OC.bulge * 0.8 : 0);
    chart.focusBox = from ? bounds(below(from), from.kids.length && linkEls.length ? OC.bulge * 0.8 : 0) : null;
    if (!chart.view || chart.view.auto) fitChart(chart.view ? chart.view.auto : 'focus');
    else { clampView(); applyView(); }
    chart.first = false;
  }

  // ------------------------------------------------------------------ window bar (after Codex and Claude Code)
  let installEvent = null, installUI = null;
  const isApp = () => /[?&]source=pwa\b/.test(location.search) || matchMedia('(display-mode: window-controls-overlay)').matches;
  function menus() { return [['file', t('common.file')], ['edit', t('appmenu.edit')], ['view', t('appmenu.view')], ['help', t('appmenu.help')]]; }
  function abBtn(ic, title, onclick, opts = {}) {
    return h('button', { class: 'ab-btn' + (opts.on ? ' on' : '') + (opts.cls ? ' ' + opts.cls : ''), type: 'button', title, 'aria-label': title,
      disabled: opts.disabled ? true : null, onmousedown: (e) => e.preventDefault(), onclick }, icon(ic, 16), opts.badge ? h('span', { class: 'ab-badge' }, opts.badge) : null);
  }
  function renderAppbar() {
    const bar = $('#appbar');
    if (!bar) return;
    bar.textContent = '';
    const v = S.view;
    const title = !S.snap ? 'Relic' : S.snap.org.name + ' · ' + (v.kind === 'group' ? t('common.group_chat') : v.kind === 'secretary' ? t('common.secretary') : dname(v.member));
    const n = S.snap ? S.snap.decisions.length : 0;
    const openBar = menuEl && menuEl.dataset.bar;
    append(bar, [
      h('div', { class: 'ab-left' },
        h('img', { class: 'ab-logo', src: '/static/icon.svg', alt: '' }),
        abBtn('sidebar', S.sideOpen ? t('appbar.hide_sidebar') : t('appbar.show_sidebar'), () => toggleSide()),
        abBtn('back', t('appbar.back'), () => goHist(-1), { disabled: S.histIdx <= 0 }),
        abBtn('fwd', t('appbar.forward'), () => goHist(1), { disabled: S.histIdx >= S.hist.length - 1 }),
        h('nav', { class: 'ab-menus', 'aria-label': t('appbar.menus') }, menus().map(([k, label]) => h('button', { class: 'ab-menu' + (openBar === k ? ' on' : ''), type: 'button', 'data-menu': k,
          onmousedown: (e) => e.preventDefault(), onclick: (e) => openAppMenu(k, e.currentTarget),
          onmouseenter: (e) => { if (menuEl && menuEl.dataset.bar && menuEl.dataset.bar !== k) openAppMenu(k, e.currentTarget); } }, label)))),
      h('div', { class: 'ab-title ellipsis', title }, title),
      h('div', { class: 'ab-right' },
        isApp() ? null : h('button', { class: 'ab-install', type: 'button', title: t('appbar.install_tip'), onmousedown: (e) => e.preventDefault(), onclick: installApp }, icon('download', 14), t('appbar.install')),
        abBtn('bell', n ? t('appbar.decisions', { n }) : t('appbar.no_decisions'), () => { setPane('org'); const b = $('#panel .pane-body'); if (b) b.scrollTop = 0; }, { badge: n || null, cls: n ? 'alert' : '' }),
        abBtn('cc', S.cc.unread ? t('appbar.cc', { n: S.cc.unread }) : t('appbar.cc_none'), openCopies, { badge: S.cc.unread || null, cls: 'ab-cc' }),
        h('span', { class: 'ab-sep' }),
        panes().map(([k, label, ic], i) => abBtn(ic, t('appbar.pane_shortcut', { pane: label, key: 'Alt+' + (i + 1) }), () => (S.panelOpen && S.pane === k ? togglePanel(false) : setPane(k)), { on: S.panelOpen && S.pane === k })))]);
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
      h('span', { class: 'ck' + (opts.icon && !opts.check ? ' ic' : '') }, opts.check ? icon('check', 14) : opts.icon ? icon(opts.icon, 14) : null),
      h('span', { class: 'lb' }, label), opts.key ? h('kbd', null, opts.key) : null);
  }
  const menuSep = () => h('div', { class: 'sep' });
  const toGroup = (fn) => () => { if (S.view.kind !== 'group') go({ kind: 'group' }); fn(); };
  function appMenu(k) {
    const sec = S.snap && secretaryName();
    if (k === 'file') {
      return [menuItem(t('appmenu.new_org'), { run: orgDialog }),
        menuItem(t('appmenu.add_member'), { run: () => memberDialog(), disabled: !S.snap }),
        menuItem(t('appmenu.add_existing'), { run: () => memberDialog({ mode: 'existing' }), disabled: !S.snap }),
        menuItem(sec ? t('appmenu.open_secretary') : t('appmenu.set_up_secretary'), { run: () => (sec ? go({ kind: 'secretary', member: sec }) : openSecretarySetup()), disabled: !S.snap }),
        menuSep(),
        menuItem(t('appmenu.org_details'), { run: () => openDetails('trace'), disabled: !S.snap }),
        menuItem(t('appmenu.open_data'), { run: () => post('/api/open', { what: 'data' }).catch((e) => toast(e.message)) }),
        menuItem(t('appmenu.open_logs'), { run: () => post('/api/open', { what: 'logs' }).catch((e) => toast(e.message)) }),
        menuSep(),
        isApp() ? null : menuItem(t('appmenu.install_app'), { run: installApp }),
        menuItem(t('appmenu.settings'), { key: 'Ctrl+,', run: () => openSettings() })];
    }
    if (k === 'edit') {
      return [menuItem(t('appmenu.undo'), { key: 'Ctrl+Z', run: () => document.execCommand('undo') }),
        menuItem(t('appmenu.redo'), { key: 'Ctrl+Y', run: () => document.execCommand('redo') }),
        menuSep(),
        menuItem(t('appmenu.cut'), { key: 'Ctrl+X', run: () => document.execCommand('cut') }),
        menuItem(t('common.copy'), { key: 'Ctrl+C', run: () => document.execCommand('copy') }),
        menuItem(t('appmenu.paste'), { key: 'Ctrl+V', run: pasteText }),
        menuItem(t('appmenu.select_all'), { key: 'Ctrl+A', run: () => document.execCommand('selectAll') }),
        menuSep(),
        menuItem(t('appmenu.quote_selection'), { run: quoteSelection }),
        menuItem(t('page.search'), { key: 'Ctrl+K', run: focusSearch })];
    }
    if (k === 'view') {
      return [menuItem(t('appmenu.sidebar'), { key: 'Ctrl+B', check: S.sideOpen, run: () => toggleSide() }),
        menuItem(t('page.panel'), { key: 'Ctrl+Alt+B', check: S.panelOpen, run: () => togglePanel() }),
        menuSep(),
        panes().map(([p, label], i) => menuItem(t('appmenu.pane', { pane: label }), { key: 'Alt+' + (i + 1), check: S.panelOpen && S.pane === p, run: () => setPane(p) })),
        menuSep(),
        menuItem(t('appmenu.org_chart'), { run: () => openChart(), disabled: !S.orgs.length }),
        menuSep(),
        menuItem(t('appmenu.plain_group'), { key: 'Ctrl+Shift+L', check: S.plainMode, disabled: !S.snap, run: toGroup(togglePlain) }),
        menuItem(t('appmenu.group_digest'), { check: S.digestOpen, disabled: !S.snap, run: toGroup(toggleDigest) }),
        menuSep(),
        [['system', t('common.theme_system')], ['light', t('common.theme_light')], ['dark', t('common.theme_dark')]].map(([th, label]) => menuItem(t('appmenu.theme', { theme: label }), { check: PREFS.theme === th, run: () => setPrefs({ theme: th }) })),
        [['small', t('common.size_small')], ['medium', t('common.size_medium')], ['large', t('common.size_large')]].map(([f, label]) => menuItem(t('appmenu.font_size', { size: label }), { check: PREFS.font === f, run: () => setPrefs({ font: f }) })),
        menuSep(),
        menuItem(t('appmenu.reload'), { key: 'Ctrl+R', run: () => location.reload() })];
    }
    return [menuItem(t('shortcuts.title'), { run: shortcutsDialog }),
      menuItem(t('common.voice_input'), { run: () => openSettings('voice') }),
      menuItem(t('common.harness'), { run: () => openSettings('harness') }),
      menuSep(),
      menuItem(t('appmenu.about'), { run: () => openSettings('about') })];
  }
  function focusSearch() { if (!S.sideOpen) toggleSide(true); const s = $('#search'); s.focus(); s.select(); }
  async function pasteText() {
    const el = document.activeElement;
    if (!el || !/^(TEXTAREA|INPUT)$/.test(el.tagName)) { toast(t('appmenu.paste_need_field')); return; }
    try { const text = await navigator.clipboard.readText(); el.focus(); document.execCommand('insertText', false, text); } catch (e) { toast(t('appmenu.paste_failed')); }
  }
  function quoteSelection() {
    const sel = window.getSelection();
    const text = sel ? sel.toString().trim() : '';
    if (!text) { toast(t('appmenu.quote_need_selection')); return; }
    const node = sel.anchorNode && (sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement);
    const bubble = node && node.closest('.bubble');
    setQuote(bubble && bubble.dataset.from ? dname(bubble.dataset.from) : t('common.quote'), text);
    sel.removeAllRanges();
  }
  function shortcutsDialog() {
    const rows = [['Ctrl+B', t('shortcuts.toggle_sidebar')], ['Ctrl+Alt+B', t('shortcuts.toggle_panel')], ['Alt+1 / 2 / 3', t('shortcuts.panes')], ['Alt+← / Alt+→', t('shortcuts.back_forward')],
      ['Ctrl+K', t('page.search')], ['Ctrl+Shift+L', t('appmenu.plain_group')], ['Ctrl+,', t('common.settings')], ['Enter / Shift+Enter', t('shortcuts.send_newline')], ['@', t('shortcuts.mention')], ['Esc', t('shortcuts.close')]];
    scrim(h('div', { class: 'dialog', role: 'dialog' }, h('h3', null, t('shortcuts.title')),
      h('dl', { class: 'keys' }, rows.map(([key, what]) => [h('dt', null, h('kbd', null, key)), h('dd', null, what)])),
      h('div', { class: 'acts-row' }, h('button', { class: 'btn primary', type: 'button', onclick: closeLayer }, t('shortcuts.ok')))));
  }
  function shortcut(e) {
    if (e.isComposing) return;
    const ctrl = e.ctrlKey || e.metaKey;
    const k = (e.key || '').toLowerCase();
    let hit = true;
    if (ctrl && e.altKey && !e.shiftKey && k === 'b') togglePanel();
    else if (ctrl && !e.altKey && !e.shiftKey && k === 'b') toggleSide();
    else if (e.altKey && !ctrl && !e.shiftKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) goHist(e.key === 'ArrowLeft' ? -1 : 1);
    else if (e.altKey && !ctrl && !e.shiftKey && /^[123]$/.test(e.key)) { const p = panes()[Number(e.key) - 1][0]; if (S.panelOpen && S.pane === p) togglePanel(false); else setPane(p); }
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
    scrim(h('div', { class: 'dialog', role: 'dialog' }, h('h3', null, t('install.title')),
      h('p', { class: 'lead' }, t('install.lead')),
      h('ol', { class: 'steps' }, h('li', null, t('install.step_open')),
        h('li', null, t('install.step_install')),
        h('li', null, t('install.step_close'))),
      h('div', { class: 'acts-row' }, h('button', { class: 'btn', type: 'button', onclick: closeLayer }, t('install.later')),
        h('button', { class: 'btn primary', type: 'button', onclick: async () => {
          try { await post('/api/install-window', {}); closeLayer(); toast(t('install.window_opened'), 6000); } catch (e) { toast(e.message); }
        } }, t('install.open_in_edge')))));
  }
  function installPage() {
    const btn = h('button', { class: 'btn primary', type: 'button', onclick: installApp }, icon('download', 15), t('install.install_relic'));
    const note = h('div', { class: 'dim', style: 'font-size:12.5px;line-height:1.7' });
    installUI = () => {
      btn.disabled = !installEvent;
      note.textContent = installEvent ? t('install.ready')
        : t('install.waiting');
    };
    installUI();
    scrim(h('div', { class: 'dialog', role: 'dialog' }, h('h3', null, t('install.page_title')),
      h('p', { class: 'lead' }, t('install.page_lead')),
      note, h('div', { class: 'acts-row' }, h('button', { class: 'btn', type: 'button', onclick: closeLayer }, t('common.close')), btn)));
  }

  // ------------------------------------------------------------------ boot
  function wire() {
    $('#btn-new-org').append(icon('neworg', 17), h('span', null, t('common.new_org')));
    $('#btn-new-org').addEventListener('click', orgDialog);
    $('#btn-settings').append(icon('gear', 18));
    $('#btn-settings').addEventListener('click', () => openSettings());
    $('#me').addEventListener('click', () => openSettings('profile'));
    $('#search-icon').append(icon('search', 15));
    const search = $('#search');
    search.addEventListener('input', (e) => { S.search = e.target.value; renderSide(); });
    if (PREFS.voice !== 'off') search.parentElement.append(micButton(search, 'mic'));
    window.addEventListener('resize', () => { closeMention(); closeMenu(); redrawChart(); });
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
      toast(t('install.installed'), 6000);
      renderAppbar();
    });
  }
  (async () => {
    const wantInstall = location.hash === '#install';
    await loadPrefs();
    await loadLang();
    renderMe();
    wire();
    try {
      const wanted = readHash();
      if (wanted && wanted.org !== S.orgId) { S.orgId = wanted.org; S.reveal = wanted.org; }  // a link to another organization shows it
      await loadOrgs();
      if (S.orgId) await openOrg(S.orgId, wanted && wanted.org === S.orgId ? wanted.view : null);
      else renderAll(true);
    } catch (e) {
      $('#stream-inner').append(h('div', { class: 'notice' }, h('span', null, t('boot.load_orgs_failed', { error: e.message }))));
    }
    loadCc().catch(() => {});
    connect();
    if (wantInstall) installPage();
    // a new language reloads the page; Settings opens again where the person was
    let reopen = null;
    try { reopen = sessionStorage.getItem('relic.reopen'); sessionStorage.removeItem('relic.reopen'); } catch (e) { /* none */ }
    if (reopen === 'language') openSettings('language');
  })();
})();
