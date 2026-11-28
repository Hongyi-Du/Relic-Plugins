// CI-only pure fixtures for the production extractor's clipping functions.
// This imports no browser, launches no process, and uses recorded DOM metrics.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import './test_reference_colors.mjs';
import './test_reference_cc.mjs';
import './test_reference_markers.mjs';
import './test_reference_swatches.mjs';

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
const readingOrderIds = vm.runInNewContext('(' + expression('readingOrderIds', 'assignReadingOrder') + ')', {
  Node: { ELEMENT_NODE: 1, TEXT_NODE: 3 },
});
const assignReadingOrder = vm.runInNewContext('(' + expression('assignReadingOrder', 'all') + ')');
const readingElement = (...children) => ({ nodeType: 1, childNodes: children });
const readingText = () => ({ nodeType: 3 });
const recordedPseudo = JSON.parse(readFileSync(new URL('./fixtures/pseudo_file_code_recorded.json', import.meta.url), 'utf8'));
const cssLineBreakConfiguration = vm.runInNewContext('(' + expression('cssLineBreakConfiguration', 'imageResourceEvidence') + ')');
const cssBreakStyle = changes => ({ whiteSpace: 'normal', textWrapMode: 'wrap', textWrapStyle: 'wrap', wordBreak: 'normal',
  overflowWrap: 'normal', lineBreak: 'auto', hyphens: 'manual', direction: 'ltr', writingMode: 'horizontal-tb', ...changes });

test('normal CSS wrapping and emergency anywhere wrapping are independent actual policies', () => {
  const normal = normalize(cssLineBreakConfiguration(cssBreakStyle(), true, 'actual-text-parent'));
  const emergency = normalize(cssLineBreakConfiguration(cssBreakStyle({ overflowWrap: 'anywhere' }), true, 'actual-text-parent'));
  assert.equal(normal.layout.normal_break_strategy, 'word');
  assert.equal(normal.layout.emergency_break_strategy, 'none');
  assert.equal(emergency.layout.normal_break_strategy, 'word');
  assert.equal(emergency.layout.emergency_break_strategy, 'break-unbreakable');
  assert.equal(emergency.evidence.raw.overflowWrap, 'anywhere');
  assert.equal(emergency.evidence.owner, 'actual-text-parent');
  assert.deepEqual(emergency.evidence.errors, []);
});

test('CSS break-all is not conflated with emergency wrapping or native byCharWrapping', () => {
  const result = normalize(cssLineBreakConfiguration(cssBreakStyle({ wordBreak: 'break-all' }), true, 'path'));
  assert.equal(result.layout.normal_break_strategy, 'break-all');
  assert.equal(result.layout.emergency_break_strategy, 'none');
  assert.notEqual(result.layout.normal_break_strategy, 'character');
});

test('nowrap and pre disable soft breaks while retaining the inherited emergency request', () => {
  for (const whiteSpace of ['nowrap', 'pre']) {
    const result = normalize(cssLineBreakConfiguration(cssBreakStyle({ whiteSpace, textWrapMode: 'nowrap', overflowWrap: 'anywhere' }), true, 'label'));
    assert.equal(result.layout.normal_break_strategy, 'none');
    assert.equal(result.layout.emergency_break_strategy, 'none');
    assert.equal(result.evidence.raw.overflowWrap, 'anywhere');
  }
});

test('CSS break-word original spelling and min-content distinction remain in raw evidence', () => {
  const result = normalize(cssLineBreakConfiguration(cssBreakStyle({ overflowWrap: 'break-word' }), true, 'label'));
  assert.equal(result.layout.normal_break_strategy, 'word');
  assert.equal(result.layout.emergency_break_strategy, 'break-unbreakable');
  assert.equal(result.evidence.raw.overflowWrap, 'break-word');
  const legacy = normalize(cssLineBreakConfiguration(cssBreakStyle({ wordBreak: 'break-word' }), true, 'label'));
  assert.equal(legacy.layout.normal_break_strategy, 'word');
  assert.equal(legacy.layout.emergency_break_strategy, 'break-unbreakable');
  assert.equal(legacy.evidence.raw.wordBreak, 'break-word');
});

test('missing CSS measurements and unrepresented break rules stay unknown', () => {
  for (const changes of [{ wordBreak: undefined }, { overflowWrap: undefined }, { lineBreak: 'anywhere' }, { textWrapMode: 'unsupported' }]) {
    const result = normalize(cssLineBreakConfiguration(cssBreakStyle(changes), true, 'label'));
    assert.equal(result.layout.normal_break_strategy, null);
    assert.equal(result.layout.emergency_break_strategy, null);
    assert.ok(result.evidence.errors.length);
  }
  const keep = normalize(cssLineBreakConfiguration(cssBreakStyle({ wordBreak: 'keep-all' }), true, 'label'));
  assert.equal(keep.layout.normal_break_strategy, 'keep-all');
  assert.equal(keep.layout.emergency_break_strategy, null);
  assert.ok(keep.evidence.errors.length);
});

test('non-text CSS properties are explicitly inapplicable, not an inferred no-wrap policy', () => {
  const result = normalize(cssLineBreakConfiguration(cssBreakStyle({ overflowWrap: 'anywhere' }), false, 'paint-region'));
  assert.equal(result.layout.break_strategy_version, 1);
  assert.equal(result.layout.normal_break_strategy, null);
  assert.equal(result.layout.emergency_break_strategy, null);
  assert.equal(result.evidence.applicable, false);
  assert.ok(result.evidence.reason);
  assert.equal(result.evidence.raw.overflowWrap, 'anywhere');
});

test('recorded file-code line number precedes source text without changing either measurement', () => {
  // Actual en-US/light/1440x900 file-code evidence from 1e3b7c5. The number's
  // CDP pseudo box is left of the source range; the old emission was reversed.
  const line = readingElement(readingText());
  const items = [
    { id: 'dom-344:text-0', parent: 'dom-342', region: 'right-pane', kind: 'text', text: 'def review(platform: str) -> str:', order: 21,
      bounds: { x: 981, y: 173.9375, width: 232.03125, height: 14 }, style: { font_size: 12, font_weight: 400 },
      evidence: { source: 'dom', source_text: 'def review(platform: str) -> str:' } },
    { id: 'dom-344::before', parent: 'dom-342', region: 'right-pane', kind: 'text', text: '1', order: 22,
      bounds: { x: 959.96875, y: 173.9375, width: 7.03125, height: 14 }, style: { font_size: 12, font_weight: 400, pseudo: '::before' },
      evidence: { source: 'CDP.DOMSnapshot' } },
  ];
  const original = new Map(items.map(({ order, ...item }) => [item.id, structuredClone(item)]));
  const raw = [{ id: 'dom-344', emitted: items.map(item => item.id) }], errors = [];
  assignReadingOrder(items, raw, readingOrderIds(line, new Map([[line, 'dom-344']])), errors);
  assert.deepEqual(items.map(item => item.text), ['1', 'def review(platform: str) -> str:']);
  assert.deepEqual(items.map(item => item.order), [0, 1]);
  assert.deepEqual(raw[0].emitted, ['dom-344::before', 'dom-344:text-0']);
  assert.deepEqual(errors, []);
  assert.equal(items.length, original.size);
  for (const { order, ...item } of items) assert.deepEqual(item, original.get(item.id), 'Only reading order changes; source text, identity, bounds, styles and evidence survive');
});

test('actual4e18fc3 three-line recording keeps each before number before text and retains highlighted card', () => {
  const lines = [readingElement(readingText()), readingElement(readingText()), readingElement(readingText())];
  const root = readingElement(...lines), ids = new Map([[root, 'dom-343'], ...lines.map((line, index) => [line, 'dom-' + (344 + index)])]);
  const items = structuredClone(recordedPseudo.old_elements), errors = [];
  const original = new Map(items.map(({ order, ...item }) => [item.id, structuredClone(item)]));
  const raw = lines.map((_, index) => ({ id: 'dom-' + (344 + index),
    emitted: items.filter(item => item.id === 'dom-' + (344 + index) || item.id.startsWith('dom-' + (344 + index) + ':')).map(item => item.id) }));
  assignReadingOrder(items, raw, readingOrderIds(root, ids), errors);
  assert.deepEqual(items.map(item => item.id), ['dom-344::before', 'dom-344:text-0', 'dom-345',
    'dom-345::before', 'dom-345:text-0', 'dom-346::before', 'dom-346:text-0']);
  assert.deepEqual(items.map(item => item.order), [0, 1, 2, 3, 4, 5, 6]);
  assert.deepEqual(raw[1].emitted, ['dom-345', 'dom-345::before', 'dom-345:text-0']);
  assert.equal(items.length, original.size);
  for (const { order, ...item } of items) assert.deepEqual(item, original.get(item.id));
  assert.deepEqual(errors, []);
});

test('nested pseudos and mixed inline children keep their actual source-tree order', () => {
  const nested = readingElement(readingText());
  const parent = readingElement(readingText(), nested, readingText());
  const ids = new Map([[parent, 'parent'], [nested, 'nested']]);
  const positions = normalize(readingOrderIds(parent, ids));
  assert.deepEqual(positions, ['parent', 'parent::marker', 'parent::before', 'parent:text-0',
    'nested', 'nested::marker', 'nested::before', 'nested:text-0', 'nested::after', 'parent:text-1', 'parent::after']);
  const items = ['parent:text-0', 'parent:text-1', 'parent::before', 'parent::after', 'parent::marker',
    'nested:text-0', 'nested::before', 'nested::after'].map(id => ({ id, region: 'dialog', order: -1 }));
  const errors = [];
  assignReadingOrder(items, [], positions, errors);
  assert.deepEqual(items.map(item => item.id), ['parent::marker', 'parent::before', 'parent:text-0',
    'nested::before', 'nested:text-0', 'nested::after', 'parent:text-1', 'parent::after']);
  assert.deepEqual(items.map(item => item.order), [0, 1, 2, 3, 4, 5, 6, 7]);
  assert.deepEqual(errors, []);
});

test('ordering does not create hidden pseudos or suppressed owned-label elements', () => {
  const button = readingElement(readingText());
  const nested = readingElement(readingText());
  const root = readingElement(button, nested);
  const ids = new Map([[root, 'body'], [button, 'button'], [nested, 'nested']]);
  const items = [{ id: 'nested:text-0', region: 'sidebar', order: 2 }, { id: 'button', region: 'header', order: 5 }];
  const errors = [];
  assignReadingOrder(items, [], readingOrderIds(root, ids), errors);
  assert.deepEqual(items.map(item => [item.id, item.order]), [['button', 0], ['nested:text-0', 0]]);
  assert.equal(items.length, 2, 'Only actually measured emitted elements are ordered');
  assert.deepEqual(errors, []);
});

