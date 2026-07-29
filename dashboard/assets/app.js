
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

// Persist the nav's scroll position across page loads -- the restore half of this
// lives inline right after the sidebar markup (see sidebar() in build_dashboard.py)
// so it runs before first paint with no visible jump.
(function () {
  const nav = document.querySelector('.navscroll');
  if (!nav) return;
  nav.addEventListener('scroll', function () {
    try { sessionStorage.setItem('na-sidebar-scroll', nav.scrollTop); } catch (e) {}
  }, { passive: true });
})();

// Collapsible sidebar sections (Foundations / Atoms / Molecules / Organisms): a
// section the visitor previously opened stays open on the next page too, EXCEPT a
// section is never force-collapsed if it contains the page you're currently on
// (data-forced="1", set server-side) -- you should never land on a component's page
// and find its own section collapsed.
document.querySelectorAll('.navsection').forEach(function (sec) {
  const key = 'na-navsec-' + sec.dataset.key;
  if (sec.dataset.forced !== '1') {
    const stored = localStorage.getItem(key);
    if (stored === '1') sec.setAttribute('open', '');
    else if (stored === '0') sec.removeAttribute('open');
  }
  sec.addEventListener('toggle', function () {
    try { localStorage.setItem(key, sec.open ? '1' : '0'); } catch (e) {}
  });
});

// Sidebar search: filters the baked-in NA_SEARCH_INDEX (every component + nav +
// foundations page, with hrefs already resolved for this page's depth) as you type,
// with arrow-key navigation and Cmd/Ctrl+K to jump to the box from anywhere.
(function () {
  const input = document.getElementById('navsearch-input');
  const results = document.getElementById('navsearch-results');
  const index = window.NA_SEARCH_INDEX;
  if (!input || !results || !index) return;
  let sel = -1;

  function renderEmpty(msg) { results.innerHTML = '<div class="navsearch-empty">' + msg + '</div>'; }

  function filter() {
    const q = input.value.trim().toLowerCase();
    sel = -1;
    if (!q) { results.hidden = true; results.innerHTML = ''; return; }
    const matches = index.filter(function (it) {
      return it.n.toLowerCase().indexOf(q) !== -1 || it.g.toLowerCase().indexOf(q) !== -1;
    }).slice(0, 20);
    results.hidden = false;
    if (!matches.length) { renderEmpty('No matches'); return; }
    results.innerHTML = matches.map(function (it) {
      return '<a class="navsearch-result" href="' + it.h + '">'
           + '<span>' + it.n.replace(/</g, '&lt;') + '</span>'
           + '<span class="grp">' + it.g.replace(/</g, '&lt;') + '</span></a>';
    }).join('');
  }

  function applySelection(links) {
    links.forEach(function (l, i) { l.classList.toggle('sel', i === sel); });
    if (links[sel]) links[sel].scrollIntoView({ block: 'nearest' });
  }

  input.addEventListener('input', filter);
  input.addEventListener('focus', function () { if (input.value.trim()) filter(); });
  input.addEventListener('keydown', function (ev) {
    const links = results.querySelectorAll('.navsearch-result');
    if (ev.key === 'ArrowDown') { ev.preventDefault(); sel = Math.min(sel + 1, links.length - 1); applySelection(links); }
    else if (ev.key === 'ArrowUp') { ev.preventDefault(); sel = Math.max(sel - 1, 0); applySelection(links); }
    else if (ev.key === 'Enter') { const l = links[sel >= 0 ? sel : 0]; if (l) location.href = l.getAttribute('href'); }
    else if (ev.key === 'Escape') { results.hidden = true; input.blur(); }
  });
  document.addEventListener('click', function (ev) {
    if (!ev.target.closest('.navsearch')) { results.hidden = true; }
  });
  document.addEventListener('keydown', function (ev) {
    if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === 'k') {
      ev.preventDefault(); input.focus(); input.select();
    }
  });
})();
