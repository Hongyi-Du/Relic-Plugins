// Read-only extraction of the rendered production DOM. No reference fixture or
// native element data is used to manufacture counterpart elements.
(meta) => {
  'use strict';
  const elements = [], raw_nodes = [], extraction_errors = [], unmeasured = [];
  for (const error of meta.input_text_errors || []) extraction_errors.push({ type: 'input_text_capture_error', detail: error });
  const viewport = { width: innerWidth, height: innerHeight, scale: devicePixelRatio };
  const nodeIds = new WeakMap(), emittedIds = new WeakMap(), styles = new WeakMap(), occlusionMasks = new WeakMap(), scrollbarOrder = new WeakMap();
  const colorCanvas = new OffscreenCanvas(1, 1);
  const colorContext = colorCanvas.getContext('2d', { willReadFrequently: true, colorSpace: 'srgb' });
  const colors = new Map(), regionOrders = new Map();
  const rect = r => ({ x: r.x, y: r.y, width: r.width, height: r.height });
  const intersect = (a, b) => {
    const x = Math.max(a.x, b.x), y = Math.max(a.y, b.y);
    return { x, y, width: Math.max(0, Math.min(a.x + a.width, b.x + b.width) - x), height: Math.max(0, Math.min(a.y + a.height, b.y + b.height) - y) };
  };
  const nonempty = r => r.width > 0 && r.height > 0;
  const styleOf = el => {
    if (!styles.has(el)) styles.set(el, getComputedStyle(el));
    return styles.get(el);
  };
  // Computed colors and Canvas pixels are different quantities. Preserve the
  // serialized sRGB channels without raster quantization or premultiplication.
  const computedSrgb = css => {
    const fail = reason => ({ rgba: null, reason });
    if (typeof css !== 'string' || !css.trim()) return fail('Missing computed color.');
    const value = css.trim().toLowerCase();
    if (value === 'none' || value === 'transparent') return { rgba: [0, 0, 0, 0], reason: null };
    const fn = value.match(/^(rgb|rgba|color)\(([\s\S]*)\)$/);
    if (!fn) return fail('Computed color is not an explicitly supported sRGB serialization.');
    let body = fn[2].trim(), scale = 255, channels, alpha;
    if (fn[1] === 'color') {
      const space = body.match(/^srgb\s+([\s\S]+)$/);
      if (!space) return fail('Only computed color(srgb ...) has a directly measured sRGB representation.');
      body = space[1]; scale = 1;
    }
    if (body.includes(',')) {
      if (fn[1] === 'color' || body.includes('/')) return fail('Invalid computed color component separators.');
      const parts = body.split(',').map(part => part.trim());
      if (parts.length !== 3 && parts.length !== 4) return fail('Invalid computed RGB component count.');
      channels = parts.slice(0, 3); alpha = parts[3];
      if (channels.some(part => part.endsWith('%')) && !channels.every(part => part.endsWith('%')))
        return fail('Legacy computed RGB mixes number and percentage channels.');
    } else {
      const parts = body.split('/');
      if (parts.length > 2) return fail('Invalid computed color alpha separator.');
      channels = parts[0].trim().split(/\s+/); alpha = parts.length === 2 ? parts[1].trim() : undefined;
      if (channels.length !== 3) return fail('Invalid computed color component count.');
    }
    const component = (part, maximum) => {
      if (typeof part !== 'string' || !/^[+-]?(?:\d*\.\d+|\d+)(?:e[+-]?\d+)?%?$/.test(part)) return null;
      const percentage = part.endsWith('%'), channel = Number(percentage ? part.slice(0, -1) : part);
      const limit = percentage ? 100 : maximum;
      if (!Number.isFinite(channel) || channel < 0 || channel > limit) return null;
      // RGB numbers already use 0..255. Preserve them directly, without an
      // unnecessary divide/multiply rounding step.
      return !percentage && maximum === 255 ? channel : channel / limit * 255;
    };
    const rgb = channels.map(part => component(part, scale));
    const opacity = alpha === undefined ? 255 : component(alpha, 1);
    if (rgb.includes(null) || opacity === null) return fail('Computed color has an unknown, non-finite, or out-of-range component.');
    return { rgba: [...rgb, opacity], reason: null };
  };
  const color = (css, path, property, pseudo = null, computedValue = css) => {
    let record = colors.get(css);
    if (!record) {
      const canonical = computedSrgb(css);
      let raster = { status: 'unavailable', rgba: null, color_space: null };
      if (typeof css === 'string' && css.trim().toLowerCase() === 'none') {
        raster = { ...raster, status: 'not-applicable', reason: 'none denotes absent paint, not a Canvas fill color.' };
      } else if (!colorContext || typeof css !== 'string' || !CSS.supports('color', css)) {
        raster.reason = 'A Canvas sRGB readback is unavailable for this computed value.';
      } else {
        try {
          colorContext.clearRect(0, 0, 1, 1);
          colorContext.fillStyle = css;
          colorContext.fillRect(0, 0, 1, 1);
          const pixels = colorContext.getImageData(0, 0, 1, 1);
          raster = { status: 'measured', rgba: Array.from(pixels.data), color_space: pixels.colorSpace ?? null };
        } catch (error) { raster.reason = String(error); }
      }
      record = { computed: css ?? null,
        canonical: { quantity: 'computed-unpremultiplied-srgb-rgba-float-0-255', ...canonical },
        canvas: { quantity: 'canvas-raster-rgba8-0-255', ...raster }, sources: [] };
      colors.set(css, record);
    }
    const source = { node: path, property, pseudo, computed_value: computedValue ?? null };
    if (!record.sources.some(item => item.node === path && item.property === property && item.pseudo === pseudo && item.computed_value === source.computed_value)) {
      record.sources.push(source);
      if (record.canonical.rgba === null) extraction_errors.push({ type: 'color_unreadable', ...source, value: css ?? null, reason: record.canonical.reason });
    }
    return record.canonical.rgba;
  };
  const number = value => Number.isFinite(parseFloat(value)) ? parseFloat(value) : null;
  const radius = (value, el, measuredBox = null) => {
    const parts = value.split(/\s+/), b = measuredBox || el.getBoundingClientRect();
    const px = (part, length) => part?.endsWith('%') ? (number(part) || 0) * length / 100 : number(part) || 0;
    return Math.max(px(parts[0], b.width), px(parts[1] || parts[0], b.height));
  };
  const hasClass = (el, list) => list.some(x => el.classList.contains(x));
  const pathOf = el => {
    if (el === document.body) return 'body';
    const parts = [];
    for (let p = el; p && p !== document.documentElement; p = p.parentElement) {
      if (p.id) { parts.unshift('#' + CSS.escape(p.id)); break; }
      let position = 1;
      for (let sibling = p.previousElementSibling; sibling; sibling = sibling.previousElementSibling) if (sibling.localName === p.localName) position++;
      parts.unshift(p.localName + ':nth-of-type(' + position + ')');
    }
    return parts.join(' > ');
  };
  // CDP supplies actual pseudo/UA-shadow layout boxes that the standard DOM
  // cannot expose. Resolve snapshot ancestry to real elements without adding
  // attributes or otherwise changing the page being measured.
  const pseudoLayoutMeasurement = (index, layout, document) => {
    const rows = layout.nodeIndex.flatMap((node, position) => {
      if (node !== index) return [];
      const raw = layout.bounds?.[position], valid = Array.isArray(raw) && raw.length === 4 && raw.every(Number.isFinite) && raw[2] >= 0 && raw[3] >= 0;
      return [{ layout_index: position, source_bounds: raw ?? null,
        bounds: valid ? { x: raw[0] - (document.scrollOffsetX || 0), y: raw[1] - (document.scrollOffsetY || 0), width: raw[2], height: raw[3] } : null,
        client_rect: layout.clientRects?.[position] ?? null, offset_rect: layout.offsetRects?.[position] ?? null,
        scroll_rect: layout.scrollRects?.[position] ?? null, paint_order: layout.paintOrders?.[position] ?? null,
        text_index: layout.text?.[position] ?? null }];
    });
    const positive = rows.filter(row => row.bounds?.width > 0 && row.bounds?.height > 0), groups = [];
    for (const row of positive) {
      const same = groups.find(group => ['x', 'y', 'width', 'height'].every(key => group[0].bounds[key] === row.bounds[key]));
      if (same) same.push(row); else groups.push([row]);
    }
    const problems = [];
    if (rows.some(row => !row.bounds)) problems.push({ property: 'pseudo.bounds', reason: 'An actual pseudo layout row has invalid bounds; no remaining row is selected as a substitute.' });
    else if (groups.length !== 1) problems.push({ property: 'pseudo.bounds', reason: groups.length ?
      'Actual pseudo layout has multiple distinct positive-area boxes; their union is not an independently measured pseudo rectangle.' :
      'No actual positive-area pseudo box is available; zero-area layout rows do not establish that visible pseudo paint is absent.' });
    const selected = problems.length ? [] : groups[0];
    const paintOrders = [...new Set(selected.map(row => row.paint_order))];
    const paintOrder = paintOrders.length === 1 ? paintOrders[0] : null;
    if (selected.length && paintOrder === null) problems.push({ property: 'pseudo.paint_order', reason: 'The actual positive pseudo layout rows have no single measured paint order.' });
    return { bounds: selected.length ? selected[0].bounds : null, layout_index: selected.length === 1 ? selected[0].layout_index : null,
      paint_order: paintOrder, layout_rows: rows, selected_layout_indices: selected.map(row => row.layout_index),
      layout_measurement: 'All actual CDP layout rows retained; only one distinct positive-area box may supply geometry, never last-row overwrite or a guessed union', problems };
  };
  const snapshot = meta.dom_snapshot, snapshotDocument = snapshot?.documents?.[0];
  const snapshotStrings = snapshot?.strings || [], snapshotNodes = snapshotDocument?.nodes;
  const snapshotLayout = snapshotDocument?.layout, snapshotTextBoxes = snapshotDocument?.textBoxes;
  const snapshotElements = new Map(), snapshotPseudo = new Map(), pseudoByOwner = new WeakMap();
  const snapshotInputBoxes = new WeakMap(), snapshotInputFontOwners = new WeakMap(), snapshotBackend = new WeakMap(), snapshotRenderedText = new WeakMap(), snapshotPaintOrder = new WeakMap();
  const snapshotTextLayouts = new WeakMap();
  // Reuse the actual pierced DOM receipt already captured for UA input text.
  // Internal select text/picker nodes are retained even when no independent
  // node represents the native theme's directly painted dropdown arrow.
  const piercedByBackend = new Map();
  const indexPierced = node => {
    if (!node) return;
    if (Number.isInteger(node.backendNodeId)) piercedByBackend.set(node.backendNodeId, node);
    for (const child of [...(node.children || []), ...(node.shadowRoots || []), ...(node.pseudoElements || [])]) indexPierced(child);
  };
  indexPierced(meta.pierced_dom?.root);
  const axByBackend = new Map(), raw_ax_nodes = meta.ax_tree?.nodes || [];
  const axById = new Map(raw_ax_nodes.map(node => [node.nodeId, node]));
  for (const ax of raw_ax_nodes) {
    if (ax.backendDOMNodeId === undefined) continue;
    const group = axByBackend.get(ax.backendDOMNodeId) || [];
    group.push(ax); axByBackend.set(ax.backendDOMNodeId, group);
  }
  if (!raw_ax_nodes.length) extraction_errors.push({ type: 'accessibility_tree_unavailable', reason: 'CDP Accessibility.getFullAXTree returned no nodes; computed names must not be guessed from title or innerText.' });
  if (snapshotNodes && snapshotLayout) {
    for (let i = 0; i < (snapshotNodes.pseudoType?.index?.length || 0); i++) snapshotPseudo.set(snapshotNodes.pseudoType.index[i], snapshotStrings[snapshotNodes.pseudoType.value[i]]);
    const elementChildren = new Map(), selectors = new Map();
    const nodeName = i => (snapshotStrings[snapshotNodes.nodeName[i]] || '').toLowerCase();
    for (let i = 0; i < snapshotNodes.nodeType.length; i++) {
      if (snapshotNodes.nodeType[i] !== Node.ELEMENT_NODE || snapshotPseudo.has(i)) continue;
      const parentIndex = snapshotNodes.parentIndex[i], tag = nodeName(i), attributes = snapshotNodes.attributes?.[i] || [];
      const attrs = {};
      for (let k = 0; k < attributes.length; k += 2) attrs[snapshotStrings[attributes[k]]] = snapshotStrings[attributes[k + 1]];
      const siblingKey = parentIndex + '/' + tag, position = (elementChildren.get(siblingKey) || 0) + 1;
      elementChildren.set(siblingKey, position);
      const selector = attrs.id ? '#' + CSS.escape(attrs.id) : tag === 'html' || tag === 'body' ? tag : selectors.has(parentIndex) ? selectors.get(parentIndex) + ' > ' + tag + ':nth-of-type(' + position + ')' : null;
      if (!selector) continue;
      selectors.set(i, selector);
      try {
        const actual = document.querySelector(selector);
        if (actual) { snapshotElements.set(i, actual); snapshotBackend.set(actual, snapshotNodes.backendNodeId?.[i]); }
      }
      catch { /* UA shadow nodes may have non-selector node names. */ }
    }
    const layoutByNode = new Map(snapshotLayout.nodeIndex.map((index, position) => [index, position]));
    for (const [index, actual] of snapshotElements) {
      const li = layoutByNode.get(index);
      if (li !== undefined && snapshotLayout.paintOrders?.[li] !== undefined) snapshotPaintOrder.set(actual, snapshotLayout.paintOrders[li]);
    }
    const snapshotRect = a => ({ x: a[0] - (snapshotDocument.scrollOffsetX || 0), y: a[1] - (snapshotDocument.scrollOffsetY || 0), width: a[2], height: a[3] });
    const textPositions = new Map();
    for (let i = 0; i < snapshotNodes.nodeType.length; i++) {
      if (snapshotNodes.nodeType[i] !== Node.TEXT_NODE) continue;
      const parentIndex = snapshotNodes.parentIndex[i], actualParent = snapshotElements.get(parentIndex);
      if (!actualParent) continue;
      const position = textPositions.get(parentIndex) || 0;
      textPositions.set(parentIndex, position + 1);
      const actual = Array.from(actualParent.childNodes).filter(n => n.nodeType === Node.TEXT_NODE)[position];
      // Verify the text identity too; a mismatch means the DOM changed between
      // snapshots, rather than permission to attach another node's AX name.
      if (actual && actual.nodeValue === (snapshotStrings[snapshotNodes.nodeValue[i]] || '')) {
        snapshotBackend.set(actual, snapshotNodes.backendNodeId?.[i]);
        const layoutIndex = layoutByNode.get(i);
        if (layoutIndex !== undefined) snapshotRenderedText.set(actual, snapshotStrings[snapshotLayout.text[layoutIndex]] || '');
        const layouts = snapshotLayout.nodeIndex.flatMap((nodeIndex, position) => nodeIndex === i ? [position] : []);
        snapshotTextLayouts.set(actual, { source: 'CDP.DOMSnapshot.captureSnapshot', backend_node_id: snapshotNodes.backendNodeId?.[i], node_index: i,
          layout_rows: layouts.map(position => ({ layout_index: position, text: snapshotStrings[snapshotLayout.text[position]] || '', bounds: snapshotRect(snapshotLayout.bounds[position]) })),
          text_boxes: (snapshotTextBoxes?.layoutIndex || []).flatMap((position, k) => layouts.includes(position)
            ? [{ layout_index: position, bounds: snapshotRect(snapshotTextBoxes.bounds[k]), start: snapshotTextBoxes.start[k], length: snapshotTextBoxes.length[k] }] : []),
          quantity: 'post-layout text fragments; not certified painted glyph ink or generated ellipsis geometry' });
      }
      else extraction_errors.push({ type: 'snapshot_text_identity_changed', snapshot_node: i, parent: selectorForSnapshot(parentIndex), reason: 'The live text node no longer matches the DOMSnapshot node.' });
    }
    function selectorForSnapshot(index) { return selectors.get(index) || null; }
    const descendantOf = (node, ancestor) => {
      for (let p = node; p >= 0; p = snapshotNodes.parentIndex[p]) if (p === ancestor) return true;
      return false;
    };
    for (const [index, type] of snapshotPseudo) {
      const owner = snapshotElements.get(snapshotNodes.parentIndex[index]);
      if (!owner) continue;
      const measurement = pseudoLayoutMeasurement(index, snapshotLayout, snapshotDocument);
      const childLayouts = snapshotLayout.nodeIndex.map((n, l) => ({ n, l })).filter(x => descendantOf(x.n, index));
      const text = childLayouts.map(x => snapshotStrings[snapshotLayout.text[x.l]] || '').join('');
      const boxes = (snapshotTextBoxes?.layoutIndex || []).flatMap((l, k) => childLayouts.some(x => x.l === l) ? [snapshotRect(snapshotTextBoxes.bounds[k])] : []);
      const data = { type: '::' + type, index, ...measurement, text, text_boxes: boxes,
        backend_node_id: snapshotNodes.backendNodeId?.[index] };
      const list = pseudoByOwner.get(owner) || []; list.push(data); pseudoByOwner.set(owner, list);
    }
    for (const [index, actual] of snapshotElements) {
      if (!actual.matches('input,textarea,select')) continue;
      const boxes = (snapshotTextBoxes?.layoutIndex || []).flatMap((l, k) => descendantOf(snapshotLayout.nodeIndex[l], index) ? [snapshotRect(snapshotTextBoxes.bounds[k])] : []);
      snapshotInputBoxes.set(actual, boxes);
      const fontOwners = snapshotLayout.nodeIndex.flatMap((node, layoutIndex) => {
        if (snapshotNodes.nodeType[node] !== Node.TEXT_NODE || !descendantOf(node, index) ||
            !(snapshotStrings[snapshotLayout.text[layoutIndex]] || '').trim()) return [];
        return [snapshotNodes.backendNodeId[node]];
      });
      snapshotInputFontOwners.set(actual, Array.from(new Set(fontOwners)));
    }
  }
  const regionOf = el => {
    if (el.closest('.menu,[role=menu],[role=tooltip],.toast')) return 'menu';
    if (el.closest('.dialog,.settings,.details,.card,[role=dialog]')) return 'dialog';
    if (el.closest('#appbar')) return 'header';
    if (el.closest('.side')) return 'sidebar';
    if (el.closest('#panel')) return 'right-pane';
    if (el.closest('#composer')) return 'composer';
    if (el.closest('.chat')) return 'conversation';
    return 'window';
  };
  const detailsVisibilityEvidence = (el, ownContent = false) => {
    // DOMRange/getBoundingClientRect may force layout in the skipped content
    // of a closed details, producing nonzero boxes for unpainted descendants.
    // Only its first direct summary Element remains exposed. Nested details
    // must satisfy every ancestor; an inner open state cannot open its parent.
    const ancestors = [];
    for (let p = ownContent ? el : el.parentElement; p; p = p.parentElement) {
      if (p.localName !== 'details') continue;
      const summary = Array.from(p.children).find(child => child.localName === 'summary') || null;
      const insideSummary = summary !== null && summary.contains(el);
      ancestors.push({ details: nodeIds.get(p) || pathOf(p), open: p.open,
        open_attribute: p.getAttribute('open'),
        first_summary: summary ? nodeIds.get(summary) || pathOf(summary) : null,
        inside_first_summary: insideSummary, own_details_content: p === el,
        hidden: p.open === false && !insideSummary });
    }
    return ancestors.length ? { source: 'live HTMLDetailsElement.open + first direct summary Element ancestry',
      hidden: ancestors.some(ancestor => ancestor.hidden), ancestors } : null;
  };
  const visibleRect = (el, inputRect, clipOwnContent = false) => {
    if (detailsVisibilityEvidence(el, clipOwnContent)?.hidden) return null;
    let clipped = intersect(inputRect, { x: 0, y: 0, width: innerWidth, height: innerHeight });
    for (let p = el; p; p = p.parentElement) {
      const s = styleOf(p);
      if (s.display === 'none' || s.visibility !== 'visible' || Number(s.opacity) === 0 || p.hidden) return null;
      if ((p !== el || clipOwnContent) && (/(hidden|clip|scroll|auto)/.test(s.overflowX) || /(hidden|clip|scroll|auto)/.test(s.overflowY))) {
        const b = p.getBoundingClientRect();
        const limit = { x: /(hidden|clip|scroll|auto)/.test(s.overflowX) ? b.x + p.clientLeft : clipped.x,
          y: /(hidden|clip|scroll|auto)/.test(s.overflowY) ? b.y + p.clientTop : clipped.y,
          width: /(hidden|clip|scroll|auto)/.test(s.overflowX) ? p.clientWidth : clipped.width,
          height: /(hidden|clip|scroll|auto)/.test(s.overflowY) ? p.clientHeight : clipped.height };
        clipped = intersect(clipped, limit);
      }
      if (!nonempty(clipped)) return null;
    }
    return nonempty(clipped) ? clipped : null;
  };
  const visibleText = (node, s) => {
    if (snapshotRenderedText.has(node)) return snapshotRenderedText.get(node);
    const text = node.nodeValue || '';
    return text;
  };
  // A text Range belongs to its parent's content, so the parent's own overflow
  // clip applies. Element borders/backgrounds do not clip themselves. Keep both
  // the original DOMRange and the measured content clip; never call the long
  // offscreen layout string a painted text rectangle.
  const measuredText = new WeakMap();
  const textMeasurement = node => {
    if (measuredText.has(node)) return measuredText.get(node);
    const owner = node.parentElement, s = styleOf(owner), range = document.createRange();
    range.selectNodeContents(node);
    const original = rect(range.getBoundingClientRect());
    const ranges = Array.from(range.getClientRects()).map(rect);
    const ownBox = owner.getBoundingClientRect();
    const ownClip = { x: /hidden|clip|scroll|auto/.test(s.overflowX) ? ownBox.x + owner.clientLeft : original.x,
      y: /hidden|clip|scroll|auto/.test(s.overflowY) ? ownBox.y + owner.clientTop : original.y,
      width: /hidden|clip|scroll|auto/.test(s.overflowX) ? owner.clientWidth : original.width,
      height: /hidden|clip|scroll|auto/.test(s.overflowY) ? owner.clientHeight : original.height };
    const ownBounds = intersect(original, ownClip);
    const boxes = ranges.map(box => visibleRect(owner, box, true)).filter(Boolean);
    const ellipsisOwners = [];
    for (let p = owner; p; p = p.parentElement) {
      const style = styleOf(p);
      if (style.textOverflow === 'ellipsis' && p.scrollWidth > p.clientWidth || style.webkitLineClamp !== 'none' && Number(style.webkitLineClamp) > 0 && p.scrollHeight > p.clientHeight)
        ellipsisOwners.push({ selector: pathOf(p), direct_owner: p === owner, text_overflow: style.textOverflow, line_clamp: style.webkitLineClamp,
          display: style.display, white_space: style.whiteSpace, scroll_width: p.scrollWidth, client_width: p.clientWidth,
          scroll_height: p.scrollHeight, client_height: p.clientHeight });
    }
    const ellipsis = ellipsisOwners.length > 0;
    const inlineTextBoxes = (axByBackend.get(snapshotBackend.get(node)) || []).flatMap(ax => (ax.childIds || []).map(id => axById.get(id)))
      .filter(ax => ax?.role?.value === 'InlineTextBox')
      .map(ax => ({ node_id: ax.nodeId, parent_id: ax.parentId, ignored: ax.ignored, name: ax.name?.value ?? null,
        properties: ax.properties || [], source: 'CDP.Accessibility.getFullAXTree', bounds: null }));
    const data = { range_bounds: ownBounds, clipped_range_envelope: visibleRect(owner, original, true), range_boxes: boxes, glyph_bounds: null,
      evidence: { source: 'DOMRange + actual owner content/ancestor overflow clips', backend_node_id: snapshotBackend.get(node) ?? null,
        source_text: node.nodeValue, raw_bounds: original, raw_rectangles: ranges, owner_element_box: rect(ownBox), owner_content_clip: ownClip,
        clipped_range_envelope: visibleRect(owner, original, true), clipped_range_boxes: boxes, glyph_bounds: null,
        dom_snapshot_layout: snapshotTextLayouts.get(node) || null,
        owner_selector: pathOf(owner), overflow_x: s.overflowX, overflow_y: s.overflowY, text_overflow: s.textOverflow,
        scroll_width: owner.scrollWidth, client_width: owner.clientWidth, scroll_height: owner.scrollHeight, client_height: owner.clientHeight,
        css_ellipsis_active: ellipsis, ellipsis_overflow_owners: ellipsisOwners,
        ellipsis_detection_quantity: 'computed ellipsis/clamp request plus overflow metrics; actual glyph visibility and geometry remain unmeasured',
        ax_inline_text_boxes: inlineTextBoxes,
        inline_text_geometry_note: inlineTextBoxes.length ? 'AX exposes text fragments, including generated ellipses, but no bounds. It can also retain the unclipped original fragment; none is promoted to painted geometry.' : null,
        geometry_kind: ellipsis ? 'unmeasured-painted-ellipsis-with-retained-range-evidence' : 'font-metric-text-advance-range',
        range_quantity: 'CSSOM font ascent/descent and text advance rectangles; clipping does not turn these into glyph ink bounds' } };
    measuredText.set(node, data); return data;
  };
  const textNodes = el => {
    const output = [], walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (n.parentElement.closest('svg,script,style,option')) continue;
      const s = styleOf(n.parentElement), text = visibleText(n, s);
      if (text.trim() && textMeasurement(n).clipped_range_envelope) output.push(n);
    }
    return output;
  };
  const textRects = nodes => nodes.flatMap(n => textMeasurement(n).range_boxes);
  const textGeometry = (measurements, boxes, kind, elementBounds, elementVisibleBounds) => {
    const unknownEllipsis = measurements.some(measurement => measurement.evidence.css_ellipsis_active);
    const envelopes = measurements.map(measurement => measurement.clipped_range_envelope).filter(Boolean);
    const envelope = envelopes.length ? { x: Math.min(...envelopes.map(box => box.x)), y: Math.min(...envelopes.map(box => box.y)),
      width: Math.max(...envelopes.map(box => box.x + box.width)) - Math.min(...envelopes.map(box => box.x)),
      height: Math.max(...envelopes.map(box => box.y + box.height)) - Math.min(...envelopes.map(box => box.y)) } : null;
    const unknownBox = () => ({ x: null, y: null, width: null, height: null });
    // Preserve directly measured control boxes. For a standalone text element,
    // unknown ellipsis paint must not be replaced by either the owner's box or
    // a clipped advance range. The latter remains report-only evidence.
    const count = boxes.length ? lineCount(boxes) : null;
    return { bounds: unknownEllipsis && kind === 'text' ? unknownBox() : elementBounds,
      visible_bounds: unknownEllipsis && kind === 'text' ? unknownBox() : elementVisibleBounds,
      text_bounds: unknownEllipsis ? null : boxes, text_layout_bounds: boxes,
      line_count: unknownEllipsis && count !== 1 ? null : count,
      line_count_source: count === 1 ? 'one measured visible layout line; ellipsis does not add a line' : unknownEllipsis ? null : 'measured visible DOMRange line rectangles',
      clipped_range_envelope: envelope, unknown_ellipsis: unknownEllipsis,
      text_bounds_quantity: unknownEllipsis ? 'unmeasured-painted-ellipsis-text' : 'font-metric-text-advance-range' };
  };
  const lineCount = boxes => new Set(boxes.filter(b => b.width >= 0 && b.height > 0).map(b => Math.round(b.y * 2) / 2)).size;
  const inputTextMeasurement = el => {
    const backend = snapshotBackend.get(el), primary = snapshotInputBoxes.get(el) || [];
    const secondary = meta.input_text_boxes?.[String(backend)];
    const evidence = { backend_node_id: backend ?? null, snapshot_boxes: primary, supplement: secondary || null,
      selected_source: primary.length ? 'CDP.DOMSnapshot.TextBoxSnapshot' : null };
    if (!secondary) return { boxes: primary, evidence };
    const validBox = box => box && ['x', 'y', 'width', 'height'].every(k => typeof box[k] === 'number' && Number.isFinite(box[k])) && box.width >= 0 && box.height > 0;
    if (secondary.source !== 'CDP.DOM+Runtime.DOMRange' || !Array.isArray(secondary.boxes) || !Array.isArray(secondary.text_nodes) || !secondary.boxes.every(validBox)) {
      extraction_errors.push({ type: 'invalid_input_text_measurement', backend_node_id: backend, selector: pathOf(el), reason: 'Supplement must contain actual UA-shadow DOMRange rectangles and source text-node evidence.' });
      return { boxes: primary, evidence };
    }
    for (const failure of secondary.errors || []) extraction_errors.push({ type: 'input_text_measurement_error', backend_node_id: backend, detail: failure });
    for (const node of secondary.text_nodes) {
      if (node.error) extraction_errors.push({ type: 'input_text_node_measurement_error', backend_node_id: backend, detail: node });
      if (typeof node.backend_node_id !== 'number' || typeof node.text !== 'string' || !Array.isArray(node.boxes) || !node.boxes.every(validBox))
        extraction_errors.push({ type: 'invalid_input_text_node_evidence', backend_node_id: backend, detail: node });
    }
    if (primary.length && secondary.boxes.length) {
      const sorted = boxes => boxes.map(box => [box.y, box.x, box.width, box.height]).sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2] || a[3] - b[3]);
      const a = sorted(primary), b = sorted(secondary.boxes);
      if (a.length !== b.length || a.some((box, i) => box.some((coordinate, j) => Math.abs(coordinate - b[i][j]) > .000001)))
        extraction_errors.push({ type: 'conflicting_input_text_measurements', backend_node_id: backend, selector: pathOf(el), snapshot_boxes: primary, dom_range_boxes: secondary.boxes });
    }
    if (!primary.length && secondary.boxes.length) evidence.selected_source = secondary.source;
    return { boxes: primary.length ? primary : secondary.boxes, evidence };
  };
  const accessibilityOf = (node, backendOverride = null) => {
    const backend = backendOverride ?? snapshotBackend.get(node), nodes = axByBackend.get(backend) || [];
    const primary = nodes.find(ax => !ax.ignored && ax.role?.value !== 'InlineTextBox') || nodes.find(ax => !ax.ignored) || nodes[0];
    return { backend_node_id: backend ?? null, node_ids: nodes.map(ax => ax.nodeId),
      measured: !!primary, ignored: primary?.ignored ?? null, name: typeof primary?.name?.value === 'string' ? primary.name.value : '',
      role: primary?.role?.value ?? null, name_sources: primary?.name?.sources || [], properties: primary?.properties || [] };
  };
  const platformFontIdentity = font => ({
    // These are two provider measurements, not aliases to normalize. The
    // PostScript face identifies the same installed face even when a platform
    // exposes a localized family spelling; preserve both exact strings.
    family_name: font.familyName, postscript_name: font.postScriptName,
    is_custom_font: typeof font.isCustomFont === 'boolean' ? font.isCustomFont : null,
    identity_source: 'CDP.CSS.getPlatformFontsForNode.postScriptName',
    family_name_source: 'CDP.CSS.getPlatformFontsForNode.familyName', glyph_count: 0,
  });
  const fontRequestEvidence = s => ({
    source: 'getComputedStyle', weight: s.fontWeight === 'normal' ? 400 : s.fontWeight === 'bold' ? 700 : number(s.fontWeight),
    weight_css: s.fontWeight, weight_unit: 'CSS numeric font-weight request',
    variation_settings: s.fontVariationSettings, style: s.fontStyle, stretch: s.fontStretch,
    quantity: 'computed render request, not resolved OpenType face weight or actual variation axes',
  });
  const fontWeightEvidence = (id, request, fonts, applicable) => ({
    version: 1, applicable, owner: id,
    legacy: { value: request?.weight ?? null, quantity: 'configured' },
    configured: { value: request?.weight ?? null, source: request?.source ?? null, raw: request },
    resolved: { source_span_complete: false, source: 'CDP.CSS.getPlatformFontsForNode',
      faces: Array.isArray(fonts) && fonts.length ? fonts.map(font => ({
        family_name: font.family_name, postscript_name: font.postscript_name, value: null,
        source: 'CDP.CSS.getPlatformFontsForNode', raw: font,
        reason: 'The actual CDP face record has no measured numeric weight or variation axes.' })) : null,
      reason: 'Computed CSS weight is a request; CDP actual face identity does not measure resolved wght. Neither the request nor a face-name suffix supplies that missing measurement.' },
  });
  const platformFonts = (el, text, id, options) => {
    if (!text) return { fonts: [], evidence: null };
    const measured = meta.reference_environment?.fonts;
    let owners = [];
    if (options.pseudo) owners = [options.axBackend];
    else if (el.matches('input,textarea,select')) {
      owners = snapshotInputFontOwners.get(el) || [];
      if (!owners.length) {
        const supplement = meta.input_text_boxes?.[String(snapshotBackend.get(el))];
        owners = (supplement?.text_nodes || []).filter(n => n.boxes?.length && n.text?.trim()).map(n => n.backend_node_id);
      }
    }
    else {
      const textNodes = options.ownedTextNodes || (options.textNode ? [options.textNode] : []);
      // snapshotBackend was associated with each actual live Text node only
      // after matching its snapshot ancestry, sibling position and nodeValue.
      // Parent Element font statistics can also include nested rich text; they
      // remain raw evidence and are never substituted for this node's result.
      owners = textNodes.map(node => snapshotBackend.get(node));
    }
    owners = Array.from(new Set(owners));
    const records = owners.map(backend => {
      const query = measured?.queries?.[String(backend)] ?? null;
      return { backend_node_id: backend ?? null, fonts: query?.result?.fonts ?? null, query,
        errors: (measured?.errors || []).filter(error => error.backend_node_id === backend) };
    });
    const evidence = { source: measured?.source || null, owners: records,
      attribution: options.pseudo ? 'whole-pseudo-layout' : 'actual-text-node-layouts',
      glyph_count_scope: options.pseudo ? 'whole-pseudo-layout-shaping' : 'actual-text-node-layout-shaping',
      quantity: 'Actual shaping font usage; not a count of visible painted glyphs or ellipsis ink bounds.' };
    if (measured?.source !== 'CDP.CSS.getPlatformFontsForNode' || !owners.length || owners.some(x => !Number.isInteger(x)) ||
        records.some(record => record.errors.length || !record.query || record.query.error ||
          record.query.request_sent !== true ||
          record.query.backend_node_id !== record.backend_node_id || !Number.isInteger(record.query.frontend_node_id) || record.query.frontend_node_id <= 0 ||
          record.query.request?.method !== 'CSS.getPlatformFontsForNode' || record.query.request?.parameters?.nodeId !== record.query.frontend_node_id ||
          (!options.pseudo && (record.query.node_type !== Node.TEXT_NODE || record.query.scope !== 'text-node-layout')) ||
          !Array.isArray(record.fonts) || !record.fonts.length || record.fonts.some(font =>
          typeof font.familyName !== 'string' || !font.familyName.trim() || typeof font.postScriptName !== 'string' || !font.postScriptName.trim() || !Number.isFinite(font.glyphCount) || font.glyphCount <= 0))) {
      unmeasured.push({ element: id, property: 'style.rendered_fonts', reason: 'No successful platform-font query with actual node identity for every owned text node or whole pseudo layout.', evidence });
      return { fonts: null, evidence };
    }
    const combined = new Map();
    for (const record of records) for (const font of record.fonts) {
      const key = JSON.stringify([font.familyName, font.postScriptName]);
      const item = combined.get(key) || platformFontIdentity(font);
      item.glyph_count += font.glyphCount; combined.set(key, item);
    }
    return { fonts: Array.from(combined.values()).sort((a, b) => a.family_name.localeCompare(b.family_name) || a.postscript_name.localeCompare(b.postscript_name)), evidence };
  };
  const panelResizeEvidence = el => {
    if (!el.matches('#panel > .pane-resize')) return null;
    const s = styleOf(el), listeners = meta.panel_listeners ?? null, backend = snapshotBackend.get(el);
    const measured = Number.isInteger(backend) && listeners?.source === 'CDP.DOMDebugger.getEventListeners' &&
      listeners.owner?.backendNodeId === backend && listeners.owner?.nodeType === 1 &&
      Array.isArray(listeners.listeners) && Array.isArray(listeners.errors) && listeners.errors.length === 0;
    return { source: 'actual DOM pane-resize element + CDP installed event-listener receipt',
      title: el.getAttribute('title'), has_pointer_handler: measured ? listeners.listeners.some(item => item.type === 'pointerdown' && item.backendNodeId === backend) : null,
      listener_evidence: listeners, owner_backend_node_id: backend ?? null, listener_owner_matches: measured,
      pointer_handler_property_type: typeof el.onpointerdown,
      bounds: rect(el.getBoundingClientRect()), cursor: s.cursor,
      pointer_state: { hovered: el.matches(':hover'), active: el.matches(':active'),
        body_resizing: document.body.classList.contains('resizing') },
      bounds_quantity: 'actual DOM handle border box, independent of the capture action coordinates',
      paint_source: 'computed CSS of this actual DOM element; canonical style records the resolved paint' };
  };
  const supplementalRegionEvidence = (el, s, ax = accessibilityOf(el)) => {
    // A generic layout wrapper is not a region just because it has a box.
    // These additions require independent DOM and actual CDP AX witnesses.
    if (!ax.measured || ax.ignored !== false) return null;
    if ((el.localName === 'nav' || el.getAttribute('role') === 'navigation') &&
        ax.role === 'navigation' && typeof ax.name === 'string' && ax.name.trim()) {
      return { reason: 'named-navigation', source: 'live DOM navigation semantics + CDP AX role/name',
        dom_tag: el.localName, dom_role: el.getAttribute('role'), accessibility: ax };
    }
    const tabindex = el.getAttribute('tabindex');
    const focusable = (Array.isArray(ax.properties) ? ax.properties : []).find(property => property.name === 'focusable')?.value?.value;
    if (tabindex === null || el.tabIndex !== 0 || Number(tabindex) !== 0 || focusable !== true) return null;
    const metrics = { client_width: el.clientWidth, client_height: el.clientHeight,
      scroll_width: el.scrollWidth, scroll_height: el.scrollHeight, scroll_left: el.scrollLeft, scroll_top: el.scrollTop };
    const axes = [];
    if (['auto', 'scroll'].includes(s.overflowX) && Number.isFinite(el.clientWidth) && el.clientWidth > 0 &&
        Number.isFinite(el.scrollWidth) && el.scrollWidth > el.clientWidth) axes.push('horizontal');
    if (['auto', 'scroll'].includes(s.overflowY) && Number.isFinite(el.clientHeight) && el.clientHeight > 0 &&
        Number.isFinite(el.scrollHeight) && el.scrollHeight > el.clientHeight) axes.push('vertical');
    if (!axes.length) return null;
    return { reason: 'focusable-scroll-region', source: 'live DOM tabindex/scroll metrics/computed overflow + CDP AX focusable',
      dom_tabindex: tabindex, tab_index: el.tabIndex, overflow_x: s.overflowX, overflow_y: s.overflowY,
      axes, metrics, accessibility: ax,
      scrollbar_measurement: 'A focusable scroll region does not establish UA scrollbar part visibility or geometry.' };
  };
  const kindOf = (el, s, supplementalRegion = supplementalRegionEvidence(el, s)) => {
    const tag = el.localName, role = el.getAttribute('role');
    if (el === document.body || el.matches('#appbar,.side,.chat,#composer,#panel,.scrim,.settings,.dialog,.details,.menu')) return 'region';
    if (panelResizeEvidence(el)) return 'resize-handle';
    if (el.matches('.oc-node')) return 'chart-node';
    if (el.matches('.oc-lines .edge,.oc-lines .link')) return 'chart-edge';
    if (el.matches('.avatar,.org-badge')) return 'avatar';
    if (el.matches('.dot')) return 'state-dot';
    if (el.matches('.badge,.ab-badge,.tag')) return 'badge';
    if (el.matches('.chip,kbd')) return 'chip';
    if (tag === 'input' && el.type === 'checkbox') return el.classList.contains('toggle') || role === 'switch' ? 'toggle' : 'checkbox';
    if (tag === 'input' && el.type === 'radio') return 'checkbox';
    if (role === 'switch') return 'toggle';
    if (role === 'checkbox' || role === 'radio') return 'checkbox';
    if (tag === 'input' || tag === 'textarea' || el.isContentEditable) return 'input';
    if (tag === 'select' || role === 'combobox') return 'dropdown';
    if (role === 'tab' || el.matches('.tabs > button,.seg > button,.settings nav > button')) return 'tab';
    if (role === 'menuitem' || el.matches('.menu .item')) return 'menu-item';
    if (el.matches('.org-row,.chat-row,.item-row,.session-row,.frow')) return 'list-row';
    if (tag === 'a') return 'link';
    if (tag === 'button' || tag === 'summary' || role === 'button') return textNodes(el).length ? 'button' : 'icon-button';
    if (tag === 'svg' && !el.matches('.oc-lines')) return 'icon';
    if (tag === 'img' || tag === 'canvas') return 'image';
    if (tag === 'hr' || el.matches('.sep,.ab-sep,.oc-legend i.link')) return 'divider';
    if (tag === 'pre' || el.matches('.doc-body,.code-view')) return 'code';
    if (el.matches('.card,.task,.cc-card,.bubble,.report,.cc-summary,.banner,.digest,.choice,.session-list')) return 'card';
    const background = color(s.backgroundColor, pathOf(el), 'background-color');
    const border = ['Top', 'Right', 'Bottom', 'Left'].some(side => number(s['border' + side + 'Width']) > 0 && !['none', 'hidden'].includes(s['border' + side + 'Style']));
    const outline = typeof s.outlineStyle === 'string' && s.outlineStyle !== 'none' &&
      (s.outlineStyle === 'auto' || number(s.outlineWidth) > 0);
    if ((background?.[3] > 0 || border || outline || s.boxShadow !== 'none' || s.backgroundImage !== 'none') && tag !== 'html') return el.getBoundingClientRect().width <= 2 || el.getBoundingClientRect().height <= 2 ? 'divider' : 'card';
    // Add previously missing regions; never replace an existing control,
    // decoration, text owner or explicitly named region classification.
    if (supplementalRegion) return 'region';
    return null;
  };
  const semanticOwnerKinds = new Set(['button', 'icon-button', 'link', 'tab', 'chip', 'badge', 'avatar']);
  const ownedText = (el, kind) => {
    if (kind === 'input') return { text: el.value || el.getAttribute('placeholder') || '', nodes: [], style: !el.value && el.getAttribute('placeholder') ? getComputedStyle(el, '::placeholder') : styleOf(el) };
    if (kind === 'dropdown') return { text: el.selectedOptions ? Array.from(el.selectedOptions).map(x => x.text).join(', ') : el.innerText, nodes: [], style: styleOf(el) };
    if (!semanticOwnerKinds.has(kind)) return null;
    const nodes = textNodes(el);
    if (!nodes.length) return { text: '', nodes, style: styleOf(el) };
    // Rich rows, badges and mixed font labels stay separate rendered elements.
    if (el.querySelector('.avatar,.org-badge,.badge,.ab-badge,.tag,.chip,kbd,input,select,textarea')) return null;
    const first = styleOf(nodes[0].parentElement);
    const uniform = nodes.every(n => ['fontFamily', 'fontSize', 'fontWeight', 'color', 'whiteSpace'].every(k => styleOf(n.parentElement)[k] === first[k]));
    if (!uniform) return null;
    return { text: el.innerText || nodes.map(n => visibleText(n, first)).join(''), nodes, style: first };
  };
  const cssList = value => {
    const parts = []; let level = 0, start = 0;
    for (let i = 0; i < value.length; i++) {
      if (value[i] === '(') level++;
      else if (value[i] === ')') level--;
      else if (value[i] === ',' && level === 0) { parts.push(value.slice(start, i).trim()); start = i + 1; }
    }
    parts.push(value.slice(start).trim()); return parts;
  };
  const shadowData = (el, value, pseudo = null) => {
    if (value === 'none') return [];
    const shadows = [];
    for (const layer of cssList(value)) {
      const tint = layer.match(/(?:rgba?|color|lab|lch|oklab|oklch)\([^)]*\)/);
      const rest = (tint ? layer.replace(tint[0], '') : layer).replace(/\binset\b/, '').trim().split(/\s+/);
      const lengths = rest.map(x => /^-?(?:\d*\.)?\d+(?:px)?$/.test(x) ? parseFloat(x) : NaN);
      if (!tint || lengths.length < 2 || lengths.length > 4 || lengths.some(x => !Number.isFinite(x))) {
        unmeasured.push({ element: nodeIds.get(el), property: 'style.shadow', raw: value, reason: 'Computed shadow could not be represented without guessing lengths or color.' });
        return null;
      }
      shadows.push({ inset: /\binset\b/.test(layer), offset_x: lengths[0], offset_y: lengths[1], blur_radius: lengths[2] || 0,
        spread_radius: lengths[3] || 0, color: color(tint[0], pathOf(el), 'box-shadow', pseudo, value) });
    }
    return shadows;
  };
  const backgroundData = (el, s, measuredBox = null, pseudo = null) => {
    const raw = s.backgroundImage;
    if (raw === 'none') return 'none';
    const conic = raw.match(/^(repeating-)?conic-gradient\((.*)\)$/);
    const sizeValues = s.backgroundSize.split(/\s+/), positionValues = s.backgroundPosition.split(/\s+/);
    const box = measuredBox || el.getBoundingClientRect();
    const length = (value, axis) => /^-?(?:\d*\.)?\d+px$/.test(value) ? parseFloat(value) : /^-?(?:\d*\.)?\d+%$/.test(value) ? parseFloat(value) * axis / 100 : NaN;
    const size = [length(sizeValues[0], box.width), length(sizeValues[1] || sizeValues[0], box.height)];
    if (conic && size.every(Number.isFinite)) {
      const layers = cssList(conic[2]), stops = []; let previous = -Infinity, valid = true;
      for (const item of layers) {
        const match = item.match(/^((?:rgba?|color|lab|lch|oklab|oklch)\([^)]*\))\s+(-?(?:\d*\.)?\d+)(deg|turn|%)$/);
        if (!match) { valid = false; break; }
        const position = Math.max(previous, parseFloat(match[2]) / (match[3] === 'deg' ? 360 : match[3] === '%' ? 100 : 1));
        previous = position; stops.push({ position, color: color(match[1], pathOf(el), 'background-image', pseudo, raw) });
      }
      const position = [length(positionValues[0], box.width - size[0]), length(positionValues[1] || '50%', box.height - size[1])];
      const repeat = s.backgroundRepeat.split(/\s+/);
      if (valid && stops.length >= 2 && position.every(Number.isFinite) && repeat.length <= 2 && repeat.every(x => ['repeat', 'no-repeat', 'space', 'round'].includes(x)))
        return { kind: 'conic-gradient', repeating: !!conic[1], angle: 0, center: [size[0] / 2, size[1] / 2], stops, size, position, repeat: [repeat[0], repeat[1] || repeat[0]] };
    }
    unmeasured.push({ element: nodeIds.get(el), property: 'style.background_image', raw, size: s.backgroundSize, position: s.backgroundPosition,
      reason: 'This gradient/image placement has no measured canonical representation; it is not treated as an absent background.' });
    return null;
  };
  const svgStrokes = new WeakMap();
  const svgStrokeData = el => {
    if (!(el instanceof SVGElement)) return null;
    if (svgStrokes.has(el)) return svgStrokes.get(el);
    const matrixValue = matrix => matrix && ['a', 'b', 'c', 'd', 'e', 'f'].every(key => Number.isFinite(matrix[key]))
      ? Object.fromEntries(['a', 'b', 'c', 'd', 'e', 'f'].map(key => [key, matrix[key]])) : null;
    const shapes = el instanceof SVGGeometryElement ? [el] : Array.from(el.querySelectorAll('path,circle,ellipse,line,polyline,polygon,rect'));
    const records = [];
    for (const shape of shapes) {
      if (shape.closest('defs,clipPath,mask,marker,pattern,symbol')) continue;
      const s = styleOf(shape);
      if (s.display === 'none' || s.visibility !== 'visible' || cumulativeOpacity(shape) === 0) continue;
      const record = { selector: pathOf(shape), source_width_css: s.strokeWidth, source_width: null, vector_effect: s.vectorEffect,
        source_dash_css: s.strokeDasharray, source_dash_offset_css: s.strokeDashoffset,
        source_linecap_css: s.strokeLinecap, source_linejoin_css: s.strokeLinejoin, source_miterlimit_css: s.strokeMiterlimit,
        source_path_length_attribute: shape.getAttribute('pathLength'), source_dash: null, source_dash_offset: null,
        screen_ctm: matrixValue(shape.getScreenCTM()), effective_width: null, effective_dash: null, effective_dash_offset: null,
        linecap: ['butt', 'round', 'square'].includes(s.strokeLinecap) ? s.strokeLinecap : null,
        linejoin: ['miter', 'miter-clip', 'round', 'bevel', 'arcs'].includes(s.strokeLinejoin) ? s.strokeLinejoin : null,
        miterlimit: Number.isFinite(Number(s.strokeMiterlimit)) ? Number(s.strokeMiterlimit) : null,
        coordinate_space: 'viewport-css-pixels' };
      records.push(record);
      if (s.stroke === 'none' || color(s.stroke, pathOf(shape), 'stroke')?.[3] === 0 || Number(s.strokeOpacity) === 0) { record.effective_width = 0; continue; }
      if (!/^(?:\d*\.)?\d+(?:px)?$/.test(s.strokeWidth)) { record.problem = 'Unresolved SVG source stroke unit.'; continue; }
      record.source_width = Number.parseFloat(s.strokeWidth);
      if (record.source_width === 0) { record.effective_width = 0; continue; }
      let mapping = record.screen_ctm;
      if (s.vectorEffect === 'non-scaling-stroke') {
        // SVG 2 defines this stroke in the furthest SVG viewport's host
        // coordinate system. Measured CTMs remove its viewBox/user transform
        // while retaining the host-to-window transform (including CSS zoom).
        let host = shape.ownerSVGElement;
        while (host?.ownerSVGElement) host = host.ownerSVGElement;
        const hostToScreen = host?.getScreenCTM(), userToHost = host?.getCTM();
        record.host_selector = host ? pathOf(host) : null;
        record.host_screen_ctm = matrixValue(hostToScreen); record.host_user_ctm = matrixValue(userToHost);
        if (!record.host_screen_ctm || !record.host_user_ctm || userToHost.a * userToHost.d - userToHost.b * userToHost.c === 0) {
          record.problem = 'Non-scaling stroke has no invertible measured host transform.'; continue;
        }
        mapping = matrixValue(hostToScreen.multiply(userToHost.inverse()));
      }
      else if (s.vectorEffect !== 'none') { record.problem = 'Unsupported actual SVG vector effect.'; continue; }
      record.stroke_to_window = mapping;
      if (!mapping) { record.problem = 'No finite measured stroke-to-window transform.'; continue; }
      const xSquared = mapping.a ** 2 + mapping.b ** 2, ySquared = mapping.c ** 2 + mapping.d ** 2;
      const dot = mapping.a * mapping.c + mapping.b * mapping.d;
      // A scalar width is valid for a similarity transform only. Nonuniform
      // scaling/shear needs a full stroked path, not a guessed mean scale.
      if (xSquared !== ySquared || dot !== 0) { record.problem = 'Nonuniform stroke transform cannot be represented by a universal scalar width.'; continue; }
      record.stroke_to_window_scale = Math.sqrt(xSquared);
      record.effective_width = record.source_width * record.stroke_to_window_scale;
      // SVG computed px/number lengths are in the stroke's user coordinate
      // space. Only the measured similarity transform makes them window px.
      // Percentages and pathLength calibration require additional evidence;
      // they must not silently become unscaled source lengths.
      const length = raw => {
        const match = /^([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?)(px)?$/i.exec(raw);
        if (!match || !Number.isFinite(Number(match[1]))) return null;
        return { value: Number(match[1]), unit: match[2] || 'number', coordinate_space: 'svg-stroke-user-units' };
      };
      const rawDash = s.strokeDasharray?.trim();
      if (rawDash === 'none') { record.source_dash = []; record.effective_dash = []; }
      else {
        const parts = rawDash?.split(/[\s,]+/).filter(Boolean), lengths = parts?.map(length);
        if (!lengths?.length || lengths.some(part => !part || part.value < 0)) record.dash_problem = 'Unresolved or invalid actual SVG dash length/unit.';
        else {
          record.source_dash = lengths;
          if (record.source_path_length_attribute !== null) record.dash_problem = 'Actual SVG pathLength calibration is not measured for dash lengths.';
          else {
            let values = lengths.map(part => part.value);
            if (values.every(value => value === 0)) values = [];
            else if (values.length % 2) values = values.concat(values);
            record.effective_dash = values.map(value => value * record.stroke_to_window_scale);
          }
        }
      }
      record.source_dash_offset = length(s.strokeDashoffset?.trim() || '');
      if (!record.source_dash_offset) record.dash_offset_problem = 'Unresolved or invalid actual SVG dash offset/unit.';
      else if (record.source_path_length_attribute !== null) record.dash_offset_problem = 'Actual SVG pathLength calibration is not measured for dash offset.';
      else record.effective_dash_offset = record.source_dash_offset.value * record.stroke_to_window_scale;
    }
    const painted = records.filter(record => record.effective_width !== 0);
    const widths = Array.from(new Set(painted.map(record => record.effective_width)));
    const width = records.some(record => record.problem) || widths.length > 1 ? null : widths[0] ?? 0;
    const uniform = (key, property) => {
      if (!painted.length) return null;
      const values = painted.map(record => record[key]);
      if (values.some(value => value === null || value === undefined) || new Set(values.map(value => JSON.stringify(value))).size !== 1) {
        unmeasured.push({ element: nodeIds.get(el), property, evidence: records,
          reason: 'The actual visible SVG strokes do not have one measured value for this style quantity; source units and per-path evidence are retained.' });
        return null;
      }
      return values[0];
    };
    const result = { width, dash: uniform('effective_dash', 'style.stroke_dash'), dash_offset: uniform('effective_dash_offset', 'style.stroke_dash_offset'),
      linecap: uniform('linecap', 'style.stroke_linecap'), linejoin: uniform('linejoin', 'style.stroke_linejoin'),
      miterlimit: uniform('miterlimit', 'style.stroke_miterlimit'), source: 'getComputedStyle + SVGGraphicsElement.getScreenCTM/getCTM', shapes: records };
    svgStrokes.set(el, result);
    if (width === null) unmeasured.push({ element: nodeIds.get(el), property: 'style.stroke_width', evidence: result,
      reason: 'Actual SVG strokes do not have one measurable content-window width; no source-space width is substituted.' });
    return result;
  };
  const outlineData = (el, s, pseudo = null, measuredBox = null) => {
    const raw = { style: s.outlineStyle, color: s.outlineColor, width: s.outlineWidth, offset: s.outlineOffset };
    const length = value => typeof value === 'string' && /^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?px$/i.test(value) && Number.isFinite(parseFloat(value)) ? parseFloat(value) : null;
    const localWidth = length(raw.width), localOffset = length(raw.offset), problems = [];
    const evidence = { source: 'actual getComputedStyle outline properties and DOM boxes; independent from border',
      selector: pathOf(el), pseudo, computed: raw, absence_proven: false,
      owner_bounds: rect(el.getBoundingClientRect()), owner_client_rects: Array.from(el.getClientRects()).map(rect),
      measured_pseudo_bounds: pseudo ? measuredBox : null, local_width: localWidth, local_offset: localOffset,
      coordinate_space: 'computed CSS px; window mapping requires actual unchanged ancestor axes',
      outline_to_window_scale: null, ancestry: [], contour: null, dash: null, dash_offset: null,
      measurement_limit: 'DOM boxes and border radii do not measure the actual outline contour. CSS dashed/dotted does not expose UA-selected segments or phase. No outline paint is copied from border.' };
    const legalStyle = ['none', 'solid', 'dashed', 'dotted', 'double', 'groove', 'ridge', 'inset', 'outset', 'auto'].includes(raw.style);
    if (raw.style === 'none' || legalStyle && raw.style !== 'auto' && localWidth === 0) {
      evidence.absence_proven = true;
      evidence.absence_reason = raw.style === 'none' ? 'Actual computed outline-style is none.' : 'Actual non-auto outline has zero computed width.';
      return { value: 'none', evidence, problems };
    }
    if (!legalStyle) problems.push({ property: 'style.outline.style', reason: 'Actual computed outline style is missing or unsupported.' });
    for (let p = el; p; p = p.parentElement) {
      const ps = styleOf(p);
      evidence.ancestry.push({ selector: pathOf(p), transform: ps.transform, perspective: ps.perspective,
        zoom: ps.zoom, scale: ps.scale, rotate: ps.rotate, translate: ps.translate });
    }
    if (pseudo) evidence.ancestry.unshift({ selector: pathOf(el), pseudo, transform: s.transform, perspective: s.perspective,
      zoom: s.zoom, scale: s.scale, rotate: s.rotate, translate: s.translate });
    const unchangedAxes = !(el instanceof SVGElement) && evidence.ancestry.length > 0 && evidence.ancestry.every(p =>
      p.transform === 'none' && p.perspective === 'none' && ['1', 'normal'].includes(p.zoom) &&
      p.scale === 'none' && p.rotate === 'none' && p.translate === 'none');
    if (unchangedAxes) evidence.outline_to_window_scale = 1;
    else problems.push({ property: 'style.outline.coordinate_space', reason: 'Actual transform/zoom/SVG coordinate mapping does not prove computed outline px equal window px.' });
    const automatic = raw.style === 'auto';
    if (automatic) problems.push({ property: 'style.outline.auto_paint', reason: 'UA auto outlines ignore outline-width and may ignore outline-color; computed requests do not establish actual auto paint.' });
    if (localWidth === null || localWidth < 0) problems.push({ property: 'style.outline.width', reason: 'No finite nonnegative actual computed outline width in px.' });
    if (localOffset === null) problems.push({ property: 'style.outline.offset', reason: 'No finite actual computed outline offset in px.' });
    const tint = automatic ? null : color(raw.color, pathOf(el), 'outline-color', pseudo);
    if (!automatic && tint === null) problems.push({ property: 'style.outline.color', reason: 'Actual outline color has no measured sRGB representation.' });
    const dashed = raw.style === 'dashed' || raw.style === 'dotted';
    if (dashed) {
      problems.push({ property: 'style.outline.dash', reason: 'Computed CSS outline style does not measure actual UA dash/gap segments.' });
      problems.push({ property: 'style.outline.dash_offset', reason: 'Computed CSS outline style does not measure the actual UA dash phase.' });
    }
    problems.push({ property: 'style.outline.contour', reason: 'Actual outline contour is not exposed by computed style or DOM client rectangles; box/radius expansion is not substituted.' });
    return { value: { style: legalStyle ? raw.style : null, color: tint,
      width: !automatic && unchangedAxes && localWidth !== null && localWidth >= 0 ? localWidth : null,
      offset: unchangedAxes ? localOffset : null, dash: raw.style === 'solid' ? [] : null,
      dash_offset: null, contour: null }, evidence, problems };
  };
  const styleData = (el, s, text, pseudo = null, measuredBox = null) => {
    const sides = ['Top', 'Right', 'Bottom', 'Left'];
    const widths = sides.map(side => number(s['border' + side + 'Width']) || 0);
    const radii = ['TopLeft', 'TopRight', 'BottomRight', 'BottomLeft'].map(corner => radius(s['border' + corner + 'Radius'], el, measuredBox));
    const foregroundProperty = el instanceof SVGElement ? (s.stroke !== 'none' ? 'stroke' : s.fill !== 'none' ? 'fill' : 'color') : 'color';
    const foreground = s[foregroundProperty];
    return { font_size: text ? number(s.fontSize) : null, font_weight: text ? (s.fontWeight === 'normal' ? 400 : s.fontWeight === 'bold' ? 700 : number(s.fontWeight)) : null,
      foreground: color(foreground, pathOf(el), foregroundProperty, pseudo), background: color(s.backgroundColor, pathOf(el), 'background-color', pseudo),
      border_color: Math.max(...widths) ? color(s['border' + sides[widths.indexOf(Math.max(...widths))] + 'Color'], pathOf(el), 'border-' + sides[widths.indexOf(Math.max(...widths))].toLowerCase() + '-color', pseudo) : [0, 0, 0, 0],
      border_width: Math.max(...widths), corner_radius: Math.max(...radii),
      font_family: text ? s.fontFamily : null, border_widths: widths, corner_radii: radii,
      border_styles: sides.map(side => s['border' + side + 'Style']),
      border_colors: sides.map((side, i) => widths[i] > 0 ? color(s['border' + side + 'Color'], pathOf(el), 'border-' + side.toLowerCase() + '-color', pseudo) : [0, 0, 0, 0]),
      outline: outlineData(el, s, pseudo, measuredBox).value,
      opacity: cumulativeOpacity(el) * (pseudo ? Number(s.opacity) : 1), shadow: shadowData(el, s.boxShadow, pseudo), background_image: backgroundData(el, s, measuredBox, pseudo),
      text_align: s.textAlign, letter_spacing: s.letterSpacing, line_height: s.lineHeight,
      stroke_width: svgStrokeData(el)?.width ?? null,
      stroke_dash: svgStrokeData(el)?.dash ?? null, stroke_dash_offset: svgStrokeData(el)?.dash_offset ?? null,
      stroke_linecap: svgStrokeData(el)?.linecap ?? null, stroke_linejoin: svgStrokeData(el)?.linejoin ?? null,
      stroke_miterlimit: svgStrokeData(el)?.miterlimit ?? null,
      pseudo };
  };
  const stateOf = el => {
    const role = el.getAttribute('role'), checkable = el.matches('input[type=checkbox],input[type=radio],[role=switch],[role=checkbox],[role=radio]');
    const expandable = el.localName === 'summary' || el.hasAttribute('aria-expanded') || el.matches('.org-row,.frow.dir');
    const selectable = el.matches('.tabs>button,.seg>button,.settings nav>button,.org-row,.chat-row,.item-row,.session-row,.who-pick .who,[role=tab],[aria-selected]');
    const interactive = el.matches('button,input,textarea,select,summary,a[href],[tabindex],[role=button],[role=tab],[role=menuitem]') || panelResizeEvidence(el) !== null;
    return { enabled: interactive ? !el.matches(':disabled,[aria-disabled=true]') : null,
      selected: selectable ? el.getAttribute('aria-selected') === 'true' || el.classList.contains('on') : null,
      checked: checkable ? !!el.checked || el.getAttribute('aria-checked') === 'true' : null,
      expanded: expandable ? el.localName === 'summary' ? !!el.parentElement.open : el.getAttribute('aria-expanded') === 'true' || el.classList.contains('open') : null,
      focused: interactive ? el === document.activeElement : null, hovered: el.matches(':hover'),
      current: el.matches('.oc-node') ? el.getAttribute('aria-current') === 'true' : null,
      unread: el.matches('.cc-card,.chat-row') ? el.classList.contains('unread') || !!el.querySelector('.badge') : null,
      indeterminate: checkable ? !!el.indeterminate || el.getAttribute('aria-checked') === 'mixed' : null,
      role };
  };
  const iconOf = (el, kind) => {
    if (kind === 'icon' || kind === 'chart-edge') {
      const shape = n => ({ tag: n.localName, attributes: Object.fromEntries(Array.from(n.attributes).filter(a => ['viewBox', 'd', 'points', 'x', 'y', 'x1', 'x2', 'y1', 'y2', 'cx', 'cy', 'r', 'rx', 'ry', 'width', 'height', 'transform', 'fill-rule'].includes(a.name)).sort((a, b) => a.name.localeCompare(b.name)).map(a => [a.name, a.value])), children: Array.from(n.children).filter(child => !['title', 'desc', 'metadata'].includes(child.localName)).map(shape) });
      return { source: 'svg', glyph: JSON.stringify(shape(el)) };
    }
    if (kind === 'image' && el.localName === 'img') return { source: 'image', glyph: el.currentSrc || el.src };
    return null;
  };
  const cssLineBreakConfiguration = (s, applicable, owner) => {
    const raw = Object.fromEntries(['whiteSpace', 'textWrapMode', 'textWrapStyle', 'wordBreak', 'overflowWrap', 'lineBreak', 'hyphens',
      'webkitLineClamp', 'direction', 'writingMode'].map(key => [key, typeof s[key] === 'string' && s[key].length ? s[key] : null]));
    const evidence = { source: 'getComputedStyle of the actual text style owner', owner, raw, applicable,
      reason: applicable ? 'Independent normal and emergency policies from actual computed CSS; not observed line placement.'
        : 'This emitted element has no text under the existing text applicability predicate.', errors: [] };
    let normal = null, emergency = null;
    if (applicable) {
      const wrapping = raw.textWrapMode === 'nowrap' ? false : raw.textWrapMode === 'wrap' ? true
        : raw.textWrapMode !== null ? null : ['pre', 'nowrap'].includes(raw.whiteSpace) ? false
        : ['normal', 'pre-wrap', 'pre-line', 'break-spaces'].includes(raw.whiteSpace) ? true : null;
      if (wrapping === false) { normal = 'none'; emergency = 'none'; }
      else if (wrapping === null) evidence.errors.push('Actual white-space/text-wrap mode does not establish whether soft wrapping is enabled.');
      else if (!['auto', 'normal', 'loose', 'strict'].includes(raw.lineBreak))
        evidence.errors.push('The actual CSS line-break value has no proved mapping in break-strategy version 1.');
      else if (!['normal', 'break-all', 'keep-all', 'break-word'].includes(raw.wordBreak))
        evidence.errors.push('The actual CSS word-break value has no proved mapping.');
      else if (!['normal', 'anywhere', 'break-word'].includes(raw.overflowWrap))
        evidence.errors.push('The actual CSS overflow-wrap value is unavailable or unsupported.');
      else {
        normal = raw.wordBreak === 'break-all' ? 'break-all' : raw.wordBreak === 'keep-all' ? 'keep-all' : 'word';
        emergency = raw.wordBreak === 'break-word' || ['anywhere', 'break-word'].includes(raw.overflowWrap) ? 'break-unbreakable' : 'none';
        // CSS overflow-wrap:normal can relax keep-all to normal opportunities;
        // that is neither no fallback nor arbitrary emergency character breaks.
        if (raw.wordBreak === 'keep-all' && raw.overflowWrap === 'normal') {
          emergency = null;
          evidence.errors.push('The CSS keep-all relaxation fallback is not represented by the version-1 emergency strategies.');
        }
      }
    }
    return { layout: { break_strategy_version: 1, normal_break_strategy: normal, emergency_break_strategy: emergency }, evidence };
  };
  const imageResourceEvidence = el => {
    if (el.localName !== 'img') return null;
    const backend = snapshotBackend.get(el) ?? null, r = el.getBoundingClientRect();
    const current = { tag: el.localName, connected: el.isConnected, owner_document_url: el.ownerDocument.URL,
      in_current_document: el.ownerDocument === document, src: el.src, current_src: el.currentSrc,
      src_attribute: el.getAttribute('src'), srcset_attribute: el.getAttribute('srcset'), sizes_attribute: el.getAttribute('sizes'),
      complete: el.complete, natural_width: el.naturalWidth, natural_height: el.naturalHeight,
      bounds: { x: r.x, y: r.y, width: r.width, height: r.height } };
    const supplied = meta.image_resources?.images?.[String(backend)], errors = [...(meta.image_resources?.errors || []), ...(supplied?.errors || [])];
    const after = supplied?.owner?.after_source_evidence;
    if (backend === null || !supplied || supplied.owner?.backend_node_id !== backend)
      errors.push('No observed image resource is bound to this actual DOMSnapshot backend node.');
    if (!after || Object.keys(current).some(key => JSON.stringify(current[key]) !== JSON.stringify(after[key])))
      errors.push('Actual image identity, loaded state or geometry changed between retained-object evidence and extraction.');
    const evidence = { ...(supplied || { source: 'actual loaded resource unavailable', status: 'unknown', binding: null,
      media_type: null, byte_length: null, body_base64: null, body_file: null, decoded_paint: null }),
      owner: { ...(supplied?.owner || {}), backend_node_id: backend, at_extraction: current },
      receipt_file: meta.image_resources?.file || null, errors };
    if (errors.length || evidence.status !== 'loaded-response-bytes') evidence.status = 'unknown';
    return evidence;
  };
  const emit = (el, kind, text, bounds, parent, suffix = '', options = {}) => {
    const region = regionOf(el), id = nodeIds.get(el) + suffix;
    const s = options.style || styleOf(el), boxes = options.textBoxes || [];
    const textOwner = options.textNode?.parentElement || options.ownedTextNodes?.[0]?.parentElement || el;
    const breaks = cssLineBreakConfiguration(s, !!text || kind === 'text', { element: nodeIds.get(textOwner), pseudo: options.pseudo || null });
    const ownedBreaks = (options.ownedTextNodes || []).map(node => cssLineBreakConfiguration(styleOf(node.parentElement), true,
      { element: nodeIds.get(node.parentElement), backend_node_id: snapshotBackend.get(node) ?? null }));
    if (ownedBreaks.length) breaks.evidence.actual_text_owners = ownedBreaks.map(value => value.evidence);
    if (ownedBreaks.some(value => JSON.stringify(value.evidence.raw) !== JSON.stringify(breaks.evidence.raw) || value.evidence.errors.length)) {
      breaks.layout.normal_break_strategy = null; breaks.layout.emergency_break_strategy = null;
      breaks.evidence.errors.push('Owned text nodes do not establish one uniform actual line-break configuration.');
    }
    for (const reason of breaks.evidence.errors) unmeasured.push({ element: id, property: 'layout.break_strategy', reason });
    const paintStyle = styleData(el, options.pseudo ? s : styleOf(el), text, options.pseudo || null, options.unclippedBounds);
    let outline = outlineData(el, options.pseudo ? s : styleOf(el), options.pseudo || null, options.unclippedBounds);
    const textStyle = styleData(el, s, text, options.pseudo || null, options.unclippedBounds);
    for (const field of ['font_size', 'font_weight', 'font_family', 'foreground', 'letter_spacing', 'line_height', 'text_align']) paintStyle[field] = textStyle[field];
    if (!text && !['icon', 'chart-edge'].includes(kind)) paintStyle.foreground = null;
    if (kind === 'icon' && el.localName === 'svg' && el.querySelector('path,circle,ellipse,line,polyline,polygon,rect')) {
      const shape = el.querySelector('path,circle,ellipse,line,polyline,polygon,rect'), shapeStyle = styleOf(shape);
      const property = shapeStyle.stroke !== 'none' ? 'stroke' : 'fill';
      paintStyle.foreground = color(shapeStyle[property], pathOf(shape), property);
    }
    if (kind === 'text' && !options.pseudo) {
      paintStyle.background = [0, 0, 0, 0]; paintStyle.border_color = [0, 0, 0, 0]; paintStyle.border_width = 0; paintStyle.corner_radius = 0;
      paintStyle.border_widths = [0, 0, 0, 0]; paintStyle.corner_radii = [0, 0, 0, 0]; paintStyle.border_colors = Array.from({ length: 4 }, () => [0, 0, 0, 0]);
      paintStyle.border_styles = ['none', 'none', 'none', 'none'];
      paintStyle.shadow = []; paintStyle.background_image = 'none';
      paintStyle.outline = 'none';
      outline = { value: 'none', problems: [], evidence: { source: 'actual DOM Text node is a glyph leaf with no independent CSS box; owner outline remains on its emitted DOM element',
        absence_proven: options.textNode?.nodeType === Node.TEXT_NODE, text_node_type: options.textNode?.nodeType ?? null,
        owner: nodeIds.get(el), owner_outline: outline.evidence, quantity: 'own outline of this text leaf only; not absence of its owner outline' } };
    }
    if (!text && !['icon', 'chart-edge'].includes(kind)) paintStyle.foreground = null;
    const accessibility = accessibilityOf(options.textNode || el, options.axBackend);
    const panelResize = kind === 'resize-handle' ? panelResizeEvidence(el) : null;
    const actualFonts = platformFonts(el, text, id, options);
    paintStyle.rendered_fonts = actualFonts.fonts;
    const weightRequest = text ? fontRequestEvidence(s) : null;
    const weightQuantities = fontWeightEvidence(id, weightRequest, actualFonts.fonts, !!text || kind === 'text');
    if (text && !options.pseudo && (options.ownedTextNodes || []).some(node => {
      const owned = node.parentElement ? fontRequestEvidence(styleOf(node.parentElement)) : null;
      return !owned || owned.weight !== weightRequest.weight || owned.variation_settings !== weightRequest.variation_settings;
    })) {
      weightQuantities.configured.value = null;
      weightQuantities.configured.reason = 'Owned actual Text nodes do not share the measured configured weight and variation settings.';
      unmeasured.push({ element: id, property: 'style.font_weight.configured', reason: weightQuantities.configured.reason });
    }
    if (weightQuantities.applicable)
      unmeasured.push({ element: id, property: 'style.font_weight.resolved', reason: weightQuantities.resolved.reason });
    const measured = (options.ownedTextNodes || (options.textNode ? [options.textNode] : [])).map(textMeasurement);
    const textMeasurements = measured.map(measurement => measurement.evidence);
    const geometry = textGeometry(measured, boxes, kind, options.unclippedBounds || rect(el.getBoundingClientRect()), bounds);
    for (const measurement of textMeasurements.filter(value => value.css_ellipsis_active))
      unmeasured.push({ element: id, property: 'text.ellipsis_glyph_geometry', evidence: measurement,
        reason: 'DOMRange and DOMSnapshot expose layout text advances; AX names identify text fragments but do not locate the generated ellipsis. Actual text geometry is null. The clipped range envelope is diagnostic evidence only, never substituted for painted glyph bounds.' });
    const item = { id, parent, region, order: regionOrders.get(region) || 0, kind, text,
      name: accessibility.name || panelResize?.title || accessibility.name, bounds: geometry.bounds, visible_bounds: geometry.visible_bounds, style: paintStyle,
      state: stateOf(el), layout: { ...breaks.layout, wrap: !text ? null : ['pre', 'nowrap'].includes(s.whiteSpace) ? 'none' : s.overflowWrap === 'anywhere' || s.wordBreak === 'break-all' ? 'character' : 'word',
        truncation: !text ? null : s.textOverflow === 'ellipsis' || s.webkitLineClamp !== 'none' && Number(s.webkitLineClamp) > 0 ? 'ellipsis' : /hidden|clip/.test(s.overflowX) && el.scrollWidth > el.clientWidth ? 'clip' : 'none', line_count: !text ? null : geometry.line_count },
      icon: iconOf(el, kind), evidence: { source: 'dom', selector: pathOf(el), tag: el.localName,
        class: el.getAttribute('class') || '', raw_node: nodeIds.get(el), unclipped_bounds: rect(el.getBoundingClientRect()),
        text_bounds: geometry.text_bounds, text_layout_bounds: geometry.text_layout_bounds, text_bounds_quantity: geometry.text_bounds_quantity,
        clipped_range_envelope: geometry.clipped_range_envelope, text_line_count_source: geometry.line_count_source,
        placeholder: el.getAttribute('placeholder'), value: 'value' in el ? el.value : null, aria_current: el.getAttribute('aria-current'), accessibility, platform_fonts: actualFonts.evidence, svg_strokes: svgStrokeData(el), text_measurements: textMeasurements,
        font_request: weightRequest, font_weight_quantities: weightQuantities, line_break_configuration: breaks.evidence,
        panel_resize: panelResize, outline: outline.evidence, image_resource: imageResourceEvidence(el), name_source: panelResize && !accessibility.name && panelResize.title ? 'actual DOM title attribute' : 'CDP accessibility',
        font_weight: text ? { requested_css: s.fontWeight, computed_css: textStyle.font_weight,
          resolved_faces: actualFonts.fonts, resolved_numeric_weight: null,
          source: 'getComputedStyle request + CSS.getPlatformFontsForNode resolved identity',
          reason: 'CDP reports actual face identity but not OpenType weight/variation axes; requested CSS weight is not substituted for resolved face weight.' } : null,
        occlusion_masks: occlusionMasks.get(el) || [], css_paint: { font_family: s.fontFamily, own_opacity: s.opacity, box_shadow: s.boxShadow, background_image: s.backgroundImage,
          background_size: s.backgroundSize, background_position: s.backgroundPosition, background_repeat: s.backgroundRepeat, background_origin: s.backgroundOrigin, background_clip: s.backgroundClip }, ...options.evidence } };
    regionOrders.set(region, item.order + 1);
    elements.push(item);
    for (const problem of outline.problems) {
      unmeasured.push({ element: id, ...problem, evidence: outline.evidence });
      extraction_errors.push({ type: 'outline_measurement_unavailable', node: id, ...problem });
    }
    if (item.evidence.image_resource) {
      const image = item.evidence.image_resource;
      if (image.status !== 'loaded-response-bytes') {
        unmeasured.push({ element: id, property: 'image.loaded_resource', reason: image.errors.join(' ') || 'Actual loaded image bytes are unavailable.' });
        extraction_errors.push({ type: 'image_resource_binding_unavailable', node: id, reason: image.errors.join(' ') || 'No independently bound actual loaded image response.' });
      }
      unmeasured.push({ element: id, property: 'image.rendered_content', reason: 'Actual resource bytes are preserved separately; decoded vector/raster paint is not measured by the URI or this transport collector.' });
    }
    if (text && !boxes.length) unmeasured.push({ element: id, property: 'layout.line_count', reason: 'No measured text-line rectangles were available.' });
    if (!accessibility.measured && !options.pseudo && ['button', 'icon-button', 'input', 'toggle', 'checkbox', 'tab', 'menu-item', 'dropdown', 'link', 'text'].includes(kind)) unmeasured.push({ element: id, property: 'accessibility.name_role', reason: 'No actual AX node was linked to this visible semantic element; empty names are not guessed.' });
    if (!suffix) emittedIds.set(el, id);
    return id;
  };
  const cumulativeOpacity = el => {
    let value = 1;
    for (let p = el; p; p = p.parentElement) value *= Number(styleOf(p).opacity);
    return value;
  };
  const opaqueOverlays = Array.from(document.querySelectorAll('.dialog,.settings,.details,.card,.menu')).filter(el => {
    const s = styleOf(el);
    return cumulativeOpacity(el) === 1 && color(s.backgroundColor, pathOf(el), 'background-color')?.[3] === 255 && visibleRect(el, rect(el.getBoundingClientRect()));
  });
  const roundedShape = el => {
    const s = styleOf(el), bounds = rect(el.getBoundingClientRect());
    const values = ['TopLeft', 'TopRight', 'BottomRight', 'BottomLeft'].map(key => {
      const parts = s['border' + key + 'Radius'].split(/\s+/);
      const px = (v, axis) => v.endsWith('%') ? parseFloat(v) * axis / 100 : parseFloat(v);
      return { x: px(parts[0], bounds.width), y: px(parts[1] || parts[0], bounds.height) };
    });
    // CSS Backgrounds' overlap reduction applies one common factor to all
    // corners, preserving their ellipse aspect ratios.
    const ratio = (length, sum) => sum > 0 ? length / sum : Infinity;
    const scale = Math.min(1, ratio(bounds.width, values[0].x + values[1].x), ratio(bounds.width, values[3].x + values[2].x),
      ratio(bounds.height, values[0].y + values[3].y), ratio(bounds.height, values[1].y + values[2].y));
    return { kind: 'css-rounded-rectangle', bounds, radii: values.map(v => ({ x: v.x * scale, y: v.y * scale })),
      source: 'getComputedStyle + DOMRect', selector: pathOf(el), paint_order: snapshotPaintOrder.get(el) ?? null };
  };
  const roundedContains = (shape, point) => {
    const b = shape.bounds, r = shape.radii;
    if (point.x < b.x || point.y < b.y || point.x > b.x + b.width || point.y > b.y + b.height) return false;
    const corners = [{ x: b.x + r[0].x, y: b.y + r[0].y, sx: -1, sy: -1 },
      { x: b.x + b.width - r[1].x, y: b.y + r[1].y, sx: 1, sy: -1 },
      { x: b.x + b.width - r[2].x, y: b.y + b.height - r[2].y, sx: 1, sy: 1 },
      { x: b.x + r[3].x, y: b.y + b.height - r[3].y, sx: -1, sy: 1 }];
    for (let i = 0; i < 4; i++) {
      const c = corners[i], rx = r[i].x, ry = r[i].y;
      if (rx > 0 && ry > 0 && (point.x - c.x) * c.sx > 0 && (point.y - c.y) * c.sy > 0)
        return ((point.x - c.x) / rx) ** 2 + ((point.y - c.y) / ry) ** 2 <= 1;
    }
    return true;
  };
  const roundedContainsRect = (shape, b) => [{ x: b.x, y: b.y }, { x: b.x + b.width, y: b.y },
    { x: b.x, y: b.y + b.height }, { x: b.x + b.width, y: b.y + b.height }].every(p => roundedContains(shape, p));
  const subtract = (a, b) => {
    const cross = intersect(a, b);
    if (!nonempty(cross)) return [a];
    return [{ x: a.x, y: a.y, width: a.width, height: cross.y - a.y },
      { x: a.x, y: cross.y + cross.height, width: a.width, height: a.y + a.height - cross.y - cross.height },
      { x: a.x, y: cross.y, width: cross.x - a.x, height: cross.height },
      { x: cross.x + cross.width, y: cross.y, width: a.x + a.width - cross.x - cross.width, height: cross.height }].filter(nonempty);
  };
  const fragmentsOf = (el, bounds) => {
    let parts = [bounds];
    const curvedMasks = [];
    for (const cover of opaqueOverlays) {
      if (cover === el || cover.contains(el) || el.contains(cover)) continue;
      const shape = roundedShape(cover), c = shape.bounds, s = styleOf(cover);
      if (!nonempty(intersect(bounds, c))) continue;
      let order = snapshotPaintOrder.get(el);
      for (let p = el.parentElement; p && order === undefined; p = p.parentElement) order = snapshotPaintOrder.get(p);
      if (shape.paint_order === null || order === undefined || shape.paint_order === order) {
        unmeasured.push({ element: nodeIds.get(el), property: 'visibility.paint_order', covering: shape.selector, reason: 'Cannot prove overlay ordering from the actual paint tree.' });
        continue;
      }
      if (shape.paint_order < order) continue;
      if (s.transform !== 'none' || s.mixBlendMode !== 'normal' || s.filter !== 'none') {
        unmeasured.push({ element: nodeIds.get(el), property: 'visibility.overlay_effect', covering: shape.selector, transform: s.transform, filter: s.filter, blend: s.mixBlendMode });
        continue;
      }
      const existing = occlusionMasks.get(el) || [];
      if (!existing.some(mask => mask.selector === shape.selector)) { existing.push(shape); occlusionMasks.set(el, existing); }
      const radiusX = Math.max(...shape.radii.map(r => r.x)), radiusY = Math.max(...shape.radii.map(r => r.y));
      const center = { x: c.x + radiusX, y: c.y, width: Math.max(0, c.width - radiusX * 2), height: c.height };
      const middle = { x: c.x, y: c.y + radiusY, width: c.width, height: Math.max(0, c.height - radiusY * 2) };
      parts = parts.filter(part => !roundedContainsRect(shape, part)).flatMap(part => subtract(part, center)).flatMap(part => subtract(part, middle));
      // A retained corner envelope is accompanied by its exact elliptical
      // subtraction mask. Convex rounded rectangles contain an entire box iff
      // they contain its four corners; this is an analytic test, not pixel or
      // center-point sampling. The envelope itself is not called the mask.
      parts = parts.filter(part => !roundedContainsRect(shape, part));
      if (radiusX && radiusY && parts.some(part => nonempty(intersect(part, c)))) curvedMasks.push(shape);
    }
    if (curvedMasks.length > 1 && curvedMasks.some((a, i) => curvedMasks.slice(i + 1).some(b => nonempty(intersect(a.bounds, b.bounds)))))
      unmeasured.push({ element: nodeIds.get(el), property: 'visibility.curved_mask_union', reason: 'Overlapping curved occluders need a combined clipping path before total occlusion is certified.' });
    return parts;
  };
  const paintBoundsOf = (el, layout) => {
    if (!(el instanceof SVGGeometryElement) || layout.width > 0 && layout.height > 0) return layout;
    const s = styleOf(el);
    if (s.stroke === 'none' || color(s.stroke, pathOf(el), 'stroke')?.[3] === 0 || Number(s.strokeOpacity) === 0) return layout;
    const measured = svgStrokeData(el)?.shapes[0], strokeWidth = measured?.source_width;
    if (strokeWidth === 0) return layout;
    const matrix = measured?.stroke_to_window;
    if (!matrix || !Number.isFinite(strokeWidth)) {
      unmeasured.push({ element: nodeIds.get(el), property: 'visibility.svg_stroke', reason: 'Visible SVG stroke has no measured screen transform.' });
      return layout;
    }
    // DOMRect excludes stroke. A zero-width vertical edge (or zero-height
    // horizontal edge) still paints a strip. Its transverse half-width follows
    // the actual screen matrix; round/square caps also extend the endpoints.
    const sx = Math.hypot(matrix.a, matrix.c);
    const sy = Math.hypot(matrix.b, matrix.d);
    const capped = s.strokeLinecap === 'round' || s.strokeLinecap === 'square';
    const dx = layout.width === 0 || capped && layout.height === 0 ? strokeWidth * sx / 2 : 0;
    const dy = layout.height === 0 || capped && layout.width === 0 ? strokeWidth * sy / 2 : 0;
    return { x: layout.x - dx, y: layout.y - dy, width: layout.width + 2 * dx, height: layout.height + 2 * dy };
  };
  const selectArrowEvidence = el => {
    if (el.localName !== 'select') return null;
    const s = styleOf(el), ax = accessibilityOf(el), backend = snapshotBackend.get(el);
    const uaOwner = piercedByBackend.get(backend) || null;
    const ownerIdentity = uaOwner?.nodeType === 1 && uaOwner?.nodeName === 'SELECT' && uaOwner.backendNodeId === backend;
    const appearance = s.appearance || s.webkitAppearance || null;
    // Suppressing native appearance does not prove an author-created icon is
    // absent. Conversely a listbox is not a collapsed native menu-list. Neither
    // is required to contain the theme arrow merely because its tag is SELECT.
    const nativeSuppressed = appearance === 'none';
    const listbox = (el.multiple || el.size > 1) && ax.measured && ax.role === 'listbox' && appearance !== 'base-select';
    const mode = nativeSuppressed ? 'native-appearance-suppressed' : listbox ? 'listbox' :
      appearance === 'base-select' ? 'customizable-picker' : ['auto', 'menulist', 'menulist-button'].includes(appearance) ? 'native-menu-list' : 'unresolved-select-appearance';
    const axNodes = [], seen = new Set(), pending = [...(ax.node_ids || [])];
    while (pending.length) {
      const id = pending.shift();
      if (seen.has(id)) continue;
      seen.add(id);
      const node = axById.get(id);
      if (node) { axNodes.push(node); pending.push(...(node.childIds || [])); }
    }
    let pickerStyle = null, pickerError = null;
    try {
      const picker = getComputedStyle(el, '::picker-icon');
      pickerStyle = { pseudo: '::picker-icon', quantity: 'computed pseudo request, not proof of painted presence or geometry',
        content: picker.content, display: picker.display, visibility: picker.visibility, opacity: picker.opacity,
        width: picker.width, height: picker.height, color: picker.color, background: picker.backgroundColor,
        transform: picker.transform, appearance: picker.appearance };
    } catch (error) { pickerError = String(error); }
    return { kind: 'icon', part: 'select-arrow', mode, requires_measurement: !nativeSuppressed && !listbox,
      source: 'actual visible SELECT owner + computed appearance + CDP DOM/AX receipts',
      owner_backend_node_id: backend ?? null, owner_selector: pathOf(el), owner_bounds: rect(el.getBoundingClientRect()),
      owner_state: { multiple: el.multiple, size: el.size, disabled_property: el.disabled, disabled_selector: el.matches(':disabled'),
        focused: document.activeElement === el, hovered: el.matches(':hover'), selected_index: el.selectedIndex, value: el.value,
        expanded: (ax.properties || []).find(property => property.name === 'expanded')?.value?.value ?? null },
      owner_style: { appearance, direction: s.direction, writing_mode: s.writingMode, zoom: s.zoom,
        transform: s.transform, transform_origin: s.transformOrigin, color: s.color, background: s.backgroundColor,
        color_scheme: s.colorScheme, font_size: s.fontSize, display: s.display, visibility: s.visibility, opacity: s.opacity,
        border_widths: ['Top', 'Right', 'Bottom', 'Left'].map(side => s['border' + side + 'Width']),
        padding: ['Top', 'Right', 'Bottom', 'Left'].map(side => s['padding' + side]) },
      owner_accessibility: ax, ax_subtree: axNodes, computed_picker_icon: pickerStyle, computed_picker_icon_error: pickerError,
      pierced_dom: { source: 'CDP.DOM.getDocument(depth=-1,pierce=true)', owner_identity_matches: ownerIdentity,
        owner: uaOwner, quantity: 'actual captured DOM and UA nodes; lack of an arrow node does not establish absence of theme paint' },
      snapshot_pseudo_parts: pseudoByOwner.get(el) || [],
      screenshot: { scene_id: meta.scene_id, file: meta.screenshot_file ?? null,
        quantity: 'whole-scene PNG captured before these DOM measurements; owner bounds are not an arrow pixel mask',
        arrow_pixel_mask: null, arrow_pixel_bounds: null, arrow_pixels: null },
      painted_presence: null, bounds: null, path: null, style: null, state: null,
      measurement_limit: 'The owner box, CSS request, AX combobox and UA subtree do not expose the native theme drawPath or certify its pixels. No source-code dimensions, fixed right-side region or parent color are substituted for actual arrow geometry/style. Native appearance none/listbox modes make no claim that custom decorations are absent.' };
  };
  const recordSelectArrowCoverage = (raw, evidence) => {
    if (!evidence) return;
    raw.ua_select_arrow = evidence;
    if (!evidence.requires_measurement) return;
    unmeasured.push({ element: raw.id, property: 'select_arrow.rendered_part', evidence,
      reason: 'This visible select can paint a native or customizable picker arrow. Independent arrow presence, bounds, path, style and state remain unmeasured; its owner and source constants are not substitutes.' });
    extraction_errors.push({ type: 'ua_select_arrow_measurement_unavailable', node: raw.id, kind: 'icon', part: 'select-arrow',
      reason: 'The actual select decoration is retained as an unresolved paint obligation, not silently omitted because no DOM SVG exists.' });
  };
  const resizeHandleEvidence = el => {
    const s = styleOf(el);
    if (el.localName !== 'textarea' || !s.resize || s.resize === 'none') return null;
    const p = getComputedStyle(el, '::-webkit-resizer'), ownerAX = accessibilityOf(el);
    const descendants = [], seen = new Set(), pending = [...(ownerAX.node_ids || [])];
    while (pending.length) {
      const id = pending.shift();
      if (seen.has(id)) continue;
      seen.add(id);
      const node = axById.get(id);
      if (node) { descendants.push(node); pending.push(...(node.childIds || [])); }
    }
    return { kind: 'resize-handle', source: 'actual textarea metrics, computed resize/pseudo style, DOMSnapshot and AX records',
      owner_bounds: rect(el.getBoundingClientRect()), owner_value: el.value, owner_placeholder: el.getAttribute('placeholder'),
      owner_resize: s.resize, owner_direction: s.direction, owner_writing_mode: s.writingMode,
      owner_overflow_x: s.overflowX, owner_overflow_y: s.overflowY, owner_disabled: el.disabled, owner_readonly: el.readOnly,
      owner_scroll_width: el.scrollWidth, owner_scroll_height: el.scrollHeight, owner_client_width: el.clientWidth, owner_client_height: el.clientHeight,
      computed_pseudo: { pseudo: '::-webkit-resizer', quantity: 'computed pseudo request, not measured grip paint or proof of existence',
        display: p.display, visibility: p.visibility, opacity: p.opacity, width: p.width, height: p.height, background: p.backgroundColor,
        color: p.color, cursor: p.cursor, border_widths: ['Top', 'Right', 'Bottom', 'Left'].map(side => p['border' + side + 'Width']),
        border_colors: ['Top', 'Right', 'Bottom', 'Left'].map(side => p['border' + side + 'Color']),
        corner_radii: ['TopLeft', 'TopRight', 'BottomRight', 'BottomLeft'].map(corner => p['border' + corner + 'Radius']) },
      dom_snapshot_parts: (pseudoByOwner.get(el) || []).filter(part => /resizer/.test(part.type)),
      ax_subtree: descendants, painted_presence: null, bounds: null, style: null, state: null,
      measurement_limit: 'Textarea resize capability, owner bounds, pseudo computed values and AX owner/subtree are not independently measured grip paint. Pointer hit success also does not establish its painted geometry. No canonical grip is invented.' };
  };
  const scrollbarEvidence = el => {
    const s = styleOf(el), axes = [];
    if (s.scrollbarWidth === 'none') return null;
    if (s.overflowX === 'scroll' || s.overflowX === 'auto' && el.scrollWidth > el.clientWidth) axes.push('horizontal');
    if (s.overflowY === 'scroll' || s.overflowY === 'auto' && el.scrollHeight > el.clientHeight) axes.push('vertical');
    if (!axes.length) return null;
    const parts = ['::-webkit-scrollbar', '::-webkit-scrollbar-button', '::-webkit-scrollbar-track', '::-webkit-scrollbar-track-piece', '::-webkit-scrollbar-thumb', '::-webkit-scrollbar-corner', '::-webkit-resizer'].map(pseudo => {
      const p = getComputedStyle(el, pseudo);
      return { pseudo, display: p.display, visibility: p.visibility, opacity: p.opacity,
        source: 'computed pseudo style request, not evidence that the UA painted this part', painted_presence: null, painted_bounds: null,
        width: p.width, height: p.height, background: p.backgroundColor, background_clip: p.backgroundClip,
        computed_background_rgba: computedSrgb(p.backgroundColor).rgba,
        background_image: p.backgroundImage, box_shadow: p.boxShadow, content: p.content,
        transform: p.transform, filter: p.filter, mix_blend_mode: p.mixBlendMode,
        border_widths: ['Top', 'Right', 'Bottom', 'Left'].map(side => p['border' + side + 'Width']),
        border_styles: ['Top', 'Right', 'Bottom', 'Left'].map(side => p['border' + side + 'Style']),
        border_colors: ['Top', 'Right', 'Bottom', 'Left'].map(side => p['border' + side + 'Color']),
        computed_border_rgba: ['Top', 'Right', 'Bottom', 'Left'].map(side => computedSrgb(p['border' + side + 'Color']).rgba),
        corner_radii: ['TopLeft', 'TopRight', 'BottomRight', 'BottomLeft'].map(corner => p['border' + corner + 'Radius']) };
    });
    if (parts[0].display === 'none' || parts[0].visibility === 'hidden' || parts[0].opacity?.trim() !== '' && Number(parts[0].opacity) === 0) return null;
    const ancestry = [];
    for (let p = el; p; p = p.parentElement) {
      const ps = styleOf(p);
      ancestry.push({ selector: pathOf(p), transform: ps.transform, perspective: ps.perspective, zoom: ps.zoom,
        opacity: ps.opacity, filter: ps.filter, backdrop_filter: ps.backdropFilter, mix_blend_mode: ps.mixBlendMode,
        clip_path: ps.clipPath, mask_image: ps.maskImage, background_image: ps.backgroundImage });
    }
    return { source: 'actual scroll metrics + getComputedStyle UA pseudo styles', axes, owner_bounds: rect(el.getBoundingClientRect()),
      owner_backend_node_id: snapshotBackend.get(el) ?? null, owner_style: { border_widths: ['Top', 'Right', 'Bottom', 'Left'].map(side => s['border' + side + 'Width']),
        transform: s.transform, zoom: s.zoom, flex_direction: s.flexDirection }, ancestry,
      client_width: el.clientWidth, client_height: el.clientHeight, client_left: el.clientLeft, client_top: el.clientTop,
      offset_width: el.offsetWidth, offset_height: el.offsetHeight, scroll_width: el.scrollWidth, scroll_height: el.scrollHeight,
      scroll_left: el.scrollLeft, scroll_top: el.scrollTop, scrollbar_width: s.scrollbarWidth, scrollbar_gutter: s.scrollbarGutter,
      direction: s.direction, writing_mode: s.writingMode, overflow_x: s.overflowX, overflow_y: s.overflowY, parts,
      dom_snapshot_parts: (pseudoByOwner.get(el) || []).filter(part => /scrollbar|resizer/.test(part.type)),
      actual_ua_parts_presence: null,
      measurement_limit: 'CSS overflow and integer client/offset metrics establish a scroll container, not actual overlay visibility or individual track/thumb/button paint bounds. Computed pseudo styles do not establish part existence.',
      measured_part_bounds: null, measured_part_pixels: null };
  };
  const scrollbarGutter = (evidence, axis) => {
    // Client/offset metrics expose reserved layout space, not the thumb box.
    // Only use their exact integer, untransformed case; rounding/overlay gaps
    // remain unknown instead of being expanded to a requested CSS thickness.
    const fail = reason => ({ bounds: null, reason, quantity: 'reserved DOM scrollbar gutter; not a thumb or hit rectangle' });
    const box = evidence.owner_bounds, metrics = ['client_width', 'client_height', 'client_left', 'client_top', 'offset_width', 'offset_height'];
    const px = value => typeof value === 'string' && /^\d+(?:\.\d+)?px$/.test(value) ? Number.parseFloat(value) : null;
    const borders = evidence.owner_style.border_widths.map(px);
    if (!metrics.every(key => Number.isInteger(evidence[key]) && evidence[key] >= 0) || !borders.every(Number.isInteger) ||
        !Object.values(box).every(Number.isInteger) || box.width !== evidence.offset_width || box.height !== evidence.offset_height)
      return fail('Integer DOM metrics do not independently resolve this fractional/rounded layout box.');
    if (evidence.writing_mode !== 'horizontal-tb' || evidence.ancestry.some(p => p.transform !== 'none' || p.perspective !== 'none' || !['1', 'normal'].includes(p.zoom)))
      return fail('Actual writing mode/transform/zoom does not expose an untransformed scrollbar gutter.');
    const [bt, br, bb, bl] = borders;
    const vertical = box.width - evidence.client_width - bl - br;
    const horizontal = box.height - evidence.client_height - bt - bb;
    const left = evidence.client_left - bl, top = evidence.client_top - bt;
    const requested = px(axis === 'vertical' ? evidence.parts[0].width : evidence.parts[0].height);
    if (vertical < 0 || horizontal < 0 || top !== 0 || ![0, vertical].includes(left))
      return fail('Measured reserved space cannot be assigned to one scrollbar side without guessing.');
    const thickness = axis === 'vertical' ? vertical : horizontal;
    if (thickness <= 0 || requested !== thickness)
      return fail('No uniquely measured reserved gutter agreeing with the actual pseudo thickness; overlay or stable gutters remain unknown.');
    const bounds = axis === 'vertical' ? { x: left ? box.x + bl : box.x + evidence.client_left + evidence.client_width,
      y: box.y + evidence.client_top, width: vertical, height: evidence.client_height } : {
      x: box.x + evidence.client_left, y: box.y + evidence.client_top + evidence.client_height, width: evidence.client_width, height: horizontal };
    if (bounds.width <= 0 || bounds.height <= 0) return fail('The measured reserved gutter has no positive area.');
    return { bounds, reason: null, quantity: 'reserved DOM scrollbar gutter outer rectangle; not individual track-piece, thumb or hit geometry',
      source: 'actual integer border/client/offset metrics and unchanged coordinate axes', side: axis === 'vertical' ? left ? 'left' : 'right' : 'bottom' };
  };
  const emitScrollbarParts = (el, raw, evidence, parent) => {
    const slots = [], region = regionOf(el);
    evidence.gutters = {};
    for (const axis of evidence.axes) {
      const gutter = scrollbarGutter(evidence, axis);
      if (gutter.bounds) {
        gutter.visible_bounds = visibleRect(el, gutter.bounds);
        gutter.visible_fragments = gutter.visible_bounds ? fragmentsOf(el, gutter.visible_bounds) : [];
        gutter.occlusion_masks = occlusionMasks.get(el) || [];
        gutter.visibility_gaps = unmeasured.filter(gap => gap.element === raw.id && gap.property?.startsWith('visibility.'));
        const equal = other => other && ['x', 'y', 'width', 'height'].every(key => other[key] === gutter.bounds[key]);
        gutter.fully_visible = equal(gutter.visible_bounds) && gutter.visible_fragments.length === 1 && equal(gutter.visible_fragments[0]) && !gutter.occlusion_masks.length && !gutter.visibility_gaps.length;
      } else { gutter.visible_bounds = null; gutter.fully_visible = false; }
      evidence.gutters[axis] = gutter;
      const extent = axis === 'vertical' ? evidence.scroll_height - evidence.client_height : evidence.scroll_width - evidence.client_width;
      const offset = axis === 'vertical' ? evidence.scroll_top : evidence.scroll_left;
      const normalFlow = evidence.writing_mode === 'horizontal-tb' && !['column-reverse', 'row-reverse'].includes(evidence.owner_style.flex_direction) && (axis === 'vertical' || evidence.direction === 'ltr');
      const position = normalFlow && Number.isFinite(extent) && extent >= 0 && Number.isFinite(offset) && offset >= 0 && offset <= extent ? extent === 0 ? 0 : offset / extent : null;
      for (const kind of ['scrollbar', 'scrollbar-thumb']) {
        const id = raw.id + ':' + kind + ':' + axis, isThumb = kind === 'scrollbar-thumb';
        const bounds = isThumb ? null : gutter.bounds;
        const item = { id, parent, region, order: 0, kind, text: '', name: null, bounds,
          visible_bounds: isThumb ? null : gutter.visible_bounds,
          style: Object.fromEntries(['font_size', 'font_weight', 'foreground', 'background', 'border_color', 'border_width', 'corner_radius',
            'border_widths', 'border_colors', 'border_styles', 'corner_radii', 'opacity', 'background_image', 'shadow', 'outline'].map(key => [key, null])),
          state: { enabled: Number.isFinite(extent) ? extent > 0 : null, selected: null, checked: null, expanded: null,
            focused: null, hovered: null, unread: null, orientation: axis, scroll_position: position },
          layout: { wrap: null, truncation: null, line_count: null, break_strategy_version: 1,
            normal_break_strategy: null, emergency_break_strategy: null }, icon: null,
          evidence: { source: 'actual DOM scroll owner; unresolved UA part retained explicitly', raw_node: raw.id, selector: pathOf(el),
            line_break_configuration: { applicable: false, source: 'actual DOM scrollbar part projection', owner: raw.id, raw: {},
              reason: 'This scrollbar part has no emitted text under the existing text applicability predicate.' },
            owner_backend_node_id: evidence.owner_backend_node_id, orientation: axis, gutter,
            outer_bounds: bounds, hit_bounds: null, ink_bounds: null, painted_presence: null,
            bounds_quantity: isThumb ? 'actual thumb part border box remains unmeasured' : gutter.quantity,
            scroll_state: { offset, range: extent, client_extent: axis === 'vertical' ? evidence.client_height : evidence.client_width,
              content_extent: axis === 'vertical' ? evidence.scroll_height : evidence.scroll_width,
              normalized_quantity: 'actual scroll offset/range state only; never used to derive thumb geometry' },
            computed_pseudo: evidence.parts.find(part => part.pseudo === (isThumb ? '::-webkit-scrollbar-thumb' : '::-webkit-scrollbar')),
            measurement_limit: 'DOM gutter and CSS pseudo requests do not expose individual transparent borders, hit rectangles, hover/name or resolved UA part paint. Original PNG sampling supplies separate ink evidence only.' } };
        elements.push(item); raw.emitted.push(id); slots.push(id);
        unmeasured.push({ element: id, property: 'scrollbar.ua_part', reason: item.evidence.measurement_limit });
        extraction_errors.push({ type: 'ua_scrollbar_part_measurement_unavailable', node: id, kind,
          reason: 'Real scroll-owner obligation is explicit; unknown part geometry/style/state cannot pass as omitted UI.' });
      }
    }
    scrollbarOrder.set(el, slots);
  };
  const readingOrderIds = (root, ids, scrollSlots = new WeakMap()) => {
    // CSS tree-abiding pseudo-elements occur at their originating element's
    // content boundaries. Enumerate mixed text/element children, not separate
    // text and element passes: ::after follows every descendant, while a code
    // line's ::before number precedes its source text.
    const ordered = [];
    const visit = el => {
      const id = ids.get(el);
      if (id !== undefined) ordered.push(id, id + '::marker', id + '::before');
      let textIndex = 0;
      for (const child of el.childNodes) {
        if (child.nodeType === Node.TEXT_NODE) {
          if (id !== undefined) ordered.push(id + ':text-' + textIndex);
          textIndex++;
        } else if (child.nodeType === Node.ELEMENT_NODE) visit(child);
      }
      if (id !== undefined) ordered.push(id + '::after');
      ordered.push(...(scrollSlots.get(el) || []));
    };
    visit(root);
    return ordered;
  };
  const assignReadingOrder = (items, rawNodes, orderedIds, errors) => {
    const positions = new Map(orderedIds.map((id, position) => [id, position]));
    // Every emitted identity must have a real source slot. Retain an unknown
    // identity and fail extraction rather than dropping it to repair order.
    for (const item of items) if (!positions.has(item.id)) errors.push({ type: 'reading_order_source_unavailable', node: item.id,
      reason: 'Emitted identity has no DOM child/pseudo source position; it remains in the inventory.' });
    const compare = (a, b) => (positions.get(a) ?? Number.MAX_SAFE_INTEGER) - (positions.get(b) ?? Number.MAX_SAFE_INTEGER);
    items.sort((a, b) => compare(a.id, b.id));
    const regionPositions = new Map();
    for (const item of items) {
      item.order = regionPositions.get(item.region) || 0;
      regionPositions.set(item.region, item.order + 1);
    }
    for (const raw of rawNodes) raw.emitted.sort(compare);
  };
  const all = Array.from(document.body.querySelectorAll('*'));
  all.unshift(document.body);
  all.forEach((el, index) => nodeIds.set(el, 'dom-' + index));
  const suppressedText = new WeakSet();
  for (const el of all) {
    const id = nodeIds.get(el), s = styleOf(el), unclipped = rect(el.getBoundingClientRect());
    const paintBounds = paintBoundsOf(el, unclipped), bounds = visibleRect(el, paintBounds), fragments = bounds ? fragmentsOf(el, bounds) : [];
    const raw = { id, parent: nodeIds.get(el.parentElement) || null, selector: pathOf(el), tag: el.localName,
      attributes: Object.fromEntries(Array.from(el.attributes).map(a => [a.name, a.value])), bounds: unclipped,
      visible_bounds: bounds, paint_bounds: paintBounds, visible_fragments: fragments, occlusion_masks: occlusionMasks.get(el) || [], display: s.display, visibility: s.visibility, opacity: s.opacity, emitted: [],
      accessibility: accessibilityOf(el), details_visibility: detailsVisibilityEvidence(el), image_resource: imageResourceEvidence(el), outline: outlineData(el, s).evidence,
      text_nodes: Array.from(el.childNodes).filter(n => n.nodeType === Node.TEXT_NODE).map((n, i) => ({ id: id + ':raw-text-' + i, text: n.nodeValue,
        details_visibility: detailsVisibilityEvidence(el, true), owned_by: suppressedText.has(n) ? 'ancestor control' : null })) };
    raw_nodes.push(raw);
    const panelResize = panelResizeEvidence(el);
    if (panelResize) {
      raw.panel_resize = panelResize;
      if (bounds && fragments.length && panelResize.has_pointer_handler !== true) {
        unmeasured.push({ element: id, property: 'resize_handle.interaction', evidence: panelResize,
          reason: 'The actual panel handle is retained, but no successful installed pointerdown listener receipt is bound to its actual DOM backend identity.' });
        extraction_errors.push({ type: 'panel_resize_interaction_unavailable', node: id,
          reason: 'A class, cursor or onpointerdown IDL property cannot substitute for actual addEventListener registration evidence.' });
      }
    }
    if (!bounds || !fragments.length || el.closest('script,style,option')) { raw.projection_reason = raw.details_visibility?.hidden ? 'closed-details-content' : !bounds ? 'hidden-or-fully-clipped' : !fragments.length ? 'fully-occluded' : 'nonrendered-content'; continue; }
    recordSelectArrowCoverage(raw, selectArrowEvidence(el));
    const resizeHandle = resizeHandleEvidence(el);
    if (resizeHandle) {
      raw.resize_handle = resizeHandle;
      unmeasured.push({ element: id, property: 'resize_handle.rendered_part', evidence: resizeHandle,
        reason: 'The visible resizable textarea can paint a UA resize-handle. Its independent painted presence, bounds, style and state are unmeasured; the owner box and corner pointer coordinates cannot replace them.' });
      extraction_errors.push({ type: 'ua_resize_handle_measurement_unavailable', node: id, kind: 'resize-handle',
        reason: 'Actual UA resize-handle paint has no independently measured canonical counterpart; retained as a coverage failure.' });
    }
    const scrollbar = scrollbarEvidence(el);
    if (scrollbar) {
      raw.scrollbar = scrollbar;
      unmeasured.push({ element: id, property: 'scrollbar.rendered_parts', evidence: scrollbar,
        reason: 'This visible scroll container can paint native UA scrollbar parts. DOM/DOMSnapshot do not expose their actual thumb/track paint bounds; overlay visibility and pixels require independent evidence. No scrollbar is silently declared absent or synthesized from scroll ratios.' });
    }
    if (s.clipPath !== 'none' || s.maskImage !== 'none') unmeasured.push({ element: id, property: 'visibility.shape_clip', reason: 'Nonrectangular CSS clip/mask requires pixel-mask visibility evidence.', clip_path: s.clipPath, mask_image: s.maskImage });
    if (el instanceof SVGElement && el.localName !== 'svg' && !el.matches('.oc-lines .edge,.oc-lines .link')) { raw.projection_reason = 'vector-owned-by-svg-icon'; continue; }
    let parent = null;
    for (let p = el.parentElement; p && !parent; p = p.parentElement) parent = emittedIds.get(p) || null;
    const regionEvidence = supplementalRegionEvidence(el, s, raw.accessibility);
    if (regionEvidence) raw.region_projection_evidence = regionEvidence;
    const kind = kindOf(el, s, regionEvidence), own = kind ? ownedText(el, kind) : null;
    if (kind) {
      const text = own?.text || '';
      const inputMeasurement = kind === 'input' || kind === 'dropdown' ? inputTextMeasurement(el) : null;
      const emitted = emit(el, kind, text, bounds, parent, '', { style: own?.style || s, ownedTextNodes: own?.nodes || [], textBoxes: own ? own.nodes.length ? textRects(own.nodes) : inputMeasurement?.boxes || [] : [], evidence: { visible_fragments: fragments, region_projection: regionEvidence, text_ownership: own?.nodes.map(n => ({ parent: nodeIds.get(n.parentElement), text: n.nodeValue })) || [], input_text_measurement: inputMeasurement?.evidence || null } });
      raw.emitted.push(emitted); parent = emitted;
      if (own) own.nodes.forEach(n => { suppressedText.add(n); for (const t of raw.text_nodes) if (t.text === n.nodeValue) t.owned_by = emitted; });
      if (el.localName === 'canvas') extraction_errors.push({ type: 'canvas_semantics_unavailable', node: id, reason: 'Canvas pixels are captured but internal element identities require a separate instrumentation contract.' });
    }
    if (scrollbar) emitScrollbarParts(el, raw, scrollbar, parent);
    const childText = Array.from(el.childNodes).filter(n => n.nodeType === Node.TEXT_NODE);
    for (let i = 0; i < childText.length; i++) {
      const n = childText[i], text = visibleText(n, s);
      if (!text.trim() || suppressedText.has(n)) continue;
      if (!snapshotRenderedText.has(n)) unmeasured.push({ element: id + ':text-' + i, property: 'text.rendered_whitespace', reason: 'No CDP LayoutText string; raw text is preserved without whitespace substitutions.' });
      const measurement = textMeasurement(n), textBounds = measurement.clipped_range_envelope;
      if (!textBounds) continue;
      const visible = fragmentsOf(el, textBounds);
      if (!visible.length) continue;
      const emitted = emit(el, 'text', text, textBounds, parent, ':text-' + i, { textNode: n, unclippedBounds: measurement.range_bounds, textBoxes: measurement.range_boxes, evidence: { source_text: n.nodeValue, visible_fragments: visible, visible_fragments_quantity: 'candidate font-metric range envelopes after clipping and occlusion; not measured glyph ink' } });
      raw.emitted.push(emitted);
    }
    for (const pseudo of ['::before', '::after', '::marker']) {
      const ps = getComputedStyle(el, pseudo), content = ps.content;
      const snapshotPseudoElement = (pseudoByOwner.get(el) || []).find(x => x.type === pseudo);
      if (ps.display === 'none' || ps.visibility !== 'visible' || Number(ps.opacity) === 0 || !snapshotPseudoElement && (!content || content === 'none' || content === 'normal')) continue;
      raw.pseudo_elements ??= [];
      const pseudoRecord = { pseudo, content, style: styleData(el, ps, content !== '""', pseudo, snapshotPseudoElement?.bounds),
        outline: outlineData(el, ps, pseudo, snapshotPseudoElement?.bounds).evidence,
        snapshot_node: snapshotPseudoElement?.index ?? null, bounds: snapshotPseudoElement?.bounds ?? null,
        layout_rows: snapshotPseudoElement?.layout_rows || [], selected_layout_indices: snapshotPseudoElement?.selected_layout_indices || [],
        layout_measurement: snapshotPseudoElement?.layout_measurement || null, layout_problems: snapshotPseudoElement?.problems || [],
        computed_corner_radii: ['TopLeft', 'TopRight', 'BottomRight', 'BottomLeft'].map(corner => ps['border' + corner + 'Radius']) };
      if (!snapshotPseudoElement?.bounds) { pseudoRecord.style.corner_radius = null; pseudoRecord.style.corner_radii = null; }
      raw.pseudo_elements.push(pseudoRecord);
      if (!snapshotPseudoElement) {
        extraction_errors.push({ type: 'pseudo_geometry_unavailable', node: id, selector: pathOf(el), pseudo, content, reason: 'No matching CDP DOMSnapshot layout; estimated rectangles are not parity evidence.' });
        continue;
      }
      const p = snapshotPseudoElement;
      for (const problem of p.problems || []) {
        unmeasured.push({ element: id + pseudo, ...problem, layout_rows: p.layout_rows });
        extraction_errors.push({ type: 'pseudo_layout_measurement_unavailable', node: id + pseudo, ...problem });
      }
      if (!p.bounds) { pseudoRecord.projection_reason = 'unresolved-pseudo-layout'; continue; }
      const vb = visibleRect(el, p.bounds);
      const pseudoFragments = vb ? fragmentsOf(el, vb) : [];
      pseudoRecord.visible_bounds = vb; pseudoRecord.visible_fragments = pseudoFragments;
      if (!vb || !pseudoFragments.length) { pseudoRecord.projection_reason = !vb ? 'hidden-or-fully-clipped' : 'fully-occluded'; continue; }
      const pkind = p.text ? pseudo === '::marker' ? 'icon' : 'text' : 'card';
      const emitted = emit(el, pkind, p.text, vb, parent, pseudo, { style: ps, pseudo, textBoxes: p.text_boxes, unclippedBounds: p.bounds, axBackend: p.backend_node_id,
        evidence: { source: 'CDP.DOMSnapshot', snapshot_node: p.index, snapshot_layout: p.layout_index,
          snapshot_layout_rows: p.layout_rows, selected_layout_indices: p.selected_layout_indices, layout_measurement: p.layout_measurement,
          backend_node_id: p.backend_node_id, paint_order: p.paint_order } });
      if (pkind === 'icon') elements[elements.length - 1].icon = { source: 'text-glyph', glyph: p.text };
      pseudoRecord.projection_reason = 'paint-or-text'; pseudoRecord.emitted = emitted;
      raw.emitted.push(emitted);
    }
    raw.projection_reason = raw.emitted.length ? 'paint-or-semantic-or-text' : 'layout-only-wrapper-or-owned-label';
  }
  assignReadingOrder(elements, raw_nodes, readingOrderIds(document.body, nodeIds, scrollbarOrder), extraction_errors);
  return { schema_version: 1, scene_id: meta.scene_id, client: 'reference', viewport,
    lang: meta.lang || document.documentElement.lang, theme: meta.theme || document.documentElement.dataset.theme, reference_environment: meta.reference_environment || null,
    capture: { source: 'production-dom', coordinate_space: 'viewport-css-pixels', device_scale_factor: devicePixelRatio,
      text_policy: 'Uniform simple control labels are owned by the control; rich labels are independent text nodes.',
      reading_order_policy: 'Actual DOM child-node order with CSS tree-abiding pseudo-elements: originating semantic container, ::marker, ::before, mixed text/element descendants, ::after. Regions have independent contiguous order. No element or measurement is removed to fix order.',
      visibility_policy: 'Viewport/ancestor clips, SVG stroke visibility, actual paint order, and analytic rounded-rectangle subtraction masks. visible_fragments are rectangular envelopes; occlusion_masks retain exact curved clipping. Unresolved compound masks remain failures.' },
    capture_evidence: { color_policy: 'Canonical colors are independently parsed computed, unpremultiplied sRGB float RGBA channels on 0..255. Canvas RGBA8 is a separate raster diagnostic, never a fallback or a source of canonical channels.',
      colors: Array.from(colors.values()), image_resources: meta.image_resources ? { file: meta.image_resources.file,
        image_count: Object.keys(meta.image_resources.images || {}).length, response_count: meta.image_resources.responses?.length || 0,
        errors: meta.image_resources.errors || [] } : null },
    elements, raw_nodes, raw_ax_nodes, extraction_errors, coverage: { raw_nodes: raw_nodes.length, emitted_elements: elements.length, unmeasured },
    summary: { dom_nodes: raw_nodes.length, elements: elements.length, extraction_errors: extraction_errors.length } };
}
