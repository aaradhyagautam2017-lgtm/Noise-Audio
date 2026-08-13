const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  PageBreak, LevelFormat,
} = require('docx');

const SP = __dirname;
const REPO = path.resolve(__dirname, '..');
// Normalize CRLF -> LF. A stray \r rides into the TextRun and Word splits it into an
// extra empty paragraph, silently doubling the line spacing of the whole block.
const read = (p) =>
  fs.readFileSync(p, 'utf-8').replace(/\r\n?/g, '\n').replace(/\s+$/, '');

// Dashboard accent, so the handbook reads as part of the same system.
const ACCENT = '6D4AFF';
const INK = '1A1A1F';
const INK2 = '4E4E57';
const CODE_BG = 'F5F3FF';
const CODE_BORDER = 'D9D2FF';
const WARN_BG = 'FFF4EC';
const WARN_BORDER = 'FFC79E';
const NEW_BG = 'ECFBF3';
const NEW_BORDER = 'A8E6C4';
const MONO = 'Consolas';
const UI = 'Calibri';
const CONTENT_W = 9360;

const runsOf = (content, base = {}) =>
  (typeof content === 'string' ? [{ t: content }] : content).map(
    (r) =>
      new TextRun({
        text: r.t,
        bold: r.b !== undefined ? r.b : !!base.b,
        italics: !!r.i,
        font: r.code ? MONO : UI,
        size: r.code ? (base.size ? base.size - 2 : 19) : base.size || 21,
        color: r.code ? ACCENT : r.color || base.color || INK2,
        shading: r.code ? { type: ShadingType.CLEAR, fill: CODE_BG, color: 'auto' } : undefined,
      })
  );

const h1 = (text) =>
  new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 380, after: 170 },
    children: [new TextRun({ text, bold: true, size: 32, color: ACCENT, font: UI })],
  });

const h2 = (text) =>
  new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 300, after: 130 },
    children: [new TextRun({ text, bold: true, size: 25, color: INK, font: UI })],
  });

const h3 = (text) =>
  new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 210, after: 95 },
    children: [new TextRun({ text, bold: true, size: 22, color: INK2, font: UI })],
  });

const p = (content, opts = {}) =>
  new Paragraph({
    spacing: { after: opts.after === undefined ? 140 : opts.after, line: 285 },
    children: runsOf(content, opts),
  });

// One Paragraph per line, shaded + bordered: an unmistakable copy-paste block.
function block(text, tone) {
  const bg = tone === 'file' ? 'F7F7F9' : CODE_BG;
  const bd = tone === 'file' ? 'DEDEE3' : CODE_BORDER;
  const lines = text.replace(/\t/g, '  ').split('\n');
  const edge = { style: BorderStyle.SINGLE, size: 6, color: bd };
  const none = { style: BorderStyle.NONE, size: 0, color: 'auto' };
  return lines.map((line, i) => {
    const first = i === 0, last = i === lines.length - 1;
    return new Paragraph({
      spacing: { before: first ? 70 : 0, after: last ? 220 : 0, line: 245 },
      shading: { type: ShadingType.CLEAR, fill: bg, color: 'auto' },
      indent: { left: 170, right: 170 },
      border: { top: first ? edge : none, left: edge, bottom: last ? edge : none, right: edge },
      children: [new TextRun({ text: line || ' ', font: MONO, size: 17, color: INK })],
    });
  });
}

function callout(lines, kind = 'warn') {
  const bg = kind === 'new' ? NEW_BG : WARN_BG;
  const bd = kind === 'new' ? NEW_BORDER : WARN_BORDER;
  const edge = { style: BorderStyle.SINGLE, size: 6, color: bd };
  const none = { style: BorderStyle.NONE, size: 0, color: 'auto' };
  return lines.map((spec, i) => {
    const first = i === 0, last = i === lines.length - 1;
    return new Paragraph({
      spacing: { before: first ? 90 : 40, after: last ? 210 : 40, line: 285 },
      shading: { type: ShadingType.CLEAR, fill: bg, color: 'auto' },
      indent: { left: 170, right: 170 },
      border: { top: first ? edge : none, left: edge, bottom: last ? edge : none, right: edge },
      children: runsOf(spec, { color: INK }),
    });
  });
}

