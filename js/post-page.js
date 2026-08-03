/* Enhancements for statically rendered post pages.
 *
 * The post content is already in the HTML — this file only adds behaviour on
 * top of it. Nothing here is required to read the article, which is the point:
 * with JavaScript disabled or unavailable the page still works.
 */
(function () {
  'use strict';

  var content = document.getElementById('post-content');
  if (!content) return;

  // ── Syntax highlighting ─────────────────────────────────────────────
  if (window.hljs) {
    content.querySelectorAll('pre code').forEach(function (el) {
      if (!el.className.includes('language-mermaid')) hljs.highlightElement(el);
    });
  }

  // ── Mermaid diagrams ────────────────────────────────────────────────
  if (window.mermaid) {
    mermaid.initialize({
      startOnLoad: false, theme: 'dark',
      themeVariables: {
        primaryColor: '#0f1217', primaryTextColor: '#e8edf2', primaryBorderColor: '#00D9FF',
        lineColor: '#00D9FF', secondaryColor: '#151920', tertiaryColor: '#1c2028',
        background: '#0a0c0f', mainBkg: '#0f1217', nodeBorder: '#00D9FF',
        clusterBkg: '#151920', titleColor: '#e8edf2', edgeLabelBackground: '#0f1217',
        fontFamily: 'JetBrains Mono, monospace'
      }
    });
    var diagrams = content.querySelectorAll('code.language-mermaid');
    diagrams.forEach(function (el) {
      var div = document.createElement('div');
      div.className = 'mermaid';
      div.textContent = el.textContent;
      (el.parentElement || el).replaceWith(div);
    });
    if (diagrams.length) mermaid.run();
  }

  // ── Copy buttons on code blocks ─────────────────────────────────────
  content.querySelectorAll('pre').forEach(function (pre) {
    var btn = document.createElement('button');
    btn.className = 'copy-btn';
    btn.type = 'button';
    btn.textContent = 'Copy';
    btn.onclick = function () {
      var code = pre.querySelector('code');
      if (code && navigator.clipboard) {
        navigator.clipboard.writeText(code.textContent).then(function () {
          btn.textContent = '✓ Copied';
          setTimeout(function () { btn.textContent = 'Copy'; }, 2000);
        });
      }
    };
    pre.appendChild(btn);
  });

  // ── Shared post behaviour ───────────────────────────────────────────
  // Anchors, progress and Copy as Markdown live in post-enhance.js so the SPA
  // renders the same behaviour from the same code. Callouts are already in this
  // page's HTML — build.py renders them — so they are not re-run here.
  var shared = window.JeffOpsPost;
  if (shared) {
    var canonical = document.querySelector('link[rel="canonical"]');
    shared.addHeadingAnchors(content, canonical ? canonical.href : null);
    shared.initProgress();
    // The markdown sits next to the page as index.md. Fetching it keeps the
    // article out of the HTML twice over.
    shared.initCopyMarkdown(function () {
      var src = document.querySelector('link[rel="alternate"][type="text/markdown"]');
      return fetch(src ? src.getAttribute('href') : 'index.md')
        .then(function (r) { return r.ok ? r.text() : ''; });
    });
  }

  // ── Table-of-contents scroll spy ────────────────────────────────────
  var tocAnchors = Array.prototype.slice.call(document.querySelectorAll('#toc-links a'));
  if (tocAnchors.length && 'IntersectionObserver' in window) {
    var headings = tocAnchors
      .map(function (a) { return document.getElementById(a.dataset.target); })
      .filter(Boolean);

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var idx = headings.indexOf(entry.target);
        if (idx < 0) return;
        tocAnchors.forEach(function (a) { a.classList.remove('active'); });
        if (tocAnchors[idx]) tocAnchors[idx].classList.add('active');
        document.querySelectorAll('.toc-progress-dot').forEach(function (dot, di) {
          dot.classList.toggle('done', di <= idx);
        });
      });
    }, { rootMargin: '-60px 0px -70% 0px', threshold: 0 });

    headings.forEach(function (h) { observer.observe(h); });

    tocAnchors.forEach(function (a) {
      a.addEventListener('click', function (e) {
        var target = document.getElementById(a.dataset.target);
        if (!target) return;
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        history.replaceState(null, '', '#' + a.dataset.target);
      });
    });
  }

  // ── Share ───────────────────────────────────────────────────────────
  // The canonical link is in the document, so there is no state to guess at.
  window.copyLink = function () {
    var link = document.querySelector('link[rel="canonical"]');
    var url = link ? link.href : window.location.href;
    var btn = document.getElementById('copy-link-btn');
    if (!navigator.clipboard) return;
    navigator.clipboard.writeText(url).then(function () {
      if (!btn) return;
      var original = btn.textContent;
      btn.textContent = '✓ Copied';
      setTimeout(function () { btn.textContent = original; }, 2000);
    });
  };
})();
