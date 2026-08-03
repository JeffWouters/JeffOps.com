---
tags: [kubernetes, aks, cost, finops, reliability, ops]
slug: cutting-kubernetes-costs-without-cutting-reliability
date: 2026-05-04
description: Most Kubernetes overspend is the gap between what you requested and what you used. Closing it safely is a reliability exercise, and the saving only reaches the invoice if it removes nodes.
---

# Cutting Kubernetes costs without cutting reliability

Someone in finance has looked at the cluster bill and asked the obvious question, and the obvious answers are all bad. Fewer replicas. Smaller nodes. Turn off the redundancy nobody has needed yet. Each of those saves money by spending reliability, and you pay it back with interest during the next incident.

Here is the line worth starting from: **most Kubernetes overspend is not a pricing problem. It is the gap between what you asked for and what you used.**

That changes who owns the fix. A pricing problem belongs to procurement. A requests problem belongs to whoever wrote the manifest.

**But be clear about the mechanism, because this is where cost articles cheat.** You are not billed for requests. You are billed for nodes. Reducing a workload's requests from 4 GiB to 1 GiB saves you nothing at all until that freed capacity lets the autoscaler remove a node. A cluster that drops from 60% requested to 40% requested on an unchanged node count has improved a dashboard and not an invoice.

So the work is two-part and the second half is the one people skip: close the gap, then make sure the freed space actually consolidates. Most of this article is about the second half.

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 520" width="760" height="520" role="img" aria-labelledby="ch-t ch-d" style="max-width:100%;height:auto;display:block;margin:1.5rem 0"><title id="ch-t">How a smaller resource request becomes a smaller bill</title><desc id="ch-d">A five step chain from reduced requests to a lower invoice, with four labelled points at which the chain commonly breaks.</desc><defs><marker id="ch-a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#0aa5c4"/></marker><marker id="ch-aw" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#d2593c"/></marker></defs><rect x="24" y="30" width="330" height="62" rx="4" fill="none" stroke="#0aa5c4" stroke-opacity="1" stroke-width="1.5"/><text x="40" y="56" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="15" fill="currentColor" fill-opacity="1" text-anchor="start" font-weight="600">1. Requests reduced</text><text x="40" y="76" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12" fill="currentColor" fill-opacity="0.62" text-anchor="start" font-weight="400">VPA, in-place resize</text><line x1="189.0" y1="96" x2="189.0" y2="120" stroke="#0aa5c4" stroke-width="1.5" marker-end="url(#ch-a)"/><rect x="24" y="124" width="330" height="62" rx="4" fill="none" stroke="currentColor" stroke-opacity="0.28" stroke-width="1.5"/><text x="40" y="150" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="15" fill="currentColor" fill-opacity="1" text-anchor="start" font-weight="600">2. Capacity freed</text><text x="40" y="170" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12" fill="currentColor" fill-opacity="0.62" text-anchor="start" font-weight="400">on the nodes you already run</text><line x1="189.0" y1="190" x2="189.0" y2="214" stroke="#0aa5c4" stroke-width="1.5" marker-end="url(#ch-a)"/><rect x="24" y="218" width="330" height="62" rx="4" fill="none" stroke="currentColor" stroke-opacity="0.28" stroke-width="1.5"/><text x="40" y="244" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="15" fill="currentColor" fill-opacity="1" text-anchor="start" font-weight="600">3. Pods consolidate</text><text x="40" y="264" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12" fill="currentColor" fill-opacity="0.62" text-anchor="start" font-weight="400">packing, Karpenter consolidation</text><line x1="189.0" y1="284" x2="189.0" y2="308" stroke="#0aa5c4" stroke-width="1.5" marker-end="url(#ch-a)"/><rect x="24" y="312" width="330" height="62" rx="4" fill="none" stroke="currentColor" stroke-opacity="0.28" stroke-width="1.5"/><text x="40" y="338" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="15" fill="currentColor" fill-opacity="1" text-anchor="start" font-weight="600">4. Node removed</text><text x="40" y="358" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12" fill="currentColor" fill-opacity="0.62" text-anchor="start" font-weight="400">autoscaler drains and deletes</text><line x1="189.0" y1="378" x2="189.0" y2="402" stroke="#0aa5c4" stroke-width="1.5" marker-end="url(#ch-a)"/><rect x="24" y="406" width="330" height="62" rx="4" fill="none" stroke="#0aa5c4" stroke-opacity="1" stroke-width="1.5"/><text x="40" y="432" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="15" fill="currentColor" fill-opacity="1" text-anchor="start" font-weight="600">5. Invoice falls</text><text x="40" y="452" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12" fill="currentColor" fill-opacity="0.62" text-anchor="start" font-weight="400">the only step finance sees</text><line x1="432" y1="202.0" x2="368" y2="202.0" stroke="#d2593c" stroke-width="1.5" marker-end="url(#ch-aw)" stroke-dasharray="4 3"/><text x="440" y="189.0" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="11" fill="#d2593c" fill-opacity="1" text-anchor="start" font-weight="600">breaks here</text><text x="440" y="206.0" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="11.5" fill="currentColor" fill-opacity="1" text-anchor="start" font-weight="400">LeastAllocated spreads pods,</text><text x="440" y="220.0" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="11.5" fill="currentColor" fill-opacity="1" text-anchor="start" font-weight="400">so no node ever empties</text><line x1="432" y1="296.0" x2="368" y2="296.0" stroke="#d2593c" stroke-width="1.5" marker-end="url(#ch-aw)" stroke-dasharray="4 3"/><text x="440" y="262.0" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="11" fill="#d2593c" fill-opacity="1" text-anchor="start" font-weight="600">breaks here</text><text x="440" y="279.0" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="11.5" fill="currentColor" fill-opacity="1" text-anchor="start" font-weight="400">· Injected anti-affinity makes</text><text x="440" y="293.0" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="11.5" fill="currentColor" fill-opacity="1" text-anchor="start" font-weight="400">  consolidation skip the node</text><text x="440" y="307.0" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="11.5" fill="currentColor" fill-opacity="1" text-anchor="start" font-weight="400">· consolidateAfter resets on churn</text><text x="440" y="321.0" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="11.5" fill="currentColor" fill-opacity="1" text-anchor="start" font-weight="400">· A PodDisruptionBudget blocks</text><text x="440" y="335.0" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="11.5" fill="currentColor" fill-opacity="1" text-anchor="start" font-weight="400">  the last eviction</text><text x="24" y="508" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="12" fill="currentColor" fill-opacity="0.7" text-anchor="start" font-weight="400">Steps 2 to 4 are where cost work quietly fails. A dashboard improves; the bill does not.</text></svg>

