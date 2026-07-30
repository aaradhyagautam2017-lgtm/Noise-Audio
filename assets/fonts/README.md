# Fonts

Installed locally so no composed screen or dashboard page depends on an
external CDN at render time. Fetched 2026-07-30 from Google Fonts.

| File | Family | Source | License |
|---|---|---|---|
| `Saira-Variable.woff2` | Saira (`--font-heading`) | https://fonts.google.com/specimen/Saira | `OFL-Saira.txt` (SIL OFL 1.1) |
| `Geist-Variable.woff2` | Geist (`--font-content`) | https://fonts.google.com/specimen/Geist | `OFL-Geist.txt` (SIL OFL 1.1) |

Both are variable fonts (`wght` axis, full 100–900 range in one file). This
repo's typography only ever uses weights 400/500/600 (see
`tokens/typography.yaml`), which is why one file per family is enough —
Google Fonts itself serves these same three static weights from this exact
file for both families.

Wired up via `@font-face` in `css/tokens.css`, which is what makes
`--font-heading` / `--font-content` and every `.text-*` utility class
actually render as Saira/Geist instead of silently falling back to a system
font. Every generated component snippet (`components/**/*.snippet.html`)
also embeds the same `@font-face` block directly, so a snippet renders
correctly even when copied somewhere that hasn't linked `css/tokens.css`.

To re-fetch (e.g. to add a weight or refresh a version):
```
curl -A "Mozilla/5.0" "https://fonts.googleapis.com/css2?family=Saira:wght@400;500;600&family=Geist:wght@400;500;600&display=swap"
```
then download the `latin` subset URL for each family from the response.
