# System design

> Read `strategy.md` first. This file says only *how*, never *why*.

---

## 1. The central principle — one loop and only one

Every module does the same shape of work:

```
module  ->  proposal  ->  queue  ->  a person clicks Yes/No  ->  execute  ->  record
```

The job-finding module produces proposals. The CV module produces proposals. The
mail module produces proposals. **All of them the same type of object:
`Proposal`.**

The consequences:

- The dashboard only has to know how to draw **one** thing.
- The Yes/No gate is written **once**.
- The statistics count **one** kind.
- **Adding a new module changes nothing in the core.**

This is why the architecture stays clean. It reduces to one loop.

> **The law:** a module may not cause an outside effect on its own. A module may
> only *propose*. Executing is the core's job, after a Yes.

## 2. The safety axis — automatic vs. Yes/No

Not every module is equal. The line follows **reversibility**:

| Kind | Modules | Why |
|---|---|---|
| **Free to run 24/7** | store, ingest, dedup, scoring, stats, dashboard | They only read and compute. Wrong output can be deleted and recomputed. |
| **Yes/No required** | cv (publishing), mail (sending), outreach (posting, connecting) | It goes outside. It cannot be taken back. |

This is not a side feature — **it is the safety axis of the whole system.**
Every irreversible action passes through one human click.

## 3. The rhythm — where 24/7 belongs

Running slowly but continuously still gets the work done. Put it in the wrong
place, though, and it breaks:

- **Happily 24/7:** public job-board APIs, reading mail, scoring, statistics,
  producing content.
- **Not 24/7:** sites with no public API (LinkedIn is the example). No real
  person is online at 3am every night, seven days a week — *that rhythm is
  itself the detection signal*, and going slower does not save it.

The handling: run in a few short, human-shaped windows, with breaks and with
empty days. The heavy work was never there anyway.

### The sources — the UK market plus global

The user is in the **UK**, aiming at **UK + global**. Verified in practice:

| Source | Key needed | Note |
|---|---|---|
| `boards-api.greenhouse.io` | No | Per company. Tried: `monzo`, `wise` both fine. |
| `api.lever.co` | No | Per company. |
| `api.ashbyhq.com` | No | Per company. |
| `reed.co.uk/api` | **Yes** (free) | A large UK board. Returns 401 without a key. |
| `jobs.service.gov.uk` | — | The UK government's board (findAJob moved here). |

**Dropped** (2026-09-07, after measuring on real data):

| Source | Fetched | Usable | Why it was dropped |
|---|---|---|---|
| `arbeitnow.com` | 2,506 | **2** | A European board — the wrong market. |
| `remotive.com` | 18 | **0** | Global remote — the wrong market. |
| `efinancialcareers` | 66 | 28 | 67% of its postings are agencies (LinkedIn: 24%). |

A low ratio is NOT on its own a reason to drop a source: greenhouse also yields
about 2%, because the whole board is fetched before filtering — but those are
DIRECT employers and it costs nothing but HTTP. The two above were dropped
because they serve an entirely different market.

Sources with no public API (LinkedIn, Otta, Indeed) go through Chrome, running
in human-shaped windows — never 24/7.

## 4. The data architecture

```
raw_posting   verbatim + the original body    NEVER edited
      ↓  derive()  — one transaction, recomputing only what went stale
posting       normalised + judged             fully recomputable from raw
```

Three required properties:

**Recomputable.** `scripts/rebuild.py` rebuilds the whole derived layer from
raw. Without it, one bug in `strip_html` is permanent damage — and it has been
wrong twice, while an expired LinkedIn posting cannot be fetched again.

**Versioned.** Every judgement records which profile version produced it
(`judged_profile`) and which rule version (`judged_rules`, `scored_rules`).
Change the profile or edit `core/versions.py` and the old postings mark
themselves "needs recomputing".

**One transaction.** Filtering, grouping and scoring sit inside one `derive()`.
The web layer reading midway sees the OLD state whole, never a half-finished one.

**One definition.** `core/postings.FIELD_MAP` is the only place linking the
`Posting` type to the table's columns. A test breaks if the two drift apart.

**A broken source must look different from a good one.** Every read returns
`Health(attempted, failed)`; more than 30% failures marks the source broken even
if a few postings did come back.

## 5. Data and cache

Four layers, kept apart, **never mixed**:

| Layer | What it holds | Deletable |
|---|---|---|
| `raw` | What was fetched, verbatim, plus source and timestamp | Yes — refetch it |
| `derived` | Dedup results, scores, analysis | Yes — recompute from `raw` |
| `state` | The application lifecycle, the Yes/No decisions | **No.** This is real data. |
| `audit` | What was done, when, and how it turned out | **No.** Every statistic comes from here. |

Why the cache is required rather than an optimisation:

1. Never fetch the same posting twice — the sources rate-limit.
2. Never score the same JD twice — it costs money and time.
3. Dedup needs history to compare against.
4. A 24/7 process **has to be restartable with nothing lost**.

