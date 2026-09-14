"""CV writing rules — drawn from studying a real CV that was being rejected.

These are rules that APPLY TO EVERY JD, not a one-off manual fix.

The layering principle:
    the CV        -> matching evidence, scannable  -> gets past the filter
    project page  -> depth, including what went wrong -> gets the interview
    the interview -> the philosophy

So a self-critical sentence is NOT deleted — it moves to the project page in
step 4.
"""

from __future__ import annotations

import re

# --- sentences that do not belong on a CV (but do on a project page) -----

# Self-criticism / telling a failure. Honesty is very valuable — at the
# interview. Someone reading 200 CVs in an afternoon remembers only the worst
# sentence. It ONLY catches YOUR OWN BAD OUTCOMES — not technical knowledge.
#
# The distinction matters:
#   "A random train/test split leaks"        -> KNOWLEDGE, keep. The strongest thing there is.
#   "Live drawdown ran 30% deeper"           -> A BAD OUTCOME, moves to the project page
#
# My first version caught the word "leaks" too and dropped the most valuable
# expertise on the page.
# YOUR OWN BAD OUTCOME — a STRUCTURAL rule, not a lookup table.
#
# The old version was a list of phrases COPIED FROM ONE PERSON'S PROFILE: "i
# was optimising
# for peak", "made money while my first choice did not", "nobody has
# exploited". Measured on two other profiles: it caught 0 of 5 sentences,
# though both contained plain failure-telling ("I honestly struggled with the
# first rebuild and it shipped two weeks late"). A lookup table dressed up as
# a rule.
#
# The real rule has two halves: a WORD FOR A BAD OUTCOME, and it is NOT in a
# sentence about handling that bad thing. "Prevented data leakage" is a claim,
# "my design leaked memory" is a failure — the same word `leak`, a different
# second half.
# PAST TENSE ONLY. That is the third half, and without it the rule catches
# exactly the strongest sentences:
#
#     "My first design leaked memory"          -> something THAT HAPPENED to you
#     "A random train/test split leaks"        -> A GENERAL TRUTH about how it works
#
# Same stem `leak`, different tense. The author of the original rule wrote
# down exactly this trap — "my first version caught the word leaks and dropped
# the most valuable expertise" — and my first structural version walked into
# it again. So the table below contains NO present-tense forms: no `fails`,
# no `leaks`, no `breaks`.
KET_XAU = re.compile(
    r"\b(failed|failures?|struggled|mistakes?|fault|"
    r"broke|broken|leaked|lost|missed|went wrong|"
    r"gave up|abandoned|could ?n[o']t|did ?n[o']t|was ?n[o']t|"
    r"ran out|rolled back|deeper than|fell short|got lucky|"
    r"shipped .{0,12}late|too late|over budget)\b", re.I)

# HANDLING verbs: with one of these present, the bad-outcome word describes
# something you PREVENTED rather than caused. "Detected and fixed a memory
# leak" is a claim.
XU_LY = re.compile(
    r"\b(prevent\w*|avoid\w*|handl\w*|reduc\w*|fix(?:ed|es|ing)?|"
    r"catch\w*|caught|detect\w*|mitigat\w*|eliminat\w*|guard\w*|"
    r"protect\w*|recover\w*|debug\w*|diagnos\w*|resolv\w*)\b", re.I)


def ke_that_bai(text: str) -> bool:
    """Is this sentence telling a BAD outcome of your own."""
    return bool(KET_XAU.search(text)) and not XU_LY.search(text)


# Button text glued to a sentence by PDF extraction ("Demo MetaTrader's backtester...")
LINK_NOISE = re.compile(r"^\s*(demo|live|code|live walkthrough|link)\s+", re.I)

