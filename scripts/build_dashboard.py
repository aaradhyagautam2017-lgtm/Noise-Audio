#!/usr/bin/env python3
"""Phase 2 — Designer Dashboard generator for the Noise Audio DLS repo.

Generates a static, browsable component-library site under dashboard/ in ONE pass,
reading ONLY this repository (components/**.yaml, tokens/*.yaml, registry.yaml).
It never connects to Figma, never invents copy or values, and renders stored
metadata as-is. Re-run it after any repo change to regenerate the site.

Usage:  python3 scripts/build_dashboard.py
"""
import hashlib
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

# Which collapsible sidebar section a given "active" key lives in, so that section
# renders pre-expanded on load -- you should never land on a component's own page and
# find its section collapsed. Root-relative hrefs here; sidebar() prefixes them per page.
SECTION_OF_ACTIVE = {"colors": "foundations", "typography": "foundations", "spacing": "foundations"}
SEARCH_ENTRIES = [
    {"n": "Overview", "h": "index.html", "g": "Nav"},
    {"n": "Component graph", "h": "graph.html", "g": "Nav"},
    {"n": "Fill the gaps", "h": "fill-gaps.html", "g": "Nav"},
    {"n": "Agent Learnings", "h": "learnings.html", "g": "Nav"},
    {"n": "Colors & tokens", "h": "foundations-colors.html", "g": "Foundations"},
    {"n": "Typography", "h": "foundations-typography.html", "g": "Foundations"},
    {"n": "Spacing & radius", "h": "foundations-spacing.html", "g": "Foundations"},
]
for _gname, _ids in group_defs:
    for _cid in _ids:
        SECTION_OF_ACTIVE[f"c-{_cid}"] = _gname.lower()
        SEARCH_ENTRIES.append({"n": components[_cid]["name"].strip(), "h": f"components/{_cid}.html", "g": _gname})

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

def _navsvg(inner, vb=24):
    return (f'<svg viewBox="0 0 {vb} {vb}" fill="none" stroke="currentColor" stroke-width="1.7" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{inner}</svg>')

# Hand-drawn line icons for the sidebar's top-level items and collapsible-section
# headers -- monochrome, sized/coloured entirely via CSS so they follow the same
# hover/active states as the text next to them.
NAV_ICONS = {
    "home": _navsvg('<path d="M4 10.5 12 4l8 6.5"/><path d="M6 9v9.5a1 1 0 0 0 1 1h4v-6h2v6h4a1 1 0 0 0 1-1V9"/>'),
    "graph": _navsvg('<circle cx="6" cy="6" r="2.3"/><circle cx="18" cy="6" r="2.3"/><circle cx="12" cy="18" r="2.3"/>'
                      '<path d="M8 7.3 10.6 15.5M16 7.3 13.4 15.5M8.3 6h7.4"/>'),
    "puzzle": _navsvg('<path d="M9.5 4.5h3a.9.9 0 0 1 .9 1v.9a1.5 1.5 0 1 0 0 3v3.1a.9.9 0 0 1-.9 1h-3.1a1.5 1.5 0 1 0-3 0H5.5a.9.9 0 0 1-.9-1v-3a1.5 1.5 0 1 0 0-3v-3a.9.9 0 0 1 .9-1h.9a1.5 1.5 0 1 0 3-1z"/>'),
    "grid": _navsvg('<rect x="4" y="4" width="7" height="7" rx="1.3"/><rect x="13" y="4" width="7" height="7" rx="1.3"/>'
                     '<rect x="4" y="13" width="7" height="7" rx="1.3"/><rect x="13" y="13" width="7" height="7" rx="1.3"/>'),
    "atom": _navsvg('<circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none"/>'
                     '<ellipse cx="12" cy="12" rx="9" ry="3.6"/>'
                     '<ellipse cx="12" cy="12" rx="9" ry="3.6" transform="rotate(60 12 12)"/>'
                     '<ellipse cx="12" cy="12" rx="9" ry="3.6" transform="rotate(120 12 12)"/>'),
    "hexagon": _navsvg('<path d="M12 3.5 19.5 8v8L12 20.5 4.5 16V8z"/>'),
    "cube": _navsvg('<path d="M12 3.5 20 8v8l-8 4.5-8-4.5V8z"/><path d="M4 8l8 4.5L20 8M12 12.5V21"/>'),
    "search": _navsvg('<circle cx="10.5" cy="10.5" r="6"/><path d="m15 15 5 5"/>'),
    "chevron": _navsvg('<path d="m5 8.5 7 6.5 7-6.5"/>'),
    "learnings": _navsvg('<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.6 10.8c.6.45.9 1.15.9 1.9V16h5.4v-.3c0-.75.3-1.45.9-1.9A6 6 0 0 0 12 3z"/>'),
}

def sidebar(prefix, active):
    def item(href, label, key, count=None, warn=0, dot=None, icon=None):
        # NB: "pill" is deliberately not added as a class here even for dot items --
        # there is an unrelated, pre-existing .pill class (the small key:value badges
        # on a component page, e.g. "reusable: True") that a shared class name would
        # silently pull in, which is exactly what happened before this comment existed.
        cls = "navitem"
        if key == active:
            cls += " active"
        if dot:
            marker = f'<span class="navdot d-{dot}"></span>'
        elif icon:
            marker = f'<span class="navicon">{icon}</span>'
        else:
            marker = ""
        badge = f'<span class="count">{count}</span>' if count is not None else ""
        wbadge = f'<span class="warnbadge" title="dangling Figma references">{warn}</span>' if warn else ""
        return (f'<a class="{cls}" href="{prefix}{href}">{marker}'
                f'<span class="navlabel">{E(label)}</span>{badge}{wbadge}</a>')

    def section(key, label, icon, items):
        # Pre-expanded only when it contains the active page, so you're never dropped
        # onto a component's page with its own section collapsed. app.js restores any
        # other section the visitor had previously left open, and never re-collapses
        # this one regardless of that stored preference (see the "forced" flag).
        forced_open = SECTION_OF_ACTIVE.get(active) == key
        openattr = " open" if forced_open else ""
        return (f'<details class="navsection" data-key="{key}" data-forced="{"1" if forced_open else "0"}"{openattr}>'
                f'<summary><span class="navsecicon">{icon}</span>'
                f'<span class="navseclabel">{E(label)}</span>'
                f'<span class="count">{len(items)}</span>'
                f'<span class="navchevron">{NAV_ICONS["chevron"]}</span></summary>'
                f'<div class="navsectionbody">{"".join(items)}</div></details>')

    parts = [f'''
    <aside class="sidebar">
      <div class="brand">
        <span class="applogo">N</span>
        <span class="brandname">{E(registry["app"])}</span>
        <button class="themetoggle" type="button" id="themetoggle" title="Toggle light / dark"
                aria-label="Toggle light or dark theme">{THEME_ICON}</button>
      </div>
      <nav class="navtop">
        {item("index.html", "Overview", "overview", icon=NAV_ICONS["home"])}
        {item("graph.html", "Component graph", "graph", icon=NAV_ICONS["graph"])}
        {item("fill-gaps.html", "Fill the gaps", "fill-gaps", icon=NAV_ICONS["puzzle"])}
        {item("learnings.html", "Agent Learnings", "learnings", icon=NAV_ICONS["learnings"])}
      </nav>
      <div class="navscroll">
    ''']
    parts.append(section("foundations", "Foundations", NAV_ICONS["grid"], [
        item("foundations-colors.html", "Colors & tokens", "colors"),
        item("foundations-typography.html", "Typography", "typography"),
        item("foundations-spacing.html", "Spacing & radius", "spacing"),
    ]))
    group_icon = {"Atoms": NAV_ICONS["atom"], "Molecules": NAV_ICONS["hexagon"], "Organisms": NAV_ICONS["cube"]}
    for gname, ids in group_defs:
        entries = []
        for cid in ids:
            dangling = sum(1 for e in reg_by_id[cid].get("figma_instance_edges", []) or [] if not e["resolved"] and not e.get("excluded"))
            entries.append(item(f"components/{cid}.html", components[cid]["name"].strip(), f"c-{cid}",
                                 warn=dangling, dot=reg_by_id[cid]["type"]))
        parts.append(section(gname.lower(), gname, group_icon[gname], entries))
    parts.append('</div>')  # /navscroll
    search_entries = [{**e, "h": prefix + e["h"]} for e in SEARCH_ENTRIES]
    parts.append(f'''
      <div class="navsearch">
        <div class="navsearch-box">
          <span class="navsearch-icon">{NAV_ICONS["search"]}</span>
          <input type="search" id="navsearch-input" placeholder="Search…" autocomplete="off" spellcheck="false">
          <kbd>⌘K</kbd>
        </div>
        <div class="navsearch-results" id="navsearch-results" hidden></div>
      </div>
    </aside>
    <script>window.NA_SEARCH_INDEX = {json.dumps(search_entries)};</script>
    ''')
    # Every nav click is a full page load (this is a static multi-page site, not an
    # SPA), so without this .navscroll silently resets to the top on every click --
    # scroll down to an organism, click it, and you're back at the top next time.
    # Restored inline (before app.js, before first paint) so there's no visible jump,
    # mirroring the theme-flash-prevention script in <head>.
    #
    # Order matters here and is the whole fix: a previously-opened section (say
    # Atoms) must be re-opened from localStorage BEFORE scrollTop is set, not after
    # in app.js. Otherwise scrollTop gets set against the shorter, still-collapsed
    # layout, then Atoms pops open afterwards, pushing everything below it down the
    # page -- which is exactly what made the list "jump back up" after a click even
    # though the stored scroll value was correct the whole time.
    parts.append(
        '<script>(function(){'
        'try{document.querySelectorAll(".navsection").forEach(function(s){'
        'if(s.dataset.forced==="1")return;'
        'var v=localStorage.getItem("na-navsec-"+s.dataset.key);'
        'if(v==="1")s.setAttribute("open","");else if(v==="0")s.removeAttribute("open");'
        '});}catch(e){}'
        'try{var e=document.querySelector(".navscroll"),'
        'y=sessionStorage.getItem("na-sidebar-scroll");if(e&&y)e.scrollTop=+y;}catch(e){}'
        '})();</script>'
    )
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
<link rel="stylesheet" href="{prefix}assets/style.css?v={STYLE_VER}">
<link rel="stylesheet" href="{prefix}../css/tokens.css">
</head><body>
<div class="layout">
{sidebar(prefix, active)}
<main class="main">
{body}
<footer class="footer">Generated from the repository — single source of truth. Regenerate with <code>python3 scripts/build_dashboard.py</code>. Source: Figma file <code>{E(registry["source"]["figma_file_key"])}</code>, page “{E(registry["source"]["figma_page"])}”, ingested {E(registry["generated"])}.</footer>
</main>
</div>
<script src="{prefix}assets/app.js?v={APPJS_VER}"></script>
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