test('unmapped emitted identities remain visible failures rather than being discarded', () => {
  const items = [{ id: 'unknown-painted-item', region: 'dialog', order: 0 }, { id: 'known', region: 'dialog', order: 1 }];
  const errors = [];
  assignReadingOrder(items, [{ emitted: ['unknown-painted-item', 'known'] }], ['known'], errors);
  assert.deepEqual(items.map(item => item.id), ['known', 'unknown-painted-item']);
  assert.equal(errors.length, 1);
  assert.equal(errors[0].type, 'reading_order_source_unavailable');
  assert.equal(errors[0].node, 'unknown-painted-item');
});

function imageFixture() {
  const doc = { URL: 'http://127.0.0.1:7777/' }, url = doc.URL + 'static/icon.svg';
  const image = { localName: 'img', ownerDocument: doc, isConnected: true, src: url, currentSrc: url,
    complete: true, naturalWidth: 256, naturalHeight: 256,
    getAttribute: name => name === 'src' ? '/static/icon.svg' : null,
    getBoundingClientRect: () => ({ x: 18, y: 17, width: 26, height: 26 }) };
  const state = { tag: 'img', connected: true, owner_document_url: doc.URL, in_current_document: true,
    src: url, current_src: url, src_attribute: '/static/icon.svg', srcset_attribute: null, sizes_attribute: null,
    complete: true, natural_width: 256, natural_height: 256, bounds: image.getBoundingClientRect() };
  const body = 'PHN2Zy8+';
  const meta = { image_resources: { file: 'actual.image-resources.json', errors: [], images: { '42': {
    source: 'actual response fixture', status: 'loaded-response-bytes', owner: { backend_node_id: 42,
      before_screenshot: state, after_source_evidence: state }, errors: [], body_base64: body,
      body_file: 'actual.body', byte_length: 6, media_type: 'image/svg+xml', decoded_paint: null } } } };
  const read = vm.runInNewContext('(' + expression('imageResourceEvidence', 'emit') + ')', {
    document: doc, meta, snapshotBackend: new WeakMap([[image, 42]]),
  });
  return { image, doc, meta, read, body };
}

test('actual img backend object and currentSrc bind original response bytes without using URI as content', () => {
  const { image, read, body } = imageFixture(), result = normalize(read(image));
  assert.equal(result.status, 'loaded-response-bytes'); assert.equal(result.body_base64, body);
  assert.equal(result.owner.backend_node_id, 42); assert.equal(result.owner.at_extraction.current_src, image.currentSrc);
  assert.equal(result.decoded_paint, null); assert.deepEqual(result.errors, []);
});

test('changed live img state, wrong backend or absent source stays unknown with original evidence retained', () => {
  for (const mutate of [
    fixture => { fixture.image.currentSrc += '?changed'; },
    fixture => { fixture.image.isConnected = false; },
    fixture => { fixture.image.complete = false; },
    fixture => { fixture.meta.image_resources.images['42'].owner.backend_node_id = 99; },
    fixture => { delete fixture.meta.image_resources.images['42']; },
    fixture => { fixture.meta.image_resources.errors.push('Actual request observation incomplete'); },
  ]) {
    const fixture = imageFixture(); mutate(fixture);
    const result = normalize(fixture.read(fixture.image));
    assert.equal(result.status, 'unknown'); assert.ok(result.errors.length);
    assert.equal(result.owner.at_extraction.current_src, fixture.image.currentSrc);
  }
});

test('only actual img elements receive external-image resource evidence', () => {
  const { read } = imageFixture();
  for (const localName of ['svg', 'div', 'canvas']) assert.equal(read({ localName }), null);
});

const context = {
  innerWidth: 1440, innerHeight: 900, intersect,
  nonempty: box => box.width > 0 && box.height > 0,
  styleOf: element => element.style,
};
const detailsVisibilityEvidence = vm.runInNewContext('(' + expression('detailsVisibilityEvidence', 'visibleRect') + ')', {
  nodeIds: new WeakMap(), pathOf: element => element.selector || element.localName,
});
context.detailsVisibilityEvidence = detailsVisibilityEvidence;
const visibleRect = vm.runInNewContext('(' + expression('visibleRect', 'visibleText') + ')', context);
const element = (bounds, values = {}) => ({
  getBoundingClientRect: () => bounds,
  clientWidth: bounds.width, clientHeight: bounds.height, clientLeft: 0, clientTop: 0,
  scrollWidth: bounds.width, scrollHeight: bounds.height, hidden: false, parentElement: null,
  style: { display: 'block', visibility: 'visible', opacity: '1', overflowX: 'visible', overflowY: 'visible',
    textOverflow: 'clip', webkitLineClamp: 'none' }, ...values,
});

const pseudoLayoutMeasurement = vm.runInNewContext('(' + expression('pseudoLayoutMeasurement', 'snapshot') + ')');
function togglePseudoLayout() {
  // Actual d8f74ff group snapshot: backend520/pseudo node514 has BOTH rows.
  // Last-row overwrite selected409 and hid the visible white14px thumb at408.
  const layout = { nodeIndex: Array(410).fill(-1), bounds: Array(410).fill(null), paintOrders: Array(410).fill(null),
    clientRects: Array(410).fill(null), offsetRects: Array(410).fill(null), scrollRects: Array(410).fill(null), text: Array(410).fill(-1) };
  layout.nodeIndex[407] = 513; layout.bounds[407] = [1117, 289.78125, 32, 18]; layout.paintOrders[407] = 138;
  for (const row of [408, 409]) {
    layout.nodeIndex[row] = 514; layout.paintOrders[row] = 139;
    layout.clientRects[row] = [0, 0, 14, 14]; layout.offsetRects[row] = [2, 2, 14, 14]; layout.scrollRects[row] = [0, 0, 14, 14];
  }
  layout.bounds[408] = [1119, 291.78125, 14, 14]; layout.bounds[409] = [0, 0, 0, 0];
  return layout;
}

test('actual toggle after pseudo keeps its14px visible box despite a later zero-area layout row', () => {
  const layout = togglePseudoLayout(), original = structuredClone(layout);
  const measured = normalize(pseudoLayoutMeasurement(514, layout, { scrollOffsetX: 0, scrollOffsetY: 0 }));
  assert.deepEqual(measured.bounds, { x: 1119, y: 291.78125, width: 14, height: 14 });
  assert.equal(measured.layout_index, 408); assert.equal(measured.paint_order, 139);
  assert.deepEqual(measured.selected_layout_indices, [408]); assert.deepEqual(measured.problems, []);
  assert.deepEqual(measured.layout_rows.map(row => row.source_bounds), [[1119, 291.78125, 14, 14], [0, 0, 0, 0]]);
  assert.deepEqual(measured.layout_rows.map(row => row.text_index), [-1, -1]);
  assert.deepEqual(layout, original, 'Raw snapshot rows, including zero-area records, are never rewritten');
  const owner = element({ x: 1117, y: 289.78125, width: 32, height: 18 });
  assert.deepEqual(normalize(visibleRect(owner, measured.bounds)), measured.bounds, 'The actual circle remains eligible for visible pseudo emission');
  const radius = vm.runInNewContext('(' + expression('radius', 'hasClass') + ')', { number: value => Number.parseFloat(value) });
  assert.equal(radius('50%', owner, measured.bounds), 7, 'Percentage radius uses the actual14px pseudo box, never the owner or zero row');
});

test('pseudo geometry follows actual unique positive bounds regardless of row order or document scroll', () => {
  const layout = togglePseudoLayout();
  [layout.bounds[408], layout.bounds[409]] = [layout.bounds[409], layout.bounds[408]];
  const measured = normalize(pseudoLayoutMeasurement(514, layout, { scrollOffsetX: 100, scrollOffsetY: 20 }));
  assert.deepEqual(measured.bounds, { x: 1019, y: 271.78125, width: 14, height: 14 });
  assert.equal(measured.layout_index, 409); assert.deepEqual(measured.selected_layout_indices, [409]);
  assert.equal(measured.layout_rows.length, 2); assert.deepEqual(measured.problems, []);
});

test('multiple distinct actual pseudo boxes stay ambiguous without guessed unions or chosen fragments', () => {
  const layout = togglePseudoLayout(); layout.bounds[409] = [1133, 291.78125, 14, 14];
  const measured = normalize(pseudoLayoutMeasurement(514, layout, {}));
  assert.equal(measured.bounds, null); assert.equal(measured.layout_index, null); assert.equal(measured.paint_order, null);
  assert.deepEqual(measured.selected_layout_indices, []); assert.equal(measured.layout_rows.length, 2);
  assert.ok(measured.problems.some(problem => /multiple distinct/.test(problem.reason)));
});

test('missing, zero-only and malformed pseudo layout remain explicit failures instead of claimed hidden paint', () => {
  for (const alteration of [
    value => { value.nodeIndex[408] = value.nodeIndex[409] = -1; },
    value => { value.bounds[408] = [0, 0, 0, 0]; },
    value => { value.bounds[409] = [0, 0, -1, 14]; },
    value => { value.bounds[409] = null; },
  ]) {
    const layout = togglePseudoLayout(); alteration(layout);
    const measured = normalize(pseudoLayoutMeasurement(514, layout, {}));
    assert.equal(measured.bounds, null); assert.ok(measured.problems.some(problem => problem.property === 'pseudo.bounds'));
  }
});

test('identical actual positive pseudo rectangles retain all rows and do not guess conflicting paint order', () => {
  const layout = togglePseudoLayout(); layout.bounds[409] = [...layout.bounds[408]];
  const measured = normalize(pseudoLayoutMeasurement(514, layout, {}));
  assert.deepEqual(measured.bounds, { x: 1119, y: 291.78125, width: 14, height: 14 });
  assert.equal(measured.layout_index, null); assert.deepEqual(measured.selected_layout_indices, [408, 409]);
  assert.equal(measured.paint_order, 139); assert.deepEqual(measured.problems, []);
  layout.paintOrders[409] = 140;
  const conflicting = normalize(pseudoLayoutMeasurement(514, layout, {}));
  assert.deepEqual(conflicting.bounds, measured.bounds); assert.equal(conflicting.paint_order, null);
  assert.ok(conflicting.problems.some(problem => problem.property === 'pseudo.paint_order'));
});

