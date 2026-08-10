# PLAYBOOK.md — Prompt Playbook
### Noise Design System · How a session with the agent starts, and how the rest of the system is operated

This is the repo-tracked copy of the prompt templates used to start or resume a session with
the composition agent on this repository, plus the non-chat workflows (dashboard review pages,
regeneration commands) that the rest of the system runs on. It lives here, not only in personal
notes, because it changes alongside the system it drives. AGENT.md §6–§7 explains how the agent
itself is expected to recognize and act on each of the chat prompts below; this file is where
their exact wording lives.

Some entries are marked **final** — exact, live wording, sourced directly from this repo's own
code or documented rules. Others are marked **draft/reconstruction** — this session has only
ever seen the prompt's stated purpose, not a verbatim transcript of what you actually typed.
Treat those as a solid starting template, not a transcription, and replace them with your real
wording once you've confirmed it.

---

## 1. Onboard a design system (Phase 1 — ingestion)

**Status: draft — reconstructed from this repo's own documented ingestion rules (README.md
"Sources of truth", INGESTION_REPORT.md), not a transcript of the original session.** Use this
the first time you bring a design system into a repo like this one, or to re-sync after the
Figma library has changed.

What it must establish, at minimum:
- The exact Figma source: file key, page name, and node id — and that **only that page** is
  the source of truth. A component referenced from any other page is out of scope, even if it
  renders correctly, and must be recorded as such rather than quietly pulled in.
- Every top-level component/component-set on that page gets its **top-level** description
  mirrored verbatim into `authored_metadata` — never reworded, cleaned up, or filled in where
  blank. Variant-level descriptions are never read.
- Every exact visual value (size, padding, gap, radius, fill, stroke, typography) is extracted
  from Figma, never guessed or invented.
- Every component gets a recorded `node_id` and `figma_fingerprint`; the whole page is checked
  for name, node-id, and fingerprint collisions before anything is trusted as unique.
- Every internal instance reference is recorded and resolved only if it points at another
  component on the same source page. An off-page reference is flagged unresolved and reported
  — never silently rewired to a same-named component somewhere else.
- `CONTROL_PANEL.md` is a designer-supplied file. If it isn't provided, the agent reports it
  missing; it never authors one itself.
- Output: `registry.yaml`, one file per component under `components/`, and an
  `INGESTION_REPORT.md` summarizing counts, collisions, metadata coverage, and every
  unresolved reference — the same shape as this repo's own.

Suggested wording:
```
I want to onboard a design system into this repository from Figma.

Source: Figma file <file key>, page "<page name>" (node <node id>). Treat only this page as
the source of truth — a component referenced from any other page is out of scope, even if it
renders correctly.

Read every top-level component and component-set on that page via the Figma MCP. For each one,
mirror its top-level authored description into authored_metadata verbatim — never reword it,
clean it up, or invent a missing field — and never read variant-level descriptions. Extract
exact visual values from Figma; never guess one. Record node_id and figma_fingerprint for every
component and check the whole page for name / node-id / fingerprint collisions.

Record every internal instance reference. Mark it resolved only if it points at another
component on this same page; otherwise mark it unresolved and report it — do not rewire it to
a same-named component on a different page.

CONTROL_PANEL.md is a file I supply myself — if it isn't already in the repo, report that it's
missing rather than writing one.

When you're done, write registry.yaml, one file per component under components/, and an
INGESTION_REPORT.md summarizing counts, collisions, metadata coverage, and every unresolved
reference.
```

After ingestion, build the component code library and the dashboard (§7 below) before anyone
starts composing flows against the new repo.

---

## 2. New flow

Used when starting a flow that doesn't exist yet under `screens/` — the first message of a
session building something new from a PRD or a description of the screens.

**Status: draft — replace with your exact working wording before treating this as final.**

What it must establish, at minimum, for AGENT.md's procedure (§3, Steps 0–8) to have
something to run on:
- The screen(s)/flow being requested — normally a short PRD: what each screen shows, what a
  person can do on it, how the screens connect, and explicitly out-of-scope items (see
  the shape of a working example in this repo's own composition history — e.g. the PRD behind
  `screens/manage-my-earbuds-flow.html`).
- An explicit instruction to follow AGENT.md in full: the agent reasons only from this
  repository's registry, snippets, and patterns (Law 1), and halts and reports rather than
  inventing anything the repository doesn't have (Law 2, Law 6).
- That the output is a real, standalone HTML file saved under `screens/` (AGENT.md §7),
  reachable afterward from the dashboard's Prototypes page — not just a chat reply.

Suggested wording:
```
I'm starting a new flow: "<flow title>".

Here's the PRD: <what each screen shows, what a person can do on it, how the screens connect,
and anything explicitly out of scope>.

Follow AGENT.md in full: reason only from this repository's registry, snippets, and patterns
(Law 1), and halt and report rather than inventing anything the repository doesn't have (Law 2,
Law 6). Save the result as a real, standalone HTML file under screens/ — not just a chat reply.
```

Optional — if the flow has more than one meaningful state (online/offline, empty/populated,
guest/logged-in…), add one line asking for a control panel; see §4.

---

## 3. Resume an existing flow

**Status: final — this is the exact, live text, not a draft.** Used to pick a specific,
already-composed flow back up in a **new** session, without replaying the whole original
conversation — expensive, and unnecessary, since the current file under `screens/` already
*is* the ground truth for what exists.

