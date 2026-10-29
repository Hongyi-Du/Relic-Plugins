// CI-only pure fixtures for the production extractor's clipping functions.
// This imports no browser, launches no process, and uses recorded DOM metrics.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('./reference-elements.js', import.meta.url), 'utf8');
const expression = (name, next) => {
  const start = source.indexOf('  const ' + name + ' = ');
  const end = source.indexOf('  const ' + next + ' = ', start);
  assert.ok(start >= 0 && end > start, 'Use the real production function, never a copied test implementation');
  return source.slice(start + ('  const ' + name + ' = ').length, end).trim().replace(/;$/, '');
};
const intersect = (a, b) => {
  const x = Math.max(a.x, b.x), y = Math.max(a.y, b.y);
  return { x, y, width: Math.max(0, Math.min(a.x + a.width, b.x + b.width) - x),
    height: Math.max(0, Math.min(a.y + a.height, b.y + b.height) - y) };
};
const normalize = value => JSON.parse(JSON.stringify(value));
const context = {
  innerWidth: 1440, innerHeight: 900, intersect,
  nonempty: box => box.width > 0 && box.height > 0,
  styleOf: element => element.style,
};
const visibleRect = vm.runInNewContext('(' + expression('visibleRect', 'visibleText') + ')', context);
const element = (bounds, values = {}) => ({
  getBoundingClientRect: () => bounds,
  clientWidth: bounds.width, clientHeight: bounds.height, clientLeft: 0, clientTop: 0,
  scrollWidth: bounds.width, scrollHeight: bounds.height, hidden: false, parentElement: null,
  style: { display: 'block', visibility: 'visible', opacity: '1', overflowX: 'visible', overflowY: 'visible',
    textOverflow: 'clip', webkitLineClamp: 'none' }, ...values,
});

test('text clips at its own ellipsis scrollport, not only the wider ancestor', () => {
  const ancestor = element({ x: 80, y: 0, width: 195, height: 900 });
  ancestor.style.overflowX = 'hidden';
  const owner = element({ x: 80, y: 263.125, width: 144.28125, height: 16.1875 }, {
    parentElement: ancestor, clientWidth: 144, clientHeight: 16, scrollWidth: 460,
  });
  owner.style = { ...owner.style, overflowX: 'hidden', overflowY: 'hidden', textOverflow: 'ellipsis' };
  const logical = { x: 80, y: 262.125, width: 459.578125, height: 17 };
  assert.deepEqual(normalize(visibleRect(owner, logical, true)), { x: 80, y: 263.125, width: 144, height: 16 });
  assert.equal(visibleRect(owner, logical).width, 195, 'Element paint and its own text content use distinct clipping rules');
});

test('own horizontal clipping does not invent a vertical clip', () => {
  const owner = element({ x: 10, y: 30, width: 80, height: 16 });
  owner.style.overflowX = 'hidden';
  assert.deepEqual(normalize(visibleRect(owner, { x: 10, y: 28, width: 200, height: 20 }, true)),
    { x: 10, y: 28, width: 80, height: 20 });
});

test('fully clipped text stays absent while partial text retains its measured extent', () => {
  const owner = element({ x: 10, y: 30, width: 80, height: 16 });
  owner.style.overflowX = 'hidden';
  assert.equal(visibleRect(owner, { x: 95, y: 30, width: 100, height: 16 }, true), null);
  assert.deepEqual(normalize(visibleRect(owner, { x: 85, y: 30, width: 100, height: 16 }, true)),
    { x: 85, y: 30, width: 5, height: 16 });
});

test('ellipsis evidence preserves both original ranges and unresolved generated-glyph geometry', () => {
  const owner = element({ x: 80, y: 263.125, width: 144.28125, height: 16.1875 }, {
    clientWidth: 144, clientHeight: 16, scrollWidth: 460,
  });
  owner.style = { ...owner.style, overflowX: 'hidden', overflowY: 'hidden', textOverflow: 'ellipsis' };
  const node = { parentElement: owner, nodeValue: "Designer: I'll check all three window sizes." };
  const logical = { x: 80, y: 262.125, width: 459.578125, height: 17 };
  const ranges = [logical, { x: 80, y: 262.125, width: 131.59375, height: 17 }];
  const measure = vm.runInNewContext('(' + expression('textMeasurement', 'textNodes') + ')', {
    ...context, visibleRect, measuredText: new WeakMap(), snapshotBackend: new WeakMap(),
    pathOf: () => '#actual-owner', rect: box => ({ ...box }),
    document: { createRange: () => ({ selectNodeContents() {}, getBoundingClientRect: () => logical, getClientRects: () => ranges }) },
  });
  const result = normalize(measure(node));
  assert.deepEqual(result.bounds, { x: 80, y: 263.125, width: 144, height: 16 });
  assert.deepEqual(result.evidence.raw_bounds, logical);
  assert.deepEqual(result.evidence.raw_rectangles, ranges);
  assert.equal(result.evidence.source_text, node.nodeValue);
  assert.equal(result.evidence.css_ellipsis_active, true);
  assert.equal(result.evidence.geometry_kind, 'clipped-range-envelope-with-unresolved-ellipsis-ink');
  assert.deepEqual(result.boxes.map(box => box.width), [144, 131.59375]);
});

test('overflow scrollbar evidence retains actual metrics without inventing thumb bounds', () => {
  const owner = element({ x: 1100, y: 84, width: 340, height: 816 }, {
    clientWidth: 329, clientHeight: 816, scrollHeight: 1320, scrollTop: 17,
    offsetWidth: 340, offsetHeight: 816, scrollLeft: 0,
  });
  owner.style = { ...owner.style, overflowY: 'auto', scrollbarWidth: 'auto' };
  const read = vm.runInNewContext('(' + expression('scrollbarEvidence', 'all') + ')', {
    styleOf: context.styleOf, rect: box => ({ ...box }),
    getComputedStyle: (_owner, pseudo) => ({ display: 'inline', visibility: 'visible', opacity: '1',
      width: '10px', height: '10px', backgroundColor: pseudo.endsWith('-thumb') ? 'rgba(143, 140, 134, 0.35)' : 'rgba(0, 0, 0, 0)' }),
  });
  const result = normalize(read(owner));
  assert.deepEqual(result.axes, ['vertical']);
  assert.equal(result.scroll_height, 1320);
  assert.equal(result.client_width, 329);
  assert.equal(result.scroll_top, 17);
  assert.equal(result.parts.length, 4);
  assert.equal(result.measured_part_bounds, null);
  assert.equal(result.measured_part_pixels, null);
  owner.style.scrollbarWidth = 'none';
  assert.equal(read(owner), null, 'An explicitly hidden scrollbar has no painted element');
});
