---
tags: [kubernetes, gpu, ai, aks, cost, finops, llm, ops]
slug: gpu-costs-kubernetes-sharing
# Held back: this post carries a TODO(jeff) marker asking for one first-person
# receipt. Resolve the marker and delete the draft line, and it publishes.
draft: true
date: 2026-08-02
description: GPU spend is idle time, not utilisation. Every way of sharing a card trades isolation for density, the metrics meant to guide that choice are misleading, and for LLM serving the defaults quietly work against you.
---

# GPU costs on Kubernetes: sharing is a reliability decision

Put a number on it before anything else. An eight-GPU H100 node ([`Standard_ND96isr_H100_v5`](https://learn.microsoft.com/azure/virtual-machines/sizes/gpu-accelerated/ndh100v5-series)) lists at $98.32 an hour in East US, which is around $72,000 a month if you leave it running. The eight-GPU A100 equivalent is $27.20 an hour, about $20,000 a month. Even a single-GPU H100 node is roughly $5,000 a month. Those are Azure retail Linux rates as of August 2026 and they move, but the order of magnitude is the point: one forgotten pool outweighs most teams' entire non-production estate.

Nobody decides to spend that. It happens because a pool was created for a project, the project finished, and no alert fires for expensive idleness.

That is the shape of accelerator spend. Not expensive work, expensive waiting. And the reflex when someone notices the number is to pack more workloads onto each card, which is a reasonable instinct with a consequence people skip past: **every mechanism for sharing a GPU trades isolation for density**. The useful question is not how much more you can fit. It is what failure you are willing to have shared.

I wrote separately about [Kubernetes cost in general](/posts/2026/cutting-kubernetes-costs-without-cutting-reliability/), where the argument is that overspend is the gap between requests and usage. Accelerators are that argument with the volume turned up and most of the usual tooling unavailable.

<!-- TODO(jeff): no first-person receipt in this one either.
     If you have run GPU workloads in anger, one concrete example, a job that
     sat idle, a sharing configuration that bit you, a utilisation number that
     turned out to be meaningless, would anchor the whole piece.
     If not, label it as a researched guide in the opening.
     The build will refuse to publish while this comment is present. -->

## How bad is idle, actually

Microsoft states the mechanism plainly: [you incur cost on a GPU node pool even when no GPU workload is running](https://learn.microsoft.com/azure/architecture/reference-architectures/containers/aks-gpu/gpu-aks). The harder question is what fraction of paid GPU time does useful work, and the published evidence is thinner than the confident numbers in circulation suggest.

The best-sourced measurement I found is the Alibaba PAI trace published at [NSDI '22](https://www.usenix.org/system/files/nsdi22-paper-weng.pdf). 6,742 GPUs, 1.2 million tasks. The headline pair is the one worth carrying: the **median instance requested 0.5 of a GPU and used 0.042 of one**. A twelve-fold gap, in production, at scale. Heavy utilisation of 95% or above accounted for only 7% of cases, and their scheduler simulation suggested half the GPUs would have sufficed with sharing enabled.

Two caveats I want to state rather than bury, because the article later criticises other people's methodology. **The trace was collected in July and August 2020.** That is a multi-tenant ML platform dominated by training and classical ML, before LLM serving existed as a workload class and before continuous batching. The request-versus-usage gap is a durable finding about human behaviour under uncertainty. The specific numbers describe notebook-scale jobs on pre-Ampere hardware, not a fleet running inference on H100s.

There is also a [Microsoft Research study from ICSE 2024](https://www.microsoft.com/en-us/research/wp-content/uploads/2024/01/gpu-util-icse2024.pdf) which examined 400 deep learning jobs, and found 85% of low-utilisation issues were fixable with small code or script changes, mostly around data loading and batch size. Note that study deliberately sampled jobs already below 50% utilisation, so it characterises causes rather than fleet averages.

Vendor reports quoting single-digit average GPU utilisation may well be right. The ones I could check do not publish their methodology, and the companies publishing them sell optimisation software. Treat them as a prompt to measure, not as a measurement.

## Your utilisation dashboard misleads in both directions

Before optimising anything, know that the obvious metric does not mean what its name implies.

**SM Activity is a duty cycle.** [NVIDIA defines it](https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/feature-overview.html) as the fraction of time at least one warp was active on a multiprocessor, averaged across multiprocessors, and gives two examples that both produce 0.2. On a GPU with N streaming multiprocessors, a kernel launching N/5 blocks that runs for the whole interval reports 0.2. So does a kernel launching N blocks that runs for a fifth of the interval with the SMs idle the rest of the time.

That is the problem in one metric: 0.2 could mean a fifth of the card all of the time, or all of the card a fifth of the time, and the number cannot tell you which. A warp waiting on memory also counts as active.

**Memory utilisation is worse, because inference servers pre-allocate.** vLLM reserves GPU memory for its KV cache at startup, with `gpu_memory_utilization` defaulting to 0.92. The memory graph therefore reads 92% permanently, whether the server is saturated or idle.

Put those together and an idle inference pod can look busy while a loaded one looks unremarkable. What to use instead:

- **GPU-seconds allocated against GPU-seconds used**, per namespace and workload. [Microsoft's GPU observability guidance](https://learn.microsoft.com/azure/aks/best-practices-gpu-observability) recommends exactly this as a shared metric between platform and finance, because aggregate averages hide over-allocation.
- **Serving metrics for inference.** Tokens per second, requests waiting, KV-cache block utilisation, time to first token. These tell you whether the server is saturated; GPU percentage does not.
- **DCGM enriched with pod labels**, so telemetry attributes to a team rather than to a card.

Same failure I described in [instrumenting AI systems](/posts/2026/ai-observability-four-problems/): the instrument you already trust is answering a question that stopped being the important one.

## The three ways to share a card

[Microsoft's comparison](https://learn.microsoft.com/azure/aks/concepts-gpu-partitioning) is a good frame, and the isolation column is the one to read first.

| | Isolation | Density | Status |
|---|---|---|---|
| **Time-slicing** | None. Shared memory, shared fault domain | Highest, arbitrary N | Stable, any CUDA GPU |
| **MPS** | Memory capped per client, limited error containment | High | Experimental in the device plugin, incompatible with MIG |
| **MIG** | Hardware partitioning, dedicated memory, error isolation | Up to 7 | Production-recommended, Ampere and later only |

[NVIDIA's device plugin documentation](https://github.com/NVIDIA/k8s-device-plugin) is blunt about time-slicing: replicas of the same GPU run in the same fault domain, so if one workload crashes they all do. It also states that requesting more than one time-sliced GPU does not guarantee a proportional share of compute. MPS is better but not safe: NVIDIA's guidance says a fatal GPU fault from one client is [reported to all clients on the affected GPUs](https://docs.nvidia.com/deploy/mps/when-to-use-mps.html), without indicating which one caused it, and the MPS server waits for all of them to exit. Contained to the shared GPU rather than isolated from it.

Two MIG constraints decide architecture rather than configuration.

**Hardware.** [NVIDIA's supported profile list](https://docs.nvidia.com/datacenter/tesla/mig-user-guide/supported-mig-profiles.html) covers A100, H100, H200 and B200 at seven instances, A30 and RTX PRO 6000 Blackwell at four, and a couple of Blackwell workstation parts at two. **L4, L40S, T4 and V100 do not appear at all**, which is an expensive planning surprise, because L4 and L40S are exactly the cards a cost-conscious team reaches for.

**Geometry is fixed at node pool creation.** Microsoft states that partitioning is static at pool level and changes require reprovisioning; through the GPU Operator, reconfiguration stops all GPU pods on the node and may need a reboot. Since nobody can name the model they will be serving in a year, the practical advice is to pick a geometry that fits the largest model you serve today with headroom, and accept that a genuinely new model class means a new node pool.

## The LLM traps

This is where general Kubernetes cost advice goes wrong, because it was written for training and batch.

**Time-slicing plus vLLM fails on the defaults, and the fix is not obvious.** Set `replicas: 4` on the device plugin and deploy four vLLM servers, and the first one reserves 92% of the card. The rest die. The instinct is to blame time-slicing for having no memory cap.

That is not quite right, and it matters. vLLM's own [field documentation](https://docs.vllm.ai/en/stable/configuration/engine_args/) says `gpu_memory_utilization` "is a per-instance limit, and only applies to the current vLLM instance. It does not matter if you have another vLLM instance running on the same GPU. For example, if you have two vLLM instances running on the same GPU, you can set the GPU memory utilization to 0.5 for each instance." The cap exists. It just has to be set by you, on every instance, in agreement with a replica count configured somewhere completely different, with nothing validating that the two add up.

So this is a footgun rather than an incompatibility. Two independent settings that must be kept consistent by hand, in different files, owned by different teams, where getting it wrong produces a crash loop at deploy time and getting it *nearly* right produces a KV cache too small to serve your batch size. You still get no fault isolation and no compute guarantee. Set both deliberately or use MIG.

**Requesting more than one time-sliced GPU silently does nothing.** `failRequestsGreaterThanOne` defaults to `false` for backwards compatibility, so a pod requesting two replicas is admitted, runs, and receives no proportional share. Setting it to `true` makes the request fail honestly, but understand what "fail" means here before you flip it. The extended resource still exists on the node, so the scheduler binds the pod happily and the **kubelet** rejects it at admission with `UnexpectedAdmissionError`. The pod lands in `Failed`, not `Pending`, and it does not self-heal: NVIDIA's documentation says you must manually delete the pod, change the resource request and redeploy. A controller behind it will keep producing pods that keep failing. Fix every manifest requesting more than one first, then set the flag.

**Sharing the server is a real option with its own cost, not a free escape.** The alternative to putting four servers on a card is one server with continuous batching handling all the traffic, with multiple adapters if you need multiple behaviours. That is what these servers are built for and it usually gets better throughput than four fragmented ones.

But be honest about what it does to the failure mode: one process serving every tenant is not less fault coupling, it is more. A crash, a bad rollout or an OOM takes every in-flight request and the whole KV cache with it. Time-slicing at least gives each tenant its own process to lose.

So the actual choice is between three failure shapes: many processes sharing a fault domain (time-slicing), one process that is a single fault domain (shared server), or genuine isolation at fixed granularity on hardware that supports it (MIG).

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 880 350" width="880" height="350" role="img" aria-labelledby="bl-t bl-d" style="max-width:100%;height:auto;display:block;margin:1.5rem 0"><title id="bl-t">Three ways to share a GPU, and the blast radius of each</title><desc id="bl-d">Time-slicing places four pods in one shared fault domain. A shared inference server places every tenant inside a single process. MIG gives each pod an isolated hardware partition.</desc><defs><marker id="bl-a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#0aa5c4"/></marker><marker id="bl-aw" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#d2593c"/></marker></defs><text x="20" y="24" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="15" fill="currentColor" fill-opacity="1" text-anchor="start" font-weight="600">Time-slicing</text><text x="20" y="42" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="11.5" fill="currentColor" fill-opacity="0.62" text-anchor="start" font-weight="400">one shared fault domain</text><rect x="20" y="62" width="250" height="200" rx="4" fill="none" stroke="currentColor" stroke-opacity="0.28" stroke-width="1.5"/><text x="32" y="84" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="11" fill="currentColor" fill-opacity="0.62" text-anchor="start" font-weight="400">GPU</text><rect x="32" y="96" width="226" height="138" rx="4" fill="none" stroke="#d2593c" stroke-opacity="1" stroke-width="1.5" stroke-dasharray="5 4"/><rect x="44" y="110" width="92" height="40" rx="4" fill="none" stroke="currentColor" stroke-opacity="0.28" stroke-width="1.5"/><text x="90" y="135" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12" fill="currentColor" fill-opacity="0.62" text-anchor="middle" font-weight="400">pod 1</text><rect x="150" y="110" width="92" height="40" rx="4" fill="none" stroke="currentColor" stroke-opacity="0.28" stroke-width="1.5"/><text x="196" y="135" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12" fill="currentColor" fill-opacity="0.62" text-anchor="middle" font-weight="400">pod 2</text><rect x="44" y="162" width="92" height="40" rx="4" fill="none" stroke="currentColor" stroke-opacity="0.28" stroke-width="1.5"/><text x="90" y="187" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12" fill="currentColor" fill-opacity="0.62" text-anchor="middle" font-weight="400">pod 3</text><rect x="150" y="162" width="92" height="40" rx="4" fill="none" stroke="currentColor" stroke-opacity="0.28" stroke-width="1.5"/><text x="196" y="187" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12" fill="currentColor" fill-opacity="0.62" text-anchor="middle" font-weight="400">pod 4</text><text x="32" y="248" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="12" fill="#d2593c" fill-opacity="1" text-anchor="start" font-weight="600">a crash takes all four</text><text x="310" y="24" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="15" fill="currentColor" fill-opacity="1" text-anchor="start" font-weight="600">Shared server</text><text x="310" y="42" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="11.5" fill="currentColor" fill-opacity="0.62" text-anchor="start" font-weight="400">one process, every tenant</text><rect x="310" y="62" width="250" height="200" rx="4" fill="none" stroke="currentColor" stroke-opacity="0.28" stroke-width="1.5"/><text x="322" y="84" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="11" fill="currentColor" fill-opacity="0.62" text-anchor="start" font-weight="400">GPU</text><rect x="322" y="96" width="226" height="138" rx="4" fill="none" stroke="#d2593c" stroke-opacity="1" stroke-width="1.5" stroke-dasharray="5 4"/><rect x="336" y="110" width="198" height="108" rx="4" fill="none" stroke="currentColor" stroke-opacity="0.28" stroke-width="1.5"/><text x="435.0" y="132" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12" fill="currentColor" fill-opacity="0.62" text-anchor="middle" font-weight="400">one server process</text><text x="435.0" y="154" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12" fill="currentColor" fill-opacity="0.62" text-anchor="middle" font-weight="400">tenant A  B  C  D</text><text x="322" y="248" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="12" fill="#d2593c" fill-opacity="1" text-anchor="start" font-weight="600">the largest single domain</text><text x="600" y="24" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="15" fill="currentColor" fill-opacity="1" text-anchor="start" font-weight="600">MIG</text><text x="600" y="42" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="11.5" fill="currentColor" fill-opacity="0.62" text-anchor="start" font-weight="400">hardware partitions</text><rect x="600" y="62" width="250" height="200" rx="4" fill="none" stroke="currentColor" stroke-opacity="0.28" stroke-width="1.5"/><text x="612" y="84" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="11" fill="currentColor" fill-opacity="0.62" text-anchor="start" font-weight="400">GPU</text><rect x="624" y="106" width="92" height="40" rx="4" fill="none" stroke="#0aa5c4" stroke-opacity="1" stroke-width="1.5" stroke-dasharray="5 4"/><text x="670" y="131" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12" fill="currentColor" fill-opacity="0.62" text-anchor="middle" font-weight="400">pod 1</text><rect x="730" y="106" width="92" height="40" rx="4" fill="none" stroke="#0aa5c4" stroke-opacity="1" stroke-width="1.5" stroke-dasharray="5 4"/><text x="776" y="131" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12" fill="currentColor" fill-opacity="0.62" text-anchor="middle" font-weight="400">pod 2</text><rect x="624" y="158" width="92" height="40" rx="4" fill="none" stroke="#0aa5c4" stroke-opacity="1" stroke-width="1.5" stroke-dasharray="5 4"/><text x="670" y="183" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12" fill="currentColor" fill-opacity="0.62" text-anchor="middle" font-weight="400">pod 3</text><rect x="730" y="158" width="92" height="40" rx="4" fill="none" stroke="#0aa5c4" stroke-opacity="1" stroke-width="1.5" stroke-dasharray="5 4"/><text x="776" y="183" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12" fill="currentColor" fill-opacity="0.62" text-anchor="middle" font-weight="400">pod 4</text><text x="612" y="248" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="12" fill="#0aa5c4" fill-opacity="1" text-anchor="start" font-weight="600">a fault stays in its slice</text><text x="20" y="336" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="12" fill="currentColor" fill-opacity="0.7" text-anchor="start" font-weight="400">Dashed boundary = fault domain. Density rises left to right in cost, not in safety.</text></svg>

The shared server wins on throughput. MIG wins on blast radius. Neither wins on both.

## Dynamic Resource Allocation, and where it actually is

Core Dynamic Resource Allocation [graduated to GA in Kubernetes 1.34](https://kubernetes.io/blog/2025/09/01/kubernetes-v1-34-dra-updates/), so the structured device allocation model has been stable for the better part of a year. Be precise about what that covers, though: the piece that actually shares one device across pods, Consumable Capacity, is still alpha, and Partitionable Devices is beta. The GA milestone is the allocation framework, not fractional sharing.

The vendor side is the gap. NVIDIA's DRA driver documents its multi-node NVLink ComputeDomains support as officially supported while GPU allocation features, including dynamic MIG, are not yet officially supported, and the GPU kubelet plugin ships disabled by default in the Helm chart. Check the current release notes before building a strategy on it, because this is the part most likely to have moved since August 2026. Today the production path remains the device plugin with MIG or time-slicing.

## Scale-to-zero costs minutes, not seconds

Scaling an idle inference endpoint to zero is the obvious answer, and it is a latency decision as much as a cost one.

Model serving images are enormous. Azure's troubleshooting guidance for the AI toolchain operator states that [inference images are typically 30 GB to 100 GB and the pull can take up to tens of minutes](https://learn.microsoft.com/troubleshoot/azure/azure-kubernetes/extensions/troubleshoot-ai-toolchain-operator-addon-issues) depending on cluster networking. Add node provisioning if the pool is also at zero, then weight loading, then CUDA graph capture.

Mitigations, with their trade-offs stated rather than ranked:

- **Pre-pull and cache images on nodes.** Costs disk, saves the largest single component of cold start.
- **Keep a warm node pool even when pods are zero.** Effective, and it is not really scaling to zero. You are paying for the node to avoid paying for the wait.
- **Model weights on a shared volume rather than baked into the image.** Sometimes faster, sometimes slower: RWX file storage pulling 70 GB can underperform a cached image pull, and it converts many independent cold starts into one shared bottleneck. Benchmark it rather than assuming.
- **One or two warm replicas during business hours, zero overnight.** The pragmatic answer for anything a human waits on.

Scale-to-zero is right for batch, evaluation and internal tooling. For an interactive surface, a warm replica is cheaper than the abandoned session.

## Separate training from inference

Standard practice, for reasons more specific than "different workloads".

**Different interruption tolerance.** Training checkpoints and resumes, so it can live on spot. Inference is restartable in principle but latency-sensitive in practice: a replacement replica that takes minutes to load weights is an outage from the user's point of view, even though the process itself restarts fine.

**Different scaling shapes.** Training scales gradually and wants large, tightly coupled, topology-aware multi-GPU nodes. Inference follows traffic and often prefers one or two GPUs per node, spread for availability.

**Different SKUs.** Training wants A100 or H100 class with NVLink. Inference frequently runs happily on L4 or A10 at a fraction of the price.

**Different sharing modes.** MIG or dedicated for latency-sensitive serving; time-slicing is defensible for experimentation where a shared fault domain costs somebody an afternoon.

Separate node pools with taints and tolerations is the mechanism.

## Queueing, and the spot caveat nobody states

Two large jobs each holding half the GPUs, neither able to start. Everything allocated, nothing progressing.

[Kueue](https://kueue.sigs.k8s.io/docs/overview/) is the Kubernetes-native answer: quota with fair sharing, fungibility across resource flavours, preemption, and **all-or-nothing gang admission**, which is what fixes the deadlock. Its provisioning-request integration also stops you spinning up expensive nodes for a job that then cannot be admitted. The API is at v1beta2, so treat it as maturing.

Which leads to a warning that follows directly and which most spot advice omits. **Gang-scheduled multi-node training on spot is close to the worst case.** Losing one node kills the whole job, you forfeit every GPU-hour since the last checkpoint across the entire allocation, and re-acquiring a large homogeneous allocation of scarce SKUs at the moment you need it is exactly when capacity is least available. Spot suits single-node and embarrassingly parallel work with frequent checkpoints. For large gang-scheduled runs, do the arithmetic rather than trusting either instinct: spot on that same eight-GPU H100 SKU is around $18 an hour against $98 on-demand, so you can afford to waste roughly five times the compute in restarts before spot loses. Whether you do depends on your eviction rate and your checkpoint interval, which is why both are worth measuring before the argument.

Where spot does fit, Microsoft's boundary is clear: work that can be checkpointed or restarted cleanly, never user-facing inference. That requires shutdown inside thirty seconds, checkpoints written outside the spot VM, idempotent jobs and pre-baked images.

And before the argument about whether spot is too risky, look up the actual number. Azure publishes **per-SKU, per-region eviction rates in bands**, queryable through the `SpotResources` table in [Azure Resource Graph](https://learn.microsoft.com/azure/virtual-machines/spot-vms) over the trailing 28 days. The portal shows the same bands over a 7-day window, so the two will not always agree. A SKU in the 0 to 5% band and one in the 20%-plus band are not the same proposition.

## Check you are optimising the right bill

This section is last in most treatments of the subject and probably should not be.

Microsoft's [AI cost optimisation guidance](https://learn.microsoft.com/startups/build/ai/ai-cost-optimization) breaks the typical bill down with **tokens at 30 to 60% and GPUs at 20 to 50%**. Those are indicative ranges on a guidance page rather than a measured benchmark, and they overlap, so do not treat them as precise. But the direction is worth taking seriously: if any part of your workload calls hosted models, the request path may be the larger lever, and prompt caching, routing simple queries to smaller models, batch APIs and quantisation all act on it without touching a node pool.

That same page is where I took the framing for this article's opening, and it is worth reading in full.

There is also a failure mode hiding in agent architectures: **retrieval fan-out**. A single chat turn can issue several hidden queries through re-rankers, query rewriters and tool-calling steps, each costing tokens and latency. Keeping retrievals per turn low and alerting on the median is only possible if the trace carries them, which is the argument from the observability piece arriving from another direction.

So: work out the split between token spend and infrastructure spend before you spend a quarter on cluster efficiency. If tokens dominate, most of this article is the second priority.

## What I would do first

Measure allocated GPU-seconds against used GPU-seconds, per namespace. Everything else is guesswork without it, and the number is usually enough on its own to make the case for the rest of the work.

Then stop trusting GPU percentage, and move inference decisions onto serving metrics. Then go looking for pools that exist because a project needed them months ago, with the caveat that in a capacity-constrained region a pool you release may not be a pool you can get back, so check availability before deleting rather than after.

After that: split training from inference onto separate pools, move checkpointable single-node work to spot with the eviction rates checked, decide deliberately between a shared server and MIG for serving rather than defaulting into time-slicing, and queue the batch work so partial allocation stops holding cards hostage.

## The trade nobody writes down

Every sharing decision here has the same shape. More density, less isolation. The saving is continuous, visible and easy to attribute. The cost is a probability of an incident that will be attributed to something else entirely when it arrives.

That is not an argument against sharing, and it would be a poor one. Running a single workload per A100 because it feels safer is its own large waste, and on hardware that supports MIG the dichotomy largely dissolves: you get isolation and density together, and the honest version of this article's title on that hardware is narrower, roughly "do not run time-slicing in production."

What remains is the part worth writing down. Which workloads may share a fault domain, which may not, and who decided. That document is worth more than any of the individual levers above, because it is the thing that stops the next cost exercise quietly making the choice for you.
