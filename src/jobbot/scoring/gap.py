"""THE GAP BLOCK — write a sentence about what, and how many POSTINGS CLEAR.

This is the block that answers the CV tab's one question: *what do I have to
sit down and write about tonight?* Everything else on that tab serves it.

THE UNIT IS **POSTINGS CLEARED** — postings where EVERY must line is
answered. Not "mentions", not "skills covered". Why that was measurable:
counted by mentions, `cloud` tops the table (67 lines) while unlocking only
14 more postings, and `visualisation` has fewer mentions but unlocks 42.
Counting in the wrong unit orders the work wrongly, and the user goes off and
does the most expensive job first.

A CUMULATIVE LADDER, NOT A LEADERBOARD. Three skills that unlock the same
posting, added up separately, count that posting three times. So each rung is
the MARGINAL value once the rungs above it are done — greedy, step by step,
exactly the way it happens for real: write the first sentence, then ask
whether the second is still worth it.

TWO LABELS, split by ONE measurable rule, not by judgement:

    WRITE  most must lines asking for it name NO product
           -> it can be said in your own words. Costs an evening.
    LEARN  most must lines name a product OUTRIGHT (AWS, Tableau…)
           -> no sentence stands in for it, it has to be learnt. Costs months.

THE WRITE LABEL IS A PROMISE, AND `nen_nhap` IS WHERE IT IS KEPT. Having said
"this can be reworded", it has to hand over A LINE TO REWORD, not an empty
box. The LEARN label is the opposite, and rightly so: "must use Tableau" has
no draft.

The label does NOT say "the user has done this" — the machine does not know
that, and an earlier version of this note claimed it while the code had never
measured it.

Measured on the real store: the whole WRITE basket takes must-coverage from
73.5% -> 90.0% (166 -> 269 postings); the whole LEARN basket only reaches
81.8% (+31 postings). Writing beats learning by more than two to one, and it
is counted in days rather than months.
"""

from __future__ import annotations

import json
import re
import sqlite3

from ..ingest.base import norm
from .vocab import alias_hits

# PRODUCT NAMES stated outright -> cannot be written, must be learnt. A
# hand-written lookup, same in kind as vocab.py — not machine-generated.
NAMED_TOOL = re.compile(
    r"\b(aws|amazon web services|azure|gcp|google cloud|s3|redshift|snowflake|"
    r"databricks|terraform|kubernetes|k8s|docker|kafka|airflow|spark|hadoop|"
    r"tableau|power ?bi|looker|qlik|sas|matlab|kdb|q/kdb|bloomberg|murex|"
    r"jenkins|gitlab ci|circleci)\b", re.I)


def _tin(conn: sqlite3.Connection) -> list:
    """[(skills each must line asks for, does it name a product outright)]

    One posting = one list of must lines. Kept PER LINE rather than merged
    into one set: "cleared" means every line is answered, and a single line
    can ask for several things while needing only one of them ("C++, Java or
    Python").
    """
    ra = []
    for row in conn.execute(
            "SELECT score_json FROM posting WHERE kept = 1"
            " AND realism IN ('likely','possible') AND score_json != ''"):
        try:
            reqs = json.loads(row["score_json"]).get("requirements", [])
        except (TypeError, ValueError):
            continue
        dong = []
        for q in reqs:
            if not q.get("must"):
                continue
            chu = q.get("text", "")
            ky = set(alias_hits(norm(chu)))
            if ky:
                dong.append((ky, bool(NAMED_TOOL.search(chu))))
        if dong:
            ra.append(dong)
    return ra


def tin_tron(tin: list, co: set) -> int:
    """How many postings have EVERY must line answered by `co`.

    A line is answered when it asks for at least one thing you have — the
    same "or" rule `cv.build._real_missing` already uses: the JD says "C++,
    Java or Python" and you have Python, so that line is done and Java is not
    a gap.
    """
    return sum(1 for dong in tin if all(ky & co for ky, _ in dong))


