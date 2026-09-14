# Roadmap — 6 steps, following the brief exactly

The brief:

```
24/7  find matching jobs
      -> tailor the CV to each JD's wording
      -> build a personal project proving the match
      -> send it (auto-clicking through Chrome)
      -> track: what went out, to whom, when
      -> remind me to check the mailbox
```

It does not need to be fast. It needs to **replace a person**. It has to cache,
because the work runs over weeks.

**The law:** do not move to the next step until the previous one meets its "Done
when". A "Done when" has to be visible or runnable — never "the code is written".

Status: ` ` not started · `~` in progress · `x` done

---

## Done first

| | Work | Result |
|---|---|---|
|x| **The user profile** | 5 sections · 35 questions · stored in SQLite with versions |
|x| **The whole interface** | every page clickable, against mock data |

The mock layer was **the contract**: connecting the backend meant replacing a
function's insides while keeping the shape of what it returned. No page had to
change a line. It has since been removed — every page now reads real data.

---

## Step 1 — FIND   *(done)*

Pull real postings in, group the duplicates, cache everything.

| | Work | Directory |
|---|---|---|
|x| Store + a 4-layer cache: raw / posting / source_run / audit | `core/` |
|x| Greenhouse ×14 · Lever ×3 · Ashby ×4 | `ingest/` |
|x| Filter by the profile, ALWAYS recording why something was dropped | `ingest/filter.py` |
|x| Group duplicates by a company + title fingerprint | `dedup/group.py` |
|x| Wire the pages to real data | `dashboard/live.py` |
|x| **Chrome, driven** — a hand-written WebSocket + CDP client | `browser/` |
|x| **eFinancialCareers** — London's largest finance board | `ingest/web/` |

**The run on 2026-09-04:**

```
2,910 real postings  ->  filtered to 24  ->  grouped into 20 unique jobs
```

Among them: Jane Street Quantitative Researcher · Point72 Academy 2026
Investment Analyst Program · Zopa 2027 Graduate Analyst · Man Group Quantitative
Developer AHL · Squarepoint Junior Credit Research Analyst · GSA · Winton ·
Quadrature · IMC. All in London, all in the graduate/junior band.

### Chrome — added once the direction was clear

The bottleneck is on the employer's side: they take **a week** to reply. A
machine a hundred times faster shortens that by not one day. So the right budget
per posting is **hours of machine time**, not seconds — and that is what makes
deep reading possible.

| | |
|---|---|
| `browser/ws.py` | A WebSocket client, ~120 lines, standard library. Nothing installed |
| `browser/chrome.py` | ITS OWN Chrome, its own profile, on port 9333 |
| `browser/cdp.py` | Open a page, wait, run JS, scroll, click |
| `ingest/web/` | One file per site, each returning the same `Posting` type |

**Headed, not headless.** Headless is blocked by Cloudflare (`Just a moment…`,
`403`). An ordinary Chrome gets in normally — this is using a real browser, not
an evasion technique.

**Two safety laws, each with a test behind it:**

1. Cookie banners: **always press Reject, never Accept.** The system has no
   authority to agree to terms on the user's behalf.
2. A page returning a bot challenge is **recorded and skipped** — that page is
   saying no to a machine, and the answer is not to argue.

### Straight to the employer, past the middleman

Middleman boards have a problem: **19 of the 28 postings taken from
eFinancialCareers belonged to agencies**, not employers. They rewrite the JD,
hide the real company name, and applying through them puts the application
through one more filter.

| | |
|---|---|
| `ingest/web/agency.py` | Recognising an agency posting — the firm's name plus the JD's wording |
| `ingest/web/careers.py` | Finding a company's careers page and verifying it is the real employer |
| `ingest/web/companies.py` | The target-company table, which **grows by itself** |
| `config/companies.toml` | 55 seed companies: funds, asset managers, UK fintech |

**Self-expanding:** on every scan, the real employers seen in postings are added
to the table and their ATS is worked out. The hand-typed `boards.toml` is now
only a seed.

**Result:** 24 of 65 companies resolved to an ATS — adding Qube Research (197
postings), Ebury (173), Jump Trading (109), Schonfeld (67), Thought Machine
(41), Quantexa (30).

```
matching jobs   20  ->  68        (49 direct · 19 through an agency)
```

**Two real bugs fixed:**

1. `norm_company` stripped `"Group"` and `"Capital"` too — right for matching a
   name, wrong for guessing a slug. *"Man Group"* became `man`, losing
   `mangroup`.
