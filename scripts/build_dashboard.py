#!/usr/bin/env python3
"""Phase 2 — Designer Dashboard generator for the Noise Audio DLS repo.

Generates a static, browsable component-library site under dashboard/ in ONE pass,
reading ONLY this repository (components/**.yaml, tokens/*.yaml, registry.yaml).
It never connects to Figma, never invents copy or values, and renders stored
metadata as-is. Re-run it after any repo change to regenerate the site.

Usage:  python3 scripts/build_dashboard.py
"""
import html
import json
import os
import re
import shutil
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "dashboard")

# ----------------------------------------------------------------- load repo
def load_yaml(path):
    with open(os.path.join(ROOT, path)) as f:
        return yaml.safe_load(f)

registry = load_yaml("registry.yaml")["registry"]
tokens_colors = load_yaml("tokens/colors.yaml")
tokens_typo = load_yaml("tokens/typography.yaml")
tokens_spacing = load_yaml("tokens/spacing.yaml")

# Overview copy is designer-authored and lives outside this script, so it can be edited
# without touching Python. Absent file degrades to an empty overview rather than failing.
try:
    overview_copy = load_yaml("overview.yaml")["overview"]
except (FileNotFoundError, KeyError, TypeError):
    overview_copy = {}

components = {}          # id -> parsed component file
for entry in registry["components"]:
    components[entry["id"]] = load_yaml(entry["file"])

reg_by_id = {c["id"]: c for c in registry["components"]}
order = [c["id"] for c in registry["components"]]
by_type = {"atom": [], "molecule": [], "organism": [], "complex-organism": []}
for cid in order:
    by_type.setdefault(reg_by_id[cid]["type"], []).append(cid)
# complex-organisms browse with organisms
group_defs = [
    ("Atoms", by_type.get("atom", [])),
    ("Molecules", by_type.get("molecule", [])),
    ("Organisms", by_type.get("organism", []) + by_type.get("complex-organism", [])),
]

# node id -> component id (top level + every variant) for resolving preview instances
node_map = {}
for cid, comp in components.items():
    node_map[comp["node_id"]] = cid
    for v in comp.get("variants", []) or []:
        node_map[v["node_id"]] = cid

# used-by = inverse of structural edges; behavioral inverses shown with relation names
used_by = {cid: [] for cid in order}
for c in registry["components"]:
    for t in (c.get("structural_edges", {}) or {}).get("uses", []) or []:
        if t in used_by:
            used_by[t].append((c["id"], "built from"))
    for e in c.get("behavioral_edges", []) or []:
        if e["target"] in used_by:
            used_by[e["target"]].append((c["id"], e["relation"]))

validation = registry.get("validation", {})
control_panel_missing = not os.path.exists(os.path.join(ROOT, "CONTROL_PANEL.md"))

# Agent learning ledger (see AGENT.md §6) — append-only, one JSON object per line. Missing
# or empty is a valid, honest state (nothing has been logged yet), not an error.
learnings = []
learnings_path = os.path.join(ROOT, "learnings.jsonl")
if os.path.exists(learnings_path):
    with open(learnings_path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                learnings.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"warning: learnings.jsonl line {lineno} is not valid JSON, skipped ({e})", file=sys.stderr)

# Reverse-indexed by component, same pattern as used_by above: scan every entry's
# `components` list and group into per-status buckets keyed by component id.
learnings_by_component = {cid: {"confirmed": [], "pending": [], "rejected": []} for cid in order}
learnings_confirmed, learnings_pending, learnings_rejected = [], [], []
STATUS_BUCKET = {"confirmed": "confirmed", "proposed": "pending", "rejected": "rejected"}
for entry in learnings:
    bucket = STATUS_BUCKET.get(entry.get("status"))
    if bucket is None:  # "superseded", or an unrecognized status — not shown as live guidance
        continue
    (learnings_confirmed if bucket == "confirmed" else
     learnings_pending if bucket == "pending" else learnings_rejected).append(entry)
    for cid in entry.get("components") or []:
        if cid in learnings_by_component:
            learnings_by_component[cid][bucket].append(entry)

E = lambda s: html.escape(str(s), quote=True)

# ----------------------------------------------------------------- library-health stats
# Everything below is read straight from the repo at build time (authored_metadata,
# figma_instance_edges, structural/behavioral edges) — there is no separate "score";
# these are the same facts the component pages already show, aggregated for the overview.
CORE_DOC_FIELDS = [("purpose", "Purpose"), ("usage", "Usage"),
                    ("design_intent", "Design intent"), ("anti_patterns", "Anti-patterns"),
                    ("rules", "Rules")]

def parse_authored_body(cid):
    """Same parse the component page uses (render_metadata): the component's
    authored_metadata is itself a YAML document, optionally nested under 'component'."""
    try:
        parsed = yaml.safe_load(components[cid].get("authored_metadata"))
    except yaml.YAMLError:
        return None, True
    if not isinstance(parsed, dict):
        return None, True
    body = parsed.get("component", parsed)
    return (body, False) if isinstance(body, dict) else (None, True)

doc_status = {}                                    # cid -> (filled, total, parse_error)
field_coverage = {k: 0 for k, _ in CORE_DOC_FIELDS}
missing_by_field = {k: [] for k, _ in CORE_DOC_FIELDS}   # field -> [cid, ...] that lack it
for cid in order:
    body, err = parse_authored_body(cid)
    if err:
        doc_status[cid] = (0, len(CORE_DOC_FIELDS), True)
        continue  # unparseable metadata has no reliable per-field state — see the error card
    filled = 0
    for key, _ in CORE_DOC_FIELDS:
        if body.get(key):
            filled += 1
            field_coverage[key] += 1
        else:
            missing_by_field[key].append(cid)
    doc_status[cid] = (filled, len(CORE_DOC_FIELDS), False)
doc_parse_errors = sum(1 for _, _, err in doc_status.values() if err)

ref_resolved = ref_excluded = ref_dangling = 0
for c in registry["components"]:
    for e in (c.get("figma_instance_edges") or []):
        if e.get("excluded"):
            ref_excluded += 1
        elif e.get("resolved"):
            ref_resolved += 1
        else:
            ref_dangling += 1
ref_total = ref_resolved + ref_excluded + ref_dangling

total_structural = sum(len((c.get("structural_edges") or {}).get("uses", []) or [])
                       for c in registry["components"])
total_behavioral = sum(len(c.get("behavioral_edges") or []) for c in registry["components"])
total_relationships = total_structural + total_behavioral
avg_connections = (2 * total_relationships / len(order)) if order else 0

# ----------------------------------------------------------------- shell
THEME_ICON = ('<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="8" cy="8" r="6.25" '
              'stroke="currentColor" stroke-width="1.4"/><path d="M8 1.75a6.25 6.25 0 0 1 0 12.5z" '
              'fill="currentColor"/></svg>')

def sidebar(prefix, active):
    def item(href, label, key, count=None, warn=0, dot=None):
        cls = "navitem pill" if dot else "navitem"
        if key == active:
            cls += " active"
        marker = f'<span class="navdot d-{dot}"></span>' if dot else ""
        badge = f'<span class="count">{count}</span>' if count is not None else ""
        wbadge = f'<span class="warnbadge" title="dangling Figma references">{warn}</span>' if warn else ""
        return (f'<a class="{cls}" href="{prefix}{href}">{marker}'
                f'<span class="navlabel">{E(label)}</span>{badge}{wbadge}</a>')
    parts = [f'''
    <aside class="sidebar">
      <div class="brand">
        <span class="applogo">N</span>
        <span class="brandname">{E(registry["app"])}</span>
        <button class="themetoggle" type="button" id="themetoggle" title="Toggle light / dark"
                aria-label="Toggle light or dark theme">{THEME_ICON}</button>
      </div>
      <nav>
        {item("index.html", "Overview", "overview")}
        {item("graph.html", "Component graph", "graph")}
        {item("fill-gaps.html", "Fill the gaps", "fill-gaps")}
        <div class="navgroup">Foundations <span class="count">3</span></div>
        {item("foundations-colors.html", "Colors & tokens", "colors")}
        {item("foundations-typography.html", "Typography", "typography")}
        {item("foundations-spacing.html", "Spacing & radius", "spacing")}
    ''']
    for gname, ids in group_defs:
        parts.append(f'<div class="navgroup">{gname} <span class="count">{len(ids)}</span></div>')
        for cid in ids:
            dangling = sum(1 for e in reg_by_id[cid].get("figma_instance_edges", []) or [] if not e["resolved"] and not e.get("excluded"))
            parts.append(item(f"components/{cid}.html", components[cid]["name"].strip(), f"c-{cid}",
                              warn=dangling, dot=reg_by_id[cid]["type"]))
    parts.append("</nav></aside>")
    return "".join(parts)

