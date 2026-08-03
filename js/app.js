const posts = {
  'k8s-cost': {
    title:'Cutting Kubernetes Costs by 60% Without Sacrificing Reliability',
    date:'Nov 18, 2024', readtime:'12 min read',
    tags:['kubernetes','finops'], related:['gitops','platform'],
    folder:'blog/2024/20241118 - Cutting Kubernetes Costs by 60% Without Sacrificing Reliability',
    excerpt:'A deep dive into VPA, HPA, spot instances, and right-sizing — with real numbers from a production migration.'
  },
  'gitops': {
    title:'GitOps in Production: Lessons from 2 Years of ArgoCD',
    date:'Nov 5, 2024', readtime:'9 min read',
    tags:['devops','platform'], related:['k8s-cost','platform'],
    folder:'blog/2024/20241105 - GitOps in Production Lessons from 2 Years of ArgoCD',
    excerpt:'What they don\'t tell you in the docs — drift detection, multi-cluster strategies, and escape hatches.'
  },
  'observability': {
    title:'Observability is Not Monitoring: A Practical Guide to OpenTelemetry',
    date:'Oct 29, 2024', readtime:'14 min read',
    tags:['observability'], related:['k8s-cost','gitops'],
    folder:'blog/2024/20241029 - Observability is Not Monitoring A Practical Guide to OpenTelemetry',
    excerpt:'The mental model shift that changes how you debug distributed systems — and how to get started with OTel in an afternoon.'
  },
  'platform': {
    title:'Building an Internal Developer Platform: Where to Start',
    date:'Oct 14, 2024', readtime:'16 min read',
    tags:['platform','kubernetes'], related:['gitops','observability'],
    folder:'blog/2024/20241014 - Building an Internal Developer Platform Where to Start',
    excerpt:'Platform engineering is not "Kubernetes + a portal." Here\'s the maturity model and what to tackle first.'
  }
};

// ── PAGE ROUTING ───────────────────────────────────────
function showPage(name, updateHash = true) {
  const page = document.getElementById('page-' + name) || document.getElementById('page-home');
  if (!page) return;

  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  // Clear all nav active states
  document.querySelectorAll('.nav-links a').forEach(a => a.classList.remove('active'));
  page.classList.add('active');

  // Mark the direct nav item active if it exists
  const navEl = document.getElementById('nav-' + name);
  if (navEl) navEl.classList.add('active');

  // Also mark the parent dropdown label active for sub-pages
  const contentPages = ['blog','newsletter','videos'];
  const servicePages = ['speaking','training'];
  if (contentPages.includes(name)) {
    const el = document.getElementById('nav-content');
    if (el) el.classList.add('active');
  }
  if (servicePages.includes(name)) {
    const el = document.getElementById('nav-services');
    if (el) el.classList.add('active');
  }

  if (name === 'blog') {
    populateBlogList();
    loadTopicFilters();
    loadSeriesFilters();
  }

  if (name === 'speaking') {
    loadSpeakingTopics();
    loadSpeakingTalks();
  }

  if (updateHash) {
    window.location.hash = name;
  }

  window.scrollTo(0, 0);
  document.getElementById('read-progress').style.display = 'none';
  setTimeout(() => {
    document.querySelectorAll('.page.active .animate').forEach(el => {
      el.style.animation = 'none'; el.offsetHeight; el.style.animation = '';
    });
  }, 10);
}

function buildHash(route, payload) {
  if (route === 'post' && payload) {
    return 'post=' + encodeURIComponent(payload);
  }
  return route;
}

