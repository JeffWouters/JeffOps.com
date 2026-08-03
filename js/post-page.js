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
  // Loaded on demand by the shared renderer, and only when a diagram exists.
  if (window.JeffOpsPost) window.JeffOpsPost.renderDiagrams(content);

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
  // The copying itself is shared with the app; only the source of the URL
  // differs between the two views.
  window.copyLink = function () {
    if (!shared) return;
    shared.copyLink(function () {
      var link = document.querySelector('link[rel="canonical"]');
      return link ? link.href : window.location.href;
    });
  };
})();