A note on what this is, because it should change how you weigh it. I have not run a cluster cost programme end to end, so nothing here is a war story. It is what the documentation and the published measurements say when you go and read them, together with the failure modes that keep turning up in other people's write-ups. Every number below is linked to whoever produced it, and where the evidence is thin I have said so rather than rounded it into confidence.

## Where the money actually goes

Split the bill before changing anything. Kubernetes spend lands in five buckets that behave differently:

- **Compute.** Nodes. Usually the largest line and usually the one holding the waste.
- **Accelerators.** If you run GPUs this can dominate everything else, and it follows different rules. It has [its own article](/posts/2026/gpu-costs-kubernetes-sharing/).
- **Storage.** Persistent volumes, OS disks, snapshots, and the disks left behind when a workload moved.
- **Network.** Egress, cross-zone traffic, load balancers that outlived their service.
- **Observability.** Your monitoring bill is part of your cluster bill, and it is the one nobody attributes.

Within compute, the waste is rarely the node price. The scheduler reserves what you requested whether you use it or not, and the request was a guess made once by whoever wrote the deployment. A node at 20% actual utilisation showing 90% requested capacity is not an efficient node, and no amount of SKU shopping fixes it.

Azure's idle-cost documentation puts it plainly: a node that is ready with no pods running, waiting for the autoscaler, is [mostly idle cost](https://learn.microsoft.com/azure/aks/cost-analysis-idle-costs).

### Measuring the gap

Before any of this, get the number. If you run Prometheus, this is the whole diagnosis in one query:

```promql
# Memory used as a fraction of memory requested, per pod, averaged over a week.
# max() on both sides matters: cAdvisor can export stale duplicate series for a
# restarted container, and kube-state-metrics emits one series per container.
avg_over_time(
  (
    sum by (namespace, pod) (
      max by (namespace, pod, container) (
        container_memory_working_set_bytes{container!="", container!="POD"}
      )
    )
    /
    sum by (namespace, pod) (
      max by (namespace, pod, container) (
        kube_pod_container_resource_requests{resource="memory"}
      )
      * on (namespace, pod) group_left
        (kube_pod_status_phase{phase=~"Pending|Running"} == 1)
    )
  )[7d:1h]
)
```