function parseHash() {
  const hash = (window.location.hash || '').replace(/^#/, '');
  if (!hash) return { route: 'home' };
  if (hash.startsWith('post=')) {
    return { route: 'post', payload: decodeURIComponent(hash.slice('post='.length)) };
  }
  return { route: hash };
}

function navigateFromHash() {
  const { route, payload } = parseHash();
  if (route === 'post' && payload) {
    if (posts[payload]) {
      showPost(payload, undefined, false);
      return;
    }
    if (window._blogEntriesByFolder && window._blogEntriesByFolder[payload]) {
      showPostFromFolder(payload, false);
      return;
    }
    showPostFromFolder(payload, false);
    return;
  }

  const routeName = route || 'home';
  const pageExists = Boolean(document.getElementById('page-' + routeName));
  showPage(pageExists ? routeName : 'home', false);
}

// ── BLOG LIST GENERATION ─────────────────────────────────
async function populateBlogList() {
  const postsIndex = await loadBlogIndex();
  const list = document.getElementById('post-list');
  if (!list) return;
  list.innerHTML = '';

  const entries = postsIndex || Object.entries(posts).map(([id, post]) => ({ id, ...post }));
  entries.forEach(post => {
    const item = document.createElement('div');
    item.className = 'post-item';
    if (post.tags?.length) item.dataset.tags = post.tags.join(' ');
    if (post.series) item.dataset.series = post.series;
    // Prefer the statically rendered page. It is a real URL: shareable,
    // linkable, and crawlable. The hash route stays as a fallback for entries
    // that predate the build step.
    item.onclick = () => {
      if (post.url) {
        window.location.href = post.url;
      } else if (post.folder) {
        showPostFromFolder(post.folder);
      } else if (post.id) {
        showPost(post.id);
      }
    };

    const tagHtml = (post.tags || []).map(tag => `<span class="tag">${tag}</span>`).join('');
    const seriesHtml = post.series_label ? `<span class="tag series-badge">${post.series_label}</span>` : '';
    const postLink = post.url ? post.url : post.folder ? `#post=${encodeURIComponent(post.folder)}` : post.id ? `#post=${encodeURIComponent(post.id)}` : '#';
    item.innerHTML = `
      <div>
        <a class="post-title" href="${postLink}">${post.title}</a>
        <div class="post-excerpt">${post.excerpt || ''}</div>
        ${seriesHtml || tagHtml ? `<div style="display:flex;flex-wrap:wrap;gap:6px;margin:8px 0;">${seriesHtml}${tagHtml}</div>` : ''}
        <div class="post-meta"><span>${post.date}</span><span>${post.readtime}</span></div>
      </div>
      <div class="post-read-time">→</div>
    `;

    list.appendChild(item);
  });
}

// ── SHOW POST ─────────────────────────────────────────
async function loadPostMarkdown(post) {
  if (post.markdown || !post.folder) return;
  // Prefer embedded markdown when blog index data exists; avoid file:// fetches
  if (window._blogEntriesByFolder && window._blogEntriesByFolder[post.folder] && window._blogEntriesByFolder[post.folder].markdown) {
    post.markdown = window._blogEntriesByFolder[post.folder].markdown;
    return;
  }

  // If there's a generated blog index available but this entry has no markdown, skip fetching
  if (window._blogIndexData) {
    console.warn('No embedded markdown available for', post.folder);
    return;
  }

  try {
    const path = post.folder.replace(/\/+$|$/, '') + '/post.md';
    const r = await fetch(encodeURI(path));
    if (!r.ok) {
      console.warn('Markdown not found for', post.folder);
      return;
    }
    post.markdown = await r.text();
  } catch (e) {
    console.warn('Failed to load markdown for', post.folder, e);
  }
}

async function showPost(id, postObj, updateHash = true) {
  const post = postObj || posts[id];
  if (!post) return;
  if (!post.markdown && post.folder && window._blogEntriesByFolder?.[post.folder]?.markdown) {
    post.markdown = window._blogEntriesByFolder[post.folder].markdown;
  }
  if (!post.markdown && post.folder) await loadPostMarkdown(post);
  if (!post.markdown) return;
  window._currentPost = post.folder || id || 'post';
  // The share buttons need the record, not just the folder string: it is what
  // carries the canonical URL.
  window._currentPostRecord = post;

  document.getElementById('post-title').textContent = post.title;
  document.getElementById('post-date').textContent = post.date;
  document.getElementById('post-readtime').textContent = post.readtime;
  renderFreshness(post);
  renderSeriesNav(post);

  // Render markdown
  document.getElementById('post-content').innerHTML = marked.parse(post.markdown);
  if (window.JeffOpsPost) JeffOpsPost.renderCallouts(document.getElementById('post-content'));

  // Add copy buttons
  document.querySelectorAll('#post-content pre').forEach(pre => {
    const btn = document.createElement('button');
    btn.className = 'copy-btn';
    btn.textContent = 'Copy';
    btn.onclick = () => {
      const code = pre.querySelector('code');
      if (code && navigator.clipboard) {
        navigator.clipboard.writeText(code.textContent).then(() => {
          btn.textContent = '✓ Copied';
          setTimeout(() => { btn.textContent = 'Copy'; }, 2000);
        });
      }
    };
    pre.appendChild(btn);
  });

  // Syntax highlight
  document.querySelectorAll('#post-content pre code').forEach(el => {
    if (!el.className.includes('language-mermaid') && window.hljs) hljs.highlightElement(el);
  });

  // Render mermaid
  document.querySelectorAll('#post-content code.language-mermaid').forEach(el => {
    const pre = el.parentElement;
    const div = document.createElement('div');
    div.className = 'mermaid';
    div.textContent = el.textContent;
    pre.replaceWith(div);
  });
  if (window.mermaid) mermaid.run();

  // Inline newsletter CTA at mid-point
  const paras = document.querySelectorAll('#post-content p');
  const midIdx = Math.floor(paras.length / 2);
  if (paras[midIdx]) {
    const cta = document.createElement('div');
    cta.className = 'inline-nl-cta';
    cta.innerHTML = '<p><strong>The JeffOps Dispatch</strong> — arguments like this every other Monday, in more depth than fits in a post.</p><button class="inline-nl-btn" onclick="showPage(\'newsletter\')">Subscribe free →</button>';
    paras[midIdx].insertAdjacentElement('afterend', cta);
  }

  // Build TOC with progress dots.
  // Heading ids come from the build's markdown renderer via the index, so a
  // fragment copied here resolves on the static page too. 'heading-N' is only
  // the fallback for a record built before that field existed.
  const headings = document.querySelectorAll('#post-content h2, #post-content h3');
  const headingMeta = post.headings || [];
  const tocLinks = document.getElementById('toc-links');
  tocLinks.innerHTML = '';
  headings.forEach((h, i) => {
    h.id = (headingMeta[i] && headingMeta[i].id) || ('heading-' + i);
    h.dataset.idx = i;
    const a = document.createElement('a');
    a.dataset.idx = i;
    a.dataset.target = h.id;
    a.href = '#' + h.id;
    if (h.tagName === 'H3') a.classList.add('h3');
    const dot = document.createElement('span');
    dot.className = 'toc-progress-dot';
    dot.id = 'tdot-' + i;
    a.textContent = h.textContent;
    a.appendChild(dot);
    a.onclick = e => {
      e.preventDefault();
      h.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };
    tocLinks.appendChild(a);
  });

  // Related posts
  const related = post.related || [];
  const relSec = document.getElementById('related-section');
  if (related.length) {
    relSec.innerHTML = '<div class="related-posts"><div class="related-title">// You might also like</div><div class="related-grid" id="related-grid"></div></div>';
    related.forEach(rid => {
      const rp = (window._blogEntriesByFolder && window._blogEntriesByFolder[rid]) || posts[rid];
      if (!rp) return;
      const card = document.createElement('div');
      card.className = 'related-card';
      card.innerHTML = '<div class="related-card-type">// Blog Post</div><div class="related-card-title">' + rp.title + '</div><div class="related-card-meta">' + rp.date + ' · ' + rp.readtime + '</div>';
      card.onclick = () => {
        if (rp.folder) {
          showPostFromFolder(rp.folder);
        } else {
          showPost(rid);
        }
      };
      document.getElementById('related-grid').appendChild(card);
    });
  } else { relSec.innerHTML = ''; }

  // Scroll-spy
  if (window._tocObserver) window._tocObserver.disconnect();
  window._tocObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        // Read the index off the element rather than parsing it out of the id:
        // ids are now slugs shared with the static page, not sequence numbers.
        const idx = parseInt(entry.target.dataset.idx, 10);
        if (Number.isNaN(idx)) return;
        document.querySelectorAll('#toc-links a').forEach(a => a.classList.remove('active'));
        const activeA = document.querySelector('#toc-links a[data-idx="' + idx + '"]');
        if (activeA) activeA.classList.add('active');
        document.querySelectorAll('.toc-progress-dot').forEach((d, di) => {
          d.classList.toggle('done', di <= idx);
        });
      }
    });
  }, { rootMargin: '-60px 0px -70% 0px', threshold: 0 });
  headings.forEach(h => window._tocObserver.observe(h));

  const hashPayload = post.folder || id;
  if (updateHash && hashPayload) {
    window.location.hash = buildHash('post', hashPayload);
  }

  showPage('post', false);

  if (window.JeffOpsPost) {
    JeffOpsPost.addHeadingAnchors(document.getElementById('post-content'), currentShare().url);
    JeffOpsPost.initProgress();
    JeffOpsPost.initCopyMarkdown(() => (window._currentPostRecord || {}).markdown || '');
  }
}