def page(title, active, body, prefix=""):
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)} — {E(registry["app"])} DLS</title>
<script>(function(){{try{{var t=localStorage.getItem('na-theme');if(t)document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}}})();</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Roboto+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{prefix}assets/style.css">
</head><body>
<div class="layout">
{sidebar(prefix, active)}
<main class="main">
{body}
<footer class="footer">Generated from the repository — single source of truth. Regenerate with <code>python3 scripts/build_dashboard.py</code>. Source: Figma file <code>{E(registry["source"]["figma_file_key"])}</code>, page “{E(registry["source"]["figma_page"])}”, ingested {E(registry["generated"])}.</footer>
</main>
</div>
<script src="{prefix}assets/app.js"></script>
</body></html>"""

def copyable(label, value):
    return (f'<div class="idrow"><span class="idlabel">{E(label)}</span>'
            f'<code class="idvalue" id="copy-{E(label).lower().replace(" ","-")}">{E(value)}</code>'
            f'<button class="copybtn" data-copy="{E(value)}" title="Copy {E(label)}">⧉ copy</button></div>')

def warn(msg):
    return f'<div class="warning">⚠ {msg}</div>'

# ----------------------------------------------------------------- generic YAML renderer
def render_val(v, depth=0):
    if v is None:
        return '<span class="missing">missing</span>'
    if isinstance(v, dict):
        rows = "".join(f'<div class="kv"><div class="k">{E(k)}</div><div class="v">{render_val(x, depth+1)}</div></div>'
                       for k, x in v.items())
        return f'<div class="kvs">{rows}</div>'
    if isinstance(v, list):
        if all(isinstance(x, dict) and ("id" in x or "rule" in x) for x in v):
            out = []
            for x in v:
                rid = x.get("id", "")
                rule = x.get("rule", "")
                rest = {k: y for k, y in x.items() if k not in ("id", "rule")}
                out.append(f'<li>{f"<code class=ruleid>{E(rid)}</code> " if rid else ""}{E(rule) if rule else ""}'
                           + (render_val(rest, depth + 1) if rest else "") + "</li>")
            return f'<ul class="rules">{"".join(out)}</ul>'
        return '<ul>' + "".join(f'<li>{render_val(x, depth+1)}</li>' for x in v) + '</ul>'
    return E(v)

SECTION_ORDER = ["purpose", "usage", "design_intent", "anti_patterns", "variant_axes", "variants",
                 "supported_variants", "states", "toggles", "rules", "composition", "parts",
                 "content_structure", "structure_default_modal", "relationships", "constraints",
                 "variant_axis", "ai_metadata", "visual_properties", "metadata_governance"]
SECTION_TITLES = {
    "purpose": "Purpose", "usage": "Usage", "design_intent": "Design intent",
    "anti_patterns": "Anti-patterns", "variant_axes": "Variant axes", "variants": "Variants",
    "supported_variants": "Supported variants", "states": "States", "toggles": "Toggles",
    "rules": "Rules", "composition": "Composition", "parts": "Parts",
    "content_structure": "Content structure", "structure_default_modal": "Structure (default modal)",
    "relationships": "Relationships", "constraints": "Constraints", "variant_axis": "Variant axis",
    "ai_metadata": "AI metadata", "visual_properties": "Visual properties",
    "metadata_governance": "Metadata governance",
}

def link_component_ids(html_text):
    """Turn known component ids appearing as text into links (post-process, safe: ids are slugs)."""
    for cid in sorted(components, key=len, reverse=True):
        html_text = re.sub(rf'(?<![\w/-]){re.escape(cid)}(?![\w-])',
                           f'<a href="{cid}.html">{cid}</a>', html_text)
    return html_text

def render_metadata(comp):
    raw = comp["authored_metadata"]
    parsed, err = None, None
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        err = str(e).split("\n")[0]
    out = []
    if parsed is None or not isinstance(parsed, dict):
        out.append(warn("The authored YAML for this component could not be parsed"
                        + (f" (<code>{E(err)}</code>)" if err else "") +
                        "; it is shown raw below exactly as stored."))
    else:
        body = parsed.get("component", parsed)
        if not isinstance(body, dict):
            body = parsed
        skip = {"id", "name", "type", "reusable", "standalone", "type_note"}
        header_bits = []
        for k in ("reusable", "standalone", "type_note"):
            if k in body:
                header_bits.append(f'<span class="pill">{E(k)}: {E(body[k])}</span>')
        if header_bits:
            out.append('<div class="pills">' + "".join(header_bits) + "</div>")
        keys = [k for k in SECTION_ORDER if k in body] + [k for k in body if k not in SECTION_ORDER and k not in skip]
        for k in keys:
            title = SECTION_TITLES.get(k, k.replace("_", " ").capitalize())
            content = link_component_ids(render_val(body[k]))
            out.append(f'<section class="metasection"><h3>{E(title)}</h3>{content}</section>')
    out.append(f'<details class="rawyaml"><summary>View authored YAML (verbatim from Figma description)</summary>'
               f'<pre>{E(raw)}</pre></details>')
    return "".join(out)

# ----------------------------------------------------------------- preview renderer
ALIGN = {"MIN": "flex-start", "CENTER": "center", "MAX": "flex-end", "SPACE_BETWEEN": "space-between",
         "BASELINE": "baseline"}
WEIGHTS = {"Regular": 400, "Medium": 500, "SemiBold": 600, "Semibold": 600, "Bold": 700}

def first_visible_solid(fills):
    for f in fills or []:
        if f.get("visible") is False:
            continue
        if f.get("type") == "SOLID":
            return f
    return None

def node_style(n):
    s = []
    if "w" in n:
        s.append(f'width:{n["w"]}px'); s.append(f'height:{n["h"]}px')
    lay = n.get("layout")
    if lay:
        s.append("display:flex")
        s.append("flex-direction:" + ("column" if lay["mode"] == "VERTICAL" else "row"))
        p = lay["padding"]
        s.append(f"padding:{p[0]}px {p[1]}px {p[2]}px {p[3]}px")
        if lay.get("gap") is not None and "SPACE_BETWEEN" not in lay.get("align", ""):
            s.append(f"gap:{max(lay['gap'],0)}px")
        prim, cnt = (lay.get("align") or "MIN/MIN").split("/")
        s.append(f"justify-content:{ALIGN.get(prim,'flex-start')}")
        s.append(f"align-items:{ALIGN.get(cnt,'flex-start')}")
        s.append("box-sizing:border-box")
    else:
        s.append("position:relative")
    r = n.get("radius")
    if r is not None:
        s.append("border-radius:" + (f"{r}px" if isinstance(r, (int, float)) else "%spx %spx %spx %spx" % tuple(r)))
    fill = first_visible_solid(n.get("fills"))
    if fill and n.get("type") != "TEXT":
        op = fill.get("opacity", 1)
        s.append(f'background:{fill["color"]}' + (f'; opacity-note:0' if False else ""))
        if op < 1:
            s.append(f"background:color-mix(in srgb, {fill['color']} {int(op*100)}%, transparent)")
    st = first_visible_solid(n.get("strokes"))
    if st:
        w = n.get("strokeWeight", 1)
        w = 1 if w == "mixed" else w
        s.append(f'border:{w}px solid {st["color"]}')
    if n.get("opacity") is not None:
        s.append(f'opacity:{n["opacity"]}')
    for e in n.get("effects", []) or []:
        if e.get("type") == "DROP_SHADOW":
            o = e.get("offset", {"x": 0, "y": 0})
            s.append(f'box-shadow:{o.get("x",0)}px {o.get("y",0)}px {e.get("radius",0)}px {e.get("spread",0)}px {e.get("color","#0002")}')
    return ";".join(s)

def text_style(n):
    s = []
    fill = first_visible_solid(n.get("fills"))
    if fill:
        s.append(f'color:{fill["color"]}')
    font = n.get("font", "")
    if font:
        fam, _, wt = font.rpartition(" ")
        if fam:
            s.append(f"font-family:'{fam}', sans-serif")
        s.append(f"font-weight:{WEIGHTS.get(wt, 400)}")
    if n.get("fontSize"):
        s.append(f'font-size:{n["fontSize"]}px')
    lh = n.get("lineHeight")
    if lh:
        s.append(f"line-height:{lh}")
    ta = (n.get("textAlign") or "LEFT").lower()
    s.append(f"text-align:{ta}")
    if n.get("decoration") == "UNDERLINE":
        s.append("text-decoration:underline")
    s.append("white-space:pre-line")
    return ";".join(s)

def render_node(n, depth=0):
    if n.get("visible") is False:
        return ""  # hidden in Figma; present in the data, not in the render
    t = n.get("type")
    tip = E(f'{n.get("name","")} · {n.get("id","")}' + (f' · token: {json.dumps(n["tokens"])}' if n.get("tokens") else ""))
    if t == "TEXT":
        return f'<span class="pv-text" title="{tip}" style="{node_style(n)};{text_style(n)}">{E(n.get("chars",""))}</span>'
    if t == "INSTANCE":
        ref = n.get("instance_of") or {}
        target = None
        if ref.get("set") and ref["set"].get("id") in node_map:
            target = node_map[ref["set"]["id"]]
        elif ref.get("id") in node_map:
            target = node_map[ref["id"]]
        label = (ref.get("set") or {}).get("name") or ref.get("name") or "instance"
        inner = (f'<a href="{target}.html">{E(label)}</a>' if target
                 else f'<span class="pv-unresolved" title="main component is outside the ingested page">{E(label)} ⚠</span>')
        return (f'<span class="pv-instance" title="{tip}" style="{node_style(n)}">'
                f'<span class="pv-instance-label">{inner}</span></span>')
    if t in ("VECTOR", "LINE", "ELLIPSE", "BOOLEAN_OPERATION"):
        return f'<span class="pv-shape" title="{tip}" style="{node_style(n)}"></span>'
    kids = n.get("children")
    if isinstance(kids, dict):
        kids = list(kids.values())
    inner = "".join(render_node(c, depth + 1) for c in (kids or []))
    if not kids and n.get("childCount"):
        inner = f'<span class="pv-note">{n["childCount"]} children — {E(n.get("note","summarized in visual_values"))}</span>'
    abspos = "" if n.get("layout") else ' data-stack="1"'
    return f'<div class="pv-frame" title="{tip}" style="{node_style(n)}"{abspos}>{inner}</div>'

def render_preview(comp):
    tree = comp.get("visual_values", {}).get("tree")
    if not isinstance(tree, dict):
        return warn("No extracted visual tree stored for this component — preview unavailable.")
    out = ['<p class="pv-caption">Preview rendered from the extracted visual values in this file '
           '(schematic: positions inside non-auto-layout groups are approximate; hidden layers omitted; '
           'nested component instances render as linked chips — each child governs itself).</p>']
    variants = []
    if tree.get("type") == "COMPONENT_SET":
        kids = tree.get("children")
        if isinstance(kids, dict):
            kids = list(kids.values())
        variants = [(k.get("name", "?"), k) for k in (kids or [])]
    else:
        variants = [(None, tree)]
    for name, vt in variants:
        w = vt.get("w", 360)
        scale = min(1.0, 620.0 / max(w, 1))
        label = f'<div class="pv-variantname">{E(name)} <span class="dim">node {E(vt.get("id",""))}</span></div>' if name else ""
        out.append(f'''<div class="pv-block">{label}
          <div class="pv-stage"><div class="pv-scale" style="transform:scale({scale});width:{w}px">{render_node(vt)}</div></div>
        </div>''')
    return "".join(out)

# ----------------------------------------------------------------- component pages
TYPE_BADGE = {"atom": "Atom", "molecule": "Molecule", "organism": "Organism", "complex-organism": "Complex organism"}

def component_page(cid):
    comp = components[cid]
    reg = reg_by_id[cid]
    name = comp["name"].strip()
    dangling = [e for e in reg.get("figma_instance_edges", []) or [] if not e["resolved"] and not e.get("excluded")]
    excluded = [e for e in reg.get("figma_instance_edges", []) or [] if e.get("excluded")]
    warns = []
    if dangling:
        items = "".join(
            f'<li><b>{E(e["references"])}</b> (node <code>{E(e["ref_node_id"])}</code>) — {E(e.get("external_location",""))}'
            + (f'; same-named library component: <a href="{e["same_named_library_component"]}.html">{e["same_named_library_component"]}</a>'
               if e.get("same_named_library_component") else "") + "</li>"
            for e in dangling)
        warns.append(warn(f'{len(dangling)} Figma instance reference(s) inside this component point outside '
                          f'the ingested library page (see INGESTION_REPORT.md):<ul>{items}</ul>'))
    excluded_note = ""
    if excluded:
        items = "".join(f'<li><b>{E(e["references"])}</b> (node <code>{E(e["ref_node_id"])}</code>) — {E(e.get("external_location",""))}</li>' for e in excluded)
        excluded_note = (f'<p class="dim">{len(excluded)} raw Figma instance reference(s) in this component were '
                         f'reviewed and excluded — confirmed not real library dependencies (see INGESTION_REPORT.md §5d):'
                         f'<ul>{items}</ul></p>')

    # Variant axes read as this library's equivalent of a component's props: the axis is the
    # knob, the declared options are its allowed values. Rendered in the rail beside the stage.
    axes_card = ""
    if comp.get("variant_axes"):
        rows = "".join(
            f'<div class="proprow"><span class="propkey">{E(axis)}</span>'
            f'<span class="propval">' +
            '<span class="sep">|</span>'.join(f'<span class="tok">{E(v)}</span>' for v in vals) +
            '</span></div>'
            for axis, vals in comp["variant_axes"].items())
        axes_card = (f'<div class="railcard"><h3>Variant axes</h3>{rows}'
                     f'<div class="proprow"><span class="propkey">variants</span>'
                     f'<span class="propval"><span class="tok">{len(comp.get("variants", []))}</span></span></div></div>')

    ids_card = ('<div class="railcard"><h3>Identifiers</h3>'
                + copyable("Node id", comp["node_id"])
                + copyable("Fingerprint", comp["figma_fingerprint"])
                + f'<div class="idrow"><span class="idlabel">Source</span>'
                  f'<span class="idvalue">{E(reg["file"])}</span></div>'
                + '</div>')

    # composition & relationships (from registry — resolved ids, all clickable)
    comp_rel = []
    uses = (reg.get("structural_edges", {}) or {}).get("uses", []) or []
    if uses:
        comp_rel.append('<div class="subhead">Is built from</div><ul class="linklist">' + "".join(
            f'<li><span class="navdot d-{E(reg_by_id[t]["type"])}"></span><a href="{t}.html">{t}</a></li>' for t in uses) + "</ul>")
    beh = reg.get("behavioral_edges", []) or []
    if beh:
        comp_rel.append('<div class="subhead">Relationships</div><ul class="linklist">' + "".join(
            f'<li><a href="{e["target"]}.html">{e["target"]}</a> <span class="rel">{E(e["relation"])}</span></li>' for e in beh) + "</ul>")
    ub = used_by.get(cid, [])
    if ub:
        comp_rel.append('<div class="subhead">Used by</div><ul class="linklist">' + "".join(
            f'<li><a href="{s}.html">{s}</a> <span class="rel">{E(r)}</span></li>' for s, r in ub) + "</ul>")
    if not comp_rel:
        comp_rel.append('<p class="dim">No declared composition edges or inbound references.</p>')
    rel_card = f'<div class="railcard"><h3>Composition</h3>{"".join(comp_rel)}</div>'

    variants_block = ""
    if comp.get("variants"):
        rows = "".join(
            f'<tr><td>{E(v["name"])}</td><td><code>{E(v["node_id"])}</code></td>'
            f'<td class="fpcell"><code>{E(v["figma_fingerprint"])}</code>'
            f'<button class="copybtn small" data-copy="{E(v["figma_fingerprint"])}">⧉</button></td>'
            f'<td>{v["width"]}×{v["height"]}</td></tr>'
            for v in comp["variants"])
        variants_block = (f'<section class="metasection"><h3>Figma variants</h3>'
                          f'<table class="table"><thead><tr><th>Figma variant</th><th>Node id</th>'
                          f'<th>Fingerprint</th><th>Size</th></tr></thead><tbody>{rows}</tbody></table></section>')

    # Learned guidance (AGENT.md §6) — only rendered when this component actually has entries,
    # so the vast majority of pages (nothing logged yet) stay exactly as they were.
    lc = learnings_by_component.get(cid, {"confirmed": [], "pending": []})
    learned_block = ""
    if lc["confirmed"] or lc["pending"]:
        parts = [f'<section class="metasection"><h3>Learned</h3>'
                 f'<p class="dim">Guidance the agent has picked up from corrections, kept separate from the '
                 f'Figma-authored rules above until a designer promotes it (see AGENT.md §6).</p>']
        if lc["confirmed"]:
            parts.append('<div class="subhead">Confirmed</div>' +
                        render_entry_list([learning_entry(e, cid) for e in lc["confirmed"]], "", "entry-learned"))
        if lc["pending"]:
            parts.append('<div class="subhead">Pending review</div>' +
                        render_entry_list([learning_entry(e, cid) for e in lc["pending"]], "", "entry-pending"))
        parts.append('</section>')
        learned_block = "".join(parts)

    body = f"""
    <header class="pagehead">
      <h1>{E(name)}</h1>
      <span class="typebadge t-{E(reg["type"])}">{E(TYPE_BADGE.get(reg["type"], reg["type"]))}</span>
      <span class="dim">used by {reg.get("usage_count", 0)}</span>
    </header>
    {"".join(warns)}
    {excluded_note}
    <div class="detailgrid">
      <div class="stagecard">{render_preview(comp)}</div>
      <aside class="rail">{axes_card}{ids_card}{rel_card}</aside>
    </div>
    {variants_block}
    {learned_block}
    <h2 class="metaheader">Metadata <span class="count">rendered from the stored authored YAML</span></h2>
    {render_metadata(comp)}
    """
    return page(name, f"c-{cid}", body, prefix="../")

# ----------------------------------------------------------------- foundations
def colors_page():
    cols = tokens_colors["collections"]
    prim = cols["color"]["variables"]
    sem = cols["tokens"]["variables"]

    prim_cards = "".join(
        f'<div class="swatchcard"><div class="swatchfill"><span style="background:{E(v)}"></span></div>'
        f'<div class="swatchmeta"><div class="swatchname">{E(k)}</div>'
        f'<div class="swatchhex"><span>{E(v)}</span>'
        f'<button class="copybtn small" data-copy="{E(v)}">⧉</button></div></div></div>'
        for k, v in prim.items())

    def resolve(val):
        if isinstance(val, str) and val.startswith("alias:"):
            return prim.get(val[6:]), val[6:]
        return val, None

    # Semantic tokens carry a value per mode, so the swatch is split rather than picking
    # one mode and hiding the other — both are the real stored values.
    sem_cards = []
    for k, modes in sem.items():
        lv, la = resolve(modes.get("light"))
        dv, da = resolve(modes.get("dark"))
        alias_note = ""
        if la or da:
            alias_note = f'<div class="dim" style="font-size:10.5px;margin-top:3px">→ {E(la or da)}</div>'
        sem_cards.append(
            f'<div class="swatchcard"><div class="swatchfill">'
            f'<span data-mode="L" style="background:{E(lv)}"></span>'
            f'<span data-mode="D" style="background:{E(dv)}"></span></div>'
            f'<div class="swatchmeta"><div class="swatchname">{E(k)}</div>'
            f'<div class="swatchhex"><span>{E(lv)}</span><span>{E(dv)}</span></div>'
            f'{alias_note}</div></div>')

    body = f"""
    <header class="pagehead"><h1>Colors &amp; tokens</h1></header>
    <p class="subtle">Synced from the Figma variable collections <code>color</code> (primitives) and
    <code>tokens</code> (semantic, Light/Dark). Source: <code>tokens/colors.yaml</code>.</p>
    <div class="subhead">Semantic <span class="dim">— {len(sem)} tokens, light and dark value each</span></div>
    <div class="swatchgrid">{''.join(sem_cards)}</div>
    <div class="subhead">Primitive <span class="dim">— {len(prim)} raw scale values</span></div>
    <div class="swatchgrid">{prim_cards}</div>
    """
    return page("Colors & tokens", "colors", body)

def typography_page():
    rows = []
    for s in tokens_typo["text_styles"]:
        fam = s["font_family"]; wt = WEIGHTS.get(s["font_style"], 400)
        lh = s["line_height"]
        sample_size = min(s["font_size"], 40)
        note = f'<div class="dim">{E(s["description"])}</div>' if s.get("description") else ""
        rows.append(f'''<div class="typo-row">
          <div class="typo-meta"><b>{E(s["name"])}</b><br>
            <span class="dim">{E(fam)} {E(s["font_style"])} · {s["font_size"]}px · line-height {E(lh)} · letter-spacing {E(s["letter_spacing"])}</span>
            <div class="idrow"><code class="idvalue">{E(s["key"])}</code><button class="copybtn small" data-copy="{E(s["key"])}">⧉</button></div>
            {note}</div>
          <div class="typo-sample" style="font-family:'{E(fam)}',sans-serif;font-weight:{wt};font-size:{sample_size}px;line-height:{'normal' if lh=='auto' else E(lh)}">Noise Audio {s["font_size"]}px{'<span class=dim> (shown at 40px)</span>' if sample_size!=s["font_size"] else ''}</div>
        </div>''')
    eff = ""
    for e in tokens_typo.get("effect_styles", []) or []:
        fx = e["effects"][0]
        eff += f'''<div class="typo-row"><div class="typo-meta"><b>{E(e["name"])}</b><br>
        <span class="dim">{E(fx["type"])} · x {fx["x"]} y {fx["y"]} blur {fx["blur"]} spread {fx["spread"]} · {E(fx["color"])}</span>
        <div class="dim">{E(e.get("note",""))}</div></div>
        <div class="shadow-sample" style="box-shadow:{fx["x"]}px {fx["y"]}px {fx["blur"]}px {fx["spread"]}px {E(fx["color"])}"></div></div>'''
    body = f"""
    <header class="pagehead"><h1>Typography</h1></header>
    <p class="dim">Synced from Figma local text styles. Source: <code>tokens/typography.yaml</code>.</p>
    <section class="metasection"><h3>Text styles ({len(tokens_typo["text_styles"])})</h3>{''.join(rows)}</section>
    <section class="metasection"><h3>Effect styles</h3>{eff}</section>
    """
    return page("Typography", "typography", body)

def spacing_page():
    authored = yaml.safe_load(tokens_spacing["authored_spacing_tokens"])["spacing_tokens"]
    sections = []
    for group in ("numeral", "gaps", "padding", "radius"):
        g = authored.get(group)
        if not g: continue
        rows = []
        for t in g["tokens"]:
            v = t["value"]
            if group == "radius":
                viz = f'<span class="radviz" style="border-radius:{min(v,28)}px"></span>'
            else:
                viz = f'<span class="barviz" style="width:{min(v*3,240)}px"></span>'
            rows.append(f'<tr><td><code>{E(t["token"])}</code></td><td>{E(t["name"])}</td><td>{v}px</td><td>{viz}</td></tr>')
        sections.append(f'''<section class="metasection"><h3>{E(group.capitalize())} <span class="dim">— {E(g["description"])}</span></h3>
        <table class="table"><thead><tr><th>Token</th><th>Name</th><th>Value</th><th></th></tr></thead><tbody>{''.join(rows)}</tbody></table></section>''')
    figvars = "".join(f'<tr><td><code>{E(v["name"])}</code></td><td>{E(v["value"])}px</td></tr>'
                      for v in tokens_spacing["figma_numeral_variables"])
    body = f"""
    <header class="pagehead"><h1>Spacing & radius</h1></header>
    <p class="dim">Authored spacing tokens (mirrored verbatim from the “spacing component” card, node <code>2036:3057</code>) plus the Figma <code>numeral</code> variable collection. Source: <code>tokens/spacing.yaml</code>.</p>
    {''.join(sections)}
    <section class="metasection"><h3>Figma <code>numeral</code> variables ({len(tokens_spacing["figma_numeral_variables"])})</h3>
    <p class="dim">{E(tokens_spacing["note"])}</p>
    <table class="table"><thead><tr><th>Variable</th><th>Value</th></tr></thead><tbody>{figvars}</tbody></table></section>
    """
    return page("Spacing & radius", "spacing", body)

# Client-side only: this is a static site with no backend, so nothing typed on this page can
# save itself. Raw string (r"""), not an f-string — it contains plenty of JS literal braces
# and \n sequences that must survive as-is; a non-raw string would have Python's own escape
# processing corrupt them before the browser ever sees this (the exact bug class documented
# elsewhere in this session's history). The one dynamic value (the ledger's current contents)
# is spliced in afterward via .replace() on a plain marker token, never via {} interpolation.
FILL_GAPS_JS = r"""
(function () {
  var CURRENT_LEDGER = __CURRENT_LEDGER_JSON__;
  function buildEntry(cid, field, text) {
    return JSON.stringify({
      id: 'learn-fill-' + cid + '-' + field + '-' + Date.now(),
      logged_at: new Date().toISOString(),
      kind: 'field_contribution',
      source: 'manual-fill',
      components: [cid],
      field: field,
      contributed_text: text,
      status: 'proposed',
      reviewed_by: null,
      reviewed_at: null
    });
  }
  function rows() { return Array.prototype.slice.call(document.querySelectorAll('.gaprow')); }
  document.addEventListener('input', function (ev) {
    var ta = ev.target.closest('textarea[data-field]');
    if (!ta) return;
    var row = ta.closest('.gaprow');
    row.classList.toggle('gaprow-filled', ta.value.trim().length > 0);
    updateCount();
  });
  function updateCount() {
    var n = rows().filter(function (r) { return r.classList.contains('gaprow-filled'); }).length;
    var btn = document.getElementById('download-ledger');
    btn.textContent = n ? 'Download learnings.jsonl with ' + n + ' new entr' + (n === 1 ? 'y' : 'ies') : 'Download learnings.jsonl';
    btn.disabled = n === 0;
  }
  document.addEventListener('click', function (ev) {
    var copyBtn = ev.target.closest('[data-copy-entry]');
    if (copyBtn) {
      var row = copyBtn.closest('.gaprow');
      var text = row.querySelector('textarea').value.trim();
      if (!text) return;
      navigator.clipboard.writeText(buildEntry(row.dataset.cid, row.dataset.field, text)).then(function () {
        var t = copyBtn.textContent; copyBtn.textContent = '✓ copied'; copyBtn.classList.add('copied');
        setTimeout(function () { copyBtn.textContent = t; copyBtn.classList.remove('copied'); }, 1200);
      });
      return;
    }
    if (ev.target.closest('#download-ledger')) {
      var lines = CURRENT_LEDGER ? CURRENT_LEDGER.split('\n').filter(function (l) { return l.trim().length; }) : [];
      var added = 0;
      rows().forEach(function (row) {
        var text = row.querySelector('textarea').value.trim();
        if (!text) return;
        lines.push(buildEntry(row.dataset.cid, row.dataset.field, text));
        added++;
      });
      var status = document.getElementById('download-status');
      if (!added) { status.textContent = 'Nothing typed yet — fill in at least one field first.'; return; }
      var blob = new Blob([lines.join('\n') + '\n'], { type: 'application/x-ndjson' });
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url; a.download = 'learnings.jsonl';
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(url);
      status.textContent = 'Downloaded, ' + added + ' new entr' + (added === 1 ? 'y' : 'ies') + ' appended to the existing ledger. Replace learnings.jsonl in the repo with this file and commit — nothing here saves on its own.';
    }
  });
  updateCount();
})();
"""

