// CI-only pure async/control fixtures. Executes the real hook and production
// loadCc/openCopies source without a browser, HTTP request or application.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const app = readFileSync(new URL('../../plugins/relic/app/static/app.js', import.meta.url), 'utf8');
const start = app.indexOf('  async function loadCc() {');
const end = app.indexOf('  function drawCopies() {', start);
assert.ok(start >= 0 && end > start);
const ccFunctions = app.slice(start, end);
const digestStart = app.indexOf('  function toggleDigest() {');
const digestEnd = app.indexOf('  async function loadDigest(', digestStart);
assert.ok(digestStart >= 0 && digestEnd > digestStart);
const digestFunction = app.slice(digestStart, digestEnd);
const hook = readFileSync(new URL('./reference-hook.js', import.meta.url), 'utf8');
const capture = readFileSync(new URL('./capture.py', import.meta.url), 'utf8');
const bootReadiness = capture.match(/REFERENCE_BOOT_READY = """([\s\S]*?)"""/)?.[1];
assert.ok(bootReadiness, 'The actual shared capture readiness expression is available');
const plain = value => JSON.parse(JSON.stringify(value));
const bootReady = env => vm.runInContext('(' + bootReadiness + ')()', env.context);

function environment() {
  const requests = [], events = [], search = {}, digestViews = [], saved = [];
  let tick = 0;
  const detail = {open: false, querySelector: selector => {
    assert.equal(selector, 'summary');
    return {click: () => {detail.open = true; events.push('expand-rule');}};
  }};
  const S = {cc: {items: [], unread: 0, loaded: false}, folded: new Set()};
  const context = vm.createContext({S, PREFS: {notify: false}, window: {innerWidth: 1440},
    performance: {now: () => ++tick}, document: {hidden: false,
      querySelector: () => ({}), querySelectorAll: () => [detail]},
    get: path => {
      assert.equal(path, '/api/cc');
      return new Promise((resolve, reject) => requests.push({resolve, reject}));
    }, renderAppbar: () => events.push('appbar'), drawCopies: () => events.push('copies'),
    closeLayer: () => {}, closeCard: () => {}, closeMenu: () => {}, closeMention: () => {},
    loadOrgs: async () => {}, openOrg: async org => { S.orgId = org; }, save: (key, value) => saved.push({key, value}),
    renderHead: () => digestViews.push({view: 'head', open: S.digestOpen}),
    renderBanner: () => digestViews.push({view: 'banner', open: S.digestOpen, digest: S.digest}),
    loadDigest: () => { throw new Error('A seeded digest must not request replacement content'); },
    toggleSide: () => {}, togglePanel: () => {}, renderAll: () => events.push('quick-start'),
    openAppMenu: () => events.push('menu'), $: () => search,
    h: () => ({isConnected: true}), scrim: () => events.push('open-copies'),
    t: key => key, toast: () => events.push('load-error')});
  vm.runInContext('let ccAsked=0, ccBox=null, settingsPane=null;\n' + ccFunctions + '\n' + digestFunction + '\n' + hook, context);
  return {context, requests, events, S, detail, digestViews, saved};
}

async function untilRequests(env, count) {
  for (let i=0; i<20 && env.requests.length<count; i++) await Promise.resolve();
  assert.equal(env.requests.length, count);
}

test('digest capture opens the seeded card and updates its header through the production toggle', async () => {
  const env = environment();
  const digest = {text: 'Deterministic digest fixture', count: 3, last_id: 17};
  const pending = env.context.window.__relicVisual('digest', {org: 'fixture-org', digest});
  await untilRequests(env, 1);
  env.requests[0].resolve({items: [], unread: 0});
  await pending;
  assert.equal(env.S.digestOpen, true);
  assert.equal(env.S.digest, digest);
  assert.deepEqual(plain(env.digestViews), [
    {view: 'head', open: true}, {view: 'banner', open: true, digest},
  ]);
  assert.ok(env.saved.some(row => row.key === 'relic.digest.fixture-org' && row.value === true));
});

test('scene controls wait for production CC and keep the server total, not unread item count', async () => {
  for (const scene of ['menu-file', 'quick-start']) {
    const env = environment();
    const pending = env.context.window.__relicVisual(scene, {org: 'fixture-org'});
    await untilRequests(env, 1);
    assert.deepEqual(env.events, []);
    const payload = {items: [{id: 17, read: false}], unread: 5};
    env.requests[0].resolve(payload);
    await pending;
    assert.deepEqual(env.events, ['appbar', scene === 'quick-start' ? 'quick-start' : 'menu']);
    assert.deepEqual(plain(env.S.cc), {...payload, loaded: true});
    const state = env.context.window.__relicVisualCcState;
    assert.equal(state.loads[0].stage, 'before-scene-controls');
    assert.equal(state.loads[0].status, 'ready');
    assert.equal(state.asked, 1);
    state.cc.unread = 0; state.loads[0].status = 'invented';
    assert.equal(env.context.window.__relicVisualCcState.cc.unread, 5);
    assert.equal(env.context.window.__relicVisualCcState.loads[0].status, 'ready');
    assert.equal(Object.getOwnPropertyDescriptor(env.context.window, '__relicVisualCcState').set, undefined);
  }
});