// ── FRESHNESS ─────────────────────────────────────────
// A technical post that nobody has revisited in a year is not necessarily
// wrong, but the page should not imply it has been checked. `reviewed` in the
// frontmatter is the claim; without one the publish date stands in, and the
// threshold below is the same number build.py uses (STALE_AFTER_DAYS).
const STALE_AFTER_DAYS = 365;

function renderFreshness(post) {
  const meta = document.getElementById('post-reviewed');
  const banner = document.getElementById('stale-note');
  if (meta) {
    meta.textContent = (post.reviewed_label && post.reviewed_label !== post.date)
      ? 'Reviewed ' + post.reviewed_label : '';
  }
  if (!banner) return;
  const stamp = post.reviewed || post.iso || '';
  const when = stamp ? new Date(stamp) : null;
  const days = when && !isNaN(when) ? (Date.now() - when.getTime()) / 86400000 : 0;
  if (days <= STALE_AFTER_DAYS || post.is_newsletter) { banner.innerHTML = ''; return; }
  const age = days < 730 ? 'over a year' : 'over ' + Math.floor(days / 365) + ' years';
  banner.innerHTML = '<aside class="stale-note"><strong>This post has not been reviewed in '
    + age + '.</strong> It was accurate when written. Version numbers, menu paths and '
    + 'vendor behaviour all move, so check anything you are about to depend on.</aside>';
}

