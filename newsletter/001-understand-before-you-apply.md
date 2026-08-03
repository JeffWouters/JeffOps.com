---
number: 1
title: AI - Understand before you apply (and buy)
date: 2026-06-22
slug: understand-before-you-apply
linkedin_url: https://www.linkedin.com/pulse/ai-understand-before-you-apply-buy-jeff-wouters-d9y1e
description: AI doesn't think, it predicts. Why that makes it superb at some tasks, a liability at others, and how to tell which is which before you buy.
---

AI is a wonderful tool. The speed at which it can perform certain tasks is just downright amazing. But it’s a tool, nothing more than that. It’s not a way to replace your workforce. Let me explain.

## How AI models work

It essentially comes down to the very basics of how AI models work. AI doesn’t think, it predicts. Instead of thinking:

> This is the correct answer

It does this:

> Here are the top 10 plausible next words, each with a probability.

Example (simplified):

| Word         | Probability |
|--------------|-------------|
| "increase"   | 40%         |
| "optimize"   | 30%         |
| "improve"    | 20%         |
| "reduce"     | 10%         |

However, instead of always picking the one with the highest probability, it often samples from the list. That means sometimes it goes left, sometimes right. And you can’t predict, and therefore depend on, when it does which. Therefore, results given by AI will never be inherently consistent. It’s simply not in its nature.

When you think about AI, think less about it as a ‘thinking brain’ and more about it as a very advanced pattern prediction engine training on enormous amounts of data.

## Why the randomness is intentionally built in

If the model would always pick the #1 most likely word the responses would be repetitive, creativity would collapse and conversations would feel robotic. That same mechanism is exactly why AI is both extremely powerful and fundamentally limited and therefore very good at certain tasks, but also very bad at others.

## Using AI’s randomness

### Creative work

For some brainstorming and creative work this is great!

> Give me 3 examples of a company logo which name is ‘JeffOps’.
>
> Explain AI to me using 3 different analogies.

You get variety. You get ideas. You get speed. So, AI is great for marketing? Yes, as a tool. Not as a replacement.

### Brainstorming

Let’s take a question that I’ve used many times, or variations of it:

> How should I grow and/or improve my business?

Valid answers to this might include:

- Improve pricing
- Increase marketing spending
- Focus on retention
- Expand to new markets

All of these exist in the models’ learned patterns and are given as answers to my question as a result. So, what you’re basically seeing is the model picking different valid paths through the same landscape (set of data), but with vastly different outcomes.

## The scalability trap (but is it a trap?)

A common argument for the use of AI is that it’s right most of the time. Which is true, but that’s not the real issue. The real issue is scale.

If AI is wrong 10% of the time, it’s manageable. But if AI runs your business (context is always important 😉), that 10% becomes hundreds of mistakes. Let's take legal work. Writing a paragraph of 200 words would mean there will be 20 wrong words in it. This could become a very heavy, and very pricy endeavor 😉

What works fine in isolation turns into a liability nightmare at scale.

## The illusion of competence

Here's the trap: AI doesn't fail loudly. It fails convincingly. Its answers sound correct, look polished, and feel complete. The grammar is clean, the structure is logical, the tone is confident. And none of that tells you whether a single word of it is true.

That's the part worth sitting with. With people, we use polish as a shortcut for competence — and most of the time it works. When someone speaks fluently and confidently about a topic, it's usually because they actually understand it. Producing a clear, well-structured answer normally requires knowing the material. So we've learned to trust the signal.

AI breaks that link completely. Remember how these models work: they don't reason toward a correct answer, they predict plausible-sounding text. Plausibility is the objective. Fluency isn't a side effect of understanding — it's the entire product. The model produces the exact same confident, polished output whether it's right or completely wrong. There's no tell. No hesitation, no "I'm not sure about this," no awkward phrasing that gives it away.

So every instinct you'd normally use to judge whether to trust an answer — the very cues that serve you well with humans — is exactly the thing AI generates effortlessly, regardless of truth. Your judgment isn't just unhelpful here; it actively works against you.

If you've spent any time in ops or engineering, this should feel especially wrong. We're trained to trust that failures are visible. A bug throws an exception. A bad deploy crashes. A broken query returns an error, a null, a stack trace — something red, something loud. You know it failed. AI doesn't give you that. It fails silently, with a straight face, and hands you a wrong answer that's indistinguishable from a right one.

And that's where the most dangerous errors live: not the ones that blow up, but the ones that look perfectly fine and slip straight through. The mistakes you never catch are the expensive ones.

This is also why "it's right most of the time" is cold comfort. If the failures announced themselves, a 90% hit rate would be easy to manage — you'd just fix the 10% you can see. But the failures don't announce themselves. They hide inside the 90% that looks identical. So the real cost isn't the error rate. It's that you can't tell which answers are the errors without checking every one yourself.

Which brings it back to the point: AI is brilliant at producing things that look finished. Whether they're actually correct is a separate question — and answering it is still your job.

## 1-person AI companies

You've probably seen the claim: a single person, no employees, running an entire company because AI agents handle everything. Marketing, sales, support, content, ops — all automated. One human, a full business.

And here's the honest part: they can do this. The agents will produce marketing copy, answer tickets, draft posts, and generate graphics around the clock. On paper it looks like a whole team.

But look closer at the output.

You'll find the misspelled graphics. The messaging that says one thing on the landing page and the opposite in the email sequence. The "facts" that are outdated or were never true to begin with. These aren't signs of a lazy operator — they're the exact failure modes I described earlier, now running unsupervised. Remember the randomness baked into the model, and the illusion of competence? A solo operator has removed the one thing that used to catch those failures: a human reading the output before it ships.

