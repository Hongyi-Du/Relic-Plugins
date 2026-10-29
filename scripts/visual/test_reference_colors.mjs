// CI-only pure tests of the production computed-color parser and recorder.
// The Canvas fixture supplies a separate recorded pixel, never a color parser.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('./reference-elements.js', import.meta.url), 'utf8');
const expression = (name, next) => {
  const start = source.indexOf('  const ' + name + ' = ');
  const end = source.indexOf('  const ' + next + ' = ', start);
  assert.ok(start >= 0 && end > start, 'Tests evaluate the actual production function');
  return source.slice(start + ('  const ' + name + ' = ').length, end).trim().replace(/;$/, '');
};
const normalize = value => JSON.parse(JSON.stringify(value));
const computedSrgb = vm.runInNewContext('(' + expression('computedSrgb', 'color') + ')');
const rgba = value => normalize(computedSrgb(value).rgba);
const recorder = ({ pixels = [255, 127, 64, 18], supported = true, failReadback = false } = {}) => {
  const colors = new Map(), extraction_errors = [], reads = [];
  const colorContext = {
    clearRect() {}, fillRect() {},
    getImageData() {
      reads.push(this.fillStyle);
      if (failReadback) throw new Error('Recorded Canvas readback failure');
      return { data: Uint8ClampedArray.from(pixels), colorSpace: 'srgb' };
    },
  };
  const color = vm.runInNewContext('(' + expression('color', 'number') + ')', {
    computedSrgb, colors, extraction_errors, colorContext, CSS: { supports: () => supported },
  });
  return { color, colors, extraction_errors, reads };
};

test('computed RGB preserves unpremultiplied fractional channels and alpha', () => {
  assert.deepEqual(rgba('rgba(255, 127.5, 64, 0.07)'), [255, 127.5, 64, 0.07 * 255]);
  assert.deepEqual(rgba('rgb(17.85 128.125 255 / .5)'), [17.85, 128.125, 255, 127.5]);
  assert.deepEqual(rgba('rgba(255 128 64)'), [255, 128, 64, 255]);
  assert.deepEqual(rgba('rgb(255, 128, 64)'), [255, 128, 64, 255]);
});

test('computed percentages and color(srgb) scale without pixel quantization', () => {
  assert.deepEqual(rgba('rgb(100%, 50%, 25%, 7%)'), [255, 127.5, 63.75, 7 / 100 * 255]);
  assert.deepEqual(rgba('rgb(255 50% 64 / 7%)'), [255, 127.5, 64, 7 / 100 * 255]);
  assert.deepEqual(rgba('color(srgb 1 .5 .25 / .07)'), [255, 127.5, 63.75, .07 * 255]);
  assert.deepEqual(rgba('color(srgb 100% 50% 25% / 7%)'), [255, 127.5, 63.75, 7 / 100 * 255]);
  assert.deepEqual(rgba('color(srgb 1e0 5e-1 2.5e-1 / 7e-2)'), [255, 127.5, 63.75, .07 * 255]);
});

test('absent and transparent paint are explicit values, while missing values fail', () => {
  assert.deepEqual(rgba('none'), [0, 0, 0, 0]);
  assert.deepEqual(rgba(' transparent '), [0, 0, 0, 0]);
  for (const value of [undefined, null, '', ' ', 0]) {
    const result = computedSrgb(value);
    assert.equal(result.rgba, null); assert.ok(result.reason);
  }
});

test('out-of-range channels and alpha are not clamped or silently accepted', () => {
  for (const value of ['rgb(256 0 0)', 'rgb(-.001 0 0)', 'rgb(101% 0% 0%)',
    'rgba(0, 0, 0, 1.0000000001)', 'rgb(0 0 0 / -.001)', 'rgb(0 0 0 / 100.0001%)',
    'color(srgb 1.0000000001 0 0)', 'color(srgb 0 -.001 0)', 'rgb(1e999 0 0)']) {
    assert.equal(computedSrgb(value).rgba, null, value);
  }
});

test('unsupported color spaces and unresolved expressions are not inferred as sRGB', () => {
  for (const value of ['color(display-p3 1 0 0)', 'color(srgb-linear 1 0 0)', 'lab(50% 0 0)',
    'oklch(.5 .2 30)', 'hsl(0 100% 50%)', 'red', '#ff0000', 'currentColor',
    'var(--color)', 'rgb(calc(255) 0 0)', 'rgb(none 0 0)', 'color(srgb 1 none 0)']) {
    assert.equal(computedSrgb(value).rgba, null, value);
  }
});

