# Noise Audio — Component Library Repository

This repository is the machine-navigable mirror of the **Noise Audio Design Language System**,
ingested from Figma (file `QjVyM5bRXgIOZn8PO1e0eK`, page **Test pilot run**, node `2025:148`).

It is built for an AI composition agent. **Read `AGENT.md` first** — it is the reasoning
rulebook that governs how anything in this repository may be used. `PLAYBOOK.md` holds the
exact prompts used to start or resume a session; AGENT.md §7 explains how the agent is
expected to tell the two apart.

## Sources of truth

1. **Figma (via MCP)** — exact visual values (radius, padding, spacing, dimensions, colors,
   typography). Figma is the master; this repo mirrors it. Every `visual_values` block and every
   token value in `tokens/` and `css/` was extracted from Figma, never invented.
2. **Authored YAML metadata** — semantics and rules, written by the designer in each Figma
   component's description. Mirrored **verbatim** into each component file's
   `authored_metadata` block. Never edited, reworded, or cleaned up.

## Layout

```
AGENT.md                  READ FIRST — the reasoning rulebook (human-placed; not generated).
PLAYBOOK.md               The prompts used to start a new flow or resume an existing one
                          (human-placed; not generated) — see AGENT.md §7.
CONTROL_PANEL.md          Screen state panel rules (human-placed; not generated).
registry.yaml             The map: every component with ids, fingerprints, edges, usage counts.
INGESTION_REPORT.md       Gaps, drift, dangling references found during ingestion.
components/
  atoms/                  16 atoms      (id.yaml + id.snippet.html per component)
  molecules/              2 molecules
  organisms/              8 organisms   (includes the two complex-organisms: the sheets)
tokens/
  colors.yaml             Figma variable collections `color` (primitives) + `tokens` (semantic, light/dark)
  typography.yaml         Figma local text styles + the single effect style
  spacing.yaml            Designer-authored spacing YAML (mirrored verbatim) + `numeral` variables
css/
  tokens.css              Concrete token values synced from Figma (light + dark custom properties)
patterns/                 Hand-authored multi-component patterns (Phase 4) — see below.
dashboard/                Designer dashboard — a static, browsable site generated FROM this repo (Phase 2).
graph/
  graph.json              The canonical component graph in queryable form (Phase 3) — nodes with
                          id/node_id/figma_fingerprint/usage_count, typed directional edges,
                          and traversal conventions for the agent. Generated from registry.yaml.
scripts/
  build_dashboard.py      Regenerates dashboard/ in one pass from the current repo state.
  build_graph.py          Regenerates graph/graph.json + dashboard/graph.html from registry.yaml
                          (also invoked automatically by build_dashboard.py).
  build_component_library.py  Regenerates components/**/*.snippet.html + registry.yaml's
                          `snippet:` pointers from the current repo state (Phase 4).
screens/                  Composed flows (AGENT.md §7), each a real standalone HTML file, plus
                          index.json — a human-editable title/description/status overlay.
                          Empty at the end of ingestion; populated only once the agent starts
                          composing flows. Browsed from the dashboard's Prototypes page.
```

## Component code library (Phase 4)

Every component has a sibling `<id>.snippet.html` next to its `<id>.yaml` (path
recorded in registry.yaml as `snippet:`) — real, self-contained HTML/CSS for
every actual Figma variant of that component, rendered directly from its own
`visual_values` by `scripts/build_component_library.py`. Nothing in a snippet
is re-derived or guessed: it reuses the exact rendering logic that already
produces the dashboard's faithful live previews. Regenerate after any repo
change with:

```
python3 scripts/build_component_library.py
```

This exists so a composition agent can copy real, already-correct markup
instead of re-deriving CSS from a text description on every request — the
latter is what let two components ship with a violated rule (wrong
checkbox-card variant side, a full-width instead of inset master-card
separator) even though the agent had read and quoted the correct rule text.

`patterns/` holds the handful of things that are true of *several* components
placed together (e.g. the grouped-list container and its inset separator, and
screen-level CTA placement) that no single component's `visual_values` can
capture on its own. Each pattern file is hand-authored directly from the exact
rule text or designer decision it implements and says so in its own header —
never presented as a Figma extraction.

## Designer dashboard

`dashboard/index.html` is a Material-style component-library site: foundations pages (colors,
typography, spacing/radius), a component graph, and a detail page per component with a schematic
live preview rendered from the extracted visual values, a copyable Figma fingerprint, the full
authored metadata rendered from the stored YAML, and clickable composition / relationships /
used-by links. It is a **rendered view of the repo only** — it contains nothing that is not in
the repo, flags repo gaps (a missing CONTROL_PANEL.md, dangling Figma references, unparseable
metadata) with warning badges, and regenerates with:

```
python3 scripts/build_dashboard.py
```

Serve it locally with `python3 -m http.server --directory dashboard` or open
`dashboard/index.html` directly.

## Component graph

`dashboard/graph.html` is the interactive canonical wiring, generated by
`scripts/build_graph.py` from `registry.yaml` only: a live, Obsidian-style force-directed graph —
Atoms seed near the center, Molecules and Organisms grow outward in concentric bands as they
compose from what's inside them, nodes colored by type and sized by usage count, solid structural
edges (part → whole), dashed behavioral edges, and registry-flagged dangling references drawn in
red to ghost markers on their own outer ring (shown, never repaired). The canvas pans and zooms,
nodes are draggable, hovering spotlights a component's neighborhood, and clicking routes to its
dashboard page. The page renders client-side from the exact JSON it embeds — the same data an
agent queries at `graph/graph.json`, whose every node maps back to the repo file (`id`), the
Figma in-file locator (`node_id`), and the stable component key
(`figma_fingerprint`). Traversal conventions (top-down, lateral, upward) are documented inside
the JSON itself.

## Component files

Each `components/**/**.yaml` carries:

- `id` — canonical id, taken from the authored metadata (`component.id`)
- `name`, `type`, `node_id`, `figma_fingerprint` (the stable component key), `figma_type`
- `variant_axes` / `variants` — each variant with its own node id and fingerprint
- `structural_references` — the raw Figma instance wiring observed inside the component,
  each marked `resolved: true` (points at a library component) or `resolved: false`
  (points outside the ingested page — catalogued, never silently rewired)
- `authored_metadata` — the designer's YAML, verbatim
- `visual_values` — the extracted node tree with exact sizes, padding, gaps, radii, fills
  (hex + bound token name), strokes, effects, and typography

## Navigation contract

Per `AGENT.md`: load `registry.yaml` and the token catalogs first; traverse the graph
top-down (organisms → molecules → atoms); resolve children through the graph; resolve every
visual value from the token layer. Do not scan component files blindly.

## Regeneration

This repo is generated from Figma. To re-sync, re-run the Phase 1 ingestion against the same
page and compare fingerprints — the `figma_fingerprint` values are stable across renames and
moves and are the identity anchor for every component.