def fill_gaps_page():
    ledger_raw = ""
    if os.path.exists(learnings_path):
        with open(learnings_path) as f:
            ledger_raw = f.read()
    js = FILL_GAPS_JS.replace("__CURRENT_LEDGER_JSON__", json.dumps(ledger_raw))

    sections = []
    total_gaps = 0
    for key, label in CORE_DOC_FIELDS:
        missing = missing_by_field[key]
        if not missing:
            continue
        total_gaps += len(missing)
        rows = "".join(f'''
          <div class="gaprow" data-cid="{E(cid)}" data-field="{E(key)}">
            <div class="gaprow-head">
              <a href="components/{cid}.html">{E(components[cid]["name"].strip())}</a>
              <span class="dim">{E(cid)}</span>
            </div>
            <textarea data-field="{E(key)}" rows="3" placeholder="Write the {E(label.lower())} for this component…"></textarea>
            <button type="button" class="gapcopybtn small" data-copy-entry>copy entry</button>
          </div>''' for cid in missing)
        sections.append(f'''
        <section class="metasection" id="gap-{E(key)}">
          <h3>{E(label)} <span class="count">{len(missing)} missing</span></h3>
          {rows}
        </section>''')

    body = f"""
    <header class="pagehead"><h1>Fill the gaps</h1></header>
    <p class="dim">{total_gaps} missing documentation field(s) across the library — one row per component per
    field. This is a static site with no backend: nothing you type here saves by itself. Write the text, then
    either copy one entry at a time or download an updated <code>learnings.jsonl</code> below, replace the
    repo's copy, and commit it. Every entry is logged as <code>proposed</code> — a designer confirms it or
    folds it into Figma directly before it counts as real guidance (see <a href="../AGENT.md">AGENT.md §6</a>).
    Filling a gap here never changes the Documentation coverage numbers on the overview; those measure the
    Figma-authored spec specifically, not this ledger.</p>
    <div class="quicklinks">
      <button type="button" id="download-ledger" class="btn btn-primary" disabled>Download learnings.jsonl</button>
      <span id="download-status" class="dim"></span>
    </div>
    {''.join(sections) if sections else '<p class="dim">No missing fields — every component has all five documentation fields authored.</p>'}
    <script>{js}</script>
    """
    return page("Fill the gaps", "fill-gaps", body)

