import { verifySession, parseCookie, SESSION_COOKIE } from "../lib/dash-auth.js";

const OWNER = "aaradhyagautam2017-lgtm";
const REPO = "Noise-Audio";
const FILE_PATH = "screens/index.json";
const FILE_RE = /^[a-z0-9][a-z0-9-]*\.html$/;
const MAX_TITLE = 120;
const MAX_DESC = 1000;

// Node.js runtime, not Edge — needs Buffer (for base64 <-> utf-8) and a plain outbound
// fetch to the GitHub REST API, both only available here. Mirrors api/decide.js, but the
// ledger here is a small JSON object (filename -> {title, description}) rather than a
// line-delimited log, since this is a human-editable overlay, not an append-only record.
export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.status(405).json({ ok: false, error: "method not allowed" });
    return;
  }

  const secret = process.env.SESSION_SECRET;
  const token = parseCookie(req.headers.cookie || "", SESSION_COOKIE);
  if (!(await verifySession(secret, token))) {
    res.status(401).json({ ok: false, error: "not signed in" });
    return;
  }

  const { file, title, description } = req.body || {};
  if (
    typeof file !== "string" || !FILE_RE.test(file) ||
    typeof title !== "string" || !title.trim() || title.length > MAX_TITLE ||
    typeof description !== "string" || description.length > MAX_DESC
  ) {
    res.status(400).json({ ok: false, error: "invalid request" });
    return;
  }

  const ghToken = process.env.GITHUB_TOKEN;
  const branch = process.env.VERCEL_GIT_COMMIT_REF || process.env.GITHUB_BRANCH;
  if (!ghToken || !branch) {
    res.status(500).json({ ok: false, error: "server not configured (missing GITHUB_TOKEN or branch)" });
    return;
  }

  const apiBase = `https://api.github.com/repos/${OWNER}/${REPO}/contents/${FILE_PATH}`;
  const ghHeaders = {
    Authorization: `Bearer ${ghToken}`,
    Accept: "application/vnd.github+json",
    "User-Agent": "noise-audio-dashboard",
  };

  try {
    for (let attempt = 0; attempt < 2; attempt++) {
      const getRes = await fetch(`${apiBase}?ref=${encodeURIComponent(branch)}`, { headers: ghHeaders });
      let registry = {};
      let sha;
      if (getRes.ok) {
        const existing = await getRes.json();
        sha = existing.sha;
        try {
          registry = JSON.parse(Buffer.from(existing.content, "base64").toString("utf-8"));
        } catch {
          registry = {};
        }
      } else if (getRes.status !== 404) {
        res.status(502).json({ ok: false, error: "could not read flow registry from GitHub (" + getRes.status + ")" });
        return;
      }
      // getRes.status === 404 means the file doesn't exist yet — sha stays undefined,
      // which tells the PUT below to create it fresh.

      registry[file] = { title: title.trim(), description: description.trim() };

      const putRes = await fetch(apiBase, {
        method: "PUT",
        headers: { ...ghHeaders, "content-type": "application/json" },
        body: JSON.stringify({
          message: `screens: update title/description for ${file} via dashboard`,
          content: Buffer.from(JSON.stringify(registry, null, 2) + "\n", "utf-8").toString("base64"),
          ...(sha ? { sha } : {}),
          branch,
        }),
      });
      if (putRes.ok) {
        res.status(200).json({ ok: true });
        return;
      }
      if (putRes.status === 409 && attempt === 0) continue; // sha conflict — someone else committed; retry once
      const detail = await putRes.text();
      res.status(502).json({ ok: false, error: "could not save to GitHub (" + putRes.status + ")", detail: detail.slice(0, 300) });
      return;
    }
    res.status(409).json({ ok: false, error: "conflicting update, please retry" });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err && err.message || err) });
  }
}
