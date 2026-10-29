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
    snapshotTextLayouts: new WeakMap([[node, { source: 'CDP.DOMSnapshot.captureSnapshot', node_index: 136,
      layout_rows: [{ layout_index: 102, bounds: logical, text: node.nodeValue }],
      text_boxes: [{ layout_index: 102, bounds: logical, start: 0, length: node.nodeValue.length }] }]]),
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
  assert.deepEqual(result.range_bounds, { x: 80, y: 263.125, width: 144, height: 16 });
  assert.deepEqual(result.clipped_range_envelope, { x: 80, y: 263.125, width: 144, height: 16 });
  assert.equal(result.glyph_bounds, null);
  assert.deepEqual(result.evidence.raw_bounds, logical);
  assert.deepEqual(result.evidence.raw_rectangles, ranges);
  assert.equal(result.evidence.source_text, node.nodeValue);
  assert.equal(result.evidence.css_ellipsis_active, true);
  assert.equal(result.evidence.geometry_kind, 'unmeasured-painted-ellipsis-with-retained-range-evidence');
  assert.deepEqual(result.range_boxes.map(box => box.width), [144, 131.59375]);
  assert.equal(result.evidence.owner_element_box.width, 144.28125, 'Direct element box is retained separately from rounded client metrics');
  assert.equal(result.evidence.dom_snapshot_layout.text_boxes[0].bounds.width, 459.578125, 'Unclipped CDP layout evidence is not relabeled as glyph paint');
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
    pseudoByOwner: new WeakMap(),
    getComputedStyle: (_owner, pseudo) => ({ display: 'inline', visibility: 'visible', opacity: '1',
      width: '10px', height: '10px', backgroundColor: pseudo.endsWith('-thumb') ? 'rgba(143, 140, 134, 0.35)' : 'rgba(0, 0, 0, 0)' }),
  });
  const result = normalize(read(owner));
  assert.deepEqual(result.axes, ['vertical']);
  assert.equal(result.scroll_height, 1320);
  assert.equal(result.client_width, 329);
  assert.equal(result.scroll_top, 17);
  assert.equal(result.parts.length, 7);
  assert.ok(result.parts.some(part => part.pseudo === '::-webkit-scrollbar-button'));
  assert.ok(result.parts.every(part => part.painted_presence === null && part.painted_bounds === null));
  assert.equal(result.actual_ua_parts_presence, null);
  assert.deepEqual(result.dom_snapshot_parts, []);
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

// Matrix/shape fixtures provide only the API quantities actually read by the
// production function. They do not stand in for browser paint validation.
class SVGElementFixture {
  constructor(children = []) { this.children = children; }
  querySelectorAll() { return this.children; }
}
class SVGGeometryFixture extends SVGElementFixture {
  constructor(style = {}, transform = matrix(1), pathLength = null) {
    super();
    this.style = { display: 'inline', visibility: 'visible', stroke: '#7058b8', strokeOpacity: '1',
      strokeWidth: '1.2px', strokeDasharray: '4px, 3px', strokeDashoffset: '0px', strokeLinecap: 'butt',
      strokeLinejoin: 'miter', strokeMiterlimit: '4', vectorEffect: 'none', ...style };
    this.transform = transform; this.pathLength = pathLength;
  }
  closest() { return null; }
  getScreenCTM() { return this.transform; }
  getAttribute(name) { return name === 'pathLength' ? this.pathLength : null; }
}
function matrix(a, b = 0, c = 0, d = a, e = 0, f = 0) {
  return { a, b, c, d, e, f,
    inverse() {
      const determinant = this.a * this.d - this.b * this.c;
      return matrix(this.d / determinant, -this.b / determinant, -this.c / determinant, this.a / determinant,
        (this.c * this.f - this.d * this.e) / determinant, (this.b * this.e - this.a * this.f) / determinant);
    },
    multiply(other) {
      return matrix(this.a * other.a + this.c * other.b, this.b * other.a + this.d * other.b,
        this.a * other.c + this.c * other.d, this.b * other.c + this.d * other.d,
        this.a * other.e + this.c * other.f + this.e, this.b * other.e + this.d * other.f + this.f);
    },
  };
}
function strokeReader() {
  const errors = [];
  const read = vm.runInNewContext('(' + expression('svgStrokeData', 'styleData') + ')', {
    SVGElement: SVGElementFixture, SVGGeometryElement: SVGGeometryFixture, svgStrokes: new WeakMap(),
    styleOf: shape => shape.style, pathOf: () => '#actual-path', cumulativeOpacity: () => 1,
    color: () => [112, 88, 184, 255], nodeIds: new WeakMap(), unmeasured: errors,
  });
  return { read, errors };
}

