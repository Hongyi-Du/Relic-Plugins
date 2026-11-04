// Pure CI fixtures: no browser, font shaping, or replacement marker drawing.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('./reference-elements.js', import.meta.url), 'utf8');
const recorded = JSON.parse(readFileSync(new URL('./fixtures/marker_disc_1ffe201.json', import.meta.url), 'utf8'));
const expression = (name, next) => {
  const prefix = '  const ' + name + ' = ';
  const start = source.indexOf(prefix), end = source.indexOf('  const ' + next + ' = ', start);
  assert.ok(start >= 0 && end > start, 'Exercise actual production helper source');
  return source.slice(start + prefix.length, end).trim().replace(/;$/, '');
};
const classify = vm.runInNewContext('(' + expression('markerSymbolEvidence', 'applyMarkerSymbolEvidence') + ')');
const apply = vm.runInNewContext('(' + expression('applyMarkerSymbolEvidence', 'suppressedText') + ')');
const normalized = value => JSON.parse(JSON.stringify(value));
// These CSS inputs are synthetic independent configurations, not claimed old capture fields.
const ownerStyle = { display: 'list-item', listStyleType: 'disc', listStyleImage: 'none', listStylePosition: 'outside' };
const pseudoStyle = { content: 'normal', display: 'inline', color: 'rgb(26, 25, 22)', fontSize: '14px' };
const counterStyles = { source: 'synthetic CSSOM fixture', rules: [], errors: [] };
const candidate = (owner = ownerStyle, pseudo = pseudoStyle, browser = recorded.browser, counters = counterStyles) =>
  normalized(classify('::marker', owner, pseudo, recorded.snapshot, browser, counters));

test('recorded alternative marker text and both DOM boxes do not become an ellipse rectangle', () => {
  const result = candidate();
  assert.equal(result.primitive, 'ellipse');
  assert.equal(result.paint_operation, 'FillEllipse');
  assert.equal(result.alternative_text, '• ');
  assert.deepEqual(result.layout_outer_bounds, recorded.snapshot.bounds);
  assert.deepEqual(result.alternative_text_bounds, recorded.snapshot.text_element_bounds);
  assert.equal(result.bounds, null);
  assert.equal(result.visible_bounds, null);
  assert.equal(result.radius, null);
  assert.equal(result.path, null);
  assert.equal(result.paint, null);
  assert.equal(result.pixels, null);
});

test('symbol projection keeps actual AX name/identity and every recorded box while failing paint coverage', () => {
  const prior = recorded.old_projection;
  const item = { ...structuredClone(prior), visible_bounds: structuredClone(prior.bounds),
    style: { foreground: [26, 25, 22, 255], background: [0, 0, 0, 0], corner_radius: 0 },
    layout: {}, evidence: { accessibility: recorded.accessibility, text_bounds: [prior.bounds], text_layout_bounds: [prior.bounds], text_bounds_quantity: 'old-alternative-text-layout' } };
  const gaps = [{ element: 'unrelated', property: 'existing' }], errors = [{ type: 'existing' }];
  apply(item, candidate(), gaps, errors);
  assert.equal(item.id, prior.id);
  assert.equal(item.kind, 'icon');
  assert.equal(item.name, '• ');
  assert.equal(item.text, '');
  assert.equal(item.icon.source, 'geometry');
  assert.equal(item.icon.glyph, null);
  assert.equal(item.icon.primitive, 'ellipse');
  assert.deepEqual(normalized(item.bounds), { x: null, y: null, width: null, height: null });
  assert.deepEqual(item.evidence.marker_symbol.accessibility, recorded.accessibility);
  assert.deepEqual(item.evidence.marker_symbol.layout_rows, recorded.snapshot.layout_rows);
  assert.deepEqual(item.evidence.marker_symbol.alternative_text_fragments, recorded.snapshot.text_fragments);
  assert.deepEqual(item.evidence.marker_symbol.prior_projection.bounds, prior.bounds);
  assert.equal(item.style.foreground, null);
  assert.equal(item.style.background, null);
  assert.equal(item.style.corner_radius, null);
  assert.equal(gaps.length, 4);
  assert.equal(errors.length, 4);
  assert.equal(gaps[0].property, 'existing');
  assert.equal(errors[0].type, 'existing');
});

