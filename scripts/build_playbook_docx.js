const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  PageBreak, LevelFormat, convertInchesToTwip,
} = require('docx');

// Dashboard accent, so the handbook reads as part of the same system.
const ACCENT = '6D4AFF';
const INK = '1A1A1F';
const INK2 = '55555E';
const INK3 = '8A8A93';
const CODE_BG = 'F4F2FF';
const CODE_BORDER = 'D9D2FF';
const RULE_BG = 'FFF4EC';
const RULE_BORDER = 'FFCFAE';
const MONO = 'Consolas';
const UI = 'Calibri';

const CONTENT_W = 9360; // 6.5" usable width in DXA

// ---------- helpers ----------
function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 160 },
    children: [new TextRun({ text, bold: true, size: 32, color: ACCENT, font: UI })],
  });
}

function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 120 },
    children: [new TextRun({ text, bold: true, size: 25, color: INK, font: UI })],
  });
}

function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 200, after: 90 },
    children: [new TextRun({ text, bold: true, size: 22, color: INK2, font: UI })],
  });
}

// Body paragraph. Accepts a string, or an array of {t, b, i, code} run specs.
function p(content, opts = {}) {
  const runs = (typeof content === 'string' ? [{ t: content }] : content).map(
    (r) =>
      new TextRun({
        text: r.t,
        bold: !!r.b,
        italics: !!r.i,
        font: r.code ? MONO : UI,
        size: r.code ? 19 : 21,
        color: r.code ? ACCENT : opts.color || INK2,
        shading: r.code
          ? { type: ShadingType.CLEAR, fill: CODE_BG, color: 'auto' }
          : undefined,
      })
  );
  return new Paragraph({
    spacing: { after: opts.after === undefined ? 140 : opts.after, line: 280 },
    indent: opts.indent ? { left: convertInchesToTwip(0.25) } : undefined,
    children: runs,
  });
}

// A copy-paste prompt block: monospace, shaded, bordered, one Paragraph per line.
function codeBlock(text) {
  const lines = text.replace(/\t/g, '  ').split('\n');
  return lines.map((line, i) => {
    const isFirst = i === 0;
    const isLast = i === lines.length - 1;
    const edge = { style: BorderStyle.SINGLE, size: 6, color: CODE_BORDER };
    const none = { style: BorderStyle.NONE, size: 0, color: 'auto' };
    return new Paragraph({
      spacing: {
        before: isFirst ? 60 : 0,
        after: isLast ? 200 : 0,
        line: 250,
      },
      shading: { type: ShadingType.CLEAR, fill: CODE_BG, color: 'auto' },
      indent: { left: 170, right: 170 },
      // Schema-enforced child order: top, left, bottom, right.
      border: {
        top: isFirst ? edge : none,
        left: edge,
        bottom: isLast ? edge : none,
        right: edge,
      },
      children: [
        new TextRun({ text: line || ' ', font: MONO, size: 18, color: INK }),
      ],
    });
  });
}

// A highlighted callout for the things that must not be skipped.
function callout(lines) {
  const edge = { style: BorderStyle.SINGLE, size: 6, color: RULE_BORDER };
  const none = { style: BorderStyle.NONE, size: 0, color: 'auto' };
  return lines.map((spec, i) => {
    const isFirst = i === 0;
    const isLast = i === lines.length - 1;
    const runs = (typeof spec === 'string' ? [{ t: spec }] : spec).map(
      (r) =>
        new TextRun({
          text: r.t,
          bold: !!r.b,
          italics: !!r.i,
          font: r.code ? MONO : UI,
          size: r.code ? 19 : 21,
          color: INK,
        })
    );
    return new Paragraph({
      spacing: { before: isFirst ? 80 : 40, after: isLast ? 200 : 40, line: 280 },
      shading: { type: ShadingType.CLEAR, fill: RULE_BG, color: 'auto' },
      indent: { left: 170, right: 170 },
      border: {
        top: isFirst ? edge : none,
        left: edge,
        bottom: isLast ? edge : none,
        right: edge,
      },
      children: runs,
    });
  });
}

function bullet(content, level = 0) {
  const runs = (typeof content === 'string' ? [{ t: content }] : content).map(
    (r) =>
      new TextRun({
        text: r.t,
        bold: !!r.b,
        italics: !!r.i,
        font: r.code ? MONO : UI,
        size: r.code ? 19 : 21,
        color: r.code ? ACCENT : INK2,
      })
  );
  return new Paragraph({
    numbering: { reference: 'pb-bullets', level },
    spacing: { after: 80, line: 280 },
    children: runs,
  });
}

