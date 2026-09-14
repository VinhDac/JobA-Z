"""M2 — Pull postings in, one file per source.

Here:
    - Một file cho một nguồn (greenhouse.py, lever.py, ashby.py, mail_alert.py, ...)
    - Each source: fetch -> normalise to Job -> return. That is all.

NOT here:
    - Dedup (-> dedup/)     - Scoring (-> scoring/)
    - Ghi DB trực tiếp (-> core/store)

Sources in use: greenhouse, lever, ashby (company boards) + linkedin (Chrome).
Sources with no public API run inside a human-shaped window, not 24/7
(design.md §3).
"""