function recordedPseudoSnapshot() {
  // Rehydrate only the recorded arrays at their ORIGINAL sparse indexes. No
  // element/pseudo bounds, text or expected layout is supplied by a browser.
  const layout = { nodeIndex: [], bounds: [], text: [], paintOrders: [], clientRects: [], offsetRects: [], scrollRects: [] };
  const strings = [], document = { scrollOffsetX: 0, scrollOffsetY: 0, textBoxes: { layoutIndex: [], bounds: [], start: [], length: [] } };
  for (const row of recordedPseudo.layout_rows) {
    const i = row.layout_index;
    layout.nodeIndex[i] = row.node_index; layout.bounds[i] = [...row.bounds]; layout.text[i] = row.text_index;
    layout.paintOrders[i] = row.paint_order; layout.clientRects[i] = row.client_rect ?? [];
    layout.offsetRects[i] = row.offset_rect ?? []; layout.scrollRects[i] = row.scroll_rect ?? [];
    if (row.text_index >= 0) strings[row.text_index] = row.text;
  }
  for (const box of recordedPseudo.text_boxes) {
    document.textBoxes.layoutIndex[box.index] = box.layout_index; document.textBoxes.bounds[box.index] = [...box.bounds];
    document.textBoxes.start[box.index] = box.start; document.textBoxes.length[box.index] = box.length;
  }
  return { layout, document, strings, node: recordedPseudo.pseudo_node.index };
}

test('actual2cb073c pseudo CSS box and anonymous LayoutText box are independent measured quantities', () => {
  const fixture = recordedPseudoSnapshot(), original = structuredClone(fixture);
  const result = normalize(pseudoLayoutMeasurement(fixture.node, fixture.layout, fixture.document, fixture.strings));
  assert.deepEqual(result.bounds, { x: 921, y: 171.9375, width: 60, height: 19.1875 });
  assert.deepEqual(result.text_element_bounds, { x: 959.765625, y: 173.9375, width: 7.234375, height: 14 });
  assert.deepEqual(result.selected_layout_indices, [402]);
  assert.deepEqual(result.text_layout_indices, [403]);
  assert.deepEqual(result.layout_rows.map(row => [row.layout_index, row.text_index, row.layout_quantity]),
    [[402, -1, 'layout-without-transformed-text'], [403, 123, 'text-layout']]);
  assert.deepEqual(result.text_fragments.map(row => [row.text_box_index, row.layout_index, row.start, row.length]), [[107, 403, 0, 1]]);
  assert.deepEqual(result.problems, []); assert.deepEqual(result.text_geometry_problems, []);
  assert.equal(result.text_source_span_coverage.complete, true);
  assert.equal(result.text_source_span_coverage.unit, 'UTF-16 code units');
  assert.equal(result.text_source_span_coverage.source_text, '1');
  assert.deepEqual(result.text_source_span_coverage.rows[0].spans.map(span => [span.start, span.end, span.source_text]), [[0, 1, '1']]);
  assert.notDeepEqual(result.bounds, result.text_element_bounds, 'Containing box never supplies text geometry');
  assert.match(result.text_quantity, /not painted glyph ink/);
  assert.deepEqual(fixture, original, 'Every original row/index/string/fragment remains unchanged');
});

test('actual pseudo outer box remains measured when text fragment coverage is missing', () => {
  const fixture = recordedPseudoSnapshot(); fixture.document.textBoxes = {};
  const result = normalize(pseudoLayoutMeasurement(fixture.node, fixture.layout, fixture.document, fixture.strings));
  assert.equal(result.bounds.width, 60);
  assert.equal(result.text_element_bounds, null);
  assert.deepEqual(result.text_layout_indices, [403]);
  assert.ok(result.text_geometry_problems.some(problem => /no independently owned/.test(problem.reason)));
  assert.equal(result.layout_rows[1].bounds.width, 7.234375, 'Raw LayoutText aggregate is retained but not substituted for absent fragments');
});

test('pseudo text geometry never borrows a sibling source-text fragment', () => {
  const fixture = recordedPseudoSnapshot(); fixture.document.textBoxes.layoutIndex[107] = 404;
  const result = normalize(pseudoLayoutMeasurement(fixture.node, fixture.layout, fixture.document, fixture.strings));
  assert.equal(result.text_element_bounds, null);
  assert.deepEqual(result.text_fragments, []);
  assert.ok(result.text_geometry_problems.length);
});

test('unknown pseudo text index or missing actual string cannot identify the CSS box by size', () => {
  for (const change of [fixture => { fixture.layout.text[403] = null; }, fixture => { delete fixture.strings[123]; }]) {
    const fixture = recordedPseudoSnapshot(); change(fixture);
    const result = normalize(pseudoLayoutMeasurement(fixture.node, fixture.layout, fixture.document, fixture.strings));
    assert.equal(result.bounds, null);
    assert.ok(result.problems.some(problem => /cannot distinguish/.test(problem.reason)));
    assert.equal(result.layout_rows.length, 2);
  }
});

test('distinct actual pseudo text fragments remain unresolved without a guessed union or chosen minimum', () => {
  const fixture = recordedPseudoSnapshot(), boxes = fixture.document.textBoxes;
  boxes.layoutIndex[109] = 403; boxes.bounds[109] = [967, 173.9375, 3, 14]; boxes.start[109] = 0; boxes.length[109] = 1;
  const result = normalize(pseudoLayoutMeasurement(fixture.node, fixture.layout, fixture.document, fixture.strings));
  assert.equal(result.bounds.width, 60);
  assert.equal(result.text_element_bounds, null);
  assert.equal(result.text_fragments.length, 2);
  assert.ok(result.text_geometry_problems.some(problem => /no containing CSS box or guessed union/.test(problem.reason)));
});

test('distinguishing anonymous text does not excuse multiple real non-text pseudo boxes', () => {
  const fixture = recordedPseudoSnapshot();
  fixture.layout.nodeIndex[405] = fixture.node; fixture.layout.bounds[405] = [100, 200, 10, 20];
  fixture.layout.text[405] = -1; fixture.layout.paintOrders[405] = 103;
  const result = normalize(pseudoLayoutMeasurement(fixture.node, fixture.layout, fixture.document, fixture.strings));
  assert.equal(result.bounds, null);
  assert.equal(result.text_element_bounds.width, 7.234375);
  assert.ok(result.problems.some(problem => /multiple distinct/.test(problem.reason)));
  assert.equal(result.layout_rows.length, 3);
});

test('pseudo fragment range must fit its own actual UTF16 source string', () => {
  for (const [start, length] of [[1, 1], [0, 2], [-1, 1], [0.5, 1], [0, Number.MAX_SAFE_INTEGER]]) {
    const fixture = recordedPseudoSnapshot();
    fixture.document.textBoxes.start[107] = start; fixture.document.textBoxes.length[107] = length;
    const result = normalize(pseudoLayoutMeasurement(fixture.node, fixture.layout, fixture.document, fixture.strings));
    assert.equal(result.bounds.width, 60, 'Actual outer box remains independent');
    assert.equal(result.text_element_bounds, null);
    assert.equal(result.text_source_span_coverage.complete, false);
    assert.ok(result.text_geometry_problems.some(problem => problem.property === 'pseudo.text_source_span' && /outside/.test(problem.reason)));
    assert.equal(result.text_fragments[0].start, start); assert.equal(result.text_fragments[0].length, length);
  }
});

test('matching pseudo rectangle cannot certify a partial source string', () => {
  const fixture = recordedPseudoSnapshot(); fixture.strings[123] = '12';
  const result = normalize(pseudoLayoutMeasurement(fixture.node, fixture.layout, fixture.document, fixture.strings));
  assert.equal(result.text_source_span_coverage.source_text, '12');
  assert.equal(result.text_source_span_coverage.rows[0].spans[0].source_text, '1');
  assert.equal(result.text_source_span_coverage.complete, false);
  assert.equal(result.text_element_bounds, null);
  assert.ok(result.text_geometry_problems.some(problem => /do not reach/.test(problem.reason)));
});

test('same-box pseudo fragments reject duplicate overlaps and gaps but accept exact source coverage', () => {
  for (const fixtureCase of [
    { text: '1', start: 0, complete: false, reason: /overlap or duplicate/ },
    { text: '123', start: 2, complete: false, reason: /omit actual text/ },
    { text: '12', start: 1, complete: true },
  ]) {
    const fixture = recordedPseudoSnapshot(), boxes = fixture.document.textBoxes;
    fixture.strings[123] = fixtureCase.text;
    boxes.layoutIndex[109] = 403; boxes.bounds[109] = [...boxes.bounds[107]];
    boxes.start[109] = fixtureCase.start; boxes.length[109] = 1;
    const result = normalize(pseudoLayoutMeasurement(fixture.node, fixture.layout, fixture.document, fixture.strings));
    assert.equal(result.text_source_span_coverage.complete, fixtureCase.complete);
    assert.equal(result.text_fragments.length, 2, 'Matching geometry never deduplicates real source spans');
    if (fixtureCase.complete) {
      assert.equal(result.text_element_bounds.width, 7.234375);
      assert.deepEqual(result.text_source_span_coverage.rows[0].spans.map(span => span.source_text), ['1', '2']);
      assert.deepEqual(result.text_geometry_problems, []);
    } else {
      assert.equal(result.text_element_bounds, null);
      assert.ok(result.text_geometry_problems.some(problem => fixtureCase.reason.test(problem.reason)));
    }
  }
});

test('each actual LayoutText row needs its own complete spans even with identical text and bounds', () => {
  const fixture = recordedPseudoSnapshot(), boxes = fixture.document.textBoxes;
  fixture.layout.nodeIndex[405] = fixture.node; fixture.layout.bounds[405] = [...fixture.layout.bounds[403]];
  fixture.layout.text[405] = 123; fixture.layout.paintOrders[405] = 103;
  const incomplete = normalize(pseudoLayoutMeasurement(fixture.node, fixture.layout, fixture.document, fixture.strings));
  assert.equal(incomplete.text_source_span_coverage.source_text, '11');
  assert.deepEqual(incomplete.text_source_span_coverage.rows.map(row => row.complete), [true, false]);
  assert.equal(incomplete.text_element_bounds, null);
  boxes.layoutIndex[109] = 405; boxes.bounds[109] = [...boxes.bounds[107]]; boxes.start[109] = 0; boxes.length[109] = 1;
  const complete = normalize(pseudoLayoutMeasurement(fixture.node, fixture.layout, fixture.document, fixture.strings));
  assert.deepEqual(complete.text_source_span_coverage.rows.map(row => row.complete), [true, true]);
  assert.equal(complete.text_source_span_coverage.complete, true);
  assert.equal(complete.text_fragments.length, 2);
});

