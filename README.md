# Noise Audio — Component Library Repository

This repository is the machine-navigable mirror of the **Noise Audio Design Language System**,
ingested from Figma (file `QjVyM5bRXgIOZn8PO1e0eK`, page **Test pilot run**, node `2025:148`).

It is built for an AI composition agent. **Read `AGENT.md` first** — it is the reasoning
rulebook that governs how anything in this repository may be used.

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
CONTROL_PANEL.md          Screen state panel rules (human-placed) — NOT YET PROVIDED, see report.
registry.yaml             The map: every component with ids, fingerprints, edges, usage counts.
INGESTION_REPORT.md       Gaps, drift, dangling references found during ingestion.
components/
  atoms/                  16 atoms      (id.yaml per component)
  molecules/              2 molecules
  organisms/              8 organisms   (includes the two complex-organisms: the sheets)
tokens/
  colors.yaml             Figma variable collections `color` (primitives) + `tokens` (semantic, light/dark)
  typography.yaml         Figma local text styles + the single effect style
  spacing.yaml            Designer-authored spacing YAML (mirrored verbatim) + `numeral` variables
css/
  tokens.css              Concrete token values synced from Figma (light + dark custom properties)
screens/                  Empty in Phase 1 — no screens are composed during ingestion.
```

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