def thang(conn: sqlite3.Connection, co: set, sau: int = 8) -> dict:
    """The cumulative ladder: which thing to write or learn first pays most.

    Greedy, one rung at a time — each round picks the skill that unlocks THE
    MOST EXTRA POSTINGS given what is already picked. That is also how it
    happens for real: finish the first sentence, then ask whether the second
    is still worth it.
    """
    tin = _tin(conn)
    if not tin:
        return {"tin": 0, "nen": 0, "buoc": []}

    # Candidates = every skill still missing on at least one unanswered must
    # line.
    ung: dict = {}
    for dong in tin:
        for ky, ten_rieng in dong:
            if ky & co:
                continue                      # this line is already answered
            for k in ky:
                a, b = ung.get(k, (0, 0))
                ung[k] = (a + 1, b + (1 if ten_rieng else 0))
    nen = tin_tron(tin, co)
    dang_co = set(co)
    buoc = []
    for _ in range(sau):
        tot, ten = 0, ""
        for k in ung:
            if k in dang_co:
                continue
            them = tin_tron(tin, dang_co | {k}) - tin_tron(tin, dang_co)
            if them > tot:
                tot, ten = them, k
        if not ten:
            break
        dang_co.add(ten)
        dong_n, rieng = ung[ten]
        buoc.append({
            "ky_nang": ten,
            "dong": dong_n,                  # how many must lines ask for it
            "rieng": rieng,                  # of those, how many name a product
            "them": tot,                     # how many EXTRA postings it unlocks
            "cong_don": tin_tron(tin, dang_co),
            # THE LABEL follows the majority, but BOTH numbers are always
            # shown next to it.
            #
            # Forcing one label loses information: `visualisation` has 51
            # must lines, 26 naming Tableau/Power BI outright (must be
            # learnt) and 25 only asking to "present findings" (writable
            # tonight). Stamp LEARN on it and the user skips 25 lines that
            # are within reach.
            "viec": "hoc" if rieng * 2 > dong_n else "viet",
        })
    # WRITING ALONE GETS YOU HOW FAR — the most decisive number on the table.
    #
    # "Do the whole table" folds in the lines that have to be LEARNT, and
    # learning is counted in months while writing is counted in evenings.
    # Mixing the two into one number sets the user a target they cannot reach
    # tonight.
    chi_viet = set(co)
    for b in buoc:
        if b["viec"] == "viet":
            chi_viet.add(b["ky_nang"])
    return {"tin": len(tin), "nen": nen, "buoc": buoc,
            "chi_viet": tin_tron(tin, chi_viet),
            "so_viet": sum(1 for b in buoc if b["viec"] == "viet")}


# --- THE WRITING BENCH: the machine clears the space, the person writes ---

def ho_hoi(conn: sqlite3.Connection, ky_nang: str, sau: int = 8) -> list:
    """The must lines asking for `ky_nang` that the profile misses, VERBATIM.

    Printed word for word, NOT summarised: people write a sharper CV reading
    the exact words the employer used, not the machine's paraphrase of them.
    The company name comes along so it is clearly a real requirement from a
    real posting.

    Split in two because they lead to two different jobs: a line naming a
    product outright cannot be written around, a general line can.
    """
    chung, rieng = [], []
    # ONE LINE ONCE. Several postings copy the same stock sentence
    # ("Understanding of data visualisation and presenting analytical
    # findings clearly" came twice from the same agency), and a brief that
    # repeats itself shrinks five readable lines to three. Keep the FIRST
    # appearance — the highest-scoring posting, since the query already
    # ORDER BY score DESC.
    da_co: set = set()
    for row in conn.execute(
            "SELECT company, title, score_json FROM posting WHERE kept = 1"
            " AND realism IN ('likely','possible') AND score_json != ''"
            " ORDER BY score DESC"):
        try:
            reqs = json.loads(row["score_json"]).get("requirements", [])
        except (TypeError, ValueError):
            continue
        for q in reqs:
            if not q.get("must"):
                continue
            chu = q.get("text", "")
            if ky_nang not in alias_hits(norm(chu)):
                continue
            dau = " ".join(norm(chu).split())
            if dau in da_co:
                continue
            da_co.add(dau)
            muc = {"cong_ty": row["company"], "tin": row["title"], "chu": chu}
            (rieng if NAMED_TOOL.search(chu) else chung).append(muc)
    # General lines first: that is the part the user can write tonight.
    return (chung[:sau], rieng[:sau])