test('invalid computed component grammar cannot yield partial numeric parses', () => {
  for (const value of ['rgb(1px 2 3)', 'rgb(1 2)', 'rgba(1, 2, 3,)', 'rgb(1, 2, 3 / .5)',
    'rgb(1% , 2, 3)', 'rgb(1 2 3 /)', 'rgb(1 2 3 / .5 / .5)', 'color(srgb 1, 0, 0)',
    'rgb(NaN 0 0)', 'rgb(Infinity 0 0)', 'rgb(1. 0 0)']) {
    assert.equal(computedSrgb(value).rgba, null, value);
  }
});

test('tiny measured serialization differences remain different without epsilon', () => {
  const low = rgba('rgba(0, 0, 0, .07)'), high = rgba('rgba(0, 0, 0, .0700000001)');
  assert.equal(low[3], .07 * 255); assert.equal(high[3], .0700000001 * 255);
  assert.notEqual(low[3], high[3]);
});

test('Canvas RGBA8 is preserved independently and never supplies canonical channels', () => {
  const read = recorder();
  const raw = 'rgba(255, 127.5, 64, 0.07)';
  assert.deepEqual(normalize(read.color(raw, '#actual-card', 'background-color')), [255, 127.5, 64, .07 * 255]);
  const evidence = normalize(read.colors.get(raw));
  assert.equal(evidence.computed, raw);
  assert.deepEqual(evidence.canvas.rgba, [255, 127, 64, 18]);
  assert.equal(evidence.canvas.quantity, 'canvas-raster-rgba8-0-255');
  assert.equal(evidence.canonical.quantity, 'computed-unpremultiplied-srgb-rgba-float-0-255');
  assert.deepEqual(evidence.sources, [{ node: '#actual-card', property: 'background-color', pseudo: null, computed_value: raw }]);
  assert.deepEqual(read.extraction_errors, []);
});

test('a cached color retains every actual node, property, pseudo and compound value', () => {
  const read = recorder(), raw = 'rgba(0, 0, 0, 0.07)';
  read.color(raw, '#one', 'background-color');
  read.color(raw, '#one', 'background-color');
  read.color(raw, '#two', 'box-shadow', '::before', raw + ' 0px 1px 2px');
  const evidence = normalize(read.colors.get(raw));
  assert.equal(read.reads.length, 1); assert.equal(evidence.sources.length, 2);
  assert.deepEqual(evidence.sources[1], { node: '#two', property: 'box-shadow', pseudo: '::before', computed_value: raw + ' 0px 1px 2px' });
});

test('a browser-readable unsupported gamut remains null and errors at each actual source', () => {
  const read = recorder({ pixels: [255, 0, 0, 255] }), raw = 'color(display-p3 1 0 0)';
  assert.equal(read.color(raw, '#one', 'color'), null);
  assert.equal(read.color(raw, '#two', 'border-top-color', '::after'), null);
  assert.equal(read.color(raw, '#one', 'color'), null);
  assert.deepEqual(normalize(read.colors.get(raw).canvas.rgba), [255, 0, 0, 255]);
  assert.equal(read.extraction_errors.length, 2);
  assert.deepEqual(read.extraction_errors.map(error => error.node), ['#one', '#two']);
  assert.equal(read.extraction_errors[1].property, 'border-top-color');
  assert.equal(read.extraction_errors[1].pseudo, '::after');
});

test('Canvas readback failure has its own evidence and does not replace computed color', () => {
  const read = recorder({ failReadback: true }), raw = 'rgba(0, 0, 0, .07)';
  assert.deepEqual(normalize(read.color(raw, '#one', 'color')), [0, 0, 0, .07 * 255]);
  const evidence = read.colors.get(raw);
  assert.equal(evidence.canvas.status, 'unavailable'); assert.equal(evidence.canvas.rgba, null);
  assert.match(evidence.canvas.reason, /Recorded Canvas readback failure/);
  assert.deepEqual(read.extraction_errors, []);
});

test('none has no fabricated pixel sample and unsupported input still records its failure', () => {
  const read = recorder({ supported: false });
  assert.deepEqual(normalize(read.color('none', '#actual-path', 'fill')), [0, 0, 0, 0]);
  assert.equal(read.colors.get('none').canvas.status, 'not-applicable');
  assert.equal(read.colors.get('none').canvas.rgba, null);
  assert.equal(read.color('rgb(unknown 0 0)', '#actual-path', 'stroke'), null);
  assert.equal(read.colors.get('rgb(unknown 0 0)').canvas.status, 'unavailable');
  assert.equal(read.extraction_errors.length, 1); assert.deepEqual(read.reads, []);
});