// ── SERIES NAVIGATION ─────────────────────────────────
// Driven by the `series:` line in a post's frontmatter. Nothing renders until
// two posts share one, which is deliberate — what belongs in a series is an
// editorial call, not something to infer from tags.
function renderSeriesNav(post) {
  const host = document.getElementById('series-nav');
  if (!host) return;
  host.innerHTML = '';
  if (!post.series) return;
  const all = window._blogIndexData || window._blogEntries || [];
  const members = all.filter(p => p.series === post.series)
                     .sort((a, b) => (a.iso || '').localeCompare(b.iso || ''));
  if (members.length < 2) return;
  const idx = members.findIndex(p => p.url === post.url);
  if (idx < 0) return;

  const link = (item, rel) => {
    const a = document.createElement('a');
    a.className = 'series-link';
    a.href = item.url;
    a.rel = rel;
    a.textContent = rel === 'prev' ? '‹ ' + item.title : item.title + ' ›';
    a.onclick = e => { e.preventDefault(); showPostFromFolder(item.folder); };
    return a;
  };

  const nav = document.createElement('nav');
  nav.className = 'series-nav';
  nav.setAttribute('aria-label', 'Series navigation');
  const head = document.createElement('div');
  head.className = 'series-nav-head';
  const label = document.createElement('span');
  label.className = 'series-nav-label';
  label.textContent = '// ' + (post.series_label || post.series);
  const count = document.createElement('span');
  count.className = 'series-nav-count';
  count.textContent = 'Part ' + (idx + 1) + ' of ' + members.length;
  head.append(label, count);
  const links = document.createElement('div');
  links.className = 'series-nav-links';
  if (idx > 0) links.appendChild(link(members[idx - 1], 'prev'));
  if (idx + 1 < members.length) links.appendChild(link(members[idx + 1], 'next'));
  nav.append(head, links);
  host.appendChild(nav);
}

// ── SHARE ─────────────────────────────────────────────
// Everything here shares the canonical URL rather than the SPA's #post= hash.
// LinkedIn and X both scrape whatever they are handed, and a hash URL resolves
// to the home page, so a shared post would arrive carrying the site's Open
// Graph card instead of its own — the same failure we chased through the Post
// Inspector. The blog index already records `url` and `canonical` for every
// post, so this reads them rather than rebuilding a slug in a second place.
const SITE_ORIGIN = 'https://jeffops.com';

function currentShare() {
  const post = window._currentPostRecord;
  const title = (post && post.title)
    || (document.getElementById('post-title') || {}).textContent
    || 'JeffOps';
  let url;
  if (post && post.canonical) {
    url = post.canonical;
  } else if (post && post.url) {
    url = SITE_ORIGIN + post.url;
  } else if (window._currentPost) {
    // No record to read a canonical from — fall back to the hash route, which
    // at least lands the reader on the right post.
    url = SITE_ORIGIN + '/#post=' + encodeURIComponent(window._currentPost);
  } else {
    url = SITE_ORIGIN + '/';
  }
  return { url: url, title: title };
}

function shareTo(network) {
  const share = currentShare();
  const targets = {
    x: 'https://x.com/intent/post?url=' + encodeURIComponent(share.url)
       + '&text=' + encodeURIComponent(share.title),
    linkedin: 'https://www.linkedin.com/sharing/share-offsite/?url='
       + encodeURIComponent(share.url),
  };
  if (targets[network]) window.open(targets[network], '_blank', 'noopener,noreferrer');
}

function copyLink() {
  const url = currentShare().url;
  const btn = document.getElementById('copy-link-btn');
  const done = function (ok) {
    if (!btn) return;
    btn.textContent = ok ? '✓ Copied!' : '✗ Copy failed';
    setTimeout(function () { btn.textContent = '⎘ Copy link'; }, 2000);
  };
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(url).then(function () { done(true); },
                                           function () { done(false); });
  } else {
    done(false);
  }
}

// ── BLOG FILTERING ────────────────────────────────────
window._blogFilterState = { query: '', tag: 'all', series: 'all' };

function applyBlogFilters() {
  const query = window._blogFilterState.query;
  const tag = window._blogFilterState.tag;
  const series = window._blogFilterState.series;
  document.querySelectorAll('.post-item').forEach(item => {
    const textMatch = item.textContent.toLowerCase().includes(query);
    const tags = (item.dataset.tags || '').split(' ').filter(Boolean);
    const seriesValue = item.dataset.series || '';
    const tagMatch = tag === 'all' || tags.includes(tag);
    const seriesMatch = series === 'all' || seriesValue === series;
    item.style.display = textMatch && tagMatch && seriesMatch ? '' : 'none';
  });
}