2. Slug guessing caught another company's board: *"London Stock Exchange Group"*
   -> slug `london`. It now verifies against the company name the board declares
   for itself.

**The earlier result:** eFinancialCareers gave **66 postings**, taking matching
jobs from 20 to **48**. The deep-read pass opens each posting for the full
description: 66 postings in **144 seconds**.

The top of the table then included a posting from the new source: *Eka Finance —
Junior Quantitative Researcher*, **100 points**.

**A real bug fixed:** the cache blocked **enrichment** as well. The fast pass
wrote postings with no description, the deep-read pass fetched the description,
and `INSERT OR IGNORE` dropped it so it had nowhere to go. Now: an existing row
missing its description is updated, and a long description is never overwritten
by a short one.

Tests: 24/24 (`test_ingest`) + 28/28 (`test_browser`).

**Three real bugs fixed along the way:**

1. `"analyst"` was in `JUNIOR_WORDS` -> every *"Senior … Analyst"* posting slipped
   through the seniority filter. In finance, "Analyst" is a title at EVERY level.
2. Greenhouse: using `first_published` showed Jane Street as "2228 days ago",
   because the posting had been open since 2020. Switched to `updated_at`.
3. Arbeitnow returned dates as Unix timestamps, not ISO -> every posting lost its
   date.

**Dropped:** checking the sponsor register — the user is on a Graduate visa
(design.md §11).

**Empty boards removed:** `marshallwace`, `optiver` return 200 with 0 postings.

## Step 2 — SCORE   *(done)*

Score the match, and **be able to explain why**.

| | Work | Directory |
|---|---|---|
|x| Pull the requirements out of the JD — by section heading and bullet | `scoring/extract.py` |
|x| A fallback pass for prose JDs, dropping benefits sentences | `scoring/extract.py` |
|x| Check each requirement, with the evidence quoted from the profile | `scoring/score.py` |
|x| Tell STRONG evidence (CV, education) from WEAK (a keyword) | `scoring/score.py` |
|x| 100 points in 4 parts, each part explicable | `scoring/score.py` |
|x| Filter and sort by score in the interface | `dashboard/` |

**The scale:** 55 for the must-have requirements · 15 for the nice-to-haves · 20
for the right seniority · 10 for the title.

**Nothing invented:** a requirement that could not be recognised does NOT go into
the denominator. If a JD's requirements cannot be read at all, `score = NULL` and
it says outright *"can't read requirements"*.

24 postings scored in **12ms**, with no LLM call. Tests: 31/31.

**Three real bugs fixed:**

1. `strip_html` removed tags BEFORE decoding `&lt;` -> an encoded tag became a
   real tag after the removal had finished. **1,522 postings carried raw HTML in
   their description.**
2. It took the HIGHEST degree mentioned and then demanded exactly that -> a line
   reading *"Undergraduate, MS, or PhD"* was scored as a miss despite an MSc. If
   the JD writes "or", it has to mean or.
3. `"ba"` and `"ms"` were compared as substrings -> `"database"` became a BA and
   `"systems"` an MS. Switched to word-boundary matching.

## Step 3 — TAILOR THE CV   *(done)*

|x| Split the CV into blocks (roles, projects, education, skills) | `cv/blocks.py` |
|x| The CV writing rules, drawn from a real CV that was being rejected | `cv/rules.py` |
|x| Choose and order sentences per JD | `cv/build.py` |
|x| The `/jobs/<id>/cv` page with its audit section | `cv/report.py` |

**The mechanism: CHOOSE and ORDER, never write.** Every sentence on a generated
CV is a sentence the user wrote. The system only decides which go on, in what
order, and which are dropped — and it always shows the reason for a drop.

**The rules (applied to every JD, not hand-fixed once):**

| Rule | Why |
|---|---|
| Bullets, not paragraphs | A 6-second scan needs somewhere for the eye to land |
| The sentences hitting what the JD asks for come first | Step 2 already extracted the requirements |
| **Drop a failure of OUTCOME** | Someone reading 200 CVs remembers only the worst sentence |
| **KEEP technical knowledge** | That is what separates you from the 40 others who also match |
| Drop opinion, keep evidence | *"Profit means nothing"* proves nothing |
| Drop the Compute and Method groups | Teaching the reader the basics reads as inexperience |
| A sensitive sentence carrying a number -> MARK it, do not throw it away | Throwing the sentence away throws the number away too |

**The most important distinction:**

