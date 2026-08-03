window._speakingTopics = [
  { value: 'platform-engineering', label: 'Platform Engineering & IDPs' },
  { value: 'kubernetes', label: 'Kubernetes & Cloud Native' },
  { value: 'devops', label: 'DevOps Culture & DORA' },
  { value: 'observability', label: 'Observability & Reliability' },
  { value: 'developer-experience', label: 'Developer Experience' },
  { value: 'other', label: 'Other' }
];

// The talk list lived here as well as in speaking_talks.json. The two
// disagreed: this file held the real twelve talks and fed the single-page
// app, while the JSON held five that were never given and fed the
// statically rendered /speaking/ page that crawlers and link previews see.
// speaking_talks.json is now the only source. app.js fetches it.