function filterPosts(q) {
  window._blogFilterState.query = q.toLowerCase();
  applyBlogFilters();
}
function setTag(tag, btn) {
  window._blogFilterState.tag = tag;
  const container = document.getElementById('topic-filter-buttons');
  if (container) container.querySelectorAll('.topic-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  applyBlogFilters();
}
function setSeries(series, btn) {
  window._blogFilterState.series = series;
  const container = document.getElementById('series-filter-buttons');
  if (container) container.querySelectorAll('.series-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  applyBlogFilters();
}

// ── NEWSLETTER ────────────────────────────────────────
// Subscription is handled by a plain link to LinkedIn in index.html, so there
// is no handler here by design.
//
// What used to be here: handleSubscribe() cleared the input and set its
// placeholder to "✓ You're subscribed! See you Thursday." It never stored or
// sent anything. Every address typed into it was discarded while the visitor
// was told they had subscribed. Do not reintroduce a confirmation message
// without a backend that has actually received the address.

// ── SPEAKING ENQUIRY ──────────────────────────────────
function loadSpeakingTopics() {
  const select = document.getElementById('eq-topic');
  if (!select) return;
  select.innerHTML = '<option value="">— Select —</option>';
  if (window._speakingTopics && Array.isArray(window._speakingTopics)) {
    window._speakingTopics.forEach(topic => {
      const option = document.createElement('option');
      option.value = topic.value || topic;
      option.textContent = topic.label || topic;
      select.appendChild(option);
    });
    handleTopicChange();
    return;
  }

  fetch('speaking_topics.json')
    .then(res => res.ok ? res.json() : Promise.reject())
    .then(topics => {
      topics.forEach(topic => {
        const option = document.createElement('option');
        option.value = topic.value;
        option.textContent = topic.label;
        select.appendChild(option);
      });
    })
    .catch(() => {
      const fallback = [
        'Platform Engineering & IDPs',
        'Kubernetes & Cloud Native',
        'DevOps Culture & DORA',
        'Observability & Reliability',
        'Developer Experience',
        'Other'
      ];
      fallback.forEach(label => {
        const option = document.createElement('option');
        option.value = label === 'Other' ? 'other' : label;
        option.textContent = label;
        select.appendChild(option);
      });
    })
    .finally(() => handleTopicChange());
}

function loadSpeakingTalks() {
  const container = document.getElementById('talks-list');
  if (!container) return;
  container.innerHTML = '<div class="talk-item">Loading talks…</div>';

  const renderTalk = talk => {
    const item = document.createElement('div');
    item.className = 'talk-item';

    const date = new Date(talk.date);
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const month = months[date.getMonth()] || '';
    const day = String(date.getDate()).padStart(2, '0');
    const year = String(date.getFullYear());

    const badge = talk.statusLabel ? `<span class="talk-badge ${talk.status === 'Upcoming' ? 'badge-upcoming' : 'badge-past'}">${talk.statusLabel}</span>` : '';
    const linkButtons = talk.links.map(link => {
      if (link.type === 'abstract') {
        return `<button class="talk-link talk-link--abstract" type="button">${link.label}<div class="abstract-popup"><div class="abstract-popup-title">${link.abstractTitle || talk.title}</div><div class="abstract-popup-text">${link.abstractText || ''}</div></div></button>`;
      }
      const href = link.href || '#';
      return `<a class="talk-link" href="${href}" target="_blank" rel="noopener">${link.label}</a>`;
    }).join('');

    item.innerHTML = `
      <div class="talk-date-col"><div class="talk-month">${month}</div><div class="talk-day">${day}</div><div class="talk-year">${year}</div></div>
      <div>
        <div class="talk-event">
          <span class="talk-event-head">${talk.event}${badge}</span>
          <div class="talk-links">${linkButtons}</div>
        </div>
        <div class="talk-title">${talk.title}</div>
        <div class="talk-location">📍 ${talk.location}</div>
      </div>
    `;

    container.appendChild(item);
  };

  if (window._speakingTalks && Array.isArray(window._speakingTalks)) {
    container.innerHTML = '';
    window._speakingTalks.forEach(renderTalk);
    return;
  }

  fetch('speaking_talks.json')
    .then(res => res.ok ? res.json() : Promise.reject())
    .then(talks => {
      container.innerHTML = '';
      talks.forEach(renderTalk);
    })
    .catch(() => {
      container.innerHTML = '';
      // No invented fallback. This used to hold two talks that were never
      // given, shown whenever the fetch failed, which is precisely when
      // nobody would notice they were wrong.
      container.innerHTML = '<p class="empty-state-title">Talks could not be loaded. <a href="/speaking/" style="color:var(--cyan)">See the full list</a>.</p>';
    });
}

function handleTopicChange() {
  const select = document.getElementById('eq-topic');
  const otherField = document.getElementById('eq-topic-other-field');
  if (!select || !otherField) return;
  otherField.style.display = select.value === 'other' ? 'block' : 'none';
}

function submitEnquiry() {
  const name = document.getElementById('eq-name').value.trim();
  const email = document.getElementById('eq-email').value.trim();
  if (!name || !email.includes('@')) { return; }
  const event = document.getElementById('eq-event').value;
  const date = document.getElementById('eq-date').value;
  const topicSelect = document.getElementById('eq-topic');
  let topic = topicSelect?.selectedOptions?.[0]?.textContent || '';
  if (topicSelect?.value === 'other') {
    topic = document.getElementById('eq-topic-other').value.trim();
  }
  if (!topic) { return; }
  const msg = document.getElementById('eq-msg').value;
  const body = encodeURIComponent('Name: ' + name + '\nEmail: ' + email + '\nEvent: ' + event + '\nDate: ' + date + '\nTopic: ' + topic + '\n\n' + msg);
  window.location.href = 'mailto:jeff@jeffops.com?subject=Speaking Enquiry from ' + encodeURIComponent(name) + '&body=' + body;
  document.getElementById('eq-success').style.display = 'block';
}

// ── TYPEWRITER ────────────────────────────────────────

// ── ORBITAL HOME ─────────────────────────────────────────────────────────────
// Runs on load and again on resize. It used to run once, which was fine while
// the orbit was a fixed 1120px square. Now that its size follows the viewport,
// a window resize changes the container underneath these positions, and without
// recomputing them the pills stay where they were and drift off the ring.
function initOrbital() {
  // Compute sizes dynamically so the orbital system can scale via CSS.
  var sys = document.getElementById('orbital-system');
  if (!sys) return;
  var rect = sys.getBoundingClientRect();
  var oW = rect.width, oH = rect.height, ocx = oW/2, ocy = oH/2;
  var base = 560; // design base size
  // The ring and pills only filled about three quarters of the square, leaving
  // dead margin all round. ORBIT_GAIN enlarges the whole assembly inside that
  // space, so the graphic grows without the container growing and without
  // pushing the tagline down the page. The dashed circle in index.html carries
  // the same factor: 170 * 1.2 = 204 in its 560-unit viewBox.
  var ORBIT_GAIN = 1.2;
  var scale = (oW / base) * ORBIT_GAIN;

  // ensure center measurements
  var center = document.querySelector('.center-node');
  var centerRect = center ? center.getBoundingClientRect() : { width:130, height:130 };
  var centerRadius = (centerRect.width || 130) / 2;

  // position orbit nodes based on scaled radii
  document.querySelectorAll('.orbit-node').forEach(function(node) {
    var ang = parseFloat(node.dataset.angle) * Math.PI / 180;
    var r   = (parseFloat(node.dataset.r) || 170) * scale;
    var pg  = node.dataset.page;
    node.style.position  = 'absolute';
    node.style.left      = (ocx + r * Math.cos(ang)) + 'px';
    node.style.top       = (ocy + r * Math.sin(ang)) + 'px';
    node.style.transform = 'translate(-50%,-50%)';
    // Bound once. Without the guard, every resize would stack another click
    // handler on the same node, and a page change would fire repeatedly.
    if (pg && !node.dataset.bound) {
      node.dataset.bound = '1';
      node.addEventListener('click', function(){ showPage(pg); });
    }
  });

  // connectors: draw from just outside the center circle to just before the orbit pill
  var cd = document.getElementById('connectors');
  if (cd) {
    cd.innerHTML = '';
    document.querySelectorAll('.orbit-node').forEach(function(node) {
      var ang = parseFloat(node.dataset.angle) * Math.PI / 180;
      var r   = (parseFloat(node.dataset.r) || 170) * scale;

      // start point just outside center circle
      var s = centerRadius + 2; // small gap

      // compute pill width to stop connector before pill
      var pill = node.querySelector('.orbit-pill');
      var pillRect = pill ? pill.getBoundingClientRect() : { width: 96 };
      var pillHalf = (pillRect.width || 96) / 2;

      // end at the dotted orbit circle (scaled) so lines reach the dotted ring
      var circleR = 170 * scale;
      var e = circleR - 1; // stop just inside the dotted stroke

      var x1 = ocx + s*Math.cos(ang), y1 = ocy + s*Math.sin(ang);
      var x2 = ocx + e*Math.cos(ang), y2 = ocy + e*Math.sin(ang);
      var len = Math.sqrt((x2-x1)*(x2-x1)+(y2-y1)*(y2-y1));
      var a   = Math.atan2(y2-y1,x2-x1)*180/Math.PI;
      var ln  = document.createElement('div');
      // ensure connectors sit behind the orbit pills
      ln.style.cssText = 'position:absolute;left:'+x1+'px;top:'+y1+'px;width:'+len+'px;height:2px;background:linear-gradient(to right,rgba(0,217,255,0.35),rgba(0,217,255,0.06));transform:rotate('+a+'deg);transform-origin:0 0;pointer-events:none;z-index:1;';
      cd.appendChild(ln);
    });
  }
}

initOrbital();

// Debounced: a drag-resize fires continuously, and this rebuilds every
// connector each time.
var orbitResizeTimer;
window.addEventListener('resize', function () {
  clearTimeout(orbitResizeTimer);
  orbitResizeTimer = setTimeout(initOrbital, 120);
});

const phrases = ['Platform Engineer.','DevOps Practitioner.','Blogger & Educator.','Conference Speaker.','Cloud-Native Advocate.'];
let pi = 0, ci = 0, deleting = false;
function type() {
  const el = document.getElementById('typed-text');
  if (!el) return;
  const phrase = phrases[pi];
  if (!deleting) {
    el.textContent = phrase.slice(0, ++ci);
    if (ci === phrase.length) { deleting = true; setTimeout(type, 1800); return; }
  } else {
    el.textContent = phrase.slice(0, --ci);
    if (ci === 0) { deleting = false; pi = (pi + 1) % phrases.length; }
  }
  setTimeout(type, deleting ? 45 : 80);
}

// ── INIT ──────────────────────────────────────────────

// ── CONSULTING ENQUIRY ────────────────────────────────────────────────────────
function submitConsulting() {
  var name = document.getElementById('con-name').value.trim();
  var email = document.getElementById('con-email').value.trim();
  if (!name || !email.includes('@')) return;
  var role = document.getElementById('con-role').value;
  var svc  = document.getElementById('con-service').value;
  var msg  = document.getElementById('con-msg').value;
  var body = encodeURIComponent('Name: '+name+'\nEmail: '+email+'\nRole: '+role+'\nService: '+svc+'\n\n'+msg);
  window.location.href = 'mailto:jeff@jeffops.com?subject=Consulting Enquiry from '+encodeURIComponent(name)+'&body='+body;
  var s = document.getElementById('con-success');
  if (s) s.style.display = 'block';
}
// ── SPEAKING ENQUIRY ──────────────────────────────────────────────────────────


// ── BLOG FOLDER LOADER ───────────────────────────────────────────────────────
// Scans blog/YYYY/YYYYMMDD - Post Name/ folders and loads the primary .md file.
// Call loadBlogIndex() to populate the post list from the filesystem.
// Call showPostFromFolder('blog/2025/20250115 - My Post') to render a post.

async function loadBlogIndex() {
  if (window._blogIndexData) {
    const idx = window._blogIndexData;
    window._blogEntries = idx;
    window._blogEntriesByFolder = Object.fromEntries(idx.map(item => [item.folder, item]));
    return idx;
  }

  // Fetch blog/index.json if it exists (generated at build time)
  // Falls back to the in-memory posts{} object
  try {
    const r = await fetch('blog/index.json');
    if (r.ok) {
      const idx = await r.json();
      window._blogEntries = idx;
      window._blogEntriesByFolder = Object.fromEntries(idx.map(item => [item.folder, item]));
      return idx; // [{ folder, title, date, readtime, tags, series, series_label, related, excerpt }]
    }
  } catch(e) { /* fallback */ }
  const idx = Object.entries(posts).map(([id, post]) => ({
    id,
    folder: post.folder,
    title: post.title,
    date: post.date,
    readtime: post.readtime,
    tags: post.tags || [],
    excerpt: post.excerpt || '',
    related: post.related || []
  }));
  window._blogEntries = idx;
  window._blogEntriesByFolder = Object.fromEntries(idx.map(item => [item.folder, item]));
  return idx;
}

async function loadTopicFilters() {
  const container = document.getElementById('topic-filter-buttons');
  if (!container) return;

  let topics = [];
  if (window._blogIndexData) {
    const counts = {};
    window._blogIndexData.forEach(post => {
      (post.tags || []).forEach(tag => { counts[tag] = (counts[tag] || 0) + 1; });
    });
    topics = Object.keys(counts).map(tag => ({ key: tag, label: tag.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase()), count: counts[tag] }));
    topics.sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
  } else {
    try {
      const res = await fetch('blog/topics.json');
      if (res.ok) {
        topics = await res.json();
      }
    } catch (e) {
      console.warn('Unable to load topic filters from blog/topics.json', e);
    }

    if (!Array.isArray(topics) || !topics.length) {
      const postsIndex = await loadBlogIndex();
      const counts = {};
      postsIndex.forEach(post => {
        (post.tags || []).forEach(tag => { counts[tag] = (counts[tag] || 0) + 1; });
      });
      topics = Object.keys(counts).map(tag => ({ key: tag, label: tag.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase()), count: counts[tag] }));
      topics.sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
    }
  }

  const allCount = topics.reduce((sum, topic) => sum + topic.count, 0);
  container.innerHTML = '';

  const allButton = document.createElement('button');
  allButton.className = 'tag-btn topic-btn active';
  allButton.innerHTML = `All Posts <span class="tag-count">${allCount}</span>`;
  allButton.onclick = () => setTag('all', allButton);
  container.appendChild(allButton);

  topics.forEach(topic => {
    const btn = document.createElement('button');
    btn.className = 'tag-btn topic-btn';
    btn.innerHTML = `${topic.label} <span class="tag-count">${topic.count}</span>`;
    btn.onclick = () => setTag(topic.key, btn);
    container.appendChild(btn);
  });
}

