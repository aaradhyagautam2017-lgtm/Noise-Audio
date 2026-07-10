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
flags as dangling (resolved: false) are drawn as red broken edges to ghost
markers — shown, never dropped or repaired. Layout is deterministic (tiered by
type, registry order); this is the canonical wiring, not a force reshuffle.

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
            if not e.get("resolved"):
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

  var TYPE_COLOR = { atom: '#1c8a4c', molecule: '#b6732b', organism: '#c42e2e', 'complex-organism': '#7a1616' };
  var tiers = ['atoms', 'molecules', 'organisms'];
  var X = { atoms: 150, molecules: 480, organisms: 810 }, GX = 1120;
  var ROW = 52, TOP = 86;

  var byTier = { atoms: [], molecules: [], organisms: [] };
  data.nodes.forEach(function (n) { byTier[n.tier].push(n); });
  var pos = {};
  tiers.forEach(function (t) {
    byTier[t].forEach(function (n, i) { pos[n.id] = { x: X[t], y: TOP + i * ROW }; });
  });
  // ghost markers for dangling references, deduped by ref_node_id (registry data, not invented)
  var ghosts = {}, ghostOrder = [];
  data.edges.forEach(function (e) {
    if (e.type !== 'dangling') return;
    if (!ghosts[e.ref_node_id]) { ghosts[e.ref_node_id] = e; ghostOrder.push(e.ref_node_id); }
  });
  var gpos = {};
  ghostOrder.forEach(function (gid, i) { gpos[gid] = { x: GX, y: TOP + i * 34 }; });

  var H = Math.max(TOP + byTier.atoms.length * ROW, TOP + ghostOrder.length * 34) + 40;
  var svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('viewBox', '0 0 1330 ' + H);
  svg.setAttribute('class', 'cgraph');
  mount.appendChild(svg);

  function el(tag, attrs, parent) {
    var e = document.createElementNS(svgNS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    (parent || svg).appendChild(e); return e;
  }
  // arrowhead for structural edges (part -> whole)
  var defs = el('defs', {});
  var m = el('marker', { id: 'arrow', viewBox: '0 0 8 8', refX: 7, refY: 4, markerWidth: 6, markerHeight: 6, orient: 'auto' }, defs);
  el('path', { d: 'M0,0 L8,4 L0,8 z', fill: '#8a8a8a' }, m);

  // tier headers with counts
  var tierCounts = { atoms: data.counts.atoms, molecules: data.counts.molecules, organisms: data.counts.organisms };
  tiers.forEach(function (t) {
    el('text', { x: X[t], y: 34, class: 'g-col' }).textContent =
      t.charAt(0).toUpperCase() + t.slice(1) + ' — ' + tierCounts[t];
    el('text', { x: X[t], y: 52, class: 'g-colsub' }).textContent =
      { atoms: 'raw parts', molecules: 'combinations', organisms: 'complete patterns' }[t];
  });
  if (ghostOrder.length) {
    el('text', { x: GX, y: 34, class: 'g-col g-broken' }).textContent = 'Outside the library — ' + ghostOrder.length;
    el('text', { x: GX, y: 52, class: 'g-colsub' }).textContent = 'dangling references (registry-flagged)';
  }

  var radius = function (n) { return 9 + 2.5 * Math.min(n.usage_count, 8); };
  var edgeEls = [], nodeEls = {}, adj = {};
  function addAdj(a, b) { (adj[a] = adj[a] || {})[b] = 1; (adj[b] = adj[b] || {})[a] = 1; }

  var eg = el('g', { class: 'edges' });
  data.edges.forEach(function (e, idx) {
    var a, b, cls;
    if (e.type === 'dangling') { a = pos[e.source]; b = gpos[e.ref_node_id]; cls = 'e-dangling'; }
    else { a = pos[e.source]; b = pos[e.target]; cls = e.type === 'structural' ? 'e-structural' : 'e-behavioral'; }
    if (!a || !b) return;
    var ra = e.type === 'dangling' ? 0 : radius(data.nodes.find(function (n) { return n.id === e.source; }));
    var x1 = a.x + (b.x > a.x ? ra : -ra), x2 = b.x - (b.x > a.x ? 12 : -12);
    if (e.type === 'behavioral' && a.x === b.x) { x1 = a.x + ra; x2 = b.x + 12; }
    var mx = (x1 + x2) / 2;
    var p = el('path', { class: 'g-edge ' + cls,
      d: 'M' + x1 + ',' + a.y + ' C' + mx + ',' + a.y + ' ' + mx + ',' + b.y + ' ' + x2 + ',' + b.y }, eg);
    if (e.type === 'structural') p.setAttribute('marker-end', 'url(#arrow)');
    var t = el('title', {}, p);
    t.textContent = e.type === 'structural' ? e.meaning
      : e.type === 'behavioral' ? e.source + ' —[' + e.relation + ']→ ' + e.target
      : e.source + ' → ' + e.ref_name + ' (' + (e.external_location || 'outside library') + ') — dangling reference';
    var key = e.type === 'dangling' ? 'ghost:' + e.ref_node_id : e.target;
    edgeEls.push({ el: p, a: e.source, b: key });
    addAdj(e.source, key);
  });

  // ghost nodes (broken-reference targets named in the registry)
  ghostOrder.forEach(function (gid) {
    var e = ghosts[gid], p = gpos[gid];
    var g = el('g', { class: 'g-ghost', 'data-key': 'ghost:' + gid });
    el('rect', { x: p.x - 12, y: p.y - 11, width: 200, height: 22, rx: 6 }, g);
    el('text', { x: p.x + 2, y: p.y + 4, class: 'g-ghostlabel' }, g).textContent = '✕ ' + e.ref_name;
    var t = el('title', {}, g);
    t.textContent = e.ref_name + ' (' + gid + ') — ' + (e.external_location || 'outside library') +
      (e.same_named_library_component ? '; same-named library component: ' + e.same_named_library_component : '');
    nodeEls['ghost:' + gid] = g;
  });

  // component nodes
  data.nodes.forEach(function (n) {
    var p = pos[n.id], r = radius(n);
    var a = document.createElementNS(svgNS, 'a');
    a.setAttribute('href', link(n));
    a.setAttribute('class', 'g-nodegroup');
    a.setAttribute('data-key', n.id);
    svg.appendChild(a);
    el('circle', { cx: p.x, cy: p.y, r: r, class: 'g-dot', fill: TYPE_COLOR[n.type] }, a);
    el('text', { x: p.x + r + 7, y: p.y + 4, class: 'g-name' }, a).textContent = n.name;
    var t = el('title', {}, a);
    t.textContent = n.id + '\ntype: ' + n.type + ' · usage count: ' + n.usage_count +
      '\nnode_id: ' + n.node_id + '\nfingerprint: ' + n.figma_fingerprint + '\nfile: ' + n.file;
    nodeEls[n.id] = a;
  });

  // hover spotlight: highlight the node's whole neighborhood, dim the rest
  function spotlight(key) {
    var keep = { }; keep[key] = 1;
    for (var k in (adj[key] || {})) keep[k] = 1;
    for (var id in nodeEls) nodeEls[id].classList.toggle('dimmed', !keep[id]);
    edgeEls.forEach(function (e) {
      var on = e.a === key || e.b === key;
      e.el.classList.toggle('dimmed', !on);
      e.el.classList.toggle('hot', on);
    });
  }
  function clear() {
    for (var id in nodeEls) nodeEls[id].classList.remove('dimmed');
    edgeEls.forEach(function (e) { e.el.classList.remove('dimmed', 'hot'); });
  }
  for (var id in nodeEls) {
    (function (key) {
      nodeEls[key].addEventListener('mouseenter', function () { spotlight(key); });
      nodeEls[key].addEventListener('mouseleave', clear);
    })(id);
  }
})();
"""

GRAPH_CSS = """
.cgraph{width:100%;min-width:1200px}
.g-colsub{font-size:10.5px;fill:#919191}
.g-broken{fill:#c42e2e}
.g-dot{stroke:#fff;stroke-width:2}
.g-nodegroup{cursor:pointer}
.g-nodegroup.dimmed,.g-ghost.dimmed{opacity:.14}
.g-name{font-size:11.5px;fill:#171717}
.g-edge{fill:none;stroke-width:1.3;transition:opacity .12s}
.e-structural{stroke:#8a8a8a;opacity:.65}
.e-behavioral{stroke:#8a38f5;stroke-dasharray:5 4;opacity:.5}
.e-dangling{stroke:#c42e2e;stroke-dasharray:2 4;stroke-width:1.6;opacity:.75}
.g-edge.dimmed{opacity:.05}
.g-edge.hot{opacity:1;stroke-width:2.2}
.g-ghost rect{fill:#fff7e8;stroke:#c42e2e;stroke-dasharray:3 3}
.g-ghostlabel{font-size:10.5px;fill:#9e1e1e}
.legend{display:flex;gap:18px;flex-wrap:wrap;align-items:center;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 16px;margin:12px 0;font-size:12.5px}
.legend .sw{display:inline-block;width:12px;height:12px;border-radius:50%;vertical-align:-2px;margin-right:5px}
.legend .ln{display:inline-block;width:26px;height:0;border-top:2px solid #8a8a8a;vertical-align:3px;margin-right:5px}
.legend .ln.dash{border-top-style:dashed;border-color:#8a38f5}
.legend .ln.bad{border-top-style:dotted;border-color:#c42e2e}
.legend .grow{display:inline-flex;align-items:center;gap:3px}
.legend .g1{width:8px;height:8px;border-radius:50%;background:#696969}
.legend .g2{width:14px;height:14px;border-radius:50%;background:#696969}
"""

def main():
    data = build_graph_data()
    gdir = os.path.join(ROOT, "graph")
    os.makedirs(gdir, exist_ok=True)
    with open(os.path.join(gdir, "graph.json"), "w") as f:
        json.dump(data, f, indent=1)

    payload = json.dumps(data).replace("</", "<\\/")
    n_dangling = sum(1 for e in data["edges"] if e["type"] == "dangling")
    body = f"""
    <header class="pagehead"><h1>Component graph</h1></header>
    <p class="dim">The canonical wiring of the library, generated from <code>registry.yaml</code> in one pass —
    it renders only nodes and edges that exist there, at fixed, deterministic positions (registry order,
    tiered by type). Hover a component to spotlight everything it is wired to; click it to open its
    dashboard page. The identical data is queryable by the agent at <code>graph/graph.json</code>
    (and embedded in this page), with every node exposing <code>id</code>, <code>node_id</code> and
    <code>figma_fingerprint</code>.</p>
    <div class="legend">
      <span><b>Legend</b></span>
      <span><span class="sw" style="background:#1c8a4c"></span>atom</span>
      <span><span class="sw" style="background:#b6732b"></span>molecule</span>
      <span><span class="sw" style="background:#c42e2e"></span>organism</span>
      <span><span class="sw" style="background:#7a1616"></span>complex-organism</span>
      <span><span class="ln"></span>solid = is built from (part → whole)</span>
      <span><span class="ln dash"></span>dashed = behavioral relationship</span>
      <span><span class="ln bad"></span>red = dangling reference ({n_dangling}, registry-flagged)</span>
      <span class="grow"><span class="g1"></span><span class="g2"></span> size = usage count</span>
    </div>
    <div class="graphwrap"><div id="graph-mount"></div></div>
    <p class="dim">Dangling references are drawn to ghost markers on the right — components the registry
    says exist outside the ingested library page. They are shown as broken, never repaired
    (details: INGESTION_REPORT.md §5).</p>
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
