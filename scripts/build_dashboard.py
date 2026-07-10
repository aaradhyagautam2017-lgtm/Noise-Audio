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

E = lambda s: html.escape(str(s), quote=True)

# ----------------------------------------------------------------- shell
def sidebar(prefix, active):
    def item(href, label, key, count=None, warn=0):
        cls = "active" if key == active else ""
        badge = f'<span class="count">{count}</span>' if count is not None else ""
        wbadge = f'<span class="warnbadge" title="dangling Figma references">{warn}</span>' if warn else ""
        return f'<a class="navitem {cls}" href="{prefix}{href}">{E(label)}{badge}{wbadge}</a>'
    parts = [f'''
    <aside class="sidebar">
      <div class="appswitcher">
        <span class="applogo">N</span>
        <select onchange="void 0" title="App switcher">
          <option selected>{E(registry["app"])}</option>
        </select>
      </div>
      <nav>
        <div class="navgroup">Overview</div>
        {item("index.html", "Overview", "overview")}
        {item("graph.html", "Component graph", "graph")}
        <div class="navgroup">Foundations <span class="count">3</span></div>
        {item("foundations-colors.html", "Colors & tokens", "colors")}
        {item("foundations-typography.html", "Typography", "typography")}
        {item("foundations-spacing.html", "Spacing & radius", "spacing")}
    ''']
    for gname, ids in group_defs:
        parts.append(f'<div class="navgroup">{gname} <span class="count">{len(ids)}</span></div>')
        for cid in ids:
            dangling = sum(1 for e in reg_by_id[cid].get("figma_instance_edges", []) or [] if not e["resolved"])
            parts.append(item(f"components/{cid}.html", components[cid]["name"].strip(), f"c-{cid}", warn=dangling))
    parts.append("</nav></aside>")
    return "".join(parts)

def page(title, active, body, prefix=""):
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)} — {E(registry["app"])} DLS</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Saira:wght@400;500;600&family=Geist:wght@400;500;600&family=Roboto+Mono:wght@400;500&display=swap" rel="stylesheet">
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
    dangling = [e for e in reg.get("figma_instance_edges", []) or [] if not e["resolved"]]
    warns = []
    if dangling:
        items = "".join(
            f'<li><b>{E(e["references"])}</b> (node <code>{E(e["ref_node_id"])}</code>) — {E(e.get("external_location",""))}'
            + (f'; same-named library component: <a href="{e["same_named_library_component"]}.html">{e["same_named_library_component"]}</a>'
               if e.get("same_named_library_component") else "") + "</li>"
            for e in dangling)
        warns.append(warn(f'{len(dangling)} Figma instance reference(s) inside this component point outside '
                          f'the ingested library page (see INGESTION_REPORT.md):<ul>{items}</ul>'))

    ids_block = (f'<div class="idsblock"><h3>Identifiers</h3>'
                 + copyable("Name", name)
                 + copyable("Node id", comp["node_id"])
                 + copyable("Figma fingerprint", comp["figma_fingerprint"])
                 + '</div>')

    variants_block = ""
    if comp.get("variant_axes"):
        rows = "".join(
            f'<tr><td>{E(v["name"])}</td><td><code>{E(v["node_id"])}</code></td>'
            f'<td class="fpcell"><code>{E(v["figma_fingerprint"])}</code>'
            f'<button class="copybtn small" data-copy="{E(v["figma_fingerprint"])}">⧉</button></td>'
            f'<td>{v["width"]}×{v["height"]}</td></tr>'
            for v in comp["variants"])
        axes = "".join(f'<span class="pill">{E(a)}: {E(", ".join(map(str, vals)))}</span>'
                       for a, vals in comp["variant_axes"].items())
        variants_block = (f'<section class="metasection"><h3>Figma variants</h3>'
                          f'<div class="pills">{axes}</div>'
                          f'<table class="table"><thead><tr><th>Figma variant</th><th>Node id</th>'
                          f'<th>Fingerprint</th><th>Size</th></tr></thead><tbody>{rows}</tbody></table></section>')

    # composition & relationships (from registry — resolved ids, all clickable)
    comp_rel = []
    uses = (reg.get("structural_edges", {}) or {}).get("uses", []) or []
    if uses:
        comp_rel.append('<h4>Is built from</h4><ul class="linklist">' + "".join(
            f'<li><a href="{t}.html">{t}</a> <span class="dim">({TYPE_BADGE.get(reg_by_id[t]["type"],"")})</span></li>' for t in uses) + "</ul>")
    beh = reg.get("behavioral_edges", []) or []
    if beh:
        comp_rel.append('<h4>Relationships</h4><ul class="linklist">' + "".join(
            f'<li><a href="{e["target"]}.html">{e["target"]}</a> <span class="rel">{E(e["relation"])}</span></li>' for e in beh) + "</ul>")
    ub = used_by.get(cid, [])
    if ub:
        comp_rel.append('<h4>Used by</h4><ul class="linklist">' + "".join(
            f'<li><a href="{s}.html">{s}</a> <span class="rel">{E(r)}</span></li>' for s, r in ub) + "</ul>")
    if not comp_rel:
        comp_rel.append('<p class="dim">No declared composition edges or inbound references.</p>')
    comp_block = f'<section class="metasection"><h3>Composition & relationships</h3>{"".join(comp_rel)}</section>'

    body = f"""
    <header class="pagehead">
      <div><h1>{E(name)}</h1>
      <span class="typebadge t-{E(reg["type"])}">{E(TYPE_BADGE.get(reg["type"], reg["type"]))}</span>
      <span class="dim">usage count: {reg.get("usage_count", 0)}</span></div>
      <div class="dim">source file: <code>{E(reg["file"])}</code></div>
    </header>
    {"".join(warns)}
    <section class="metasection"><h3>Preview</h3>{render_preview(comp)}</section>
    {ids_block}
    {variants_block}
    {comp_block}
    <h2 class="metaheader">Metadata <span class="dim">(rendered from the stored authored YAML)</span></h2>
    {render_metadata(comp)}
    """
    return page(name, f"c-{cid}", body, prefix="../")