function numItem(content) {
  const runs = (typeof content === 'string' ? [{ t: content }] : content).map(
    (r) =>
      new TextRun({
        text: r.t,
        bold: !!r.b,
        italics: !!r.i,
        font: r.code ? MONO : UI,
        size: r.code ? 19 : 21,
        color: r.code ? ACCENT : INK2,
      })
  );
  return new Paragraph({
    numbering: { reference: 'pb-numbers', level: 0 },
    spacing: { after: 80, line: 280 },
    children: runs,
  });
}

// Two- or three-column table. cols = array of DXA widths summing to CONTENT_W.
function table(cols, headerCells, bodyRows) {
  const mkCell = (content, width, isHeader) =>
    new TableCell({
      width: { size: width, type: WidthType.DXA },
      shading: isHeader
        ? { type: ShadingType.CLEAR, fill: CODE_BG, color: 'auto' }
        : undefined,
      margins: { top: 90, bottom: 90, left: 130, right: 130 },
      children: [
        new Paragraph({
          spacing: { after: 0, line: 260 },
          children: (typeof content === 'string' ? [{ t: content }] : content).map(
            (r) =>
              new TextRun({
                text: r.t,
                bold: isHeader || !!r.b,
                font: r.code ? MONO : UI,
                size: r.code ? 17 : 19,
                color: isHeader ? INK : r.code ? ACCENT : INK2,
              })
          ),
        }),
      ],
    });

  return new Table({
    columnWidths: cols,
    width: { size: CONTENT_W, type: WidthType.DXA },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 4, color: CODE_BORDER },
      bottom: { style: BorderStyle.SINGLE, size: 4, color: CODE_BORDER },
      left: { style: BorderStyle.SINGLE, size: 4, color: CODE_BORDER },
      right: { style: BorderStyle.SINGLE, size: 4, color: CODE_BORDER },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 4, color: CODE_BORDER },
      insideVertical: { style: BorderStyle.SINGLE, size: 4, color: CODE_BORDER },
    },
    rows: [
      new TableRow({
        tableHeader: true,
        children: headerCells.map((c, i) => mkCell(c, cols[i], true)),
      }),
      ...bodyRows.map(
        (row) =>
          new TableRow({ children: row.map((c, i) => mkCell(c, cols[i], false)) })
      ),
    ],
  });
}

function spacer(after = 200) {
  return new Paragraph({ spacing: { after }, children: [new TextRun({ text: '' })] });
}

function statusLine(kind, text) {
  return new Paragraph({
    spacing: { after: 140, line: 280 },
    children: [
      new TextRun({
        text: kind === 'final' ? 'STATUS: FINAL  ' : 'STATUS: TEMPLATE  ',
        bold: true,
        font: MONO,
        size: 17,
        color: kind === 'final' ? '1F7A4D' : 'A86414',
      }),
      new TextRun({ text, font: UI, size: 20, color: INK2, italics: true }),
    ],
  });
}

// ---------- document ----------
const children = [];

// Cover
children.push(
  new Paragraph({
    spacing: { before: 1400, after: 0 },
    children: [
      new TextRun({
        text: 'DESIGN SYSTEM  ·  AI AGENT WORKFLOW',
        font: MONO,
        size: 18,
        color: ACCENT,
        bold: true,
      }),
    ],
  }),
  new Paragraph({
    spacing: { before: 200, after: 100 },
    children: [
      new TextRun({ text: 'The Operating Playbook', bold: true, size: 60, color: INK, font: UI }),
    ],
  }),
  new Paragraph({
    spacing: { after: 400 },
    border: {
      bottom: { style: BorderStyle.SINGLE, size: 12, color: ACCENT },
    },
    children: [new TextRun({ text: '' })],
  }),
  p(
    'Every prompt and every workflow needed to run this system end to end — onboarding a design system from Figma, composing screens with an AI agent, correcting it, and keeping the whole thing honest.',
    { color: INK2 }
  ),
  spacer(300),
  p([
    { t: 'Who this is for. ', b: true },
    {
      t: 'Anyone standing this workflow up against their own design system. It assumes no prior knowledge of the repository. Read Section 0 before running anything — it describes the one failure that is silent, expensive, and easy to repeat.',
    },
  ]),
  p([
    { t: 'How to use it. ', b: true },
    { t: 'Every shaded ' },
    { t: 'monospace block', code: true },
    {
      t: ' is a prompt you copy and paste to the agent, filling in anything inside angle brackets. Everything outside those blocks is explanation.',
    },
  ]),
  spacer(300),
  p([{ t: 'Companion files', b: true }]),
  table(
    [2400, 6960],
    ['File', 'What it is'],
    [
      [[{ t: 'AGENT.md', code: true }], 'The reasoning rulebook. The agent reads this in full before acting on anything. Human-placed, never generated.'],
      [[{ t: 'CONTROL_PANEL.md', code: true }], 'Rules for the optional screen-state panel. Human-placed, never generated.'],
      [[{ t: 'build_dashboard.py', code: true }], 'The entire dashboard — layout, theme, every page. Run it, get the dashboard.'],
      [[{ t: 'build_component_library.py', code: true }], 'Generates the real component code snippets. See Section 0.'],
      [[{ t: 'build_graph.py', code: true }], 'Generates the component graph. Called automatically by the dashboard build.'],
    ]
  ),
  new Paragraph({ children: [new PageBreak()] })
);

