---
number: 3
title: Use AI to learn, but don't let it be your teacher
date: 2026-07-20
slug: use-ai-to-learn
linkedin_url: https://www.linkedin.com/pulse/use-ai-learn-dont-let-your-teacher-jeff-wouters-pvvae
description: AI answers questions. Learning requires asking the right ones. How to use it to build understanding instead of quietly skipping past it.
---

I've spent the last two articles on where AI fits and where it doesn't, as a business tool and as a coding tool. This one is more personal, because it's about you (and me) using AI to actually learn something.

And I'll start with the line this whole edition hangs on: AI answers questions. Learning requires asking the right ones.

## Why AI feels like a great teacher

On the surface, AI looks like the perfect teacher. It never tires of your questions. It explains anything, instantly, in clean and patient language. Ask it to go simpler and it goes simpler. Ask again and it tries a different angle. No judgement, no waiting, available at 2am. If you'd sat down to design a tutor from scratch, it might look a lot like this.

These models were trained on an enormous pile of human explanation. Documentation, tutorials, textbooks, Q&A threads, endless "explain like I'm five" posts. Explaining things is one of the most common tasks in the whole training set. But here's the tension sitting underneath all of it: AI doesn't guide your learning, it responds to your input. Those are very different things.

A real teacher steers. They decide what you should look at next, notice when you've skipped something important, and drag you back to it. AI doesn't steer. It reacts. It answers the question you asked, at the level you asked it, and then sits there waiting for the next one. Which means the quality of your learning is capped by the quality of your questions. If you don't know what to ask, it isn't going to tell you.

## The missing piece: it doesn't understand you

Picture a good teacher in a room with you. They watch your face and they catch the exact moment your eyes glaze over, they hear the hesitation in a question and realize you've misunderstood something three steps back, they notice when you're bored and push harder, and when you're drowning and ease off. Half of good teaching is reading the student, not reciting the material.

Now look at what AI has to work with. It sees your question. That's the whole of it. It can't see your confusion. It has no way of knowing you've quietly misunderstood the premise of your own question, so it will cheerfully answer the wrong question you didn't realize you were asking. The model has no real contextual awareness. It doesn't see you or your confusion. It just sees the words about your problem.

Which gives us the sharpest version of the point: the model doesn't know what you don't know. And in learning, that gap is the whole game.

## The illusion of learning

This one is the illusion of competence wearing a different hat.

Understanding feels instant with AI, and that's the trap, because real understanding almost never is. You get a smooth, clean answer that sounds right. What you don't get is the slower, gnarlier process of an idea taking root, the part that would leave you able to judge whether the answer is right in the first place. The model can hand you the feeling of learning with none of the substance. And because it fails convincingly, you won't notice the gap until you go to use the thing you thought you'd learned.

## The learning trap

AI removes friction, but friction isn't always the enemy. The being stuck, the working through it, the hitting a wall and clawing your way around it is the process that actually builds understanding. That's the part your brain keeps.

AI lets you skip all of it. You get the answer before you've done any of the wrestling. You read it, you move on, faster than ever, and it feels productive as anything. But you've quietly traded the thing that makes learning stick for the feeling of actually having learned something new.

Here's the test I keep coming back to. You read the explanation and it makes total sense. Could you reproduce it an hour later or explain it to someone else? Can you solve the next problem without going back to ask? If reading it felt effortless but reproducing it is impossible, you didn't learn it.

## Where AI works well as a learning tool

So let's be concrete. AI is genuinely strong at:

- Explanations: taking a concept and laying it out clearly
- Alternative perspectives: the same idea from a new angle when the first one didn't land
- Breaking down concepts: splitting something big into pieces you can actually hold
- Generating examples: as many worked examples as you care to ask for
- Answering follow-up questions: the endless "but why?" chain, without ever getting impatient

The pattern: AI is strong at expanding your understanding once you're already pointed in a sensible direction. It's a phenomenal amplifier for exploration.

## Where it breaks down

And the other column. AI is weak at:

- Identifying your misunderstandings: it can't see the gap that you can't see either
- Building deep intuition: it can hand you the explanation, not the wrestling that turns into instinct
- Ensuring correctness: a confident explanation is not a verified one
- Guiding a long-term path: it reacts to the question in front of it, with no map of where you should go next

Same core issue as always. It explains, but it doesn't teach in the full sense, because teaching means knowing the student and steering the journey, and the model does neither.

## How to actually use AI to learn

None of this means don't use it. It means use it on purpose. The tool is strong, the default way most people reach for it is weak. Here's how to flip that.

Move from "what is it?" to "why does it work?" The first hands you a fact to copy down. The second forces the model to show its reasoning, which is the part you actually needed. Answers you can look up any time. Understanding you have to build.

### Force depth and variation

Don't take the first explanation and run. Push it:

- "Explain this in three different ways."
- "Give me a real-world analogy."
- "What are the common mistakes people make here?"
- "Where does this break down?"

Variation is how you find out whether you actually understand the thing or just got comfortable with one particular way of phrasing it.

### Use it as a reviewer, not a teacher

Start saying "here's what I tried, what's wrong with it?"

Bring your own attempt: your code, your explanation, your reasoning, however rough. Let the model react to your thinking instead of replacing your thinking for you. Now you're getting feedback on something real rather than passively sitting through a lecture. And learning happens in the feedback, not the consumption.

### Use it to test yourself

Flip the model from answer-machine to examiner. Ask it to generate questions on the topic. Ask for the edge cases you probably missed. Ask for the pros and cons, and let it explain. Ask it to throw a scenario at you and then check your answer against it. Discuss the answers and challenge the AI on what it tells you but instruct the AI to also do this with you. That's the shift from passive to active, from reading about the thing to being put on the spot about it. Passive feels nice. Active is where it actually sticks.

### Verify when it matters

If correctness matters, don't trust a single explanation. The model can be fluent and wrong in the very same breath. For idle curiosity, fine, let it ride. For something you're about to build on, act on, or teach to someone else, check it against a second source. Being confident is not the same as being right.

So why is any of this a good idea, when the warning I keep coming back to is that AI fails convincingly? Fair question, and it's the right one to end on. The answer is that none of this asks you to trust it. The danger I keep flagging is AI as the final word, unchecked, with nobody able to catch it. Learning flips that around: you are the one becoming able to catch it. A critique is easier to check than an answer is to produce, so when it says "this is wrong," that's a lead you go and verify, not a verdict you swallow. And you keep a referee that doesn't care how confident it sounded: the compiler, the tests, the docs, a second source. Can it be trusted to overturn a correct answer? No. If you're right and it confidently says otherwise, and you can't yet tell, it will talk you out of it, and that is exactly when you know the least. So, it never gets the final word. It raises the question; you and your referee settle it.

## Example: learning to code

Let's make it concrete with coding.

The good kind of use, the kind that builds a developer: paste the error you're stuck on and ask why it happened. Ask for two other ways to approach the problem and what each one costs you. Have it break down the concept you keep tripping over. Every one of those leaves you more capable than you were before.

The bad kind, the kind that quietly hollows you out: "write the whole thing for me." It'll work. The code will run. And you'll have learned precisely nothing, because working code is not a learned skill. Do it enough and you end up with a project full of solutions you can't reproduce or debug on your own. That's not a developer getting better. That's a dependency getting deeper.

## Conclusion

AI can be a genuinely powerful learning tool. Probably the most powerful one most of us have ever had our hands on. But only if you use it correctly, and "correctly" happens to be the opposite of how it's easiest to use.

AI doesn't replace learning. It amplifies how you already learn. Hand it good questions, your own attempts, and a habit of checking, and it will accelerate you enormously. Hand it "just give me the answer," and it will accelerate that too, straight past the point where learning happens. That's the part worth sitting with. AI scales whatever you bring to it.

It’s a tool to enhance, so let the thing it's enhancing be you.

A quick note: everything here reflects my own personal views and experience — not those of my employer or any organization I'm affiliated with. It's my personal take, nothing more and nothing less 😉
