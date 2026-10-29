// Read-only extraction of the rendered production DOM. No reference fixture or
// native element data is used to manufacture counterpart elements.
(meta) => {
  'use strict';
  const elements = [], raw_nodes = [], extraction_errors = [], unmeasured = [];
  for (const error of meta.input_text_errors || []) extraction_errors.push({ type: 'input_text_capture_error', detail: error });
  const viewport = { width: innerWidth, height: innerHeight, scale: devicePixelRatio };
  const nodeIds = new WeakMap(), emittedIds = new WeakMap(), styles = new WeakMap(), occlusionMasks = new WeakMap();
  const colorCanvas = new OffscreenCanvas(1, 1);
  const colorContext = colorCanvas.getContext('2d', { willReadFrequently: true });
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
  const color = (css, path) => {
    if (!css || css === 'none') return [0, 0, 0, 0];
    if (colors.has(css)) return colors.get(css);
    if (!CSS.supports('color', css)) {
      extraction_errors.push({ type: 'color_unreadable', node: path, value: css });
      return null;
    }
    colorContext.clearRect(0, 0, 1, 1);
    colorContext.fillStyle = css;
    colorContext.fillRect(0, 0, 1, 1);
    const result = Array.from(colorContext.getImageData(0, 0, 1, 1).data);
    colors.set(css, result);
    return result;
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
  const snapshot = meta.dom_snapshot, snapshotDocument = snapshot?.documents?.[0];
  const snapshotStrings = snapshot?.strings || [], snapshotNodes = snapshotDocument?.nodes;
  const snapshotLayout = snapshotDocument?.layout, snapshotTextBoxes = snapshotDocument?.textBoxes;
  const snapshotElements = new Map(), snapshotPseudo = new Map(), pseudoByOwner = new WeakMap();
  const snapshotInputBoxes = new WeakMap(), snapshotInputFontOwners = new WeakMap(), snapshotBackend = new WeakMap(), snapshotRenderedText = new WeakMap(), snapshotPaintOrder = new WeakMap();
  const axByBackend = new Map(), raw_ax_nodes = meta.ax_tree?.nodes || [];
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
      }
      else extraction_errors.push({ type: 'snapshot_text_identity_changed', snapshot_node: i, parent: selectorForSnapshot(parentIndex), reason: 'The live text node no longer matches the DOMSnapshot node.' });
    }
    function selectorForSnapshot(index) { return selectors.get(index) || null; }
    const snapshotRect = a => ({ x: a[0] - (snapshotDocument.scrollOffsetX || 0), y: a[1] - (snapshotDocument.scrollOffsetY || 0), width: a[2], height: a[3] });
    const descendantOf = (node, ancestor) => {
      for (let p = node; p >= 0; p = snapshotNodes.parentIndex[p]) if (p === ancestor) return true;
      return false;
    };
    for (const [index, type] of snapshotPseudo) {
      const owner = snapshotElements.get(snapshotNodes.parentIndex[index]), li = layoutByNode.get(index);
      if (!owner || li === undefined) continue;
      const childLayouts = snapshotLayout.nodeIndex.map((n, l) => ({ n, l })).filter(x => descendantOf(x.n, index));
      const text = childLayouts.map(x => snapshotStrings[snapshotLayout.text[x.l]] || '').join('');
      const boxes = (snapshotTextBoxes?.layoutIndex || []).flatMap((l, k) => childLayouts.some(x => x.l === l) ? [snapshotRect(snapshotTextBoxes.bounds[k])] : []);
      const data = { type: '::' + type, index, layout_index: li, bounds: snapshotRect(snapshotLayout.bounds[li]), text, text_boxes: boxes,
        paint_order: snapshotLayout.paintOrders?.[li] ?? null, backend_node_id: snapshotNodes.backendNodeId?.[index] };
      const list = pseudoByOwner.get(owner) || []; list.push(data); pseudoByOwner.set(owner, list);
    }
    for (const [index, actual] of snapshotElements) {
      if (!actual.matches('input,textarea,select')) continue;
      const boxes = (snapshotTextBoxes?.layoutIndex || []).flatMap((l, k) => descendantOf(snapshotLayout.nodeIndex[l], index) ? [snapshotRect(snapshotTextBoxes.bounds[k])] : []);
      snapshotInputBoxes.set(actual, boxes);
      const fontOwners = snapshotLayout.nodeIndex.flatMap((node, layoutIndex) => {
        if (!descendantOf(node, index) || !(snapshotStrings[snapshotLayout.text[layoutIndex]] || '').trim()) return [];
        const owner = snapshotNodes.nodeType[node] === Node.TEXT_NODE ? snapshotNodes.parentIndex[node] : node;
        return [snapshotNodes.backendNodeId[owner]];
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
  const visibleRect = (el, inputRect) => {
    let clipped = intersect(inputRect, { x: 0, y: 0, width: innerWidth, height: innerHeight });
    for (let p = el; p; p = p.parentElement) {
      const s = styleOf(p);
      if (s.display === 'none' || s.visibility !== 'visible' || Number(s.opacity) === 0 || p.hidden) return null;
      if (p !== el && (/(hidden|clip|scroll|auto)/.test(s.overflowX) || /(hidden|clip|scroll|auto)/.test(s.overflowY))) {
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
  const textNodes = el => {
    const output = [], walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (n.parentElement.closest('svg,script,style,option')) continue;
      const s = styleOf(n.parentElement), text = visibleText(n, s);
      const range = document.createRange(); range.selectNodeContents(n);
      if (text.trim() && visibleRect(n.parentElement, rect(range.getBoundingClientRect()))) output.push(n);
    }
    return output;
  };
  const textRects = nodes => nodes.flatMap(n => {
    const range = document.createRange(); range.selectNodeContents(n);
    return Array.from(range.getClientRects()).map(rect).map(r => visibleRect(n.parentElement, r)).filter(Boolean);
  });
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
  const platformFonts = (el, text, id, options) => {
    if (!text) return { fonts: [], evidence: null };
    const measured = meta.reference_environment?.fonts;
    let owners = [], attribution = [];
    if (options.pseudo) owners = [options.axBackend];
    else if (el.matches('input,textarea,select')) {
      owners = snapshotInputFontOwners.get(el) || [];
      if (!owners.length) {
        const supplement = meta.input_text_boxes?.[String(snapshotBackend.get(el))];
        owners = (supplement?.text_nodes || []).filter(n => n.boxes?.length && n.text?.trim()).map(n => n.font_owner_backend_node_id);
      }
    }
    else {
      const textNodes = options.ownedTextNodes || (options.textNode ? [options.textNode] : []);
      const hosts = Array.from(new Set(textNodes.map(n => n.parentElement)));
      owners = hosts.map(host => snapshotBackend.get(host));
      for (const host of hosts) {
        const other = Array.from(host.childNodes).filter(n => n.nodeType === Node.TEXT_NODE && visibleText(n, styleOf(host)).trim() && !textNodes.includes(n));
        if (other.length) attribution.push({ owner_backend_node_id: snapshotBackend.get(host), other_text_nodes: other.map(n => n.nodeValue),
          reason: 'CDP reports the combined fonts of direct text children; their glyph counts cannot be attributed to this one text element.' });
      }
    }
    owners = Array.from(new Set(owners));
    const records = owners.map(backend => ({ backend_node_id: backend ?? null, fonts: measured?.by_backend_node?.[String(backend)] ?? null,
      errors: (measured?.errors || []).filter(error => error.backend_node_id === backend) }));
    // A host with a single actual font identifies every one of its text runs,
    // even when its glyph count is aggregated. Mixed actual fonts require a
    // run-level measurement before they can be assigned to separate elements.
    const ambiguous = attribution.filter(item => {
      const record = records.find(record => record.backend_node_id === item.owner_backend_node_id);
      return new Set((record?.fonts || []).map(font => JSON.stringify([font.familyName, font.postScriptName]))).size > 1;
    });
    const evidence = { source: measured?.source || null, owners: records, attribution, glyph_count_scope: 'actual-font-hosts', ambiguous_font_hosts: ambiguous };
    if (measured?.source !== 'CDP.CSS.getPlatformFontsForNode' || !owners.length || owners.some(x => !Number.isInteger(x)) || ambiguous.length ||
        records.some(record => record.errors.length || !Array.isArray(record.fonts) || !record.fonts.length || record.fonts.some(font =>
          typeof font.familyName !== 'string' || typeof font.postScriptName !== 'string' || !Number.isFinite(font.glyphCount) || font.glyphCount <= 0))) {
      unmeasured.push({ element: id, property: 'style.rendered_fonts', reason: 'No unambiguous actual platform-font measurement for every visible text host.', evidence });
      return { fonts: null, evidence };
    }
    const combined = new Map();
    for (const record of records) for (const font of record.fonts) {
      const key = JSON.stringify([font.familyName, font.postScriptName]);
      const item = combined.get(key) || { family_name: font.familyName, postscript_name: font.postScriptName, glyph_count: 0 };
      item.glyph_count += font.glyphCount; combined.set(key, item);
    }
    return { fonts: Array.from(combined.values()).sort((a, b) => a.family_name.localeCompare(b.family_name) || a.postscript_name.localeCompare(b.postscript_name)), evidence };
  };
  const kindOf = (el, s) => {
    const tag = el.localName, role = el.getAttribute('role');
    if (el === document.body || el.matches('#appbar,.side,.chat,#composer,#panel,.scrim,.settings,.dialog,.details,.menu')) return 'region';
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
    const background = color(s.backgroundColor, pathOf(el));
    const border = ['Top', 'Right', 'Bottom', 'Left'].some(side => number(s['border' + side + 'Width']) > 0 && !['none', 'hidden'].includes(s['border' + side + 'Style']));
    if ((background?.[3] > 0 || border || s.boxShadow !== 'none' || s.backgroundImage !== 'none') && tag !== 'html') return el.getBoundingClientRect().width <= 2 || el.getBoundingClientRect().height <= 2 ? 'divider' : 'card';
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
  const shadowData = (el, value) => {
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
        spread_radius: lengths[3] || 0, color: color(tint[0], pathOf(el)) });
    }
    return shadows;
  };
  const backgroundData = (el, s, measuredBox = null) => {
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
        previous = position; stops.push({ position, color: color(match[1], pathOf(el)) });
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
        screen_ctm: matrixValue(shape.getScreenCTM()), effective_width: null, coordinate_space: 'viewport-css-pixels' };
      records.push(record);
      if (s.stroke === 'none' || color(s.stroke, pathOf(shape))?.[3] === 0 || Number(s.strokeOpacity) === 0) { record.effective_width = 0; continue; }
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
      record.effective_width = record.source_width * Math.sqrt(xSquared);
    }
    const painted = records.filter(record => record.effective_width !== 0);
    const widths = Array.from(new Set(painted.map(record => record.effective_width)));
    const width = records.some(record => record.problem) || widths.length > 1 ? null : widths[0] ?? 0;
    const result = { width, source: 'getComputedStyle + SVGGraphicsElement.getScreenCTM/getCTM', shapes: records };
    svgStrokes.set(el, result);
    if (width === null) unmeasured.push({ element: nodeIds.get(el), property: 'style.stroke_width', evidence: result,
      reason: 'Actual SVG strokes do not have one measurable content-window width; no source-space width is substituted.' });
    return result;
  };
  const styleData = (el, s, text, pseudo = null, measuredBox = null) => {
    const sides = ['Top', 'Right', 'Bottom', 'Left'];
    const widths = sides.map(side => number(s['border' + side + 'Width']) || 0);
    const radii = ['TopLeft', 'TopRight', 'BottomRight', 'BottomLeft'].map(corner => radius(s['border' + corner + 'Radius'], el, measuredBox));
    const foreground = el instanceof SVGElement ? (s.stroke !== 'none' ? s.stroke : s.fill !== 'none' ? s.fill : s.color) : s.color;
    return { font_size: text ? number(s.fontSize) : null, font_weight: text ? (s.fontWeight === 'normal' ? 400 : s.fontWeight === 'bold' ? 700 : number(s.fontWeight)) : null,
      foreground: color(foreground, pathOf(el)), background: color(s.backgroundColor, pathOf(el)),
      border_color: Math.max(...widths) ? color(s['border' + sides[widths.indexOf(Math.max(...widths))] + 'Color'], pathOf(el)) : [0, 0, 0, 0],
      border_width: Math.max(...widths), corner_radius: Math.max(...radii),
      font_family: text ? s.fontFamily : null, border_widths: widths, corner_radii: radii,
      border_colors: sides.map((side, i) => widths[i] > 0 ? color(s['border' + side + 'Color'], pathOf(el)) : [0, 0, 0, 0]),
      opacity: cumulativeOpacity(el) * (pseudo ? Number(s.opacity) : 1), shadow: shadowData(el, s.boxShadow), background_image: backgroundData(el, s, measuredBox),
      text_align: s.textAlign, letter_spacing: s.letterSpacing, line_height: s.lineHeight,
      stroke_width: svgStrokeData(el)?.width ?? null,
      pseudo };
  };
  const stateOf = el => {
    const role = el.getAttribute('role'), checkable = el.matches('input[type=checkbox],input[type=radio],[role=switch],[role=checkbox],[role=radio]');
    const expandable = el.localName === 'summary' || el.hasAttribute('aria-expanded') || el.matches('.org-row,.frow.dir');
    const selectable = el.matches('.tabs>button,.seg>button,.settings nav>button,.org-row,.chat-row,.item-row,.session-row,.who-pick .who,[role=tab],[aria-selected]');
    const interactive = el.matches('button,input,textarea,select,summary,a[href],[tabindex],[role=button],[role=tab],[role=menuitem]');
    return { enabled: interactive ? !el.matches(':disabled,[aria-disabled=true]') : null,
      selected: selectable ? el.getAttribute('aria-selected') === 'true' || el.classList.contains('on') : null,
      checked: checkable ? !!el.checked || el.getAttribute('aria-checked') === 'true' : null,
      expanded: expandable ? el.localName === 'summary' ? !!el.parentElement.open : el.getAttribute('aria-expanded') === 'true' || el.classList.contains('open') : null,
      focused: interactive ? el === document.activeElement : null, hovered: el.matches(':hover'),
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
  const emit = (el, kind, text, bounds, parent, suffix = '', options = {}) => {
    const region = regionOf(el), id = nodeIds.get(el) + suffix;
    const s = options.style || styleOf(el), boxes = options.textBoxes || [];
    const paintStyle = styleData(el, options.pseudo ? s : styleOf(el), text, options.pseudo || null, options.unclippedBounds);
    const textStyle = styleData(el, s, text, options.pseudo || null, options.unclippedBounds);
    for (const field of ['font_size', 'font_weight', 'font_family', 'foreground', 'letter_spacing', 'line_height', 'text_align']) paintStyle[field] = textStyle[field];
    if (!text && !['icon', 'chart-edge'].includes(kind)) paintStyle.foreground = null;
    if (kind === 'icon' && el.localName === 'svg' && el.querySelector('path,circle,ellipse,line,polyline,polygon,rect')) {
      const shapeStyle = styleOf(el.querySelector('path,circle,ellipse,line,polyline,polygon,rect'));
      paintStyle.foreground = color(shapeStyle.stroke !== 'none' ? shapeStyle.stroke : shapeStyle.fill, pathOf(el));
    }
    if (kind === 'text' && !options.pseudo) {
      paintStyle.background = [0, 0, 0, 0]; paintStyle.border_color = [0, 0, 0, 0]; paintStyle.border_width = 0; paintStyle.corner_radius = 0;
      paintStyle.border_widths = [0, 0, 0, 0]; paintStyle.corner_radii = [0, 0, 0, 0]; paintStyle.border_colors = Array.from({ length: 4 }, () => [0, 0, 0, 0]);
      paintStyle.shadow = []; paintStyle.background_image = 'none';
    }
    if (!text && !['icon', 'chart-edge'].includes(kind)) paintStyle.foreground = null;
    const accessibility = accessibilityOf(options.textNode || el, options.axBackend);
    const actualFonts = platformFonts(el, text, id, options);
    paintStyle.rendered_fonts = actualFonts.fonts;
    const item = { id, parent, region, order: regionOrders.get(region) || 0, kind, text,
      name: accessibility.name, bounds: options.unclippedBounds || rect(el.getBoundingClientRect()), visible_bounds: bounds, style: paintStyle,
      state: stateOf(el), layout: { wrap: !text ? null : ['pre', 'nowrap'].includes(s.whiteSpace) ? 'none' : s.overflowWrap === 'anywhere' || s.wordBreak === 'break-all' ? 'character' : 'word',
        truncation: !text ? null : s.textOverflow === 'ellipsis' || s.webkitLineClamp !== 'none' && Number(s.webkitLineClamp) > 0 ? 'ellipsis' : /hidden|clip/.test(s.overflowX) && el.scrollWidth > el.clientWidth ? 'clip' : 'none', line_count: !text ? null : boxes.length ? lineCount(boxes) : null },
      icon: iconOf(el, kind), evidence: { source: 'dom', selector: pathOf(el), tag: el.localName,
        class: el.getAttribute('class') || '', raw_node: nodeIds.get(el), unclipped_bounds: rect(el.getBoundingClientRect()), text_bounds: boxes,
        placeholder: el.getAttribute('placeholder'), value: 'value' in el ? el.value : null, accessibility, platform_fonts: actualFonts.evidence, svg_strokes: svgStrokeData(el),
        occlusion_masks: occlusionMasks.get(el) || [], css_paint: { font_family: s.fontFamily, own_opacity: s.opacity, box_shadow: s.boxShadow, background_image: s.backgroundImage,
          background_size: s.backgroundSize, background_position: s.backgroundPosition, background_repeat: s.backgroundRepeat, background_origin: s.backgroundOrigin, background_clip: s.backgroundClip }, ...options.evidence } };
    regionOrders.set(region, item.order + 1);
    elements.push(item);
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
    return cumulativeOpacity(el) === 1 && color(s.backgroundColor, pathOf(el))?.[3] === 255 && visibleRect(el, rect(el.getBoundingClientRect()));
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
    if (s.stroke === 'none' || color(s.stroke, pathOf(el))?.[3] === 0 || Number(s.strokeOpacity) === 0) return layout;
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
      accessibility: accessibilityOf(el),
      text_nodes: Array.from(el.childNodes).filter(n => n.nodeType === Node.TEXT_NODE).map((n, i) => ({ id: id + ':raw-text-' + i, text: n.nodeValue, owned_by: suppressedText.has(n) ? 'ancestor control' : null })) };
    raw_nodes.push(raw);
    if (!bounds || !fragments.length || el.closest('script,style,option')) { raw.projection_reason = !bounds ? 'hidden-or-fully-clipped' : !fragments.length ? 'fully-occluded' : 'nonrendered-content'; continue; }
    if (s.clipPath !== 'none' || s.maskImage !== 'none') unmeasured.push({ element: id, property: 'visibility.shape_clip', reason: 'Nonrectangular CSS clip/mask requires pixel-mask visibility evidence.', clip_path: s.clipPath, mask_image: s.maskImage });
    if (el instanceof SVGElement && el.localName !== 'svg' && !el.matches('.oc-lines .edge,.oc-lines .link')) { raw.projection_reason = 'vector-owned-by-svg-icon'; continue; }
    let parent = null;
    for (let p = el.parentElement; p && !parent; p = p.parentElement) parent = emittedIds.get(p) || null;
    const kind = kindOf(el, s), own = kind ? ownedText(el, kind) : null;
    if (kind) {
      const text = own?.text || '';
      const inputMeasurement = kind === 'input' || kind === 'dropdown' ? inputTextMeasurement(el) : null;
      const emitted = emit(el, kind, text, bounds, parent, '', { style: own?.style || s, ownedTextNodes: own?.nodes || [], textBoxes: own ? own.nodes.length ? textRects(own.nodes) : inputMeasurement?.boxes || [] : [], evidence: { visible_fragments: fragments, text_ownership: own?.nodes.map(n => ({ parent: nodeIds.get(n.parentElement), text: n.nodeValue })) || [], input_text_measurement: inputMeasurement?.evidence || null } });
      raw.emitted.push(emitted); parent = emitted;
      if (own) own.nodes.forEach(n => { suppressedText.add(n); for (const t of raw.text_nodes) if (t.text === n.nodeValue) t.owned_by = emitted; });
      if (el.localName === 'canvas') extraction_errors.push({ type: 'canvas_semantics_unavailable', node: id, reason: 'Canvas pixels are captured but internal element identities require a separate instrumentation contract.' });
    }
    const childText = Array.from(el.childNodes).filter(n => n.nodeType === Node.TEXT_NODE);
    for (let i = 0; i < childText.length; i++) {
      const n = childText[i], text = visibleText(n, s);
      if (!text.trim() || suppressedText.has(n)) continue;
      if (!snapshotRenderedText.has(n)) unmeasured.push({ element: id + ':text-' + i, property: 'text.rendered_whitespace', reason: 'No CDP LayoutText string; raw text is preserved without whitespace substitutions.' });
      const range = document.createRange(); range.selectNodeContents(n);
      const textBounds = visibleRect(el, rect(range.getBoundingClientRect()));
      if (!textBounds) continue;
      const visible = fragmentsOf(el, textBounds);
      if (!visible.length) continue;
      const emitted = emit(el, 'text', text, textBounds, parent, ':text-' + i, { textNode: n, unclippedBounds: rect(range.getBoundingClientRect()), textBoxes: textRects([n]), evidence: { source_text: n.nodeValue, visible_fragments: visible } });
      raw.emitted.push(emitted);
    }
    for (const pseudo of ['::before', '::after', '::marker']) {
      const ps = getComputedStyle(el, pseudo), content = ps.content;
      const snapshotPseudoElement = (pseudoByOwner.get(el) || []).find(x => x.type === pseudo);
      if (ps.display === 'none' || ps.visibility !== 'visible' || Number(ps.opacity) === 0 || !snapshotPseudoElement && (!content || content === 'none' || content === 'normal')) continue;
      raw.pseudo_elements ??= [];
      const pseudoRecord = { pseudo, content, style: styleData(el, ps, content !== '""', pseudo, snapshotPseudoElement?.bounds),
        snapshot_node: snapshotPseudoElement?.index ?? null, bounds: snapshotPseudoElement?.bounds ?? null };
      raw.pseudo_elements.push(pseudoRecord);
      if (!snapshotPseudoElement) {
        extraction_errors.push({ type: 'pseudo_geometry_unavailable', node: id, selector: pathOf(el), pseudo, content, reason: 'No matching CDP DOMSnapshot layout; estimated rectangles are not parity evidence.' });
        continue;
      }
      const p = snapshotPseudoElement, vb = visibleRect(el, p.bounds);
      const pseudoFragments = vb ? fragmentsOf(el, vb) : [];
      pseudoRecord.visible_bounds = vb; pseudoRecord.visible_fragments = pseudoFragments;
      if (!vb || !pseudoFragments.length) { pseudoRecord.projection_reason = !vb ? 'hidden-or-fully-clipped' : 'fully-occluded'; continue; }
      const pkind = p.text ? pseudo === '::marker' ? 'icon' : 'text' : 'card';
      const emitted = emit(el, pkind, p.text, vb, parent, pseudo, { style: ps, pseudo, textBoxes: p.text_boxes, unclippedBounds: p.bounds, axBackend: p.backend_node_id,
        evidence: { source: 'CDP.DOMSnapshot', snapshot_node: p.index, snapshot_layout: p.layout_index, backend_node_id: p.backend_node_id, paint_order: p.paint_order } });
      if (pkind === 'icon') elements[elements.length - 1].icon = { source: 'text-glyph', glyph: p.text };
      pseudoRecord.projection_reason = 'paint-or-text'; pseudoRecord.emitted = emitted;
      raw.emitted.push(emitted);
    }
    raw.projection_reason = raw.emitted.length ? 'paint-or-semantic-or-text' : 'layout-only-wrapper-or-owned-label';
  }
  return { schema_version: 1, scene_id: meta.scene_id, client: 'reference', viewport,
    lang: meta.lang || document.documentElement.lang, theme: meta.theme || document.documentElement.dataset.theme, reference_environment: meta.reference_environment || null,
    capture: { source: 'production-dom', coordinate_space: 'viewport-css-pixels', device_scale_factor: devicePixelRatio,
      text_policy: 'Uniform simple control labels are owned by the control; rich labels are independent text nodes.',
      visibility_policy: 'Viewport/ancestor clips, SVG stroke visibility, actual paint order, and analytic rounded-rectangle subtraction masks. visible_fragments are rectangular envelopes; occlusion_masks retain exact curved clipping. Unresolved compound masks remain failures.' },
    elements, raw_nodes, raw_ax_nodes, extraction_errors, coverage: { raw_nodes: raw_nodes.length, emitted_elements: elements.length, unmeasured },
    summary: { dom_nodes: raw_nodes.length, elements: elements.length, extraction_errors: extraction_errors.length } };
}
