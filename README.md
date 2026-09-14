# jobbot

A job search that runs by itself — **the machine proposes, the person decides.**

Version **1.0**. A real macOS app that runs 24/7 in the background: it scans job
sources, scores each posting against your profile and explains the score, builds
a CV per posting out of sentences *you* wrote, and tracks every application
through to the reply.

No dependencies. No LLM. Nothing is sent anywhere on your behalf.

## Run it

```bash
python3 scripts/make_app.py && python3 scripts/install_agent.py
```

The first command builds `jobbot.app`. The second installs it as a service —
**it starts with the machine** and restarts itself after a crash.

This is a **real macOS app**, not a browser tab:

- Its own window (`NSWindow` + `WKWebView`) — no URL bar, no tabs
- An icon in the Dock, cmd-tabbable, present in Launchpad
- A `◆` icon in the menu bar: status, Open jobbot, Scan now, Quit
- **Closing the window hides it; the app keeps running** — like Discord. Only
  Quit exits for good
- It scans on a schedule, and tells you through a macOS notification (and
  Telegram, if you connect it) when something new matches

Nothing to install, no venv — **Python 3.11 or later** is all it needs.

PyObjC is **not** shipped with macOS: `/usr/bin/python3` (3.9.6) does not have
it, and that build is too old for 3.11 anyway. With PyObjC (Anaconda, or
`pip install pyobjc`) you get a real macOS window; without it the app falls back
to a Chrome `--app` window — still a window of its own, still no address bar.
WebKit is loaded at run time.

The app finds a Python for itself at startup (`scripts/find-python.sh`), so it
does not depend on the one it was built with. If your Python lives somewhere
unusual, point at it: `export JOBBOT_PYTHON=/path/to/python3`.

| Command | What it does |
|---|---|
| `open jobbot.app` | Open the app |
| `./start.command` | Double-clickable — if it is already running, it only opens the dashboard |
| `python3 run.py` | Run it directly, without the bundle |
| `python3 run.py --window` | Run in Terminal, see the log, Ctrl+C to stop |
| `python3 run.py --scan` | One scan, then exit |
| `python3 scripts/install_agent.py --status` | Is the service running? |
| `python3 scripts/install_agent.py --uninstall` | Remove the service |

Tests: `python3 tests/run_all.py` — 21 files, ~2,465 checks, and they have to be
green before anything ships.

---

## The seven founding laws

Every one of them has a test standing behind it. A law with no guard is a
sentence in a README, not a law — see `tests/test_luat.py`, which names where
each is watched.

1. **No LLM.** Anywhere. Not for scoring, not for writing, not for reading.
2. **The CV's sentences are yours.** The machine cuts and reorders what you
   wrote. It never writes a sentence about work you did.
3. **The mailbox is read-only.** IMAP, four constraints enforced in code.
4. **The machine never presses Send.** It fills the boring fields; the last
   click is yours.
5. **Secrets live only in `config/config.toml`** (chmod 600, gitignored). The
   handover package refuses to carry them, by name *and* by content.
6. **Blocked means stop.** If a site says no, the scan stops there. No evasion.
7. **Failures must speak.** A silent failure is the worst kind of failure in
   this codebase; it is the bug class most of these tests exist to catch.

## What each tab does

| Tab | Question it answers |
|---|---|
| **Home** | Is this whole thing working? The funnel, the results, the output per day, and a diagnosis when something is broken |
| **Search** | What is out there? Company boards (Greenhouse · Lever · Ashby), LinkedIn through Chrome, and job-alert mail — sieved, scored, and each score explained |
| **CV** | What will be sent, and what to write tonight to close the gap |
| **Track** | What happened to each application, rebuilt from the mailbox |
| **Profile** | Who you are, what you want, and what you will not take |

Settings (the gear at the foot of the sidebar) holds the run schedule, the
sources, the theme, Gmail, Telegram and "start over".

## Directory map

```
docs/                 The documents. Decisions live here, not in anyone's head.
config/               config.example.toml -> copy to config.toml (gitignored)
src/jobbot/
  profile/      M0     The user profile: who they are, what they want, what they refuse
  core/         M1     Data types, the SQLite store, the 4 layers, cache, journal, scheduler
  ingest/       M2     Pulling postings in. One file per source.
  dedup/        M3     Grouping duplicate postings
  dashboard/    M4     The web layer — server, views, live SSE, CSS, one small JS file
    layout.py          The shared frame: nav, stage bar, cards, badges
    views/             One file per page
  scoring/      M5     Scoring the CV against a JD, with an explanation
  cv/           M7     Building a CV per JD, and measuring the gap
  apply/        M6     Filling the application form  [the last click is yours]
  track/        M5-6   Applications, mail outcomes, the silence threshold
  browser/             Driving Chrome for the sources with no API
tests/                One file per area. 21 files.
scripts/              Hand-run commands and one-off jobs
data/                 The DB, the cache and the Chrome profile. NEVER committed.
```

Every subpackage of `src/jobbot/` has an `__init__.py` saying **what belongs in
it and what does not**. Read that line before adding a file. If you cannot tell
where a new file belongs, you do not yet know what it does.

`notify/`, `outreach/` and `stats/` are roadmap placeholders: a docstring each,
imported by nothing.

## Rules that keep it clean

- One data source = one file in `ingest/`. Never two sources in one file.
- No business logic in `dashboard/`. It only draws.
- `core/` must not know what Greenhouse or LinkedIn is.
- Experiments and one-off jobs go in `scripts/`, never loose in the root.
- Write decisions down in `docs/`, not in a chat log.
- Tick a module off in `roadmap.md` only when it truly meets its "Done when".

## Read in this order

| | File | What it holds |
|---|---|---|
| 1 | [docs/strategy.md](docs/strategy.md) | *Why.* What the job-hunting problem actually is. Read this first. |
| 2 | [docs/design.md](docs/design.md) | *How.* The proposal loop, the safety axis, caching, the stack. |
| 3 | [docs/roadmap.md](docs/roadmap.md) | *In what order.* Every module with its own "Done when". |