Swap in `rate(container_cpu_usage_seconds_total[5m])` and `resource="cpu"` for the CPU version. Anything sitting below 0.3 is your list.

Two things this does not do, and both matter. It gives you a ratio, so run `sum by (namespace, pod) (kube_pod_container_resource_requests{resource="memory"})` alongside it and sort by that, because a 10% ratio on a 128 MiB pod is noise and a 60% ratio on a 32 GiB one is real money. And pods with no memory request at all produce no denominator and vanish silently, which is exactly the population the governance section below is about. Find those separately with `kube_pod_container_info unless on (namespace, pod, container) kube_pod_container_resource_requests{resource="memory"}`.

## The requests gap is a reliability problem in a finance costume

Here is why "just lower the requests" is not the whole answer.

CPU and memory fail differently, and the asymmetry is the game.

**CPU is elastic.** Exceed your CPU limit and the kernel throttles you. The pod gets slower, latency rises, a queue builds. Unpleasant and survivable, and visible on a graph if you are watching.

**Memory is not.** Exceed your memory limit and the container is OOMKilled mid-request. There are leading indicators if you look for them, working set climbing and garbage collection getting busier, but the failure itself has no gradual mode. It is a cliff.

So the two deserve opposite instincts. Under-requesting CPU costs latency. Under-requesting memory costs availability. Treat them as one slider and you will eventually trade an outage for a saving.

A practical position: aggressive on CPU requests, conservative on memory, and memory limits equal to memory requests **for workloads whose memory profile you have actually measured**. That last clause matters. Setting limits equal to requests on an unmeasured JVM heap or a Go service with a growing cache guarantees an OOMKill at precisely the point a looser limit would have survived. Measure first, then pin.

CPU limits are genuinely contested. Leaving them off avoids throttling a burst that had capacity available; setting them makes behaviour reproducible and stops one workload starving its neighbours. Decide per workload class.