const bullet = (content, level = 0) =>
  new Paragraph({
    numbering: { reference: 'hb-bullets', level },
    spacing: { after: 85, line: 285 },
    children: runsOf(content),
  });

const numItem = (content) =>
  new Paragraph({
    numbering: { reference: 'hb-numbers', level: 0 },
    spacing: { after: 85, line: 285 },
    children: runsOf(content),
  });

// Label strip that sits directly above a copy block.
function promptLabel(text, badge) {
  const kids = [
    new TextRun({ text: text, bold: true, font: MONO, size: 18, color: ACCENT }),
  ];
  if (badge) {
    kids.push(new TextRun({ text: '   ' + badge, bold: true, font: MONO, size: 16, color: badge.includes('UNCHANGED') ? '1F7A4D' : 'B0560F' }));
  }
  return new Paragraph({ spacing: { before: 230, after: 60 }, children: kids });
}

function table(cols, header, rows) {
  const cell = (content, width, isHead) =>
    new TableCell({
      width: { size: width, type: WidthType.DXA },
      shading: isHead ? { type: ShadingType.CLEAR, fill: CODE_BG, color: 'auto' } : undefined,
      margins: { top: 90, bottom: 90, left: 130, right: 130 },
      children: [
        new Paragraph({
          spacing: { after: 0, line: 265 },
          children: runsOf(content, { size: 19, b: isHead, color: isHead ? INK : INK2 }),
        }),
      ],
    });
  const b = { style: BorderStyle.SINGLE, size: 4, color: CODE_BORDER };
  return new Table({
    columnWidths: cols,
    width: { size: CONTENT_W, type: WidthType.DXA },
    borders: { top: b, bottom: b, left: b, right: b, insideHorizontal: b, insideVertical: b },
    rows: [
      new TableRow({ tableHeader: true, children: header.map((c, i) => cell(c, cols[i], true)) }),
      ...rows.map((r) => new TableRow({ children: r.map((c, i) => cell(c, cols[i], false)) })),
    ],
  });
}

const gap = (after = 200) => new Paragraph({ spacing: { after }, children: [new TextRun({ text: '' })] });
const pageBreak = () => new Paragraph({ children: [new PageBreak()] });

// ============================================================ content
const C = [];

// ---------- COVER ----------
C.push(
  new Paragraph({
    spacing: { before: 1200, after: 0 },
    children: [new TextRun({ text: 'DESIGN SYSTEM  ·  AI COMPOSITION AGENT', font: MONO, size: 18, color: ACCENT, bold: true })],
  }),
  new Paragraph({
    spacing: { before: 220, after: 60 },
    children: [new TextRun({ text: 'Design-to-Screen', bold: true, size: 66, color: INK, font: UI })],
  }),
  new Paragraph({
    spacing: { after: 130 },
    children: [new TextRun({ text: 'with AI', bold: true, size: 66, color: ACCENT, font: UI })],
  }),
  new Paragraph({
    spacing: { after: 330 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: ACCENT } },
    children: [new TextRun({ text: '' })],
  }),
  p('How to turn a Figma component library into a screen-building assistant.', { size: 26, color: INK }),
  p('A complete, step-by-step handbook — with every prompt ready to copy.', { size: 22 }),
  gap(300),
  ...callout([
    [{ t: 'The golden rule that makes all of this work. ', b: true },
     { t: 'The assistant may only use pieces that exist in your library. It is never allowed to invent anything. If it cannot build your request from the library, it tells you what is missing instead of guessing.' }],
  ]),
  gap(200),
  p([{ t: 'How to read this handbook. ', b: true },
     { t: 'Every shaded ' }, { t: 'monospace block', code: true },
     { t: ' is something you copy and paste, filling in anything inside double braces or angle brackets. Everything outside those blocks is explanation. Prompts are labelled where they have been revised since the previous edition.' }]),
  pageBreak()
);

