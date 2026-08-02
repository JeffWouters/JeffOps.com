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

  // ── Read progress + scroll percentage ───────────────────────────────
  var bar = document.getElementById('read-progress');
  var pctEl = document.getElementById('scroll-pct');
  var sbEl = document.getElementById('scroll-bar');
  if (bar) bar.style.display = 'block';

  function onScroll() {
    var doc = document.documentElement;
    var scrollable = doc.scrollHeight - doc.clientHeight;
    var pct = scrollable > 0 ? Math.min(100, Math.round((doc.scrollTop / scrollable) * 100)) : 0;
    if (bar) bar.style.width = pct + '%';
    if (pctEl) pctEl.textContent = pct + '%';
    if (sbEl) sbEl.style.width = pct + '%';
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

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
