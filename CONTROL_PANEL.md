# CONTROL_PANEL.md — The Screen State Panel
### Noise Design System · Optional presentation sidecar

Read this file only when a request asks for a panel. By default, no panel is produced.

1. WHAT IT IS
An optional interactive sidecar rendered beside the phone frame. It lets a person switch the composed screen between the distinct STATES of the flow — the conditions the screen can be in — and see the screen the agent composed for each one. Purpose: make multi-state flows demonstrable from a single output. Examples of states: user online/offline; typing/not typing; list empty/populated; guest/logged in; loading/loaded; search active/idle. Simple screens may have one state and need no panel.

2. WHAT IT SWITCHES — AND WHAT IT DOES NOT
It switches between screen states (conditions of the flow). Each state is a complete screen the agent has already composed and reasoned in full.
It does NOT switch component variants, states, or internals. The viewer has no power to change which variant a component uses, its theme, its scroll state, or any component-level property. Those decisions belong entirely to the agent and are already fixed within each composed state.
Variants may differ between screen states — because the agent may correctly reason a different variant for, say, the offline state than the online state — but that is a consequence of the agent's reasoning, not a lever the viewer pulls. The viewer chooses the condition; the agent already decided what that condition looks like, variants and all.
If a control would let the viewer directly pick a component variant or property, it does not belong on this panel.

3. HOW STATES ARE DETERMINED
The states come from the flow described in the request, not from component metadata. For each state named: the agent composes a complete screen, reasoning every component choice (including which variants) exactly as for any single-state composition, fully governed by AGENT.md. Each composed state is a first-class, rule-complete screen — not a partial overlay or edit of another. The panel then lists these states and lets the viewer switch between the agent-composed screens.

4. WHERE IT SITS AND WHAT IT MUST NOT DO
- Renders OUTSIDE the phone frame — a rail beside it. The phone-framed screen is the deliverable; the panel is chrome around it.
- Switching a state swaps which agent-composed screen is shown inside the frame. The panel drives the view; it is never rendered inside the frame and never becomes part of any exported screen.
- Every state shown must independently satisfy the screen output contract: inside the phone frame, no visible scrollbar, nothing spilling outside the viewport.
- The panel exposes only states the request defined and the agent composed. It never fabricates a state and never exposes component-level controls.

5. WHEN IT IS BUILT
Default: no panel. Built only when the request explicitly asks for it, and only when the flow has more than one state worth switching between. When asked, the agent composes each named state as a full screen, then builds the panel to switch between them.

6. THE TEST, BEFORE EMITTING A PANEL
Ask: "Is every entry on this panel a distinct screen STATE that the request defined and the agent fully composed — and does the panel expose zero component-level controls?" If yes, emit. If any control lets the viewer touch a component variant or property, remove it. The panel switches flows and conditions, never internals.