def render_prose(text):
    """Designer-authored prose -> HTML.

    Escapes everything first, then applies a deliberately tiny markup vocabulary on top:
    a blank line starts a paragraph, `backticks` set monospace, **stars** set bold. Because
    escaping happens before any of that, authored copy can never inject markup into the page.
    YAML folded scalars (`>`) collapse wrapped lines and leave a single newline where the
    author left a blank line, so paragraphs split on runs of newlines.
    """
    if not text:
        return ""
    out = []
    for block in re.split(r"\n+", str(text).strip()):
        block = block.strip()
        if not block:
            continue
        block = E(block)
        block = re.sub(r"`([^`]+)`", r"<code>\1</code>", block)
        block = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", block)
        out.append(f"<p>{block}</p>")
    return "".join(out)

def render_chip(c):
    tag = "a" if c.get("href") else "span"
    href_attr = f' href="{c["href"]}"' if c.get("href") else ""
    return f'<{tag} class="entry-where"{href_attr}>{E(c["label"])}</{tag}>'

def render_entry_list(items, empty_msg, marker_cls=""):
    """A titled/detailed row with 0+ linked location chips on the right — the shape shared by
    the error list and both learning lists. `items` are dicts with title, detail, and chips
    (a list of {label, href}; href None renders a bare span, for a place with nowhere to link)."""
    if not items:
        return f'<p class="entrylist-empty">{E(empty_msg)}</p>'
    cls = "entry" + (f" {marker_cls}" if marker_cls else "")
    rows = "".join(
        f'<li class="{cls}"><div class="entry-main">'
        f'<div class="entry-title">{E(i["title"])}</div><div class="entry-detail">{E(i["detail"])}</div></div>'
        f'<div class="entry-chips">{"".join(render_chip(c) for c in i.get("chips", []))}</div>'
        '</li>' for i in items)
    return f'<ul class="entrylist">{rows}</ul>'