```
"A random train/test split leaks"      -> KNOWLEDGE       -> keep
"Live drawdown ran 30% deeper"          -> A FAILED OUTCOME -> belongs on the project page
```

The first version caught the word `leaks` as well, and so dropped the most
valuable technical content there was. Fixed, with a test against a relapse.

**Run against real postings:**

```
Point72 Quant Researcher Intern   missing: — (the "or" list is satisfied)
IMC Quant Researcher Equities     missing: derivatives, equities
Jane Street Quant Researcher      missing: market data
```

Tests: 28/28. No LLM call anywhere.

**Since then:** the CV tab also measures THE GAP — what to write tonight that
would unlock the most postings — and prints to PDF through an inspection gate
that looks at the page about to print.

## Step 4 — PERSONAL PROJECTS   *(built, then removed)*

This step was built in full — a seven-stage pipeline that clustered JDs, read
them closely, had an LLM propose four briefs, put them through 8 hard rules,
downloaded the candidate datasets and looked INSIDE them, ranked on 6 dimensions
and picked the winner.

**It was then removed entirely**, along with `core/llm.py`, when founding law 1
(no LLM anywhere) was settled. Nothing in `src/` references it now, and the
routes it left behind return 404 — with a test proving it.

What the work taught, and what was kept:

- **Checking a URL returns 200 is a weak gate.** The strong gate is downloading a
  few KB and looking inside: is there a real date column, a price column, how
  many rows, is it merely a lookup table. That gate caught a brief the pipeline
  itself had produced: an S&P 500 constituents dataset that returned 200 and
  passed all 8 hard rules — but was a **399-row lookup table with no prices**,
  which can backtest nothing.
- **A question has to be refutable.** A brief that can only ever confirm itself
  is not research, it is advertising.
- **The loop closes here.** The sentences `cv/rules.py` CUTS from the CV — the
  self-criticism, the failures — are exactly the material for a project page's
  *"What I gave up, and got wrong"*. Nothing is lost, it only changes layer:

```
The CV         -> drop where it went wrong     -> pass the filter
A project page -> where it went wrong is the strongest part -> get the interview
```

The CV layer still cuts those sentences and still says why, so the material is
still there for a page written by hand.

## Step 5 — APPLY   *(done)*

| | Work | Directory |
|---|---|---|
|x| Open the posting, fill in the form's boring fields | `apply/` |
|x| **The machine never presses Send** — the last click is the user's | `apply/send.py` |
|x| Answers come only from the profile, never guessed | `apply/answer.py` |
|x| No duplicate applications — same company, same role | `track/board.py` |
|x| The journal: what went out, to whom, when, and how it turned out | `core/journal.py` |

**Done when:** a real application goes out and a row appears in the table, with a
journal entry. Met.

`work_auth`, sponsorship, demographic questions, GPA and graduation dates are
never guessed — the machine leaves them for the user, by design.

## Step 6 — TRACK + REMIND   *(done)*

| | Work | Directory |
|---|---|---|
|x| The application lifecycle | `track/board.py` |
|x| Read the mailbox and match replies back to the right application | `track/mail.py` · `track/scan.py` |
|x| The silence mark: past N days with no reply, treat it as rejected — an inference, never written down | `track/board.py` |
|x| A queue for mail that carries an outcome but no known owner | `dashboard/views/trackcho.py` |
|x| Notifications: macOS, and Telegram if it is connected | `core/notify.py` · `bao.py` |
|x| Counts: the funnel, results, output per day, a diagnosis | `dashboard/tongquan.py` |

**Done when:** apply -> see it in the table -> a reply arrives -> it matches back
to that application -> the reminder arrives at the right time. Met.

The mailbox is **read-only**, with four constraints enforced in code.

---

## Why this order

- **Step 1 blocks everything.** Without real postings, scoring, CV tailoring and
  project building are all guesswork.
- Step 2 needed real data before an algorithm could be chosen. Choosing first
  would have been a guess.
- Steps 3–4 needed step 2 to know what a JD asks for.
- Step 5 goes outside -> only after the CV was good enough.
- Step 6 needed step 5 running long enough to have something to count.

Write `audit` **from step 1 onward**. Without it, step 6 has nothing to count and
nothing can be recovered.

## More urgent than this roadmap

September is when UK graduate schemes open for the 2027 intake, and many close
as soon as they are full. Apply by hand now, in parallel with building the
system. The system is an amplifier, not an excuse to postpone.
