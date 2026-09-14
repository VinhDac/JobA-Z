# Running on Windows

## What it needs

| | |
|---|---|
| **Python 3.11+** | required — the app uses `tomllib`, which only exists from 3.11. Download it from python.org, and **tick "Add python.exe to PATH"** during the install. |
| **Google Chrome** | required — it is both the window shell and the thing that reads LinkedIn. Edge and Brave work too (all Chromium). |

No Python packages. No venv. No `pip install`.

## Running it

Double-click **`run.bat`** — it opens the app in its own window, with no address
bar.

To see the log and stop with Ctrl+C, use **`run-console.bat`**.

Or from a terminal:

```
py -3 run.py             the app window
py -3 run.py --window    run in the terminal, open a browser
py -3 run.py --scan      one scan, then exit
```

## Moving over from a Mac

Copy **the whole project folder**, with two exceptions:

```
data/jobbot.db        <- MUST be copied. Every posting, score, profile and journal entry.
data/chrome-profile/  <- DO NOT copy. Large, regenerates itself, and easily corrupted by copying.
data/chrome-ui/       <- DO NOT copy. Regenerates itself.
```

`data/` is in `.gitignore`, so a `git clone` will **not** bring the DB — copy
`data/jobbot.db` by hand.

Nothing depends on an absolute path: everything uses `pathlib`, and the data
directory is derived from where the repo sits. Put the folder anywhere.

To keep the data somewhere else (on another drive, say):

```
set JOBBOT_DATA_DIR=D:\jobbot-data
py -3 run.py
```

## How it differs from the macOS build

| | macOS | Windows |
|---|---|---|
| The app window | `NSWindow` + `WKWebView`, a Dock icon, a menu-bar icon | a **Chrome `--app`** window — no tabs, no address bar, its own taskbar icon |
| Notifications | `osascript` | a PowerShell toast (WinRT) — **not yet tried on a real Windows machine** |
| Reading a CV from PDF | the system's PDFKit — it reads embedded fonts too | the standard library — **plain-text PDFs only** |
| Starting with the machine | `scripts/install_agent.py` (launchd) | **not built** |

### PDF: the real weak spot

The standard-library PDF reader cannot read a PDF that uses an **embedded font
with its own encoding** — LaTeX, Canva and InDesign all export that way. Given
one, the app **says so and asks you to paste the text** rather than pushing
garbage characters into the profile.

The way round it: open the PDF, `Ctrl+A`, `Ctrl+C`, and paste into the "paste"
box on the Import CV page. The result is identical.

## The Chrome `--app` shell — what it is

Chrome opened in `--app=<url>` mode: a window standing on its own, with **no
tabs and no address bar**, its own taskbar entry and its own Alt+Tab slot. Not a
true native window, but the closest thing that needs no package installed — and
installing nothing is this app's whole principle.

The interface window uses **its own Chrome profile** (`data/chrome-ui`), kept
apart from the scraping profile (`data/chrome-profile`). Share one profile and
closing the window you are reading kills the tab the machine is driving.

## Where to look when it breaks

```
py -3 run.py --window
```

The log prints straight to the terminal. The line `shell   ->` says which shell
is in use.

Inside the app, every background job writes to the **Journal** — one strip per
tab, with Home gathering them all. A broken source shows as a warning inside its
own tab.

Chrome not found -> the error names every place that was searched. Install
Chrome in the default location, or add `chrome.exe` to `PATH`.

## Not built yet

- **Starting with the machine.** macOS has `scripts/install_agent.py` (launchd).
  On Windows it would be Task Scheduler or a shortcut in the Startup folder —
  not written.
- **Packaging into an `.exe`.** `scripts/make_app.py` builds a macOS `.app` only.
- **Windows notifications have never been run on a real machine.** They were
  written from the WinRT documentation. If they fail, `send()` returns `False`
  and the scheduler writes `notify_failed` into the journal — not silent, but
  not proven either.