async function loadSeriesFilters() {
  const container = document.getElementById('series-filter-buttons');
  if (!container) return;

  let seriesList = [];
  if (window._blogIndexData) {
    const counts = {};
    const labels = {};
    window._blogIndexData.forEach(post => {
      if (post.series) {
        counts[post.series] = (counts[post.series] || 0) + 1;
        labels[post.series] = post.series_label || labels[post.series] || post.series;
      }
    });
    seriesList = Object.keys(counts).map(key => ({ key, label: labels[key].replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase()), count: counts[key] }));
    seriesList.sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
  } else {
    try {
      const r = await fetch('blog/series.json');
      if (r.ok) {
        seriesList = await r.json();
      }
    } catch (e) {
      console.warn('Unable to load series filters from blog/series.json', e);
    }

    if (!Array.isArray(seriesList) || !seriesList.length) {
      const postsIndex = await loadBlogIndex();
      const counts = {};
      const labels = {};
      postsIndex.forEach(post => {
        if (post.series) {
          counts[post.series] = (counts[post.series] || 0) + 1;
          labels[post.series] = post.series_label || labels[post.series] || post.series;
        }
      });
      seriesList = Object.keys(counts).map(key => ({ key, label: labels[key].replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase()), count: counts[key] }));
      seriesList.sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
    }
  }

  const allCount = seriesList.reduce((sum, series) => sum + series.count, 0);
  container.innerHTML = '';

  const allButton = document.createElement('button');
  allButton.className = 'tag-btn series-btn active';
  allButton.innerHTML = `All Series <span class="tag-count">${allCount}</span>`;
  allButton.onclick = () => setSeries('all', allButton);
  container.appendChild(allButton);

  seriesList.forEach(series => {
    const btn = document.createElement('button');
    btn.className = 'tag-btn series-btn';
    btn.innerHTML = `${series.label} <span class="tag-count">${series.count}</span>`;
    btn.onclick = () => setSeries(series.key, btn);
    container.appendChild(btn);
  });
}

