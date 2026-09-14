# Strategy — what the job-hunting problem actually is

> This document is the *reason* the system exists. Read it before `design.md`.
> Every technical decision has to trace back to a section here. If it cannot be
> traced back, it does not get built.

---

## 1. The premise

Companies hire people who **can do the job now**. They do not keep people on for
their potential.

The direct consequence: the application has to match the JD. Not "roughly" match
— match in the exact language they wrote the JD in.

## 2. The mistake, named

Applying above your level and hoping someone notices the talent.

It fails because it is cut at the filter, **before** anyone reaches the part
worth reading. Cut not for being weak — cut because the filter is doing exactly
its job.

But the opposite reflex is wrong too: aim lower and you are cut as
overqualified, or you get in and get stuck.

**The right target:** apply inside your own band, but as the application with
the strongest evidence in that band.

## 3. Two mechanisms — never merge them

An application passes three gates:

| Gate | Who reads | The real criterion |
|-----|--------|---------------|
| 1. ATS / keyword filter | A machine | Words that match |
| 2. A recruiter's few-second scan | A person, not reading closely | *Recognition*: is this person actually in this line of work |
| 3. The hiring manager reading properly | A person, reading closely | Evidence they can do the work |

> **Matching is the filter. Evidence is what makes a difference.**

Matching takes you from 200 people down to a group of 40. From 40 down to the 5
who get called, matching is useless — all 40 match. What decides it is **the
personal project**.

The system has to serve **both**, and never confuse one for the other.

## 4. Why a GitHub link is worth nothing

- **Nobody clicks it.** Whoever reads the CV does not clone the repo. Ever.
- **Evaluating it costs too much.** Reading a stranger's code well enough to
  judge it takes 20–30 minutes. Nobody pays that for a candidate they have not
  yet decided they like.
- **It does not distinguish.** Everyone has a GitHub, everyone has a scraper, a
  todo app, a chatbot. What everyone has carries no information.
- **It is a claim, not evidence.** "Here is code I wrote" — and? Does it run?
  What did it solve?

| | |
|---|---|
| **A project** | "I built X" — an artefact |
| **Evidence** | "Problem P, I did X, the number went from A to B, measured this way, and here is where I got it wrong" |

The **"here is where I got it wrong"** part is the part everyone leaves out, and
it is the part experienced readers trust most. Real work always has trade-offs.
A project that wins everywhere, with no scratches on it, reads as one that never
really ran.

## 5. The shape of evidence

Not a repo. **One results page**, readable in 90 seconds:

```
The problem   — one sentence, in the JD's own language
The approach  — 3-5 lines, a real mechanism, no buzzwords
The numbers   — before -> after, plus HOW IT WAS MEASURED
                (without the method, the number means nothing)
The trade-off — what was sacrificed, and why
The code      — at the foot of the page, for the 5% who want it
```

One screen. No gloss. An experienced reader finishes it knowing whether the work
was real.

## 6. The general answer for personal projects

The hard part:
- You cannot build a project per JD — it does not scale, not even running 24/7.
- You cannot spread one generic project across all of them — that is the GitHub
  link problem again.

The answer:

> **One real system + many slices taken along the JD.**

Build **one** thing, real, running. Pick something that touches many dimensions,
so that many slices can be cut and **every slice is true** — not one invented
sentence.

| If the JD is about | Cut this slice |
|---|---|
| Data engineering | multi-source ingest, dedup / entity resolution |
| Backend | the API, the lifecycle state machine, scheduling |
| Reliability | failure handling, retries, a dead source |
| ML / IR | the CV↔JD scoring engine, false-positive analysis |
| Analytics | reply rate measured by source and by score |

Three different pages, three different languages, not one sentence that lies.

## 7. This system IS that project

Look at it technically and it has: heterogeneous multi-source ingest · dedup /
entity resolution · a scoring engine · scheduling and rate limiting · a state
machine · failure handling · real measurement.

And it has what almost no portfolio has: **real results, real numbers, real
consequences.**

> "1,240 postings in 8 weeks -> dedup left 890 unique -> applied to 60 matching
> above 75% -> 9 replies -> 3 interviews. The 75% threshold is what came out of
> trying 60% and 85%."

The loop proves itself: **the thing that gets the job is the argument for
hiring.**

## 8. The presentation trap — and it is serious

- ❌ "A bot that auto-applies to jobs in bulk" -> what a hiring manager reads:
  *this person spams*. Instant step back.
- ✅ "A system that dedups and scores job postings from many sources — and why
  80% of the high-scoring matches are false positives"

Tell **the hard technical problem**, not the automation.

The consequence that comes with it: **volume with a high match is good; volume
without a match is spam**, and it destroys itself. The system has to stop this
by design, never by personal discipline.

---

## Still open

- [ ] **The real band:** which area, and how many years of real work?
- [ ] **2–3 real JDs** where the reaction is "I can genuinely do this" (not "I
      could if I stretched") — so the project is derived backwards from the JD,
      rather than built first and then fitted in somewhere.