FIELD_LABEL = dict(CORE_DOC_FIELDS)

def learning_entry(entry, cid=None):
    """A ledger entry -> the dict render_entry_list expects. On the overview every component a
    learning touches is a chip, so the reader can see the connection at a glance. On a
    component's own page the current component is dropped from its own chip row — the page
    already says which component this is — leaving only the *other* components it connects to,
    if any (a learning that spans two components shows the other one right there as the link)."""
    comps = [c for c in (entry.get("components") or []) if c != cid]
    chips = [{"label": components.get(c, {}).get("name", c).strip() if c in components else c,
              "href": f"components/{c}.html" if cid is None else f"{c}.html"} for c in comps]
    if entry.get("kind") == "field_contribution":
        field_label = FIELD_LABEL.get(entry.get("field"), entry.get("field", "a field"))
        return {"title": f'{field_label} — contributed', "detail": entry.get("contributed_text") or "", "chips": chips}
    return {"title": entry.get("proposed_rule") or entry.get("user_correction") or "(no rule text logged)",
            "detail": entry.get("user_correction") or "", "chips": chips}

# ----------------------------------------------------------------- overview + graph
def overview_page():
    # Every open problem in the library, each carrying the place it lives so the card can
    # point straight at it. Collected per component so nothing is reported without a location.
    issues = []
    if control_panel_missing:
        issues.append({"chips": [{"label": "Repository root", "href": None}],
                       "title": "CONTROL_PANEL.md is missing",
                       "detail": "The screen-state panel rulebook is designer-provided and has not been supplied (INGESTION_REPORT.md §4)."})
    for cid in order:
        cname = components[cid]["name"].strip()
        href = f"components/{cid}.html"
        if doc_status[cid][2]:
            issues.append({"chips": [{"label": cname, "href": href}],
                           "title": "Authored metadata does not parse as YAML",
                           "detail": "The stored metadata is shown raw on the component page instead of rendered sections."})
        for e in (reg_by_id[cid].get("figma_instance_edges") or []):
            if not e.get("resolved") and not e.get("excluded"):
                issues.append({"chips": [{"label": cname, "href": href}],
                               "title": "Figma reference points outside the ingested library page",
                               "detail": f'References {e.get("references", "an unnamed component")} in {e.get("external_location", "another page")}.'})

    n_atoms, n_molecules = len(by_type.get("atom", [])), len(by_type.get("molecule", []))
    n_organisms, n_complex = len(by_type.get("organism", [])), len(by_type.get("complex-organism", []))
    n_total = len(order)
    breakdown = [("Atoms", n_atoms, "var(--atom)"), ("Molecules", n_molecules, "var(--molecule)"),
                 ("Organisms", n_organisms, "var(--organism)"), ("Complex organisms", n_complex, "var(--complex)")]
    kpi_html = "".join(
        f'<div class="kpi"><div class="kpi-value">{v}</div><div class="kpi-label">{E(label)}</div></div>'
        for label, v, _ in breakdown)
    propbar_html = "".join(
        f'<div class="propbar-seg" style="flex:{max(v,1)};background:{color}" '
        f'title="{E(label)} — {v} ({(v/n_total*100 if n_total else 0):.0f}%)"></div>'
        for label, v, color in breakdown if v)

    FIELD_ICON = ('<svg viewBox="0 0 16 16" fill="none" aria-hidden="true">'
                  '<rect x="2.5" y="1.5" width="11" height="13" rx="2" stroke="currentColor" stroke-width="1.3"/>'
                  '<path d="M5 5.5h6M5 8h6M5 10.5h3.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>')
    CHECK_ICON = ('<svg viewBox="0 0 14 14" fill="none" aria-hidden="true">'
                  '<path d="M3 7.3l2.6 2.6L11 4.5" stroke="currentColor" stroke-width="1.6" '
                  'stroke-linecap="round" stroke-linejoin="round"/></svg>')
    WARN_ICON = ('<svg viewBox="0 0 14 14" fill="none" aria-hidden="true"><circle cx="7" cy="7" r="5.5" '
                'stroke="currentColor" stroke-width="1.3"/><path d="M7 4.2v3.4" stroke="currentColor" '
                'stroke-width="1.3" stroke-linecap="round"/><circle cx="7" cy="9.6" r=".75" fill="currentColor"/></svg>')
    PENCIL_ICON = ('<svg viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M9.5 2.5l2 2-6.5 6.5-2.4.4.4-2.4z" '
                   'stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>')

    field_rows = sorted(((key, label, field_coverage[key], len(order)) for key, label in CORE_DOC_FIELDS),
                        key=lambda r: -r[2])
    def field_row_html(key, label, n, total):
        gap = missing_by_field[key]
        if gap:
            status = f'<span class="fieldstatus fieldstatus-incomplete">Incomplete {WARN_ICON}</span>'
            action = f'<a class="fieldedit" href="fill-gaps.html#gap-{E(key)}">Edit {PENCIL_ICON}</a>'
        else:
            status = f'<span class="fieldstatus fieldstatus-complete">Complete {CHECK_ICON}</span>'
            action = '<span class="fielddash">—</span>'
        return f'''
      <div class="fieldrow">
        <span class="fieldicon">{FIELD_ICON}</span>
        <span class="fieldlabel">{E(label)}</span>
        <span class="fieldfrac">{n} / {total}</span>
        {status}
        <span class="fieldaction">{action}</span>
      </div>'''
    meters_html = f'<div class="fieldlist">{"".join(field_row_html(key, label, n, total) for key, label, n, total in field_rows)}</div>'

    ref_pct = (ref_resolved / ref_total * 100) if ref_total else 100
    dangling_tile_cls = "kpi kpi-warn" if ref_dangling else "kpi"
    split_html = ""
    if total_relationships:
        struct_pct = total_structural / total_relationships * 100
        split_html = (f'<div class="propbar splitbar"><div class="propbar-seg" style="flex:{total_structural or 1};background:var(--ink3)" '
                      f'title="Structural (is built from) — {total_structural}"></div>'
                      f'<div class="propbar-seg" style="flex:{total_behavioral or 1};background:var(--plum)" '
                      f'title="Behavioral — {total_behavioral}"></div></div>'
                      f'<div class="ov-legend"><span><span class="ov-sw" style="background:var(--ink3)"></span>Structural (built from) <b>{total_structural}</b></span>'
                      f'<span><span class="ov-sw" style="background:var(--plum)"></span>Behavioral <b>{total_behavioral}</b></span></div>')

    # Two peer cards sitting side by side. Both are plain <details>, so they open with no JS;
    # an open card takes the whole row (grid-column:1/-1) so its contents get the full width.
    ov_sections = "".join(
        f'<section class="ovsec"><h3>{E(s.get("heading", ""))}</h3>{render_prose(s.get("body"))}</section>'
        for s in (overview_copy.get("sections") or []) if s.get("heading") or s.get("body"))
    doc_card = ""
    if ov_sections:
        label = overview_copy.get("expand_label") or "How this system works"
        doc_card = (f'<details class="ovcard"><summary><span class="ovcard-head">'
                    f'<span class="ovcard-title">{E(label)}</span>'
                    f'<span class="ovcard-sub">Rules and usage for the library</span></span>'
                    f'<span class="ovchev" aria-hidden="true"></span></summary>'
                    f'<div class="ovcard-body">{ov_sections}</div></details>')

    # Agent learnings — see AGENT.md §6. Confirmed entries are guidance the agent now applies;
    # pending ones are unvalidated corrections a designer hasn't reviewed yet. Both are shown —
    # this section is the audit trail for what the agent has actually learned, not a score.
    n_confirmed, n_pending, n_rejected = len(learnings_confirmed), len(learnings_pending), len(learnings_rejected)
    pending_tile_cls = "kpi kpi-warn" if n_pending else "kpi"
    learnings_section = f'''
      <h4 class="subhead">Agent learnings <span class="dim">— corrections the agent has absorbed, and what is still pending review</span></h4>
      <div class="kpirow">
        <div class="kpi"><div class="kpi-value">{n_confirmed}</div><div class="kpi-label">Confirmed — applied as guidance</div></div>
        <div class="kpi"><div class="kpi-value">{n_rejected}</div><div class="kpi-label">Reviewed and rejected</div></div>
        <div class="{pending_tile_cls}"><div class="kpi-value">{n_pending}</div><div class="kpi-label">Pending review</div></div>
      </div>
      <div class="subhead" style="margin:22px 0 10px">Confirmed</div>
      {render_entry_list([learning_entry(e) for e in learnings_confirmed], "No learnings confirmed yet.", "entry-learned")}
      <div class="subhead" style="margin:22px 0 10px">Pending review</div>
      {render_entry_list([learning_entry(e) for e in learnings_pending], "Nothing awaiting review.", "entry-pending")}
    '''

    n_issues = len(issues)
    issue_word = "error" if n_issues == 1 else "errors"
    if n_issues:
        issue_card = (f'<details class="ovcard ovcard-issue"><summary><span class="ovcard-head">'
                      f'<span class="ovcard-title">{n_issues} {issue_word}</span>'
                      f'<span class="ovcard-sub">Open problems, and where each one lives</span></span>'
                      f'<span class="ovchev" aria-hidden="true"></span></summary>'
                      f'<div class="ovcard-body">{render_entry_list(issues, "")}</div></details>')
    else:
        issue_card = ('<div class="ovcard ovcard-clean"><div class="ovcard-head">'
                      '<span class="ovcard-title">0 errors</span>'
                      '<span class="ovcard-sub">Every component parses and every reference resolves</span>'
                      '</div></div>')

    body = f"""
    <header class="landing">
      <h1>{E(overview_copy.get("title") or "Design System")}</h1>
      <div class="ovcards">{doc_card}{issue_card}</div>
    </header>

    <section class="metasection">
      <h3 class="sec-title">Library at a glance</h3>
      <div class="hero"><div class="hero-value">{n_total}</div><div class="hero-label">components in the library</div></div>
      <div class="kpirow">{kpi_html}</div>
      <div class="propbar">{propbar_html}</div>
    </section>

    <section class="metasection">
      <h3 class="sec-title">System understanding</h3>
      <p class="dim">What the library actually knows about itself right now — computed fresh from the repo on every
      build, not a fixed score.</p>

      {meters_html}

      <h4 class="subhead">Reference integrity <span class="dim">— every Figma instance reference, reviewed</span></h4>
      <div class="kpirow">
        <div class="kpi"><div class="kpi-value">{ref_resolved}</div><div class="kpi-label">Resolved to a real in-page component</div></div>
        <div class="kpi"><div class="kpi-value">{ref_excluded}</div><div class="kpi-label">Reviewed and confirmed not a dependency</div></div>
        <div class="{dangling_tile_cls}"><div class="kpi-value">{ref_dangling}</div><div class="kpi-label">Still dangling</div></div>
      </div>
      <p class="dim">{ref_total} Figma instance references tracked across the library; {ref_pct:.0f}% resolve to a
      component that exists in the ingested page (see <a href="../INGESTION_REPORT.md">INGESTION_REPORT.md §5</a>).</p>

      <h4 class="subhead">Relationship density <span class="dim">— how much of the graph is actually wired</span></h4>
      <div class="kpirow">
        <div class="kpi"><div class="kpi-value">{total_relationships}</div><div class="kpi-label">Relationships mapped</div></div>
        <div class="kpi"><div class="kpi-value">{avg_connections:.1f}</div><div class="kpi-label">Avg. connections per component</div></div>
      </div>
      {split_html}
      <div class="quicklinks"><a class="btn" href="graph.html">Open the component graph →</a></div>

      {learnings_section}
    </section>

    """
    return page("Overview", "overview", body)