// ---------- CONTENTS ----------
C.push(h1('Contents'));
const toc = [
  ['1.', 'What this is, in plain words'],
  ['2.', 'The moving parts'],
  ['3.', 'The whole flow at a glance'],
  ['4.', 'Before you start — the one mistake that costs the most'],
  ['5.', 'Chapter A — Setting up the library'],
  ['', '     Step 1 — Get your components ready in Figma'],
  ['', '     Step 2 — Write the metadata     [PROMPT — Metadata author]'],
  ['', '     Step 3 — Open Claude Code and connect it to Figma'],
  ['', '     Step 4 — Build the repository     [PROMPT 1 — revised]'],
  ['', '     Step 5 — Build the dashboard     [PROMPT 2 — revised]'],
  ['', '     Step 6 — Build the connection graph     [PROMPT 3 — revised]'],
  ['', '     Step 7 — Build the component code library     [PROMPT 4]'],
  ['6.', 'Chapter B — Using the library to build screens'],
  ['', '     Step 1 — Paste the Starting Prompt'],
  ['', '     Step 2 — Describe the screen you want'],
  ['', '     Step 3 — Resume an existing flow'],
  ['', '     Step 4 — Show multiple states (optional)'],
  ['', '     Step 5 — Correcting the assistant'],
  ['7.', 'Chapter C — Keeping the library healthy'],
  ['', '     Missing Data  ·  Agent Learnings  ·  Re-syncing  ·  Regeneration commands'],
  ['8.', 'The rulebook files — AGENT.md, CONTROL_PANEL.md'],
  ['9.', 'Quick reference — what to paste, and when'],
];
toc.forEach(([n, t]) =>
  C.push(new Paragraph({
    spacing: { after: 70, line: 275 },
    children: [
      new TextRun({ text: n ? n + '  ' : '', bold: true, font: MONO, size: 19, color: ACCENT }),
      new TextRun({ text: t, font: UI, size: 21, color: n ? INK : INK2, bold: !!n }),
    ],
  }))
);
C.push(pageBreak());

// ---------- 1 ----------
C.push(h1('1.  What this is, in plain words'));
C.push(p('We have a library of design pieces — buttons, toggles, cards, navigation bars, and so on. Normally, turning those pieces into finished app screens is slow: a designer hand-builds each screen, then explains it to developers, then everyone waits.'));
C.push(p('This system changes that. We teach an AI assistant our entire design library — not just what each piece looks like, but when to use it, why it exists, and what never to do with it. Once the assistant knows all this, anyone — a product manager, a designer, or a manager — can describe a screen in plain English and get back a real, interactive screen built only from our approved pieces.'));
C.push(h3('Why we do it'));
C.push(bullet([{ t: 'Faster iteration', b: true }, { t: ' — a screen idea becomes a clickable mockup in minutes, not days.' }]));
C.push(bullet([{ t: 'Cleaner handoff', b: true }, { t: ' — developers receive real values and real behaviour they can build from directly.' }]));
C.push(bullet([{ t: 'A single trusted library', b: true }, { t: ' — like Material Design, but ours. Everything stays consistent because the assistant can only use approved pieces.' }]));
C.push(bullet([{ t: 'Everyone can use it', b: true }, { t: ' — PMs to explore, designers to build, management to feel how a design works, all from the same source.' }]));

// ---------- 2 ----------
C.push(h1('2.  The moving parts'));
C.push(p('A few names repeat throughout. Here is each one, in a line.'));
C.push(table([2450, 6910], ['Name', 'What it is'], [
  ['Figma', 'Where the designer draws the actual components. The master copy; everything else mirrors it.'],
  ['Metadata', 'The written notes on each component saying when, why, and why-not to use it. Written first.'],
  ['The repository', 'A GitHub folder holding every component, its metadata, its real code, and how they all connect. The assistant\'s memory.'],
  ['The dashboard', 'A browsable website of the whole library — a catalogue for designers, and the place governance decisions get made.'],
  ['The graph', 'A map of how components connect. Designers navigate it; the assistant reasons over it instead of reading everything.'],
  [[{ t: 'AGENT.md', code: true }], 'The assistant\'s rulebook — how it is allowed to think. The most important file in the system.'],
  [[{ t: 'CONTROL_PANEL.md', code: true }], 'Optional rulebook for showing one screen in several states (online/offline, empty/populated).'],
  [[{ t: 'learnings.jsonl', code: true }], 'A ledger of corrections you have given the assistant, and gaps humans have filled in. Nothing in it binds until a human confirms it.'],
  ['Claude chat vs Claude Code', 'Normal Claude chat WRITES the metadata. Claude Code (which connects to Figma and GitHub) BUILDS and USES the library.'],
]));