test('pseudo source offsets count UTF16 code units rather than Unicode code points', () => {
  const fixture = recordedPseudoSnapshot(); fixture.strings[123] = 'A😀B';
  fixture.document.textBoxes.length[107] = 3;
  const partial = normalize(pseudoLayoutMeasurement(fixture.node, fixture.layout, fixture.document, fixture.strings));
  assert.equal(partial.text_source_span_coverage.rows[0].length_utf16, 4);
  assert.equal(partial.text_source_span_coverage.complete, false);
  assert.equal(partial.text_element_bounds, null);
  fixture.document.textBoxes.length[107] = 4;
  const full = normalize(pseudoLayoutMeasurement(fixture.node, fixture.layout, fixture.document, fixture.strings));
  assert.equal(full.text_source_span_coverage.complete, true);
  assert.equal(full.text_source_span_coverage.rows[0].spans[0].source_text, 'A😀B');
  assert.equal(full.text_element_bounds.width, 7.234375);
});

function disclosure(tag, children = [], open = false, bounds = { x: 377, y: 575.59375, width: 686, height: 19.1875 }) {
  const node = element(bounds, { localName: tag, children, open,
    selector: tag, getAttribute(name) { return name === 'open' && this.open ? '' : null; },
    contains(other) {
      for (let descendant = other; descendant; descendant = descendant.parentElement) if (descendant === this) return true;
      return false;
    },
  });
  for (const child of children) child.parentElement = node;
  return node;
}

test('38af737 closed copies details rejects nonzero DOMRange boxes for unpainted cc-meta content', () => {
  // Observed source: copies backend 791 has no open attribute; descendants
  // 797/798 and 799/800 are absent from snapshot layout and AX. Its screenshot
  // contains the summary, not these two strings, despite these forced boxes.
  const first = disclosure('div');
  const second = disclosure('div', [], false, { x: 377, y: 600.78125, width: 686, height: 19.1875 });
  const rule = disclosure('div', [first, second]), summary = disclosure('summary');
  const details = disclosure('details', [summary, rule]);
  details.selector = '#layer details.cc-code';
  for (const content of [first, second]) {
    assert.equal(visibleRect(content, content.getBoundingClientRect()), null);
    const evidence = normalize(detailsVisibilityEvidence(content));
    assert.equal(evidence.hidden, true);
    assert.deepEqual(evidence.ancestors, [{ details: '#layer details.cc-code', open: false,
      open_attribute: null, first_summary: 'summary', inside_first_summary: false, own_details_content: false, hidden: true }]);
    assert.ok(content.getBoundingClientRect().width > 0, 'Raw forced layout geometry remains available and is not rewritten');
  }
  assert.ok(visibleRect(summary, summary.getBoundingClientRect()), 'Actual primary summary stays visible');
});

test('38af737 live tool nested disclosure respects each actual open state', () => {
  const output = disclosure('pre', [], false, { x: 370, y: 676.796875, width: 681, height: 33.8125 });
  const stepSummary = disclosure('summary'), step = disclosure('details', [stepSummary, disclosure('div', [output])]);
  step.selector = '#live details.step.err';
  const acts = disclosure('details', [disclosure('summary'), disclosure('div', [step])], true);
  acts.selector = '#live details.acts';
  const evidence = normalize(detailsVisibilityEvidence(output));
  assert.equal(evidence.hidden, true);
  assert.deepEqual(evidence.ancestors.map(item => [item.details, item.open, item.hidden]),
    [['#live details.step.err', false, true], ['#live details.acts', true, false]]);
  assert.equal(visibleRect(output, output.getBoundingClientRect()), null);
  assert.ok(visibleRect(stepSummary, stepSummary.getBoundingClientRect()));
  acts.open = false;
  step.open = true;
  assert.equal(visibleRect(stepSummary, stepSummary.getBoundingClientRect()), null,
    'Opening an inner details does not expose it through a closed ancestor');
});

test('only the first direct summary and its descendants survive a closed details', () => {
  const preceding = disclosure('div'), label = disclosure('b'), first = disclosure('summary', [label]);
  const second = disclosure('summary'), details = disclosure('details', [preceding, first, second]);
  assert.ok(visibleRect(first, first.getBoundingClientRect()), 'Primary summary need not be the first child');
  assert.ok(visibleRect(label, label.getBoundingClientRect()));
  assert.equal(visibleRect(preceding, preceding.getBoundingClientRect()), null);
  assert.equal(visibleRect(second, second.getBoundingClientRect()), null, 'A later summary is ordinary closed content');
  assert.ok(visibleRect(details, details.getBoundingClientRect()), 'The details container itself remains visible');
  assert.equal(visibleRect(details, details.getBoundingClientRect(), true), null,
    'A direct Text child belongs to hidden details content, not its visible primary summary');
});