// ---- Section 0 ----
children.push(h1('0.  The one mistake that costs the most'));
children.push(
  p([{ t: 'Read this before running anything else.', b: true, i: true }])
);
children.push(
  ...callout([
    [
      {
        t: 'The repository must contain real, runnable component code — not just descriptions of it.',
        b: true,
      },
    ],
  ])
);
children.push(h3('What went wrong'));
children.push(
  p('The first build of this repository described every component thoroughly: the authored rules, and the exact visual values pulled from Figma — sizes, colours, padding, radii, typography. What it did not contain was any actual component code. So on every single request, the agent had to re-derive real HTML and CSS from that structured description.')
);
children.push(
  p('That drifts. In a live test the agent correctly read, quoted, and understood the rule — "the checkbox sits on the right", "the separator is inset, not full-width" — and then wrote code that did the opposite. Twice. The knowledge layer was fine. Re-deriving code from a description, fresh, every time, was not.')
);
children.push(
  p([
    { t: 'This is the dangerous kind of failure: it does not throw an error. It produces screens that look right and quietly violate your rules.', b: true },
  ])
);
children.push(h3('The fix'));
children.push(
  p([
    { t: 'Every component gets a real, self-contained ' },
    { t: '<id>.snippet.html', code: true },
    { t: ' sitting next to its ' },
    { t: '<id>.yaml', code: true },
    { t: ' — actual HTML and CSS, one block per real Figma variant, rendered directly from that component\'s own extracted visual values. The agent then ' },
    { t: 'copies a known-correct block', b: true },
    { t: ' instead of rewriting one from prose.' },
  ])
);
children.push(
  p([
    { t: 'That is what ' },
    { t: 'build_component_library.py', code: true },
    { t: ' produces, and it is why the rulebook forbids re-derivation outright.' },
  ])
);
children.push(h3('What this means for you'));
children.push(
  bullet('The ingestion prompt in Section 1 must ask for the component code library. It does — do not remove that block.')
);
children.push(
  bullet('Section 2 must be run before anyone composes a single screen.')
);
children.push(
  bullet('Skipping it produces no visible error. It produces wrong screens that pass review.')
);
children.push(h3('The one gap this does not close'));
children.push(
  p('Some things are true of a group of components and exist in no single component\'s visual tree — for example, how several cards stack into a grouped list with an inset separator between them. A card\'s own visual data describes one card, not several cards plus a divider. Those live in a patterns folder, hand-authored directly from the rule text, and are labelled as such — never presented as extracted from Figma.')
);

children.push(new Paragraph({ children: [new PageBreak()] }));