async function showPostFromFolder(folderPath, updateHash = true) {
  if (!folderPath) return;

  // Ensure in-memory index structures exist when an embedded blog index was provided
  if (window._blogIndexData && !window._blogEntriesByFolder) {
    window._blogEntries = window._blogIndexData;
    window._blogEntriesByFolder = Object.fromEntries(window._blogIndexData.map(item => [item.folder, item]));
  }

  if (window._blogEntriesByFolder?.[folderPath]) {
    const entry = window._blogEntriesByFolder[folderPath];
    if (entry.markdown) {
      showPost(null, entry, updateHash);
      return;
    }
    // If embedded index exists but markdown missing, don't attempt file:// fetch
    if (window._blogIndexData) {
      console.warn('Embedded index present but no markdown for', folderPath);
      return;
    }
  }

  // If the payload is a known post ID, use the ID route
  if (posts[folderPath]) {
    showPost(folderPath, undefined, updateHash);
    return;
  }

  const candidates = ['post.md', 'index.md', 'README.md'];
  for (const name of candidates) {
    try {
      const path = encodeURI(folderPath.replace(/\/+$/, '') + '/' + name);
      const r = await fetch(path);
      if (!r.ok) continue;
      const text = await r.text();
      const titleMatch = text.match(/^#\s+(.+)$/m);
      const title = titleMatch ? titleMatch[1]
        : folderPath.split('/').pop().replace(/^\d{8}\s*-\s*/, '');
      const words = text.trim().split(/\s+/).length;
      const readtime = Math.max(1, Math.round(words / 200)) + ' min read';
      const dm = folderPath.match(/(\d{4})(\d{2})(\d{2})/);
      let date = '';
      if (dm) {
        const mo = ['Jan','Feb','Mar','Apr','May','Jun',
                    'Jul','Aug','Sep','Oct','Nov','Dec'];
        date = mo[parseInt(dm[2])-1] + ' ' + parseInt(dm[3]) + ', ' + dm[1];
      }
      showPost(null, { title, date, readtime, markdown: text, tags:[], related:[], folder: folderPath }, updateHash);
      return;
    } catch(e) { console.warn('Error loading post', folderPath, e); }
  }

  console.warn('No markdown found for blog post:', folderPath);
}

// Blog folder structure helper — generates the folder name from a post title and date
// e.g. blogFolder('2025-01-15', 'My Post Title') => 'blog/2025/20250115 - My Post Title'
function blogFolder(isoDate, title) {
  const d = isoDate.replace(/-/g, '');
  const yr = isoDate.slice(0, 4);
  return 'blog/' + yr + '/' + d + ' - ' + title;
}

// Guarded because this sits at the top level: when mermaid failed to load, the
// ReferenceError thrown here stopped execution and silently disabled every
// feature defined below it.
if (window.mermaid) mermaid.initialize({
  startOnLoad: false, theme: 'dark',
  themeVariables: {
    primaryColor:'#0f1217', primaryTextColor:'#e8edf2', primaryBorderColor:'#00D9FF',
    lineColor:'#00D9FF', secondaryColor:'#151920', tertiaryColor:'#1c2028',
    background:'#0a0c0f', mainBkg:'#0f1217', nodeBorder:'#00D9FF',
    clusterBkg:'#151920', titleColor:'#e8edf2', edgeLabelBackground:'#0f1217',
    fontFamily:'JetBrains Mono, monospace',
  }
});
document.addEventListener('DOMContentLoaded', () => {
  type();
  navigateFromHash();
  window.addEventListener('hashchange', navigateFromHash);
});

// Home page portrait: one of two, chosen per visit.
// The default src stays in the HTML so the picture is there with scripting off
// and for anything that does not run JavaScript. This only swaps it, and only
// once the replacement has actually loaded, so a slow connection does not show
// the first image and then jump to the second.
function pickPortrait() {
  const targets = document.querySelectorAll('img[data-portraits]');
  if (!targets.length) return;

  const options = targets[0].dataset.portraits.split(',').map(pair => {
    const [src, alt] = pair.split('|');
    return { src: src.trim(), alt: (alt || '').trim() };
  }).filter(o => o.src);
  if (options.length < 2) return;

  // Chosen once and applied to every target. The hero and the About avatar are
  // both in this document, so choosing per element would put two different
  // photos of the same person on one page.
  const choice = options[Math.floor(Math.random() * options.length)];

  const apply = () => targets.forEach(img => {
    img.src = choice.src;
    if (choice.alt) img.alt = choice.alt;
  });

  if (choice.src === targets[0].getAttribute('src')) { apply(); return; }
  const preload = new Image();
  preload.onload = apply;
  preload.src = choice.src;
}

pickPortrait();