test('a nested summary is not a direct details summary and no-summary content remains closed', () => {
  const nestedSummary = disclosure('summary'), wrapper = disclosure('div', [nestedSummary]);
  const details = disclosure('details', [wrapper]);
  assert.equal(detailsVisibilityEvidence(nestedSummary).ancestors[0].first_summary, null);
  assert.equal(visibleRect(nestedSummary, nestedSummary.getBoundingClientRect()), null);
  assert.ok(visibleRect(details, details.getBoundingClientRect()), 'No default UA summary is manufactured by this rule');
  details.open = true;
  assert.ok(visibleRect(nestedSummary, nestedSummary.getBoundingClientRect()), 'Live open changes are read instead of cached');
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
  const read = vm.runInNewContext('(' + expression('scrollbarEvidence', 'scrollbarGutter') + ')', {
    styleOf: context.styleOf, rect: box => ({ ...box }),
    pseudoByOwner: new WeakMap(), pathOf: () => '#actual-overflow-owner', snapshotBackend: new WeakMap(), computedSrgb: () => ({ rgba: null }),
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

test('textarea resize evidence exists without scroll overflow and never promotes the owner box to a grip box', () => {
  // Actual 1e3b7c5 en-US/light/1440x900 new-org owner dom-505 has this
  // border box and AX owner 766; the old record had no scrollbar or grip.
  const owner = element({ x: 482, y: 416.09375, width: 476, height: 76 }, {
    localName: 'textarea', value: '', disabled: false, readOnly: false,
    getAttribute: name => name === 'placeholder' ? 'What this organization should accomplish' : null,
  });
  owner.style = { ...owner.style, resize: 'both', direction: 'ltr', writingMode: 'horizontal-tb', overflowX: 'auto', overflowY: 'auto' };
  const ax = { nodeId: '766', backendDOMNodeId: 766, role: { value: 'textbox' }, childIds: [] };
  const read = vm.runInNewContext('(' + expression('resizeHandleEvidence', 'scrollbarEvidence') + ')', {
    styleOf: context.styleOf, rect: box => ({ ...box }), pseudoByOwner: new WeakMap(),
    accessibilityOf: () => ({ node_ids: ['766'] }), axById: new Map([['766', ax]]),
    getComputedStyle: () => ({ display: 'inline', visibility: 'visible', opacity: '1', width: 'auto', height: 'auto' }),
  });
  const evidence = normalize(read(owner));
  assert.equal(evidence.kind, 'resize-handle');
  assert.equal(evidence.owner_scroll_height, evidence.owner_client_height, 'No overflow is required to expose a textarea resize affordance');
  assert.deepEqual(evidence.owner_bounds, owner.getBoundingClientRect());
  assert.equal(evidence.owner_resize, 'both');
  assert.deepEqual(evidence.ax_subtree, [ax]);
  assert.deepEqual(evidence.dom_snapshot_parts, []);
  for (const quantity of ['painted_presence', 'bounds', 'style', 'state']) assert.equal(evidence[quantity], null);
  assert.match(evidence.computed_pseudo.quantity, /not measured/);
});

test('actual resize pseudo and AX child records remain raw evidence until independent grip paint is measured', () => {
  const owner = element({ x: 40, y: 50, width: 200, height: 100 }, {
    localName: 'textarea', value: 'untouched', disabled: false, readOnly: false, getAttribute: () => null,
  });
  owner.style.resize = 'vertical';
  const pseudo = { type: 'resizer', bounds: { x: 225, y: 135, width: 15, height: 15 }, source: 'fixture CDP layout record' };
  const axOwner = { nodeId: 'owner', childIds: ['child'], role: { value: 'textbox' } };
  const axChild = { nodeId: 'child', childIds: [], role: { value: 'generic' } };
  const read = vm.runInNewContext('(' + expression('resizeHandleEvidence', 'scrollbarEvidence') + ')', {
    styleOf: context.styleOf, rect: box => ({ ...box }), pseudoByOwner: new WeakMap([[owner, [pseudo]]]),
    accessibilityOf: () => ({ node_ids: ['owner'] }), axById: new Map([['owner', axOwner], ['child', axChild]]),
    getComputedStyle: () => ({ display: 'inline', backgroundColor: 'rgb(20, 30, 40)', width: '15px', height: '15px' }),
  });
  const evidence = normalize(read(owner));
  assert.deepEqual(evidence.dom_snapshot_parts, [pseudo]);
  assert.deepEqual(evidence.ax_subtree, [axOwner, axChild]);
  assert.equal(evidence.computed_pseudo.background, 'rgb(20, 30, 40)');
  assert.equal(evidence.bounds, null, 'A layout record is not silently certified as painted grip bounds');
  assert.equal(evidence.style, null, 'Computed pseudo style does not prove a painted grip or its pixel colors');
});

test('resize none keeps the nonresizable composer out of resize capability evidence', () => {
  const owner = element({ x: 311, y: 811, width: 758, height: 26 }, { localName: 'textarea' });
  owner.style.resize = 'none';
  const read = vm.runInNewContext('(' + expression('resizeHandleEvidence', 'scrollbarEvidence') + ')', {
    styleOf: context.styleOf,
  });
  assert.equal(read(owner), null);
  owner.localName = 'input'; owner.style.resize = 'both';
  assert.equal(read(owner), null, 'This evidence route claims only actual textarea capabilities');
});

function selectArrowReader({ appearance = 'auto', multiple = false, size = 0, role = 'combobox', measured = true } = {}) {
  // These owner IDs/rect and UA identities come from 38af737 group/backend559.
  // They intentionally contain no arrow node or independently measured pixels.
  const owner = element({ x: 1177, y: 666.34375, width: 237, height: 37 }, {
    localName: 'select', multiple, size, disabled: false, selectedIndex: 1, value: 'org_000001', matches: () => false,
  });
  owner.style = { ...owner.style, appearance, direction: 'ltr', writingMode: 'horizontal-tb', zoom: '1',
    transform: 'none', transformOrigin: '118.5px 18.5px', color: 'rgb(27, 27, 26)', backgroundColor: 'rgb(255, 255, 255)',
    colorScheme: 'light', fontSize: '14px' };
  for (const side of ['Top', 'Right', 'Bottom', 'Left']) owner.style['border' + side + 'Width'] = '1px';
  const uaOwner = { nodeId: 535, backendNodeId: 559, nodeType: 1, nodeName: 'SELECT', localName: 'select', nodeValue: '',
    attributes: ['class', 'input', 'aria-label', '上级组织'], shadowRoots: [{ nodeId: 536, backendNodeId: 795,
      nodeType: 11, nodeName: '#document-fragment', shadowRootType: 'user-agent', children: [
        { nodeId: 537, backendNodeId: 765, nodeType: 1, nodeName: 'DIV', attributes: ['aria-hidden', 'true', 'pseudo', '-internal-select-inner-element'],
          children: [{ nodeId: 538, backendNodeId: 796, nodeType: 3, nodeName: '#text', nodeValue: 'Relic 工作室' }] },
        { nodeId: 539, backendNodeId: 766, nodeType: 1, nodeName: 'SLOT', attributes: ['pseudo', '-internal-select-button-slot'], distributedNodes: [] },
      ] }] };
  const ax = { measured, backend_node_id: 559, node_ids: ['559'], role, properties: [{ name: 'expanded', value: { value: false } }] };
  const axNode = { nodeId: '559', backendDOMNodeId: 559, role: { value: role }, childIds: [] };
  const environment = { styleOf: element => element.style, accessibilityOf: () => ax,
    snapshotBackend: new WeakMap([[owner, 559]]), piercedByBackend: new Map([[559, uaOwner]]),
    axById: new Map([['559', axNode]]), pseudoByOwner: new WeakMap(),
    pathOf: () => '#panel select[aria-label="上级组织"]', rect: bounds => ({ ...bounds }), document: { activeElement: null },
    meta: { scene_id: 'zh-CN-light-1440x900-group', screenshot_file: 'zh-CN-light-1440x900-group.png' },
    getComputedStyle: () => ({ content: 'normal', display: 'block', visibility: 'visible', opacity: '1',
      width: 'auto', height: 'auto', color: 'rgb(27, 27, 26)', backgroundColor: 'rgba(0, 0, 0, 0)', transform: 'none', appearance: 'none' }),
  };
  const read = vm.runInNewContext('(' + expression('selectArrowEvidence', 'recordSelectArrowCoverage') + ')', environment);
  const unmeasured = [], errors = [];
  const record = vm.runInNewContext('(' + expression('recordSelectArrowCoverage', 'resizeHandleEvidence') + ')', {
    unmeasured, extraction_errors: errors,
  });
  return { read, record, owner, uaOwner, environment, unmeasured, errors };
}

test('actual native select retains real owner/UA identities but no manufactured arrow geometry', () => {
  const f = selectArrowReader(), evidence = f.read(f.owner), raw = { id: 'dom-369' };
  f.record(raw, evidence);
  assert.equal(raw.ua_select_arrow, evidence);
  assert.deepEqual(normalize(evidence.owner_bounds), { x: 1177, y: 666.34375, width: 237, height: 37 });
  assert.equal(evidence.owner_backend_node_id, 559);
  assert.equal(evidence.pierced_dom.owner, f.uaOwner, 'Keep the original recorded UA subtree, not a synthesized arrow node');
  assert.equal(evidence.pierced_dom.owner_identity_matches, true);
  assert.equal(evidence.owner_state.expanded, false);
  assert.equal(evidence.mode, 'native-menu-list'); assert.equal(evidence.requires_measurement, true);
  for (const key of ['painted_presence', 'bounds', 'path', 'style', 'state']) assert.equal(evidence[key], null, key);
  assert.equal(evidence.screenshot.arrow_pixel_bounds, null);
  assert.equal(evidence.screenshot.arrow_pixels, null);
  assert.equal(f.unmeasured[0].property, 'select_arrow.rendered_part');
  assert.equal(f.errors[0].type, 'ua_select_arrow_measurement_unavailable');
});

test('appearance none records source evidence without requiring a native-theme arrow', () => {
  const f = selectArrowReader({ appearance: 'none' }), raw = { id: 'author-select' };
  const evidence = f.read(f.owner); f.record(raw, evidence);
  assert.equal(evidence.mode, 'native-appearance-suppressed');
  assert.equal(evidence.requires_measurement, false);
  assert.equal(evidence.painted_presence, null, 'Suppressing native appearance cannot prove that author decorations are absent');
  assert.equal(raw.ua_select_arrow, evidence);
  assert.deepEqual(f.unmeasured, []); assert.deepEqual(f.errors, []);
});

test('actual listbox semantics differ from an unresolved or customizable select', () => {
  const listbox = selectArrowReader({ size: 4, role: 'listbox' });
  assert.equal(listbox.read(listbox.owner).requires_measurement, false);
  const unconfirmed = selectArrowReader({ multiple: true, role: 'listbox', measured: false });
  assert.equal(unconfirmed.read(unconfirmed.owner).requires_measurement, true, 'Missing AX evidence does not certify listbox presentation');
  const custom = selectArrowReader({ appearance: 'base-select' }), raw = { id: 'custom-picker' };
  custom.environment.pseudoByOwner.set(custom.owner, [{ type: '::picker-icon', bounds: { x: 12, y: 14, width: 20, height: 20 } }]);
  const evidence = custom.read(custom.owner); custom.record(raw, evidence);
  assert.equal(evidence.mode, 'customizable-picker');
  assert.equal(evidence.bounds, null, 'A pseudo layout candidate is not certified independent arrow paint');
  assert.equal(evidence.computed_picker_icon.width, 'auto');
  assert.equal(evidence.snapshot_pseudo_parts.length, 1);
  assert.equal(custom.errors.length, 1);
});

test('missing UA receipt and unsupported pseudo style retain an explicit arrow failure', () => {
  const f = selectArrowReader(); f.environment.piercedByBackend.clear();
  f.environment.getComputedStyle = () => { throw new Error('actual pseudo provider failure'); };
  const evidence = f.read(f.owner); f.record({ id: 'actual-select' }, evidence);
  assert.equal(evidence.pierced_dom.owner, null);
  assert.equal(evidence.pierced_dom.owner_identity_matches, false);
  assert.equal(evidence.computed_picker_icon, null);
  assert.match(evidence.computed_picker_icon_error, /actual pseudo provider failure/);
  assert.equal(evidence.painted_presence, null);
  assert.equal(f.errors.length, 1);
});

test('non-select controls do not acquire a fabricated dropdown obligation', () => {
  const f = selectArrowReader();
  f.owner.localName = 'button';
  assert.equal(f.read(f.owner), null);
  const raw = { id: 'real-button' }; f.record(raw, null);
  assert.equal(raw.ua_select_arrow, undefined);
  assert.deepEqual(f.unmeasured, []); assert.deepEqual(f.errors, []);
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
  const request = vm.runInNewContext('(' + expression('fontRequestEvidence', 'fontWeightEvidence') + ')', {
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

test('computed 700 never becomes a resolved weight through a Semibold face name', () => {
  const read = vm.runInNewContext('(' + expression('fontWeightEvidence', 'platformFonts') + ')');
  const request = { source: 'getComputedStyle', weight: 700, weight_css: '700', variation_settings: 'normal' };
  const fonts = [{ family_name: '蘋方-簡', postscript_name: 'PingFangSC-Semibold', glyph_count: 1 }];
  const actual = normalize(read('actual-dom-node', request, fonts, true));
  assert.equal(actual.configured.value, 700);
  assert.equal(actual.legacy.value, 700);
  assert.equal(actual.owner, 'actual-dom-node');
  assert.deepEqual(actual.configured.raw, request);
  assert.equal(actual.resolved.faces[0].value, null);
  assert.deepEqual(actual.resolved.faces[0].raw, fonts[0]);
  assert.equal(actual.resolved.source_span_complete, false);
});

test('unmeasured font request and actual face remain explicit unknown quantities', () => {
  const read = vm.runInNewContext('(' + expression('fontWeightEvidence', 'platformFonts') + ')');
  const actual = normalize(read('unknown-owner', null, null, true));
  assert.equal(actual.configured.value, null);
  assert.equal(actual.resolved.faces, null);
  assert.equal(actual.applicable, true);
  assert.equal(normalize(read('nontext-owner', null, [], false)).applicable, false);
});

function fontNodeReader() {
  const unmeasured = [], snapshotBackend = new WeakMap(), snapshotInputFontOwners = new WeakMap();
  const fonts = { source: 'CDP.CSS.getPlatformFontsForNode', by_backend_node: {}, queries: {}, errors: [] };
  const meta = { reference_environment: { fonts }, input_text_boxes: {} };
  const identity = vm.runInNewContext('(' + expression('platformFontIdentity', 'fontRequestEvidence') + ')');
  const read = vm.runInNewContext('(' + expression('platformFonts', 'panelResizeEvidence') + ')', {
    meta, snapshotBackend, snapshotInputFontOwners, unmeasured, Node: { TEXT_NODE: 3 }, platformFontIdentity: identity,
  });
  const actual = (backend, face, count, type = 3) => {
    const result = [{ familyName: 'actual family', postScriptName: face, glyphCount: count, isCustomFont: false }];
    fonts.by_backend_node[backend] = result;
    fonts.queries[backend] = { backend_node_id: backend, node_type: type, frontend_node_id: backend + 1000,
      scope: type === 3 ? 'text-node-layout' : 'descendant-layout-aggregate', request_sent: true, error: null,
      request: { method: 'CSS.getPlatformFontsForNode', parameters: { nodeId: backend + 1000 } }, result: { fonts: result } };
  };
  const owner = { matches: () => false }, first = {}, bold = {}, last = {};
  for (const [node, backend] of [[owner, 360], [first, 361], [bold, 363], [last, 364]]) snapshotBackend.set(node, backend);
  return { read, fonts, actual, meta, unmeasured, snapshotBackend, snapshotInputFontOwners, owner, first, bold, last };
}

test('font attribution uses the actual text node instead of its mixed parent aggregate', () => {
  const f = fontNodeReader();
  f.actual(360, 'parent-includes-nested-bold', 99, 1);
  f.actual(361, 'actual-first-regular', 8); f.actual(363, 'actual-bold', 12); f.actual(364, 'actual-last-regular', 10);
  const result = normalize(f.read(f.owner, '收到。我会按 ', 'dom-231:text-0', { textNode: f.first }));
  assert.deepEqual(result.fonts.map(font => [font.postscript_name, font.glyph_count]), [['actual-first-regular', 8]]);
  assert.deepEqual(result.evidence.owners.map(owner => owner.backend_node_id), [361]);
  assert.equal(result.evidence.attribution, 'actual-text-node-layouts');
  assert.equal(result.evidence.owners[0].query.frontend_node_id, 1361);
  assert.deepEqual(f.unmeasured, []);
});

test('a control label combines only its owned actual Text queries and does not double count a node', () => {
  const f = fontNodeReader();
  f.actual(361, 'actual-face', 8); f.actual(364, 'actual-face', 10); f.actual(363, 'unowned-bold', 12);
  const result = normalize(f.read(f.owner, 'actual owned label', 'actual-control', { ownedTextNodes: [f.first, f.last, f.first] }));
  assert.deepEqual(result.fonts.map(font => [font.postscript_name, font.glyph_count]), [['actual-face', 18]]);
  assert.deepEqual(result.evidence.owners.map(owner => owner.backend_node_id), [361, 364]);
});

test('a failed or unproven Text query cannot use successful parent statistics as fallback', () => {
  for (const failure of ['missing', 'error', 'wrong-node-type', 'missing-query']) {
    const f = fontNodeReader();
    f.actual(360, 'parent-face', 99, 1);
    if (failure !== 'missing') f.actual(361, 'child-face', 8, failure === 'wrong-node-type' ? 1 : 3);
    if (failure === 'error') {
      f.fonts.queries[361].error = 'Actual provider error';
      f.fonts.errors.push({ backend_node_id: 361, reason: 'Actual provider error' });
    }
    if (failure === 'missing-query') delete f.fonts.queries[361];
    const result = f.read(f.owner, 'actual text', 'actual-text', { textNode: f.first });
    assert.equal(result.fonts, null, failure);
    assert.equal(f.unmeasured.length, 1, failure);
    assert.equal(f.unmeasured[0].property, 'style.rendered_fonts');
    assert.deepEqual(normalize(result.evidence.owners.map(owner => owner.backend_node_id)), [361]);
  }
});

test('UA input font supplement consumes the measured text-node identity, not its aggregate owner', () => {
  const f = fontNodeReader(), input = { matches: () => true };
  f.snapshotBackend.set(input, 500);
  f.meta.input_text_boxes['500'] = { text_nodes: [{ backend_node_id: 502, font_owner_backend_node_id: 501,
    text: 'actual value', boxes: [{ x: 10, y: 20, width: 30, height: 15 }] }] };
  f.actual(501, 'ua-parent', 50, 1); f.actual(502, 'actual-input-face', 12);
  const result = normalize(f.read(input, 'actual value', 'actual-input', {}));
  assert.deepEqual(result.fonts.map(font => [font.postscript_name, font.glyph_count]), [['actual-input-face', 12]]);
  assert.deepEqual(result.evidence.owners.map(owner => owner.backend_node_id), [502]);
});

test('whole pseudo-layout evidence stays explicitly scoped and cannot substitute for direct text', () => {
  const f = fontNodeReader();
  f.actual(600, 'actual-pseudo-face', 1, 1);
  const result = normalize(f.read(f.owner, '1', 'actual-line::before', { pseudo: '::before', axBackend: 600 }));
  assert.equal(result.evidence.attribution, 'whole-pseudo-layout');
  assert.equal(result.fonts[0].postscript_name, 'actual-pseudo-face');
  assert.match(result.evidence.quantity, /not a count of visible painted glyphs or ellipsis ink bounds/);
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
  const read = vm.runInNewContext('(' + expression('svgStrokeData', 'outlineData') + ')', {
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
    outlineData: () => ({ value: 'none' }),
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

function outlineFixture(changes = {}, globals = {}) {
  const style = { outlineStyle: 'dashed', outlineWidth: '1.5px', outlineOffset: '-1.5px', outlineColor: 'rgb(143, 140, 134)',
    transform: 'none', perspective: 'none', zoom: '1', scale: 'none', rotate: 'none', translate: 'none', ...changes };
  const bounds = { x: 22, y: 84, width: 22, height: 22 };
  const owner = { localName: 'span', parentElement: null, style, getBoundingClientRect: () => bounds, getClientRects: () => [bounds] };
  const computed = vm.runInNewContext('(' + expression('computedSrgb', 'color') + ')');
  const read = vm.runInNewContext('(' + expression('outlineData', 'styleData') + ')', {
    pathOf: () => '#actual-outline-owner', rect: box => ({ ...box }), styleOf: el => el.style, SVGElement: SVGElementFixture,
    color: value => computed(value).rgba,
    DOMMatrixReadOnly: class {
      constructor(value) {
        const parts = /^matrix\(([^)]+)\)$/.exec(value)?.[1].split(',').map(Number);
        if (!parts || parts.length !== 6 || !parts.every(Number.isFinite)) throw new TypeError('Fixture matrix is unreadable');
        [this.a, this.b, this.c, this.d, this.e, this.f] = parts; this.is2D = true;
      }
    }, ...globals,
  });
  return { owner, style, bounds, read };
}

test('computed outline is independent from the 22px owner box and has no inferred dashed contour', () => {
  const { owner, style, bounds, read } = outlineFixture();
  const result = normalize(read(owner, style));
  assert.deepEqual(result.value, { style: 'dashed', color: [143, 140, 134, 255], width: 1.5, offset: -1.5,
    dash: null, dash_offset: null, contour: null });
  assert.equal(result.evidence.absence_proven, false);
  assert.deepEqual(result.evidence.owner_bounds, bounds); assert.deepEqual(result.evidence.owner_client_rects, [bounds]);
  assert.equal(result.evidence.outline_to_window_scale, 1);
  assert.deepEqual(result.evidence.computed, { style: 'dashed', color: style.outlineColor, width: '1.5px', offset: '-1.5px' });
  assert.deepEqual(result.problems.map(problem => problem.property), ['style.outline.dash', 'style.outline.dash_offset', 'style.outline.contour']);
});

test('outline records the actual computed width including UA snapping instead of stylesheet constants', () => {
  const { owner, style, read } = outlineFixture({ outlineWidth: '1px' });
  const result = normalize(read(owner, style));
  assert.equal(result.value.width, 1, 'The declared 1.5px subgroup style cannot replace an actual 1px computed value');
  assert.equal(result.value.offset, -1.5); assert.equal(result.evidence.computed.width, '1px');
  assert.equal(result.value.contour, null);
});

test('none requires actual nonpainting outline evidence and zero auto width is not absence', () => {
  for (const changes of [{ outlineStyle: 'none', outlineWidth: '3px' }, { outlineStyle: 'solid', outlineWidth: '0px' }]) {
    const { owner, style, read } = outlineFixture(changes), result = normalize(read(owner, style));
    assert.equal(result.value, 'none'); assert.equal(result.evidence.absence_proven, true);
    assert.deepEqual(result.problems, []); assert.ok(result.evidence.absence_reason);
  }
  const { owner, style, read } = outlineFixture({ outlineStyle: 'auto', outlineWidth: '0px' });
  const automatic = normalize(read(owner, style));
  assert.equal(automatic.value.style, 'auto'); assert.equal(automatic.value.width, null); assert.equal(automatic.value.color, null);
  assert.equal(automatic.evidence.absence_proven, false); assert.equal(automatic.evidence.computed.width, '0px');
  assert.ok(automatic.problems.some(problem => problem.property === 'style.outline.auto_paint'));
});

test('solid outline has no dash subdivision but its actual contour remains unknown', () => {
  const { owner, style, read } = outlineFixture({ outlineStyle: 'solid', outlineWidth: '2px', outlineOffset: '1px',
    outlineColor: 'color(srgb 1 0.5 0.25 / 0.6)' });
  const result = normalize(read(owner, style));
  assert.deepEqual(result.value.dash, []); assert.equal(result.value.dash_offset, null, 'Continuous paint has no applicable dash phase, not a measured zero');
  assert.deepEqual(result.value.color, [255, 127.5, 63.75, .6 * 255]);
  assert.equal(result.value.contour, null); assert.equal(result.value.offset, 1);
  assert.deepEqual(result.problems.map(problem => problem.property), ['style.outline.contour']);
});

test('transformed or unresolved outline units preserve local evidence without guessed window lengths', () => {
  for (const changes of [{ transform: 'matrix(2, 0, 0, 1, 0, 0)' }, { zoom: '1.25' }, { scale: '2 2' },
    { rotate: '30deg' }, { translate: '10px 0px' }]) {
    const { owner, style, read } = outlineFixture(changes), result = normalize(read(owner, style));
    assert.equal(result.value.width, null); assert.equal(result.value.offset, null);
    assert.equal(result.evidence.local_width, 1.5); assert.equal(result.evidence.local_offset, -1.5);
    assert.ok(result.problems.some(problem => problem.property === 'style.outline.coordinate_space'));
  }
  const f = outlineFixture({ outlineWidth: 'medium', outlineOffset: 'calc(1px + 2%)' }), result = normalize(f.read(f.owner, f.style));
  assert.equal(result.value.width, null); assert.equal(result.value.offset, null);
  assert.equal(result.evidence.computed.offset, 'calc(1px + 2%)');
  assert.ok(result.problems.some(problem => problem.property === 'style.outline.width'));
  assert.ok(result.problems.some(problem => problem.property === 'style.outline.offset'));
});

test('recorded chart ancestor translation preserves measured outline lengths but not unresolved paint', () => {
  // 3a924e7 reference zh-CN-light-1440x900-chart, dom-558:
  // the actual chart ancestor matrix and computed outline values below are
  // retained in elements/reference/*chart.elements.json, evidence.outline.
  const f = outlineFixture({ outlineWidth: '1px', outlineOffset: '-1px', outlineColor: 'rgb(120, 54, 65)' });
  f.owner.parentElement = { style: { ...f.style, transform: 'matrix(1, 0, 0, 1, 542, 125)' }, parentElement: null };
  const result = normalize(f.read(f.owner, f.style));
  assert.equal(result.value.width, 1); assert.equal(result.value.offset, -1);
  assert.equal(result.evidence.outline_to_window_scale, 1);
  assert.deepEqual(result.evidence.axis_mappings[1].matrix, { is2D: true, a: 1, b: 0, c: 0, d: 1, e: 542, f: 125 });
  assert.equal(result.evidence.ancestry[1].transform, 'matrix(1, 0, 0, 1, 542, 125)');
  assert.equal(result.value.dash, null); assert.equal(result.value.dash_offset, null); assert.equal(result.value.contour, null);
  assert.deepEqual(result.problems.map(p => p.property), ['style.outline.dash', 'style.outline.dash_offset', 'style.outline.contour']);
});

test('outline translation rejects any nonidentity linear component and unresolved dimensionality', () => {
  for (const transform of ['matrix(1.0000001, 0, 0, 1, 542, 125)', 'matrix(1, 0.01, 0, 1, 542, 125)',
    'matrix(1, 0, 0.01, 1, 542, 125)', 'matrix(1, 0, 0, 0.9999999, 542, 125)',
    'matrix(0, 1, -1, 0, 542, 125)', 'matrix(-1, 0, 0, -1, 542, 125)',
    'matrix(1, 0, 0, 1, Infinity, 125)', 'matrix3d(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 542, 125, 0, 1)']) {
    const f = outlineFixture({ transform }), result = normalize(f.read(f.owner, f.style));
    assert.equal(result.value.width, null, transform); assert.equal(result.value.offset, null, transform);
    assert.equal(result.evidence.outline_to_window_scale, null);
    assert.ok(result.problems.some(p => p.property === 'style.outline.coordinate_space'));
  }
});

test('outline translation cannot conceal another transformed ancestor or a failed actual matrix read', () => {
  for (const ancestor of [{ zoom: '1.1' }, { perspective: '500px' }, { scale: '1.01' },
    { rotate: '1deg' }, { translate: '1px 0px' }]) {
    const f = outlineFixture({ transform: 'matrix(1, 0, 0, 1, 542, 125)' });
    f.owner.parentElement = { style: { ...f.style, transform: 'none', ...ancestor }, parentElement: null };
    const result = normalize(f.read(f.owner, f.style));
    assert.equal(result.value.width, null); assert.equal(result.value.offset, null);
    assert.ok(result.problems.some(p => p.property === 'style.outline.coordinate_space'));
  }
  const f = outlineFixture({ transform: 'matrix(1, 0, 0, 1, 542, 125)' }, { DOMMatrixReadOnly: undefined });
  const result = normalize(f.read(f.owner, f.style));
  assert.equal(result.value.width, null); assert.equal(result.value.offset, null);
  assert.ok(result.evidence.axis_mappings[0].error);
  assert.ok(result.problems.some(p => p.property === 'style.outline.coordinate_space'));
});

test('style extraction keeps outline separate from an actual zero border', () => {
  const f = outlineFixture();
  const read = vm.runInNewContext('(' + expression('styleData', 'stateOf') + ')', {
    number: value => Number.parseFloat(value), radius: () => 6, SVGElement: SVGElementFixture,
    color: value => value, pathOf: () => '#actual-outline-owner', cumulativeOpacity: () => 1,
    shadowData: () => [], backgroundData: () => 'none', svgStrokeData: () => null, outlineData: f.read,
  });
  for (const side of ['Top', 'Right', 'Bottom', 'Left']) {
    f.style['border' + side + 'Width'] = '0px'; f.style['border' + side + 'Style'] = 'none'; f.style['border' + side + 'Color'] = 'rgb(143, 140, 134)';
  }
  const result = normalize(read(f.owner, f.style, false));
  assert.equal(result.border_width, 0); assert.deepEqual(result.border_widths, [0, 0, 0, 0]);
  assert.deepEqual(result.border_styles, ['none', 'none', 'none', 'none']);
  assert.equal(result.outline.width, 1.5); assert.equal(result.outline.offset, -1.5); assert.equal(result.outline.contour, null);
});

test('a real outline-only DOM box remains a painted element rather than a layout-only wrapper', () => {
  const f = outlineFixture();
  f.owner.localName = 'div'; f.owner.getAttribute = () => null; f.owner.matches = () => false;
  Object.assign(f.style, { backgroundColor: 'rgba(0,0,0,0)', boxShadow: 'none', backgroundImage: 'none' });
  for (const side of ['Top', 'Right', 'Bottom', 'Left']) f.style['border' + side + 'Width'] = '0px';
  const read = vm.runInNewContext('(' + expression('kindOf', 'semanticOwnerKinds') + ')', {
    document: { body: {} }, supplementalRegionEvidence: () => null, panelResizeEvidence: () => null,
    color: () => [0, 0, 0, 0], pathOf: () => '#actual-outline-owner', number: value => Number.parseFloat(value),
  });
  assert.equal(read(f.owner, f.style, null), 'card');
  f.style.outlineStyle = 'none'; assert.equal(read(f.owner, f.style, null), null);
});

test('current chart organization is distinct from selection and uses actual aria-current', () => {
  const read = vm.runInNewContext('(' + expression('stateOf', 'iconOf') + ')', { document: { activeElement: null }, panelResizeEvidence: () => null });
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
  const read = vm.runInNewContext('(' + expression('scrollbarEvidence', 'scrollbarGutter') + ')', {
    styleOf: context.styleOf, rect: box => ({ ...box }), pseudoByOwner: new WeakMap(),
    pathOf: () => '#actual-owner', snapshotBackend: new WeakMap(), computedSrgb: () => ({ rgba: null }),
    getComputedStyle: () => ({ display: 'inline', visibility: 'visible', opacity: '1', width: '10px', height: '10px' }),
  });
  const result = normalize(read(owner));
  assert.deepEqual(result.axes, ['vertical']); assert.equal(result.offset_width - result.client_width, 0);
  assert.equal(result.actual_ua_parts_presence, null); assert.equal(result.measured_part_bounds, null);
  assert.equal(result.measured_part_pixels, null);
});

const scrollbarGutter = vm.runInNewContext('(' + expression('scrollbarGutter', 'emitScrollbarParts') + ')');
const actualScrollOwner = () => ({ axes: ['vertical'], owner_backend_node_id: 171,
  owner_bounds: { x: 276, y: 96, width: 824, height: 698 }, client_width: 814, client_height: 698,
  client_left: 0, client_top: 0, offset_width: 824, offset_height: 698,
  scroll_width: 814, scroll_height: 907, scroll_left: 0, scroll_top: 209,
  writing_mode: 'horizontal-tb', direction: 'ltr',
  owner_style: { border_widths: ['0px', '0px', '0px', '0px'], flex_direction: 'column' },
  ancestry: [{ transform: 'none', perspective: 'none', zoom: '1' }],
  parts: [{ pseudo: '::-webkit-scrollbar', width: '10px', height: '10px' }, { pseudo: '::-webkit-scrollbar-thumb' }],
});

test('recorded reference gutter is measured from client/offset geometry without thumb ratios', () => {
  const actual = actualScrollOwner(), result = normalize(scrollbarGutter(actual, 'vertical'));
  assert.deepEqual(result.bounds, { x: 1090, y: 96, width: 10, height: 698 });
  assert.equal(result.side, 'right'); assert.equal(result.reason, null);
  actual.scroll_top = 0; actual.scroll_height = 4000;
  assert.deepEqual(normalize(scrollbarGutter(actual, 'vertical')).bounds, result.bounds, 'Scroll ratios cannot affect any measured gutter extent');
  actual.client_left = 10;
  assert.deepEqual(normalize(scrollbarGutter(actual, 'vertical')).bounds, { x: 276, y: 96, width: 10, height: 698 });
  actual.client_left = 0; actual.client_height = 688; actual.axes.push('horizontal');
  assert.deepEqual(normalize(scrollbarGutter(actual, 'horizontal')).bounds, { x: 276, y: 784, width: 814, height: 10 });
});

test('overlay, fractional, transformed and ambiguous reserved scrollbar geometry stays unknown', () => {
  for (const mutate of [
    value => { value.client_width = value.offset_width; },
    value => { value.owner_bounds.x += .5; },
    value => { value.ancestry[0].transform = 'matrix(1, 0, 0, 1, 1, 0)'; },
    value => { value.ancestry[0].zoom = '1.25'; },
    value => { value.writing_mode = 'vertical-rl'; },
    value => { value.client_left = 5; },
    value => { value.parts[0].width = 'auto'; },
    value => { value.client_height = 0; },
  ]) {
    const actual = actualScrollOwner(); mutate(actual);
    const result = normalize(scrollbarGutter(actual, 'vertical'));
    assert.equal(result.bounds, null); assert.ok(result.reason);
  }
});

test('unmeasured scrollbar thumb is emitted and fails instead of inheriting gutter or ratio bounds', () => {
  const items = [], errors = [], gaps = [], slots = new WeakMap();
  const emit = vm.runInNewContext('(' + expression('emitScrollbarParts', 'readingOrderIds') + ')', {
    elements: items, extraction_errors: errors, unmeasured: gaps, scrollbarOrder: slots, scrollbarGutter,
    regionOf: () => 'conversation', pathOf: () => '#stream', visibleRect: (_, box) => box,
    fragmentsOf: (_, box) => [box], occlusionMasks: new WeakMap(),
  });
  const owner = {}, raw = { id: 'dom-171', emitted: [] }, actual = actualScrollOwner();
  emit(owner, raw, actual, 'dom-170');
  const [bar, thumb] = normalize(items);
  assert.deepEqual(bar.bounds, { x: 1090, y: 96, width: 10, height: 698 });
  assert.equal(thumb.bounds, null); assert.equal(thumb.evidence.outer_bounds, null);
  assert.equal(thumb.evidence.hit_bounds, null); assert.equal(thumb.evidence.ink_bounds, null);
  assert.equal(thumb.style.background, null); assert.equal(thumb.state.hovered, null);
  assert.equal(thumb.state.orientation, 'vertical'); assert.equal(thumb.state.scroll_position, 1);
  assert.equal(thumb.name, null, 'An unexposed UA accessible name is not invented');
  assert.deepEqual(raw.emitted, items.map(item => item.id)); assert.equal(errors.length, 2); assert.equal(gaps.length, 2);
  assert.deepEqual(normalize(slots.get(owner)), items.map(item => item.id));
});

test('unresolved overlay ordering prevents scrollbar PNG attribution without discarding raw geometry', () => {
  const items = [], errors = [], gaps = [{ element: 'dom-171', property: 'visibility.paint_order', reason: 'Actual overlay ordering is unavailable' }];
  const emit = vm.runInNewContext('(' + expression('emitScrollbarParts', 'readingOrderIds') + ')', {
    elements: items, extraction_errors: errors, unmeasured: gaps, scrollbarOrder: new WeakMap(), scrollbarGutter,
    regionOf: () => 'conversation', pathOf: () => '#stream', visibleRect: (_, box) => box,
    fragmentsOf: (_, box) => [box], occlusionMasks: new WeakMap(),
  });
  const actual = actualScrollOwner();
  emit({}, { id: 'dom-171', emitted: [] }, actual, 'dom-170');
  assert.equal(actual.gutters.vertical.fully_visible, false);
  assert.deepEqual(normalize(actual.gutters.vertical.bounds), { x: 1090, y: 96, width: 10, height: 698 });
  assert.equal(actual.gutters.vertical.visibility_gaps[0].property, 'visibility.paint_order');
});

test('actual scrollbar part slots follow their owner content without erasing DOM children', () => {
  const owner = readingElement(readingText()), ids = new Map([[owner, 'owner']]);
  const slots = new WeakMap([[owner, ['owner:scrollbar:vertical', 'owner:scrollbar-thumb:vertical']]]);
  assert.deepEqual(normalize(readingOrderIds(owner, ids, slots)), ['owner', 'owner::marker', 'owner::before',
    'owner:text-0', 'owner::after', 'owner:scrollbar:vertical', 'owner:scrollbar-thumb:vertical']);
});

const panelResizeDocument = { body: { classList: { contains: () => false } }, activeElement: null };
const panelResizeMeta = { panel_listeners: { source: 'CDP.DOMDebugger.getEventListeners', owner: { backendNodeId: 902, nodeType: 1 },
  listeners: [{ type: 'pointerdown', backendNodeId: 902, useCapture: false, scriptId: 'actual-script', lineNumber: 1452 }], errors: [] } };
const panelResizeEvidence = vm.runInNewContext('(' + expression('panelResizeEvidence', 'supplementalRegionEvidence') + ')', {
  document: panelResizeDocument, styleOf: el => el.style, rect: value => value,
  meta: panelResizeMeta, snapshotBackend: { get: el => el.backendNodeId },
});
const supplementalRegionEvidence = vm.runInNewContext('(' + expression('supplementalRegionEvidence', 'kindOf') + ')', {
  accessibilityOf: owner => owner.accessibility,
});
const kindOf = vm.runInNewContext('(' + expression('kindOf', 'semanticOwnerKinds') + ')', {
  supplementalRegionEvidence, panelResizeEvidence, document: { body: {} },
  color: value => value === 'rgba(0, 0, 0, 0)' ? [0, 0, 0, 0] : [248, 247, 245, 255],
  number: value => parseFloat(value) || 0, pathOf: () => '#fixture-owner', textNodes: () => [],
});
const regionOwner = (values = {}) => ({
  localName: 'div', tabIndex: -1, attrs: {}, selectors: new Set(),
  clientWidth: 824, clientHeight: 698, scrollWidth: 824, scrollHeight: 698, scrollLeft: 0, scrollTop: 0,
  accessibility: { measured: true, ignored: false, role: 'generic', name: '', properties: [] },
  getAttribute(name) { return this.attrs[name] ?? null; },
  matches(selectors) { return selectors.split(',').some(selector => this.selectors.has(selector.trim())); },
  getBoundingClientRect: () => ({ x: 276, y: 96, width: 824, height: 698 }), ...values,
});
const regionStyle = (values = {}) => ({
  backgroundColor: 'rgba(0, 0, 0, 0)', boxShadow: 'none', backgroundImage: 'none', overflowX: 'hidden', overflowY: 'auto',
  ...Object.fromEntries(['Top', 'Right', 'Bottom', 'Left'].flatMap(side => [
    ['border' + side + 'Width', '0px'], ['border' + side + 'Style', 'none']])), ...values,
});

test('real panel pointer handle is retained even with an idle transparent background', () => {
  const owner = regionOwner({ selectors: new Set(['#panel > .pane-resize']), attrs: { title: 'Drag to resize' },
    style: { cursor: 'col-resize' }, onpointerdown: null, backendNodeId: 902,
    getBoundingClientRect: () => ({ x: 1100, y: 36, width: 5, height: 864 }) });
  const evidence = normalize(panelResizeEvidence(owner));
  assert.equal(kindOf(owner, regionStyle()), 'resize-handle');
  assert.deepEqual(evidence.bounds, { x: 1100, y: 36, width: 5, height: 864 });
  assert.equal(evidence.title, 'Drag to resize'); assert.equal(evidence.has_pointer_handler, true);
  assert.deepEqual(evidence.pointer_state, { hovered: false, active: false, body_resizing: false });
  owner.selectors.add(':hover');
  assert.equal(panelResizeEvidence(owner).pointer_state.hovered, true);
  assert.equal(kindOf(owner, regionStyle({ backgroundColor: 'rgb(248, 247, 245)' })), 'resize-handle', 'Hover paint does not turn the real control into a card');
  assert.equal(evidence.pointer_handler_property_type, 'object', 'addEventListener does not populate an IDL onpointerdown property');
  owner.backendNodeId = 903;
  assert.equal(panelResizeEvidence(owner).has_pointer_handler, null, 'Another node listener receipt cannot establish this handle interaction');
  assert.equal(kindOf(owner, regionStyle()), 'resize-handle', 'Missing listener coverage is a failure, not a reason to omit the real element');
});

test('panel handle enabled, focused and hover state come from the actual control', () => {
  const read = vm.runInNewContext('(' + expression('stateOf', 'iconOf') + ')', {
    document: panelResizeDocument, panelResizeEvidence,
  });
  const owner = regionOwner({ selectors: new Set(['#panel > .pane-resize', ':hover']),
    style: { cursor: 'col-resize' }, backendNodeId: 902, onpointerdown: null, hasAttribute: () => false, classList: { contains: () => false } });
  const state = normalize(read(owner));
  assert.equal(state.enabled, true); assert.equal(state.focused, false); assert.equal(state.hovered, true);
  assert.equal(state.selected, null); assert.equal(state.expanded, null);
});

test('recorded named navigation becomes a region from its own DOM and actual AX evidence', () => {
  // 5ff6706/reference-macos/en-US-light-1440x900-group: dom-56 was raw-only.
  const owner = regionOwner({ localName: 'nav', attrs: { 'aria-label': 'Organizations' },
    accessibility: { measured: true, ignored: false, backend_node_id: 108, node_ids: ['108'],
      role: 'navigation', name: 'Organizations', properties: [] } });
  const evidence = normalize(supplementalRegionEvidence(owner, regionStyle()));
  assert.equal(evidence.reason, 'named-navigation');
  assert.equal(evidence.dom_tag, 'nav'); assert.equal(evidence.dom_role, null);
  assert.equal(evidence.accessibility.name, 'Organizations');
  assert.equal(evidence.accessibility.backend_node_id, 108);
  assert.equal(kindOf(owner, regionStyle()), 'region');
  owner.localName = 'section'; owner.attrs.role = 'navigation';
  assert.equal(kindOf(owner, regionStyle()), 'region', 'Explicit live navigation semantics also qualify');
});

test('recorded focusable scrollport is retained independently of unknown scrollbar parts', () => {
  // 5ff6706/reference-macos/en-US-light-1440x900-group: dom-171/#stream.
  const owner = regionOwner({ attrs: { tabindex: '0' }, tabIndex: 0, scrollHeight: 969, scrollTop: 271,
    accessibility: { measured: true, ignored: false, backend_node_id: 9, node_ids: ['9'], role: 'generic', name: '',
      properties: [{ name: 'focusable', value: { type: 'booleanOrUndefined', value: true } }] } });
  const evidence = normalize(supplementalRegionEvidence(owner, regionStyle()));
  assert.equal(evidence.reason, 'focusable-scroll-region'); assert.deepEqual(evidence.axes, ['vertical']);
  assert.equal(evidence.metrics.scroll_height, 969); assert.equal(evidence.metrics.client_height, 698);
  assert.equal(evidence.metrics.scroll_top, 271); assert.equal(evidence.dom_tabindex, '0');
  assert.equal(evidence.accessibility.properties[0].value.value, true);
  assert.equal(kindOf(owner, regionStyle()), 'region');
  assert.equal(evidence.measured_part_bounds, undefined, 'Region classification supplies no scrollbar geometry');
  owner.scrollWidth = 900; owner.scrollHeight = 698;
  assert.deepEqual(normalize(supplementalRegionEvidence(owner, regionStyle({ overflowX: 'scroll' })).axes), ['horizontal']);
});

test('navigation requires a live semantic role and an independently measured nonempty AX name', () => {
  for (const invalid of [{ measured: false }, { ignored: true }, { role: 'generic' }, { name: '' }, { name: ' ' }]) {
    const owner = regionOwner({ localName: 'nav', attrs: { 'aria-label': 'Expected-looking name' },
      accessibility: { measured: true, ignored: false, role: 'navigation', name: 'Actual name', properties: [], ...invalid } });
    assert.equal(supplementalRegionEvidence(owner, regionStyle()), null);
    assert.equal(kindOf(owner, regionStyle()), null);
  }
  const generic = regionOwner({ accessibility: { measured: true, ignored: false, role: 'navigation', name: 'Name', properties: [] } });
  assert.equal(kindOf(generic, regionStyle()), null, 'AX role alone does not replace missing DOM semantic evidence');
});

test('scroll metrics or tabindex alone cannot invent an interactive region', () => {
  const valid = () => regionOwner({ attrs: { tabindex: '0' }, tabIndex: 0, scrollHeight: 969,
    accessibility: { measured: true, ignored: false, role: 'generic', name: '',
      properties: [{ name: 'focusable', value: { value: true } }] } });
  for (const mutate of [
    owner => { owner.attrs = {}; }, owner => { owner.tabIndex = -1; },
    owner => { owner.attrs.tabindex = '-1'; }, owner => { owner.scrollHeight = owner.clientHeight; },
    owner => { owner.clientHeight = 0; }, owner => { owner.scrollHeight = NaN; },
    owner => { owner.accessibility.measured = false; }, owner => { owner.accessibility.ignored = true; },
    owner => { owner.accessibility.properties = []; },
    owner => { owner.accessibility.properties[0].value.value = false; },
  ]) {
    const owner = valid(); mutate(owner);
    assert.equal(supplementalRegionEvidence(owner, regionStyle()), null);
    assert.equal(kindOf(owner, regionStyle()), null);
  }
  assert.equal(kindOf(valid(), regionStyle({ overflowY: 'hidden' })), null, 'Clipped overflow is not independent user scrolling');
});

test('supplemental regions add missing elements without replacing existing semantic or painted kinds', () => {
  const owner = regionOwner({ attrs: { tabindex: '0' }, tabIndex: 0, scrollHeight: 969,
    accessibility: { measured: true, ignored: false, role: 'generic', name: '',
      properties: [{ name: 'focusable', value: { value: true } }] } });
  assert.equal(kindOf(owner, regionStyle()), 'region');
  assert.equal(kindOf(owner, regionStyle({ backgroundColor: 'rgb(248, 247, 245)' })), 'card');
  owner.localName = 'button'; assert.equal(kindOf(owner, regionStyle()), 'icon-button');
  owner.localName = 'pre'; assert.equal(kindOf(owner, regionStyle()), 'code');
  owner.localName = 'div'; owner.selectors.add('.chat-row'); assert.equal(kindOf(owner, regionStyle()), 'list-row');
});