// ---------- 3 ----------
C.push(h1('3.  The whole flow at a glance'));
C.push(p('There are three chapters. Chapter A is done once, by a designer, to set the library up. Chapter B is done any time, by anyone, to create screens. Chapter C keeps the library honest as it grows.'));
C.push(h3('Chapter A — Set up the library (one time)'));
C.push(numItem('Organise and finalise all your components in Figma.'));
C.push(numItem('In a normal Claude chat, paste the metadata prompt and work through your components one at a time.'));
C.push(numItem('Open Claude Code and connect it to your Figma page.'));
C.push(numItem([{ t: 'Prompt 1', b: true }, { t: ' — build the repository, together with the rulebook files you place yourself.' }]));
C.push(numItem([{ t: 'Prompt 2', b: true }, { t: ' — build the dashboard.' }]));
C.push(numItem([{ t: 'Prompt 3', b: true }, { t: ' — build the connection graph.' }]));
C.push(numItem([{ t: 'Prompt 4', b: true }, { t: ' — build the component code library. Not optional. See section 4.' }]));
C.push(h3('Chapter B — Use the library (any time, anyone)'));
C.push(numItem('Open a fresh Claude Code chat and paste the Starting Prompt.'));
C.push(numItem('Once it confirms it is ready, describe the screen you want.'));
C.push(numItem('Resume an earlier flow with the prompt the dashboard generates for it.'));
C.push(numItem('Optionally add a state panel for multi-state flows.'));
C.push(h3('Chapter C — Keep it healthy'));
C.push(numItem('Fill documentation gaps from the dashboard\'s Missing Data page.'));
C.push(numItem('Confirm or reject what the assistant has learned, on the Agent Learnings page.'));
C.push(numItem('Re-sync when Figma changes, and regenerate after every change.'));

C.push(pageBreak());

// ---------- 4 ----------
C.push(h1('4.  Before you start — the one mistake that costs the most'));
C.push(...callout([
  [{ t: 'The repository must contain real, runnable component code — not just descriptions of it.', b: true }],
]));
C.push(h3('What went wrong'));
C.push(p('The first build of this system described every component thoroughly: the authored rules, and the exact visual values pulled from Figma — sizes, colours, padding, radii, typography. What it did not contain was any actual component code. So on every single request, the assistant had to re-derive real HTML and CSS from that structured description.'));
C.push(p('That drifts. In a live test the assistant correctly read, quoted, and understood the rule — "the checkbox sits on the right", "the separator is inset, not full-width" — and then wrote code that did the opposite. Twice. The knowledge layer was fine. Re-deriving code from a description, fresh, every time, was not.'));
C.push(p([{ t: 'This is the dangerous kind of failure: it throws no error. It produces screens that look right and quietly violate your rules.', b: true, color: INK }]));
C.push(h3('The fix'));
C.push(p([{ t: 'Every component gets a real, self-contained ' }, { t: '<id>.snippet.html', code: true }, { t: ' next to its ' }, { t: '<id>.yaml', code: true }, { t: ' — actual HTML and CSS, one block per real Figma variant, generated straight from that component\'s own captured visual values. The assistant then ' }, { t: 'copies a known-correct block', b: true }, { t: ' instead of rewriting one from prose. That is Prompt 4, and it is why the rulebook forbids re-derivation outright.' }]));
C.push(h3('What this means for you'));
C.push(bullet('Prompt 4 is a required step of setup, not optional polish.'));
C.push(bullet('Do not let anyone compose a screen from a repository where it has not been run.'));
C.push(bullet('Re-run it after any change to a component\'s visual values. A stale snippet is worse than none — it looks correct and is not.'));
C.push(h3('The one gap it does not close'));
C.push(p('Some things are true of a group of components and exist in no single component\'s visual tree — for example, how several cards stack into a grouped list with an inset separator. A card\'s own data describes one card, not several cards plus a divider. Those live in a patterns folder, written directly from the exact rule text or a decision you gave, quoted verbatim — never guessed, and never presented as extracted from Figma.'));