This prompt is **never hand-typed**. It's generated per-card on the dashboard's Prototypes
page (`dashboard/prototypes.html`): every flow card — a real one or a sample — carries a
small speech-bubble tag next to its title. Tapping it opens a "Resume prompt" popup with the
text below already filled in from that card's own title, file, description, and status, plus
a "Copy prompt" button. Paste the copied text as the first message of a fresh session
connected to this repo, then replace the placeholder line with what you actually want done.

Exact template (see `buildResumePrompt` inside `PROTOTYPES_JS` in
`scripts/build_dashboard.py` — that function is the source of truth; everything below is a
description of its output, not a second copy to keep in sync by hand):

```
I'm resuming work on an existing flow: "<title>" (screens/<file>.html).

This flow already exists in the repo. Before changing anything, read the current file at
screens/<file>.html to see its current state, and follow this repo's AGENT.md — especially
the Step 7 composition process, the confirmed entries in learnings.jsonl, and the real
component snippets under components/** — so changes stay consistent with how it and the rest
of the library were built. Don't rebuild it from scratch or re-derive values already sitting
in the registry.

Current description: <description, if any — omitted when there isn't one>
Current status: <status label, if any — omitted when there isn't one>

Here's what I want you to work on next:
<describe the change here>
```

A sample card (no real file under `screens/` yet) gets different second-paragraph wording —
it reads as a starting brief instead of "go read this file," since there's nothing to read.
Same function, same file, for the exact text.

---

## 4. Add a control panel (modifier, not a standalone prompt)

Not its own session-starter — one line you append to a New Flow or Resume prompt. By default
no panel is built (CONTROL_PANEL.md is read only when a request explicitly asks for one). Use
this only when the flow genuinely has more than one state worth switching between.

Suggested wording to append:
```
This flow has more than one state: <list the states, e.g. "online / offline", "empty /
populated", "guest / logged in">. Add a control panel per CONTROL_PANEL.md so I can switch
between the composed states — it switches screen states only, never a component's variant or
internals.
```

---

## 5. Contribute missing metadata (Missing Data page)

Not a chat prompt — a form flow on the dashboard itself, for filling in a documentation field
Figma doesn't have yet (`fill-gaps.html`, one page per component+field gap).

Usage: open **Missing Data** in the sidebar → pick the tab for the missing field (Purpose,
Usage, Design intent, Anti-patterns, Rules) → click into a listed component → its real
rendered preview is shown above a text box — write the field against the thing in view, not
from memory → **copy entry** or **Download learnings.jsonl**, replace the repo's copy, and
commit.

What this actually does: it appends a `field_contribution` entry to `learnings.jsonl` with
`status: "proposed"` (AGENT.md §6). It is stopgap documentation, not authored metadata — it
never touches the Overview page's Documentation coverage numbers, and it isn't binding until a
designer either confirms it on the Agent Learnings page (§6) or folds it into Figma directly
and re-ingests. This is a static site with no backend for this particular page, so nothing
saves by itself — the copy/download step is required.

---

## 6. Review an agent learning (Agent Learnings page)

Not a chat prompt either — this is where a human turns a `proposed` correction or field
contribution into something binding, or discards it.

Usage: open **Agent Learnings** in the sidebar → **Pending review** tab → **Approve** (moves
it to Confirmed, binding from then on per AGENT.md §6) or **Deny** (moves it to Rejected). A
Confirmed or Rejected entry can be **Revoke**d back to Pending if it was decided in error.

On the **live, deployed** dashboard this is real, not a mockup: Approve/Deny/Revoke call
`/api/decide` (`api/decide.js`), which is authenticated (the whole dashboard sits behind a
password) and writes the status change straight back to `learnings.jsonl` in the GitHub repo
via the GitHub API. That push triggers a new Vercel deploy, whose build command re-runs
`python3 scripts/build_dashboard.py` automatically (see `vercel.json`) — so the dashboard
reflects the decision on its own within about a minute, with nothing further to commit or push
by hand. Locally (no `/api/decide` to call), the same decision has to be made by hand: edit the
entry's `status` in `learnings.jsonl`, then regenerate (§7).

Either way, when *you* (the agent) are the one who received the correction in chat rather than
via the dashboard, AGENT.md §6 still applies in full: append the `proposed` entry yourself,
then regenerate, commit, and push in the same turn — never leave a learnings.jsonl change
sitting alongside a stale `dashboard/`.

---

## 7. Regenerate — commands reference

Run from the repo root. Not prompts — the commands the agent (or you) run after any change
that should show up on the dashboard.

| Command | When |
|---|---|
| `python3 scripts/build_dashboard.py` | After **any** repo change that should be visible on the dashboard — new/edited component metadata, a `learnings.jsonl` change, a new flow saved under `screens/`, edits to `readme.yaml`. Also regenerates `graph/graph.json` + `dashboard/graph.html` automatically. This is the one command to reach for by default. |
| `python3 scripts/build_component_library.py` | After a component's `visual_values` change (new/edited variant) — regenerates every `components/**/*.snippet.html` and registry `snippet:` pointers so the agent always copies real, current markup (AGENT.md Step 7) instead of re-deriving it. |
| `python3 scripts/build_graph.py` | Only if you need to regenerate the graph in isolation — normally unnecessary since `build_dashboard.py` already calls this. |
| `python3 -m http.server --directory dashboard` | Serve the generated dashboard locally to review before committing. |

---

## Other prompts

Nothing else from the working playbook has come up in this repo's history yet. If there's
another prompt in regular use — for reviewing a flow, for a specific kind of correction,
anything else — say so and it belongs here too, cross-referenced from AGENT.md the same way
the entries above are.
