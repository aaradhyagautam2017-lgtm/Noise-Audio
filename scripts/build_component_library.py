#!/usr/bin/env python3
"""Phase 4 — Component code library generator for the Noise Audio DLS repo.

WHY THIS EXISTS
Before this script, the repo described every component (authored_metadata +
visual_values) but contained no actual component code — css/ held only token
values. A composition agent had to re-derive real markup/CSS from the layout-
model description on every single request. A live test showed this drifts:
the agent correctly read and quoted rules (e.g. "checkbox sits on the right",
"separator is inset, not full-width") and then wrote code that did the
opposite. The knowledge layer worked; re-deriving code from a text
description, every time, did not.

This script closes that gap. It renders one real, self-contained HTML/CSS
snippet per component — and per real Figma variant that component has —
directly from this repo's own visual_values, reusing the exact rendering
logic already trusted to produce the dashboard's faithful live previews
(render_node / node_style / text_style in build_dashboard.py). Nothing here
is re-guessed: every element, color, and piece of text traces straight back
to the component's own file. An agent composing a screen now copies a real,
already-correct block instead of re-deriving one from prose.

What this does NOT solve: composition patterns that are true of a GROUP of
components but never captured as a single component's visual tree (e.g. how
several master-cards stack into a grouped list with an inset separator —
master-card's own visual_values is one card, not N cards plus a divider).
Those patterns are hand-authored from the exact rule text in patterns/, and
clearly labeled as such — never presented as Figma-extracted.

Usage:  python3 scripts/build_component_library.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_dashboard as bd  # reuses components, node_map, render_node, E — no side effects on import

ROOT = bd.ROOT

# The exact helper-class CSS the dashboard's own preview renderer depends on
# (build_dashboard.py's <style> block, .pv-* rules only) — copied verbatim so
# every snippet file is correct standing completely on its own.
RENDERER_CSS = """  .pv-frame{flex:none}
  .pv-frame[data-stack="1"]{display:flex;align-items:center;justify-content:center}
  .pv-frame[data-stack="1"]>*{position:absolute}
  .pv-text{display:block;flex:none;overflow:hidden}
  .pv-shape{display:block;flex:none;min-width:2px;min-height:2px}
  .pv-shape:not([style*="background"]):not([style*="border"]){background:#d4d4d8;border-radius:2px}
  .pv-icon-placeholder{display:block;flex:none;line-height:0}
  .pv-icon-placeholder svg{display:block}
  .pv-instance{display:flex;flex:none;align-items:center;justify-content:center}
  .pv-instance-label{font-size:9.5px;background:rgba(140,110,220,.13);border-radius:3px;padding:1px 5px}
  .pv-instance-label a{color:#6b4fb8}
  .pv-unresolved{color:#8a6414}
  .pv-note{font-size:10.5px;color:#8e8e96;padding:4px}"""

# Same font files/weights wired into css/tokens.css (see assets/fonts/README.md).
# Embedded directly here too so a snippet renders its real fonts even when
# copied somewhere that hasn't linked css/tokens.css. Every components/<tier>/
# file sits at the same depth from repo root, so one relative path fits all.
FONT_FACE_CSS = """  @font-face {
    font-family: 'Saira';
    font-style: normal;
    font-weight: 100 900;
    font-display: swap;
    src: url('../../assets/fonts/Saira-Variable.woff2') format('woff2');
  }
  @font-face {
    font-family: 'Geist';
    font-style: normal;
    font-weight: 100 900;
    font-display: swap;
    src: url('../../assets/fonts/Geist-Variable.woff2') format('woff2');
  }"""


def variants_of(tree):
    """Mirrors build_dashboard.render_preview's own variant loop: a COMPONENT_SET's
    children are the real variants; anything else is a single, variant-less tree."""
    if tree.get("type") == "COMPONENT_SET":
        kids = tree.get("children")
        if isinstance(kids, dict):
            kids = list(kids.values())
        return [(k.get("name", "?"), k) for k in (kids or [])]
    return [(None, tree)]


def snippet_for(cid):
    comp = bd.components[cid]
    reg = bd.reg_by_id[cid]
    tree = comp.get("visual_values", {}).get("tree")
    if not isinstance(tree, dict):
        return None, "no visual_values.tree stored — nothing to render"

    blocks = []
    for name, vt in variants_of(tree):
        body = bd.render_node(vt, 0, link_prefix="")
        label = bd.E(name) if name else "default (no variants)"
        blocks.append(f'''<!-- variant: {label} · node {bd.E(vt.get("id",""))} -->
<div class="nds-variant" data-variant="{bd.E(name or "")}">
{body}
</div>''')

    header = f'''<!-- ============================================================
     {comp.get("name","").strip()} ({cid}) · {reg["type"]}
     node_id {reg["node_id"]} · figma_fingerprint {reg["figma_fingerprint"]}
     Rendered verbatim from this repo's own visual_values — see
     {reg["file"]}. Not re-derived, not guessed; regenerate with
     scripts/build_component_library.py after any repo change.
     ============================================================ -->
<style>
{FONT_FACE_CSS}
{RENDERER_CSS}
</style>
'''
    return header + "\n".join(blocks) + "\n", None


def patch_registry_with_snippet_paths():
    """Adds a `snippet:` pointer under each component's existing `file:` line,
    mirroring that line's own convention — a small, targeted text edit rather
    than a full re-dump, so registry.yaml's authored formatting/order/comments
    (Phase 1 ingestion output) are left otherwise untouched.

    Idempotent: any `snippet:` line from a previous run is stripped first, so
    re-running this after a repo change never duplicates the pointer."""
    path = os.path.join(ROOT, "registry.yaml")
    with open(path) as f:
        lines = f.readlines()

    lines = [l for l in lines if not re.match(r"^\s*snippet: components/\S+\.snippet\.html\s*$", l)]

    out = []
    current_id = None
    for line in lines:
        m_id = re.match(r"^  - id: (\S+)\s*$", line)
        if m_id:
            current_id = m_id.group(1)
        m_file = re.match(r"^(\s*)file: (components/\S+\.yaml)\s*$", line)
        out.append(line)
        if m_file and current_id in bd.components:
            indent, yaml_path = m_file.groups()
            snippet_path = yaml_path.rsplit(".yaml", 1)[0] + ".snippet.html"
            if os.path.exists(os.path.join(ROOT, snippet_path)):
                out.append(f"{indent}snippet: {snippet_path}\n")

    with open(path, "w") as f:
        f.writelines(out)


def main():
    written, skipped = [], []
    for cid in bd.order:
        reg = bd.reg_by_id[cid]
        out_path = os.path.join(ROOT, reg["file"].rsplit(".yaml", 1)[0] + ".snippet.html")
        content, err = snippet_for(cid)
        if err:
            skipped.append((cid, err))
            continue
        with open(out_path, "w") as f:
            f.write(content)
        written.append(out_path)

    patch_registry_with_snippet_paths()

    print(f"component library generated: {len(written)} snippet files written, "
          f"{len(skipped)} skipped (registry.yaml patched with snippet: pointers)")
    for cid, err in skipped:
        print(f"  skipped {cid}: {err}")


if __name__ == "__main__":
    main()