# The Component graph page (dashboard/graph.html) and graph/graph.json are generated
# by scripts/build_graph.py (Phase 3), invoked from main() so a dashboard rebuild
# always regenerates the graph from the same registry state.

# ----------------------------------------------------------------- assets
STYLE = """
/* Noise Audio DLS dashboard — dark-first, minimal, hairline-bordered.
   Near-black canvas with recessed surfaces, a single restrained violet accent for
   interactive state, and taxonomy carried by small colour dots rather than loud
   badges. Light theme is a full override on [data-theme=light], not an inversion. */
:root{
  --canvas:#0b0b0c; --surface:#141416; --surface-2:#1b1b1e; --surface-3:#232326;
  --line:#28282b; --line-2:#323236; --line-soft:#1e1e21;
  --ink:#ededef; --ink2:#a1a1a6; --ink3:#6e6e73;
  --accent:#a78bfa; --accent-2:#8b6df5; --accent-soft:#2a2340;
  --stage:#e9e9ec; --stage-grid:#dededf;
  --atom:#35c97f; --molecule:#d6a23c; --organism:#e0604c; --complex:#a8443a; --plum:#a78bfa;
  --warn-bg:#26200f; --warn-line:#5c4a1c; --warn-ink:#e0b341;
  --good-bg:#122a1c; --good-line:#1f5c39; --good-ink:#4ade80;
  --font:'Inter',-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
  --font-mono:'Roboto Mono',ui-monospace,'SF Mono',monospace;
  --r-xs:6px; --r-sm:8px; --r-md:12px; --r-lg:16px; --r-xl:20px; --r-pill:9999px;
}
html[data-theme=light]{
  --canvas:#fbfbfc; --surface:#ffffff; --surface-2:#f5f5f7; --surface-3:#ededf0;
  --line:#e4e4e7; --line-2:#d4d4d8; --line-soft:#f0f0f2;
  --ink:#131315; --ink2:#5c5c63; --ink3:#8e8e96;
  --accent:#6d4aff; --accent-2:#5a35f5; --accent-soft:#efeaff;
  --stage:#f4f4f6; --stage-grid:#e8e8ea;
  --atom:#1c7a45; --molecule:#9c6a1f; --organism:#b3261e; --complex:#6b1414; --plum:#6d4aff;
  --warn-bg:#fff9ec; --warn-line:#e3cb96; --warn-ink:#8a6414;
  --good-bg:#eafbf1; --good-line:#a8dfc0; --good-ink:#1c7a45;
}
*{box-sizing:border-box}
html{background:var(--canvas)}
body{margin:0;font-family:var(--font);background:var(--canvas);color:var(--ink);
  font-size:14px;line-height:1.55;-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}
h1,h2,h3,h4{font-weight:600;letter-spacing:-0.018em;margin:0}
a{color:inherit;text-decoration:none}
code{font-family:var(--font-mono);font-size:.92em}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}

/* ---------------------------------------------------------------- shell */
.layout{display:flex;min-height:100vh}
.sidebar{width:262px;flex:none;background:var(--surface);border-right:1px solid var(--line);
  padding:16px 12px 32px;position:sticky;top:0;height:100vh;overflow-y:auto}
/* No visible scrollbars anywhere inside the app. These containers still scroll — the bar
   itself is just never painted, so panels never grow a track down their edge. */
.sidebar,.ovcard-body,.pv-stage,.codeblock,.graphwrap,.rawyaml pre,.overviewdoc-body{
  scrollbar-width:none;-ms-overflow-style:none}
.sidebar::-webkit-scrollbar,.ovcard-body::-webkit-scrollbar,.pv-stage::-webkit-scrollbar,
.codeblock::-webkit-scrollbar,.graphwrap::-webkit-scrollbar,.rawyaml pre::-webkit-scrollbar{
  width:0;height:0;display:none}
.brand{display:flex;gap:10px;align-items:center;margin:2px 4px 20px}
.applogo{width:30px;height:30px;flex:none;border-radius:var(--r-sm);background:var(--ink);color:var(--canvas);
  display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px}
.brandname{flex:1;font-weight:600;font-size:13.5px;letter-spacing:-0.01em}
.themetoggle{width:30px;height:30px;flex:none;border-radius:var(--r-sm);border:1px solid var(--line);
  background:var(--surface-2);color:var(--ink2);cursor:pointer;display:flex;align-items:center;
  justify-content:center;padding:0;transition:color .15s,border-color .15s}
.themetoggle:hover{color:var(--ink);border-color:var(--line-2)}
.themetoggle svg{width:15px;height:15px}
.navgroup{margin:20px 8px 7px;font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink3);font-weight:600;display:flex;align-items:center;gap:7px}
.navgroup .count{background:none;color:var(--ink3);padding:0;font-size:10.5px;opacity:.75}
.navitem{display:flex;align-items:center;gap:9px;padding:7px 10px;border-radius:var(--r-sm);
  color:var(--ink2);font-size:13px;transition:background .13s,color .13s}
.navitem:hover{background:var(--surface-2);color:var(--ink)}
.navitem.active{background:var(--surface-3);color:var(--ink);font-weight:500}
.navitem.pill{background:var(--surface-2);margin-bottom:3px}
.navitem.pill:hover{background:var(--surface-3)}
.navitem.pill.active{background:var(--surface-3);box-shadow:inset 0 0 0 1px var(--line-2)}
.navdot{width:6px;height:6px;flex:none;border-radius:50%;background:var(--ink3)}
.navitem .count{margin-left:auto;color:var(--ink3);font-size:11px;font-variant-numeric:tabular-nums}
.navlabel{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.main{flex:1;min-width:0;padding:36px 44px 64px;max-width:1180px}

/* ---------------------------------------------------------------- headers */
.pagehead{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:baseline;margin-bottom:6px}
.pagehead h1{font-size:26px}
.landing h1{font-size:40px;letter-spacing:-0.03em;line-height:1.1}
.tagline{color:var(--ink2);max-width:620px;font-size:15px;margin:14px 0 0}
/* Designer-authored front-page cards: two peers side by side, each the full width of a
   column. Opening one gives it the whole row, and :has() collapses the grid to one column
   so the sibling matches its width instead of being left as a stranded half-card. */
.ovcards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:28px 0 0}
.ovcards:has(.ovcard[open]){grid-template-columns:minmax(0,1fr)}
@media (max-width:900px){.ovcards{grid-template-columns:minmax(0,1fr)}}
.ovcard{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);
  transition:border-color .15s}
.ovcard:hover,.ovcard[open]{border-color:var(--line-2)}
.ovcard[open]{grid-column:1/-1}
.ovcard>summary{cursor:pointer;list-style:none;display:flex;align-items:center;gap:14px;
  padding:22px;border-radius:var(--r-lg);transition:background .14s}
.ovcard>summary::-webkit-details-marker{display:none}
.ovcard>summary:hover{background:var(--surface-2)}
.ovcard-head{flex:1;min-width:0;display:flex;flex-direction:column;gap:5px}
.ovcard-title{font-size:16px;font-weight:600;letter-spacing:-0.01em;color:var(--ink)}
.ovcard-sub{font-size:12.5px;color:var(--ink3);line-height:1.45}
.ovchev{width:0;height:0;flex:none;border-left:5px solid var(--ink3);
  border-top:4px solid transparent;border-bottom:4px solid transparent;transition:transform .18s}
.ovcard[open]>summary{border-bottom:1px solid var(--line);border-radius:var(--r-lg) var(--r-lg) 0 0}
.ovcard[open]>summary .ovchev{transform:rotate(90deg)}
.ovcard-clean{padding:22px}
.ovcard-issue .ovcard-title{color:var(--warn-ink)}
.entrylist{list-style:none;padding:0;margin:0;grid-column:1/-1}
.entrylist-empty{color:var(--ink3);font-size:13px;margin:4px 0 0;grid-column:1/-1}
.entry{display:flex;gap:18px;align-items:baseline;justify-content:space-between;
  padding:15px 0;border-bottom:1px solid var(--line-soft)}
.entry:last-child{border-bottom:none;padding-bottom:2px}
.entry-main{min-width:0}
.entry-title{font-size:13.5px;font-weight:500;color:var(--ink)}
.entry-detail{font-size:12.5px;color:var(--ink3);margin-top:3px;line-height:1.5}
.entry-chips{flex:none;display:flex;flex-wrap:wrap;gap:6px;justify-content:flex-end;max-width:40%}
.entry-where{font-size:11.5px;font-family:var(--font-mono);color:var(--ink2);
  background:var(--surface-2);border:1px solid var(--line);border-radius:var(--r-pill);padding:4px 12px}
a.entry-where{color:var(--accent)}
a.entry-where:hover{border-color:var(--accent)}
.entry-learned .entry-title::before{content:"! ";color:var(--accent);font-weight:700}
.entry-pending .entry-title::before{content:"○ ";color:var(--ink3)}
/* Sections lay out as whole blocks in a grid, not a single edge-to-edge column: at this
   card's width a full-bleed paragraph would run 150+ characters per line, which is
   established to hurt reading comprehension well before it gets that wide (the
   comfortable range is roughly 60-90 characters). A multi-column grid of sections uses
   the width the wide card actually has without stretching any one paragraph past that. */
.ovcard-body{padding:4px 22px 22px;display:grid;
  grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:4px 48px;align-items:start}
.ovsec{padding:16px 0;border-bottom:1px solid var(--line-soft)}
.ovsec:last-child{border-bottom:none;padding-bottom:2px}
.ovsec h3{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--ink3);margin:0 0 8px}
.ovsec p{color:var(--ink2);font-size:14px;line-height:1.65;margin:0 0 10px}
.ovsec p:last-child{margin-bottom:0}
.ovsec strong{color:var(--ink);font-weight:600}
.ovsec code{background:var(--surface-2);border-radius:4px;padding:1px 5px;font-size:12px;color:var(--ink)}
@media (prefers-reduced-motion:reduce){.ovchev{transition:none}}
.subtle{color:var(--ink3);font-size:12.5px;margin:6px 0 0}
.dim{color:var(--ink3);font-size:12.5px;font-weight:400}
.rel{color:var(--ink3);font-size:12px}
.subhead{font-size:12px;font-weight:600;color:var(--ink2);margin:26px 0 12px;
  letter-spacing:.04em;text-transform:uppercase}
.subhead:first-of-type{margin-top:2px}
.subhead .dim{text-transform:none;letter-spacing:0;font-weight:400;margin-left:4px}
h2{font-size:19px;margin:36px 0 14px;display:flex;align-items:baseline;gap:9px}
h2 .count{color:var(--ink3);font-size:12.5px;font-weight:400;font-variant-numeric:tabular-nums}

/* ---------------------------------------------------------------- surfaces */
.panel,.metasection,.idsblock{background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r-lg);padding:20px 22px;margin:14px 0}
.panel h3,.metasection h3,.idsblock h3{font-size:14px;margin:0 0 14px;letter-spacing:-0.005em}
.metasection h3.sec-title{font-size:19px;letter-spacing:-0.01em;margin-bottom:16px}
.metaheader{margin-top:40px}

/* ---------------------------------------------------------------- controls */
.quicklinks{display:flex;gap:8px;flex-wrap:wrap;margin:20px 0 0}
.btn{display:inline-flex;align-items:center;gap:7px;background:var(--surface-2);
  border:1px solid var(--line);border-radius:var(--r-pill);padding:8px 16px;font-size:13px;
  color:var(--ink2);font-family:inherit;cursor:pointer;transition:color .14s,border-color .14s,background .14s}
.btn:hover{color:var(--ink);border-color:var(--line-2);background:var(--surface-3)}
.btn:active{transform:scale(.975)}
.btn-primary{background:var(--ink);color:var(--canvas);border-color:var(--ink)}
.btn-primary:hover{background:var(--ink);color:var(--canvas);opacity:.88}
.btn:disabled{opacity:.45;cursor:not-allowed;transform:none}
.btn:disabled:hover{background:var(--ink);border-color:var(--ink);color:var(--canvas)}
.gaprow{background:var(--surface-2);border:1px solid var(--line);border-radius:var(--r-md);
  padding:14px 16px;margin:0 0 10px;transition:border-color .15s}
.gaprow:last-child{margin-bottom:0}
.gaprow-filled{border-color:var(--accent)}
.gaprow-head{display:flex;align-items:baseline;gap:9px;margin-bottom:9px;font-size:13.5px;font-weight:500}
.gaprow-head a{color:var(--accent)}
.gaprow textarea{width:100%;background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r-sm);padding:9px 11px;font:inherit;font-size:13px;color:var(--ink);
  resize:vertical;box-sizing:border-box}
.gaprow textarea:focus{outline:none;border-color:var(--accent)}
.gaprow .gapcopybtn{margin-top:8px}
.pills{display:flex;gap:6px;flex-wrap:wrap;margin:14px 0 0}
.pill{background:var(--surface-2);border:1px solid var(--line);border-radius:var(--r-pill);
  padding:4px 11px;font-size:12px;color:var(--ink2)}
.copybtn,.gapcopybtn{border:1px solid var(--line);background:var(--surface-2);color:var(--ink3);
  border-radius:var(--r-xs);padding:3px 8px;cursor:pointer;font:inherit;font-size:11px;
  transition:color .14s,border-color .14s}
.copybtn:hover,.gapcopybtn:hover{color:var(--ink);border-color:var(--line-2)}
.copybtn:active,.gapcopybtn:active{transform:scale(.94)}
.copybtn.copied,.gapcopybtn.copied{background:var(--accent);color:#fff;border-color:var(--accent)}
.copybtn.small,.gapcopybtn.small{padding:2px 6px}

/* ---------------------------------------------------------------- taxonomy */
.typebadge{display:inline-flex;align-items:center;gap:6px;border-radius:var(--r-pill);
  padding:3px 10px 3px 8px;font-size:11.5px;color:var(--ink2);background:var(--surface-2);
  border:1px solid var(--line)}
.typebadge::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.t-atom{color:var(--atom)}.t-molecule{color:var(--molecule)}
.t-organism{color:var(--organism)}.t-complex-organism{color:var(--complex)}
.d-atom{background:var(--atom)}.d-molecule{background:var(--molecule)}
.d-organism{background:var(--organism)}.d-complex-organism{background:var(--complex)}
.warnbadge{background:var(--warn-bg);border:1px solid var(--warn-line);color:var(--warn-ink);
  border-radius:var(--r-pill);padding:0 6px;font-size:10px}
.docbadge{color:var(--ink3);font-size:11px;font-variant-numeric:tabular-nums}
.docbadge-low{color:var(--warn-ink)}

/* ---------------------------------------------------------------- cards */
.cardgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(238px,1fr));gap:12px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);
  padding:18px;display:flex;flex-direction:column;gap:3px;position:relative;
  transition:border-color .15s,background .15s,transform .15s}
.card:hover{border-color:var(--line-2);background:var(--surface-2);transform:translateY(-2px)}
.cardname{font-weight:600;font-size:14.5px;letter-spacing:-0.008em;display:flex;
  align-items:center;gap:8px;padding-right:18px}
.cardid{color:var(--ink3);font-size:11.5px;font-family:var(--font-mono)}
.cardmeta{margin-top:14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.cardarrow{position:absolute;top:18px;right:18px;color:var(--ink3);opacity:0;
  transition:opacity .15s,transform .15s}
.card:hover .cardarrow{opacity:1;transform:translateX(2px)}

/* ---------------------------------------------------------------- figures */
.hero{margin:2px 0 22px}
.hero-value{font-size:54px;font-weight:600;letter-spacing:-0.035em;line-height:1}
.hero-label{color:var(--ink3);font-size:13px;margin-top:6px}
.kpirow{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}
.kpi{background:var(--surface-2);border:1px solid var(--line);border-radius:var(--r-md);
  padding:14px 16px;flex:1;min-width:152px}
.kpi-value{font-size:24px;font-weight:600;letter-spacing:-0.02em;font-variant-numeric:tabular-nums;line-height:1.2}
.kpi-label{color:var(--ink3);font-size:11.5px;margin-top:4px;line-height:1.4}
.kpi-warn{background:var(--warn-bg);border-color:var(--warn-line)}
.kpi-warn .kpi-value{color:var(--warn-ink)}
.propbar{display:flex;gap:2px;height:8px;border-radius:var(--r-pill);overflow:hidden;
  background:var(--surface-3);margin:18px 0 12px}
.propbar-seg{min-width:3px}
.propbar.splitbar{margin-top:14px}
.ov-legend{display:flex;gap:18px;flex-wrap:wrap;font-size:12.5px;color:var(--ink2)}
.ov-legend .ov-sw{display:inline-block;width:7px;height:7px;border-radius:50%;
  vertical-align:1px;margin-right:7px}
.ov-legend b{color:var(--ink);font-weight:600;margin-left:4px;font-variant-numeric:tabular-nums}
.fieldlist{border:1px solid var(--line);border-radius:var(--r-md);overflow:hidden}
.fieldrow{display:grid;grid-template-columns:22px 1fr 72px 128px 76px;align-items:center;
  gap:14px;padding:11px 14px;background:var(--surface-2);border-bottom:1px solid var(--line)}
.fieldrow:last-child{border-bottom:none}
.fieldicon{width:22px;height:22px;border-radius:var(--r-xs);background:var(--accent-soft);
  color:var(--accent);display:flex;align-items:center;justify-content:center;flex:none}
.fieldicon svg{width:13px;height:13px}
.fieldlabel{font-size:13px;color:var(--ink);font-weight:500}
.fieldfrac{font-size:12.5px;color:var(--ink2);font-variant-numeric:tabular-nums;
  font-family:var(--font-mono);text-align:center}
.fieldstatus{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:500;
  border-radius:var(--r-pill);padding:4px 11px;width:fit-content}
.fieldstatus svg{width:11px;height:11px}
.fieldstatus-complete{background:var(--good-bg);color:var(--good-ink)}
.fieldstatus-incomplete{background:var(--warn-bg);color:var(--warn-ink)}
.fieldaction{text-align:right}
.fielddash{color:var(--ink3)}
.fieldedit{display:inline-flex;align-items:center;gap:5px;font-size:12px;color:var(--accent);
  border:1px solid var(--line-2);border-radius:var(--r-pill);padding:4px 12px;transition:border-color .14s,background .14s}
.fieldedit:hover{border-color:var(--accent);background:var(--accent-soft)}
.fieldedit svg{width:10px;height:10px}
@media (max-width:640px){.fieldrow{grid-template-columns:22px 1fr auto;row-gap:8px}
  .fieldstatus,.fieldaction{grid-column:2/4}}
.codeblock{background:var(--canvas);border:1px solid var(--line);border-radius:var(--r-md);
  padding:14px 16px;font-family:var(--font-mono);font-size:11.5px;line-height:1.7;
  overflow-x:auto;white-space:pre;margin:10px 0 0;color:var(--ink2)}

/* ---------------------------------------------------------------- component detail */
.detailgrid{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:14px;align-items:start;margin-top:18px}
@media (max-width:1080px){.detailgrid{grid-template-columns:minmax(0,1fr)}}
.stagecard{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);padding:14px}
.rail{display:flex;flex-direction:column;gap:14px;position:sticky;top:24px}
.railcard{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);padding:18px 20px}
.railcard h3{font-size:13px;margin:0 0 14px}
.proprow{display:flex;justify-content:space-between;align-items:baseline;gap:14px;
  padding:8px 0;border-bottom:1px solid var(--line-soft)}
.proprow:last-child{border-bottom:none;padding-bottom:0}
.proprow:first-of-type{padding-top:0}
.propkey{color:var(--ink2);font-size:12.5px;flex:none}
.propval{font-family:var(--font-mono);font-size:11.5px;color:var(--ink);text-align:right;
  overflow-wrap:anywhere;display:flex;flex-wrap:wrap;gap:4px;justify-content:flex-end}
.propval .sep{color:var(--ink3)}
.propval .tok{background:var(--surface-2);border-radius:4px;padding:1px 6px}
.idrow{display:flex;align-items:center;gap:8px;margin:9px 0}
.idlabel{width:96px;color:var(--ink3);font-size:12px;flex:none}
.idvalue{flex:1;min-width:0;background:var(--surface-2);border:1px solid var(--line);
  border-radius:var(--r-xs);padding:5px 9px;font-family:var(--font-mono);font-size:11px;
  overflow-wrap:anywhere;color:var(--ink2)}

/* ---------------------------------------------------------------- preview stage */
.pv-caption{color:var(--ink3);font-size:12px;margin:0 0 14px}
.pv-block{margin:0 0 12px}
.pv-block:last-child{margin-bottom:0}
.pv-variantname{font-size:11px;font-weight:500;margin:0 0 7px 2px;color:var(--ink2);
  font-family:var(--font-mono);display:flex;gap:8px;align-items:baseline}
.pv-stage{background:var(--stage);border-radius:var(--r-md);padding:28px 24px;overflow-x:auto;
  display:flex;justify-content:center}
.pv-scale{transform-origin:top left}
.pv-frame{flex:none}
.pv-frame[data-stack="1"]{display:flex;align-items:center;justify-content:center}
.pv-frame[data-stack="1"]>*{position:absolute}
.pv-text{display:block;flex:none;overflow:hidden}
.pv-shape{display:block;flex:none;min-width:2px;min-height:2px}
.pv-shape:not([style*="background"]):not([style*="border"]){background:#d4d4d8;border-radius:2px}
.pv-instance{display:flex;flex:none;align-items:center;justify-content:center;
  outline:1px dashed #9c87d6;outline-offset:-1px;border-radius:5px;overflow:hidden}
.pv-instance-label{font-size:9.5px;background:rgba(140,110,220,.13);border-radius:3px;padding:1px 5px;
  max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#6b4fb8}
.pv-instance-label a{color:#6b4fb8}
.pv-unresolved{color:#8a6414}
.pv-note{font-size:10.5px;color:#8e8e96;padding:4px}

/* ---------------------------------------------------------------- swatches */
.swatchgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(168px,1fr));gap:10px;margin-bottom:8px}
.swatchcard{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-md);
  overflow:hidden;transition:border-color .15s}
.swatchcard:hover{border-color:var(--line-2)}
.swatchfill{height:74px;display:flex;border-bottom:1px solid var(--line)}
.swatchfill span{flex:1;position:relative}
.swatchfill span[data-mode]::after{content:attr(data-mode);position:absolute;left:7px;bottom:5px;
  font-size:9px;font-family:var(--font-mono);color:rgba(128,128,132,.9);letter-spacing:.05em}
.swatchmeta{padding:10px 12px}
.swatchname{font-size:12.5px;font-weight:500;letter-spacing:-0.005em;overflow-wrap:anywhere;line-height:1.35}
.swatchhex{font-family:var(--font-mono);font-size:10.5px;color:var(--ink3);margin-top:2px;
  display:flex;gap:8px;flex-wrap:wrap}
.swatch{display:inline-block;width:16px;height:16px;border-radius:4px;
  border:1px solid var(--line);vertical-align:-3px;margin-right:8px}

/* ---------------------------------------------------------------- tables & lists */
.table{border-collapse:collapse;width:100%;font-size:13px}
.table th{text-align:left;color:var(--ink3);font-weight:500;font-size:11px;
  text-transform:uppercase;letter-spacing:.06em;border-bottom:1px solid var(--line);padding:8px 10px}
.table td{border-bottom:1px solid var(--line-soft);padding:9px 10px;vertical-align:middle;color:var(--ink2)}
.table tr:last-child td{border-bottom:none}
.table code{color:var(--ink);font-size:11.5px}
.fpcell code{font-size:10.5px}
.darkcell{background:var(--surface-2);border-radius:4px}
ul{margin:6px 0;padding-left:20px;color:var(--ink2)}
ul.rules li,ul li{margin:6px 0}
.linklist{list-style:none;padding-left:0}
.linklist li{margin:7px 0;display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}
.linklist a,.comp-block a,.metasection a,.panel a{color:var(--accent)}
.linklist a:hover,.metasection a:hover,.panel a:hover{text-decoration:underline}
.ruleid{background:var(--surface-2);border:1px solid var(--line);border-radius:var(--r-xs);
  padding:1px 6px;font-size:10.5px;font-family:var(--font-mono);color:var(--ink3)}
.kvs{margin:2px 0 2px 2px;border-left:1px solid var(--line);padding-left:12px}
.kv{margin:6px 0}
.kv .k{font-weight:600;font-size:12px;color:var(--ink2)}
.kv .v{margin-left:2px}
.missing{color:var(--warn-ink);font-style:italic}
.warning{background:var(--warn-bg);border:1px solid var(--warn-line);border-radius:var(--r-md);
  padding:12px 16px;margin:14px 0;font-size:13px;color:var(--warn-ink)}
.warning ul{margin:8px 0 0;color:inherit}
.warning a{color:inherit;text-decoration:underline}
.rawyaml{margin-top:16px}
.rawyaml summary{cursor:pointer;color:var(--ink2);font-size:13px}
.rawyaml pre{background:var(--canvas);border:1px solid var(--line);color:var(--ink2);
  border-radius:var(--r-md);padding:16px;overflow:auto;font-size:11.5px;font-family:var(--font-mono)}
.footer{margin-top:56px;padding-top:16px;border-top:1px solid var(--line);
  color:var(--ink3);font-size:11.5px;line-height:1.7}

/* ---------------------------------------------------------------- foundations pages */
.typo-row{display:flex;gap:24px;align-items:center;border-bottom:1px solid var(--line-soft);padding:16px 0}
.typo-row:last-child{border-bottom:none}
.typo-meta{width:340px;flex:none;font-size:12.5px;color:var(--ink2)}
.typo-sample{flex:1;overflow:hidden;white-space:nowrap;color:var(--ink)}
.shadow-sample{width:120px;height:56px;border-radius:var(--r-md);background:var(--surface-3)}
.barviz{display:inline-block;height:8px;background:var(--accent);border-radius:99px;vertical-align:middle}
.radviz{display:inline-block;width:34px;height:34px;border:1.5px solid var(--ink3);vertical-align:middle}

/* ---------------------------------------------------------------- graph */
.graphwrap{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);
  padding:10px;overflow:hidden;position:relative;height:min(76vh,740px)}
.graph{width:100%;min-width:900px}
.g-col{font-size:13px;font-weight:600;fill:var(--ink2)}
.g-node{fill:var(--surface);stroke:var(--line)}
.g-node.t-atom{stroke:var(--atom)}.g-node.t-molecule{stroke:var(--molecule)}
.g-node.t-organism{stroke:var(--organism)}.g-node.t-complex-organism{stroke:var(--complex)}
.g-label{font-size:10.5px;text-anchor:middle;fill:var(--ink)}
.g-edge{fill:none;stroke:var(--line-2);stroke-width:1.2;opacity:.75}
.g-beh{stroke-dasharray:4 3;stroke:var(--plum);opacity:.55}
"""

