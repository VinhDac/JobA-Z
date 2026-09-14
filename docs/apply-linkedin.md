# The apply route for LinkedIn postings — there isn't one, and why

Measured 2026-09-10.

## The facts

LinkedIn is only a **noticeboard**. Applying still happens on the company's own
site. But the link to that site **appears only once you are signed in**:

    the guest page        ->  "Sign in to apply", with no href at all
    the body we store     ->  the job description only
    7 of 111 postings carry an outside link, and all of them sit inside the
    description, not on the Apply button

So `posting.url` for those 111 LinkedIn postings points at **the page that shows
the posting**, not at the page that takes an application. Pressing Apply on them
opens exactly that page — readable, but not applicable.

## How much of it can be recovered

    111 LinkedIn postings
     24 (22%)  agencies — no ATS of their own, you apply through the recruiter
     14        already duplicated by a posting from another source, merged by
               dedup -> a real apply URL exists
     11        the company already has a board API we know -> it can be looked up
    ~62        the rest: the company name is known, the apply page is not

## Three routes, none chosen

1. **Look it up by company.** `ingest/web/careers.py` already has
   `resolve_ats()` — give it a company name and it works out the board. The
   cheapest option, and it serves the whole scan rather than just applying. It
   will not always hit, but a miss only opens the wrong page.

2. **Sign in to LinkedIn to read the Apply button.** This gets the exact URL,
   but scraping from a real account is how accounts get locked. Losing the
   account in the middle of a job hunt costs far more than this saves. NOT to be
   done unless the user says outright that they accept that risk.

3. **Leave it.** Apply opens the LinkedIn page and the user presses Apply there
   themselves. A row still goes into the Track table — the form-filling is lost,
   the following-up is not.

Today it is (3).
