import { sha256Hex, timingSafeEqualHex, signSession, SESSION_COOKIE, SESSION_MAX_AGE } from "../lib/dash-auth.js";

// Node.js runtime (not Edge) — Vercel auto-parses a JSON body into req.body when the
// request's content-type is application/json, so no manual parsing is needed here.
export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.status(405).json({ ok: false, error: "method not allowed" });
    return;
  }

  const expectedHash = process.env.DASHBOARD_PASSWORD_HASH;
  const secret = process.env.SESSION_SECRET;
  if (!expectedHash || !secret) {
    res.status(500).json({ ok: false, error: "server not configured (missing DASHBOARD_PASSWORD_HASH or SESSION_SECRET)" });
    return;
  }

  const password = typeof req.body?.password === "string" ? req.body.password : "";
  const gotHash = await sha256Hex(password);
  if (!timingSafeEqualHex(gotHash, expectedHash)) {
    res.status(401).json({ ok: false, error: "wrong password" });
    return;
  }

  const token = await signSession(secret);
  res.setHeader(
    "Set-Cookie",
    `${SESSION_COOKIE}=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${SESSION_MAX_AGE}`
  );
  res.status(200).json({ ok: true });
}