// ---- Section 1 ----
children.push(h1('1.  Onboard a design system'));
children.push(
  statusLine('template', 'A working starting point — replace with your own wording once you have run it a few times.')
);
children.push(
  p('Use this the first time you bring a design system into a repository. It is the longest prompt in this playbook, deliberately so: almost everything that goes wrong later traces back to something skipped here.')
);
children.push(
  ...codeBlock(`I want to onboard a design system into this repository from Figma.

SOURCE
Figma file <file key>, page "<page name>" (node <node id>).
Treat only this page as the source of truth. A component referenced from any other page is
out of scope, even if it renders correctly — record it as an unresolved reference and report
it. Never silently rewire it to a same-named component on a different page.

METADATA — mirror, never author
Read every top-level component and component-set on that page via the Figma MCP. Mirror each
one's top-level description into authored_metadata VERBATIM. Do not reword it, clean it up,
reformat it, or fill in a field that is blank. Never read variant-level descriptions. If a
component has no authored metadata, record it as missing — that gap is real information.

VISUAL VALUES — extract, never guess
Extract exact visual values from Figma for every component: sizes, padding, gaps, radii, fills
(with their bound token names), strokes, effects, typography. Never guess or approximate a
value. Sync the variable collections and text styles into tokens/ and css/ the same way.

IDENTITY
Record node_id and figma_fingerprint for every component and every variant. Check the whole
page for name, node-id, and fingerprint collisions before trusting anything as unique, and
report the result explicitly.

REFERENCES
Record every internal instance reference. Mark it resolved only if it points at another
component on this same page; otherwise mark it unresolved and report it. Do not repair,
reroute, or drop a dangling reference — catalogue it.

BUILD THE ACTUAL COMPONENT CODE — do not skip this
Describing a component is not enough. For every component, generate a real, self-contained
<id>.snippet.html next to its <id>.yaml: actual HTML and CSS, one block per real Figma
variant, rendered directly from that component's own extracted visual_values, with the
fingerprint and node id recorded in the file. Record the path in registry.yaml as "snippet:".

This is mandatory and it is the highest-risk step. A repo that only describes its components
forces an agent to re-derive CSS from prose on every request, and that drifts silently — it
will correctly quote a rule and then write code that breaks it. The snippets exist so the
agent copies known-correct code instead of rewriting it. Nothing in a snippet may be
invented: every element, value, and string must trace back to that component's own file.

Where a relationship is true of SEVERAL components together and appears in no single
component's visual tree (e.g. how repeated rows group with a separator between them, or where
a screen-level CTA sits), author it as a file under patterns/ directly from the rule text, and
label it in its own header as hand-authored — never as a Figma extraction.

FILES I SUPPLY MYSELF
AGENT.md, PLAYBOOK.md and CONTROL_PANEL.md are human-placed. If one is missing, report it —
never write one yourself.

OUTPUT
- registry.yaml — the index: every component with ids, fingerprints, edges, usage counts,
  and its snippet pointer
- components/<tier>/<id>.yaml + <id>.snippet.html — one pair per component
- tokens/ and css/tokens.css — synced token values
- patterns/ — any hand-authored multi-component patterns, labeled as such
- INGESTION_REPORT.md — counts, collisions, metadata coverage, every unresolved reference

Then run scripts/build_dashboard.py and confirm the dashboard renders every component.`)
);

// ---- Section 2 ----
children.push(h1('2.  Build or rebuild the component code library'));
children.push(statusLine('final', 'This is a command, not a prompt.'));
children.push(...codeBlock('python3 scripts/build_component_library.py'));
children.push(
  p([
    { t: 'Regenerates every ' },
    { t: 'components/**/<id>.snippet.html', code: true },
    { t: ' and every snippet pointer in the registry, using the same rendering logic that produces the dashboard\'s live previews.' },
  ])
);
children.push(
  p([
    { t: 'Run it: ', b: true },
    { t: 'after ingestion, and after any change to a component\'s visual values — a new variant, a resize, a colour change. If you are ever unsure whether it is stale, just run it. It is deterministic and cheap.' },
  ])
);

children.push(new Paragraph({ children: [new PageBreak()] }));

// ---- Section 3 ----
children.push(h1('3.  Start a new flow'));
children.push(statusLine('template', 'The first message of a session building a screen or flow that does not exist yet.'));
children.push(
  ...codeBlock(`I'm starting a new flow: "<flow title>".

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
id / node_id / fingerprint, the variant you chose, and the rule that justified it.`)
);
children.push(
  p([
    { t: 'Afterwards, regenerate the dashboard (Section 10) so the flow appears on the Prototypes page.' },
  ])
);

