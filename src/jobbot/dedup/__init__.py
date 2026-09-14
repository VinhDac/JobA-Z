"""M3 — Group duplicate postings.

The same job posted on 4 boards, with different titles and the company name
spelled differently. This is entity resolution, not string comparison.

The requirement: every merge must be EXPLICABLE.
A wrong merge whose reason cannot be traced loses a real posting.
"""
