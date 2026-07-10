# Ingestion Report — Noise Audio DLS, Phase 1

- **Source**: Figma file `QjVyM5bRXgIOZn8PO1e0eK`, page **Test pilot run** (`2025:148`)
- **Ingested**: 2026-07-10, via Figma MCP (read-only Plugin API queries)
- **Figma account used**: aaradhya.gautam@nexxbase.com (org: Noise)

## 1. Counts

| Category | Count |
|---|---|
| Top-level entities enumerated on the page | **27** (16 component sets + 11 single components) |
| Atoms | 16 |
| Molecules | 2 |
| Organisms | 8 (includes 2 `complex-organism`: `action-sheet`, `modal-sheet`) |
| Token sources | 1 (`spacing component`, node `2036:3057` — carries the authored spacing-token YAML) |
| Variant components (children of sets) | 61 |
| Variable collections | 3 (`color` 40 vars, `tokens` 55 vars light/dark, `numeral` 22 vars) |
| Text styles | 12 · Effect styles: 1 (`Navigation shadow`) · Paint styles: 0 |

## 2. Identifier uniqueness (hard requirement) — PASS

- **Name collisions: 0** — all 27 top-level names unique (after trimming trailing spaces; see §7).
- **Node-id collisions: 0.**
- **Fingerprint collisions: 0** — at top level and across all 61 variants.
- **Components missing a fingerprint: 0.**

## 3. Metadata coverage

- **`metadata: missing`: none.** All 27 top-level entities carry authored YAML in their
  top-level description (variant descriptions were never read, per the ingestion rules).
- Metadata was mirrored **verbatim**. The MCP transport HTML-escapes descriptions
  (`>` arrives as `&gt;`, `&` as `&amp;`); this transport escaping was reversed when writing the
  files, and mirrors were verified against Figma by re-escaped length + head/tail equality on
  sampled components (exact match).

## 4. Missing human-placed files

- **`CONTROL_PANEL.md` was not provided.** The designer supplies this file (screen state panel
  rules); it was not in the upload and the repo had no prior content. It is **absent from the
  repo root** — per the constraints it must not be authored by the ingestion agent. ACTION:
  designer to add it.
- `AGENT.md` was provided by the designer (uploaded) and placed at root unmodified.

## 5. Broken / dangling structural references (Figma instance wiring)

The metadata-declared graph is **fully resolved — 0 broken metadata edges** (every
`used_atoms` / `used_molecules` / `used_cta` / `used_organisms` / `contains` / `relationships`
target exists in the library).

However, the **raw Figma instance wiring** inside several components points at components that
are **not on the ingested page**. These are catalogued per component under
`structural_references` (`resolved: false`) and in `registry.yaml` (`figma_instance_edges`).
Nothing was silently re-pointed; where a same-named library component exists it is recorded as
`same_named_library_component` for the designer to confirm.

### 5a. Duplicate-component drift (a library twin exists, but the instance points elsewhere)

| Component | Instance points at | Location of target | Library twin |
|---|---|---|---|
| `actionables` (all 5 variants) | Chevron `2031:379`, Toggle `2031:392`, Checkbox `2031:406`, Cross `2031:416`, Radio Button `2031:426` | orphaned (detached from any page) | `chevron`, `toggle`, `checkbox`, `cross`, `radio-button` |
| `master-card`, `text-field` (Bold), `action-card`, `modal-card` (hidden) | Actionables set `329:2095` | page “AI Metdata” | `actionables` (`2031:1132`) |
| `checkbox-card` | Actionables `2031:437` (orphaned), Heading-content `2031:372` (orphaned), Cross `2031:416` (orphaned) | orphaned | `actionables`, `heading-content-component`, `cross` |
| `action-card` (list rows) | Radio Button set `395:636` | page “AI Metdata” | `radio-button` (`2031:1178`) — metadata declares rows link to the **actionables** molecule |
| `action-sheet` | “Action Sheet” set `420:1299` | page “06 Building Blocks” | `action-card` (`2096:1434`) — metadata declares it contains **action-card** |
| `modal-sheet` | “Modal” set `786:4487` | page “06 Building Blocks” | `modal-card` (`2097:1930`) — metadata declares it contains **modal-card** |
| `action-sheet`, `modal-sheet` | Status bar `374:7867` | page “AI Metdata” | `status-bar` (`2007:775`) |
| `l1-inner-page-navigation` | system/Chevron `2007:379`, system/cross `2007:411` (both orphaned) | orphaned | `chevron`, `cross` — note: `system/cross` shares fingerprint `96e4573d…` with the orphaned Cross variant, i.e. they are the same published component |

Interpretation: the library page appears to hold **re-created copies** of atoms/organisms while
the organisms' internal wiring still points at older copies on “AI Metdata” / “06 Building
Blocks” or at detached (deleted-from-canvas) sets. The metadata layer describes the intended
graph; the Figma wiring lags it. The registry keeps both layers visible.

### 5b. References with **no** library equivalent (off-page dependencies)

| Referenced component | Node id | Location | Used by |
|---|---|---|---|
| system/Selected device, Device option 1, Device adder, Downloading Success, Store | `231:26268/26277/26218/26254/26234` | page “04 Icons” | `l1-home-page-navigation` |
| system/Restart, system/Downloading Success | `2007:405`, `2007:399` | orphaned | `l1-inner-page-navigation` |
| Transcribe time chips | `2007:416` | orphaned | `l1-inner-page-navigation` (AI Token Banner variant) |
| Circled icon | `301:20193` | page “06 Building Blocks” | `master-card` (leading icon) |
| Bottomsheet heading | `414:3175` | page “06 Building Blocks” | `action-card` (all 8 variants) |
| Home Indicator | `386:1835` | page “06 Building Blocks” | `action-sheet`, `modal-sheet` |
| Profile icon set | `460:985` | page “06 Building Blocks” | `image-asset-placeholder` (XS variant) |