test('SVG dash and offset use the actual screen transform and retain source units', () => {
  const { read, errors } = strokeReader();
  const shape = new SVGGeometryFixture({ strokeDashoffset: '-1.5px', strokeLinecap: 'round', strokeLinejoin: 'bevel' }, matrix(2, 0, 0, 2, 50, 70));
  const result = normalize(read(shape));
  assert.equal(result.width, 2.4);
  assert.deepEqual(result.dash, [8, 6]);
  assert.equal(result.dash_offset, -3);
  assert.equal(result.linecap, 'round'); assert.equal(result.linejoin, 'bevel'); assert.equal(result.miterlimit, 4);
  assert.equal(result.shapes[0].source_dash_css, '4px, 3px');
  assert.deepEqual(result.shapes[0].source_dash, [
    { value: 4, unit: 'px', coordinate_space: 'svg-stroke-user-units' },
    { value: 3, unit: 'px', coordinate_space: 'svg-stroke-user-units' },
  ]);
  assert.deepEqual(result.shapes[0].screen_ctm, { a: 2, b: 0, c: 0, d: 2, e: 50, f: 70 });
  assert.equal(result.shapes[0].stroke_to_window_scale, 2);
  assert.deepEqual(errors, []);
});

test('SVG odd dash cycles repeat and all-zero cycles paint as a solid stroke', () => {
  const { read, errors } = strokeReader();
  assert.deepEqual(normalize(read(new SVGGeometryFixture({ strokeDasharray: '5, 3, 2' })).dash), [5, 3, 2, 5, 3, 2]);
  assert.deepEqual(normalize(read(new SVGGeometryFixture({ strokeDasharray: '0px, 0px' })).dash), []);
  assert.deepEqual(normalize(read(new SVGGeometryFixture({ strokeDasharray: 'none' })).dash), []);
  assert.deepEqual(errors, []);
});

test('nonuniform transforms fail dash and width coverage instead of averaging axes', () => {
  const { read, errors } = strokeReader();
  const result = normalize(read(new SVGGeometryFixture({}, matrix(2, 0, 0, 1))));
  assert.equal(result.width, null); assert.equal(result.dash, null); assert.equal(result.dash_offset, null);
  assert.equal(result.linecap, 'butt', 'The measured cap enum is retained independently of unresolved window geometry');
  assert.ok(errors.some(error => error.property === 'style.stroke_width'));
  assert.ok(errors.some(error => error.property === 'style.stroke_dash'));
  assert.ok(errors.some(error => error.property === 'style.stroke_dash_offset'));
  assert.deepEqual(result.shapes[0].screen_ctm, { a: 2, b: 0, c: 0, d: 1, e: 0, f: 0 });
});

test('unresolved percentage and pathLength units remain gaps while measured width survives', () => {
  const first = strokeReader();
  const percentage = normalize(first.read(new SVGGeometryFixture({ strokeDasharray: '4%, 3%', strokeDashoffset: '5%' })));
  assert.equal(percentage.width, 1.2); assert.equal(percentage.dash, null); assert.equal(percentage.dash_offset, null);
  assert.equal(percentage.shapes[0].source_dash_css, '4%, 3%');
  assert.ok(first.errors.some(error => error.property === 'style.stroke_dash'));
  const second = strokeReader();
  const calibrated = normalize(second.read(new SVGGeometryFixture({}, matrix(1), '100')));
  assert.equal(calibrated.width, 1.2); assert.equal(calibrated.dash, null); assert.equal(calibrated.dash_offset, null);
  assert.equal(calibrated.shapes[0].source_path_length_attribute, '100');
  assert.ok(second.errors.some(error => error.property === 'style.stroke_dash_offset'));
});

