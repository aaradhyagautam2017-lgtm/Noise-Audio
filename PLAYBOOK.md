# PLAYBOOK.md — The Operating Playbook
### Design system → AI agent · Every prompt, every workflow, start to finish

This is the complete operating manual for this system: the exact prompts used to drive the
agent, and the non-chat workflows (dashboard review pages, regeneration commands, deploy
settings) that everything else runs on.

It is written to be **handed to someone who has never seen this repo before**. Together with
`AGENT.md` (the reasoning rulebook the agent obeys) and `scripts/build_dashboard.py` (the
dashboard generator), it is everything a new designer or team needs to stand this workflow up
against their own design system.

**Status markers.** Entries marked **final** are exact, live wording sourced directly from this
repo's code or its documented rules. Entries marked **template** are a working starting point
assembled from the repo's own rules — solid to use as-is, but replace them with your own
wording once you've run them a few times.

---

## The setup kit — what to hand a new team

| File | What it is | Generated? |
|---|---|---|
| `PLAYBOOK.md` | This file. Every prompt and workflow. | No — human-placed |
| `AGENT.md` | The reasoning rulebook. The agent reads this before acting on anything. | No — human-placed |
| `CONTROL_PANEL.md` | Rules for the optional screen-state panel. | No — human-placed |
| `scripts/build_dashboard.py` | The entire dashboard: layout, theme, every page. Run it, get the dashboard. | No — it *is* the generator |
| `scripts/build_component_library.py` | Generates the real component code snippets. See §0. | No |
| `scripts/build_graph.py` | Generates the component graph. Called automatically by the dashboard build. | No |

Everything else in the repo — `registry.yaml`, `components/`, `tokens/`, `css/`, `graph/`,
`dashboard/` — is produced by running the prompts and scripts below against **your** Figma file.

---

## §0. The one mistake that costs the most — read this first

> **The repository must contain real, runnable component code — not just descriptions of it.**

This is the single biggest failure this system has hit, and it is worth understanding before
you run anything, because it is silent and it looks like success.

**What went wrong.** The first build of this repo described every component thoroughly:
`authored_metadata` (the rules) and `visual_values` (exact sizes, colors, padding, radii,
typography, straight from Figma). It contained no actual component code — `css/` held only
token values. So on every single request, the agent had to *re-derive* real HTML/CSS from that
structured description.

That drifts. In a live test the agent correctly read, quoted, and understood the rule — "the
checkbox sits on the right", "the separator is inset, not full-width" — and then wrote code
that did the opposite. Twice. The knowledge layer was fine. Re-deriving code from a description,
fresh, every time, was not.

**The fix.** Every component gets a real, self-contained `<id>.snippet.html` sitting next to its
`<id>.yaml` — actual HTML and CSS, one block per real Figma variant, rendered directly from that
component's own `visual_values`. The agent then **copies a known-correct block** instead of
rewriting one from prose. That is what `scripts/build_component_library.py` produces, and it is
why AGENT.md Step 7 forbids re-derivation outright.

**What this means for you:** the ingestion prompt in §1 *must* ask for the component code
library, and §2 must be run before anyone composes a single screen. Skipping it does not
produce an obvious error — it produces screens that look right and quietly violate your rules.

**The one gap it doesn't close.** Some things are true of a *group* of components and exist in
no single component's visual tree — e.g. how several cards stack into a grouped list with an
inset separator between them (a card's own `visual_values` is one card, not N cards plus a
divider). Those live in `patterns/`, hand-authored directly from the rule text, and are labeled
as such — never presented as Figma-extracted.

---

## §1. Onboard a design system (ingestion)

**Status: template.** Use this the first time you bring a design system into a repo like this
one. This is the longest prompt in the playbook, and deliberately so — almost everything that
goes wrong later traces back to something skipped here.

