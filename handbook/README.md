# handbook/

Generates `Design-to-Screen-with-AI-Handbook.docx` — the complete onboarding
handbook: every prompt, both rulebooks, and the workflow end to end.

## Regenerating

```
cd handbook
npm install docx          # once
node build_handbook.cjs
python3 fix_docx_schema.py ../Design-to-Screen-with-AI-Handbook.docx
```

The second step is required, not optional. docx-js emits paragraph borders as
top/bottom/left/right, but OOXML's CT_PBdr enforces top/left/bottom/right —
Word tolerates the wrong order, strict validators and LibreOffice do not. It
also rezips with `[Content_Types].xml` first and drops directory entries.

`.cjs`, not `.js`: the repo root's package.json sets `"type": "module"` for the
Vercel endpoints, which would otherwise make Node parse this as ESM.

## Editing

Prompt text lives in `prompts/*.txt`, one file per prompt — edit those, not the
generator, and never the generated .docx. `prompts/prompt_metadata.txt` is
carried verbatim from the original handbook and is deliberately frozen.

AGENT.md and CONTROL_PANEL.md are read from the repo root at build time, so the
handbook always prints the live rulebooks rather than a stale transcription.