## 6. Language

The whole project is in **English**: the interface, the comments, the docstrings
and these documents.

The interface was always English — the market is UK/global, and both CVs and JDs
are written in English. The comments and documents were Vietnamese until v1, and
were translated in full for the same reason the question was left open here for
so long: if this repo is ever read as a portfolio, a reader in the UK cannot read
a Vietnamese comment, and an unreadable explanation is the same as no
explanation.

## 7. The shape of the app

**A real macOS app, not a browser tab.** The same way Discord, Slack and VS Code
do it: the content is HTML, but it sits inside a native `NSWindow` +
`WKWebView`.

One process, three parts:

| Thread | Job | Note |
|---|---|---|
| main | The Cocoa event loop and the window | It has to be the main thread |
| background | The web server | The content for the window, on localhost |
| background | The scheduler | Scans on a schedule |

The port is **handed out by the operating system**, so it changes from run to
run; the live address is written to `data/dang-chay.txt` (see
`core/dia_chi.py`), which is how `start.command` finds a running instance
instead of booting a second one on top of the same SQLite file.

`setActivationPolicy(Regular)` -> a Dock icon, and cmd-tab works.
Confirmed: `lsappinfo` reports `ApplicationType="Foreground"`, and
`CGWindowListCopyWindowInfo` shows the window `'jobbot' 1180x806 layer=0`
alongside the status item `'Item-0' layer=25`.

Discord-shaped behaviour: `windowShouldClose:` returns `False` and calls
`orderOut:` — closing the window hides it and the app keeps running.
`applicationShouldTerminateAfterLastWindowClosed:` is `False` too. Clicking the
Dock icon -> `applicationShouldHandleReopen:` brings the window back.

WebKit has no prebuilt bindings in Anaconda's PyObjC, so it is loaded
dynamically with `objc.loadBundle` -> still nothing extra to install.

launchd keeps it alive: `KeepAlive={SuccessfulExit: false}` — restart after a
crash, but stay down after Quit. With `KeepAlive=true`, every Quit would be
followed by an immediate restart.

## 8. The interface

A **desktop app** layout, not a web page:

- **A fixed left sidebar** (216px) running to the top of the window. Settings
  sits at its foot.
- A transparent title bar with the text hidden (`FullSizeContentView`), leaving
  only the three traffic-light buttons floating on the ground. The CSS reserves
  `--top`.
- A **status bar along the bottom of the app** carrying the state that belongs
  to the whole app, not to one tab — always visible, with no page to open.
- **Home = the situation**, not a wall of numbers. The order is: *what needs you*
  -> *what the machine is doing* -> *the numbers* -> *what was done*. Someone
  opening the app does not ask "how many postings are there", they ask "is there
  anything for me".

The palette — a committed dark theme, **one tone**, not following the system
theme:

| Variable | Value | Role |
|---|---|---|
| `--bg` | `#0D0D0D` | The MAIN area's ground: black |
| `--side` | `#1A1A1A` | The chrome: grey, lighter than main |
| `--panel` | `#212121` | Cards, lifting clear of the main ground |
| `--ink` | `#D4D4D4` | The main text. Softer than white, less glare |
| `--acc` | `#55C98D` | A soft green — neither neon nor washed out |

Every colour is a variable, so changing the tone means editing one `:root`
block. The Settings panel offers a few accent themes on top of it, and a test
proves each one still meets the 4.5:1 contrast bar. The native window's
background is set to match `--bg` so nothing flashes white on open.

## 9. The stack

| Choice | Why |
|---|---|
| Python | The real work is parsing, scoring and calling APIs |
| SQLite | One file. No server. Nothing lost on restart. Far more than enough for one user. |
| A small web dashboard | Watch it live, click Yes/No |

**Not used:** Docker, Postgres, a message queue, microservices.
Adding any of them costs maintenance and solves nothing at the scale of one
person.

## 10. Decisions settled

- [x] One `Proposal` loop for every module
- [x] Every irreversible action passes the Yes/No gate
- [x] Python + SQLite + a small dashboard
- [x] LinkedIn is not the centre — it is one source among several
- [x] Nothing is built without a test to match (see `roadmap.md`)
- [x] The whole project is written in English (see §6)

## 11. Dropped, with a reason

**Checking the gov.uk sponsor register** — the user is on a Graduate visa, so
there is no need to filter by which companies may sponsor. Dropped from step 1.

The data is still there if it has to come back:
`gov.uk/government/publications/register-of-licensed-sponsors-workers`, a CSV of
143,082 organisations, updated daily. Worth switching back on when the Graduate
visa has about 9 months left — at that point a company that cannot sponsor is a
company that cannot keep them.

## 12. Still open

- [ ] The scoring engine: pure keyword/BM25, embeddings, or something else —
      decided once there is real data at M5. Not an LLM: founding law 1.
- [ ] Which route mail goes out by