# OPINIONS — and this is where the old rule was MOST wrong, so the new one
# stops guessing.
#
# The old version: nine phrases copied from one person's profile ("means
# nothing", "nobody has exploited", "rather than betting"). On another profile
# it caught 0 sentences, despite a plain opinion ("Good code is code other
# people can delete").
#
# But an opinion CANNOT be separated from KNOWLEDGE by a cheap rule, and
# rules.py states plainly that knowledge is the STRONGEST thing on a technical
# CV:
#
#     "A random train/test split leaks, because adjacent dates are correlated"
#         -> KNOWLEDGE. Keep. This is what separates someone who has done it.
#     "Good code is code other people can delete"
#         -> AN OPINION. Proves nothing.
#
# Both have the same shape: present simple, no numbers, no action. Guessing
# means guessing one of them wrong, and guessing wrong means DELETING one of
# the strongest sentences.
#
# So the machine no longer deletes, it ASKS. Three signals; missing all three
# marks it "review" for the user to decide — the writer knows whether that
# sentence is knowledge or a nice phrase, and the machine does not.


def khong_ke_viec(text: str, tags: list[str] | None = None) -> bool:
    """This sentence tells NO action, carries NO number, names NO skill.

    Missing all three it could be valuable knowledge, or it could be a nice
    phrase. The machine cannot tell — so it flags rather than deletes.
    """
    return not (mo_bang_hanh_dong(text)
                or HAS_NUMBER.search(text)
                or (tags or []))


# Sentences that invite the reader to doubt you
RISKY = re.compile(
    r"\b(claude code|copilot|codex|chatgpt|prompt|ai (?:tool|assistant)|"
    r"self-funded|own capital|demo account)\b", re.I)

# SKILL SECTIONS WORTH DROPPING — recognised by CONTENT, not by heading.
#
# The old version: `{"compute", "method"}` — exactly two headings from one
# person's CV. On another profile it missed the section most worth dropping:
# "Soft — communication, teamwork" on a data analyst's CV, or "Interests —
# chess, running".
#
# The real rule: a skills section is worth printing when it names SKILLS the
# machine recognises. A section whose whole line contains not one technology
# name is taking up space with adjectives.
def bo_muc_ky_nang(title: str, body: str) -> bool:
    """Is this skills section worth printing — judged on CONTENT."""
    from .build import skills_in
    if skills_in(body):
        return False
    # No recognised skill: it could be a soft section ("teamwork"), or a
    # technology the machine does not know the name of. Only drop it when the
    # heading also says soft — dropping an unfamiliar technology section is a
    # real loss.
    return bool(MUC_MEM.search(title or ""))


# Headings that signal "not a technical skill".
MUC_MEM = re.compile(
    r"\b(soft|interests?|hobbies|personal|languages? spoken|activities|"
    r"volunteering|references?|about|profile|strengths?)\b", re.I)

# --- signals of a GOOD CV sentence ---------------------------------------

# "I "/"We " are allowed in front — real CVs very often write "I built…", and
# anchoring hard at the start misses most lines with an action verb.
# AN ACTION VERB opening the sentence — recognised by MORPHOLOGY, not by a
# hand-typed list.
#
# The old list had 21 words chosen around one quant profile: no `detected`,
# `fixed`, `migrated`, `owned`, `shipped`, `launched`, `scaled`, `refactored`,
# `mentored`… On a backend engineer's or a marketer's profile most of their
# claims fell outside it, and the machine concluded they never said what they
# did.
#
# The real rule: a subject-dropped CV sentence opens with a PAST-TENSE verb.
# Past tense is recognised by two signals, enough for English: an `-ed`
# suffix, or membership of the irregular table. That table already exists in
# cv/rewrite.py — reused, not copied into a second version that would drift.
_BAT_QUY_TAC = (
    "built", "rebuilt", "wrote", "rewrote", "chose", "ran", "led", "made",
    "took", "set", "kept", "found", "put", "sent", "sold", "won", "cut",
    "held", "grew", "drew", "spent", "taught", "brought", "began", "drove",
    "shipped", "ran", "oversaw", "rebuilt", "sped",
)
ACTION_VERB = re.compile(
    r"^(?:i|we)?\s*(?:\w+ed|" + "|".join(_BAT_QUY_TAC) + r")\b", re.I)

