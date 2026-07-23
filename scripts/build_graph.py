#!/usr/bin/env python3
"""Phase 3 — Component Graph generator for the Noise Audio DLS repo.

Reads ONLY registry.yaml and generates, in one pass:

  graph/graph.json        the canonical, queryable graph (nodes + typed directional
                          edges) for agent traversal — every node carries id,
                          node_id and figma_fingerprint so results map back to the
                          exact repo file and Figma component.
  dashboard/graph.html    the interactive visualization. The page embeds the SAME
                          JSON and renders from it client-side, so the picture can
                          never diverge from the data.

It renders only nodes and edges that exist in the registry. Edges the registry
flags as dangling (resolved: false, excluded: false) are drawn as red broken
edges to ghost markers — shown, never dropped or repaired. Layout is a live
force simulation (Obsidian-style): atoms seed near the center, molecules and
organisms grow outward in concentric bands, node position settles from
repulsion + structural/behavioral spring edges + a gentle per-band radial
pull. Nodes are draggable; the canvas pans and zooms. The underlying wiring
(nodes, edges, ids) is exactly the registry — only the layout is simulated.

Usage:  python3 scripts/build_graph.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_dashboard as dash  # reuse repo loading + page shell (reads registry.yaml)

ROOT = dash.ROOT
registry = dash.registry

TIER = {"atom": "atoms", "molecule": "molecules", "organism": "organisms", "complex-organism": "organisms"}

def build_graph_data():
    nodes, edges = [], []
    for c in registry["components"]:
        nodes.append({
            "id": c["id"],
            "name": dash.components[c["id"]]["name"].strip(),
            "type": c["type"],
            "tier": TIER[c["type"]],
            "node_id": c["node_id"],
            "figma_fingerprint": c["figma_fingerprint"],
            "usage_count": c.get("usage_count", 0),
            "file": c["file"],
            "dashboard": f"components/{c['id']}.html",
        })
    for c in registry["components"]:
        for part in (c.get("structural_edges", {}) or {}).get("uses", []) or []:
            edges.append({"type": "structural", "source": part, "target": c["id"],
                          "meaning": f"{c['id']} is built from {part}"})
        for e in c.get("behavioral_edges", []) or []:
            edges.append({"type": "behavioral", "source": c["id"], "target": e["target"],
                          "relation": e["relation"]})
        for e in c.get("figma_instance_edges", []) or []:
            if not e.get("resolved") and not e.get("excluded"):
                edges.append({
                    "type": "dangling", "source": c["id"],
                    "ref_name": e["references"], "ref_node_id": e["ref_node_id"],
                    "external_location": e.get("external_location"),
                    "same_named_library_component": e.get("same_named_library_component"),
                    "status": e.get("status"),
                })
    return {
        "app": registry["app"],
        "generated_from": "registry.yaml",
        "generated": registry["generated"],
        "source": registry["source"],
        "traversal": {
            "top_down": "Start at nodes with tier=organisms. A component C's parts are the sources of "
                        "structural edges whose target == C. Recurse into molecules, then atoms.",
            "lateral": "Behavioral edges are directional as declared in the authored metadata "
                       "(source declares the relation toward target).",
            "upward": "A component C's consumers ('used by') are the targets of structural edges whose source == C.",
            "identity": "Every node exposes id (repo file components/<tier>/<id>.yaml), node_id (Figma "
                        "in-file locator) and figma_fingerprint (stable component key).",
            "dangling": "Edges with type=dangling are broken references flagged by the registry: the "
                        "component's Figma instance points outside the ingested library page. They are "
                        "rendered as broken, never repaired.",
        },
        "legend": {"node_color": "component type", "node_size": "usage count",
                   "solid_edge": "structural — is built from (drawn part → whole)",
                   "dashed_edge": "behavioral relationship",
                   "red_edge": "dangling reference flagged in the registry"},
        "counts": registry["counts"],
        "nodes": nodes,
        "edges": edges,
    }

GRAPH_JS = r"""
(function () {
  var data = JSON.parse(document.getElementById('graph-data').textContent);
  var svgNS = 'http://www.w3.org/2000/svg';
  var mount = document.getElementById('graph-mount');
  // when this page is bundled into the single-file dashboard, route via hashes
  var bundled = !!document.querySelector('[data-page]');
  var link = function (n) { return bundled ? '#/components/' + n.id : n.dashboard; };
  var goTo = function (n) { if (bundled) { location.hash = link(n); } else { location.href = link(n); } };

  var TYPE_COLOR = { atom: '#1c7a45', molecule: '#9c6a1f', organism: '#b3261e', 'complex-organism': '#6b1414' };
  // concentric bands, atoms innermost growing out to molecules then organisms — like Obsidian's
  // force graph, but biased into layers so the taxonomy stays legible at a glance.
  var BAND = { atoms: [0, 165], molecules: [165, 280], organisms: [280, 410] };
  var W = 1400, H = 900, CX = W / 2, CY = H / 2;

  var radius = function (n) { return 8 + 2.6 * Math.min(n.usage_count, 8); };

  // ---------------------------------------------------------------- seed node positions
  var byTier = { atoms: [], molecules: [], organisms: [] };
  data.nodes.forEach(function (n) { byTier[n.tier].push(n); });
  var nodes = [], nodeById = {};
  function seed(list, band) {
    var n = list.length;
    list.forEach(function (src, i) {
      var a = (i / Math.max(n, 1)) * Math.PI * 2 + Math.random() * 0.4;
      var r = (band[0] + band[1]) / 2 + (Math.random() - 0.5) * (band[1] - band[0]) * 0.6;
      var node = {
        id: src.id, name: src.name, type: src.type, tier: src.tier,
        node_id: src.node_id, figma_fingerprint: src.figma_fingerprint,
        usage_count: src.usage_count, file: src.file, dashboard: src.dashboard,
        x: CX + Math.cos(a) * r, y: CY + Math.sin(a) * r, vx: 0, vy: 0,
        band: band, r: radius(src), ghost: false,
      };
      nodes.push(node); nodeById[node.id] = node;
    });
  }
  seed(byTier.atoms, BAND.atoms);
  seed(byTier.molecules, BAND.molecules);
  seed(byTier.organisms, BAND.organisms);

  // ghost nodes: dangling references, deduped by ref_node_id (registry data, not invented).
  // Placed on their own outer ring, static (no physics) — broken, shown, never repaired.
  var ghosts = {}, ghostOrder = [];
  data.edges.forEach(function (e) {
    if (e.type !== 'dangling') return;
    if (!ghosts[e.ref_node_id]) { ghosts[e.ref_node_id] = e; ghostOrder.push(e.ref_node_id); }
  });
  var GR = 470;
  ghostOrder.forEach(function (gid, i) {
    var e = ghosts[gid];
    var a = (i / Math.max(ghostOrder.length, 1)) * Math.PI * 2;
    var node = {
      id: 'ghost:' + gid, name: e.ref_name, type: 'ghost', ghost: true, static: true,
      x: CX + Math.cos(a) * GR, y: CY + Math.sin(a) * GR, vx: 0, vy: 0, r: 5,
      external_location: e.external_location, same_named_library_component: e.same_named_library_component,
    };
    nodes.push(node); nodeById[node.id] = node;
  });

  // ---------------------------------------------------------------- edges + adjacency
  var edges = [], adj = {};
  function addAdj(a, b) { (adj[a] = adj[a] || {})[b] = 1; (adj[b] = adj[b] || {})[a] = 1; }
  data.edges.forEach(function (e) {
    var aId = e.source, bId = e.type === 'dangling' ? 'ghost:' + e.ref_node_id : e.target;
    var a = nodeById[aId], b = nodeById[bId];
    if (!a || !b) return;
    edges.push({
      a: a, b: b, type: e.type,
      title: e.type === 'structural' ? e.meaning
        : e.type === 'behavioral' ? e.source + ' —[' + e.relation + ']→ ' + e.target
        : e.source + ' → ' + e.ref_name + ' (' + (e.external_location || 'outside library') + ') — dangling reference',
    });
    addAdj(aId, bId);
  });
  var IDEAL = { structural: 95, behavioral: 160, dangling: 140 };
  var SPRING = { structural: 0.018, behavioral: 0.01, dangling: 0.008 };

  // ---------------------------------------------------------------- physics (n-body, spring, radial band)
  var REPULSE = 2400, CROSS_TIER_REPULSE = 0.3, DAMPING = 0.82, BAND_PULL = 0.28;
  var live = nodes.filter(function (n) { return !n.static; });
  var dragging = null, panning = false, rafId = null, asleep = false;

  function physicsStep() {
    for (var i = 0; i < live.length; i++) {
      for (var j = i + 1; j < live.length; j++) {
        var A = live[i], B = live[j];
        var dx = B.x - A.x, dy = B.y - A.y, d2 = dx * dx + dy * dy; if (d2 < 4) d2 = 4;
        // repulsion is much weaker across tiers than within one: cross-tier separation is the
        // radial band constraint's job below, not this force's — letting repulsion push evenly
        // across tiers is what drags atoms/organisms into the same radius band.
        var sameTier = A.tier === B.tier;
        var f = (REPULSE * (sameTier ? 1 : CROSS_TIER_REPULSE)) / d2;
        var d = Math.sqrt(d2), fx = dx / d * f, fy = dy / d * f;
        A.vx -= fx; A.vy -= fy; B.vx += fx; B.vy += fy;
      }
    }
    edges.forEach(function (e) {
      var A = e.a, B = e.b;
      if (A.static && B.static) return;
      var dx = B.x - A.x, dy = B.y - A.y, d = Math.sqrt(dx * dx + dy * dy) || 1;
      var k = SPRING[e.type] || 0.01, ideal = IDEAL[e.type] || 110;
      var f = k * (d - ideal), fx = dx / d * f, fy = dy / d * f;
      if (!A.static) { A.vx += fx; A.vy += fy; }
      if (!B.static) { B.vx -= fx; B.vy -= fy; }
    });
    var ke = 0;
    live.forEach(function (n) {
      if (n === dragging) { n.vx = 0; n.vy = 0; return; }
      n.vx *= DAMPING; n.vy *= DAMPING;
      n.x += n.vx; n.y += n.vy;
      // hard radial constraint, applied AFTER integration so it always wins over the spring/
      // repulsion tug-of-war: pull this frame's distance-from-center a fixed fraction toward the
      // tier's band midpoint. Angular position (and so which neighbors cluster together) is left
      // entirely to the forces above — only the ring the node sits on is enforced.
      var dx = n.x - CX, dy = n.y - CY, d = Math.sqrt(dx * dx + dy * dy) || 0.001;
      var mid = (n.band[0] + n.band[1]) / 2;
      var newD = d + (mid - d) * BAND_PULL;
      n.x = CX + dx / d * newD; n.y = CY + dy / d * newD;
      ke += n.vx * n.vx + n.vy * n.vy;
    });
    return ke;
  }

  // ---------------------------------------------------------------- SVG scaffold
  var svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
  svg.setAttribute('class', 'ograph');
  svg.setAttribute('tabindex', '0');
  mount.appendChild(svg);
  function el(tag, attrs, parent) {
    var e = document.createElementNS(svgNS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    (parent || svg).appendChild(e); return e;
  }
  var defs = el('defs', {});
  var arrow = el('marker', { id: 'og-arrow', viewBox: '0 0 8 8', refX: 7, refY: 4, markerWidth: 6, markerHeight: 6, orient: 'auto' }, defs);
  el('path', { d: 'M0,0 L8,4 L0,8 z', fill: '#7a7a7a' }, arrow);

  var viewport = el('g', { id: 'og-viewport' });
  var edgeLayer = el('g', { class: 'og-edges' }, viewport);
  // dots and labels are separate layers, labels drawn LAST, so a label can never be painted
  // over by some other node's circle just because that node happened to be created later —
  // paint order previously followed per-node creation order, not proximity, which cut labels
  // off behind neighboring dots. All labels now sit above all dots, always.
  var dotLayer = el('g', { class: 'og-dots' }, viewport);
  var labelLayer = el('g', { class: 'og-labels' }, viewport);

  var edgeEls = edges.map(function (e) {
    var cls = e.type === 'structural' ? 'og-e-structural' : e.type === 'behavioral' ? 'og-e-behavioral' : 'og-e-dangling';
    var line = el('line', { class: 'og-edge ' + cls }, edgeLayer);
    if (e.type === 'structural') line.setAttribute('marker-end', 'url(#og-arrow)');
    el('title', {}, line).textContent = e.title;
    return { el: line, edge: e };
  });

  var nodeEls = {}, labelEls = [];
  nodes.forEach(function (n) {
    var dg = el('g', { class: 'og-node' + (n.ghost ? ' og-ghost' : ''), 'data-key': n.id }, dotLayer);
    var lg = el('g', { class: 'og-node' + (n.ghost ? ' og-ghost' : ''), 'data-key': n.id }, labelLayer);
    var title;
    if (n.ghost) {
      el('circle', { r: n.r, class: 'og-dot og-dot-ghost' }, dg);
      var lbl = el('text', { class: 'og-label og-label-ghost', x: n.r + 6, y: 4 }, lg);
      lbl.textContent = '✕ ' + n.name;
      title = n.name + ' — ' + (n.external_location || 'outside library') +
        (n.same_named_library_component ? '; same-named library component: ' + n.same_named_library_component : '');
      labelEls.push({ el: lbl, ghost: true });
    } else {
      el('circle', { r: n.r, class: 'og-dot', fill: TYPE_COLOR[n.type] }, dg);
      var lbl2 = el('text', { class: 'og-label', x: n.r + 6, y: 4 }, lg);
      lbl2.textContent = n.name;
      title = n.id + '\ntype: ' + n.type + ' · usage count: ' + n.usage_count +
        '\nnode_id: ' + n.node_id + '\nfingerprint: ' + n.figma_fingerprint + '\nfile: ' + n.file;
      dg.style.cursor = 'pointer'; lg.style.cursor = 'pointer';
      labelEls.push({ el: lbl2, ghost: false });
    }
    el('title', {}, dg).textContent = title;
    el('title', {}, lg).textContent = title;
    nodeEls[n.id] = { dot: dg, label: lg };
  });

  function render() {
    nodes.forEach(function (n) {
      var t = 'translate(' + n.x.toFixed(1) + ',' + n.y.toFixed(1) + ')';
      nodeEls[n.id].dot.setAttribute('transform', t);
      nodeEls[n.id].label.setAttribute('transform', t);
    });
    edgeEls.forEach(function (e) {
      var a = e.edge.a, b = e.edge.b;
      e.el.setAttribute('x1', a.x); e.el.setAttribute('y1', a.y);
      e.el.setAttribute('x2', b.x); e.el.setAttribute('y2', b.y);
    });
  }

  // ---------------------------------------------------------------- run/settle loop
  var frame = 0;
  var MIN_SETTLE_FRAMES = 260; // the radial band-pull is a slow exponential correction (not
  // reflected in velocity/KE) — isolated nodes can go velocity-quiet in ~10 frames while still
  // far outside their tier's ring, so sleep must not trigger on KE alone until it's had time to converge.
  function tick() {
    var ke = physicsStep();
    render();
    frame++;
    if (ke < 0.6 && frame > MIN_SETTLE_FRAMES && !dragging) { asleep = true; rafId = null; return; }
    rafId = requestAnimationFrame(tick);
  }
  function wake() { if (rafId == null) { asleep = false; frame = 0; rafId = requestAnimationFrame(tick); } }
  render();
  wake();

  // ---------------------------------------------------------------- zoom / pan
  var view = { x: 0, y: 0, scale: 1 };
  // Labels live inside the same scaled group as the nodes, so a plain font-size would grow
  // linearly with zoom forever (unreadable at high zoom, all-or-nothing at low zoom). Instead
  // labels are invisible below LABEL_ZOOM_MIN, fade + grow in screen-space size between MIN and
  // MAX, then hold a fixed on-screen size beyond MAX — done by counter-dividing the local
  // font-size by view.scale so the RENDERED pixel size is the thing being controlled, not the
  // local SVG unit size.
  var LABEL_ZOOM_MIN = 0.55, LABEL_ZOOM_MAX = 1.6;
  var LABEL_PX_MIN = 7, LABEL_PX_MAX = 17, GHOST_PX_RATIO = 0.85;
  function applyView() {
    viewport.setAttribute('transform', 'translate(' + view.x + ',' + view.y + ') scale(' + view.scale + ')');
    var t = Math.max(0, Math.min(1, (view.scale - LABEL_ZOOM_MIN) / (LABEL_ZOOM_MAX - LABEL_ZOOM_MIN)));
    var screenPx = LABEL_PX_MIN + t * (LABEL_PX_MAX - LABEL_PX_MIN);
    var localPx = screenPx / view.scale;
    labelLayer.style.setProperty('--og-label-op', t);
    labelEls.forEach(function (l) {
      l.el.style.fontSize = (localPx * (l.ghost ? GHOST_PX_RATIO : 1)).toFixed(2) + 'px';
    });
  }
  function fitView() { view.x = 0; view.y = 0; view.scale = 1; applyView(); }
  fitView();

  function localPoint(clientX, clientY) {
    var rect = svg.getBoundingClientRect();
    return { x: (clientX - rect.left) * (W / rect.width), y: (clientY - rect.top) * (H / rect.height) };
  }
  function toWorld(clientX, clientY) {
    var p = localPoint(clientX, clientY);
    return { x: (p.x - view.x) / view.scale, y: (p.y - view.y) / view.scale };
  }

  // Trackpads report both gestures through the same 'wheel' event: a pinch arrives with
  // ctrlKey set (the browser's own convention for synthesizing pinch-to-zoom on trackpads,
  // independent of OS), a two-finger scroll arrives without it. So: pinch (or Ctrl/⌘+scroll,
  // for mouse users) zooms; a plain two-finger scroll pans — no click-and-hold required for
  // either, matching Figma's own canvas since that's exactly what this graph mirrors.
  svg.addEventListener('wheel', function (ev) {
    ev.preventDefault();
    if (ev.ctrlKey || ev.metaKey) {
      var p = localPoint(ev.clientX, ev.clientY);
      var world = { x: (p.x - view.x) / view.scale, y: (p.y - view.y) / view.scale };
      var dy = Math.max(-120, Math.min(120, ev.deltaY)); // clamp stray large-delta spikes (some trackpads/mice)
      var factor = Math.exp(-dy * 0.0055);
      var newScale = Math.min(4, Math.max(0.15, view.scale * factor));
      view.x = p.x - world.x * newScale;
      view.y = p.y - world.y * newScale;
      view.scale = newScale;
    } else {
      var scaleX = W / svg.getBoundingClientRect().width;
      view.x -= ev.deltaX * scaleX;
      view.y -= ev.deltaY * scaleX;
    }
    applyView();
  }, { passive: false });

  var dragKey = null, dragMoved = false, dragPointerId = null, panStart = null, panViewStart = null;
  var CLICK_SLOP = 4;

  svg.addEventListener('pointerdown', function (ev) {
    var g = ev.target.closest('.og-node');
    dragPointerId = ev.pointerId;
    svg.setPointerCapture(ev.pointerId);
    if (g && !g.classList.contains('og-ghost')) {
      dragKey = g.getAttribute('data-key'); dragMoved = false;
      dragging = nodeById[dragKey];
      wake();
    } else {
      panning = true; panStart = { x: ev.clientX, y: ev.clientY }; panViewStart = { x: view.x, y: view.y };
    }
  });
  svg.addEventListener('pointermove', function (ev) {
    if (dragKey) {
      var w = toWorld(ev.clientX, ev.clientY);
      var n = nodeById[dragKey];
      var moved = Math.abs(w.x - n.x) > CLICK_SLOP || Math.abs(w.y - n.y) > CLICK_SLOP;
      if (moved) dragMoved = true;
      n.x = w.x; n.y = w.y; n.vx = 0; n.vy = 0;
      render();
    } else if (panning) {
      var scaleX = W / svg.getBoundingClientRect().width;
      view.x = panViewStart.x + (ev.clientX - panStart.x) * scaleX;
      view.y = panViewStart.y + (ev.clientY - panStart.y) * scaleX;
      applyView();
    }
  });
  function endPointer(ev) {
    if (dragKey) {
      if (!dragMoved) goTo(nodeById[dragKey]);
      dragging = null; dragKey = null; dragMoved = false;
      wake();
    }
    panning = false;
    if (dragPointerId != null) { try { svg.releasePointerCapture(dragPointerId); } catch (e) {} dragPointerId = null; }
  }
  svg.addEventListener('pointerup', endPointer);
  svg.addEventListener('pointercancel', endPointer);
  svg.style.cursor = 'grab';
  svg.addEventListener('pointerdown', function (ev) { if (!ev.target.closest('.og-node')) svg.style.cursor = 'grabbing'; });
  window.addEventListener('pointerup', function () { svg.style.cursor = 'grab'; });

  // zoom toolbar
  var toolbar = mount.parentElement.querySelector('.og-toolbar');
  if (toolbar) {
    toolbar.querySelector('[data-zoom=in]').addEventListener('click', function () { zoomBy(1.3); });
    toolbar.querySelector('[data-zoom=out]').addEventListener('click', function () { zoomBy(1 / 1.3); });
    toolbar.querySelector('[data-zoom=reset]').addEventListener('click', fitView);
  }
  function zoomBy(factor) {
    var p = { x: W / 2, y: H / 2 };
    var world = { x: (p.x - view.x) / view.scale, y: (p.y - view.y) / view.scale };
    view.scale = Math.min(4, Math.max(0.15, view.scale * factor));
    view.x = p.x - world.x * view.scale; view.y = p.y - world.y * view.scale;
    applyView();
  }

  // ---------------------------------------------------------------- hover spotlight
  function spotlight(key) {
    var keep = {}; keep[key] = 1;
    for (var k in (adj[key] || {})) keep[k] = 1;
    for (var id in nodeEls) {
      var on = !keep[id];
      nodeEls[id].dot.classList.toggle('dimmed', on);
      nodeEls[id].label.classList.toggle('dimmed', on);
    }
    edgeEls.forEach(function (e) {
      var on = e.edge.a.id === key || e.edge.b.id === key;
      e.el.classList.toggle('dimmed', !on);
      e.el.classList.toggle('hot', on);
    });
  }
  function clearSpotlight() {
    for (var id in nodeEls) {
      nodeEls[id].dot.classList.remove('dimmed');
      nodeEls[id].label.classList.remove('dimmed');
    }
    edgeEls.forEach(function (e) { e.el.classList.remove('dimmed', 'hot'); });
  }
  viewport.addEventListener('pointerover', function (ev) {
    var g = ev.target.closest('.og-node'); if (g) spotlight(g.getAttribute('data-key'));
  });
  viewport.addEventListener('pointerout', function (ev) {
    var g = ev.target.closest('.og-node'); if (g) clearSpotlight();
  });
})();
"""

GRAPH_CSS = """
.graphwrap{display:flex;align-items:stretch;gap:0}
.graphstage{flex:1;min-width:0;position:relative;height:100%}
#graph-mount{width:100%;height:100%}
.ograph{width:100%;height:100%;display:block;touch-action:none;user-select:none}
.og-toolbar{position:absolute;top:20px;right:20px;display:flex;flex-direction:column;gap:6px;z-index:2}
.og-toolbar button{width:30px;height:30px;border-radius:var(--r-sm);border:1px solid var(--line);background:var(--panel);color:var(--ink);font-size:15px;cursor:pointer;box-shadow:0 1px 2px rgba(0,0,0,.06);transition:border-color .15s,transform .1s}
.og-toolbar button:hover{border-color:var(--blue);color:var(--blue)}
.og-toolbar button:active{transform:scale(.9)}
.og-hint{position:absolute;left:20px;bottom:16px;font-size:11.5px;color:var(--ink3);background:var(--panel);border:1px solid var(--line);border-radius:var(--r-pill);padding:4px 12px;z-index:2;font-family:var(--font-text)}
.og-node{cursor:pointer}
.og-node.dimmed{opacity:.15}
.og-dot{stroke:var(--panel);stroke-width:2;transition:opacity .12s}
.og-dot-ghost{fill:var(--warn-bg);stroke:var(--organism);stroke-dasharray:2 2;r:5}
.og-label{font-size:11px;fill:var(--ink);opacity:var(--og-label-op,1);transition:opacity .15s,font-size .15s;pointer-events:none;font-family:var(--font-text)}
.og-label-ghost{fill:var(--organism);font-size:10px}
.og-edge{stroke-width:1.3;transition:opacity .12s,stroke-width .12s}
.og-e-structural{stroke:var(--ink3);opacity:.5}
.og-e-behavioral{stroke:var(--plum);stroke-dasharray:5 4;opacity:.4}
.og-e-dangling{stroke:var(--organism);stroke-dasharray:2 4;stroke-width:1.6;opacity:.6}
.og-edge.dimmed{opacity:.04}
.og-edge.hot{opacity:1;stroke-width:2.2}
.legend{display:flex;gap:18px;flex-wrap:wrap;align-items:center;background:var(--panel);border:1px solid var(--line);border-radius:var(--r-md);padding:10px 16px;margin:12px 0;font-size:12.5px}
.legend .sw{display:inline-block;width:12px;height:12px;border-radius:50%;vertical-align:-2px;margin-right:5px}
.legend .ln{display:inline-block;width:26px;height:0;border-top:2px solid var(--ink3);vertical-align:3px;margin-right:5px}
.legend .ln.dash{border-top-style:dashed;border-color:var(--plum)}
.legend .ln.bad{border-top-style:dotted;border-color:var(--organism)}
.legend .grow{display:inline-flex;align-items:center;gap:3px}
.legend .g1{width:8px;height:8px;border-radius:50%;background:var(--ink3)}
.legend .g2{width:14px;height:14px;border-radius:50%;background:var(--ink3)}
.graph-legend{flex:none;width:180px;flex-direction:column;align-items:flex-start;flex-wrap:nowrap;gap:12px;
  background:transparent;border:none;border-radius:0;margin:0;padding:6px 0 6px 18px;
  border-left:1px solid var(--line)}
.graph-legend .legend-title{font-family:var(--font-display);font-weight:600;font-size:12.5px;color:var(--ink)}
.graph-desc{margin:14px 2px 0}
"""

def main():
    data = build_graph_data()
    gdir = os.path.join(ROOT, "graph")
    os.makedirs(gdir, exist_ok=True)
    with open(os.path.join(gdir, "graph.json"), "w") as f:
        json.dump(data, f, indent=1)

    payload = json.dumps(data).replace("</", "<\\/")
    n_dangling = sum(1 for e in data["edges"] if e["type"] == "dangling")
    dangling_legend = (f'<span><span class="ln bad"></span>red = dangling reference '
                       f'({n_dangling}, registry-flagged)</span>') if n_dangling else ""
    dangling_note = ("""<p class="dim">Dangling references sit on their own outer ring, drawn as broken red
    edges to ghost markers — components the registry says exist outside the ingested library page.
    They are shown as broken, never repaired (details: INGESTION_REPORT.md §5).</p>""") if n_dangling else ""
    body = f"""
    <header class="pagehead"><h1>Component graph</h1></header>
    <div class="graphwrap">
      <div class="graphstage">
        <div id="graph-mount"></div>
        <div class="og-toolbar">
          <button type="button" data-zoom="in" title="Zoom in">+</button>
          <button type="button" data-zoom="out" title="Zoom out">−</button>
          <button type="button" data-zoom="reset" title="Reset view">⤢</button>
        </div>
        <div class="og-hint">Two-finger scroll to pan · pinch (or Ctrl/⌘+scroll) to zoom · drag a node to reposition</div>
      </div>
      <aside class="legend graph-legend">
        <span class="legend-title">Legend</span>
        <span><span class="sw" style="background:#1c7a45"></span>atom</span>
        <span><span class="sw" style="background:#9c6a1f"></span>molecule</span>
        <span><span class="sw" style="background:#b3261e"></span>organism</span>
        <span><span class="sw" style="background:#6b1414"></span>complex-organism</span>
        <span><span class="ln"></span>solid = is built from (part → whole)</span>
        <span><span class="ln dash"></span>dashed = behavioral relationship</span>
        {dangling_legend}
        <span class="grow"><span class="g1"></span><span class="g2"></span> size = usage count</span>
      </aside>
    </div>
    <p class="dim graph-desc">The canonical wiring of the library, generated from <code>registry.yaml</code> and laid out
    live by a force simulation — atoms cluster at the center, molecules and organisms grow outward as they
    compose from what's inside them, exactly like the underlying <code>used_atoms</code>/<code>used_molecules</code>
    relationships. Hover a component to spotlight everything it is wired to; drag a node to reposition it;
    two-finger scroll (or drag the canvas) to pan, pinch or Ctrl/⌘+scroll to zoom; click a node to open its
    dashboard page. The identical data is queryable
    by the agent at <code>graph/graph.json</code> (and embedded in this page), with every node exposing
    <code>id</code>, <code>node_id</code> and <code>figma_fingerprint</code>.</p>
    {dangling_note}
    <style>{GRAPH_CSS}</style>
    <script type="application/json" id="graph-data">{payload}</script>
    <script>{GRAPH_JS}</script>
    """
    with open(os.path.join(dash.OUT, "graph.html"), "w") as f:
        f.write(dash.page("Component graph", "graph", body))
    print(f"graph: {len(data['nodes'])} nodes, {len(data['edges'])} edges "
          f"({n_dangling} dangling) -> graph/graph.json + dashboard/graph.html")

if __name__ == "__main__":
    main()
