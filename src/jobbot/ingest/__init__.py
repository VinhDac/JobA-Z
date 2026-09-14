"""M2 — Pull postings in, one file per source.

Here:
    - One file per source (greenhouse.py, lever.py, ashby.py, mail_alert.py, ...)
    - Each source: fetch -> normalise to Job -> return. That is all.

NOT here:
    - Dedup (-> dedup/)     - Scoring (-> scoring/)
    - Writing to the DB directly (-> core/store)

Sources in use: greenhouse, lever, ashby (company boards) + linkedin (Chrome).
Sources with no public API run inside a human-shaped window, not 24/7
(design.md §3).
"""
