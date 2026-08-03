---
number: 2
title: Why AI Works So Well for Coding, and Where It Actually Fits
date: 2026-07-06
slug: why-ai-works-for-coding
cover: cover.jpg
cover_alt: A cartoon cat squeezed into a cardboard box slightly too small for it, looking unimpressed.
linkedin_url: https://www.linkedin.com/pulse/why-ai-works-so-well-coding-where-actually-fits-jeff-wouters-u8hne
description: Coding is not the exception to AI's limits. It is the one place those limits hurt least, because code tells you loudly when it is wrong.
---

In my previous newsletter edition I made a fairly blunt argument: AI doesn't think, it predicts. It samples plausible-sounding text, it's inconsistent by nature, and it fails convincingly rather than loudly. That's why I don't trust it with legal interpretation, risk decisions, or anything where judgment matters more than pattern-matching.

So here's the obvious question I promised to answer. If all of that is true, why does coding feel like the exception?

Because it kind of is. And the reason isn't the one most people assume.

## Coding feels different, and there's a reason

Ask AI to write you a marketing strategy and you get a confident answer you can't fully trust. Ask it to write a function that parses a date string, and… it usually just works. Same model, same token-prediction engine underneath, and yet the reliability is night and day.

The easy conclusion is "coding must be the thing AI is genuinely good at." I think that's backwards. AI isn't good at coding because it understands code. It's good at coding because coding happens to fit, almost perfectly, the way these models actually work. Every one of the limitations I keep banging on about is still there. Coding is just the one place where those limitations hurt the least.

Let me walk through why.

### Code is predictable by nature

Human language is ambiguous. A single sentence can carry three different meanings depending on tone, context, and who's reading it. Code doesn't get to do that. It has strict syntax, defined keywords, and rules that don't bend. `if` means `if`. A missing semicolon isn't a stylistic choice you get to defend in review.

The model, remember, is a next-token predictor. The less ambiguous the "next token" is, the better it does. Language hands it a wide, fuzzy field of plausible options. Code narrows that field hard, because a lot of the time there's genuinely only one correct next token. You've basically handed the prediction engine the easiest version of its own job.

### The entire industry became training data

Think about what these models were trained on. Decades of open source. Every framework's documentation. Millions of Stack Overflow answers, GitHub more or less in its entirety, plus the endless tutorials, blog posts, code reviews and bug reports on top.

Software engineering might be the most thoroughly documented human activity on the internet. And it's documented in exactly the shape the model learns best from: here's a problem, here's the working solution, here's why it works. We didn't just give it examples. We handed it the answer key.

### Most code is variations of the same patterns

Here's the slightly uncomfortable truth most of us already know. We don't write that much genuinely original code. We wire up an API client. We loop over a collection. We validate some input. We map one shape of data onto another. Every one of us has written the same try/catch a few hundred times.

That's not an insult, by the way. Reuse and composition are good engineering. But it does mean most of what we produce is a variation on a pattern that already exists a million times over in the training data. And "give me a variation on a well-established pattern" is about the most on-target request you can hand one of these models.

### Code tells you when it's wrong

This is the big one. Honestly, if you take one thing from this piece, take this.

The real danger with AI is that it fails silently. A wrong business decision looks exactly like a right one: polished, confident, no red flags anywhere. There's no stack trace for a bad marketing call. You find out it was wrong three months later, if you ever find out at all.

Code is the opposite. Code has a feedback loop baked into it. The compiler rejects it. The linter starts complaining. The test suite goes red. The thing falls over at runtime and hands you an actual error message. The illusion of competence, which is the model's most dangerous trait everywhere else, gets punctured almost immediately here, because the code has to actually run.

For once the failures are loud. Something red, something you can see. And that one property changes almost everything about how safely you can lean on it.

### And that's how it kept getting better

That same property, code being checkable, did something bigger than help you catch mistakes. It's a large part of why these models improved at coding faster than at almost anything else they do.

To make a model better at something, you have to be able to tell it when it got something right and when it got it wrong. For most work that's hard and subjective. What's a "good" marketing email, or a "good" legal argument? Ask ten experts and you'll get ten answers, none of which compile. Code is different. Does it run? Do the tests pass? Those are yes/no questions a machine can grade millions of times over without tiring or having an opinion. So the model could be trained against a real answer key: reward the code that works, penalise the code that doesn't, and repeat at a scale no human review could ever touch. It was effectively taught what "good" and "bad" code look like by something that could check every single time, and that objective, automatic grader is a big reason coding ability raced ahead while the fuzzier, unverifiable work stayed stuck.

### "Almost correct" is still extremely useful

With something like legal work, being wrong 10% of the time is a liability nightmare at scale. Twenty wrong words in a 200-word paragraph, and any one of them could be the expensive one.

Coding flips that math on its head. If AI gets you 70% of the way to a working function, that isn't a 30% failure. It's a 70% head start. You take the scaffolding, spot the gaps (the compiler is right there helping you spot them), and finish the job. "Almost correct" in a contract is dangerous. "Almost correct" in code is just a normal Tuesday, and most days it's genuinely useful.

### Most problems are smaller than they look