# --- LINES USABLE AS THE BASE OF A DRAFT --------------------------------
#
# The WRITE label says: this line names NO product outright, so it can be
# said in your own words. That is exactly the base a draft is built on — and
# the reason the LEARN label has no draft: "must use Tableau" is not
# something a sentence can stand in for.
#
# BUT NOT EVERY GENERAL LINE IS USABLE. Measured on the real store,
# `visualisation` has 22 general lines and 12 of them DESCRIBE A QUALITY
# ("Interest in statistics, data visualisation or modelling"). Turn that into
# a CV sentence and it turns into what? There is no work in it to tell.
#
# So only lines that DESCRIBE WORK are taken: opening with an imperative verb
# ("Build and maintain data pipelines…") or a gerund ("Developing and
# maintaining…"). Those are the lines saying WHAT THEY WANT THIS PERSON TO
# DO — and a CV sentence is also an account of what you did, so the two have
# the same shape.
#
# A hand-written lookup, same in kind as NAMED_TOOL and vocab.py — not
# machine-generated, and a missing word gets added here.
LAM_VIEC = (
    "build", "rebuild", "develop", "design", "create", "implement", "deliver",
    "maintain", "write", "produce", "automate", "analyse", "analyze", "model",
    "optimise", "optimize", "improve", "enhance", "manage", "own", "lead",
    "support", "use", "apply", "conduct", "perform", "run", "translate",
    "present", "communicate", "collaborate", "partner", "research", "explore",
    "investigate", "monitor", "test", "validate", "clean", "process",
    "extract", "transform", "visualise", "visualize", "report", "deploy",
    "scale", "integrate", "migrate", "refactor", "debug", "document",
    "contribute", "drive", "define", "evaluate", "benchmark", "tune",
    "forecast", "backtest", "prototype", "ship", "maintain", "assist",
)

# A STATE noun at the front -> describes a quality, not work. It usually has
# an adjective or two before it ("Solid experience…", "Detailed
# understanding…").
PHAM_CHAT = re.compile(
    # FOUR filler words, not two. "Strong programming and scripting skills
    # (Python, Bash)" has four words before the state noun, so it slipped
    # through and was offered as the base of a draft — a line with no work in
    # it to tell.
    r"^(?:[a-z+0-9-]+\s+){0,4}"
    r"(interest|curiosity|understanding|knowledge|awareness|familiarity|"
    r"passion|enthusiasm|exposure|appreciation|experience|experiences|"
    r"proficiency|proficient|competency|comfort|comfortable|background|"
    r"degree|degrees|education|grasp|attention|ability|aptitude|mindset|"
    r"motivations?|desire|willingness|skills?|expertise|fluency|command|"
    r"confidence|confident|strength|acumen|literacy)\b", re.I)

# A gerund at the front ("Developing and maintaining…"). Minus the -ing words
# that are really INDUSTRY nouns, not work being done.
_ING_KHONG_PHAI_VIEC = re.compile(
    r"^(engineering|marketing|accounting|banking|consulting|training|"
    r"understanding|reporting line)\b", re.I)

_MO_DAU = re.compile(
    r"^(?:the |a |an )?(?:proven |demonstrable |strong )?(?:ability to |able to )?"
    r"([a-z][a-z-]*)", re.I)


def ta_viec(chu: str) -> bool:
    """Does this requirement line DESCRIBE WORK — i.e. can a draft start here.

    Describes work     "Build and maintain data pipelines, ensuring data quality…"
    Describes a quality "Interest in statistics, data visualisation or modelling"

    Only a line describing work converts into a CV sentence: a CV sentence is
    also an account of what you DID. Offering a quality line as the base of a
    draft invites the user to rewrite the employer's compliment to itself.
    """
    t = " ".join((chu or "").split())
    if len(t) < 18 or PHAM_CHAT.match(t):
        return False
    m = _MO_DAU.match(t)
    if not m:
        return False
    tu = m.group(1).lower()
    if tu in LAM_VIEC:
        return True
    return tu.endswith("ing") and not _ING_KHONG_PHAI_VIEC.match(tu)


# --- THE SUGGESTION: their line turned into the SHAPE of a CV sentence ---
#
# The machine invents NO claim. It performs exactly three mechanical steps,
# and all three can be checked by eye:
#
#   1  cut the posting-writer's tail ("…, ensuring data quality across…")
#   2  put the imperative verb into the PAST — the shape of a CV sentence
#   3  leave a BLANK `___` for the evidence, the one thing only the user has
#
# The blank is the most important part. Without it the "suggestion" is just
# the employer's own line conjugated into the past — a claim the user never
# made and cannot hold up when the interviewer asks the next question. With
# it the machine supplies the SHAPE, the user supplies the CONTENT, and
# `con_trong` refuses to save while the blank is still there.