C.push(pageBreak());

// ---------- 5 : CHAPTER A ----------
C.push(h1('5.  Chapter A — Setting up the library'));

C.push(h2('Step 1 — Get your components ready in Figma'));
C.push(p('Before anything else, make sure every component you want in the library lives on one Figma page, is named clearly, and has its own unique name. No two components should share a name. Clean this up first — everything downstream depends on it, and a collision is a hard stop in the very next step.'));

C.push(h2('Step 2 — Write the metadata'));
C.push(p('Open a normal Claude chat (not Claude Code). Paste the prompt below. Then, one component at a time, share a screenshot. The assistant asks questions, you answer, it writes human-readable notes, you approve, and it produces the final YAML. Paste that YAML into the component\'s description field in Figma. Repeat for every component.'));
C.push(...callout([
  [{ t: 'Do not rush this. ', b: true }, { t: 'The quality of every screen this system ever builds depends on how good these notes are. Answer the questions carefully, and never let it guess.' }],
]));
C.push(promptLabel('PROMPT — Metadata author  (normal Claude chat)', '[ UNCHANGED ]'));
C.push(...block(read(path.join(SP, 'prompts/prompt_metadata.txt'))));

C.push(h2('Step 3 — Open Claude Code and connect it to Figma'));
C.push(p('Switch to Claude Code and connect it to the exact page where your components live. This lets it read both the drawings and the notes you just wrote.'));

C.push(h2('Step 4 — Build the repository'));
C.push(p('Paste Prompt 1. Along with it, place the rulebook files yourself — AGENT.md and CONTROL_PANEL.md, both printed in full in section 8. Prompt 1 reads every component, pulls its exact values and notes from Figma, and lays out the repository.'));
C.push(...callout([
  [{ t: 'The rulebook files are placed by you, not written by the assistant. ', b: true }, { t: 'It must never author or edit them — they are the law it obeys, and an assistant that can rewrite its own rules is not governed by them.' }],
]));
C.push(...callout([
  [{ t: 'Revised in this edition. ', b: true }, { t: 'Prompt 1 now also covers: the transport-escaping trap that silently corrupts mirrored metadata; a hard rule against silently rewiring off-page references, with a "probable mis-wire" report instead; creation of the learnings ledger and the designer-editable files; real font files; and an explicit statement that the repository is not usable until Prompt 4 has run.' }],
], 'new'));
C.push(promptLabel('PROMPT 1 — Build the repository  (Claude Code)', '[ REVISED ]'));
C.push(...block(read(path.join(SP, 'prompts/prompt1_repo.txt'))));

C.push(h2('Step 5 — Build the dashboard'));
C.push(p('Paste Prompt 2. This turns the repository into a browsable website: a catalogue of every component with its notes, a faithful live preview, and a copyable fingerprint — plus the pages where the library\'s gaps and the assistant\'s learnings are actually managed.'));
C.push(...callout([
  [{ t: 'Revised in this edition. ', b: true }, { t: 'Prompt 2 now specifies: build it as one regenerating script rather than hand-written pages; a README page driven by an editable copy file; live system-understanding metrics on Overview, with the rule that human contributions never inflate coverage; the Missing Data and Agent Learnings pages; the Prototypes page with per-flow resume prompts; global search and theming; responsive layout at every screen size; and how to deploy it safely with write-back.' }],
], 'new'));
C.push(promptLabel('PROMPT 2 — Build the dashboard  (Claude Code)', '[ REVISED ]'));
C.push(...block(read(path.join(SP, 'prompts/prompt2_dashboard.txt'))));

C.push(h2('Step 6 — Build the connection graph'));
C.push(p('Paste Prompt 3. This draws the map of how components connect — which small pieces build into bigger ones, and which have special relationships. Designers click any node to jump to it; the assistant uses the same map to reason quickly instead of reading every component.'));
C.push(...callout([
  [{ t: 'Revised in this edition. ', b: true }, { t: 'Prompt 3 now treats the machine-queryable graph as a first-class output alongside the picture, requires the traversal conventions to be documented inside the data file itself, requires unresolved references to be visible in both outputs rather than silently absent, and folds regeneration into the dashboard build so the two can never drift apart.' }],
], 'new'));
C.push(promptLabel('PROMPT 3 — Build the connection graph  (Claude Code)', '[ REVISED ]'));
C.push(...block(read(path.join(SP, 'prompts/prompt3_graph.txt'))));

