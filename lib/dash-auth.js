// Shared session/password helpers for the dashboard's password gate.
//
// Used from two different Vercel runtimes: the Edge runtime (middleware.js) and the
// Node.js runtime (api/login.js, api/decide.js). Only the Web Crypto API (the global
// `crypto.subtle`) is used here, deliberately, because it's the one crypto API both
// runtimes provide natively — anything from node:crypto would break under Edge, and
// Buffer isn't available under Edge either, hence the manual hex encoding below.

function bufToHex(buf) {
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function hmacHex(secret, message) {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  return bufToHex(sig);
}

export async function sha256Hex(message) {
  const enc = new TextEncoder();
  const digest = await crypto.subtle.digest("SHA-256", enc.encode(message));
  return bufToHex(digest);
}

export function timingSafeEqualHex(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

const SESSION_TTL_SECONDS = 60 * 60 * 24 * 30; // 30 days

// Cookie value is "<expiry-unix-seconds>.<hmac-of-expiry>" — a signed, stateless session
// token. No session store anywhere; validity is just "signature checks out and hasn't
// expired yet", which is enough for a single shared team password.
export async function signSession(secret) {
  const expiry = Math.floor(Date.now() / 1000) + SESSION_TTL_SECONDS;
  const sig = await hmacHex(secret, String(expiry));
  return `${expiry}.${sig}`;
}

export async function verifySession(secret, cookieValue) {
  if (!secret || !cookieValue) return false;
  const dot = cookieValue.indexOf(".");
  if (dot === -1) return false;
  const expiryStr = cookieValue.slice(0, dot);
  const sig = cookieValue.slice(dot + 1);
  const expiry = Number(expiryStr);
  if (!Number.isFinite(expiry) || expiry < Math.floor(Date.now() / 1000)) return false;
  const expected = await hmacHex(secret, expiryStr);
  return timingSafeEqualHex(expected, sig);
}

export function parseCookie(header, name) {
  if (!header) return null;
  for (const part of header.split(";")) {
    const eq = part.indexOf("=");
    if (eq === -1) continue;
    if (part.slice(0, eq).trim() === name) return decodeURIComponent(part.slice(eq + 1).trim());
  }
  return null;
}

export const SESSION_COOKIE = "dash_session";
export const SESSION_MAX_AGE = SESSION_TTL_SECONDS;