```
I want to onboard a design system into this repository from Figma.

SOURCE
Figma file <file key>, page "<page name>" (node <node id>).
Treat only this page as the source of truth. A component referenced from any other page is
out of scope, even if it renders correctly — record it as an unresolved reference and report
it. Never silently rewire it to a same-named component on a different page.

METADATA — mirror, never author
Read every top-level component and component-set on that page via the Figma MCP. Mirror each
one's top-level description into `authored_metadata` VERBATIM. Do not reword it, clean it up,
reformat it, or fill in a field that is blank. Never read variant-level descriptions. If a
component has no authored metadata, record it as missing — that gap is real information.

VISUAL VALUES — extract, never guess
Extract exact visual values from Figma for every component: sizes, padding, gaps, radii, fills
(with their bound token names), strokes, effects, typography. Never guess or approximate a
value. Sync the variable collections and text styles into tokens/ and css/ the same way.

IDENTITY
Record `node_id` and `figma_fingerprint` for every component and every variant. Check the whole
page for name, node-id, and fingerprint collisions before trusting anything as unique, and
report the result explicitly.

REFERENCES
Record every internal instance reference. Mark it `resolved: true` only if it points at another
component on this same page; otherwise mark it unresolved and report it. Do not repair, reroute,
or drop a dangling reference — catalogue it.

BUILD THE ACTUAL COMPONENT CODE — do not skip this
Describing a component is not enough. For every component, generate a real, self-contained
`<id>.snippet.html` next to its `<id>.yaml`: actual HTML and CSS, one block per real Figma
variant, rendered directly from that component's own extracted visual_values, with the
fingerprint and node id recorded in the file. Record the path in registry.yaml as `snippet:`.

This is mandatory and it is the highest-risk step. A repo that only describes its components
forces an agent to re-derive CSS from prose on every request, and that drifts silently — it
will correctly quote a rule and then write code that breaks it. The snippets exist so the agent
copies known-correct code instead of rewriting it. Nothing in a snippet may be invented: every
element, value, and string must trace back to that component's own file.

Where a relationship is true of SEVERAL components together and appears in no single
component's visual tree (e.g. how repeated rows group with a separator between them, or where
a screen-level CTA sits), author it as a file under patterns/ directly from the rule text, and
label it in its own header as hand-authored — never as a Figma extraction.

FILES I SUPPLY MYSELF
AGENT.md, PLAYBOOK.md and CONTROL_PANEL.md are human-placed. If one is missing, report it —
never write one yourself.

OUTPUT
- registry.yaml — the index: every component with ids, fingerprints, edges, usage counts,
  and its `snippet:` pointer
- components/<tier>/<id>.yaml + <id>.snippet.html — one pair per component
- tokens/ and css/tokens.css — synced token values
- patterns/ — any hand-authored multi-component patterns, labeled as such
- INGESTION_REPORT.md — counts, collisions, metadata coverage, and every unresolved reference

Then run scripts/build_dashboard.py and confirm the dashboard renders every component.
```

---

## §2. Build / rebuild the component code library

**Status: final — this is a command, not a prompt.**

```
python3 scripts/build_component_library.py
```

Regenerates every `components/**/<id>.snippet.html` and every `snippet:` pointer in
`registry.yaml`, using the same rendering logic that produces the dashboard's live previews.

**Run it:** after ingestion, and after any change to a component's `visual_values` (a new
variant, a resize, a color change). If you're ever unsure whether it's stale, just run it — it's
deterministic and cheap.

---

## §3. New flow

**Status: template.** The first message of a session building a screen or flow that doesn't
exist yet under `screens/`.

```
I'm starting a new flow: "<flow title>".

PRD:
<What each screen shows. What a person can do on it. How the screens connect.
Anything explicitly out of scope.>

Follow AGENT.md in full. Specifically:
- Reason only from this repository — its registry, its component snippets, its patterns
  (Law 1). Nothing from your training data or general UI convention.
- Copy each component's real markup from its components/<tier>/<id>.snippet.html. Do not
  re-derive CSS from visual_values or from the rule text (Step 7).
- Halt and report rather than inventing anything the repository doesn't have (Law 2, Law 6).
- Surface any conflict between what I've asked for and a component's rules — don't quietly
  resolve it either way (Law 5).

Save the result as a real, standalone HTML file under screens/ — not just a chat reply, and
not an in-chat artifact preview. Render it inside the correct device frame, with no visible
scrollbar and nothing spilling outside the screen bounds.

Give me the reasoning trail separately from the screen file — every component you placed, its
id / node_id / fingerprint, the variant you chose, and the rule that justified it.
```

Then regenerate the dashboard (§10) so the flow appears on the Prototypes page.

---

## §4. Resume an existing flow

**Status: final — exact live text. Never hand-typed.**

Generated per-card on the dashboard's Prototypes page. Every flow card carries a small
speech-bubble tag next to its title; tapping it opens a "Resume prompt" popup, pre-filled from
that card's own title, file, description, and status, with a **Copy prompt** button. Paste it as
the first message of a fresh session, then replace the last line with what you want done.

The source of truth is `buildResumePrompt` inside `PROTOTYPES_JS` in `scripts/build_dashboard.py`.
What it produces:

