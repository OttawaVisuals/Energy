/* Author credit on each tool page, for visitors who land on one page and never see
   index.html: a "Built by Simon" button in the header (hover/tap opens a popover with
   a short bio and an inline contact form) plus a line in the <footer>. One place to
   edit the credit. Self-contained: not every page loads assets/site-theme.css (ceud,
   construction, permits don't), so styles are injected here and use the page's
   theme variables with fixed fallbacks. The form posts to the same Cloudflare
   function as index.html (functions/api/contact.js). Pages include it with
   <script defer src="assets/author-footer.js">. */
(function () {
  var TEXT = 'Built by Simon · energy engineer (MEng, CEM)';
  // GitHub Pages has no /api, so off-madeclear hosts post cross-origin (CORS allow-listed in the function).
  var API = location.hostname === 'energy.madeclear.ca' ? '/api/contact' : 'https://energy.madeclear.ca/api/contact';

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
  }
  function link(text, href) {
    var a = el('a', null, text);
    a.href = href;
    a.style.color = 'inherit';
    a.style.textDecoration = 'underline';
    return a;
  }

  /* ---- footer line ---- */
  var footer = document.querySelector('footer');
  if (footer && !footer.querySelector('.author-line')) {
    var line = el('p', 'author-line');
    line.style.margin = '.6rem 0 0';
    line.appendChild(document.createTextNode(TEXT + ' · '));
    line.appendChild(link('All tools', 'index.html'));
    line.appendChild(document.createTextNode(' · '));
    line.appendChild(link('Get in touch', 'index.html#contact'));
    footer.appendChild(line);
  }

  /* ---- header button + popover ---- */
  var header = document.querySelector('header');
  if (!header || header.querySelector('.ab-wrap')) return;

  var css = document.createElement('style');
  css.textContent =
    '.ab-wrap{position:relative;display:inline-block;flex:none}' +
    '.ab-btn{font:12px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif;color:rgba(255,255,255,.85);background:none;' +
      'border:1px solid rgba(255,255,255,.35);border-radius:999px;padding:2px 10px;cursor:pointer;white-space:nowrap}' +
    '.ab-btn:hover,.ab-btn[aria-expanded="true"]{color:#fff;border-color:rgba(255,255,255,.7)}' +
    '.ab-short{display:none}' +
    '.ab-compact .ab-full{display:none}.ab-compact .ab-short{display:inline}' +
    '.ab-mini .ab-short{font-size:0}.ab-mini .ab-short:first-letter{font-size:12px}' +
    '.ab-mini .ab-btn{width:24px;height:24px;padding:0;text-align:center;line-height:22px}' +
    '.ab-pop{position:absolute;right:0;top:calc(100% + 10px);width:min(320px,92vw);box-sizing:border-box;z-index:1000;' +
      'background:var(--card,#fff);color:var(--text,#1C2B3A);border:1px solid var(--border,#D2D8E3);border-radius:10px;' +
      'box-shadow:0 8px 28px rgba(0,0,0,.28);padding:14px 16px;font:13px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;' +
      'text-align:left;white-space:normal;text-transform:none;letter-spacing:0}' +
    '.ab-pop[hidden]{display:none}' +
    '.ab-pop:before{content:"";position:absolute;right:28px;top:-6px;width:10px;height:10px;transform:rotate(45deg);' +
      'background:var(--card,#fff);border-left:1px solid var(--border,#D2D8E3);border-top:1px solid var(--border,#D2D8E3)}' +
    '.ab-pop p{margin:0 0 8px}' +
    '.ab-pop .ab-name{font-weight:600;font-size:14px}' +
    '.ab-pop .ab-note{color:var(--muted,#5C6E82);font-size:12px}' +
    '.ab-pop a{color:inherit}' +
    '.ab-pop button.ab-go,.ab-pop button.ab-send{font:inherit;font-size:12.5px;cursor:pointer;border-radius:6px;padding:5px 12px;' +
      'border:1px solid rgba(128,150,180,.55);background:#0B2545;color:#fff}' +
    '.ab-pop form{margin-top:10px}' +
    '.ab-pop form[hidden]{display:none}' +
    '.ab-pop label{display:block;font-size:12px;color:var(--muted,#5C6E82);margin:6px 0 2px}' +
    '.ab-pop input,.ab-pop textarea{width:100%;box-sizing:border-box;font:inherit;font-size:13px;padding:5px 7px;border-radius:6px;' +
      'border:1px solid var(--border,#D2D8E3);background:var(--cream,#fff);color:var(--text,#1C2B3A)}' +
    '.ab-pop textarea{min-height:76px;resize:vertical}' +
    '.ab-pop .ab-status{margin-left:8px;font-size:12px;color:var(--muted,#5C6E82)}' +
    '@media(max-width:640px){.ab-full{display:none}.ab-short{display:inline}' +
      '.ab-pop{position:fixed;left:8px;right:8px;top:54px;width:auto}.ab-pop:before{display:none}}';
  document.head.appendChild(css);

  var wrap = el('div', 'ab-wrap');
  var btn = el('button', 'ab-btn');
  btn.type = 'button';
  btn.setAttribute('aria-haspopup', 'dialog');
  btn.setAttribute('aria-expanded', 'false');
  btn.appendChild(el('span', 'ab-full', 'Built by Simon'));
  btn.appendChild(el('span', 'ab-short', 'Simon'));

  var pop = el('div', 'ab-pop');
  pop.setAttribute('role', 'dialog');
  pop.setAttribute('aria-label', 'About the author');
  pop.hidden = true;

  pop.appendChild(el('p', 'ab-name', 'Simon · Ottawa, ON'));
  pop.appendChild(el('p', null, 'Energy engineer (MEng, CEM, RETScreen Expert). I build these open-data tools to make Canadian energy, retrofit and construction data easier to read.'));
  pop.appendChild(el('p', 'ab-note', 'A personal project, built with help from Claude (an AI assistant). Every source and assumption is on each page’s methodology.'));

  var more = el('p');
  more.appendChild(link('All tools', 'index.html'));
  more.appendChild(document.createTextNode(' · '));
  more.appendChild(link('GitHub', 'https://github.com/OttawaVisuals/Energy'));
  pop.appendChild(more);

  var go = el('button', 'ab-go', 'Contact');
  go.type = 'button';
  pop.appendChild(go);

  var form = el('form');
  form.hidden = true;
  form.innerHTML =
    '<label for="ab-name">Name (optional)</label><input id="ab-name" name="name" maxlength="80" autocomplete="name">' +
    '<label for="ab-email">Email</label><input id="ab-email" name="email" type="email" maxlength="120" autocomplete="email" required>' +
    '<label for="ab-msg">Message</label><textarea id="ab-msg" name="message" maxlength="2000" required></textarea>' +
    '<input name="website" tabindex="-1" autocomplete="off" aria-hidden="true" style="position:absolute;left:-9999px">' +
    '<p style="margin:10px 0 0"><button class="ab-send" type="submit">Send</button><span class="ab-status" role="status"></span></p>';
  pop.appendChild(form);

  wrap.appendChild(btn);
  wrap.appendChild(pop);

  // Sit beside "All tools" / the theme toggle: append to the group that holds the hub link.
  // (the logo can also link to index.html, so prefer the .sibling-link one)
  var hub = header.querySelector('a.sibling-link[href="index.html"]') || header.querySelector('a[href="index.html"]');
  var group = hub && hub.parentElement !== header ? hub.parentElement : null;
  if (!group) {
    group = header.lastElementChild && header.lastElementChild.tagName !== 'SCRIPT' ? header.lastElementChild : header;
  }
  group.appendChild(wrap);

  // A tight header (ceud at ~1200px) would wrap the button onto a second row: use the short label there.
  // Tighter still: just the initial in a circle.
  function tight() {
    return header.scrollWidth > header.clientWidth || wrap.getBoundingClientRect().top - header.getBoundingClientRect().top > 30;
  }
  // Last resort (phone headers that already overflow): put the button first so it is not pushed off-screen.
  function fit() {
    wrap.classList.remove('ab-compact', 'ab-mini');
    if (group.lastChild !== wrap) group.appendChild(wrap);
    if (!tight()) return;
    wrap.classList.add('ab-compact');
    if (!tight()) return;
    wrap.classList.add('ab-mini');
    if (tight() && group !== header) group.insertBefore(wrap, group.firstChild);
  }
  fit();
  window.addEventListener('resize', fit);
  window.addEventListener('load', fit);
  // Some headers are filled in by the page's own script after load (ceud's selector), so re-fit when they change size.
  if (window.ResizeObserver) {
    var ro = new ResizeObserver(fit);
    ro.observe(header);
    if (group !== header) ro.observe(group);
  }

  /* ---- open / close ---- */
  var pinned = false, timer = null;
  var status = form.querySelector('.ab-status');
  var t0 = Date.now();

  function busy() { // don't close on a stray mouse move while the visitor is typing
    return !form.hidden && (pop.contains(document.activeElement) || form.message.value || form.email.value);
  }
  function open() {
    clearTimeout(timer);
    pop.hidden = false;
    btn.setAttribute('aria-expanded', 'true');
  }
  function close() {
    pop.hidden = true;
    pinned = false;
    btn.setAttribute('aria-expanded', 'false');
  }
  function maybeClose() {
    if (pinned || busy()) return;
    timer = setTimeout(close, 250);
  }

  wrap.addEventListener('mouseenter', function () { if (window.matchMedia('(hover:hover)').matches) open(); });
  wrap.addEventListener('mouseleave', maybeClose);
  btn.addEventListener('click', function () {
    if (pop.hidden) { open(); pinned = true; } else close();
  });
  go.addEventListener('click', function () {
    form.hidden = false;
    go.hidden = true;
    pinned = true;
    form.email.focus();
  });
  document.addEventListener('click', function (e) { if (!wrap.contains(e.target) && !pop.hidden) close(); });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !pop.hidden) { close(); btn.focus(); }
  });

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var f = form.elements;
    if (!f.email.value || !f.message.value.trim()) { status.textContent = 'Please enter your email and a message.'; return; }
    status.textContent = 'Sending…';
    fetch(API, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ name: f.name.value, email: f.email.value, message: f.message.value, website: f.website.value, fillMs: Date.now() - t0 })
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (x) {
        if (x.ok) { form.reset(); status.textContent = 'Sent. Thank you.'; }
        else status.textContent = (x.d && x.d.error) || 'Could not send.';
      })
      .catch(function () { status.textContent = 'Could not send. Please try again later.'; });
  });
})();