test('a superseding production request cannot be mistaken for completion of the awaited call', async () => {
  const env = environment();
  const first = env.context.visualLoadCc('before-scene-controls');
  const rejected = assert.rejects(first, /superseded/);
  const newer = env.context.loadCc();
  env.requests[1].resolve({items: [], unread: 3});
  await newer;
  env.requests[0].resolve({items: [], unread: 1});
  await rejected;
  assert.equal(env.context.window.__relicVisualCcState.loads[0].status, 'failed');
  assert.equal(env.S.cc.unread, 3);
});

test('an older startup response retains the production stale-response guard', async () => {
  const env = environment();
  const startup = env.context.loadCc();
  const ready = env.context.visualLoadCc('before-scene-controls');
  env.requests[1].resolve({items: [], unread: 4});
  await ready;
  env.requests[0].resolve({items: [], unread: 0});
  await startup;
  assert.equal(env.S.cc.unread, 4);
  assert.equal(env.context.window.__relicVisualCcState.loads[0].status, 'ready');
  assert.deepEqual(env.events, ['appbar']);
});

test('copy rules wait for the latest real load before operating their summary controls', async () => {
  const env = environment();
  const pending = env.context.window.__relicVisual('copy-rules', {org: 'fixture-org'});
  await untilRequests(env, 1);
  env.requests[0].resolve({items: [], unread: 1});
  await untilRequests(env, 3); // openCopies' real fire-and-forget load plus the awaited load.
  assert.equal(env.detail.open, false);
  env.requests[2].resolve({items: [{id: 7, read: false}], unread: 2});
  await pending;
  assert.equal(env.detail.open, true);
  assert.equal(env.events.at(-1), 'expand-rule');
  assert.equal(env.context.window.__relicVisualCcState.loads[1].stage, 'after-open-copies');
  env.requests[1].resolve({items: [], unread: 0});
  await Promise.resolve(); await Promise.resolve();
  assert.equal(env.S.cc.unread, 2);
});

test('load failures remain failures and cannot write loaded or unread fixture values', async () => {
  const env = environment();
  const pending = env.context.visualLoadCc('before-scene-controls');
  const rejected = assert.rejects(pending, /actual response failed/);
  env.requests[0].reject(new Error('actual response failed'));
  await rejected;
  assert.deepEqual(plain(env.S.cc), {items: [], unread: 0, loaded: false});
  assert.equal(env.context.window.__relicVisualCcState.loads[0].status, 'failed');
});

test('rendered stream cannot start scene controls before the real startup CC response', async () => {
  const env = environment();
  env.context.document.querySelector = () => ({children: [{}]});
  assert.equal(bootReady(env), false); // openOrg has rendered, boot loadCc has not started.
  const startup = env.context.loadCc();
  assert.equal(bootReady(env), false); // the real request is still pending.
  assert.equal(env.requests.length, 1);
  assert.equal(env.context.window.__relicVisualCcState.loads.length, 0);
  env.requests[0].resolve({items: [{id: 17, read: false}], unread: 5});
  await startup;
  assert.equal(bootReady(env), true);
  const scene = env.context.window.__relicVisual('menu-file', {org: 'fixture-org'});
  await untilRequests(env, 2);
  assert.deepEqual(env.events, ['appbar']);
  env.requests[1].resolve({items: [{id: 17, read: false}], unread: 5});
  await scene;
  assert.deepEqual(env.events, ['appbar', 'appbar', 'menu']);
  const load = env.context.window.__relicVisualCcState.loads[0];
  assert.equal(load.before.asked, 1);
  assert.equal(load.request_asked, 2);
  assert.equal(load.status, 'ready');
});

test('startup CC failure cannot satisfy readiness or trigger a replacement request', async () => {
  const env = environment();
  env.context.document.querySelector = () => ({children: [{}]});
  const startup = env.context.loadCc();
  const rejected = assert.rejects(startup, /actual startup failure/);
  env.requests[0].reject(new Error('actual startup failure'));
  await rejected;
  assert.equal(bootReady(env), false);
  assert.equal(env.requests.length, 1);
  assert.deepEqual(env.events, []);
  assert.equal(env.context.window.__relicVisualCcState.loads.length, 0);
});

test('boot readiness still requires the real rendered stream and valid measured CC total', async () => {
  for (const unread of [2, true, -1]) {
    const env = environment();
    let children = [];
    env.context.document.querySelector = () => ({children});
    const startup = env.context.loadCc();
    env.requests[0].resolve({items: [], unread});
    await startup;
    assert.equal(bootReady(env), false);
    children = [{}];
    assert.equal(bootReady(env), unread === 2);
    assert.equal(env.requests.length, 1);
    assert.deepEqual(plain(env.S.cc), {items: [], unread, loaded: true});
  }
});