One interaction that is easy to miss: [node swap is stable as of Kubernetes 1.34](https://kubernetes.io/docs/concepts/cluster-administration/swap-memory-management/), and under `LimitedSwap` only Burstable pods may swap. Setting memory request equal to limit makes a container Guaranteed, which opts it out of swap entirely. If you are experimenting with swap as an overcommit lever, that advice and the paragraph above are in tension.

## Right-sizing no longer means restarting everything

Historically, changing a pod's CPU or memory meant recreating it. That made right-sizing a scheduled, disruptive event, so it happened rarely, so requests drifted between rounds.

**In-place pod resize is [stable as of Kubernetes 1.35](https://kubernetes.io/docs/tasks/configure-pod-container/resize-container-resources/)** and on by default. You can change a running container's allocation while potentially avoiding disruption. Paired with the Vertical Pod Autoscaler, right-sizing becomes continuous rather than scheduled.

Three cautions. Resizing memory downwards is the awkward direction and depends on the per-resource resize policy you set, so read the semantics; do not assume symmetry. VPA acting automatically on anything holding data deserves the same care as any other automated change to state: recommendation mode first. And **do not point VPA at CPU while an HPA is scaling on CPU**, because the two will fight, VPA raising requests as HPA adds replicas to the same signal. VPA on memory alongside HPA on CPU is the combination that works.

Recommendation mode is worth running even if you never let it act. Azure Advisor [recommends exactly that](https://learn.microsoft.com/azure/advisor/advisor-reference-cost-recommendations) as a first step, and comparing what VPA thinks each workload needs against what it currently requests is the fastest way to size the prize.

For sidecar-heavy clusters, note that pod-level resources reached beta and default-on in Kubernetes 1.34, letting a pod hold one shared envelope rather than each container carrying its own padding. In-place resizing of pod-level resources reached beta in 1.36.

## The overhead you pay per node

Allocatable is not capacity, and the difference is a strong argument for fewer, larger nodes.

Every node reserves CPU and memory before your pods get anything, and [AKS publishes the schedule](https://learn.microsoft.com/azure/aks/node-resource-reservations). The CPU reservation is regressive: a 2-core node gives up 100 millicores, which is 5% of it; a 64-core node gives up 740 millicores, which is 1.2%. Memory reservation is the lesser of 20 MB per max-pod plus 50 MB, or 25% of system memory, putting an 8 GB node at 30 max pods at roughly 90.6% allocatable.

Two things compound it. Every DaemonSet is a per-node tax, so your log shipper, node exporter, CSI and CNI agents multiply by node count rather than by workload. And there is a pod-slot ceiling: [AKS allows between 10 and 250 pods per node](https://learn.microsoft.com/azure/aks/concepts-network-ip-address-planning), defaulting to 250 on Azure CNI Overlay and 30 on Azure CNI with standard networking. A fleet of small pods on a default standard-networking pool hits 30 long before it fills CPU or memory, which is a configuration problem rather than a law of nature, but it is one worth checking.

Consolidating to fewer, larger nodes removes copies of all of that. The trade is real: a larger node is a larger blast radius and coarser autoscaling granularity.

While counting fixed costs, the AKS Standard tier control plane is [$0.10 per cluster per hour](https://learn.microsoft.com/azure/architecture/aws-professional/eks-to-aks/cost-management#aks-cost-basics), roughly $73 a month flat regardless of size. Ten clusters is $730 before a single node, and underneath each sits a system node pool floor of at least two nodes at 4 vCPU minimum.

## Make the nodes fit the pods

Once requests reflect reality, the next waste is nodes that do not fit them. Three pods needing 5 GB each on an 8 GB node means two nodes and a lot of stranded memory.

**Node autoprovisioning**, which in AKS is [built on Karpenter](https://learn.microsoft.com/azure/aks/node-auto-provisioning), looks at pending pods and provisions the VM configuration that fits them, rather than making you define pools and hope.

The money is mostly in **consolidation** rather than in initial provisioning: reclaiming capacity after scale-down, after a deployment shrinks, after churn. That is where steady-state drift accumulates. If you are reading older guidance, the policy names changed: `WhenUnderutilized` is gone, and [current Karpenter](https://karpenter.sh/docs/concepts/disruption/) offers `WhenEmpty`, `Balanced` and `WhenEmptyOrUnderutilized`, the last being the default.

Two things quietly stop consolidation working, and this is the part that connects back to the thesis. Karpenter's documentation warns that **preferred anti-affinity and topology spread constraints reduce consolidation effectiveness**, because it keeps trying to honour your preferences and skips otherwise-valid moves. And `consolidateAfter` resets whenever a pod is added or removed, so a churning node never becomes a candidate.

That matters more than it first appears on AKS Automatic, because Deployment Safeguards runs there in Enforce mode and **injects preferred pod anti-affinity and topology spread constraints into workloads that lack them**. The platform marketed for cost efficiency mandatorily adds the two constraints that impede the mechanism doing most of the saving. Both facts are on Microsoft's own pages. Neither page mentions the other.

Two smaller levers: **Arm64 node pools**, which Microsoft describes as offering [up to 50% better price-performance](https://learn.microsoft.com/azure/aks/best-practices-cost) for scale-out workloads, with mixed architectures supported in one cluster. And **keep application images small**, because every scale-out downloads them and slow starts cause the overprovisioning discussed below. (Model-serving images are a different problem, covered in the GPU article.)

One infrastructure detail with a real recurring cost: AKS [defaults to ephemeral OS disks](https://learn.microsoft.com/azure/aks/concepts-storage#ephemeral-os-disks-in-aks) where the VM SKU supports the requested size, and the VM price includes them, so you avoid the managed OS disk charge. That charge scales with the node: AKS defaults to a 128 GiB P10 at 1 to 7 vCPU, rising to 1024 GiB P30 at 64 vCPU and above, so the saving is larger on exactly the big nodes recommended above. The fallback is silent: ask for 100 GiB on a VM with 75 GiB of temp storage and you get a managed disk without being told. Ephemeral also rules out [disk snapshots, Azure Disk Encryption, Azure Backup and Site Recovery](https://learn.microsoft.com/azure/virtual-machines/ephemeral-os-disks) on the node, so check your compliance posture before assuming it is free money.

## Scale to zero where the workload allows it

The Horizontal Pod Autoscaler handles demand that varies. **KEDA** handles demand that stops, scaling on queue depth, event backlog and schedules, and going to zero. Anything queue-driven or batch should not be sitting idle overnight waiting for work that arrives at nine.

Two HPA defaults worth knowing. Scale-down stabilisation is 300 seconds while scale-up can double every 15 seconds, an asymmetry most people never look at. And **configurable tolerance reached beta and default-on in 1.35**, so you can now set different tolerances per direction: tight on scale-up for fast reaction, loose on scale-down so a 2% dip does not cause churn.

Thrash matters less for the replicas than for what follows them. Replica churn drives node churn, node churn drives image pulls and warm-up CPU, and it keeps resetting the consolidation timers so nodes never become candidates for removal.

**The slow-start trap raises your floor permanently.** The HPA ignores a pod's CPU during the [CPU initialisation period](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/), five minutes by default, and treats not-yet-ready pods as consuming nothing. A workload taking minutes to become Ready is invisible to its own autoscaler for that window. The team concludes the HPA is too slow and raises `minReplicas`. That floor is now permanent cost. Fixing start time, with a startup probe so Ready means ready, is what lets it come back down.

## Bin packing, and the tool that undoes it

Two levers that only work as a pair.

The default scheduler scoring strategy is `LeastAllocated`, which spreads pods across nodes. Every node ends up partially full, which is exactly the state in which the autoscaler cannot remove any of them. Switching `NodeResourcesFit` to a packing strategy concentrates idle capacity onto whole nodes that can be deleted.

This is now possible on AKS: [configurable scheduler profiles](https://learn.microsoft.com/azure/aks/configure-node-binpack-scheduler) arrived in preview for Kubernetes 1.33 and later. Read Microsoft's guidance rather than reaching for the obvious setting, because two details matter. Raw `MostAllocated` "risks saturating nodes beyond desirable limits, causing throttling or additional bottlenecks", and Microsoft recommends `RequestedToCapacityRatio` for production instead, which lets you target a utilisation band and deprioritise nodes above it. And Microsoft says you **must disable the `PodTopologySpread` plugin**, because it can override the `NodeResourcesFit` weighted score.

Which raises a combination this article has now recommended in three places and which you should not deploy blind: aggressive CPU requests, plus deliberate packing, plus a descheduler evicting from under-used nodes. CPU requests set the kernel's CPU weight (`cpu.weight` on cgroup v2), not just placement. Aggressively low requests on a deliberately saturated node means starvation under contention, missed liveness probes, restarts, and rescheduling onto other saturated nodes. Introduce these one at a time.

On the descheduler itself: its `HighNodeUtilization` plugin evicts from under-utilised nodes so they can be emptied, and its [documentation states](https://github.com/kubernetes-sigs/descheduler) the plugin **must** be used with `MostAllocated` scoring. Without it, evicted pods spread straight back out and you have built an eviction loop that costs money. Run it as a CronJob rather than a hot loop, with `nodeFit: true` so it checks a pod can be placed before evicting it, and with eviction caps. It evicts and hopes; it does not schedule replacements.

## Spot, done in a way you will not regret

Azure is explicit: spot node pools have **no SLA**, sit in a single fault domain, and provide [no high-availability guarantees](https://learn.microsoft.com/azure/architecture/aws-professional/eks-to-aks/cost-management), with eviction notice of [at least 30 seconds](https://learn.microsoft.com/azure/architecture/guide/spot/spot-eviction) delivered best-effort.

The rules follow:

- **Never put stateful workloads, single-replica services, or the only capacity behind a user-facing path on spot.**
- **Mix, for workloads that tolerate it.** An on-demand baseline that can carry the service, with spot absorbing peaks. This works for stateless request handlers with fast startup. It does not work for latency-sensitive inference, where a cold replacement replica takes minutes.
- **Set PodDisruptionBudgets and mean them**, so a reclamation cannot take your last healthy replica.
- **Make shutdown fit in thirty seconds.**
- **Spread across zones and instance types**, so one capacity squeeze does not take a whole tier.

Azure publishes real eviction rates per SKU and region, so this does not have to be an argument about vibes. The [GPU article](/posts/2026/gpu-costs-kubernetes-sharing/) covers how to query them, where the stakes make it matter more.

## Commitments, and one thing that is not a discount

Reservations and savings plans produce a discount [up to 72% against pay-as-you-go](https://learn.microsoft.com/azure/aks/best-practices-cost) with no runtime change at all.

There is a real reason to right-size first, and it is not that discounts "multiply your waste", which is arithmetically confused since the two levers commute. It is **shape lock-in**. A one or three year commitment is a bet on a fleet profile. Make it before you have closed the requests gap and you have committed to a shape you are about to change, and the unused portion is not refundable because you got more efficient.

**Capacity reservations are not a discount.** They guarantee capacity is available to you, which is genuine reliability value in a constrained region, but Azure's billing documentation is blunt that a capacity reservation bills at full rate for the reserved quantity [whether or not you use it](https://learn.microsoft.com/azure/virtual-machines/capacity-reservation-overview#pricing-and-billing). They can be covered by a reservation or savings plan, which is the only way they get cheaper.

## The bucket nobody attributes: your monitoring bill

Usually the fastest saving in the exercise, and the one people forget is part of the cluster bill at all.

Azure Advisor recommends switching from log-based Container Insights metrics to [Managed Prometheus, which it describes as up to 80% cheaper](https://learn.microsoft.com/azure/advisor/advisor-reference-cost-recommendations) for the same metric data. If you run both, you are paying twice for substantially the same numbers. That one is close to free money.

The rest of the list is not free money, and I want to be careful here, because this section is where a cost article most easily commits the sin it opened by condemning. Every lever below trades some future ability to answer a question:

- **Collect logs and events only** in Container Insights if you have Managed Prometheus. Low risk, mostly removes duplication.
- **Move container logs to ContainerLogV2 and Basic Logs** if you do not query them routinely. You lose alerting and most query capability on that table. Fine for chatty application stdout, wrong for anything you investigate.
- **Turn off control plane log categories you genuinely do not use.** Not `kube-audit`. Audit logs are what answer "who deleted that secret" during a security investigation, and they frequently carry a retention obligation. Trim the noisy categories, keep the forensic one, and if audit volume is the problem, use ingestion-time transformations to filter it rather than switching it off.
- **Alert on metrics rather than logs** where the signal exists in both.
- **Use ingestion-time transformations** to drop or reshape data before it lands, so you never pay for what you discard.

One trap when combining these. [Commitment tiers](https://learn.microsoft.com/azure/azure-monitor/logs/cost-logs#commitment-tiers) start at 100 GB per day and save as much as 30%, but apply **only to Analytics Logs**. Basic and Auxiliary Logs bill at flat per-GB rates and are excluded. The "move to Basic Logs" lever and the "buy a commitment tier" lever do not compose.

The same discipline appears in [instrumenting AI systems](/posts/2026/ai-observability-four-problems/): telemetry volume is a design decision with a price attached, and the default is rarely right.

## Storage and network

Persistent volumes outlive the workloads that created them, and a `Retain` reclaim policy leaves the disk behind when the claim goes. List unattached disks and orphaned snapshots against live claims periodically, and delete them with an owner attached, not with hope.

On disk choice, classic Premium SSD ties IOPS to capacity, so a workload needing 4,000 IOPS forces a 1 TiB disk even if it stores 50 GiB. Premium SSD v2 decouples them and includes 3,000 IOPS and 125 MB/s at no extra charge, at the cost of being LRS only with no zone-redundant option, which is a reliability trade rather than a free upgrade.

Cross-zone traffic is billable, so a chatty service spread across three zones pays for that redundancy twice. `spec.trafficDistribution` with `PreferSameZone` [went stable in Kubernetes 1.35](https://kubernetes.io/docs/reference/networking/virtual-ips/#traffic-distribution) and is the current mechanism. Be honest about what it does: keeping traffic in-zone reduces egress cost and consumes the cross-zone failover headroom you were paying for.

Do not confuse it with the older `service.kubernetes.io/topology-mode: Auto` annotation, which has been beta since 1.23 and distributes proportionally with safeguards, including falling back to cluster-wide routing when there are too few endpoints. `PreferSameZone` deliberately dropped those heuristics for predictability: if a zone has endpoints they take all of that zone's traffic, and it falls back only when the zone has none. Simpler, and it makes overloading a zone's endpoints your problem rather than the control plane's.

And every load balancer and public IP left behind by a deleted service is a standing charge nobody is watching.

## When the governance control raises the bill

AKS [Deployment Safeguards](https://learn.microsoft.com/azure/aks/deployment-safeguards) in Enforce mode assigns **500 millicores and 2 GiB**, as both request and limit, to any pod arriving with no resources set, and raises anything below 100m or 100Mi to those floors. That is sound governance, and on a cluster of small utility pods that previously ran unspecified, 2 GiB of *requested* memory each is a scheduling floor that the node count follows upwards.

Worth knowing before you rely on it as a control: Microsoft documents Gatekeeper as operating fail-open, so if the admission webhook does not respond the validation is skipped. It is a strong default, not a guarantee.

**LimitRange has a sharper edge.** A container specifying **only a limit** gets its request set equal to that limit, and this happens *whether or not* you have set a `defaultRequest` for the namespace. Your default is simply ignored for that container. A team asks for burst headroom and silently reserves all of it for the pod's lifetime. [Upstream documents this](https://kubernetes.io/docs/tasks/administer-cluster/manage-resources/cpu-default-namespace/), and [notes separately](https://kubernetes.io/docs/concepts/policy/limit-range/) that with two LimitRanges in a namespace, which default applies is not deterministic. Keep one.

Used deliberately the pairing works: a ResourceQuota makes requests mandatory by rejecting pods without them, and a single LimitRange supplies sane defaults.

## Non-production is where the easy money is

Development, test and staging are frequently a large share of the bill and the savings are uncontroversial.

Scale non-production node pools down outside working hours, with the obvious caveats: check nightly CI, scheduled integration suites and colleagues in other timezones before picking the window, and prefer a small floor to a hard zero if anything needs to run unattended. Put an expiry on ephemeral environments so a preview namespace from a merged pull request does not run until the heat death of the universe. Use spot aggressively here, because an interrupted CI runner is an inconvenience rather than an incident.

## "Finance wants a number this quarter"

The fair objection to everything above: you have been told to spend a month measuring, and someone wants a saving on this quarter's report.

Two answers. The monitoring bill and idle non-production capacity are both actionable in days, carry little risk, and are large enough to be worth reporting. Start there, and they buy you the time for the rest.

And be straight about the alternative. The fast levers, cutting replicas and shrinking nodes, are available to anyone in an afternoon. They work. They also spend reliability, and that spend does not appear on the same report as the saving. If the decision is made anyway, make sure it is recorded as a decision with a trade attached, so the incident review has somewhere to point.

## The order I would do it in

1. **Get visibility.** Cost analysis on, VPA in recommendation mode, and the requests-versus-usage query above. [AKS Cost Analysis](https://learn.microsoft.com/azure/aks/cost-analysis) breaks spend down by Kubernetes construct, separating idle, system and unallocated charges; [OpenCost](https://www.opencost.io/docs/configuration/azure) is the vendor-neutral option.
2. **Fix the monitoring bill**, minus the audit logs.
3. **Close the requests gap.** Aggressive on CPU, careful on measured memory, using in-place resize so it is not a disruptive event. Keep PodDisruptionBudgets on everything that matters, because this generates a lot of voluntary disruption.
4. **Make the freed space consolidate**, which is the step that turns a dashboard change into an invoice change. Node autoprovisioning, packing, fewer larger nodes, and a check that nothing is injecting anti-affinity you did not ask for.
5. **Scale to zero** what can be, non-production first.
6. **Introduce spot** behind PDBs with an on-demand baseline.
7. **Commit** to the steady-state remainder, once the shape has stopped moving.
8. **Show teams their own numbers.** Showback works because the person who set `memory: 4Gi` because it seemed safe is usually happy to fix it once they can see the cost. They were being cautious with a number nobody had ever shown them.

Change one thing at a time and watch it. An exercise that changes six variables in a week cannot tell you which one caused the incident. And keep an eye on the error budget while you work: if reliability degrades as costs fall, you have not optimised anything, you have sold something that was not yours to sell.

## What this does not do

None of it will halve your bill in a fortnight, and any guide promising a specific percentage is describing someone else's cluster. What is available depends entirely on how far your requests have drifted from your usage, which is knowable only by looking.

What it does do is separate the savings you can take safely from the ones that quietly borrow against reliability. The bill and the reliability are not opposing forces. They are both downstream of whether your resource requests tell the truth, and of whether the truth reaches the node count.
