import { verifySession, parseCookie, SESSION_COOKIE } from "./lib/dash-auth.js";

// Everything the dashboard serves is generated from repository state and meant for the
// design team, not the public internet. This gate is the whole reason a write-back
// endpoint (api/decide.js) is safe to expose: without it, anyone with the dashboard's
// URL could call that endpoint and commit to the repo.
const LOGIN_HTML = `<!doctype html>
<html><head><meta charset="utf-8"><title>Test DLS dashboard — sign in</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root{color-scheme:dark light}
  *{box-sizing:border-box}
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
    background:#0b0b0e;color:#e8e8ea;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
  form{background:#17171b;border:1px solid #27272c;border-radius:14px;padding:32px;width:300px}
  h1{font-size:16px;margin:0 0 18px;font-weight:600}
  input{width:100%;background:#0f0f12;border:1px solid #2a2a30;color:#fff;
    border-radius:8px;padding:10px 12px;font-size:14px;margin-bottom:12px;font-family:inherit}
  input:focus{outline:none;border-color:#7c6cf6}
  button{width:100%;background:#7c6cf6;color:#fff;border:none;border-radius:8px;padding:10px;
    font-size:14px;cursor:pointer;font-family:inherit}
  button:disabled{opacity:.6;cursor:default}
  p{color:#8a8a92;font-size:12.5px;margin:12px 0 0;min-height:16px}
</style></head>
<body>
  <form id="f">
    <h1>Test DLS dashboard</h1>
    <input type="password" id="pw" placeholder="Password" autofocus required autocomplete="current-password">
    <button type="submit">Sign in</button>
    <p id="err"></p>
  </form>
  <script>
    document.getElementById('f').addEventListener('submit', async function (e) {
      e.preventDefault();
      var btn = e.target.querySelector('button');
      var err = document.getElementById('err');
      btn.disabled = true;
      err.textContent = '';
      try {
        var res = await fetch('/api/login', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ password: document.getElementById('pw').value })
        });
        if (res.ok) { location.reload(); return; }
        err.textContent = res.status === 401 ? 'Wrong password.' : 'Something went wrong. Try again.';
      } catch (e) {
        err.textContent = 'Network error. Try again.';
      }
      btn.disabled = false;
    });
  </script>
</body></html>`;

export default async function middleware(request) {
  const secret = process.env.SESSION_SECRET;
  const cookieHeader = request.headers.get("cookie");
  const token = parseCookie(cookieHeader, SESSION_COOKIE);
  const authenticated = secret ? await verifySession(secret, token) : false;
  if (authenticated) return; // let the request through to normal static serving

  return new Response(LOGIN_HTML, {
    status: 200,
    headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" },
  });
}

// Everything except /api/* goes through the gate above — each API route (login, decide)
// checks its own auth as needed, independent of this middleware.
export const config = {
  matcher: ["/((?!api/).*)"],
};