```
I'm resuming work on an existing flow: "<title>" (screens/<file>.html).

This flow already exists in the repo. Before changing anything, read the current file at
screens/<file>.html to see its current state, and follow this repo's AGENT.md — especially
the Step 7 composition process, the confirmed entries in learnings.jsonl, and the real
component snippets under components/** — so changes stay consistent with how it and the rest
of the library were built. Don't rebuild it from scratch or re-derive values already sitting
in the registry.

Current description: <description, if any — the line is omitted when there isn't one>
Current status: <status label, if any — the line is omitted when there isn't one>

Here's what I want you to work on next:
<describe the change here>
```

A **sample** card (no real file under `screens/` yet) gets different second-paragraph wording —
it reads as a starting brief rather than "go read this file," since there's nothing to read yet.

**Why it's generated, not typed:** its pointers are correct by construction. A hand-typed
resume prompt sends the agent looking for a file that may have been renamed, or worse, silently
rebuilds a flow that was already reviewed and approved.

---

## §5. Add a control panel (modifier — append to §3 or §4)

Not a standalone prompt. By default **no panel is built** — `CONTROL_PANEL.md` is read only when
a request explicitly asks for one. Use it only when a flow genuinely has more than one state
worth switching between.

```
This flow has more than one state: <e.g. "online / offline", "list empty / populated",
"guest / logged in">. Add a control panel per CONTROL_PANEL.md so I can switch between the
composed states.

Compose each state as a complete, fully-reasoned screen in its own right. The panel switches
screen states only — it must expose zero component-level controls, and it sits outside the
device frame, never inside it.
```

---

## §6. Correcting the agent

**Status: final — this is AGENT.md §6 behavior.** When the agent gets something wrong, correct
it in plain language. No special format is needed — but here is what must happen next, and it's
worth knowing so you can tell whether it did.

On being corrected, the agent must, **in the same turn**:
1. Append one entry to `learnings.jsonl` with `status: "proposed"` — what it did, what you said,
   and the rule it infers.
2. **Never** edit the component's `authored_metadata`. That field is sourced from Figma; this
   repo never writes back to it.
3. Regenerate the dashboard (`python3 scripts/build_dashboard.py`) — this is the only thing that
   rebuilds the Agent Learnings counts and each affected component's learnings section.
4. Commit the ledger change **and** the regenerated `dashboard/` together, as one commit.
5. Push.

You should never have to notice the dashboard went stale, or ask for it to be rebuilt, committed,
or pushed. If you find yourself asking, that's a bug in the agent's behavior, not a step you own.

A `proposed` entry is **not** binding. It only becomes binding when a human confirms it (§8) —
which exists specifically so the agent can't reinforce its own uncorrected mistakes.

---

## §7. Contribute missing metadata — the Missing Data page

Not a chat prompt. A form flow on the dashboard, for a documentation field Figma doesn't have
filled in yet.

**Sidebar → Missing Data** → pick the tab for the field (Purpose, Usage, Design intent,
Anti-patterns, Rules) → click a listed component → its **real rendered preview** appears above
the text box, so you write the field against the thing in view rather than from memory →
**copy entry** or **Download learnings.jsonl** → replace the repo's copy and commit.

**What it actually does:** appends a `field_contribution` entry with `status: "proposed"`. This
is stopgap documentation, not authored metadata — it never moves the Overview page's
Documentation coverage numbers (those measure the Figma-authored spec specifically), and it
isn't binding until it's confirmed (§8) or folded back into Figma and re-ingested.

**Note:** this page has no backend. Nothing saves by itself — the copy/download + commit step is
required.

---

## §8. Review an agent learning — the Agent Learnings page

Where a human turns a `proposed` entry into something binding, or throws it out.

**Sidebar → Agent Learnings → Pending review** → **Approve** (→ Confirmed, binding from then on)
or **Deny** (→ Rejected). A Confirmed or Rejected entry can be **Revoked** back to Pending if it
was decided in error.

**On the live deployed dashboard this is real, not a mockup.** Approve/Deny/Revoke call
`/api/decide` (`api/decide.js`), which is authenticated — the whole dashboard sits behind a
password gate in `middleware.js`, which is exactly why exposing a write-back endpoint is safe.
It writes the status change straight into `learnings.jsonl` in the GitHub repo via the GitHub
API. That push triggers a Vercel deploy, whose build command re-runs `build_dashboard.py`
automatically. The dashboard catches up on its own in about a minute — nothing to commit by hand.

**Locally** there's no `/api/decide` to call: edit the entry's `status` in `learnings.jsonl`
directly, then regenerate (§10).