C.push(h2('Step 7 — Build the component code library'));
C.push(p('Paste Prompt 4. This turns every component\'s captured layout into real, ready-to-use HTML and CSS, so composing a screen later means copying already-correct code rather than re-deriving it every session. Section 4 explains why this step exists and what it cost to learn.'));
C.push(promptLabel('PROMPT 4 — Build the component code library  (Claude Code)', '[ UNCHANGED ]'));
C.push(...block(read(path.join(SP, 'prompts/prompt4_codelib.txt'))));
C.push(p([{ t: 'That is setup done. ', b: true }, { t: 'You now have a repository, a dashboard, a graph, and real component code — with the rulebooks in place. The library is ready to use.' }]));

C.push(pageBreak());

// ---------- 6 : CHAPTER B ----------
C.push(h1('6.  Chapter B — Using the library to build screens'));
C.push(p('This is the part PMs, designers and management use day to day. It is short.'));

C.push(h2('Step 1 — Paste the Starting Prompt'));
C.push(p('Every new session starts with a blank slate. The Starting Prompt points the assistant at the repository and makes it read its rulebook first. It replies with a readiness check — confirming it read the rulebook, reporting how many components it found, and flagging anything broken — so you never get output from a half-loaded library.'));
C.push(promptLabel('STARTING PROMPT — Begin a session  (Claude Code)', '[ UNCHANGED ]'));
C.push(...block(read(path.join(SP, 'prompts/prompt_starting.txt'))));

C.push(h2('Step 2 — Describe the screen you want'));
C.push(p('Once it says it is ready, tell it what you need — a full PRD, a short description, or a single screen. It reasons over the library and hands back an interactive HTML file inside a phone frame, plus a short explanation of why it chose each component.'));
C.push(p([{ t: 'What you can trust: ', b: true }, { t: 'every piece it used is a real approved component, every value came from Figma, and every rule was honoured. If your request needed something the library does not have, it tells you what is missing instead of faking it.' }]));

C.push(h2('Step 3 — Resume an existing flow'));
C.push(p('To pick up a flow you built earlier, do not retype a description of it. Open the Prototypes page on the dashboard, find the flow\'s card, and use its Resume prompt control — it generates the text below pre-filled from that card\'s own title, file, description and status, with a copy button. Paste it into a fresh session and replace the last line.'));
C.push(...callout([
  [{ t: 'Why generated, not typed: ', b: true }, { t: 'its pointers are correct by construction. A hand-typed resume prompt sends the assistant looking for a file that may have been renamed — or worse, silently rebuilds a flow that was already reviewed and approved.' }],
]));
C.push(promptLabel('RESUME PROMPT — generated per flow by the dashboard', '[ UNCHANGED ]'));
C.push(...block(read(path.join(SP, 'prompts/prompt_resume.txt'))));

C.push(h2('Step 4 — Show multiple states (optional)'));
C.push(p('Some flows need showing in more than one condition — online versus offline, typing versus idle, empty versus populated. Paste the prompt below and the assistant composes each state as a full screen and gives you a switcher beside the phone.'));
C.push(p([{ t: 'The switcher only changes the situation. ', b: true }, { t: 'It does not let anyone hand-pick component variants — the assistant decides the right design for each situation itself. By default there is no panel; you only get one when you ask.' }]));
C.push(promptLabel('PROMPT — Screen State Panel  (optional, Claude Code)', '[ UNCHANGED ]'));
C.push(...block(read(path.join(SP, 'prompts/prompt_statepanel.txt'))));

