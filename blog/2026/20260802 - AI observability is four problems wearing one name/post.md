---
tags: [observability, ai, opentelemetry, azure, ops, agents]
slug: ai-observability-four-problems
# Held back: this post carries a TODO(jeff) marker asking for one first-person
# receipt. Resolve the marker and delete the draft line, and it publishes.
draft: true
date: 2026-08-02
description: Monitoring tells you the AI ran. It cannot tell you it was right. Four layers, four different denominators, and a privacy flag that protects your users by blinding your quality monitoring.
---

# AI observability is four problems wearing one name

An AI system returns a confident, well-formatted, completely wrong answer. Status 200. Latency inside the p95. No exception, nothing in the error log, dashboard green.

Your alerting is built on exceptions, status codes, timeouts, saturation and error rates. Every one of those is a signal that something announced itself. **Monitoring tells you the system ran. It cannot tell you the system was right**, and until now those were close enough to the same question that nobody had to separate them.

That is the illusion of competence with a dashboard in front of it.

The reason your telemetry feels thin the first time you point it at an AI system is not that you instrumented it badly. It is that "AI observability" is four different problems and most instrumentation treats them as one.

1. **The call.** One inference. Request in, tokens out.
2. **What you fed it.** The prompt, the system instructions, and whatever you retrieved and put in front of the question.
3. **The tools.** The functions the model is allowed to invoke. Real side effects.
4. **The loop.** The agent that runs the other three until it decides it is finished.

The fourth one is not a layer. It is the axis the other three run along, and it is the reason per-call metrics stop meaning anything. More on that below, because it is the part most instrumentation gets wrong.

If you only do a handful of things: get the structural attributes flowing, put one trace around the whole task, version your prompts on the span, promote the quiet failures to loud ones, and add evaluation as a separate sampled track. The rest of this is why.

## The call tells you almost nothing you care about

The model call is the easiest thing to instrument and the most misleading thing to look at. You get latency, token counts, cost and a status. All of it is about the call, not the answer. A call can be fast, cheap, successful and wrong. There is no field for wrong.

The attributes worth carrying, from the [OpenTelemetry GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai):

```
gen_ai.operation.name           chat
gen_ai.provider.name            azure.ai.openai
gen_ai.request.model            <your deployment name>
gen_ai.response.model           <the dated version actually served>
gen_ai.usage.input_tokens       3184
gen_ai.usage.output_tokens      412
gen_ai.response.finish_reasons  ["length"]
gen_ai.prompt.name              triage-classifier
gen_ai.prompt.version           v7
gen_ai.conversation.id          c-8f21...
```

Two of those repay attention.

**`gen_ai.response.finish_reasons` is the closest thing you have to an exception.** A finish reason of `length` means the model stopped because it ran out of output budget, not because it finished the thought. The answer is truncated, the call succeeded, and your user got half a sentence and a conclusion that never arrived. `content_filter` is the other one worth catching, and on a filtered endpoint it can account for more truncation than `length` does. Measure the split rather than assuming it.

**`gen_ai.request.model` and `gen_ai.response.model` are separate fields for a reason.** On Azure you call a deployment name rather than a model alias, and if that deployment is set to auto-update to the default version, the version underneath it rolls forward and your outputs change without you deploying anything. If the response model is not on every span, you cannot answer "what changed on Tuesday", because on your side nothing did.

### Querying finish reasons, and the trap in it

Here is where I have to be careful, because the obvious query does not work everywhere.

`gen_ai.response.finish_reasons` is typed `string[]`. The Azure Monitor exporters flatten span attributes into `customDimensions`, which is a string-to-string map, and they do it differently per language. The .NET exporter calls `Convert.ToString` on the tag value, and for a string array that returns the literal text `System.String[]`. Python stringifies the tuple, so you get `"('length',)"` and a `has` operator matches by accident.

So a query written against the array works in Python, silently returns nothing in .NET, and looks identical in both cases. Agent Framework and Semantic Kernel both ship in Python and .NET, so which behaviour you get depends on the language your agents are written in, not on the framework. Check before you trust the number.

Set your own scalar alongside it and query that:

```python
finish = response.choices[0].finish_reason          # "stop" | "length" | "content_filter"
span.set_attribute("gen_ai.response.finish_reasons", [finish])   # spec-conformant
span.set_attribute("app.finish_reason", finish)                  # queryable everywhere
```

```kusto
// Truncation and filtering as a *rate*. A raw count rises with traffic
// and tells you nothing about quality.
dependencies
| where timestamp > ago(1d)
| where tostring(customDimensions["gen_ai.operation.name"]) == "chat"
| extend finish = tostring(customDimensions["app.finish_reason"])
| summarize
    cut_short = countif(finish in ("length", "content_filter")),
    total     = count()
  by bin(timestamp, 1h), model = tostring(customDimensions["gen_ai.request.model"])
| extend pct = round(100.0 * cut_short / total, 2)
```

Watch it for a week before you set a threshold. Truncation rate is workload-specific: a summarisation service with a tight output budget may sit at several percent quite happily, while a classifier that ever truncates is broken. Alert on a deviation from your own baseline rather than an absolute number.

Two conventions worth matching while you are in there. The span name should be `{gen_ai.operation.name} {gen_ai.request.model}`, so `chat gpt-4.1` rather than `chat`. And the inference span [should be `SpanKind.CLIENT`](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md), though the spec allows `INTERNAL` for a model running in the same process. Hand-rolled spans default to `INTERNAL`, which breaks nothing but looks wrong to anyone reading your traces against the spec.

## Most confident wrong answers start upstream of the model

When a model states something untrue, the instinct is to blame the model. Often enough the model behaved perfectly and faithfully summarised the wrong document.

If you are doing retrieval, the interesting telemetry is not in the model call at all. It is in what you handed the model: which documents came back and their identifiers, how many and how much of the context window they consumed, the score distribution and whether anything crossed the relevance threshold at all, and whether the final answer cited anything that was actually in the retrieved set.

That last one is the whole game. An answer citing nothing you retrieved is an answer the model produced from its own weights. It may be right, it may be stale, and it is definitely not what your retrieval system was for.

The conventions give you a `retrieval` operation with `gen_ai.data_source.id`, plus `gen_ai.retrieval.documents` and `gen_ai.retrieval.query.text` as opt-in attributes.

Prompt versioning is in the spec too, which surprised me: `gen_ai.prompt.name` and `gen_ai.prompt.version` are conditionally required on the inference span when a named template is used. Use them rather than inventing your own namespace, because conformant tooling will read them and your own attributes will be ignored. Keep custom attributes for things the spec genuinely does not cover, such as how many documents came back as opposed to how many you asked for:

```python
with tracer.start_as_current_span(f"chat {model}", kind=SpanKind.CLIENT) as span:
    span.set_attribute("gen_ai.operation.name", "chat")
    span.set_attribute("gen_ai.provider.name", "azure.ai.openai")
    span.set_attribute("gen_ai.prompt.name", "triage-classifier")
    span.set_attribute("gen_ai.prompt.version", "v7")
    span.set_attribute("gen_ai.conversation.id", conversation_id)
    span.set_attribute("app.retrieval.doc_count", len(docs))
```

A prompt behaves like code. It is deployed, it changes behaviour, and it can be rolled back. Plenty of teams already keep prompts in version control with review; plenty do not, and in those the prompt changes without appearing in any release note. Either way, if the version is not on the span you cannot correlate a quality drop with the change that caused it.

## Tool invocation is honest. Tool internals may not be

Here is the good news. A tool call either ran or it threw, took arguments you can inspect, and returned a result you can log. Spans are named `execute_tool {gen_ai.tool.name}`, with `gen_ai.tool.call.arguments` and `gen_ai.tool.call.result` available opt-in.

The caveat is that the spec's own `gen_ai.tool.type` includes `datastore`, and Microsoft's LangChain integration maps retrievers onto `execute_tool`. Sub-agents-as-tools and remote MCP servers land in the same span type. So tool *invocation* is deterministic and observable; a good share of what sits behind it is not.

The failure that matters here is not the tool erroring. That is loud, and loud you can already handle. It is the model calling the wrong tool, or the right tool with plausible but incorrect arguments, and that tool succeeding perfectly. Every metric says success. A record got updated. It was the wrong record.