---

## §9. Re-sync after Figma changes

**Status: template.** When the design system has moved on in Figma and the repo needs to catch up.

```
The Figma library has changed and this repo needs to re-sync.

Re-run the ingestion against the same source page (file <file key>, page "<page name>",
node <node id>) under the same rules as the original onboarding: only that page is the source
of truth, metadata is mirrored verbatim, visual values are extracted and never guessed,
dangling references are catalogued and never rewired.

Match components by `figma_fingerprint`, not by name — fingerprints are stable across renames
and moves, names are not. Report, before changing anything:
- components added
- components removed
- components whose fingerprint matched but whose visual values or metadata changed
- any authored_metadata that changed, quoted before and after

Then rebuild the component snippets (scripts/build_component_library.py) and regenerate the
dashboard, and tell me if any confirmed entry in learnings.jsonl is now superseded by a rule
that has since been authored directly in Figma.
```

---

## §10. Regeneration — command reference

Run from the repo root.

| Command | When |
|---|---|
| `python3 scripts/build_dashboard.py` | After **any** change that should show on the dashboard — component metadata, `learnings.jsonl`, a new flow under `screens/`, edits to `readme.yaml`. Also regenerates the graph automatically. **This is the default one to reach for.** |
| `python3 scripts/build_component_library.py` | After any change to a component's `visual_values` — new variant, resize, color change. See §0 and §2. |
| `python3 scripts/build_graph.py` | Graph only. Rarely needed directly — the dashboard build already calls it. |
| `python3 -m http.server --directory dashboard` | Serve the dashboard locally to review before committing. |

**Rule of thumb:** never commit a `learnings.jsonl` or component change without the regenerated
`dashboard/` in the same commit.

---

## §11. Deploying the dashboard

Deployed on Vercel as a static site with four small serverless endpoints.

**`vercel.json`** — build command installs `pyyaml` and runs `python3 scripts/build_dashboard.py`;
output directory is `dashboard`. So every push rebuilds the dashboard from repo state
automatically. Nothing generated is ever committed by hand for the deploy's benefit.

**`package.json`** exists only so Vercel treats `middleware.js` and `api/*.js` as ES modules. No
app lives there.

**Environment variables** (Vercel project settings):

| Variable | Purpose |
|---|---|
| `DASHBOARD_PASSWORD_HASH` | The password gate in `middleware.js` |
| `SESSION_SECRET` | Signs the session cookie |
| `GITHUB_TOKEN` | Lets `api/decide.js` etc. write back to the repo |
| `GITHUB_BRANCH` | Fallback when `VERCEL_GIT_COMMIT_REF` isn't set |

**Endpoints:** `api/login.js` (sign in), `api/decide.js` (approve/deny/revoke a learning),
`api/update-flow.js` and `api/delete-flow.js` (edit/remove a flow from the Prototypes page).

---

## Appendix — file map

```
AGENT.md                   READ FIRST — the reasoning rulebook. Human-placed.
PLAYBOOK.md                This file. Human-placed.
CONTROL_PANEL.md           Screen-state panel rules. Human-placed.
readme.yaml                Copy for the dashboard's README page. Human-edited.
registry.yaml              The index: every component, ids, fingerprints, edges, snippet pointers.
learnings.jsonl            Append-only ledger of corrections + field contributions.
INGESTION_REPORT.md        Gaps, drift, dangling references found during ingestion.
components/<tier>/
  <id>.yaml                Identity, variants, references, authored metadata, visual values.
  <id>.snippet.html        REAL component code, per variant. See §0.
patterns/                  Hand-authored multi-component patterns. Labeled as such.
tokens/ · css/             Token catalogs synced from Figma.
graph/graph.json           The component graph, queryable.
screens/                   Composed flows + index.json (title/description/status overlay).
dashboard/                 Generated. Never hand-edit — overwritten every build.
scripts/                   The three generators. See §10.
api/ · lib/ · middleware.js   Auth gate + write-back endpoints. See §11.
```

---

## The short version

1. Onboard from Figma — **and build the real component snippets** (§0, §1, §2).
2. Compose flows with §3; resume them with the generated prompt in §4.
3. Correct the agent in plain language; it logs, regenerates, commits, pushes (§6).
4. Confirm or reject what it logged (§8). Fill real gaps (§7).
5. Regenerate after every change (§10). Push; the deploy rebuilds itself (§11).

The system's whole premise: **the repository is the agent's only universe.** Everything above
exists to keep that universe accurate, complete, and honest about what it doesn't have.
