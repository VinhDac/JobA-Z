"""Versions of the rule sets.

Change a rule, CHANGE THE NUMBER HERE. Anything judged under an older version
is recomputed automatically on the next scan.

Without this: edit vocab.py and old scores sit next to new scores in the same
table, with no way to tell which rule produced which.
"""

# 2026-09-12.1 — "where you are" is derived from the profile answer "Where
# you're based" instead of being hardcoded to the UK, + a guard for US state
# codes where city names collide (Birmingham, AL).
FILTER_RULES = "2026-09-12.1"  # ingest/filter.py + ingest/base.norm_*
# scoring/vocab.py + scoring/extract.py + scoring/score.py + realism + deadline
# 2026-09-12.4 — (a) norm() now keeps `+ # /` and alias boundaries moved from
# \b to (?<!\w)/(?!\w): before that "C++" normalised down to "c", so 208
# postings asking for C++ never matched, even though the CV HAS C++. (b)
# search_keywords/stack_want dropped from the evidence index — they are
# self-declared, labelled "(not proof)", and were still letting 249 lines
# across 153 postings count as MET. Scores will drop; those are the real ones.
SCORE_RULES = "2026-09-12.4"
# cv/rules.py + cv/build.py + cv/rewrite.py. A built CV is SAVED to disk
# (table cv_build), so changing the CV rules without changing this number
# leaves old builds behind with no record of which rules made them.
#
# 2026-09-12.1 — the builder started ASKING rules.sentence_ok (before that it
# did not, and 3 banned sentences went out on every version), + cv/rewrite.py
# drops first-person subjects.
# 2026-09-12.2 — the "what will be sent" coverage line measures the LEAD
# posting instead of the union of the group (the union measures group size,
# not CV quality).
CV_RULES = "2026-09-13.1"