A lot of programming, when you actually watch yourself do it, is a long series of small, local, self-contained problems. Parse this. Transform that. Sort the list. Format the output. These are the bite-sized, well-bounded tasks the model is good at, precisely because none of them ask it to hold the whole system in its head at once. The trouble starts when the problem isn't local. Hold that thought, because that's where this whole thing turns.

## What this really changes: from writing code to evaluating it

Put all of that together and something quietly shifts under your feet. The value isn't in writing the code anymore. It's in knowing whether the code is right. The model can produce the function. It can produce ten versions of the function before you've finished your coffee. What it can't do is tell you which one belongs in your system, handles your edge cases, and won't quietly fall over in production six weeks from now. That judgment is the actual job now.

## Who this actually works well for

The same tool lands completely differently depending on whose hands it's in.

### Experienced developers: faster, not replaced

If you already know what good looks like, AI is a force multiplier. You read its output the way you'd read a junior's pull request. You catch the mistakes, refine it, wire it in properly, and move on. You're not trusting it, you're supervising it. And because you can actually evaluate the result, you get the speed without inheriting the risk.

### Generalists: filling the gaps

If you work across a lot of tools and languages, AI smooths over the friction. Less time lost to unfamiliar syntax, less time digging for the magic incantation in a language you touch twice a year. It won't make you an expert in everything, but it clears out a lot of the small stumbles that used to slow you to a crawl.

### Prototypers: from idea to code instantly

If your goal is to get from idea to working demo as fast as humanly possible, this is where AI really shines. Iteration speed goes through the roof. You can try five approaches in the time it used to take to wire up one. And for a prototype that's exactly the right trade, because the goal is to learn something, not to ship something bulletproof.

### Beginners: learning tool or crutch

Here's where I get cautious. For a beginner, AI is genuinely powerful and quietly dangerous at the same time. It'll hand you working code before you have any idea why it works. Point it at "why did that actually fix it?" and it's a phenomenal tutor. Use it to skip the understanding entirely and you're building a dependency on a tool that fails convincingly. You end up unable to tell when it's wrong, which is the one skill that turns out to matter most.

### Specialists: where the model runs out of data

Out at the deep end, the model starts to thin out. Novel problems, deep systems work, the genuinely weird edge cases: the places where there isn't much training data, because not many people have solved this before. That's exactly where pattern-matching has nothing to match against, and the confident-but-wrong behaviour comes creeping back. The further you get from the well-trodden path, the less the model has to offer you.

## What actually matters now

If writing code isn't the bottleneck anymore, the questions worth asking are about you, not the tool. Four of them.

**Can you describe the problem clearly?** The model is only ever as good as the problem you hand it. Vague in, vague out. Thinking clearly about what you actually need is now half the work.

**Can you tell when something is wrong?** This is the successor to the illusion of competence. The output looks finished. Whether it is finished is your call, and you can only make that call if you know what wrong looks like.

**Can you tell a good solution from a bad one?** Working isn't the same as good. Plenty of AI-generated code runs perfectly and is still a maintenance liability waiting to happen. Spotting that difference is judgment, not pattern-matching.

**Do you understand the system beyond the code?** The model sees the snippet. It doesn't see your architecture, your constraints, your history, or the three other services this quietly touches. All of that context lives with you.

None of those are really coding skills. They're engineering skills. The typing got automated. The thinking didn't.

## Where AI works well in coding

Let's get concrete. AI is genuinely strong at:

- Boilerplate and scaffolding: the repetitive setup nobody enjoys writing
- Writing tests: structured, pattern-heavy, and easy to verify
- Refactoring: reshaping code that already works into something cleaner
- Explaining code: a fast way into an unfamiliar codebase
- Translating between languages: porting a known solution from one syntax to another

See the shape of it? Structured, repeatable, verifiable. It's the same profile as checking a contract against a fixed checklist. You're asking it to work inside known patterns rather than invent something new, and you can check the result when it's done.

## Where it breaks down

And here's the other column. AI struggles badly with:

- Architecture decisions: trade-offs that hinge on where the business is heading
- Cross-system reasoning: problems that span services, teams, and boundaries
- Long-term maintainability: choices whose real cost only shows up months later
- Edge cases: the rare, weird, high-stakes paths that judgment exists for in the first place

Same core issue every time: the moment the problem stops being local and turns into judgment, the model runs out of road.

## The same problem, just in a different form

All of the above leads to the following. This is the part that I really want to land.

Nothing about the model actually changed between "don't use it for legal" and "it's great for coding." It's the same randomness, the same illusion of competence, the same engine sampling plausible tokens with no idea whether any of them are true. Coding didn't fix a single bit of that. It just happens to come with guardrails that business decisions don't have: strict syntax, a mountain of training data, and above all a feedback loop that makes the failures loud instead of silent. Strip those guardrails away, push it toward architecture and edge cases and cross-system judgment, and the exact same problems come marching straight back.

The reliability was never in the model. It was in the environment around it.

## Conclusion

So use it. For scaffolding, tests, refactoring, translation, and getting yourself unstuck, it's a real multiplier. Just keep doing the part that was always the actual work: deciding what to build, and knowing whether what came back is any good.

A tool to enhance, not to replace. Same as it ever was. Just this time with a stack trace.

A quick note: everything here reflects my own personal views and experience — not those of my employer or any organization I'm affiliated with. It's my personal take, nothing more and nothing less 😉
