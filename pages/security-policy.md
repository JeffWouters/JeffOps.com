---
slug: security-policy
title: Security policy
description: How to report a security problem with jeffops.com, what is in scope, what is not, and what you can expect back.
---

# Security policy

If you have found a security problem with this website, I want to hear about it.

Mail **jeff+jeffopscom@jeffops.com**. The plus sign is part of the address rather than a typo, and it routes reports away from everything else in my inbox.

Include enough to reproduce it: the URL, what you did, what happened, and what you expected instead. A short proof of concept beats a scanner report every time.

There is a machine-readable version of this at [/.well-known/security.txt](/.well-known/security.txt), following [RFC 9116](https://www.rfc-editor.org/rfc/rfc9116).

## What to expect

I run this site on my own. There is no security team here and there is no bug bounty. What I can commit to:

- An acknowledgement within five working days.
- An honest answer about whether I think it is real and what I intend to do about it.
- Credit under Acknowledgments below if you want it, and no mention at all if you would rather stay anonymous.

If you have not heard back in five working days, assume the mail went astray and send it again.

## Scope

In scope: **jeffops.com** and the content served from it.

Worth knowing before you spend an evening on it, because it will save you time. This is a static site. There is no application server, no database, no login, and no user data to steal. The pages are HTML, CSS, a little JavaScript, and markdown rendered to files at build time. So the realistic attack surface is narrower than the front page makes it look, and it is mostly these:

- DNS and domain configuration, including anything that would allow a subdomain takeover.
- The third-party scripts the pages pull from a CDN, and the integrity of what gets served from there.
- The build pipeline and the dependencies it installs.
- Content problems, such as a link or a redirect that points somewhere it should not.

## Out of scope

- **Anything belonging to my employer or to a client.** This policy covers jeffops.com and nothing else. If you have found something in a system I work on professionally, that organisation runs its own disclosure process and this is not it. Please do not send it here.
- Third-party platforms I publish on but do not operate, including LinkedIn and GitHub.
- Denial of service, load testing, brute forcing, or anything else that degrades the site for other people.
- Missing security headers, TLS configuration preferences, SPF, DKIM and DMARC observations, and similar output from an automated scan, unless you can show concrete impact. I am happy to read them and I may well act on them, but on their own they are findings rather than vulnerabilities.
- Social engineering of me or of anyone else.

## Good-faith research

If you follow this policy, act in good faith, avoid privacy violations and disruption to others, access no more data than you need to demonstrate the problem, and give me a reasonable opportunity to fix it before you publish, then I will not pursue a complaint against you for the research itself.

Two honest caveats. I cannot waive anyone else's rights, so this covers me and not third parties whose systems you might touch on the way. And I am not a lawyer, so read this as a statement of how I intend to behave rather than as a legal instrument.

## Acknowledgments {#acknowledgments}

Nobody yet.

If you report something real, your name goes here, along with a one-line description of what you found, unless you ask me not to.