def node_style(n, parent_dir=None):
    s = []
    size = n.get("size")
    # --- sizing. The layout-model 'size' (fill / hug / fixed-px, per axis) supersedes a legacy
    # fixed w/h snapshot. 'fill' grows/shrinks to fill the parent (flex on the main axis,
    # stretch on the cross); 'hug' sizes to content; a number is fixed px. This is the field
    # whose absence made hard-pinned snapshot widths overflow and bleed out of their box.
    if size:
        for axis in ("w", "h"):
            val = size.get(axis)
            if val is None:
                continue
            main = (axis == "w" and parent_dir == "row") or (axis == "h" and parent_dir == "column")
            dim = "width" if axis == "w" else "height"
            if val == "fill":
                if main:
                    s.append("flex:1 1 0"); s.append(f"min-{dim}:0")
                else:
                    s.append("align-self:stretch")
            elif val == "hug":
                if main:
                    s.append("flex:0 0 auto")
            elif isinstance(val, (int, float)):
                s.append(f"{dim}:{val}px")
                if main:
                    s.append("flex:none")
    elif "w" in n:
        s.append(f'width:{n["w"]}px')
        # A TEXT node's captured height is a snapshot of how tall Figma's own renderer made
        # the wrapped text; ours doesn't always agree (missing/approximated line-height, a
        # different font stack), so pinning it can crop a wrapped line right off. Width still
        # constrains wrapping (that's what has to match Figma); height is left intrinsic.
        if n.get("type") != "TEXT" and "h" in n:
            s.append(f'height:{n["h"]}px')
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
    # --- positioning. 'abs' pins a child out of the auto-layout flow to its parent's edges
    # (the trailing count / badge / overlay that Figma positions absolutely -- pinning it in
    # flow was what pushed "0/50" out of the box). Legacy x/y kept for older components;
    # everything else is position:relative so it can host absolutely-positioned children.
    abs_ = n.get("abs")
    if abs_:
        s.append("position:absolute")
        for edge in ("left", "right", "top", "bottom"):
            if edge in abs_:
                s.append(f"{edge}:{abs_[edge]}px")
    elif "x" in n and "y" in n:
        s.append(f'position:absolute;left:{n["x"]}px;top:{n["y"]}px')
    else:
        s.append("position:relative")
    if n.get("clip"):
        s.append("overflow:hidden")
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
        # Figma stores line-height either as a bare px number or a "110%" string. CSS treats
        # a *unitless* number as a multiplier of font-size (22 == 2200%), not px, so a bare
        # number must get an explicit unit or it silently blows up the line box (and, combined
        # with .pv-text{overflow:hidden}, clips the glyph out of view entirely).
        s.append(f"line-height:{lh}px" if isinstance(lh, (int, float)) else f"line-height:{lh}")
    ta = (n.get("textAlign") or "LEFT").lower()
    s.append(f"text-align:{ta}")
    if n.get("decoration") == "UNDERLINE":
        s.append("text-decoration:underline")
    s.append("white-space:pre-line")
    return ";".join(s)

# Hand-authored stand-ins for the small set of icon glyphs the ingested visual_values can't
# reproduce (Figma exports these as flattened image/SVG assets, never as CSS-representable
# shape data -- see INGESTION_REPORT.md). Each is flagged in its component YAML via
# `placeholder_icon` so it's traceable as a placeholder, not presented as the real Figma asset.
def _chevron_svg(dx, dy):
    """A chevron is one continuous two-segment stroke path; dx/dy give the direction it
    points in (unit vector), so all four rotations share one path shape."""
    def draw(n, w, h, color):
        cx, cy = w / 2, h / 2
        r = min(w, h) * 0.32
        # perpendicular unit vector, to place the two ends of the "V" either side of the point
        px, py = -dy, dx
        tipx, tipy = cx + dx * r, cy + dy * r
        e1x, e1y = cx - dx * r + px * r, cy - dy * r + py * r
        e2x, e2y = cx - dx * r - px * r, cy - dy * r - py * r
        return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" aria-hidden="true">'
                f'<path d="M{e1x:.1f} {e1y:.1f}L{tipx:.1f} {tipy:.1f}L{e2x:.1f} {e2y:.1f}" fill="none" '
                f'stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>')
    return draw

def _cross_diag_svg(flip):
    """Cross is two overlapping diagonal strokes; each instance draws one, and the existing
    data-stack centering (see .pv-frame[data-stack="1"]) overlays them into one X."""
    def draw(n, w, h, color):
        x1, x2 = (w - 1, 1) if flip else (1, w - 1)
        return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" aria-hidden="true">'
                f'<line x1="{x1}" y1="1" x2="{x2}" y2="{h-1}" stroke="{color}" stroke-width="1.5" '
                f'stroke-linecap="round"/></svg>')
    return draw