# A few -ed words are NOT opening verbs — they are adjectives, and a sentence
# starting with one is descriptive rather than a claim.
KHONG_PHAI_DONG_TU = re.compile(
    r"^(?:advanced|detailed|dedicated|experienced|skilled|motivated|"
    r"focused|based|related|mixed|limited|combined|applied statistics)\b", re.I)


def mo_bang_hanh_dong(text: str) -> bool:
    """Does this sentence open with an action verb."""
    t = text.strip()
    return bool(ACTION_VERB.match(t)) and not KHONG_PHAI_DONG_TU.match(t)


HAS_NUMBER = re.compile(r"\b\d[\d,.]*\s*(%|years?|instruments?|models?|strategies|x)?\b")

# The one-page budget
BUDGET = {"experience": 2, "exp_bullets": 3, "project": 3, "skill": 4}


def clean(text: str) -> str:
    """Remove button text glued to the start of a sentence by PDF extraction."""
    out = LINK_NOISE.sub("", text).strip()
    return re.sub(r"\s*·?\s*(Demo|Live|code|Live walkthrough)\s*$", "", out).strip()


def sentence_ok(text: str, tags: list[str] | None = None) -> tuple[str, str]:
    """Can this sentence go on a CV: keep | review | drop, with the reason.

    `review` = kept but flagged for Vin to decide. Used when a sentence has
    both hard evidence (numbers, skills) and wording that could be
    misunderstood — throwing the sentence away loses the number, while keeping
    it silently hides the risk.
    """
    # THREE RULE-REVERSING SWITCHES WERE REMOVED. They forced the user to
    # learn three rules before using the app, while all three are right in
    # most cases and all three have measurements behind them. The report
    # (report.py) still states which sentence was dropped and why, so the user
    # loses no information — only three buttons.
    # COMPUTE `tags` IF NOT PASSED. A missing argument used to mean "this
    # sentence has no skills", so THE SAME SENTENCE produced two verdicts
    # depending on whether the caller remembered to pass them: "A random
    # train/test split leaks…" returned `keep` with tags and `review`
    # without. A rule whose result depends on the call signature is not a
    # rule.
    if tags is None:
        from .build import skills_in
        tags = sorted(skills_in(text))
    if ke_that_bai(text):
        return "drop", "outcome failure — belongs on the project page, not the CV"
    if len(text) < 30:
        return "drop", "too short to carry evidence"
    # DO NOT DELETE, ASK. See the note on `khong_ke_viec`: opinions and
    # knowledge share a shape, and knowledge is the strongest thing on a
    # technical CV.
    if khong_ke_viec(text, tags):
        return "review", ("tells no action you TOOK, carries no measurement, "
                          "names no skill — is this valuable knowledge or just "
                          "a nice line? your call")
    if RISKY.search(text):
        strong = bool(HAS_NUMBER.search(text)) or len(tags or []) >= 2
        if strong:
            return "review", "has hard evidence but wording may read badly — your call"
        return "drop", "invites the reader to doubt you"
    return "keep", ""


def sentence_weight(text: str, wanted: set[str], tags: list[str],
                    khoa: float = 3.0) -> float:
    """How much this sentence deserves a place, for the JD in hand.

    `khoa` is the weight of "hits what the posting asks" — the "keyword
    density" knob on the Adjust panel turned exactly this number. Heavier and
    the machine prefers sentences that hit keywords; lighter and it prefers
    sentences that are strong on content even if they hit none.

    It does NOT stuff keywords into the CV: the machine adds no words. It only
    changes the PRIORITY ORDER among the sentences Vin already wrote.
    """
    score = 0.0
    score += khoa * len(wanted & set(tags))       # hits what the JD asks for
    score += 1.0 * len(tags)                      # has technical content
    if mo_bang_hanh_dong(text):
        score += 1.5                              # opens with an action verb
    if HAS_NUMBER.search(text):
        score += 1.0                              # has a number
    if len(text) > 220:
        score -= 1.0                              # too long to scan
    return score
