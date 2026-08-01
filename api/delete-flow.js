import { verifySession, parseCookie, SESSION_COOKIE } from "../lib/dash-auth.js";

const OWNER = "aaradhyagautam2017-lgtm";
const REPO = "Noise-Audio";
const SCREENS_DIR = "screens";
const INDEX_PATH = "screens/index.json";
const FILE_RE = /^[a-z0-9][a-z0-9-]*\.html$/;

// Node.js runtime, not Edge — same reason as api/update-flow.js (Buffer, plain outbound fetch).
// Deletes the real screen file, then drops its entry from the title/description/status overlay
// if it has one — two separate GitHub commits, same as any two Contents-API writes, not one
// atomic operation, but that's fine here: if the file delete succeeds and the registry cleanup
// fails, the flow is still gone from screens/ and simply leaves a stale, harmless entry behind
// (the same one that already tolerates being edited via update-flow.js).
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

  const { file } = req.body || {};
  if (typeof file !== "string" || !FILE_RE.test(file)) {
    res.status(400).json({ ok: false, error: "invalid request" });
    return;
  }

  const ghToken = process.env.GITHUB_TOKEN;
  const branch = process.env.VERCEL_GIT_COMMIT_REF || process.env.GITHUB_BRANCH;
  if (!ghToken || !branch) {
    res.status(500).json({ ok: false, error: "server not configured (missing GITHUB_TOKEN or branch)" });
    return;
  }

  const ghHeaders = {
    Authorization: `Bearer ${ghToken}`,
    Accept: "application/vnd.github+json",
    "User-Agent": "noise-audio-dashboard",
  };
  const fileApiBase = `https://api.github.com/repos/${OWNER}/${REPO}/contents/${SCREENS_DIR}/${file}`;
  const indexApiBase = `https://api.github.com/repos/${OWNER}/${REPO}/contents/${INDEX_PATH}`;

  try {
    // 1. Delete the actual screen file, if it's still there (404 here just means it's already
    // gone — treat that as success and move on to cleaning up its registry entry).
    const fileGetRes = await fetch(`${fileApiBase}?ref=${encodeURIComponent(branch)}`, { headers: ghHeaders });
    if (fileGetRes.ok) {
      const existing = await fileGetRes.json();
      const delRes = await fetch(fileApiBase, {
        method: "DELETE",
        headers: { ...ghHeaders, "content-type": "application/json" },
        body: JSON.stringify({ message: `screens: delete ${file} via dashboard`, sha: existing.sha, branch }),
      });
      if (!delRes.ok) {
        const detail = await delRes.text();
        res.status(502).json({ ok: false, error: "could not delete file from GitHub (" + delRes.status + ")", detail: detail.slice(0, 300) });
        return;
      }
    } else if (fileGetRes.status !== 404) {
      res.status(502).json({ ok: false, error: "could not read flow file from GitHub (" + fileGetRes.status + ")" });
      return;
    }

    // 2. Drop its entry from the overlay, if any, retrying once on a sha conflict — same
    // pattern as api/update-flow.js.
    for (let attempt = 0; attempt < 2; attempt++) {
      const idxGetRes = await fetch(`${indexApiBase}?ref=${encodeURIComponent(branch)}`, { headers: ghHeaders });
      if (!idxGetRes.ok) {
        if (idxGetRes.status === 404) break; // no overlay file at all — nothing to clean up
        res.status(502).json({ ok: false, error: "could not read flow registry from GitHub (" + idxGetRes.status + ")" });
        return;
      }
      const existing = await idxGetRes.json();
      let registry;
      try {
        registry = JSON.parse(Buffer.from(existing.content, "base64").toString("utf-8"));
      } catch {
        registry = {};
      }
      if (!(file in registry)) break; // nothing to remove

      delete registry[file];
      const putRes = await fetch(indexApiBase, {
        method: "PUT",
        headers: { ...ghHeaders, "content-type": "application/json" },
        body: JSON.stringify({
          message: `screens: remove ${file} from registry via dashboard`,
          content: Buffer.from(JSON.stringify(registry, null, 2) + "\n", "utf-8").toString("base64"),
          sha: existing.sha,
          branch,
        }),
      });
      if (putRes.ok) break;
      if (putRes.status === 409 && attempt === 0) continue; // someone else committed; retry once
      const detail = await putRes.text();
      res.status(502).json({ ok: false, error: "could not update flow registry on GitHub (" + putRes.status + ")", detail: detail.slice(0, 300) });
      return;
    }

    res.status(200).json({ ok: true });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err && err.message || err) });
  }
}