C.push(h2('Step 5 — Correcting the assistant'));
C.push(p('When it gets something wrong, just say so in plain language. No special format. What matters is what happens next, so you can tell whether it behaved correctly.'));
C.push(p([{ t: 'In the same turn, it must:', b: true, color: INK }]));
C.push(numItem([{ t: 'Append an entry to ' }, { t: 'learnings.jsonl', code: true }, { t: ' with status "proposed" — what it did, what you said, and the rule it infers.' }]));
C.push(numItem([{ t: 'Never', b: true }, { t: ' edit the component\'s authored metadata. That comes from Figma; this repository never writes back to it.' }]));
C.push(numItem('Regenerate the dashboard — the only thing that rebuilds the learnings counts and the component\'s own learnings section.'));
C.push(numItem('Commit the ledger change and the regenerated dashboard together, as one commit, then push.'));
C.push(...callout([
  [{ t: 'You should never have to notice the dashboard went stale, or ask for it to be rebuilt, committed, or pushed. If you find yourself asking, that is a bug in the assistant\'s behaviour — not a step you own.' }],
]));
C.push(p([{ t: 'A proposed entry is ' }, { t: 'not', b: true }, { t: ' binding. It becomes binding only when a human confirms it, which exists precisely so the assistant cannot reinforce its own uncorrected mistakes.' }]));

C.push(pageBreak());

// ---------- 7 : CHAPTER C ----------
C.push(h1('7.  Chapter C — Keeping the library healthy'));

C.push(h2('Missing Data — filling documentation gaps'));
C.push(p([{ t: 'Sidebar → Missing Data', b: true }, { t: ' → pick the tab for the field (Purpose, Usage, Design intent, Anti-patterns, Rules) → click a listed component. Its real rendered preview appears above the text box, so you write against the component in view rather than from memory. Then copy the entry or download the updated ledger, and commit it.' }]));
C.push(p([{ t: 'What it actually does: ', b: true }, { t: 'records a contribution with status "proposed". This is stopgap documentation, not authored metadata. It never moves the coverage meters — those measure the Figma-authored spec specifically — and it is not binding until confirmed, or until you fold it back into Figma and re-ingest, which is the real fix.' }]));

C.push(h2('Agent Learnings — confirming what the assistant learned'));
C.push(p([{ t: 'Sidebar → Agent Learnings → Pending review', b: true }, { t: ' → ' }, { t: 'Approve', b: true }, { t: ' (binding from then on) or ' }, { t: 'Deny', b: true }, { t: '. A decided entry can be ' }, { t: 'Revoked', b: true }, { t: ' back to pending if it was decided in error.' }]));
C.push(p('On a deployed dashboard these buttons are real: they write the status change back to the repository, and the deploy rebuilds the dashboard automatically within about a minute. Running locally, make the change in the ledger by hand and regenerate.'));

C.push(h2('Re-syncing after Figma changes'));
C.push(p('When the design system moves on in Figma, the repository has to catch up — and the order matters, because a refreshed component with a stale code snippet is exactly the silent failure section 4 describes.'));
C.push(promptLabel('PROMPT — Re-sync after Figma changes  (Claude Code)', '[ NEW ]'));
C.push(...block(read(path.join(SP, 'prompts/prompt_resync.txt'))));

C.push(h2('Regeneration commands'));
C.push(p('Run from the repository root. Exact script names will match whatever your build produced in Chapter A.'));
C.push(table([4300, 5060], ['Command', 'When to run it'], [
  [[{ t: 'build_dashboard', code: true }], [{ t: 'After ' }, { t: 'any', b: true }, { t: ' change that should show on the dashboard — metadata, the ledger, a new flow, README copy. Regenerates the graph too. The default one to reach for.' }]],
  [[{ t: 'build_component_library', code: true }], 'After any change to a component\'s visual values — new variant, resize, colour change. See section 4.'],
  [[{ t: 'build_graph', code: true }], 'Graph only. Rarely needed directly; the dashboard build already calls it.'],
]));
C.push(gap(150));
C.push(...callout([
  [{ t: 'Rule of thumb: ', b: true }, { t: 'never commit a ledger or component change without the regenerated dashboard in the same commit. A stale dashboard is a governance record that disagrees with the repository.' }],
]));

C.push(pageBreak());

// ---------- 8 : RULEBOOKS ----------
C.push(h1('8.  The rulebook files'));
C.push(p('These two files are the law the assistant obeys. You place them at the repository root during setup. You do not need to change them, and the assistant is never permitted to. They are printed in full so you always have a copy.'));
C.push(h2('AGENT.md — the assistant\'s constitution'));
C.push(p('The single most important file. It defines what the assistant is, the laws it can never break, exactly how it must reason, what a finished screen must look like, how it records corrections, and how a session starts.'));
C.push(promptLabel('FILE — AGENT.md  (place at repository root)'));
C.push(...block(read(path.join(REPO, 'AGENT.md')), 'file'));