# The posting-writer's tail: context, conditions, promises. None of it
# belongs in a CV sentence. ONLY CUT WHILE THE SKILL SURVIVES — see `goi_y`.
# Cut the skill name itself away and the sentence written from it fills no
# gap, and filling gaps is the entire reason the user is sitting here.
_DUOI = re.compile(
    r"\s*(?:,\s*)?\b(?:ensuring|including|as well as|in order to|so that|"
    r"to ensure|to support|to help|with a focus on|whilst|while ensuring|"
    r"across multiple|and related|or similar|and other|such as|e\.g\.|etc)"
    r"\b.*$", re.I)

# Cut further at the joins, again only while the skill survives. A job ad
# line often packs three or four jobs together; a CV sentence tells ONE.
_NOI = re.compile(r"\s*(?:,\s+and\s+|,\s+|\s+and\s+|\s+through\s+|"
                  r"\s+across\s+|\s+within\s+|\s+for\s+)", re.I)

# The irregular verbs that appear in LAM_VIEC. A hand-written lookup — same
# in kind as NAMED_TOOL and vocab.py.
_QUA_KHU = {"build": "built", "rebuild": "rebuilt", "write": "wrote",
            "run": "ran", "lead": "led", "drive": "drove", "ship": "shipped",
            "own": "owned", "deal": "dealt", "keep": "kept", "make": "made"}

CHO_TRONG = "___"


def qua_khu(tu: str) -> str:
    """Imperative verb or gerund -> PAST TENSE. The shape of a CV sentence."""
    t = tu.lower()
    if t.endswith("ing"):                       # Developing -> develop
        goc = t[:-3]
        t = goc if goc in LAM_VIEC else (goc + "e" if goc + "e" in LAM_VIEC
                                         else goc)
    if t in _QUA_KHU:
        return _QUA_KHU[t]
    if t.endswith("e"):
        return t + "d"
    if len(t) > 2 and t.endswith("y") and t[-2] not in "aeiou":
        return t[:-1] + "ied"
    return t + "ed"


def _con_ky_nang(t: str, ky_nang: str) -> bool:
    """Does this stretch of text still mention the skill being aimed at."""
    return bool(ky_nang) and ky_nang in alias_hits(norm(t))


def goi_y(chu: str, ky_nang: str = "") -> str:
    """A requirement line -> the SHAPE of a CV sentence, blank left for proof.

    Three mechanical steps, none of which invents a new claim:
        cut the posting-writer's excess — but NEVER cut the skill name away
        put the imperative verb into the past — the shape of a CV sentence
        leave `___` for the evidence, the one thing only the user has

    RETURNS "" WHEN IT CANNOT GET FAR ENOUGH. Measured on the real store: cut
    lightly, and 12 of 19 lines come out as the employer's own line in the
    past tense (similarity 0.86–1.00) — that is, the machine suggests exactly
    what `qua_giong` will block at Save. A suggestion the machine itself
    rejects is worse than no suggestion: the user clicks, types, gets
    blocked, and has no idea what they did wrong. So where the cut does not
    get far enough, it stays quiet.
    """
    t = " ".join((chu or "").split())
    goc = t
    t = _DUOI.sub("", t).rstrip(" ,;.:-–—")
    if not _con_ky_nang(t, ky_nang):
        t = " ".join(goc.split())               # skill was cut away -> undo

    # Keep cutting at the joins, right to left, stopping the moment the skill
    # is about to be lost.
    for m in reversed(list(_NOI.finditer(t))):
        ngan = t[:m.start()].rstrip(" ,;.:-–—")
        if len(ngan.split()) >= 2 and _con_ky_nang(ngan, ky_nang):
            t = ngan

    if not t or not ta_viec(t):
        return ""
    m = _MO_DAU.match(t)
    if not m:
        return ""
    tach = t.split()
    # Drop the "The ability to …" hedge before conjugating.
    while tach and tach[0].lower() != m.group(1).lower():
        tach.pop(0)
    if not tach:
        return ""
    tach[0] = qua_khu(tach[0]).capitalize()
    # "Build AND maintain X" / "Developing AND maintaining X" -> both verbs
    # go to the past, otherwise the sentence comes out half past, half
    # present.
    if len(tach) > 2 and tach[1].lower() == "and":
        k = tach[2].lower()
        if k in LAM_VIEC or (k.endswith("ing") and k[:-3] in LAM_VIEC):
            tach[2] = qua_khu(tach[2])
    ra = " ".join(tach) + " — " + CHO_TRONG
    # THE LAST GATE: the suggestion has to pass the very check Save applies.
    return "" if qua_giong(ra, chu) >= 0.6 else ra