def _real_svg_icon(filename):
    """Unlike the hand-drawn stand-ins above, these read a real, properly-licensed icon
    file under assets/icons/ (see assets/icons/README.md for source + license) and
    recolor/resize it to the node's own captured dimensions -- used where Figma exported
    only a flattened shape with no real icon data (status bar signal/wifi/battery)."""
    with open(os.path.join(ROOT, "assets", "icons", filename)) as f:
        svg = f.read()
    viewbox = (re.search(r'viewBox="([^"]+)"', svg) or [None, "0 0 16 16"])[1]
    inner = re.sub(r"</?svg[^>]*>", "", svg).strip()
    def draw(n, w, h, color):
        return f'<svg viewBox="{viewbox}" width="{w}" height="{h}" fill="{color}" aria-hidden="true">{inner}</svg>'
    return draw

# Hand-authored stand-ins for the small set of icon glyphs the ingested visual_values can't
# reproduce (Figma exports these as flattened image/SVG assets, never as CSS-representable
# shape data -- see INGESTION_REPORT.md). Each is flagged in its component YAML via
# `placeholder_icon` so it's traceable as a placeholder, not presented as the real Figma asset.
PLACEHOLDER_ICONS = {
    "checkbox-check": lambda n, w, h, color: (
        f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" aria-hidden="true">'
        f'<rect width="{w}" height="{h}" rx="4.5" fill="{color}"/>'
        f'<path d="M{w*0.27} {h*0.52}l{w*0.14} {h*0.14} {w*0.29}-{h*0.32}" fill="none" '
        f'stroke="#f7f7f7" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    ),
    "chevron-back": _chevron_svg(-1, 0),
    "chevron-forward": _chevron_svg(1, 0),
    "chevron-up": _chevron_svg(0, -1),
    "chevron-down": _chevron_svg(0, 1),
    "cross-diag-1": _cross_diag_svg(False),
    "cross-diag-2": _cross_diag_svg(True),
    "signal-cellular": _real_svg_icon("signal-cellular.svg"),
    "signal-wifi": _real_svg_icon("signal-wifi.svg"),
    "battery-icon": _real_svg_icon("battery.svg"),
}

def resolve_variant_node(target_tree, target_comp, props):
    """An instance's `props` records the actual Figma variant it was set to (e.g.
    {"Action": "Chevron"}). If the target is a variant set, find the matching variant
    child so the preview shows the real selected form, not an arbitrary/default one.
    Plain (non-set) components have nothing to select and are returned as-is."""
    if target_tree.get("type") != "COMPONENT_SET":
        return target_tree
    # Boolean/instance-swap component properties (Figma keys like "Heading#395:0") are not
    # variant axes and never appear on their own on a real variant set in this library.
    axis_props = {k: v for k, v in (props or {}).items() if not re.search(r"#\d", str(k))}
    if axis_props:
        for v in target_comp.get("variants") or []:
            axes = {}
            for part in (v.get("name") or "").split(","):
                if "=" in part:
                    k, _, val = part.strip().partition("=")
                    axes[k.strip().lower()] = val.strip().lower()
            if all(axes.get(str(k).strip().lower()) == str(val).strip().lower() for k, val in axis_props.items()):
                for c in target_tree.get("children") or []:
                    if c.get("id") == v.get("node_id"):
                        return c
    children = target_tree.get("children") or []
    return children[0] if children else target_tree

MAX_INSTANCE_DEPTH = 6  # guards against a cyclic instance reference; never expected in practice

def render_node(n, depth=0, link_prefix="", instance_chain=(), parent_dir=None):
    if n.get("visible") is False:
        return ""  # hidden in Figma; present in the data, not in the render
    t = n.get("type")
    tip = E(f'{n.get("name","")} · {n.get("id","")}' + (f' · token: {json.dumps(n["tokens"])}' if n.get("tokens") else ""))
    if t == "TEXT":
        return f'<span class="pv-text" title="{tip}" style="{node_style(n, parent_dir)};{text_style(n)}">{E(n.get("chars",""))}</span>'
    if t == "INSTANCE":
        ref = n.get("instance_of") or {}
        target = None
        if ref.get("set") and ref["set"].get("id") in node_map:
            target = node_map[ref["set"]["id"]]
        elif ref.get("id") in node_map:
            target = node_map[ref["id"]]
        label = (ref.get("set") or {}).get("name") or ref.get("name") or "instance"
        # Resolve into the target component's own visual_values and render its actual
        # content in place, instead of stopping at a name+link chip. This is what makes a
        # composed organism (a card built from Actionables/Heading-content instances, say)
        # look like the real Figma design rather than a row of unlabeled placeholders. Each
        # child still "governs itself" — we're just inlining what it already governs.
        target_tree = components.get(target, {}).get("visual_values", {}).get("tree") if target else None
        if target and isinstance(target_tree, dict) and target not in instance_chain and len(instance_chain) < MAX_INSTANCE_DEPTH:
            variant_node = resolve_variant_node(target_tree, components[target], n.get("props") or {})
            # carry the instance's own sizing/position onto the resolved variant so a
            # fill/hug/pinned instance still sizes and sits where the parent placed it
            for k in ("size", "abs", "clip"):
                if k in n and k not in variant_node:
                    variant_node = {**variant_node, k: n[k]}
            return render_node(variant_node, depth + 1, link_prefix, instance_chain + (target,), parent_dir)
        inner = (f'<a href="{link_prefix}{target}.html">{E(label)}</a>' if target
                 else f'<span class="pv-unresolved" title="main component is outside the ingested page">{E(label)} ⚠</span>')
        return (f'<span class="pv-instance" title="{tip}" style="{node_style(n, parent_dir)}">'
                f'<span class="pv-instance-label">{inner}</span></span>')
    # Checked before the type dispatch below: a placeholder_icon tag can sit on a plain
    # VECTOR (chevron, cross) or on a FRAME (status-bar's Battery is a 3-shape frame, not
    # a single vector) -- either way it substitutes the whole subtree with a real icon.
    icon = PLACEHOLDER_ICONS.get(n.get("placeholder_icon"))
    if icon and t in ("VECTOR", "LINE", "ELLIPSE", "BOOLEAN_OPERATION", "FRAME"):
        # chevron/cross are stroke-only vectors (no fill at all) -- checking fills alone
        # always missed them and silently fell back to a hardcoded near-black. A FRAME
        # substitution (battery) carries no fill/stroke of its own -- it's a container --
        # so fall through to its first colored child (e.g. the Border/Capacity shapes)
        # rather than losing the real captured color to the hardcoded fallback.
        color_source = n
        if not (first_visible_solid(n.get("fills")) or first_visible_solid(n.get("strokes"))):
            for c in (n.get("children") or []):
                if first_visible_solid(c.get("fills")) or first_visible_solid(c.get("strokes")):
                    color_source = c
                    break
        color = (first_visible_solid(color_source.get("fills")) or first_visible_solid(color_source.get("strokes")) or {}).get("color", "#171717")
        svg = icon(n, n.get("w", 24), n.get("h", 24), color)
        return f'<span class="pv-icon-placeholder" title="{tip} · placeholder, pending real Figma asset">{svg}</span>'
    if t in ("VECTOR", "LINE", "ELLIPSE", "BOOLEAN_OPERATION"):
        return f'<span class="pv-shape" title="{tip}" style="{node_style(n, parent_dir)}"></span>'
    kids = n.get("children")
    if isinstance(kids, dict):
        kids = list(kids.values())
    my_dir = ("column" if n["layout"]["mode"] == "VERTICAL" else "row") if n.get("layout") else None
    inner = "".join(render_node(c, depth + 1, link_prefix, instance_chain, my_dir) for c in (kids or []))
    if not kids and n.get("childCount"):
        inner = f'<span class="pv-note">{n["childCount"]} children — {E(n.get("note","summarized in visual_values"))}</span>'
    # a frame with absolutely-positioned children must NOT also get the data-stack overlap rule
    abspos = "" if (n.get("layout") or any((isinstance(c, dict) and c.get("abs")) for c in (kids or []))) else ' data-stack="1"'
    return f'<div class="pv-frame" title="{tip}" style="{node_style(n, parent_dir)}"{abspos}>{inner}</div>'

def render_preview(comp, link_prefix=""):
    tree = comp.get("visual_values", {}).get("tree")
    if not isinstance(tree, dict):
        return warn("No extracted visual tree stored for this component — preview unavailable.")
    out = []
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
          <div class="pv-stage"><div class="pv-scale" style="transform:scale({scale});width:{w}px">{render_node(vt, 0, link_prefix)}</div></div>
        </div>''')
    return "".join(out)

# ----------------------------------------------------------------- component pages
TYPE_BADGE = {"atom": "Atom", "molecule": "Molecule", "organism": "Organism", "complex-organism": "Complex organism"}

def component_page(cid):
    comp = components[cid]
    reg = reg_by_id[cid]
    name = comp["name"].strip()
    dangling = [e for e in reg.get("figma_instance_edges", []) or [] if not e["resolved"] and not e.get("excluded")]
    warns = []
    if dangling:
        items = "".join(
            f'<li><b>{E(e["references"])}</b> (node <code>{E(e["ref_node_id"])}</code>) — {E(e.get("external_location",""))}'
            + (f'; same-named library component: <a href="{e["same_named_library_component"]}.html">{e["same_named_library_component"]}</a>'
               if e.get("same_named_library_component") else "") + "</li>"
            for e in dangling)
        warns.append(warn(f'{len(dangling)} Figma instance reference(s) inside this component point outside '
                          f'the ingested library page (see INGESTION_REPORT.md):<ul>{items}</ul>'))

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
PRIMITIVE_FAMILIES = [("gray", "Greys"), ("red", "Reds"), ("green", "Greens"), ("amber", "Ambers")]

def colors_page():
    cols = tokens_colors["collections"]
    prim = cols["color"]["variables"]
    sem = cols["tokens"]["variables"]

    def prim_hex(k):
        v = prim.get(k)
        return v["value"] if isinstance(v, dict) else v

    # Grouped by color family (designer's own categorization: Greys / Reds / Greens /
    # Ambers) rather than the flat grid it used to be, with the Usage text pulled
    # verbatim from the Figma "Colors Visualization" documentation frame (2035:1542).
    prim_rows = []
    for prefix, label in PRIMITIVE_FAMILIES:
        keys = [k for k in prim if k.split("/")[0] == prefix]
        if not keys:
            continue
        prim_rows.append(f'<tr class="tok-grouphead"><td colspan="3">{E(label)}</td></tr>')
        for k in keys:
            v = prim[k]
            hexval = v["value"] if isinstance(v, dict) else v
            usage = v.get("usage") if isinstance(v, dict) else None
            usage_html = E(usage) if usage else '<span class="dim">not yet ingested from Figma</span>'
            prim_rows.append(
                f'<tr><td><code>{E(k)}</code></td><td>{usage_html}</td>'
                f'<td><div class="tokcell"><span class="tokswatch" style="background:{E(hexval)}" '
                f'title="{E(hexval)}"></span><span class="tokswatchlabel">{E(hexval)}</span>'
                f'<button class="copybtn small" data-copy="{E(hexval)}">⧉</button></div></td></tr>')

    def resolve(val):
        if isinstance(val, str) and val.startswith("alias:"):
            return prim_hex(val[6:]), val[6:]
        return val, None

    # Semantic tokens are grouped by their top-level namespace (background/text/icon/...),
    # mirroring how the collection is browsed in Figma, with one row per token and a
    # dedicated column per mode instead of one split swatch.
    def modecell(v, alias):
        label = E(alias) if alias else E(v)
        return (f'<div class="tokcell"><span class="tokswatch" style="background:{E(v)}" '
                f'title="{E(v)}"></span><span class="tokswatchlabel">{label}</span></div>')

    rows = []
    current_group = None
    for k, modes in sem.items():
        group = k.split("/")[0]
        if group != current_group:
            current_group = group
            rows.append(f'<tr class="tok-grouphead"><td colspan="4">'
                        f'<span class="dim">token</span> <span class="tok-groupsep">/</span> '
                        f'{E(group.title())}</td></tr>')
        lv, la = resolve(modes.get("light"))
        dv, da = resolve(modes.get("dark"))
        usage = modes.get("usage")
        usage_html = E(usage) if usage else '<span class="dim">not yet ingested from Figma</span>'
        rows.append(
            f'<tr><td><code>token/{E(k)}</code></td>'
            f'<td>{usage_html}</td>'
            f'<td>{modecell(lv, la)}</td>'
            f'<td>{modecell(dv, da)}</td></tr>')

    body = f"""
    <header class="pagehead"><h1>Colors &amp; tokens</h1></header>
    <p class="subtle">Synced from the Figma variable collections <code>color</code> (primitives) and
    <code>tokens</code> (semantic, Light/Dark). Source: <code>tokens/colors.yaml</code>.</p>
    <div class="subhead">Semantic <span class="dim">— {len(sem)} tokens, light and dark value each</span></div>
    <table class="table toktable"><thead><tr><th>Token</th><th>Usage</th><th>Light mode</th><th>Dark mode</th></tr></thead>
    <tbody>{''.join(rows)}</tbody></table>
    <div class="subhead">Primitive <span class="dim">— {len(prim)} raw scale values</span></div>
    <table class="table toktable"><thead><tr><th>Token</th><th>Usage</th><th>Value</th></tr></thead>
    <tbody>{''.join(prim_rows)}</tbody></table>
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
FILL_GAP_JS = r"""
(function () {
  var CURRENT_LEDGER = __CURRENT_LEDGER_JSON__;
  var CID = __CID_JSON__;
  var FIELD = __FIELD_JSON__;
  function buildEntry(text) {
    return JSON.stringify({
      id: 'learn-fill-' + CID + '-' + FIELD + '-' + Date.now(),
      logged_at: new Date().toISOString(),
      kind: 'field_contribution',
      source: 'manual-fill',
      components: [CID],
      field: FIELD,
      contributed_text: text,
      status: 'proposed',
      reviewed_by: null,
      reviewed_at: null
    });
  }
  var ta = document.getElementById('gap-text');
  function currentText() { return ta.value.trim(); }
  function update() {
    var has = currentText().length > 0;
    var dl = document.getElementById('download-ledger');
    var cp = document.getElementById('copy-entry');
    dl.disabled = !has; cp.disabled = !has;
  }
  ta.addEventListener('input', update);
  document.getElementById('copy-entry').addEventListener('click', function () {
    var text = currentText();
    if (!text) return;
    var btn = this;
    navigator.clipboard.writeText(buildEntry(text)).then(function () {
      var t = btn.textContent; btn.textContent = '✓ copied'; btn.classList.add('copied');
      setTimeout(function () { btn.textContent = t; btn.classList.remove('copied'); }, 1200);
    });
  });
  document.getElementById('download-ledger').addEventListener('click', function () {
    var text = currentText();
    var status = document.getElementById('download-status');
    if (!text) { status.textContent = 'Write something first.'; return; }
    var lines = CURRENT_LEDGER ? CURRENT_LEDGER.split('\n').filter(function (l) { return l.trim().length; }) : [];
    lines.push(buildEntry(text));
    var blob = new Blob([lines.join('\n') + '\n'], { type: 'application/x-ndjson' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = 'learnings.jsonl';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
    status.textContent = 'Downloaded, with this entry appended to the existing ledger. Replace learnings.jsonl in the repo with this file and commit — nothing here saves on its own.';
  });
  update();
})();
"""

# Same reasoning as FILL_GAP_JS above: raw string, one marker token spliced in via .replace().
# Approve/Deny only ever edit an in-memory copy of the ledger text -- nothing here writes to
# the real learnings.jsonl on disk. The download at the bottom is what makes a decision real;
# per AGENT.md §6 the actual repo update (replace the file, commit, push) is the agent's job,
# not something a static page can do for itself.
LEARNINGS_JS = r"""
(function () {
  var CURRENT_LEDGER = __CURRENT_LEDGER_JSON__;
  var lines = CURRENT_LEDGER ? CURRENT_LEDGER.split('\n').filter(function (l) { return l.trim().length; }) : [];
  var decisions = {}; // id -> modified line text, only for entries reviewed this session

  function findLineIndex(id) {
    for (var i = 0; i < lines.length; i++) {
      try { if (JSON.parse(lines[i]).id === id) return i; } catch (e) {}
    }
    return -1;
  }

  function decide(row, id, newStatus) {
    var idx = findLineIndex(id);
    if (idx === -1) return;
    var entry;
    try { entry = JSON.parse(lines[idx]); } catch (e) { return; }
    entry.status = newStatus;
    entry.reviewed_at = new Date().toISOString();
    decisions[id] = JSON.stringify(entry);

    row.classList.add('is-decided');
    var ctas = row.querySelector('[data-ctas]');
    ctas.querySelector('[data-approve]').hidden = true;
    ctas.querySelector('[data-deny]').hidden = true;
    var note = ctas.querySelector('[data-decided-note]');
    note.hidden = false;
    note.textContent = newStatus === 'confirmed'
      ? 'Marked approved — download below to save.'
      : 'Marked denied — download below to save.';
    note.classList.add(newStatus === 'confirmed' ? 'is-approved' : 'is-denied');

    var dlBtn = document.getElementById('download-learnings');
    dlBtn.disabled = false;
    document.getElementById('learnings-download-status').textContent =
      Object.keys(decisions).length + ' decision(s) made this session, not yet saved.';
  }

  document.querySelectorAll('.learning-row[data-learning-id]').forEach(function (row) {
    var id = row.getAttribute('data-learning-id');
    var approveBtn = row.querySelector('[data-approve]');
    var denyBtn = row.querySelector('[data-deny]');
    if (approveBtn) approveBtn.addEventListener('click', function (ev) { ev.preventDefault(); decide(row, id, 'confirmed'); });
    if (denyBtn) denyBtn.addEventListener('click', function (ev) { ev.preventDefault(); decide(row, id, 'rejected'); });
  });

  document.getElementById('download-learnings').addEventListener('click', function () {
    var out = lines.map(function (line, i) {
      try {
        var id = JSON.parse(line).id;
        if (decisions[id]) return decisions[id];
      } catch (e) {}
      return line;
    });
    var blob = new Blob([out.join('\n') + '\n'], { type: 'application/x-ndjson' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = 'learnings.jsonl';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
    document.getElementById('learnings-download-status').textContent =
      'Downloaded with ' + Object.keys(decisions).length + ' decision(s) applied. Replace learnings.jsonl in the repo with this file, then follow AGENT.md §6: regenerate the dashboard and commit both together.';
  });
})();
"""

def fill_gap_page(cid, key, label):
    """One dedicated page per (component, missing field) gap — the actual entry point, showing
    the component's real rendered preview above the text field so the gap is filled with the
    thing in view, not from memory. Lives in fill-gaps/, so it needs the same "../" prefix and
    the same render_preview link_prefix component pages already use for sibling instance links."""
    comp = components[cid]
    name = comp["name"].strip()
    ledger_raw = ""
    if os.path.exists(learnings_path):
        with open(learnings_path) as f:
            ledger_raw = f.read()
    js = (FILL_GAP_JS.replace("__CURRENT_LEDGER_JSON__", json.dumps(ledger_raw))
                     .replace("__CID_JSON__", json.dumps(cid))
                     .replace("__FIELD_JSON__", json.dumps(key)))
    body = f"""
    <div class="crumb"><a href="../fill-gaps.html">Fill the gaps</a> / {E(label)}</div>
    <header class="pagehead"><h1>{E(name)}</h1><span class="dim">{E(label)} is missing</span></header>
    <p class="dim">This is a static site with no backend: nothing typed below saves by itself. Write the
    {E(label.lower())}, then copy the entry or download an updated <code>learnings.jsonl</code> — replace the
    repo's copy and commit it. It's logged as <code>proposed</code> until a designer confirms it or folds it
    into Figma directly (see <a href="../../AGENT.md">AGENT.md §6</a>). This never changes the Documentation
    coverage numbers on the overview; those measure the Figma-authored spec specifically.</p>
    <div class="stagecard">{render_preview(comp, "../components/")}</div>
    <section class="metasection">
      <h3>{E(label)}</h3>
      <textarea id="gap-text" rows="5" placeholder="Write the {E(label.lower())} for {E(name)}…"></textarea>
      <div class="quicklinks">
        <button type="button" id="copy-entry" class="gapcopybtn" disabled>copy entry</button>
        <button type="button" id="download-ledger" class="btn btn-primary" disabled>Download learnings.jsonl</button>
        <span id="download-status" class="dim"></span>
      </div>
    </section>
    <div class="quicklinks"><a class="btn" href="../components/{cid}.html">Open {E(name)}'s full page →</a></div>
    <script>{js}</script>
    """
    return page(f"{name} — {label}", "fill-gaps", body, prefix="../")

def fill_gaps_page():
    """Mirrors learnings_page()'s segmented-control layout: one tab per documentation field,
    so a library with gaps scattered across all five fields never makes you scroll past
    Purpose and Usage just to reach the Rules gaps you actually came to fill."""
    total_gaps = sum(len(missing_by_field[key]) for key, _ in CORE_DOC_FIELDS)

    tabs = []
    for key, label in CORE_DOC_FIELDS:
        missing = missing_by_field[key]
        rows = "".join(
            f'<a class="gaprow gaprow-link" href="fill-gaps/{cid}--{E(key)}.html">'
            f'<span class="gaprow-name">{E(components[cid]["name"].strip())}</span>'
            f'<span class="dim">{E(cid)}</span><span class="gaprow-arrow">→</span></a>'
            for cid in missing) or '<p class="entrylist-empty">No gaps — every component has this field authored.</p>'
        tabs.append((key, label, len(missing), rows))

    segtabs_html = "".join(
        f'<button type="button" class="segtab" data-seg-key="{key}">{E(label)}'
        f'<span class="segtab-count">{count}</span></button>'
        for key, label, count, _ in tabs)
    segpanels_html = "".join(
        f'<div class="metasection" data-segpanel-group="fillgaps" data-seg-key="{key}">{rows}</div>'
        for key, _, _, rows in tabs)

    body = f"""
    <header class="pagehead"><h1>Fill the gaps</h1></header>
    <p class="dim">{total_gaps} missing documentation field(s) across the library. Each one is its own page,
    with the component's real preview shown above the text field. This is a static site with no backend —
    nothing saves automatically anywhere in here; see any gap's own page for how to actually contribute it.</p>

    <div class="segtabs" data-seg-group="fillgaps">{segtabs_html}</div>
    {segpanels_html}
    """
    return page("Fill the gaps", "fill-gaps", body)

SEG_ICONS = {
    "pending": _navsvg('<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>'),
    "confirmed": _navsvg('<circle cx="12" cy="12" r="8.5"/><path d="M8.3 12.3l2.5 2.5 5-5.2"/>'),
    "rejected": _navsvg('<circle cx="12" cy="12" r="8.5"/><path d="M9 9l6 6M15 9l-6 6"/>'),
}

def learnings_page():
    """The dedicated destination the overview's three learnings tiles link into (see
    AGENT.md §6). Pending entries are actionable (Approve/Deny); confirmed and rejected
    ones are the closed record of past decisions. A segmented control shows exactly one
    category at a time -- with dozens of entries logged over time, stacking all three
    on one page would mean scrolling past everything confirmed just to reach what's
    rejected, which is the opposite of what this page is for."""
    ledger_raw = ""
    if os.path.exists(learnings_path):
        with open(learnings_path) as f:
            ledger_raw = f.read()
    js = LEARNINGS_JS.replace("__CURRENT_LEDGER_JSON__", json.dumps(ledger_raw))

    tabs = [
        ("pending", "Pending review", len(learnings_pending),
         "".join(learning_row_html(e, actionable=True) for e in learnings_pending) or
         '<p class="entrylist-empty">Nothing awaiting review.</p>'),
        ("confirmed", "Confirmed", len(learnings_confirmed),
         "".join(learning_row_html(e) for e in learnings_confirmed) or
         '<p class="entrylist-empty">No learnings confirmed yet.</p>'),
        ("rejected", "Rejected", len(learnings_rejected),
         "".join(learning_row_html(e) for e in learnings_rejected) or
         '<p class="entrylist-empty">Nothing rejected yet.</p>'),
    ]
    segtabs_html = "".join(
        f'<button type="button" class="segtab" data-seg-key="{key}">'
        f'<span class="segtab-icon">{SEG_ICONS[key]}</span>{E(label)}'
        f'<span class="segtab-count">{count}</span></button>'
        for key, label, count, _ in tabs)
    segpanels_html = "".join(
        f'<div class="metasection" data-segpanel-group="learnings" data-seg-key="{key}">{rows}</div>'
        for key, _, _, rows in tabs)

    body = f"""
    <header class="pagehead"><h1>Agent Learnings</h1></header>
    <p class="dim">Corrections the agent has absorbed, and what's still waiting on a human decision — see
    <a href="../AGENT.md">AGENT.md §6</a>. This is a static site with no backend: clicking Approve/Deny marks
    your decision here in the browser only. Download the updated <code>learnings.jsonl</code> at the bottom
    once you're done, replace the repo's copy, and commit — nothing here saves by itself.</p>

    <div class="segtabs" data-seg-group="learnings">{segtabs_html}</div>
    {segpanels_html}

    <div class="learnings-download-bar">
      <button type="button" id="download-learnings" class="btn btn-primary" disabled>Download updated learnings.jsonl</button>
      <span id="learnings-download-status" class="dim">Approve or deny an entry above to enable this.</span>
    </div>
    <script>{js}</script>
    """
    return page("Agent Learnings", "learnings", body)

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

def learning_row_html(entry, actionable=False):
    """One collapsible row for learnings.html. Collapsed, only the proposed rule (or field
    label) and a chevron show — the component chips and the full what-happened/what-you-said
    detail are inside the <details> body, so a reader sees what a review is about before
    deciding whether to open it. `actionable` adds the Approve/Deny controls; only a still-
    pending entry gets those — a confirmed or rejected one is a closed, read-only record."""
    chips = "".join(render_chip({"label": components.get(c, {}).get("name", c).strip() if c in components else c,
                                  "href": f"components/{c}.html"})
                     for c in (entry.get("components") or []))
    eid = entry.get("id", "")
    if entry.get("kind") == "field_contribution":
        field_label = FIELD_LABEL.get(entry.get("field"), entry.get("field", "a field"))
        summary_text = f"{field_label} — contributed"
        fields_html = (f'<div class="learning-field"><div class="learning-field-label">Contributed text</div>'
                        f'<div class="learning-field-value">{E(entry.get("contributed_text") or "")}</div></div>')
    else:
        summary_text = entry.get("proposed_rule") or entry.get("user_correction") or "(no rule text logged)"
        fields_html = (
            f'<div class="learning-field"><div class="learning-field-label">What the agent did</div>'
            f'<div class="learning-field-value">{E(entry.get("agent_action") or "")}</div></div>'
            f'<div class="learning-field"><div class="learning-field-label">What you said</div>'
            f'<div class="learning-field-value">{E(entry.get("user_correction") or "")}</div></div>'
        )

    ctas = ""
    if actionable:
        ctas = ('<div class="learning-ctas" data-ctas>'
                '<button type="button" class="btn btn-approve" data-approve>Approve</button>'
                '<button type="button" class="btn btn-deny" data-deny>Deny</button>'
                '<span class="learning-decided-note" data-decided-note hidden></span></div>')

    return (f'<details class="learning-row" data-learning-id="{E(eid)}">'
            f'<summary><span class="learning-summary-text">{E(summary_text)}</span>'
            f'<span class="ovchev" aria-hidden="true"></span></summary>'
            f'<div class="learning-body"><div class="learning-chips">{chips}</div>'
            f'{fields_html}{ctas}</div></details>')

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
            action = f'<a class="fieldedit" href="fill-gaps.html#{E(key)}">Edit {PENCIL_ICON}</a>'
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
    # pending ones are unvalidated corrections a designer hasn't reviewed yet. The overview only
    # gives the counts (each one a link into learnings.html): the full entries — proposed rule,
    # what happened, what was said, the Approve/Deny review — live on that dedicated page, so this
    # page doesn't grow a paragraph taller every time a correction gets logged.
    n_confirmed, n_pending, n_rejected = len(learnings_confirmed), len(learnings_pending), len(learnings_rejected)
    pending_tile_cls = "kpi kpi-warn" if n_pending else "kpi"

    def learnings_tile(count, label, anchor, cls):
        return (f'<a class="{cls}" href="learnings.html#{anchor}">'
                f'<div class="kpi-value">{count}</div>'
                f'<div class="kpi-linkrow"><span class="kpi-label">{E(label)}</span>'
                f'<span class="kpi-arrow">→</span></div></a>')

    learnings_section = f'''
      <h4 class="subhead">Agent learnings <span class="dim">— corrections the agent has absorbed, and what is still pending review</span></h4>
      <div class="kpirow">
        {learnings_tile(n_confirmed, "Confirmed — applied as guidance", "confirmed", "kpi")}
        {learnings_tile(n_rejected, "Reviewed and rejected", "rejected", "kpi")}
        {learnings_tile(n_pending, "Pending review", "pending", pending_tile_cls)}
      </div>
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
  --bad-bg:#2a1614; --bad-line:#5c2620; --bad-ink:#f0685a;
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
  --bad-bg:#fdecea; --bad-line:#f0b8b0; --bad-ink:#b3261e;
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
  padding:16px 12px 0;position:sticky;top:0;height:100vh;display:flex;flex-direction:column}