C.push(h2('CONTROL_PANEL.md — the screen-state panel rules'));
C.push(p('Read only when someone asks for a multi-state panel. It defines what the panel may switch (situations of the screen) and what it must never touch (component internals).'));
C.push(promptLabel('FILE — CONTROL_PANEL.md  (place at repository root)'));
C.push(...block(read(path.join(REPO, 'CONTROL_PANEL.md')), 'file'));

C.push(pageBreak());

// ---------- 9 : QUICK REFERENCE ----------
C.push(h1('9.  Quick reference — what to paste, and when'));
C.push(h3('Setting up (one time)'));
C.push(table([1250, 3450, 4660], ['Order', 'Paste', 'Where / result'], [
  ['1', 'Metadata author prompt', 'Normal Claude chat → YAML notes for every component, pasted into Figma'],
  ['2', [{ t: 'Prompt 1', b: true }, { t: ' + AGENT.md + CONTROL_PANEL.md' }], 'Claude Code → the repository'],
  ['3', [{ t: 'Prompt 2', b: true }], 'Claude Code → the dashboard'],
  ['4', [{ t: 'Prompt 3', b: true }], 'Claude Code → the connection graph'],
  ['5', [{ t: 'Prompt 4', b: true }], 'Claude Code → real component code. Required, not optional.'],
]));
C.push(gap(180));
C.push(h3('Using it (any time)'));
C.push(table([1250, 3450, 4660], ['Order', 'Paste', 'Where / result'], [
  ['1', 'Starting Prompt', 'Fresh Claude Code chat → readiness check'],
  ['2', 'Your requirement', 'A PRD, a description, or one screen → an interactive HTML screen'],
  ['3', 'Resume prompt', 'Generated by the dashboard per flow → continue earlier work'],
  ['4', 'Screen State Panel prompt', 'Optional → multi-state switcher'],
]));
C.push(gap(180));
C.push(h3('Which model to use'));
C.push(bullet([{ t: 'Metadata authoring', b: true }, { t: ' — the most capable model available. These notes govern everything built later.' }]));
C.push(bullet([{ t: 'Prompt 1 (ingestion)', b: true }, { t: ' — Opus. Its fidelity is the foundation and must never be summarised or approximated.' }]));
C.push(bullet([{ t: 'Prompts 2, 3 and 4', b: true }, { t: ' — Opus or Sonnet. These read the repo and generate deterministically.' }]));
C.push(bullet([{ t: 'Composing screens (Chapter B)', b: true }, { t: ' — Opus, for the strongest reasoning over the library.' }]));
C.push(gap(260));
C.push(...callout([
  [{ t: 'If you remember only one thing: ', b: true },
   { t: 'the assistant only uses what is in the library, and never invents. A truthful "this is not in the library yet" is the system working correctly — it is what protects everyone from off-brand, made-up designs.' }],
]));
C.push(gap(200));
C.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 300 },
  children: [new TextRun({ text: '— End of handbook —', font: MONO, size: 18, color: ACCENT })],
}));

// ============================================================ document
const doc = new Document({
  numbering: {
    config: [
      {
        reference: 'hb-bullets',
        levels: [
          { level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 470, hanging: 250 } } } },
          { level: 1, format: LevelFormat.BULLET, text: '◦', alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 900, hanging: 250 } } } },
        ],
      },
      {
        reference: 'hb-numbers',
        levels: [
          { level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 470, hanging: 250 } } } },
        ],
      },
    ],
  },
  styles: { default: { document: { run: { font: UI, size: 21, color: INK2 } } } },
  sections: [
    {
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 1080, bottom: 1080, left: 1400, right: 1400 },
        },
      },
      children: C,
    },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  const out = path.join(REPO, 'Design-to-Screen-with-AI-Handbook.docx');
  fs.writeFileSync(out, buf);
  console.log('written:', out, buf.length, 'bytes');
});
