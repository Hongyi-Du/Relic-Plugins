// Read-only extraction of the rendered production DOM. No reference fixture or
// native element data is used to manufacture counterpart elements.
(meta) => {
  'use strict';
  const elements = [], raw_nodes = [], extraction_errors = [], unmeasured = [];
  for (const error of meta.input_text_errors || []) extraction_errors.push({ type: 'input_text_capture_error', detail: error });
  const viewport = { width: innerWidth, height: innerHeight, scale: devicePixelRatio };
  const nodeIds = new WeakMap(), emittedIds = new WeakMap(), styles = new WeakMap();
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
  const radius = (value, el) => {
    const parts = value.split(/\s+/), b = el.getBoundingClientRect();
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
  const snapshotInputBoxes = new WeakMap(), snapshotBackend = new WeakMap(), snapshotRenderedText = new WeakMap();
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
  const styleData = (el, s, text, pseudo = null) => {
    const sides = ['Top', 'Right', 'Bottom', 'Left'];
    const widths = sides.map(side => number(s['border' + side + 'Width']) || 0);
    const radii = ['TopLeft', 'TopRight', 'BottomRight', 'BottomLeft'].map(corner => radius(s['border' + corner + 'Radius'], el));
    const foreground = el instanceof SVGElement ? (s.stroke !== 'none' ? s.stroke : s.fill !== 'none' ? s.fill : s.color) : s.color;
    return { font_size: text ? number(s.fontSize) : null, font_weight: text ? (s.fontWeight === 'normal' ? 400 : s.fontWeight === 'bold' ? 700 : number(s.fontWeight)) : null,
      foreground: color(foreground, pathOf(el)), background: color(s.backgroundColor, pathOf(el)),
      border_color: Math.max(...widths) ? color(s['border' + sides[widths.indexOf(Math.max(...widths))] + 'Color'], pathOf(el)) : [0, 0, 0, 0],
      border_width: Math.max(...widths), corner_radius: Math.max(...radii),
      font_family: text ? s.fontFamily : null, border_widths: widths, corner_radii: radii,
      border_colors: sides.map(side => color(s['border' + side + 'Color'], pathOf(el))),
      opacity: number(s.opacity), shadow: s.boxShadow, background_image: s.backgroundImage,
      text_align: s.textAlign, letter_spacing: s.letterSpacing, line_height: s.lineHeight,
      stroke_width: el instanceof SVGElement ? number(s.strokeWidth) : null,
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
      const shape = n => ({ tag: n.localName, attributes: Object.fromEntries(Array.from(n.attributes).filter(a => ['viewBox', 'd', 'points', 'x', 'y', 'x1', 'x2', 'y1', 'y2', 'cx', 'cy', 'r', 'rx', 'ry', 'width', 'height', 'transform', 'fill-rule'].includes(a.name)).sort((a, b) => a.name.localeCompare(b.name)).map(a => [a.name, a.value])), children: Array.from(n.children).map(shape) });
      return { source: 'svg', glyph: JSON.stringify(shape(el)) };
    }
    if (kind === 'image' && el.localName === 'img') return { source: 'image', glyph: el.currentSrc || el.src };
    return null;
  };
  const emit = (el, kind, text, bounds, parent, suffix = '', options = {}) => {
    const region = regionOf(el), id = nodeIds.get(el) + suffix;
    const s = options.style || styleOf(el), boxes = options.textBoxes || [];
    const paintStyle = styleData(el, options.pseudo ? s : styleOf(el), text, options.pseudo || null);
    const textStyle = styleData(el, s, text, options.pseudo || null);
    for (const field of ['font_size', 'font_weight', 'font_family', 'foreground', 'letter_spacing', 'line_height', 'text_align']) paintStyle[field] = textStyle[field];
    if (!text && !['icon', 'chart-edge'].includes(kind)) paintStyle.foreground = null;
    if (kind === 'icon' && el.localName === 'svg' && el.firstElementChild) {
      const shapeStyle = styleOf(el.firstElementChild);
      paintStyle.foreground = color(shapeStyle.stroke !== 'none' ? shapeStyle.stroke : shapeStyle.fill, pathOf(el));
      paintStyle.stroke_width = number(shapeStyle.strokeWidth);
    }
    if (kind === 'text' && !options.pseudo) {
      paintStyle.background = [0, 0, 0, 0]; paintStyle.border_color = [0, 0, 0, 0]; paintStyle.border_width = 0; paintStyle.corner_radius = 0;
      paintStyle.border_widths = [0, 0, 0, 0]; paintStyle.corner_radii = [0, 0, 0, 0]; paintStyle.border_colors = Array.from({ length: 4 }, () => [0, 0, 0, 0]);
      paintStyle.shadow = 'none'; paintStyle.background_image = 'none';
    }
    if (!text && !['icon', 'chart-edge'].includes(kind)) paintStyle.foreground = null;
    const accessibility = accessibilityOf(options.textNode || el, options.axBackend);
    const item = { id, parent, region, order: regionOrders.get(region) || 0, kind, text,
      name: accessibility.name, bounds: options.unclippedBounds || rect(el.getBoundingClientRect()), visible_bounds: bounds, style: paintStyle,
      state: stateOf(el), layout: { wrap: !text ? null : ['pre', 'nowrap'].includes(s.whiteSpace) ? 'none' : s.overflowWrap === 'anywhere' || s.wordBreak === 'break-all' ? 'character' : 'word',
        truncation: !text ? null : s.textOverflow === 'ellipsis' || s.webkitLineClamp !== 'none' && Number(s.webkitLineClamp) > 0 ? 'ellipsis' : /hidden|clip/.test(s.overflowX) && el.scrollWidth > el.clientWidth ? 'clip' : 'none', line_count: !text ? null : boxes.length ? lineCount(boxes) : null },
      icon: iconOf(el, kind), evidence: { source: 'dom', selector: pathOf(el), tag: el.localName,
        class: el.getAttribute('class') || '', raw_node: nodeIds.get(el), unclipped_bounds: rect(el.getBoundingClientRect()), text_bounds: boxes,
        placeholder: el.getAttribute('placeholder'), value: 'value' in el ? el.value : null, accessibility, ...options.evidence } };
    regionOrders.set(region, item.order + 1);
    elements.push(item);
    if (text && !boxes.length) unmeasured.push({ element: id, property: 'layout.line_count', reason: 'No measured text-line rectangles were available.' });
    if (!accessibility.measured && !options.pseudo && ['button', 'icon-button', 'input', 'toggle', 'checkbox', 'tab', 'menu-item', 'dropdown', 'link', 'text'].includes(kind)) unmeasured.push({ element: id, property: 'accessibility.name_role', reason: 'No actual AX node was linked to this visible semantic element; empty names are not guessed.' });
    if (!suffix) emittedIds.set(el, id);
    return id;
  };
  const opaqueOverlays = Array.from(document.querySelectorAll('.dialog,.settings,.details,.card,.menu')).filter(el => {
    const s = styleOf(el);
    return Number(s.opacity) === 1 && color(s.backgroundColor, pathOf(el))?.[3] === 255 && visibleRect(el, rect(el.getBoundingClientRect()));
  });
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
    for (const cover of opaqueOverlays) {
      if (cover === el || cover.contains(el) || el.contains(cover)) continue;
      const c = cover.getBoundingClientRect(), s = styleOf(cover), coverRadius = Math.max(...['TopLeft', 'TopRight', 'BottomRight', 'BottomLeft'].map(k => radius(s['border' + k + 'Radius'], cover)));
      // Only subtract the definitely opaque rectangular interior. Rounded
      // corners remain visible fragments rather than deleting visible content.
      const center = { x: c.x + coverRadius, y: c.y, width: Math.max(0, c.width - coverRadius * 2), height: c.height };
      const middle = { x: c.x, y: c.y + coverRadius, width: c.width, height: Math.max(0, c.height - coverRadius * 2) };
      const intersection = intersect(bounds, rect(c));
      if (!nonempty(intersection)) continue;
      const p = { x: Math.min(innerWidth - .5, Math.max(.5, intersection.x + intersection.width / 2)), y: Math.min(innerHeight - .5, Math.max(.5, intersection.y + intersection.height / 2)) };
      const stack = document.elementsFromPoint(p.x, p.y), ci = stack.findIndex(x => x === cover || cover.contains(x)), ei = stack.findIndex(x => x === el || el.contains(x));
      if (ci >= 0 && (ei < 0 || ci < ei)) {
        parts = parts.flatMap(x => subtract(x, center)).flatMap(x => subtract(x, middle));
        const corners = [{ x: c.x, y: c.y }, { x: c.right - coverRadius, y: c.y }, { x: c.x, y: c.bottom - coverRadius }, { x: c.right - coverRadius, y: c.bottom - coverRadius }];
        if (coverRadius && parts.some(part => corners.some(corner => nonempty(intersect(part, { ...corner, width: coverRadius, height: coverRadius }))))) {
          const gap = { element: nodeIds.get(el), property: 'visibility.rounded_corner_occlusion', covering: pathOf(cover), reason: 'The opaque interior is measured; a partially covered rounded-corner fragment needs an exact paint mask.' };
          if (!unmeasured.some(x => x.element === gap.element && x.property === gap.property && x.covering === gap.covering)) unmeasured.push(gap);
        }
      }
    }
    return parts;
  };
  const all = Array.from(document.body.querySelectorAll('*'));
  all.unshift(document.body);
  all.forEach((el, index) => nodeIds.set(el, 'dom-' + index));
  const suppressedText = new WeakSet();
  for (const el of all) {
    const id = nodeIds.get(el), s = styleOf(el), unclipped = rect(el.getBoundingClientRect());
    const bounds = visibleRect(el, unclipped), fragments = bounds ? fragmentsOf(el, bounds) : [];
    const raw = { id, parent: nodeIds.get(el.parentElement) || null, selector: pathOf(el), tag: el.localName,
      attributes: Object.fromEntries(Array.from(el.attributes).map(a => [a.name, a.value])), bounds: unclipped,
      visible_bounds: bounds, visible_fragments: fragments, display: s.display, visibility: s.visibility, opacity: s.opacity, emitted: [],
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
      const emitted = emit(el, kind, text, bounds, parent, '', { style: own?.style || s, textBoxes: own ? own.nodes.length ? textRects(own.nodes) : inputMeasurement?.boxes || [] : [], evidence: { visible_fragments: fragments, text_ownership: own?.nodes.map(n => ({ parent: nodeIds.get(n.parentElement), text: n.nodeValue })) || [], input_text_measurement: inputMeasurement?.evidence || null } });
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
      raw.pseudo_elements.push({ pseudo, content, style: styleData(el, ps, content !== '""', pseudo) });
      if (!snapshotPseudoElement) {
        extraction_errors.push({ type: 'pseudo_geometry_unavailable', node: id, selector: pathOf(el), pseudo, content, reason: 'No matching CDP DOMSnapshot layout; estimated rectangles are not parity evidence.' });
        continue;
      }
      const p = snapshotPseudoElement, vb = visibleRect(el, p.bounds);
      if (!vb || !fragmentsOf(el, vb).length) continue;
      const pkind = p.text ? pseudo === '::marker' ? 'icon' : 'text' : 'card';
      const emitted = emit(el, pkind, p.text, vb, parent, pseudo, { style: ps, pseudo, textBoxes: p.text_boxes, unclippedBounds: p.bounds, axBackend: p.backend_node_id,
        evidence: { source: 'CDP.DOMSnapshot', snapshot_node: p.index, snapshot_layout: p.layout_index, backend_node_id: p.backend_node_id, paint_order: p.paint_order } });
      if (pkind === 'icon') elements[elements.length - 1].icon = { source: 'text-glyph', glyph: p.text };
      raw.emitted.push(emitted);
    }
    raw.projection_reason = raw.emitted.length ? 'paint-or-semantic-or-text' : 'layout-only-wrapper-or-owned-label';
  }
  return { schema_version: 1, scene_id: meta.scene_id, client: 'reference', viewport,
    lang: meta.lang || document.documentElement.lang, theme: meta.theme || document.documentElement.dataset.theme,
    capture: { source: 'production-dom', coordinate_space: 'viewport-css-pixels', device_scale_factor: devicePixelRatio,
      text_policy: 'Uniform simple control labels are owned by the control; rich labels are independent text nodes.',
      visibility_policy: 'Viewport and ancestor clipping; subtract only proven opaque overlay interiors. Preserve raw nodes and partial fragments for audit.' },
    elements, raw_nodes, raw_ax_nodes, extraction_errors, coverage: { raw_nodes: raw_nodes.length, emitted_elements: elements.length, unmeasured },
    summary: { dom_nodes: raw_nodes.length, elements: elements.length, extraction_errors: extraction_errors.length } };
}
