# PLAYBOOK.md — Prompt Playbook
### Noise Design System · How a session with the agent starts

This is the repo-tracked copy of the prompt templates used to start or resume a session with
the composition agent on this repository. It lives here, not only in personal notes, because
it changes alongside the system it drives — most recently with the addition of the Resume
prompt below. AGENT.md §7 explains how the agent itself is expected to recognize and act on
each of these; this file is where their exact wording lives.

This file is still being assembled — see "Status" under each prompt below.

---

## 1. New flow

Used when starting a flow that doesn't exist yet under `screens/` — the first message of a
session building something new from a PRD or a description of the screens.

**Status: draft — replace with your exact working wording before treating this as final.**
This session hasn't seen your literal prompt text verbatim, only its stated purpose ("only
when I'm starting to build a new flow"), so what follows is a reconstruction of what it must
accomplish, not a transcription of what you actually type. Paste your real version in here
when you're ready.

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

## 2. Resume an existing flow

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

## Other prompts

Nothing else from the working playbook has come up in this repo's history yet — the two
above are the only ones this session has seen described or built. If there's another prompt
in regular use — for reviewing a flow, for a specific kind of correction, anything else — say
so and it belongs here too, cross-referenced from AGENT.md the same way the two above are.
