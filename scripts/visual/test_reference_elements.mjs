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
    ...context, visibleRect, measuredText: new WeakMap(), snapshotBackend: new WeakMap([[node, 144]]),
    axByBackend: new Map([[144, [{ childIds: ['original', 'prefix', 'ellipsis'] }]]]),
    axById: new Map([
      ['original', { nodeId: 'original', parentId: '144', ignored: false, role: { value: 'InlineTextBox' }, name: { value: node.nodeValue } }],
      ['prefix', { nodeId: 'prefix', parentId: '144', ignored: false, role: { value: 'InlineTextBox' }, name: { value: "Designer: I'll check all " } }],
      ['ellipsis', { nodeId: 'ellipsis', parentId: '144', ignored: false, role: { value: 'InlineTextBox' }, name: { value: '…' } }],
    ]),
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
  assert.deepEqual(result.evidence.ax_inline_text_boxes.map(box => box.name), [node.nodeValue, "Designer: I'll check all ", '…']);
  assert.ok(result.evidence.ax_inline_text_boxes.every(box => box.bounds === null), 'AX names never stand in for actual glyph coordinates');
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

test('actual PostScript identity preserves localized family evidence without aliasing', () => {
  const identity = vm.runInNewContext('(' + expression('platformFontIdentity', 'fontRequestEvidence') + ')');
  const actual = normalize(identity({ familyName: '蘋方-簡', postScriptName: 'PingFangSC-Semibold', isCustomFont: false, glyphCount: 10 }));
  assert.equal(actual.family_name, '蘋方-簡');
  assert.equal(actual.postscript_name, 'PingFangSC-Semibold');
  assert.equal(actual.is_custom_font, false);
  assert.equal(actual.identity_source, 'CDP.CSS.getPlatformFontsForNode.postScriptName');
  assert.equal(actual.font_weight, undefined, 'A Semibold name does not prove a numeric resolved weight');
  assert.equal(normalize(identity({ familyName: 'Other', postScriptName: 'DifferentFace-Regular' })).postscript_name, 'DifferentFace-Regular');
});

test('requested weight and variation settings stay distinct from resolved faces', () => {
  const request = vm.runInNewContext('(' + expression('fontRequestEvidence', 'platformFonts') + ')', {
    number: value => Number.isFinite(parseFloat(value)) ? parseFloat(value) : null,
  });
  const actual = normalize(request({ fontWeight: '550', fontVariationSettings: '"wght" 575, "wdth" 90', fontStyle: 'oblique 12deg', fontStretch: '90%' }));
  assert.equal(actual.weight, 550);
  assert.equal(actual.weight_css, '550');
  assert.equal(actual.variation_settings, '"wght" 575, "wdth" 90');
  assert.equal(actual.style, 'oblique 12deg');
  assert.equal(actual.stretch, '90%');
  assert.equal(actual.resolved_numeric_weight, undefined, 'A computed request must not become a measured resolved axis');
  assert.equal(request({ fontWeight: 'bold', fontVariationSettings: 'normal', fontStyle: 'normal', fontStretch: 'normal' }).weight, 700);
  assert.equal(request({ fontWeight: 'normal', fontVariationSettings: 'normal', fontStyle: 'normal', fontStretch: 'normal' }).weight, 400);
});