# ----------------------------------------------------------------- foundations
def colors_page():
    cols = tokens_colors["collections"]
    prim = cols["color"]["variables"]
    sem = cols["tokens"]["variables"]
    prim_rows = "".join(
        f'<tr><td><span class="swatch" style="background:{E(v)}"></span></td><td>{E(k)}</td>'
        f'<td><code>{E(v)}</code><button class="copybtn small" data-copy="{E(v)}">⧉</button></td></tr>'
        for k, v in prim.items())
    def resolve(val):
        if isinstance(val, str) and val.startswith("alias:"):
            return prim.get(val[6:]), val[6:]
        return val, None
    sem_rows = []
    for k, modes in sem.items():
        lv, la = resolve(modes.get("light")); dv, da = resolve(modes.get("dark"))
        sem_rows.append(
            f'<tr><td>{E(k)}</td>'
            f'<td><span class="swatch" style="background:{E(lv)}"></span><code>{E(lv)}</code>'
            + (f' <span class="dim">← {E(la)}</span>' if la else ' <span class="dim">(raw)</span>') + '</td>'
            f'<td class="darkcell"><span class="swatch" style="background:{E(dv)}"></span><code>{E(dv)}</code>'
            + (f' <span class="dim">← {E(da)}</span>' if da else ' <span class="dim">(raw)</span>') + '</td></tr>')
    body = f"""
    <header class="pagehead"><h1>Colors & tokens</h1></header>
    <p class="dim">Synced from Figma variable collections <code>color</code> (primitives) and <code>tokens</code> (semantic, Light/Dark). Source: <code>tokens/colors.yaml</code>.</p>
    <section class="metasection"><h3>Semantic tokens ({len(sem)}) — Light / Dark</h3>
    <table class="table"><thead><tr><th>Token</th><th>Light</th><th>Dark</th></tr></thead><tbody>{''.join(sem_rows)}</tbody></table></section>
    <section class="metasection"><h3>Primitive scale ({len(prim)})</h3>
    <table class="table"><thead><tr><th></th><th>Variable</th><th>Value</th></tr></thead><tbody>{prim_rows}</tbody></table></section>
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

# ----------------------------------------------------------------- overview + graph
def overview_page():
    counts = registry["counts"]
    cards = []
    for gname, ids in group_defs:
        items = "".join(
            f'''<a class="card" href="components/{cid}.html">
                 <div class="cardname">{E(components[cid]["name"].strip())}</div>
                 <div class="dim">{E(cid)}</div>
                 <div class="cardmeta"><span class="typebadge t-{E(reg_by_id[cid]["type"])}">{E(TYPE_BADGE.get(reg_by_id[cid]["type"]))}</span>
                 {"<span class=warnbadge title=dangling-references>" + str(sum(1 for e in reg_by_id[cid].get("figma_instance_edges",[]) or [] if not e["resolved"])) + "</span>" if any(not e["resolved"] for e in reg_by_id[cid].get("figma_instance_edges",[]) or []) else ""}</div>
               </a>''' for cid in ids)
        cards.append(f'<h2>{gname} <span class="count">{len(ids)}</span></h2><div class="cardgrid">{items}</div>')
    warns = []
    if control_panel_missing:
        warns.append(warn("<b>CONTROL_PANEL.md is missing from the repo root.</b> It is designer-provided and was not supplied in Phase 1 (see INGESTION_REPORT.md §4)."))
    de = validation.get("dangling_figma_instance_edges", 0)
    if de:
        warns.append(warn(f"<b>{de} dangling Figma instance references</b> across the library — instances whose main component lives outside the ingested page. Flagged on each affected component page and catalogued in INGESTION_REPORT.md §5."))
    body = f"""
    <header class="landing">
      <h1>{E(registry["app"])} <span class="dim">Design Language System</span></h1>
      <p class="tagline">The machine-navigable mirror of the Noise Audio Design Language System — ingested from Figma; this dashboard is a rendered view of the repository and never a second source of truth.</p>
      <div class="quicklinks">
        <a class="btn" href="graph.html">Component graph</a>
        <a class="btn" href="foundations-colors.html">Foundations</a>
        <a class="btn" href="../registry.yaml">registry.yaml</a>
        <a class="btn" href="../INGESTION_REPORT.md">Ingestion report</a>
        <a class="btn" href="{E(registry["source"]["figma_url"])}">Figma source ↗</a>
      </div>
      <div class="pills">
        <span class="pill">{counts["atoms"]} atoms</span>
        <span class="pill">{counts["molecules"]} molecules</span>
        <span class="pill">{counts["organisms"]} organisms</span>
        <span class="pill">{counts["token_sources"]} token source</span>
        <span class="pill">ingested {E(registry["generated"])}</span>
      </div>
    </header>
    {''.join(warns)}
    {''.join(cards)}
    """
    return page("Overview", "overview", body)

# The Component graph page (dashboard/graph.html) and graph/graph.json are generated
# by scripts/build_graph.py (Phase 3), invoked from main() so a dashboard rebuild
# always regenerates the graph from the same registry state.

# ----------------------------------------------------------------- assets
STYLE = """
:root{--bg:#f7f7f7;--panel:#ffffff;--ink:#171717;--ink2:#696969;--ink3:#919191;--line:#ededed;
--accent:#292929;--warn-bg:#fff7e8;--warn-line:#d4882f;--atom:#1c8a4c;--molecule:#b6732b;--organism:#c42e2e;}
*{box-sizing:border-box}
body{margin:0;font-family:'Geist',system-ui,sans-serif;background:var(--bg);color:var(--ink);font-size:14px}
h1,h2,h3,h4{font-family:'Saira',sans-serif;font-weight:600}
a{color:inherit}
.layout{display:flex;min-height:100vh}
.sidebar{width:264px;flex:none;background:var(--panel);border-right:1px solid var(--line);padding:14px 10px;position:sticky;top:0;height:100vh;overflow-y:auto}
.appswitcher{display:flex;gap:8px;align-items:center;margin-bottom:14px}
.applogo{width:30px;height:30px;border-radius:9px;background:var(--accent);color:#f7f7f7;display:flex;align-items:center;justify-content:center;font-family:'Saira';font-weight:600}
.appswitcher select{flex:1;padding:6px 8px;border:1px solid var(--line);border-radius:8px;background:var(--bg);font:inherit}
.navgroup{margin:14px 6px 4px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink3)}
.navitem{display:flex;align-items:center;gap:6px;padding:6px 10px;border-radius:8px;text-decoration:none;color:var(--ink);font-size:13px}
.navitem:hover{background:var(--bg)}
.navitem.active{background:var(--accent);color:#f7f7f7}
.count{margin-left:auto;background:var(--line);color:var(--ink2);border-radius:99px;padding:0 7px;font-size:11px}
.navitem.active .count{background:#454545;color:#ededed}
.warnbadge{background:var(--warn-bg);border:1px solid var(--warn-line);color:#8a5218;border-radius:99px;padding:0 6px;font-size:10px}
.main{flex:1;padding:28px 36px;max-width:1080px}
.pagehead h1{margin:0 8px 6px 0;display:inline-block}
.landing h1{font-size:34px;margin:0}
.tagline{color:var(--ink2);max-width:640px}
.quicklinks{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
.btn{background:var(--panel);border:1px solid var(--line);border-radius:99px;padding:7px 14px;text-decoration:none;font-size:13px}
.btn:hover{border-color:var(--ink3)}
.pills{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}
.pill{background:var(--panel);border:1px solid var(--line);border-radius:99px;padding:3px 10px;font-size:12px;color:var(--ink2)}
.typebadge{display:inline-block;border-radius:99px;padding:2px 10px;font-size:11px;color:#fff;vertical-align:middle}
.t-atom{background:var(--atom)}.t-molecule{background:var(--molecule)}.t-organism{background:var(--organism)}.t-complex-organism{background:#7a1616}
.dim{color:var(--ink3);font-weight:400;font-size:12px}
.rel{color:var(--ink3);font-size:12px;font-style:italic}
.cardgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px;margin-bottom:22px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:14px;text-decoration:none;display:block}
.card:hover{border-color:var(--ink3)}
.cardname{font-family:'Saira';font-weight:500;font-size:15px}
.cardmeta{margin-top:8px;display:flex;gap:6px;align-items:center}
.metasection{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:16px 18px;margin:14px 0}
.metasection h3{margin:0 0 10px}
.metaheader{margin-top:28px}
.kvs{margin:2px 0 2px 2px;border-left:2px solid var(--line);padding-left:10px}
.kv{margin:4px 0}
.kv .k{font-weight:600;font-size:12.5px;color:var(--ink2)}
.kv .v{margin-left:2px}
ul{margin:4px 0;padding-left:20px}
ul.rules li{margin:5px 0}
.ruleid{background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:1px 6px;font-size:11px}
.table{border-collapse:collapse;width:100%;font-size:13px}
.table th{text-align:left;color:var(--ink3);font-weight:500;font-size:12px;border-bottom:1px solid var(--line);padding:6px 8px}
.table td{border-bottom:1px solid var(--line);padding:6px 8px;vertical-align:middle}
.darkcell{background:#171717;color:#ededed;border-radius:4px}
.swatch{display:inline-block;width:18px;height:18px;border-radius:6px;border:1px solid var(--line);vertical-align:middle;margin-right:8px}
.warning{background:var(--warn-bg);border:1px solid var(--warn-line);border-radius:12px;padding:10px 14px;margin:12px 0;font-size:13px}
.warning ul{margin:6px 0 0}
.missing{color:var(--warn-line);font-style:italic}
.idsblock{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:16px 18px;margin:14px 0}
.idsblock h3{margin:0 0 10px}
.idrow{display:flex;align-items:center;gap:8px;margin:6px 0}
.idlabel{width:130px;color:var(--ink3);font-size:12px;flex:none}
.idvalue{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:4px 10px;font-family:'Roboto Mono',monospace;font-size:12px;overflow-wrap:anywhere}
.copybtn{border:1px solid var(--line);background:var(--panel);border-radius:8px;padding:4px 10px;cursor:pointer;font:inherit;font-size:12px}
.copybtn:hover{border-color:var(--ink3)}
.copybtn.copied{background:var(--atom);color:#fff;border-color:var(--atom)}
.copybtn.small{padding:2px 7px;margin-left:6px}
.fpcell code{font-size:11px}
.linklist{list-style:none;padding-left:2px}
.linklist li{margin:4px 0}
.rawyaml{margin-top:14px}
.rawyaml summary{cursor:pointer;color:var(--ink2);font-size:13px}
.rawyaml pre{background:#171717;color:#ededed;border-radius:12px;padding:14px;overflow:auto;font-size:12px;font-family:'Roboto Mono',monospace}
.footer{margin-top:36px;padding-top:12px;border-top:1px solid var(--line);color:var(--ink3);font-size:12px}
/* preview */
.pv-caption{color:var(--ink3);font-size:12px;margin:0 0 10px}
.pv-block{margin:10px 0 18px}
.pv-variantname{font-size:12.5px;font-weight:600;margin-bottom:6px}
.pv-stage{background:repeating-conic-gradient(#f0f0f0 0 25%,#fafafa 0 50%) 0 0/16px 16px;border:1px solid var(--line);border-radius:12px;padding:16px;overflow-x:auto}
.pv-scale{transform-origin:top left}
.pv-frame{flex:none}
.pv-frame[data-stack="1"]{display:flex;align-items:center;justify-content:center}
.pv-frame[data-stack="1"]>*{position:absolute}
.pv-text{display:block;flex:none;overflow:hidden}
.pv-shape{display:block;flex:none;min-width:2px;min-height:2px}
.pv-shape:not([style*="background"]):not([style*="border"]){background:#d9d9d9;border-radius:2px}
.pv-instance{display:flex;flex:none;align-items:center;justify-content:center;outline:1.5px dashed #8a38f5;outline-offset:-1.5px;border-radius:6px;overflow:hidden}
.pv-instance-label{font-size:10px;background:#8a38f51a;border-radius:4px;padding:1px 5px;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pv-instance-label a{color:#8a38f5;text-decoration:none}
.pv-unresolved{color:#8a5218}
.pv-note{font-size:11px;color:var(--ink3);padding:4px}
/* typography page */
.typo-row{display:flex;gap:20px;align-items:center;border-bottom:1px solid var(--line);padding:12px 0}
.typo-meta{width:380px;flex:none}
.typo-sample{flex:1;overflow:hidden;white-space:nowrap}
.shadow-sample{width:120px;height:56px;border-radius:12px;background:#fff}
.barviz{display:inline-block;height:12px;background:var(--accent);border-radius:3px;vertical-align:middle}
.radviz{display:inline-block;width:36px;height:36px;border:2px solid var(--accent);vertical-align:middle}
/* graph */
.graphwrap{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:10px;overflow:auto}
.graph{width:100%;min-width:900px}
.g-col{font-family:'Saira';font-size:14px;font-weight:600;fill:var(--ink2)}
.g-node{fill:#fff;stroke:var(--line)}
.g-node.t-atom{stroke:var(--atom)}.g-node.t-molecule{stroke:var(--molecule)}.g-node.t-organism{stroke:var(--organism)}.g-node.t-complex-organism{stroke:#7a1616}
.g-label{font-size:10.5px;text-anchor:middle;fill:var(--ink)}
.g-edge{fill:none;stroke:#b5b5b5;stroke-width:1.2;opacity:.75}
.g-beh{stroke-dasharray:4 3;stroke:#8a38f5;opacity:.55}
@media (prefers-color-scheme: dark){ /* dashboard chrome stays light-neutral by design; component tokens page shows both modes explicitly */ }
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
