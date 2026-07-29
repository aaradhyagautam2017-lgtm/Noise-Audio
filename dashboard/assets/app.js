
document.addEventListener('click', function (ev) {
  const b = ev.target.closest('.copybtn');
  if (!b) return;
  navigator.clipboard.writeText(b.dataset.copy).then(() => {
    b.classList.add('copied');
    const t = b.textContent; b.textContent = '✓ copied';
    setTimeout(() => { b.classList.remove('copied'); b.textContent = t; }, 1200);
  });
});

// theme toggle — the <head> applies the stored choice before first paint, so this
// only has to flip it and persist. Dark is the default when nothing is stored.
document.addEventListener('click', function (ev) {
  if (!ev.target.closest('#themetoggle')) return;
  const root = document.documentElement;
  const next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
  root.setAttribute('data-theme', next);
  try { localStorage.setItem('na-theme', next); } catch (e) {}
});

// Persist the sidebar's scroll position across page loads -- the restore half of
// this lives inline right after the sidebar markup (see sidebar() in
// build_dashboard.py) so it runs before first paint with no visible jump.
(function () {
  const sidebar = document.querySelector('.sidebar');
  if (!sidebar) return;
  sidebar.addEventListener('scroll', function () {
    try { sessionStorage.setItem('na-sidebar-scroll', sidebar.scrollTop); } catch (e) {}
  }, { passive: true });
})();