test('mixed visible child strokes cannot collapse to the first child style', () => {
  const { read, errors } = strokeReader();
  const result = normalize(read(new SVGElementFixture([
    new SVGGeometryFixture(), new SVGGeometryFixture({ strokeDasharray: '1px, 2px', strokeLinecap: 'square' }),
  ])));
  assert.equal(result.width, 1.2); assert.equal(result.dash, null); assert.equal(result.linecap, null);
  assert.equal(result.linejoin, 'miter');
  assert.ok(errors.some(error => error.property === 'style.stroke_dash'));
  assert.ok(errors.some(error => error.property === 'style.stroke_linecap'));
});

test('non-scaling stroke removes measured viewBox mapping but retains actual host CSS scale', () => {
  const { read, errors } = strokeReader();
  const shape = new SVGGeometryFixture({ vectorEffect: 'non-scaling-stroke' }, matrix(60));
  shape.ownerSVGElement = { getScreenCTM: () => matrix(8, 0, 0, 8, 50, 70), getCTM: () => matrix(4), ownerSVGElement: null };
  const result = normalize(read(shape));
  assert.equal(result.width, 2.4); assert.deepEqual(result.dash, [8, 6]);
  assert.deepEqual(result.shapes[0].stroke_to_window, { a: 2, b: 0, c: 0, d: 2, e: 50, f: 70 });
  assert.equal(result.shapes[0].screen_ctm.a, 60, 'Original CTM remains available and is not overwritten');
  assert.deepEqual(errors, []);
});

test('CSS border styles preserve each side and do not invent dashed paint lengths', () => {
  const read = vm.runInNewContext('(' + expression('styleData', 'stateOf') + ')', {
    number: value => Number.parseFloat(value), radius: () => 0, SVGElement: SVGElementFixture,
    color: value => value, pathOf: () => '#real-border', cumulativeOpacity: () => 1,
    shadowData: () => [], backgroundData: () => 'none', svgStrokeData: () => null,
  });
  const style = { fontSize: '14px', fontWeight: '400', color: '#111111', backgroundColor: '#ffffff',
    borderTopWidth: '1px', borderRightWidth: '2px', borderBottomWidth: '0px', borderLeftWidth: '3px',
    borderTopStyle: 'solid', borderRightStyle: 'dashed', borderBottomStyle: 'none', borderLeftStyle: 'double',
    borderTopColor: '#222222', borderRightColor: '#333333', borderBottomColor: '#444444', borderLeftColor: '#555555' };
  const result = normalize(read({}, style, false));
  assert.deepEqual(result.border_styles, ['solid', 'dashed', 'none', 'double']);
  assert.deepEqual(result.border_widths, [1, 2, 0, 3]);
  assert.equal(result.border_dash, undefined, 'CSS dashed does not expose the UA-selected dash/gap lengths');
  assert.equal(result.stroke_dash, null);
});

test('current chart organization is distinct from selection and uses actual aria-current', () => {
  const read = vm.runInNewContext('(' + expression('stateOf', 'iconOf') + ')', { document: { activeElement: null } });
  const chart = value => ({ localName: 'button', classList: { contains: () => false }, hasAttribute: () => false,
    getAttribute: name => name === 'aria-current' ? value : null,
    matches: selector => selector === '.oc-node' || selector.startsWith('button,input'),
  });
  assert.equal(read(chart('true')).current, true);
  assert.equal(read(chart(null)).current, false);
  assert.equal(read(chart('true')).selected, null);
});

function geometryReader() {
  const lineCount = vm.runInNewContext('(' + expression('lineCount', 'inputTextMeasurement') + ')');
  return vm.runInNewContext('(' + expression('textGeometry', 'lineCount') + ')', { lineCount });
}

test('ellipsis projection does not call its clipped envelope measured glyph geometry', () => {
  const read = geometryReader();
  const envelope = { x: 80, y: 263.125, width: 144, height: 16 };
  const result = normalize(read([{ evidence: { css_ellipsis_active: true }, clipped_range_envelope: envelope }], [envelope], 'text', envelope, envelope));
  assert.deepEqual(result.bounds, { x: null, y: null, width: null, height: null });
  assert.deepEqual(result.visible_bounds, { x: null, y: null, width: null, height: null });
  assert.equal(result.text_bounds, null);
  assert.deepEqual(result.clipped_range_envelope, envelope);
  assert.deepEqual(result.text_layout_bounds, [envelope]);
  assert.equal(result.line_count, 1, 'A known single layout line is retained independently of unknown ellipsis glyph extents');
  assert.equal(result.text_bounds_quantity, 'unmeasured-painted-ellipsis-text');
});