```python
with tracer.start_as_current_span(f"execute_tool {tool_name}") as span:
    span.set_attribute("gen_ai.operation.name", "execute_tool")
    span.set_attribute("gen_ai.tool.name", tool_name)
    span.set_attribute("gen_ai.tool.call.id", call_id)
    # The model's choice is the thing under test, not the function.
    span.set_attribute("app.tool.args_valid", schema_ok)
    span.set_attribute("app.tool.write", is_mutating)
```

Flagging mutating tools separately is worth the few minutes it costs. "How many write operations did agents perform against production this week, and how many were later reversed by a human" is a governance question that arrives eventually, and it is easier to have the answer than to build it retrospectively.

There is a design point underneath this. Every piece of work you move out of the model's prose and into a tool call becomes deterministic, testable and auditable. Tools are where an AI system stops being a text generator and starts being a system you can operate.

## The loop is not a fourth layer, it is a change of denominator

A single agent run is not one model call. It is a plan, some retrieval, several tool calls, more model calls to decide what to do with the results, and a final answer.

The conventions handle the shape: `invoke_agent {gen_ai.agent.name}`, `invoke_workflow {gen_ai.workflow.name}`, `plan {gen_ai.agent.name}`, with `gen_ai.agent.id` and `gen_ai.agent.version` identifying who did what.

The trap is the unit of measurement. Every metric you instinctively reach for is per call, and per call is now the wrong denominator. What you want is cost per completed task rather than per call, steps per task as a distribution rather than an average (the tail is where the loops live), the termination reason, and the human intervention rate. A run that terminates on its step ceiling is a failure that reports as a completion.

