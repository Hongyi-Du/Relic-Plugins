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
const hook = readFileSync(new URL('./reference-hook.js', import.meta.url), 'utf8');
const plain = value => JSON.parse(JSON.stringify(value));

function environment() {
  const requests = [], events = [], search = {};
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
    loadOrgs: async () => {}, openOrg: async () => {}, save: () => {},
    toggleSide: () => {}, togglePanel: () => {}, renderAll: () => events.push('quick-start'),
    openAppMenu: () => events.push('menu'), $: () => search,
    h: () => ({isConnected: true}), scrim: () => events.push('open-copies'),
    t: key => key, toast: () => events.push('load-error')});
  vm.runInContext('let ccAsked=0, ccBox=null, settingsPane=null;\n' + ccFunctions + '\n' + hook, context);
  return {context, requests, events, S, detail};
}

async function untilRequests(env, count) {
  for (let i=0; i<20 && env.requests.length<count; i++) await Promise.resolve();
  assert.equal(env.requests.length, count);
}

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
