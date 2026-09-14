"""Rewording CV sentences — USING ONLY VIN'S OWN WORDS.

The founding rule of the whole CV layer (see build.py): *every sentence on
the CV is one Vin wrote*. This module does not break that rule; it makes it
explicit as two different
jobs:

    TRANSFORM  cut and reorder existing words -> the machine does it,
                                                  adding 0 facts
    WEAKNESS   point at what the sentence lacks -> the machine only SAYS it,
                                                  Vin writes it

The boundary is exactly one question: *does the reworded sentence assert
anything Vin never wrote?* Dropping a leading "I" does not. Adding "resulting
in a 30% improvement" does — and that is a sentence Vin has to defend in front
of an interviewer without having written it. So that is where the machine
stops.

WHY NO COLON SURGERY. Measured on the real CV: 5 of 16 surviving sentences
have a colon inside their first 60 characters, and looking at them, it is the
part BEFORE the colon that carries the point ("The fix was not a better
parameter but better normalisation: …"). Cutting automatically kills the
meaning. So a long sentence is MARKED, not cut.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import rules

# --- TRANSFORMS ----------------------------------------------------------

# Common IRREGULAR past tenses in a CV. This table is needed because the
# "-ed suffix" rule does not catch "built", "wrote", "chose". This is
# morphology, not a lookup built around Vin's CV — new sentences still work.
QUA_KHU = (
    "built", "rebuilt", "wrote", "rewrote", "chose", "ran", "led", "made",
    "took", "set", "kept", "found", "put", "sent", "sold", "won", "cut",
    "held", "grew", "drew", "spent", "taught", "brought", "began",
)

# "I <past-tense verb>" at the START of a sentence. Only at the start: fixing
# mid-sentence ("…, so I chose on average risk/return") changes the sentence's
# structure and is no longer just cutting words.
#
# It does NOT catch auxiliaries. "I was optimising" -> "Was optimising" is
# ungrammatical, and the -ed/irregular rule excludes them by itself: "was",
# "had" and "could" have no -ed suffix and are not in the table above.
NGOI_MOT = re.compile(
    r"^\s*I\s+(?=(\w+ed|" + "|".join(QUA_KHU) + r")\b)", re.I)


@dataclass
class Sua:
    """One transform that was applied, enough for Vin to check by eye."""
    phep: str           # the transform code, for tests and grouping
    truoc: str
    sau: str
    vi_sao: str         # written for a PERSON, not for the machine


def _chu_ngu(text: str) -> tuple[str, str]:
    """Drop the first-person subject — the CV convention.

    A CV does not write "I built X", it writes "Built X": the reader already
    knows who the whole sheet is about. The first two words are the most
    expensive place on a CV line, and "I " carries no evidence.
    """
    moi = NGOI_MOT.sub("", text)
    if moi == text:
        return text, ""
    moi = moi[0].upper() + moi[1:]
    return moi, ("CVs drop the subject — the whole sheet is already about "
                 "you, so the first two words go to what you did, not to a "
                 "pronoun")


def _hoa_dau(text: str) -> tuple[str, str]:
    """Capitalise the first letter.

    A lowercase opening is a fragment from PDF extraction, not intent — one
    such sentence was measured in the real profile ("the whole pipeline
    turned into…"). On a CV it reads as a typo, and for someone reading 200
    CVs in an afternoon one typo is enough.
    """
    if not text or not text[0].islower():
        return text, ""
    return text[0].upper() + text[1:], ("the first letter was lowercase — a "
                                        "fragment from PDF extraction; on a "
                                        "CV it reads as a mistake")


# The order MATTERS: drop the subject first, capitalise second — once "I" is
# gone a new word leads, and it may be lowercase.
PHEP = (("chu_ngu", _chu_ngu), ("hoa_dau", _hoa_dau))


def sua(text: str, giong: str = "cv") -> tuple[str, list[Sua]]:
    """The reworded sentence, with the list of transforms applied.

    If no transform applies it returns the original sentence and an empty
    list — that is how the caller tells "reworded" from "needed no rewording".

    `giong` = "nguyen" means DO NOT drop the subject — Vin wants his own
    voice kept. PDF junk and a lowercase opening are still fixed: those are
    extraction errors, not voice, and nobody chooses to keep a typo.
    """
    ra = rules.clean(text)          # PDF junk at either end — the rule exists
    da: list[Sua] = []
    if ra != text:
        da.append(Sua("rac_pdf", text, ra,
                      "button text glued to the sentence by PDF extraction"))
    for ma, phep in PHEP:
        if ma == "chu_ngu" and giong == "nguyen":
            continue
        truoc = ra
        ra, vi_sao = phep(ra)
        if vi_sao:
            da.append(Sua(ma, truoc, ra, vi_sao))
    return ra, da


# --- WEAKNESSES: the machine POINTS, Vin writes -------------------------

DAI_NHAT = 200          # past this the reader's eye slides over the whole line


@dataclass
class Yeu:
    ma: str
    noi: str            # what the weakness is
    lam_gi: str         # how to fix it — has to be an action, not advice


def diem_yeu(text: str, tags: list[str], wanted: set[str]) -> list[Yeu]:
    """What this sentence still lacks. It changes NOTHING — it only says.

    This is the half the machine must not do on Vin's behalf. A sentence
    missing a measurement is missing A REAL NUMBER, and only Vin knows that
    number. Inventing one produces a sentence he cannot defend in an
    interview — so the machine only points at the gap.
    """
    ra: list[Yeu] = []
    # A CV SENTENCE IS ONE OF TWO THINGS, and they demand different standards:
    #
    #   A CLAIM     "Built two systems…"  -> needs a number, or the claim
    #               cannot be checked
    #   KNOWLEDGE   "A random train/test split leaks, because…"  -> there is
    #               no number to add, and rules.py calls this the STRONGEST
    #
    # Measured on the real profile: 12 of 16 sentences are knowledge.
    # Demanding a measurement on all 16 makes 12 of the marks false alarms —
    # and a mark that appears on every line stops being a mark and becomes
    # the background. The user learns to stop looking at marks.
    khoe_viec = bool(rules.mo_bang_hanh_dong(text))
    if khoe_viec and not rules.HAS_NUMBER.search(text):
        ra.append(Yeu("khong_so",
                      "a claim with no measurement",
                      "add a real number: how many, over how much data, how "
                      "many per cent it moved"))
    # "does not open with a verb" WAS REMOVED from the weakness list: a
    # knowledge sentence does not open with an action verb, so it flagged
    # exactly the profile's 12 strongest sentences out of 16 and called them
    # mistakes.
    if len(text) > DAI_NHAT:
        ra.append(Yeu("qua_dai",
                      f"{len(text)} characters long",
                      "split it in two, or cut the context and keep what you "
                      "did"))
    if tags and wanted and not (set(tags) & wanted):
        ra.append(Yeu("khong_tra_loi",
                      "touches none of this posting's requirements",
                      "save it for another posting — or connect it to a skill "
                      "this posting does ask for"))
    return ra


# --- SPANS: WHERE in the sentence, not WHICH sentence -------------------
#
# This is the difference between "marking work" and "listing errors".
# Underlining the whole line still leaves the reader hunting for the broken
# part; underlining the exact phrase sends the eye straight to what needs
# fixing. That is where most of Grammarly's value lives.
#
# Not every weakness has a span. A missing measurement is an ABSENCE — you
# cannot underline what is not there. But you can underline WHERE THE NUMBER
# SHOULD BE: the claim's verb phrase. "Built two systems" underlined, with
# the note "how many, over how much data" — and the reader knows exactly
# where to insert it.

# The CLAIM phrase: from the action verb to the end of the first clause.
# This is where the number belongs.
_MENH_DE = re.compile(r"^(.{0,90}?)(?=[,:;]|\s+(?:then|and then|which)\b|$)",
                      re.I | re.S)


@dataclass
class Vet:
    """A SPAN worth marking: [start, end) inside the sentence."""
    dau: int
    cuoi: int
    loai: str           # 'thieu_so' | 'qua_dai' | 'lac_de' | 'da_sua'
    noi: str            # what is wrong here
    lam_gi: str         # how to fix it


def vet(text: str, tags: list, wanted: set, da_sua=()) -> list:
    """Every span worth marking inside ONE sentence.

    Returned in order of appearance. Overlapping spans are normal (a sentence
    can be both too long and missing a number); the renderer merges them.
    """
    ra: list = []

    # 1. REWORDED — mark the first word, because that is where "I" was cut.
    if da_sua:
        het = text.find(" ")
        ra.append(Vet(0, het if het > 0 else len(text), "da_sua",
                      "the machine reworded this",
                      " · ".join(x.vi_sao for x in da_sua)))

    # 2. A CLAIM WITH NO NUMBER — underline the verb phrase, where the number belongs.
    if rules.mo_bang_hanh_dong(text) and not rules.HAS_NUMBER.search(text):
        m = _MENH_DE.match(text)
        if m and m.end() > 3:
            ra.append(Vet(0, m.end(), "thieu_so",
                          "a claim with no measurement",
                          "insert a real number right here: how many, over "
                          "how much data, how many per cent it moved"))

    # 3. TOO LONG — underline THE EXCESS, from where the eye starts sliding.
    if len(text) > DAI_NHAT:
        ra.append(Vet(DAI_NHAT, len(text), "qua_dai",
                      f"from here is the {len(text) - DAI_NHAT} characters over the limit",
                      "cut the context and keep what you DID — or split it in two"))

    # 4. TOUCHES NOTHING HERE — the whole sentence, because that is the problem.
    if tags and wanted and not (set(tags) & set(wanted)):
        ra.append(Vet(0, len(text), "lac_de",
                      "touches none of this posting's requirements",
                      "save it for another posting, or swap in one that hits"))
    return sorted(ra, key=lambda v: (v.dau, -v.cuoi))