test('circle and square preserve distinct native engine operations without deriving dimensions', () => {
  for (const [type, primitive, operation] of [['circle', 'ellipse', 'StrokeEllipse'], ['square', 'rect', 'FillRect']]) {
    const result = candidate({ ...ownerStyle, listStyleType: type });
    assert.equal(result.primitive, primitive);
    assert.equal(result.paint_operation, operation);
    assert.equal(result.bounds, null);
    assert.equal(result.paint, null);
  }
});

test('custom marker content, image markers, decimal and nonmarker pseudos are not reclassified as symbols', () => {
  assert.equal(candidate(ownerStyle, { ...pseudoStyle, content: '"• "' }), null);
  assert.equal(candidate({ ...ownerStyle, listStyleImage: 'url(actual.png)' }), null);
  assert.equal(candidate({ ...ownerStyle, listStyleType: 'decimal' }), null);
  assert.equal(classify('::before', ownerStyle, pseudoStyle, recorded.snapshot, recorded.browser, counterStyles), null);
});

test('unverified engine or inaccessible/custom counter styles do not fabricate known paint branches', () => {
  for (const result of [candidate(ownerStyle, pseudoStyle, { name: 'Chromium', version: '157.0' }),
    candidate(ownerStyle, pseudoStyle, recorded.browser, { rules: [], errors: [{ error: 'SecurityError' }] }),
    candidate(ownerStyle, pseudoStyle, recorded.browser, { rules: [{ name: 'disc', css_text: '@counter-style disc {}' }], errors: [] })]) {
    assert.equal(result.classification_verified, false);
    assert.equal(result.primitive, null);
    assert.equal(result.paint_operation, null);
    assert.equal(result.bounds, null);
    const item = { id: 'actual-marker', text: '', bounds: null, visible_bounds: null, style: {}, layout: {}, icon: null, evidence: {} };
    const gaps = [], errors = [];
    apply(item, result, gaps, errors);
    assert.equal(gaps.length, 4);
    assert.equal(errors.length, 4);
    assert.equal(errors.at(-1).type, 'marker_symbol_classification_unmeasured');
  }
});

test('actual CSSOM traversal retains custom definitions and unreadable imported sheet errors', () => {
  const blocked = { href: 'https://other.invalid/style.css', get cssRules() { throw new Error('SecurityError'); } };
  const custom = { name: 'disc', cssText: '@counter-style disc { system: cyclic; symbols: X; }' };
  const adopted = { href: null, cssRules: [{ cssText: '@media print {}', cssRules: [custom] }] };
  const sheet = { href: 'http://127.0.0.1/app.css', cssRules: [{ cssText: '@import url(other.css)', styleSheet: blocked }] };
  const read = vm.runInNewContext('(' + expression('markerCounterStyles', 'markerSymbolEvidence') + ')', {
    document: { styleSheets: [sheet], adoptedStyleSheets: [adopted] },
  });
  const actual = normalized(read());
  assert.equal(actual.rules[0].name, 'disc');
  assert.match(actual.rules[0].css_text, /symbols: X/);
  assert.match(actual.errors[0].error, /SecurityError/);
});

test('the full production collector remains syntactically valid and the new fixtures are in the CI entrypoint', () => {
  new vm.Script('(' + source + ')');
  const main = readFileSync(new URL('./test_reference_elements.mjs', import.meta.url), 'utf8');
  assert.match(main, /import '\.\/test_reference_markers\.mjs'/);
  assert.match(source, /applyMarkerSymbolEvidence\(elements\[elements\.length - 1\], symbol, unmeasured, extraction_errors\)/);
});