/* No visible scrollbars anywhere inside the app. These containers still scroll — the bar
   itself is just never painted, so panels never grow a track down their edge. */
.navscroll,.ovcard-body,.pv-stage,.codeblock,.graphwrap,.rawyaml pre,.overviewdoc-body{
  scrollbar-width:none;-ms-overflow-style:none}
.navscroll::-webkit-scrollbar,.ovcard-body::-webkit-scrollbar,.pv-stage::-webkit-scrollbar,
.codeblock::-webkit-scrollbar,.graphwrap::-webkit-scrollbar,.rawyaml pre::-webkit-scrollbar{
  width:0;height:0;display:none}
.brand{display:flex;gap:10px;align-items:center;margin:2px 4px 16px;flex:none}
.applogo{width:30px;height:30px;flex:none;border-radius:var(--r-sm);background:var(--ink);color:var(--canvas);
  display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px}
.brandname{flex:1;font-weight:600;font-size:13.5px;letter-spacing:-0.01em}
.themetoggle{width:30px;height:30px;flex:none;border-radius:var(--r-sm);border:1px solid var(--line);
  background:var(--surface-2);color:var(--ink2);cursor:pointer;display:flex;align-items:center;
  justify-content:center;padding:0;transition:color .15s,border-color .15s}
.themetoggle:hover{color:var(--ink);border-color:var(--line-2)}
.themetoggle svg{width:15px;height:15px}
.navtop{display:flex;flex-direction:column;gap:2px;flex:none;margin-bottom:14px}
/* ---- collapsible sections (Foundations / Atoms / Molecules / Organisms) ---- */
.navscroll{flex:1;min-height:0;overflow-y:auto;padding-bottom:12px}
.navsection{margin-bottom:2px}
.navsection>summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:9px;
  padding:8px 10px;border-radius:var(--r-sm);color:var(--ink2);font-size:11px;letter-spacing:.08em;
  text-transform:uppercase;font-weight:600;transition:background .13s,color .13s;user-select:none}