test('an ellipsized control keeps its directly measured control box', () => {
  const read = geometryReader();
  const control = { x: 10, y: 20, width: 236, height: 80 };
  const envelope = { x: 48, y: 26, width: 120, height: 17 };
  const result = normalize(read([{ evidence: { css_ellipsis_active: true }, clipped_range_envelope: envelope }], [envelope], 'button', control, control));
  assert.deepEqual(result.bounds, control); assert.deepEqual(result.visible_bounds, control);
  assert.equal(result.text_bounds, null); assert.deepEqual(result.clipped_range_envelope, envelope);
});

test('plain text retains measured advance rectangles without claiming glyph ink', () => {
  const read = geometryReader();
  const bounds = { x: 10, y: 20, width: 80, height: 17 };
  const result = normalize(read([{ evidence: { css_ellipsis_active: false }, clipped_range_envelope: bounds }], [bounds], 'text', bounds, bounds));
  assert.deepEqual(result.bounds, bounds); assert.deepEqual(result.text_bounds, [bounds]);
  assert.equal(result.text_bounds_quantity, 'font-metric-text-advance-range');
  assert.equal(result.unknown_ellipsis, false);
});

test('unresolved multiline ellipsis does not invent an actual painted line count', () => {
  const read = geometryReader();
  const boxes = [{ x: 10, y: 20, width: 80, height: 17 }, { x: 10, y: 40, width: 80, height: 17 }];
  const result = normalize(read([{ evidence: { css_ellipsis_active: true }, clipped_range_envelope: boxes[0] }], boxes, 'text', boxes[0], boxes[0]));
  assert.equal(result.line_count, null); assert.equal(result.line_count_source, null);
  assert.deepEqual(result.text_layout_bounds, boxes); assert.equal(result.text_bounds, null);
});

test('inline child text retains an ancestor ellipsis coverage gap', () => {
  const owner = element({ x: 10, y: 20, width: 150, height: 17 });
  const block = element({ x: 10, y: 20, width: 80, height: 17 }, { clientWidth: 80, scrollWidth: 150 });
  block.style = { ...block.style, overflowX: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' };
  owner.parentElement = block;
  const node = { parentElement: owner, nodeValue: 'Actual longer inline label' };
  const logical = { x: 10, y: 20, width: 150, height: 17 };
  const read = vm.runInNewContext('(' + expression('textMeasurement', 'textNodes') + ')', {
    ...context, visibleRect, measuredText: new WeakMap(), snapshotBackend: new WeakMap(), snapshotTextLayouts: new WeakMap(),
    axByBackend: new Map(), axById: new Map(), pathOf: value => value === block ? '#real-block' : '#real-inline', rect: box => ({ ...box }),
    document: { createRange: () => ({ selectNodeContents() {}, getBoundingClientRect: () => logical, getClientRects: () => [logical] }) },
  });
  const result = normalize(read(node));
  assert.equal(result.evidence.css_ellipsis_active, true);
  assert.equal(result.evidence.ellipsis_overflow_owners[0].selector, '#real-block');
  assert.equal(result.evidence.ellipsis_overflow_owners[0].direct_owner, false);
  assert.equal(result.clipped_range_envelope.width, 80);
  assert.equal(result.glyph_bounds, null);
});

test('zero scrollbar gutter is not proof that overlay scrollbars are absent', () => {
  const owner = element({ x: 10, y: 20, width: 200, height: 300 }, { offsetWidth: 200, clientWidth: 200, offsetHeight: 300, clientHeight: 300, scrollHeight: 900 });
  owner.style = { ...owner.style, overflowY: 'auto', scrollbarWidth: 'auto', direction: 'ltr', writingMode: 'horizontal-tb' };
  const read = vm.runInNewContext('(' + expression('scrollbarEvidence', 'all') + ')', {
    styleOf: context.styleOf, rect: box => ({ ...box }), pseudoByOwner: new WeakMap(),
    getComputedStyle: () => ({ display: 'inline', visibility: 'visible', opacity: '1', width: '10px', height: '10px' }),
  });
  const result = normalize(read(owner));
  assert.deepEqual(result.axes, ['vertical']); assert.equal(result.offset_width - result.client_width, 0);
  assert.equal(result.actual_ua_parts_presence, null); assert.equal(result.measured_part_bounds, null);
  assert.equal(result.measured_part_pixels, null);
});
