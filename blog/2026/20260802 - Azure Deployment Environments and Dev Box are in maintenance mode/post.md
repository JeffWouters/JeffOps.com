---
tags: [platform-engineering, azure, idp, enterprise, ops]
slug: azure-platform-engineering-maintenance-mode
date: 2026-08-02
description: The two Azure services most commonly recommended as the foundation of an internal developer platform are both in maintenance mode with no further features planned. Here is what Microsoft actually said, and what is left standing.
---

# Azure Deployment Environments and Dev Box are in maintenance mode

If you are part-way through a design that assumes either of these, this is worth knowing this week rather than next year.

**Azure Deployment Environments and Microsoft Dev Box are both in maintenance mode.** Most of the "build an internal developer platform on Azure" writing currently in circulation nominates one or both as the foundation. That advice has not caught up.

Microsoft's [wording for Azure Deployment Environments](https://learn.microsoft.com/azure/deployment-environments/maintenance-mode) is short enough to quote in full: "Azure Deployment Environments is in maintenance mode, with no additional features planned. Existing capabilities remain available."

[For Dev Box](https://learn.microsoft.com/azure/dev-box/dev-box-windows-365-announcement) it is more pointed: "Dev Box is now in maintenance mode, with no additional features planned", and "Customers should consider Windows 365 as the recommended path forward."

Several announced Dev Box features were cancelled before they shipped, including on-behalf-of creation, firewall service tags, developer offboarding, single sign-on for existing machines, auto-remediation and the latency improvements. There is no migration guide yet. The documentation says guidance will be provided.

Maintenance mode is not end of life, and nothing you are running today stops working. But it changes the calculation. A service with no further features is a service you should not be building a five-year platform strategy on top of, and it is a service whose gaps will stay gaps.

## What has not gone into maintenance

The awkward part is that the two services now parked are the ones that felt most like a platform, in the sense of a thing a developer touches. What is left is less exciting and considerably more durable, because it is the substrate rather than the surface.

**[Landing zones and subscription vending](https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/subscription-vending).** This is the genuinely platform-shaped primitive in Azure: a request produces a subscription placed in the right management group, with networking, RBAC and identity already wired. It is the paved road, expressed as infrastructure rather than as a portal.

Read Microsoft's own framing carefully, because it cuts against the way golden paths are usually described. It is not "pick one blessed route and make everyone take it". Microsoft says that organisations "that only provide a 'one size fits all' approach to subscription vending often limit their internal customers' flexibility" and that "platform teams need to provide various product lines to cater to their organization's needs", noting that customers typically start with three: sandbox, corp connected, and online.

A small catalogue of paved roads, not one. That is a more useful model than the singular golden path, and it is the difference between a platform people route around and one they use.

**[Azure Verified Modules](https://azure.github.io/Azure-Verified-Modules/)** as the module layer. Read the support statement before you depend on it. The commitment is a meaningful response toward resolution within five business days, and Microsoft is explicit that this is "not for a fix within these durations". Modules also carry lifecycle states, including "orphaned" for when maintainers stop responding. That is fine, and it is a great deal better than writing your own modules from scratch. It is not the same as a supported product, and the difference matters when you are telling your organisation that this is the supported way to build.

**Azure Policy** as the governance layer. Microsoft's framing here is the useful bit: [start right and stay right](https://learn.microsoft.com/platform-engineering/application-platform), meaning catalogued templates get you compliant at creation and policy keeps you compliant afterwards. Note the warning that comes attached, because it is the thing that will bite you: while policies "can enforce compliance, they can also break applications unexpectedly". Roll them out in rings, the same way you would roll out anything else that can take production down.

## On portals, Microsoft's advice runs against the instinct

Worth quoting because it is the opposite of where most platform projects start. A developer portal, Microsoft says, is ["a destination rather than a starting point"](https://learn.microsoft.com/platform-engineering/developer-self-service). Before building somewhere new for people to go, extend the surfaces they already use: the IDE, the CLI, the DevOps tooling, chat.

That ordering is well supported by evidence from outside Microsoft. Spotify, who built the most popular developer portal there is, [put average Backstage adoption inside adopting organisations at around 10%](https://www.techtarget.com/searchitoperations/news/366558592/Behind-the-scenes-Spotify-Backstage-a-work-in-progress). Building a second front door and then asking people to learn it is a hard way to earn attention you could have had for free.

## One caveat if you standardise on azd templates

Azure Developer CLI templates are a genuinely good accelerator, and Microsoft states plainly that the templates, "including those provided from Microsoft, are not supported by any Microsoft support program or service". They are provided as is.

That is fine for a starting point and a problem for a paved road. The moment you tell your organisation "this is the supported way to deploy", you have quietly assumed the support obligation yourself. Decide that deliberately rather than discovering it during an incident.

## What I would take from this

The services that went into maintenance are the ones that looked like a product. The ones still standing are the ones that look like plumbing. That is not a coincidence, and there is a lesson in it about which layer is worth building your platform on.

More generally, it is a small live demonstration of a bigger point: [an internal platform is a bet on a gap, and the gap moves](/posts/2026/internal-developer-platform-expiry-date/). Sometimes it moves because the hyperscalers close it. Sometimes, as here, it moves because the hyperscaler you built on quietly stops developing the thing you built on. Either way, the assumption is worth re-pricing on a schedule rather than at the point where someone sends you a documentation link.