.navsection>summary::-webkit-details-marker{display:none}
.navsection>summary::marker{content:""}
.navsection>summary:hover{background:var(--surface-2);color:var(--ink)}
.navsection[open]>summary{color:var(--ink)}
.navsecicon{width:16px;height:16px;flex:none;display:flex}
.navsecicon svg{width:100%;height:100%}
.navseclabel{flex:1}
.navsection .count{background:none;color:var(--ink3);padding:0;font-size:10.5px;
  font-weight:600;font-variant-numeric:tabular-nums}
.navchevron{width:14px;height:14px;flex:none;color:var(--ink3);transition:transform .16s}
.navchevron svg{width:100%;height:100%}
.navsection[open] .navchevron{transform:rotate(180deg)}
.navsectionbody{display:flex;flex-direction:column;gap:1px;padding:2px 0 6px 4px}
/* ---- nav items (both top-level and inside a section) ---- */
.navitem{display:flex;align-items:center;gap:9px;padding:7px 10px;border-radius:var(--r-sm);
  color:var(--ink2);font-size:13px;transition:background .13s,color .13s}
.navitem:hover{background:var(--surface-2);color:var(--ink)}
.navitem.active{background:var(--accent);color:#fff;font-weight:500}
.navitem.active .count,.navitem.active .warnbadge{color:#fff;opacity:.85}
.navicon{width:16px;height:16px;flex:none;display:flex}
.navicon svg{width:100%;height:100%}
.navdot{width:6px;height:6px;flex:none;border-radius:50%;background:var(--ink3)}
.navitem.active .navdot{background:#fff}
.navitem .count{margin-left:auto;color:var(--ink3);font-size:11px;font-variant-numeric:tabular-nums}
.navlabel{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* ---- search ---- */
.navsearch{flex:none;position:relative;margin:0 -12px;padding:14px 12px 16px;
  border-top:1px solid var(--line);background:var(--surface)}
.navsearch-box{display:flex;align-items:center;gap:8px;background:var(--surface-2);
  border:1px solid var(--line);border-radius:var(--r-sm);padding:7px 10px;color:var(--ink3)}
.navsearch-icon{width:15px;height:15px;flex:none;display:flex}
.navsearch-icon svg{width:100%;height:100%}
.navsearch-box input{flex:1;min-width:0;background:none;border:none;outline:none;color:var(--ink);
  font-size:13px;font-family:inherit}
.navsearch-box input::placeholder{color:var(--ink3)}
.navsearch-box kbd{font-family:var(--font-mono);font-size:10.5px;color:var(--ink3);
  background:var(--surface-3);border:1px solid var(--line-2);border-radius:4px;padding:2px 5px;flex:none}
.navsearch-results{position:absolute;left:12px;right:12px;bottom:calc(100% + 6px);
  background:var(--surface-2);border:1px solid var(--line-2);border-radius:var(--r-md);
  box-shadow:0 12px 28px rgba(0,0,0,.35);max-height:min(50vh,360px);overflow-y:auto;
  padding:6px;z-index:20;scrollbar-width:none}
.navsearch-results::-webkit-scrollbar{width:0;height:0;display:none}
.navsearch-results[hidden]{display:none}
.navsearch-result{display:flex;align-items:center;gap:8px;padding:7px 9px;border-radius:var(--r-sm);
  color:var(--ink2);font-size:12.5px}
.navsearch-result:hover,.navsearch-result.sel{background:var(--surface-3);color:var(--ink)}
.navsearch-result .grp{margin-left:auto;color:var(--ink3);font-size:10.5px}
.navsearch-empty{padding:10px;color:var(--ink3);font-size:12.5px;text-align:center}
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
/* the fill-gaps index: each gap is a plain link row out to its own dedicated page */
.gaprow-link{display:flex;align-items:baseline;gap:10px;text-decoration:none;cursor:pointer}
.gaprow-link:hover{border-color:var(--accent);background:var(--surface-3)}
.gaprow-name{font-size:13.5px;font-weight:500;color:var(--ink)}
.gaprow-arrow{margin-left:auto;color:var(--accent);flex:none}
/* the standalone entry field on a gap's own page */
textarea#gap-text{width:100%;background:var(--surface-2);border:1px solid var(--line);
  border-radius:var(--r-sm);padding:11px 13px;font:inherit;font-size:13.5px;color:var(--ink);
  resize:vertical;box-sizing:border-box}
textarea#gap-text:focus{outline:none;border-color:var(--accent)}
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

/* ---------------------------------------------------------------- learnings.html */
/* One entry, collapsed to just its proposed rule + a chevron by default -- the chips,
   the "what happened"/"what you said" detail, and (for pending ones) the review CTAs
   only appear once opened, so a page with a dozen corrections logged still reads as a
   dozen headings, not a wall of tags and paragraphs. */
.learning-row{background:var(--surface-2);border:1px solid var(--line);border-radius:var(--r-md);
  margin:0 0 10px;overflow:hidden;transition:border-color .15s}
.learning-row:last-child{margin-bottom:0}
.learning-row[open]{border-color:var(--line-2)}
.learning-row summary{list-style:none;cursor:pointer;padding:14px 16px;
  display:flex;align-items:flex-start;gap:12px}
.learning-row summary::-webkit-details-marker{display:none}
.learning-summary-text{font-size:13.5px;font-weight:500;color:var(--ink);line-height:1.5;flex:1}
.learning-row .ovchev{margin-top:5px}
.learning-row[open] .ovchev{transform:rotate(90deg)}
.learning-body{padding:2px 16px 16px;border-top:1px solid var(--line-soft)}
.learning-chips{display:flex;flex-wrap:wrap;gap:6px;margin:14px 0}
.learning-field{margin-bottom:14px}
.learning-field:last-child{margin-bottom:0}
.learning-field-label{font-size:10.5px;font-weight:600;letter-spacing:.06em;
  text-transform:uppercase;color:var(--ink3);margin-bottom:4px}
.learning-field-value{font-size:13px;color:var(--ink2);line-height:1.55}
.learning-ctas{display:flex;align-items:center;gap:8px;margin-top:16px}
.btn-approve{border-color:var(--good-line);color:var(--good-ink)}
.btn-approve:hover{background:var(--good-ink);color:var(--canvas);border-color:var(--good-ink)}
.btn-deny{border-color:var(--bad-line);color:var(--bad-ink)}
.btn-deny:hover{background:var(--bad-ink);color:var(--canvas);border-color:var(--bad-ink)}
.learning-row.is-decided{opacity:.6}
.learning-decided-note{font-size:12.5px;font-weight:500}
.learning-decided-note.is-approved{color:var(--good-ink)}
.learning-decided-note.is-denied{color:var(--bad-ink)}
.learnings-download-bar{position:sticky;bottom:0;margin:24px -22px -20px;padding:16px 22px;
  background:var(--surface);border-top:1px solid var(--line);
  display:flex;align-items:center;gap:12px;flex-wrap:wrap}

/* Segmented control: switches which category panel shows, so a page with several
   categories (learnings.html's Pending/Confirmed/Rejected, fill-gaps.html's five
   fields) never makes you scroll past ones you don't care about right now to reach
   the one you do. See the shared handler in app.js. */
.segtabs{display:flex;gap:4px;background:var(--surface-2);border:1px solid var(--line);
  border-radius:var(--r-pill);padding:4px;margin:20px 0}
.segtab{flex:1;display:flex;align-items:center;justify-content:center;gap:8px;
  padding:10px 14px;border-radius:var(--r-pill);cursor:pointer;font-size:13px;
  color:var(--ink2);border:none;background:none;font-family:inherit;white-space:nowrap;
  transition:background .15s,color .15s}
.segtab:hover{color:var(--ink)}
.segtab.active{background:var(--accent-soft);color:var(--ink)}
.segtab-icon{width:15px;height:15px;flex:none}
.segtab-count{background:var(--surface-3);border-radius:var(--r-pill);padding:1px 9px;
  font-size:11.5px;color:var(--ink3);font-variant-numeric:tabular-nums}
.segtab.active .segtab-count{background:var(--accent);color:#fff}
@media (max-width:760px){.segtabs{flex-direction:column}.segtab{justify-content:flex-start}}
[data-segpanel-group]{display:none}
[data-segpanel-group].active{display:block}

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
/* KPI tiles that are really links through to learnings.html — same tile, but with a
   hover state and a trailing arrow so it reads as "there's more, one layer in" rather
   than a plain stat. */
a.kpi{text-decoration:none;display:block;cursor:pointer;transition:border-color .15s,background .15s}
a.kpi:hover{border-color:var(--accent);background:var(--surface-3)}
a.kpi:hover .kpi-arrow{transform:translateX(2px)}
.kpi-linkrow{display:flex;align-items:baseline;gap:6px}
.kpi-arrow{color:var(--accent);font-size:12px;transition:transform .15s}
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
.pv-icon-placeholder{display:block;flex:none;line-height:0}
.pv-icon-placeholder svg{display:block}
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
.toktable td{color:var(--ink2)}
.tok-grouphead td{background:var(--surface-2);color:var(--ink);font-weight:600;font-size:12.5px;
  padding:8px 10px;border-bottom:1px solid var(--line)}
.tok-groupsep{color:var(--ink3);font-weight:400}
.tokcell{display:flex;align-items:center;gap:9px}
.tokswatch{display:inline-block;width:26px;height:26px;border-radius:6px;flex:none;
  border:1px solid var(--line-2)}
.tokswatchlabel{font-family:var(--font-mono);font-size:11px;color:var(--ink3)}
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

// Persist the nav's scroll position across page loads -- the restore half of this
// lives inline right after the sidebar markup (see sidebar() in build_dashboard.py)
// so it runs before first paint with no visible jump.
(function () {
  const nav = document.querySelector('.navscroll');
  if (!nav) return;
  nav.addEventListener('scroll', function () {
    try { sessionStorage.setItem('na-sidebar-scroll', nav.scrollTop); } catch (e) {}
  }, { passive: true });
})();

// Collapsible sidebar sections (Foundations / Atoms / Molecules / Organisms): a
// section the visitor previously opened stays open on the next page too, EXCEPT a
// section is never force-collapsed if it contains the page you're currently on
// (data-forced="1", set server-side). Applying the stored open/closed state itself
// happens earlier, inline right after the sidebar markup (see sidebar() in
// build_dashboard.py) -- it has to run before the scroll-position restore below it,
// or the container's height is still wrong when scrollTop gets set. This block only
// has to persist future toggles.
document.querySelectorAll('.navsection').forEach(function (sec) {
  const key = 'na-navsec-' + sec.dataset.key;
  sec.addEventListener('toggle', function () {
    try { localStorage.setItem(key, sec.open ? '1' : '0'); } catch (e) {}
  });
});

// Sidebar search: filters the baked-in NA_SEARCH_INDEX (every component + nav +
// foundations page, with hrefs already resolved for this page's depth) as you type,
// with arrow-key navigation and Cmd/Ctrl+K to jump to the box from anywhere.
(function () {
  const input = document.getElementById('navsearch-input');
  const results = document.getElementById('navsearch-results');
  const index = window.NA_SEARCH_INDEX;
  if (!input || !results || !index) return;
  let sel = -1;

  function renderEmpty(msg) { results.innerHTML = '<div class="navsearch-empty">' + msg + '</div>'; }

  function filter() {
    const q = input.value.trim().toLowerCase();
    sel = -1;
    if (!q) { results.hidden = true; results.innerHTML = ''; return; }
    const matches = index.filter(function (it) {
      return it.n.toLowerCase().indexOf(q) !== -1 || it.g.toLowerCase().indexOf(q) !== -1;
    }).slice(0, 20);
    results.hidden = false;
    if (!matches.length) { renderEmpty('No matches'); return; }
    results.innerHTML = matches.map(function (it) {
      return '<a class="navsearch-result" href="' + it.h + '">'
           + '<span>' + it.n.replace(/</g, '&lt;') + '</span>'
           + '<span class="grp">' + it.g.replace(/</g, '&lt;') + '</span></a>';
    }).join('');
  }

  function applySelection(links) {
    links.forEach(function (l, i) { l.classList.toggle('sel', i === sel); });
    if (links[sel]) links[sel].scrollIntoView({ block: 'nearest' });
  }

  input.addEventListener('input', filter);
  input.addEventListener('focus', function () { if (input.value.trim()) filter(); });
  input.addEventListener('keydown', function (ev) {
    const links = results.querySelectorAll('.navsearch-result');
    if (ev.key === 'ArrowDown') { ev.preventDefault(); sel = Math.min(sel + 1, links.length - 1); applySelection(links); }
    else if (ev.key === 'ArrowUp') { ev.preventDefault(); sel = Math.max(sel - 1, 0); applySelection(links); }
    else if (ev.key === 'Enter') { const l = links[sel >= 0 ? sel : 0]; if (l) location.href = l.getAttribute('href'); }
    else if (ev.key === 'Escape') { results.hidden = true; input.blur(); }
  });
  document.addEventListener('click', function (ev) {
    if (!ev.target.closest('.navsearch')) { results.hidden = true; }
  });
  document.addEventListener('keydown', function (ev) {
    if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === 'k') {
      ev.preventDefault(); input.focus(); input.select();
    }
  });
})();

// Generic segmented control: any page with a `.segtabs[data-seg-group="X"]` of
// `.segtab[data-seg-key]` buttons plus matching `[data-segpanel-group="X"][data-seg-key]`
// panels gets tab-switching for free, so a review/gap list shows one category panel at a
// time instead of every category stacked on the same page (learnings.html, fill-gaps.html).
// The URL hash (e.g. "#pending") both opens a page straight into that tab and keeps the
// existing tile links elsewhere in the dashboard (e.g. the overview's KPI tiles) working.
document.querySelectorAll('.segtabs').forEach(function (tabs) {
  var group = tabs.dataset.segGroup;
  var buttons = tabs.querySelectorAll('.segtab');
  var panels = document.querySelectorAll('[data-segpanel-group="' + group + '"]');
  function activate(key) {
    var found = false;
    buttons.forEach(function (b) {
      var match = b.dataset.segKey === key;
      b.classList.toggle('active', match);
      if (match) found = true;
    });
    if (!found && buttons.length) { key = buttons[0].dataset.segKey; buttons[0].classList.add('active'); }
    panels.forEach(function (p) { p.classList.toggle('active', p.dataset.segKey === key); });
  }
  buttons.forEach(function (b) {
    b.addEventListener('click', function () {
      activate(b.dataset.segKey);
      history.replaceState(null, '', '#' + b.dataset.segKey);
    });
  });
  var initial = (location.hash || '').slice(1);
  activate(initial && tabs.querySelector('[data-seg-key="' + initial + '"]') ? initial : buttons[0].dataset.segKey);
});
"""

# Cache-busting for the static asset files. style.css/app.js are fixed filenames --
# a browser or an intermediate CDN can and does keep serving a stale copy from cache
# indefinitely even after a hard-refresh, since a hard-refresh only forces the browser's
# OWN cache to revalidate, not every proxy/edge cache in between. Appending a hash of
# the actual content as a query string means any real change always produces a new URL,
# so a cached response for the old URL is simply never reused -- this can't go stale.
STYLE_VER = hashlib.md5(STYLE.encode()).hexdigest()[:10]
APPJS_VER = hashlib.md5(APPJS.encode()).hexdigest()[:10]

# ----------------------------------------------------------------- emit
def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT, "components"))
    os.makedirs(os.path.join(OUT, "assets"))
    os.makedirs(os.path.join(OUT, "fill-gaps"), exist_ok=True)
    with open(os.path.join(OUT, "assets", "style.css"), "w") as f:
        f.write(STYLE)
    with open(os.path.join(OUT, "assets", "app.js"), "w") as f:
        f.write(APPJS)
    pages = {
        "index.html": overview_page(),
        "fill-gaps.html": fill_gaps_page(),
        "learnings.html": learnings_page(),
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
    n_gap_pages = 0
    for key, label in CORE_DOC_FIELDS:
        for cid in missing_by_field[key]:
            with open(os.path.join(OUT, "fill-gaps", f"{cid}--{key}.html"), "w") as f:
                f.write(fill_gap_page(cid, key, label))
            n_gap_pages += 1
    print(f"dashboard generated: {len(pages)} shell pages + {len(order)} component pages + "
          f"{n_gap_pages} fill-gap pages -> dashboard/")
    import build_graph  # Phase 3 — regenerates dashboard/graph.html + graph/graph.json
    build_graph.main()

if __name__ == "__main__":
    main()
