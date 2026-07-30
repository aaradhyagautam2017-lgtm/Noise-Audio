# Status bar system glyphs

The real Figma file draws the cellular signal, wifi, and battery glyphs as
flattened shapes with no icon data (see `components/atoms/status-bar.yaml`,
visual_values note: *"signal/wifi/battery are system glyphs rendered as solid
shapes"*) — Figma exports them as plain rectangles, not real icon paths. That
made every rendering of the status bar show flat gray/black blocks instead of
a recognizable signal/wifi/battery glyph.

These three are real, properly-licensed icon files fetched to replace those
blocks with an actual glyph, fetched 2026-07-30:

| File | Represents | Source | License |
|---|---|---|---|
| `signal-cellular.svg` | Cellular signal bars | [Bootstrap Icons](https://icons.getbootstrap.com/icons/reception-4/) (`reception-4`) | MIT (`LICENSE-bootstrap-icons.txt`) |
| `signal-wifi.svg` | Wifi | [Bootstrap Icons](https://icons.getbootstrap.com/icons/wifi/) (`wifi`) | MIT (`LICENSE-bootstrap-icons.txt`) |
| `battery.svg` | Battery | [Bootstrap Icons](https://icons.getbootstrap.com/icons/battery-full/) (`battery-full`) | MIT (`LICENSE-bootstrap-icons.txt`) |

Bootstrap Icons was chosen deliberately over cloning Apple's own SF Symbols:
signal bars / wifi arcs / a battery outline are generic, widely-used glyph
shapes, and Bootstrap Icons ships them under a permissive MIT license safe to
vendor directly into this repo.

Wired up in `scripts/build_dashboard.py` via `PLACEHOLDER_ICONS` — the same
mechanism already used for the chevron/cross/checkbox glyphs, extended so a
`placeholder_icon` tag now also works on a `FRAME` node (needed for battery,
which is a 3-shape frame in the captured tree, not a single vector) and not
only a `VECTOR`. Tagged on the real nodes in
`components/atoms/status-bar.yaml`: `Cellular Connection` → `signal-cellular`,
`Wifi` → `signal-wifi`, `Battery` → `battery-icon`. Regenerate the dashboard
and component snippets after any change here with:

```
python3 scripts/build_dashboard.py
python3 scripts/build_component_library.py
```