// ---- Section 4 ----
children.push(h1('4.  Resume an existing flow'));
children.push(statusLine('final', 'Exact live text. This one is never hand-typed.'));
children.push(
  p('Generated per-card on the dashboard\'s Prototypes page. Every flow card carries a small speech-bubble tag next to its title. Tapping it opens a "Resume prompt" popup, pre-filled from that card\'s own title, file, description, and status, with a Copy prompt button. Paste it as the first message of a fresh session, then replace the last line with what you want done.')
);
children.push(
  ...codeBlock(`I'm resuming work on an existing flow: "<title>" (screens/<file>.html).

This flow already exists in the repo. Before changing anything, read the current file at
screens/<file>.html to see its current state, and follow this repo's AGENT.md — especially
the Step 7 composition process, the confirmed entries in learnings.jsonl, and the real
component snippets under components/** — so changes stay consistent with how it and the rest
of the library were built. Don't rebuild it from scratch or re-derive values already sitting
in the registry.

Current description: <description, if any — the line is omitted when there isn't one>
Current status: <status label, if any — the line is omitted when there isn't one>

Here's what I want you to work on next:
<describe the change here>`)
);
children.push(
  p('A sample card, with no real file saved yet, gets different second-paragraph wording — it reads as a starting brief rather than "go read this file", since there is nothing to read.')
);
children.push(
  p([
    { t: 'Why it is generated rather than typed: ', b: true },
    { t: 'its pointers are correct by construction. A hand-typed resume prompt sends the agent looking for a file that may have been renamed — or worse, silently rebuilds a flow that was already reviewed and approved.' },
  ])
);

// ---- Section 5 ----
children.push(h1('5.  Add a control panel'));
children.push(statusLine('template', 'A modifier you append to Section 3 or Section 4 — not a standalone prompt.'));
children.push(
  p('By default no panel is built. Use this only when a flow genuinely has more than one state worth switching between.')
);
children.push(
  ...codeBlock(`This flow has more than one state: <e.g. "online / offline", "list empty / populated",
"guest / logged in">. Add a control panel per CONTROL_PANEL.md so I can switch between the
composed states.

Compose each state as a complete, fully-reasoned screen in its own right. The panel switches
screen states only — it must expose zero component-level controls, and it sits outside the
device frame, never inside it.`)
);

children.push(new Paragraph({ children: [new PageBreak()] }));

// ---- Section 6 ----
children.push(h1('6.  Correcting the agent'));
children.push(statusLine('final', 'No special prompt format needed — but here is what must happen next.'));
children.push(
  p('When the agent gets something wrong, correct it in plain language. What matters is what it does next, so you can tell whether it behaved correctly.')
);
children.push(p([{ t: 'In the same turn, it must:', b: true }]));
children.push(
  numItem([
    { t: 'Append one entry to ' },
    { t: 'learnings.jsonl', code: true },
    { t: ' with status "proposed" — what it did, what you said, and the rule it infers.' },
  ])
);
children.push(
  numItem([
    { t: 'Never', b: true },
    { t: ' edit the component\'s authored metadata. That field comes from Figma; this repository never writes back to it.' },
  ])
);
children.push(
  numItem([
    { t: 'Regenerate the dashboard. This is the only thing that rebuilds the Agent Learnings counts and each affected component\'s learnings section.' },
  ])
);
children.push(
  numItem('Commit the ledger change and the regenerated dashboard together, as one commit.')
);
children.push(numItem('Push.'));
children.push(
  ...callout([
    [
      { t: 'You should never have to notice the dashboard went stale, or ask for it to be rebuilt, committed, or pushed. If you find yourself asking, that is a bug in the agent\'s behaviour — not a step you own.' },
    ],
  ])
);
children.push(
  p([
    { t: 'A proposed entry is ' },
    { t: 'not', b: true },
    { t: ' binding. It becomes binding only when a human confirms it (Section 8) — which exists specifically so the agent cannot reinforce its own uncorrected mistakes.' },
  ])
);

// ---- Section 7 ----
children.push(h1('7.  Contribute missing metadata'));
children.push(statusLine('final', 'A form on the dashboard, not a chat prompt.'));
children.push(
  p('For a documentation field Figma does not have filled in yet.')
);
children.push(
  p([
    { t: 'Sidebar → Missing Data', b: true },
    { t: ' → pick the tab for the field (Purpose, Usage, Design intent, Anti-patterns, Rules) → click a listed component → its real rendered preview appears above the text box, so you write the field against the thing in view rather than from memory → ' },
    { t: 'copy entry', b: true },
    { t: ' or ' },
    { t: 'Download learnings.jsonl', b: true },
    { t: ' → replace the repository\'s copy and commit.' },
  ])
);
children.push(
  p([
    { t: 'What it actually does: ', b: true },
    { t: 'appends a field-contribution entry with status "proposed". This is stopgap documentation, not authored metadata — it never moves the Overview page\'s documentation coverage numbers, which measure the Figma-authored spec specifically. It is not binding until confirmed (Section 8) or folded back into Figma and re-ingested.' },
  ])
);
children.push(
  p([
    { t: 'Note: ', b: true },
    { t: 'this page has no backend. Nothing saves by itself — the copy or download step, then a commit, is required.' },
  ])
);