These are functional parts of the components but live outside the declared library page. They
are not modeled as library components (Law: only the page is the universe); each is recorded on
the consuming component so a future phase can either ingest them or the designer can move them
onto the library page.

## 6. Design ↔ metadata drift (variant axes vs authored YAML)

| Component | Authored YAML | Figma | Assessment |
|---|---|---|---|
| `image-asset-placeholder` | variants `xs, s, n, m, device-native-pop-up, transcribing-loading-pop-up`; `n` carries the rule-of-thirds grid | axis `size usage` = `XS, S, M, L, Native popup placeholder, transcribe loading`; the **L** variant carries the grid overlay | Count matches (6=6) but names diverge: YAML `n` ↔ Figma `L` (grid observed in L), YAML `m` ↔ Figma `M`. Needs designer confirmation. |
| `secondary-cta-button` | axis `usage` | Figma axis named **`Usecase`** (Primary uses `Usage`) | Axis-name inconsistency between the two CTAs; values map 1:1. |
| `link-cta` | declares a `state` axis with single value `default` | no State axis in Figma (only `Usecase`) | Consistent in substance (single state); the axis exists only conceptually. |
| `modal-sheet` | `modal-card-variant`, `device-native-pop-up-variant` | `App Modal`, `Device native popup modal` | Values map 1:1; naming differs (YAML gives no figma_value mapping). |
| `action-card` | `categorized-list, list, single-option-card, calendar-card, year-card, month-card, profile-picture-card, find-my-earbuds-card` | `Categorised, list, Single option, Date selector, year selector, Month selector, upload profile picture, Find my earbuds` | 8=8, map 1:1 by meaning; naming differs. |
| `l1-inner-page-navigation` | declares explicit `figma_value` mapping | matches exactly (incl. example-only `Heading` variant) | No drift — model declaration. |
| `toggle`, `checkbox`, `radio-button`, `cross`, `chevron`, `modal-card`, `text-field`, `checkbox-card`, `primary-cta-button` | — | — | Values map 1:1 (case/spacing differences only, e.g. `On state` vs `on`). |

**Undeclared structural dependencies observed in Figma (not in the metadata composition):**

- `text-field` (File upload variant) embeds 3 instances of `heading-content-component` — metadata declares only `chevron`.
- `action-card` rows use direct `Radio Button` instances (foreign set `395:636`) and a `Bottomsheet heading` component — metadata declares `actionables` for selection rows and the header as self-contained.
- `modal-card` contains **hidden** Actionables/Cross instances (visible_count = 0 in both variants) — consistent with its `no-dismissal-affordance` rule at render time, but the wiring exists.
- `l1-home-page-navigation` metadata marks the download/store icons `self-contained`, but they are instances of components on page “04 Icons”.

**Authored-YAML quality flags (mirrored untouched, flagged only):**

- `status-bar` description contains **two top-level `rules:` blocks** and mixed indentation
  (the first block is unindented). A strict YAML parser will merge/drop duplicate keys —
  consumers should treat this block as text, not parse it naively.
- Trailing spaces in Figma layer names: `Heading-content component `, `Card heading ` (kept
  as-is in `name`; ids are clean).

## 7. Tokens

- `tokens` collection (semantic, Light/Dark) fully resolved: every alias chases to a `color`
  primitive. Five tokens hold raw (non-alias) values: the four `Ios/*` glass tokens (raw rgba
  by design) and `button/secondary/pressed`, whose **dark** mode is raw `#ffffff` instead of an
  alias (light mode aliases `gray/500`) — possibly unintended, flagged.
- Authored spacing YAML (from the `spacing component` card) **agrees with the `numeral`
  variable collection on every value** (XS 4 … Rarely use 80; gaps 24/16/12/8; radius
  18/32/8/12; paddings 0/12/16/16/20). Naming mapping: `space.numeral.s` ↔ Figma variable `S`,
  `space.gap.small` ↔ `Gaps/small gap`, `radius.card` ↔ `Radius/Card`, etc.
- `radius.tiniest` (12) and `padding.bottom-sheet` (20) are defined in tokens but were **not
  observed bound** to any ingested component; kept in the catalogs (Figma is master).
- Typography: Saira (headings/sub-headings) + Geist (content) + system fonts inside the status
  bar mock (SF Pro) and one `Roboto Mono` counter inside the download-list modal — the latter
  two have no text-style token (raw font usage; flagged).

## 8. Page hygiene notes (informational)

- The page contains instances named “Master card old” used as examples inside section frames;
  their main component is not on the page and they are not part of any library component, so
  they were excluded from the library.
- The orphaned sets in §5 share fingerprints with `system/*` components (e.g. orphaned Chevron
  set `2031:379` and `system/Chevron` `2007:379` both have key `7d33453c…`), confirming they are
  the same published components seen through stale local copies.

## 9. Result

Repository built: 26 component files (both layers: verbatim authored metadata + extracted
visual values, every one carrying `id`, `name`, `type`, `node_id`, `figma_fingerprint`),
3 token catalogs, `css/tokens.css`, validated `registry.yaml` (0 unresolved metadata edges,
32 dangling Figma instance edges catalogued), `AGENT.md` placed, `screens/` empty.
No screens, dashboards, or graphs were composed.

**Open items for the designer:** provide `CONTROL_PANEL.md`; confirm the
`image-asset-placeholder` n/L naming; decide whether to relink organism internals to the
library copies (§5a) and/or move the §5b off-page dependencies onto the library page;
review the `status-bar` duplicate `rules:` keys and the `button/secondary/pressed` dark value.
