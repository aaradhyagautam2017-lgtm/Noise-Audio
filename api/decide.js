import { verifySession, parseCookie, SESSION_COOKIE } from "../lib/dash-auth.js";

const OWNER = "aaradhyagautam2017-lgtm";
const REPO = "Noise-Audio";
const FILE_PATH = "learnings.jsonl";
const VALID_STATUSES = new Set(["confirmed", "rejected"]);
const ID_RE = /^learn-[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-zA-Z0-9]+$/;

// Node.js runtime, not Edge — needs Buffer (for base64 <-> utf-8) and a plain outbound
// fetch to the GitHub REST API, both of which are only available here.
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

  const { id, status } = req.body || {};
  if (typeof id !== "string" || !ID_RE.test(id) || !VALID_STATUSES.has(status)) {
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
      if (!getRes.ok) {
        res.status(502).json({ ok: false, error: "could not read ledger from GitHub (" + getRes.status + ")" });
        return;
      }
      const file = await getRes.json();
      const raw = Buffer.from(file.content, "base64").toString("utf-8");
      const lines = raw.split("\n");
      let found = false;
      const updatedLines = lines.map((line) => {
        if (!line.trim()) return line;
        let entry;
        try {
          entry = JSON.parse(line);
        } catch {
          return line;
        }
        if (entry.id === id) {
          found = true;
          entry.status = status;
          entry.reviewed_at = new Date().toISOString();
          return JSON.stringify(entry);
        }
        return line;
      });
      if (!found) {
        res.status(404).json({ ok: false, error: "entry not found in ledger" });
        return;
      }

      const putRes = await fetch(apiBase, {
        method: "PUT",
        headers: { ...ghHeaders, "content-type": "application/json" },
        body: JSON.stringify({
          message: `learnings: mark ${id} as ${status} via dashboard`,
          content: Buffer.from(updatedLines.join("\n"), "utf-8").toString("base64"),
          sha: file.sha,
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