// ---- Section 8 ----
children.push(h1('8.  Review an agent learning'));
children.push(statusLine('final', 'Where a human makes a proposed entry binding, or throws it out.'));
children.push(
  p([
    { t: 'Sidebar → Agent Learnings → Pending review', b: true },
    { t: ' → ' },
    { t: 'Approve', b: true },
    { t: ' (becomes Confirmed, binding from then on) or ' },
    { t: 'Deny', b: true },
    { t: ' (becomes Rejected). A Confirmed or Rejected entry can be ' },
    { t: 'Revoked', b: true },
    { t: ' back to Pending if it was decided in error.' },
  ])
);
children.push(h3('On the live deployed dashboard, this is real'));
children.push(
  p('Approve, Deny and Revoke are not a mockup. They call an authenticated endpoint — the whole dashboard sits behind a password gate, which is exactly why exposing a write-back endpoint is safe. It writes the status change straight into the ledger file in the GitHub repository via the GitHub API. That push triggers a deploy, whose build command re-runs the dashboard generator automatically. The dashboard catches up on its own in about a minute, with nothing to commit by hand.')
);
children.push(
  p([
    { t: 'Locally', b: true },
    { t: ' there is no endpoint to call: edit the entry\'s status in ' },
    { t: 'learnings.jsonl', code: true },
    { t: ' directly, then regenerate (Section 10).' },
  ])
);

children.push(new Paragraph({ children: [new PageBreak()] }));

// ---- Section 9 ----
children.push(h1('9.  Re-sync after Figma changes'));
children.push(statusLine('template', 'When the design system has moved on and the repository needs to catch up.'));
children.push(
  ...codeBlock(`The Figma library has changed and this repo needs to re-sync.

Re-run the ingestion against the same source page (file <file key>, page "<page name>",
node <node id>) under the same rules as the original onboarding: only that page is the source
of truth, metadata is mirrored verbatim, visual values are extracted and never guessed,
dangling references are catalogued and never rewired.

Match components by figma_fingerprint, not by name — fingerprints are stable across renames
and moves, names are not. Report, before changing anything:
- components added
- components removed
- components whose fingerprint matched but whose visual values or metadata changed
- any authored_metadata that changed, quoted before and after

Then rebuild the component snippets (scripts/build_component_library.py) and regenerate the
dashboard, and tell me if any confirmed entry in learnings.jsonl is now superseded by a rule
that has since been authored directly in Figma.`)
);

// ---- Section 10 ----
children.push(h1('10.  Regeneration commands'));
children.push(p('Run from the repository root.'));
children.push(
  table(
    [4200, 5160],
    ['Command', 'When to run it'],
    [
      [
        [{ t: 'python3 scripts/build_dashboard.py', code: true }],
        [{ t: 'After any change that should show on the dashboard — component metadata, the learnings ledger, a new flow, README copy. Also regenerates the graph. ', }, { t: 'This is the default one to reach for.', b: true }],
      ],
      [
        [{ t: 'python3 scripts/build_component_library.py', code: true }],
        'After any change to a component\'s visual values — new variant, resize, colour change. See Sections 0 and 2.',
      ],
      [
        [{ t: 'python3 scripts/build_graph.py', code: true }],
        'Graph only. Rarely needed directly — the dashboard build already calls it.',
      ],
      [
        [{ t: 'python3 -m http.server --directory dashboard', code: true }],
        'Serve the dashboard locally to review before committing.',
      ],
    ]
  )
);
children.push(spacer(160));
children.push(
  ...callout([
    [
      { t: 'Rule of thumb: ', b: true },
      { t: 'never commit a ledger or component change without the regenerated dashboard in the same commit.' },
    ],
  ])
);