def con_trong(cau: str) -> bool:
    """Sentence still holds the blank -> not finished, refuse to save."""
    return CHO_TRONG in (cau or "")


def nen_nhap(conn: sqlite3.Connection, ky_nang: str, sau: int = 12) -> list:
    """The requirement lines USABLE as a draft base, best postings first.

    The machine writes NO new sentence — it hands over the EMPLOYER's words,
    verbatim, for the user to rewrite as work THEY actually did. Every claim
    on the CV is still the user's own, and `qua_giong` below guards exactly
    that point.
    """
    # TAKE WIDE, cut after. This used to be `sau=3`, while `goi_y` can only
    # build a draft out of a small share of the lines — measured on the real
    # store: `nlp` has 8 lines describing work, the first 3 yield 1 draft,
    # all 8 yield 3. `equities` went from 0 to 1. Truncating before trying
    # throws drafts away.
    chung, _rieng = ho_hoi(conn, ky_nang, sau=60)
    return [m for m in chung if ta_viec(m["chu"])][:sau]


# Function words — not counted when comparing two sentences for likeness.
_RONG = frozenset(
    "a an the and or of to in on for with by as at from into across is are be "
    "that this those these you your our their its it we they have has had will "
    "would can could should may might not no than then such including include "
    "e g eg ie etc other others more most both all any some".split())


def _goc(w: str) -> str:
    """Crude suffix stripping, but enough: `maintained` and `maintain` are one.

    Without it, changing a verb's tense is enough to pass the gate — and
    "Built and maintained data pipelines, ensuring data quality" is still the
    employer's line written in the past, not the user's account of their own
    work. Measured: without stripping -> 0.57; with -> 0.86.
    """
    for duoi in ("ing", "ed", "es", "s"):
        if len(w) > len(duoi) + 2 and w.endswith(duoi):
            return w[:-len(duoi)]
    return w


def _loi(text: str) -> set:
    return {_goc(w) for w in re.findall(r"[a-z0-9+#]+", (text or "").lower())
            if w not in _RONG and len(w) > 1}


def qua_giong(cau: str, nen: str) -> float:
    """How much of the requirement line the typed sentence still IS — 0…1.

    This is the gate the whole suggestion mechanism rests on. The draft base
    is the employer's words; saving them into the CV does two kinds of damage
    at once: whoever screens the CV recognises the words from their own job
    ad, and the user has to defend a claim they never made.

    Measured as the share of the REQUIREMENT LINE's meaningful words still
    present in the sentence — not a two-way Jaccard: a user who writes at
    greater length would see Jaccard drop even though they dropped none of
    the employer's words.
    """
    a, b = _loi(cau), _loi(nen)
    if not b:
        return 0.0
    return len(a & b) / len(b)


def gan_nhat(profile: dict, ky_nang: str, sau: int = 3) -> list:
    """Vin's OWN sentences closest to this skill — to extend, not rewrite.

    The blank is the hard part. Put Vin's own nearest sentence in front of
    him and what is left is adding a clause, not thinking from scratch. And
    it keeps Vin's voice — the thing any sentence template destroys.
    """
    from ..cv.blocks import parse, sentences
    from ..cv.build import skills_in

    # Words from the same FAMILY as the skill being aimed at: the sentence
    # about "backtesting" is the nearest place to say more about "data
    # pipeline".
    ra = []
    for b in parse(str(profile.get("cv_text") or "")):
        if b.kind not in ("experience", "project"):
            continue
        for s in sentences(b):
            ky = skills_in(s)
            if not ky:
                continue
            ra.append({"khoi": b.title, "chu": s.strip(), "ky": sorted(ky),
                       "diem": len(ky)})
    ra.sort(key=lambda x: -x["diem"])
    return ra[:sau]