And it compounds, because no single agent sees the whole business.

This is the real reason it breaks down. AI has no genuine contextual awareness — it doesn't understand your situation, your intent, or the consequences of being wrong. It only interprets patterns in the text you hand it. In practice that means:

- It misses the context a human just knows — internal history, customer relationships, where the market is heading.
- It produces answers that sound right but don't fit your specific situation.
- It fails on edge cases, exactly where judgment matters more than pattern-matching.
- It treats every input as a "text problem" instead of a real-world decision.

It doesn't see the situation. It only sees the words about the situation.

Now multiply that across agents. Your marketing agent, your sales agent, and your support agent each interpret their own slice of text with no shared understanding of the business. Individually their output might be fine. Together, they drift — and the customer is the one who notices the contradictions.

So yes, one person can run a company on agents. The question is whether the result holds up under scrutiny — and at any meaningful scale, it usually doesn't.

Note: there are tools and techniques that give models more context — RAG, memory, system instructions — but it's still nowhere near what a human brings to the table.

## What not to use AI for

Let’s take legal as a more concrete example. AI handles edge cases poorly, especially when it comes to complaints and legal issues. While some models perform better than others, law is a precise and context-heavy domain.

AI systems don’t understand the situation—they generate responses based on patterns—so they can produce different outputs for the same input or miss critical nuances. That makes them fundamentally unpredictable in high-stakes scenarios.

In legal contexts, even a slightly incorrect or poorly phrased statement can have serious consequences. And because the AI isn’t accountable, the responsibility always falls entirely on you.

That’s why I would never trust AI to handle legal matters independently; at best, it’s a drafting or research tool, not a decision-maker. And there you have it: A research tool.

When it comes to legal, what you can use AI for is reviewing contracts:

- The contract mentions a payment window of maximum 30 days or shorter.
- There is no scenario mentioned where the payment window is allowed to exceed 30 days.
- The contract does not include ambiguous phrasing that could be interpreted differently under certain conditions.
- There are no conflicting clauses that override or weaken the 30‑day requirement elsewhere in the document.
- Standard enforcement, dispute resolution, and penalty clauses are present and aligned with that payment term.

In this context, AI works very well because the task is structured, the criteria are defined in advance and more importantly: You’re asking it to verify patterns, not make judgement calls.

It’s essentially acting as a high-speed checklist processor.

## What to use AI for

Every tool has its own use case. When you understand the basics of how AI models work (read above), you can start to plot it against your business and its processes.

A few cases where AI can clearly be useful:

- Contract scanning (not contract writing!)
- Clause extraction
- Consistency checks
- First-pass reviews
- Coding (more information about this specific case in my next newsletter!)

But not for:

- Legal interpretation
- Risk decisions
- Negotiation strategies
- Liability-bearing judgements

One of there more ‘beautiful’ examples I’ve encountered thus far was a judge using AI to generate a verdict. The problem was that the AI model came up with precedents that were fake. They didn’t exist!

I’m guessing that’s why Microsoft’s Co-pilot client in Windows has the following message under its prompt input:

> AI-generated content may be incorrect.

## The system problem (multiple AI agents)

Everything so far has been about a single model. The moment you start chaining them together, the problem doesn't just add up — it multiplies.

> The Marketing AI says one thing.
>
> The Sales AI says something else.
>
> The Support AI contradicts both.

Individually, their answers might be fine. Good, even. But together? Inconsistent. And in business, consistency is everything.

But the visible contradictions are the easy problem — at least you can see those. The harder one is what happens underneath, where the agents feed each other.

In a real pipeline, the output of one agent becomes the input of the next. So when an agent gets something subtly wrong — a hallucinated detail, a misread of context — the next agent doesn't question it. It treats that wrong output as ground truth and builds on top of it. The error doesn't stay contained. It travels downstream, and it grows.

Now bring back the maths from earlier. Say each agent is 90% reliable on its own — pretty good, right? Watch what happens when you chain them:

- 1 agent: 90% reliable. Manageable.
- 3 agents in a chain: 0.9 × 0.9 × 0.9 ≈ 73%. Already a 1-in-4 chance something's off by the end.
- 5 agents in a chain: 0.9⁵ ≈ 59%. Now it's basically a coin flip.

Every handoff is another roll of the dice. Reliability doesn't hold steady across a system — it compounds downward. And because each agent only sees its own slice of text (remember: no real contextual awareness, no shared understanding of the business), there's nothing holding the whole thing together. No agent sees the full picture. No agent owns the outcome.

And here's where it ties back to the illusion of competence: each individual step still looks clean. Polished output, confident tone, no errors thrown. So when the final result is wrong, good luck tracing it back — was it the marketing agent? The third handoff? Something five steps upstream? There's no stack trace. Just a confident, broken result and no clear place to point.

A human team isn't immune to this — people miscommunicate too. But people share context, ask each other questions, and someone, somewhere, owns the result. Strip all of that out and replace it with a chain of confident, isolated, non-deterministic components, and you don't get a leaner business. You get a faster way to be consistently wrong.

## Conclusion

Please don’t misunderstand me: I love AI and I think it’s a transformative and game-changing tool for finding and structuring information, and to an extent automating certain tasks and perhaps even very specific jobs, but not for deciding what that information means in the real world.

Using AI for the right tasks can enhance the productivity of people, enhance the quality of their work, broaden their experiences and knowledge, and much more. But it should be used as such: A tool to enhance, not to replace.

A quick note: everything here reflects my own personal views and experience — not those of my employer or any organization I'm affiliated with. It's my personal take, nothing more and nothing less 😉
