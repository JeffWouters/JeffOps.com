/* Post-page behaviour shared by the static pages and the single-page app.
 *
 * There are two renderers on this site: build.py produces the crawlable HTML,
 * and the SPA renders the same markdown in the browser. Anything that behaves
 * rather than renders belongs here, so the two views cannot drift apart — the
 * bug that gave the Speaking page three different talk lists started as two
 * copies of one small function.
 *
 * Everything in here is an enhancement. With scripting off the article still
 * reads: headings still have ids, the anchors are plain links, and the progress
 * box simply does not move.
 */
(function (global) {
  'use strict';

  var NS = {};

  // ── Heading anchors ───────────────────────────────────────────────────
  // The table of contents gets a reader into a section. This is the way back
  // out: a # beside each heading that copies a link straight to it.
  NS.addHeadingAnchors = function (root, baseUrl) {
    if (!root) return;
    root.querySelectorAll('h2[id], h3[id]').forEach(function (h) {
      if (h.querySelector('.heading-anchor')) return;
      var a = document.createElement('a');
      a.className = 'heading-anchor';
      a.href = '#' + h.id;
      a.textContent = '#';
      a.setAttribute('aria-label', 'Link to “' + h.textContent.trim() + '”');
      a.addEventListener('click', function (e) {
        e.preventDefault();
        var url = (baseUrl || location.origin + location.pathname).split('#')[0] + '#' + h.id;
        history.replaceState(null, '', '#' + h.id);
        h.scrollIntoView({ behavior: 'smooth', block: 'start' });
        if (navigator.clipboard && global.isSecureContext) {
          navigator.clipboard.writeText(url).then(function () { flash(a); }, function () {});
        }
      });
      h.appendChild(a);
    });
  };

  function flash(anchor) {
    anchor.classList.add('copied');
    setTimeout(function () { anchor.classList.remove('copied'); }, 1400);
  }

  // ── Callouts ──────────────────────────────────────────────────────────
  // GitHub's blockquote syntax: > [!WARNING] on the first line. build.py does
  // this server-side so the crawled HTML carries the real markup; this is the
  // SPA's copy, because marked renders in the browser and never sees Python.
  // Keep the two in step — the class names and the type list are the contract.
  var CALLOUT_TYPES = {
    NOTE: 'Note', TIP: 'Tip', IMPORTANT: 'Important',
    WARNING: 'Warning', CAUTION: 'Caution'
  };

  NS.renderCallouts = function (root) {
    if (!root) return;
    root.querySelectorAll('blockquote').forEach(function (quote) {
      if (quote.classList.contains('callout')) return;
      var first = quote.firstElementChild;
      if (!first || first.tagName !== 'P') return;
      var match = first.innerHTML.match(/^\s*\[!([A-Z]+)\]\s*(?:<br\s*\/?>)?\s*/);
      if (!match) return;
      var kind = match[1];
      if (!CALLOUT_TYPES[kind]) return;
      first.innerHTML = first.innerHTML.slice(match[0].length);
      if (!first.textContent.trim() && !first.querySelector('img,code')) first.remove();
      quote.className = 'callout callout-' + kind.toLowerCase();
      var label = document.createElement('div');
      label.className = 'callout-label';
      label.textContent = CALLOUT_TYPES[kind];
      quote.insertBefore(label, quote.firstChild);
    });
  };

  // ── Syntax highlighting ───────────────────────────────────────────────
  // 122KB of script plus a stylesheet. The static pages carry it in their
  // markup, because the build knows at render time whether the page has a code
  // block. The app cannot know until it has rendered a post, so it asks here,
  // and a visitor who never opens a post with code never pays for it.
  var HLJS_SRC = '/vendor/highlight.min.js';
  var HLJS_CSS = '/vendor/github-dark.min.css';
  var hljsPending = null;

  function loadOnce(make) {
    return new Promise(function (resolve) {
      var el = make();
      el.onload = resolve;
      el.onerror = resolve;   // unhighlighted code is still readable code
      document.head.appendChild(el);
    });
  }

  NS.highlight = function (root) {
    if (!root) return;
    var blocks = [].slice.call(root.querySelectorAll('pre code'))
      .filter(function (el) { return !el.className.includes('language-mermaid'); });
    if (!blocks.length) return;

    var run = function () {
      if (!global.hljs) return;
      blocks.forEach(function (el) {
        if (!el.dataset.highlighted) global.hljs.highlightElement(el);
      });
    };
    if (global.hljs) { run(); return; }
    if (!hljsPending) {
      hljsPending = Promise.all([
        loadOnce(function () {
          var l = document.createElement('link');
          l.rel = 'stylesheet'; l.href = HLJS_CSS; return l;
        }),
        loadOnce(function () {
          var s = document.createElement('script');
          s.src = HLJS_SRC; return s;
        })
      ]);
    }
    hljsPending.then(run);
  };

  // ── Mermaid diagrams ──────────────────────────────────────────────────
  // Mermaid is 2.9MB, 875KB gzipped — larger than the whole of the rest of the
  // site — and it was being loaded eagerly by every post page, every newsletter
  // edition and the home page. No post contains a diagram, so every one of
  // those downloads was for nothing.
  //
  // It is not vendored either: committing 2.9MB for something unused costs more
  // than the request would. This fetches it from a CDN the first time a diagram
  // is actually on the page, and never otherwise.
  var MERMAID_SRC = 'https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.6.1/mermaid.min.js';
  var MERMAID_THEME = {
    startOnLoad: false, theme: 'dark',
    themeVariables: {
      primaryColor: '#0f1217', primaryTextColor: '#e8edf2', primaryBorderColor: '#00D9FF',
      lineColor: '#00D9FF', secondaryColor: '#151920', tertiaryColor: '#1c2028',
      background: '#0a0c0f', mainBkg: '#0f1217', nodeBorder: '#00D9FF',
      clusterBkg: '#151920', titleColor: '#e8edf2', edgeLabelBackground: '#0f1217',
      fontFamily: 'JetBrains Mono, monospace'
    }
  };
  var mermaidPending = null;

  NS.renderDiagrams = function (root) {
    if (!root) return;
    var blocks = root.querySelectorAll('code.language-mermaid');
    if (!blocks.length) return;

    // Swap each code block for the div mermaid expects, before loading it.
    blocks.forEach(function (el) {
      var div = document.createElement('div');
      div.className = 'mermaid';
      div.textContent = el.textContent;
      (el.parentElement || el).replaceWith(div);
    });

    var run = function () {
      if (!global.mermaid) return;
      global.mermaid.initialize(MERMAID_THEME);
      global.mermaid.run();
    };
    if (global.mermaid) { run(); return; }
    if (!mermaidPending) {
      mermaidPending = new Promise(function (resolve) {
        var s = document.createElement('script');
        s.src = MERMAID_SRC;
        s.onload = resolve;
        s.onerror = function () {
          // The diagram source stays visible as text, which is readable and
          // honest, rather than an empty box where a picture should be.
          document.querySelectorAll('.mermaid').forEach(function (d) {
            d.classList.add('mermaid-unrendered');
          });
          resolve();
        };
        document.head.appendChild(s);
      });
    }
    mermaidPending.then(run);
  };

  // ── Progress ──────────────────────────────────────────────────────────
  // The percentage answers "where am I in the scrollbar". Minutes left answer
  // "can I finish this before my next meeting", which is the question people
  // actually have. Both are shown; the minutes are derived from the same read
  // time already printed in the header, so there is no second estimate to rot.
  NS.readMinutes = function () {
    var el = document.getElementById('post-readtime');
    var m = el && el.textContent.match(/(\d+)/);
    return m ? parseInt(m[1], 10) : 0;
  };

  NS.initProgress = function () {
    var bar = document.getElementById('read-progress');
    var pctEl = document.getElementById('scroll-pct');
    var sbEl = document.getElementById('scroll-bar');
    var leftEl = document.getElementById('scroll-remaining');
    if (bar) { bar.style.display = 'block'; bar.style.width = '0%'; }

    function update() {
      var doc = document.documentElement;
      var scrollable = doc.scrollHeight - doc.clientHeight;
      var pct = scrollable > 0
        ? Math.max(0, Math.min(100, Math.round((doc.scrollTop / scrollable) * 100)))
        : 0;
      if (bar) bar.style.width = pct + '%';
      if (pctEl) pctEl.textContent = pct + '%';
      if (sbEl) sbEl.style.width = pct + '%';
      if (leftEl) {
        var total = NS.readMinutes();
        if (!total) { leftEl.textContent = ''; return; }
        // Round up while there is anything left, so a reader three quarters
        // through a 4 minute piece is told "1 min left" rather than "0".
        var left = Math.ceil(total * (1 - pct / 100));
        leftEl.textContent = pct >= 100 || left <= 0 ? 'finished' : left + ' min left';
      }
    }

    if (NS._progressBound) global.removeEventListener('scroll', NS._progressBound);
    NS._progressBound = update;
    global.addEventListener('scroll', update, { passive: true });
    update();
    return update;
  };

  // ── Copy link ─────────────────────────────────────────────────────────
  // One implementation, two callers. app.js and post-page.js each had their
  // own, differing only in where the URL came from — so getUrl is the argument.
  NS.copyLink = function (getUrl) {
    var btn = document.getElementById('copy-link-btn');
    var label = btn ? btn.textContent : '';
    var done = function (ok) {
      if (!btn) return;
      btn.textContent = ok ? '✓ Copied!' : '✗ Copy failed';
      setTimeout(function () { btn.textContent = label; }, 2000);
    };
    var url = typeof getUrl === 'function' ? getUrl() : getUrl;
    if (!url || !navigator.clipboard || !global.isSecureContext) { done(false); return; }
    navigator.clipboard.writeText(url).then(function () { done(true); },
                                           function () { done(false); });
  };

  // ── Copy as Markdown ──────────────────────────────────────────────────
  // For readers who want to hand the piece to a model rather than read it in a
  // browser. getMarkdown returns a string or a promise for one.
  NS.initCopyMarkdown = function (getMarkdown) {
    var btn = document.getElementById('copy-md-btn');
    if (!btn) return;
    btn.onclick = function () {
      var label = '⌄ Copy as Markdown';
      Promise.resolve()
        .then(getMarkdown)
        .then(function (text) {
          if (!text) throw new Error('no markdown');
          if (!navigator.clipboard || !global.isSecureContext) throw new Error('no clipboard');
          return navigator.clipboard.writeText(text);
        })
        .then(function () { btn.textContent = '✓ Copied'; },
              function () { btn.textContent = '✗ Not available'; })
        .then(function () {
          setTimeout(function () { btn.textContent = label; }, 2000);
        });
    };
  };

  // The Copy link button exists on the static pages and in the app, and each
  // defines its own window.copyLink. One listener, loaded by both.
  document.addEventListener('click', function (event) {
    var el = event.target.closest('[data-action="copy-link"]');
    if (el && typeof global.copyLink === 'function') global.copyLink();
  });

  global.JeffOpsPost = NS;
})(window);
