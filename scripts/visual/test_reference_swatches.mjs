// CI-only pure fixtures for the real reference state extractor and preference flow.
// No browser/server is started, and no native/reference expected state is copied.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const collector = readFileSync(new URL('./reference-elements.js', import.meta.url), 'utf8');
const app = readFileSync(new URL('../../plugins/relic/app/static/app.js', import.meta.url), 'utf8');
const between = (source, startText, endText) => {
  const start = source.indexOf(startText), end = source.indexOf(endText, start);
  assert.ok(start >= 0 && end > start, 'Use actual production source');
  return source.slice(start, end);
};
const stateSource = between(collector, '  const stateOf = ', '  const iconOf = ');
const appearanceSource = between(app, '  function drawAppearance(pane) {', '  function drawLanguage(pane) {');
const preferenceSource = between(app, '  async function setPrefs(changes) {', '\n  // ------------------------------------------------------------------ language');
const redrawSource = between(app, '  function redraw() {', '  function drawProfile(pane) {');
const legendSource = between(app, '    const swatch = ', '    const tool = ');

// Small independent DOM fixture: matching is based on tag/class/parent/attribute
// relationships, never on the extractor's whole selector string or its result.
function h(tag, attributes = {}, ...children) {
  const attrs = attributes || {};
  const node = {
    localName: tag, attrs, children: [], parentElement: null,
    getAttribute: name => attrs[name] ?? null,
    hasAttribute: name => Object.hasOwn(attrs, name),
    classList: { contains: value => (attrs.class || '').split(/\s+/).includes(value) },
    querySelector: () => null,
    append(...items) {
      for (const child of items.flat(Infinity).filter(item => item != null)) {
        if (typeof child === 'object') child.parentElement = this;
        this.children.push(child);
      }
    },
    matches(selectors) {
      return selectors.split(',').some(selector => {
        const parts = selector.trim().split('>').map(part => part.trim());
        if (parts.length > 1) return this.matches(parts.at(-1)) && !!this.parentElement?.matches(parts.slice(0, -1).join('>'));
        const simple = parts[0];
        if (simple === ':hover') return false;
        if (simple === ':disabled') return attrs.disabled === true;
        const match = /^([a-z][\w-]*)?((?:\.[\w-]+)*)(?:\[([\w-]+)(?:=([^\]]+))?\])?$/.exec(simple);
        if (!match || (!match[1] && !match[2] && !match[3])) return false;
        return (!match[1] || match[1] === tag)
          && match[2].split('.').filter(Boolean).every(value => this.classList.contains(value))
          && (!match[3] || this.hasAttribute(match[3]) && (match[4] == null || String(attrs[match[3]]) === match[4]));
      });
    },
  };
  node.append(children);
  return node;
}

const readState = vm.runInNewContext(stateSource + '\nstateOf;', {
  document: { activeElement: null }, panelResizeEvidence: () => null,
});

function appearance(accent = 'clay') {
  const pane = h('div'), writes = [], applied = [];
  const prefs = { accent, theme: 'light', font: 'medium', density: 'comfortable' };
  const context = vm.createContext({ PREFS: prefs, h, t: key => key,
    segControl: () => h('div'), setRow: (title, hint, control) => h('div', {}, control),
    applyPrefs: () => applied.push({ ...prefs }),
    post: async (path, changes) => { writes.push({ path, changes: { ...changes } }); return changes; },
    toast: message => { throw new Error(message); },
    settingsPane: { draw: () => { pane.children = []; context.drawAppearance(pane); } },
  });
  vm.runInContext(preferenceSource + appearanceSource + redrawSource, context);
  context.redraw();
  const swatches = () => pane.children.flatMap(row => typeof row === 'object' ? row.children : [])
    .filter(node => typeof node === 'object' && node.classList.contains('swatches'))[0].children;
  return { prefs, writes, applied, swatches };
}

test('recorded 312dab7 settings swatch classes expose selected and unselected states', () => {
  // Actual settings-appearance DOM metadata: dom-537 clay "swatch on",
  // dom-538..542 ink/indigo/blue/rose/amber "swatch". Old selected was null.
  const names = ['clay', 'ink', 'indigo', 'blue', 'rose', 'amber'];
  const group = h('div', { class: 'swatches' }, names.map((name, index) =>
    h('button', { class: index === 0 ? 'swatch on' : 'swatch', title: name, type: 'button' })));
  assert.deepEqual(group.children.map(node => readState(node).selected), [true, false, false, false, false, false]);
  assert.ok(group.children.every(node => readState(node).enabled === true));
  assert.ok(group.children.every(node => readState(node).checked === null));
  assert.equal(group.children[0].attrs.class, 'swatch on');
});

test('the real appearance click updates PREFS, persists it and redraws the selected swatch', async () => {
  const env = appearance();
  assert.deepEqual(env.swatches().filter(node => readState(node).selected).map(node => node.attrs.title), ['clay']);
  env.swatches().find(node => node.attrs.title === 'indigo').attrs.onclick();
  await Promise.resolve();
  assert.equal(env.prefs.accent, 'indigo');
  assert.deepEqual(env.writes, [{ path: '/api/prefs', changes: { accent: 'indigo' } }]);
  assert.equal(env.applied[0].accent, 'indigo');
  assert.deepEqual(env.swatches().map(node => readState(node).selected), [false, false, true, false, false, false]);
  env.swatches().find(node => node.attrs.title === 'rose').attrs.onclick();
  await Promise.resolve();
  assert.deepEqual(env.swatches().filter(node => readState(node).selected).map(node => node.attrs.title), ['rose']);
});

test('unknown accent remains unselected instead of inventing a default selection', () => {
  const env = appearance('unrecognized-preference');
  assert.ok(env.swatches().every(node => readState(node).selected === false));
  assert.equal(env.prefs.accent, 'unrecognized-preference');
});

test('real chart legend swatches and unrelated on classes remain nonselectable', () => {
  const chartSwatch = vm.runInNewContext(legendSource + '\nswatch;', { h });
  const legend = h('div', { class: 'oc-legend' }, ['', 'sub', 'cab', 'ended', 'link'].map(cls => chartSwatch(cls, cls)));
  for (const row of legend.children) {
    assert.equal(readState(row).selected, null);
    assert.equal(readState(row.children[0]).selected, null);
  }
  const outside = h('button', { class: 'swatch on' });
  assert.equal(readState(outside).selected, null);
  const unrelated = h('div', { class: 'swatches' }, h('button', { class: 'on' }), h('span', { class: 'swatch on' }));
  assert.ok(unrelated.children.every(node => readState(node).selected === null));
});

test('swatch tests are wired into the existing CI entrypoint', () => {
  const main = readFileSync(new URL('./test_reference_elements.mjs', import.meta.url), 'utf8');
  assert.match(main, /import '\.\/test_reference_swatches\.mjs'/);
});