// ---- Section 11 ----
children.push(h1('11.  Deploying the dashboard'));
children.push(
  p('Deployed as a static site with a few small serverless endpoints. The build command installs the YAML dependency and runs the dashboard generator; the output directory is the generated dashboard folder. So every push rebuilds the dashboard from repository state automatically — nothing generated is ever committed by hand for the deploy\'s benefit.')
);
children.push(h3('Environment variables'));
children.push(
  table(
    [3400, 5960],
    ['Variable', 'Purpose'],
    [
      [[{ t: 'DASHBOARD_PASSWORD_HASH', code: true }], 'The password gate in front of the whole dashboard'],
      [[{ t: 'SESSION_SECRET', code: true }], 'Signs the session cookie'],
      [[{ t: 'GITHUB_TOKEN', code: true }], 'Lets the review endpoints write back to the repository'],
      [[{ t: 'GITHUB_BRANCH', code: true }], 'Fallback when the platform\'s own branch variable is not set'],
    ]
  )
);
children.push(spacer(160));
children.push(h3('Endpoints'));
children.push(bullet([{ t: 'login', code: true }, { t: ' — sign in to the dashboard' }]));
children.push(bullet([{ t: 'decide', code: true }, { t: ' — approve, deny or revoke an agent learning' }]));
children.push(bullet([{ t: 'update-flow', code: true }, { t: ' and ', }, { t: 'delete-flow', code: true }, { t: ' — edit or remove a flow from the Prototypes page' }]));

children.push(new Paragraph({ children: [new PageBreak()] }));

// ---- Appendix ----
children.push(h1('Appendix  ·  File map'));
children.push(
  ...codeBlock(`AGENT.md                   READ FIRST — the reasoning rulebook. Human-placed.
PLAYBOOK.md                This document. Human-placed.
CONTROL_PANEL.md           Screen-state panel rules. Human-placed.
readme.yaml                Copy for the dashboard's README page. Human-edited.
registry.yaml              The index: every component, ids, fingerprints, edges, snippets.
learnings.jsonl            Append-only ledger of corrections + field contributions.
INGESTION_REPORT.md        Gaps, drift, dangling references found during ingestion.
components/<tier>/
  <id>.yaml                Identity, variants, references, authored metadata, visual values.
  <id>.snippet.html        REAL component code, per variant. See Section 0.
patterns/                  Hand-authored multi-component patterns. Labeled as such.
tokens/ · css/             Token catalogs synced from Figma.
graph/graph.json           The component graph, queryable.
screens/                   Composed flows + a title/description/status overlay.
dashboard/                 Generated. Never hand-edit — overwritten every build.
scripts/                   The three generators. See Section 10.
api/ · lib/ · middleware.js   Auth gate + write-back endpoints. See Section 11.`)
);

children.push(h1('The short version'));
children.push(numItem([{ t: 'Onboard from Figma — ' }, { t: 'and build the real component snippets', b: true }, { t: ' (Sections 0, 1, 2).' }]));
children.push(numItem('Compose flows with Section 3; resume them with the generated prompt in Section 4.'));
children.push(numItem('Correct the agent in plain language; it logs, regenerates, commits and pushes (Section 6).'));
children.push(numItem('Confirm or reject what it logged (Section 8). Fill real gaps (Section 7).'));
children.push(numItem('Regenerate after every change (Section 10). Push; the deploy rebuilds itself (Section 11).'));
children.push(spacer(240));
children.push(
  ...callout([
    [
      { t: 'The system\'s whole premise: the repository is the agent\'s only universe. ', b: true },
      { t: 'Everything in this playbook exists to keep that universe accurate, complete, and honest about what it does not have.' },
    ],
  ])
);

const doc = new Document({
  numbering: {
    config: [
      {
        reference: 'pb-bullets',
        levels: [
          {
            level: 0,
            format: LevelFormat.BULLET,
            text: '•',
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 460, hanging: 240 } } },
          },
          {
            level: 1,
            format: LevelFormat.BULLET,
            text: '◦',
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 900, hanging: 240 } } },
          },
        ],
      },
      {
        reference: 'pb-numbers',
        levels: [
          {
            level: 0,
            format: LevelFormat.DECIMAL,
            text: '%1.',
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 460, hanging: 240 } } },
          },
        ],
      },
    ],
  },
  styles: {
    default: {
      document: { run: { font: UI, size: 21, color: INK2 } },
    },
  },
  sections: [
    {
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 1080, bottom: 1080, left: 1440, right: 1440 },
        },
      },
      children,
    },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync('/home/user/Noise-Audio/The-Operating-Playbook.docx', buf);
  console.log('written:', buf.length, 'bytes');
});