APPJS = """
document.addEventListener('click', function (ev) {
  const b = ev.target.closest('.copybtn');
  if (!b) return;
  navigator.clipboard.writeText(b.dataset.copy).then(() => {
    b.classList.add('copied');
    const t = b.textContent; b.textContent = '✓ copied';
    setTimeout(() => { b.classList.remove('copied'); b.textContent = t; }, 1200);
  });
});

// theme toggle — the <head> applies the stored choice before first paint, so this
// only has to flip it and persist. Dark is the default when nothing is stored.
document.addEventListener('click', function (ev) {
  if (!ev.target.closest('#themetoggle')) return;
  const root = document.documentElement;
  const next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
  root.setAttribute('data-theme', next);
  try { localStorage.setItem('na-theme', next); } catch (e) {}
});
"""

# ----------------------------------------------------------------- emit
def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT, "components"))
    os.makedirs(os.path.join(OUT, "assets"))
    with open(os.path.join(OUT, "assets", "style.css"), "w") as f:
        f.write(STYLE)
    with open(os.path.join(OUT, "assets", "app.js"), "w") as f:
        f.write(APPJS)
    pages = {
        "index.html": overview_page(),
        "fill-gaps.html": fill_gaps_page(),
        "foundations-colors.html": colors_page(),
        "foundations-typography.html": typography_page(),
        "foundations-spacing.html": spacing_page(),
    }
    for name, content in pages.items():
        with open(os.path.join(OUT, name), "w") as f:
            f.write(content)
    for cid in order:
        with open(os.path.join(OUT, "components", f"{cid}.html"), "w") as f:
            f.write(component_page(cid))
    print(f"dashboard generated: {len(pages)} shell pages + {len(order)} component pages -> dashboard/")
    import build_graph  # Phase 3 — regenerates dashboard/graph.html + graph/graph.json
    build_graph.main()

if __name__ == "__main__":
    main()