Then there is the arithmetic. If each step were independently 90% reliable, five steps in a chain would be 0.9⁵, roughly 59%. That is a thought experiment rather than a measurement, and real systems are not that clean in either direction: errors are correlated, but many are also recoverable, because a validator rejects or a tool throws. I have [written about the compounding version of this before](https://www.linkedin.com/pulse/ai-understand-before-you-apply-buy-jeff-wouters-d9y1e). The point that survives the caveats is that reliability does not hold steady across a chain, and the output of one step becomes the input of the next, so a subtle error does not stay put. It gets treated as ground truth downstream.

So when the final answer is wrong, where do you look? Each step looks clean on its own. There is no stack trace, just a confident broken result.

## What that actually looks like in a trace

<!-- TODO(jeff): replace this section with a real incident from your own environment.
     What is here is a worked illustration, not something I observed. It needs:
     a real symptom, roughly how long it took to find, and what the fix was.
     The build will refuse to publish while this comment is present. -->

Take a document triage agent that returns the wrong routing decision on a small fraction of cases. Nothing errors. Users notice because the wrong team receives the work.

The trace for one bad run:

```
invoke_agent triage-router            2.9s   ok
├─ plan triage-router                 0.4s   ok
├─ retrieval policy-index             0.2s   ok   app.retrieval.doc_count=0
├─ chat                               1.1s   ok   gen_ai.prompt.version=v7
│                                                 finish_reasons=["stop"]
├─ execute_tool lookup_owner          0.1s   ok   app.tool.args_valid=true
└─ execute_tool assign_queue          0.3s   ok   app.tool.write=true
```

Every span is green. The answer is wrong. The only anomaly is `app.retrieval.doc_count=0`: the retrieval returned nothing above threshold, the model answered from its own weights anyway, and the tool faithfully assigned the queue it was told to.

Without that one custom attribute, the trace says a healthy agent did five healthy things. With it, the diagnosis is a retrieval threshold, not a model problem, and it takes minutes rather than a day of arguing about the prompt.

That is the argument for logging inputs as well as outputs at every hop. Not because you want to read them, but because when you need to walk backwards, output-only telemetry tells you the run happened and nothing about why it went wrong.

Which leads to the problem underneath all of this.

## You cannot evaluate what you are not allowed to store

To measure quality automatically you need the content. To protect people you must not keep the content. Both are true at once.

The specification is unambiguous: model instructions, user messages and model outputs are classed as sensitive, and instrumentations should not capture them without explicit opt-in. `gen_ai.input.messages`, `gen_ai.output.messages` and `gen_ai.system_instructions` are all opt-in for that reason.

Microsoft's Foundry SDK follows suit. Content recording is off unless you switch it on, via [`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`](https://learn.microsoft.com/azure/foundry/observability/how-to/trace-agent-client-side#control-tracing-behavior-with-environment-variables) (or the `Azure.Experimental.TraceGenAIMessageContent` switch in .NET), with a plain warning not to enable it in production unless your compliance requirements allow it. On that SDK you also need `AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true` before you get any GenAI spans at all, which is a confusing hour if nobody told you.

**Do not generalise that default across your stack, though.** Microsoft's own [LangChain integration](https://learn.microsoft.com/azure/foundry/how-to/develop/langchain-traces) documents content recording as **enabled by default**, and Agent Framework and Semantic Kernel emit traces automatically once tracing is on for the project, with a different set of variables again. "Off by default" is a property of a particular SDK, not of the ecosystem. Check the framework you actually run, in the environment you actually run it, rather than trusting a blog post about a different one.

Now the collision. Foundry's trace-based evaluation [only reads spans where `gen_ai.operation.name` is `invoke_agent`](https://learn.microsoft.com/azure/foundry/observability/how-to/troubleshooting#trace-evaluation-issues), and Microsoft's wording is that if those spans have neither `gen_ai.input.messages` nor `gen_ai.output.messages`, the evaluators have no conversation content to score. No content, no automated quality score.

So the flag that protects your users is the same flag that blinds your quality monitoring. That is not a bug in anyone's product. It is the shape of the problem.

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 380" width="720" height="380" role="img" aria-labelledby="dl-t dl-d" style="max-width:100%;height:auto;display:block;margin:1.5rem 0"><title id="dl-t">The privacy and evaluation deadlock</title><desc id="dl-d">A four step cycle: scoring quality requires message content, message content is sensitive and off by default, so spans carry no content, so the evaluator returns no score.</desc><defs><marker id="dl-a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#0aa5c4"/></marker><marker id="dl-aw" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#d2593c"/></marker></defs><rect x="235.0" y="13.0" width="250" height="62" rx="4" fill="none" stroke="currentColor" stroke-opacity="0.28" stroke-width="1.5"/><text x="360" y="38" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="14" fill="currentColor" fill-opacity="1" text-anchor="middle" font-weight="600">You want a quality score</text><text x="360" y="59" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="11" fill="currentColor" fill-opacity="0.62" text-anchor="middle" font-weight="400">groundedness, tool-call accuracy</text><rect x="435.0" y="159.0" width="250" height="62" rx="4" fill="none" stroke="currentColor" stroke-opacity="0.28" stroke-width="1.5"/><text x="560" y="184" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="14" fill="currentColor" fill-opacity="1" text-anchor="middle" font-weight="600">The evaluator needs content</text><text x="560" y="205" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="11" fill="currentColor" fill-opacity="0.62" text-anchor="middle" font-weight="400">gen_ai.*.messages must be present</text><rect x="235.0" y="305.0" width="250" height="62" rx="4" fill="none" stroke="currentColor" stroke-opacity="0.28" stroke-width="1.5"/><text x="360" y="330" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="14" fill="currentColor" fill-opacity="1" text-anchor="middle" font-weight="600">Spans carry no content</text><text x="360" y="351" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="11" fill="currentColor" fill-opacity="0.62" text-anchor="middle" font-weight="400">nothing to evaluate against</text><rect x="35.0" y="159.0" width="250" height="62" rx="4" fill="none" stroke="currentColor" stroke-opacity="0.28" stroke-width="1.5"/><text x="160" y="184" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="14" fill="currentColor" fill-opacity="1" text-anchor="middle" font-weight="600">Content is sensitive</text><text x="160" y="205" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="11" fill="currentColor" fill-opacity="0.62" text-anchor="middle" font-weight="400">opt-in, and off by default</text><line x1="470" y1="62" x2="545" y2="158" stroke="#d2593c" stroke-width="1.5" marker-end="url(#dl-aw)"/><line x1="545" y1="222" x2="470" y2="318" stroke="#d2593c" stroke-width="1.5" marker-end="url(#dl-aw)"/><line x1="250" y1="318" x2="175" y2="222" stroke="#d2593c" stroke-width="1.5" marker-end="url(#dl-aw)"/><line x1="175" y1="158" x2="250" y2="62" stroke="#d2593c" stroke-width="1.5" marker-end="url(#dl-aw)"/><text x="360" y="186" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="13" fill="#d2593c" fill-opacity="1" text-anchor="middle" font-weight="600">no way out</text><text x="360" y="206" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="11" fill="currentColor" fill-opacity="1" text-anchor="middle" font-weight="400">without a deliberate trade</text></svg>

What I would do in an environment with real data protection obligations, and I would want a DPIA rather than a blog post to settle it:

- **Enable content recording for a sampled slice, not the whole stream.** You do not need every conversation to detect a regression.
- **Send content-bearing telemetry to its own resource**, with its own access control and its own retention period. Not the general workspace half of IT can query.
- **Redact before export.** Once it is in the pipeline it is in the backups, and unpicking that later is worse than gating it now.
- **Keep the structural telemetry always on.** Token counts, finish reasons, tool names, step counts, termination reasons and costs are far lower risk and answer most operational questions on their own.

One correction to a claim you will see made often, including by me until someone checked it: structural telemetry is lower risk, not risk-free. `gen_ai.conversation.id` is a pseudonymous identifier, and pseudonymised data counts as personal data under GDPR wherever it can still be attributed to a person using other information you hold. In most deployments a conversation id can be joined back to a user, which is the case you should assume until someone demonstrates otherwise. Retrieved document identifiers can point at a case file about a named individual. Application Insights typically stamps rows with client city and country derived from IP, without you instrumenting anything, [unless IP collection is disabled](https://learn.microsoft.com/azure/azure-monitor/app/ip-collection). "No content" narrows the conversation with your DPO. It does not end it.

## What breaks, and what does not

Your existing stack still works perfectly for availability and latency, for tool and API failures, for cost and token spend, for throughput and saturation, and for trace topology, which was designed for exactly this shape.

It goes quiet on correctness, where there is no signal and no threshold to alert on. On groundedness, meaning whether the answer came from your data or the model's memory. On tool selection, where the right function is called for the wrong reason. On task completion, where every step is green and the outcome is useless. And on drift, where this month's answers are worse than last month's and nothing errored in between.

Look back at the four layers and the same issue turns up each time. The truncated answer, the stale model version, the confidently summarised wrong document, the right tool with the wrong argument, the agent that hit its step ceiling and reported success. None of them is an availability failure. Every one is a judgement failure, and judgement does not throw exceptions.

The first list is monitoring. The second needs evaluation, which is a different discipline you add rather than a dial you turn.

## What this costs, and what you would actually be buying

The instrumentation is genuinely cheap. If you already run OpenTelemetry, the GenAI conventions are a set of attributes and a few new span types, not a new stack. Azure Monitor ingests them as ordinary spans and Application Insights has [an agent view](https://learn.microsoft.com/azure/azure-monitor/app/agents-view) built on them.

The honest caveat, as of August 2026: **no `gen_ai.*` attribute is marked Stable.** The whole namespace is Development, it has [moved into its own repository](https://github.com/open-telemetry/semantic-conventions-genai), and it is iterating quickly. Adopt it, because a moving standard still beats everyone inventing their own names, but put a thin translation layer between the conventions and any dashboard you would be annoyed to rewrite.

Two things I would not pretend away.

**Ingestion is not free and this design is ingestion-heavy.** Twenty spans for one user question, with inputs and outputs at every hop, into a backend billed per gigabyte. Microsoft says so directly in its own tracing guidance: trace data is subject to your retention settings and Azure Monitor pricing, and you should consider adjusting sampling rates or retention. Cost your ingestion before you enable content recording broadly, not after the first invoice.

**Evaluation is where the products earn their money.** The vocabulary is standardised and free. Golden dataset curation, annotation queues, human review interfaces tied to specific spans, judge calibration, inter-annotator agreement, dataset versioning and online eval scheduling are not, and none of them is an attribute you can set. If you buy something in this category, buy it for that, and know that the tracing layer underneath it is a commodity you already own. Buying a product to emit spans is the part that does not make sense.

## Making it survive scale

**Sample on outcome, and know what that costs you.** Head sampling decides before the run has an outcome, so it discards the interesting runs at the same rate as the boring ones. What you want is tail sampling: keep everything that scored badly, errored, looped or made the user retry, and discard most of the clean successes. Be clear that this is a real architectural addition rather than a setting. Application Insights' own sampler is trace-ID-hash based and outcome-blind, and Microsoft states that full tail-based sampling [is not currently supported](https://learn.microsoft.com/azure/azure-monitor/app/application-insights-faq); doing it properly means an OpenTelemetry Collector with the `tail_sampling` processor in front of the exporter. This is the one place where "you already own the pipeline" stops being true.

**Keep prompt text out of metric dimensions.** It belongs on a sampled span. As a metric label it is unbounded cardinality, which hurts ingest and query performance and shows up on the bill.

**Watch the cost of watching.** Judging every response with a model adds a second non-deterministic system to the one you were trying to understand, and a bill that varies enormously with the judge model and rubric size. Judge a sample. Use cheap deterministic proxies for the rest: regeneration rate, abandonment, escalation to a human, and the edit distance between what the AI drafted and what actually got sent.

That last signal is a useful one and an imperfect one, so treat it carefully. If people heavily rewrite what the assistant produces, something is wrong regardless of what your groundedness score says. But it is confounded, because people edit for tone and house style as much as for correctness, and a low edit rate can mean the output is good or that users have stopped reading it. Make it a KPI and you will get paste-accept behaviour with the fixes made downstream where you cannot see them.

## Where to start

**Get the structural attributes flowing.** Operation name, provider, request and response model, token usage, finish reasons, conversation id. Low risk, immediate value, and no privacy discussion needed beyond confirming that conversation ids fall under your existing telemetry policy.

**Put one trace around the whole task.** One conversation id and one root span from the user's question through every call, retrieval, tool and sub-agent. Without it you have a pile of unrelated spans and no way to ask whether the task worked.

**Version everything on the span.** Prompt name and version, tool schema version, agent version. Five attributes, and the difference between diagnosing a regression quickly and arguing about it for a day.

**Promote the quiet failures.** Truncation and content filtering, retrieval returning nothing above threshold, agents terminating on a step ceiling. These are already in your telemetry and nothing is looking at them.

**Add evaluation as a separate sampled track.** Groundedness and tool-call accuracy on a slice of production traffic, plus a golden set you run on every prompt change. Decide up front who owns it, because this is where it usually stalls: the app team has the context, the platform team has the pipeline, and neither has the budget line.

**Instrument the humans.** Override rate, escalation rate, regeneration rate.

## Why trust an AI to grade an AI

Fair question to finish on. If AI fails convincingly, why would an AI evaluator be any better at spotting it?

Partly it is not, and anyone selling LLM-as-a-judge as solved is overselling. Judge models have the same non-determinism, and there is a real literature on their position bias, verbosity bias and preference for their own outputs.

The reason it is still worth doing is narrower than it first looks. Grading a specific answer against specific retrieved documents and a defined rubric is a bounded, structured task with the criteria fixed in advance. Deciding what the user should be told is an open judgement call. That is the same line I drew around [contract review](https://www.linkedin.com/pulse/ai-understand-before-you-apply-buy-jeff-wouters-d9y1e): excellent at checking whether a document contains a clause matching defined criteria, poor at telling you what your exposure is. Verification, not interpretation.

So use the judge for what it is good at, sample it, calibrate against human review often enough to notice drift, and never let it be the only thing between a broken system and your users.

Please don't misunderstand me. I am not arguing that AI systems are unobservable, or that you should wait for the conventions to settle before building anything. I am arguing that the instruments you already trust were built to answer a question that has quietly stopped being the important one, and nothing will tell you that, because the dashboard stays green either way.

Monitoring tells you the system ran. Evaluation tells you it was right. You need both, and you currently have one.

---

*Everything here reflects my own personal views and experience, not those of my employer or any organisation I'm affiliated with.*
