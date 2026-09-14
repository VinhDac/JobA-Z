"""Build a CV tailored to one JD — THE CV IS AN ANSWER SHEET.

Every sentence on the CV is a sentence Vin wrote in his profile. No LLM here.

CHANGED AT THE ROOT (10/09): this used to be a SECOND selection engine. The
scoring layer looked the profile up against the JD's requirements and produced
a number; this layer then weighed everything again from scratch and padded out
to `BUDGET`. Two independent paths, so they drifted apart — measured: a
92-point posting got a CV where **76% of the sentences touched none of it**,
and 2 of 18 sentences were PDF scrapings ("·", "Sep 2025") that went out
anyway because there was an empty slot to fill.

Now there is only ONE engine. `score.build_index` gathers the profile into
evidence at SENTENCE level; this layer only asks that same index:

    what they ask  ->  which of my sentences answers it  ->  print, in their order

A sentence that answers nothing does not go on. There is no budget any more,
so CV length is a MEASUREMENT of the profile rather than a target: five
sentences means the profile answers five things. To make it longer, do another
project, do not pad with more sentences.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..ingest.base import norm
from ..scoring.vocab import alias_hits
from . import rewrite, rules
from .blocks import Block, parse, sentences


@dataclass
class Line:
    text: str
    weight: float = 0.0
    hits: list[str] = field(default_factory=list)   # JD skills this sentence hits
    review: str = ""                                # kept, but Vin should look
    # THE BEFORE/AFTER lives here. `goc` is the sentence Vin wrote, `text` is
    # the one that will be printed — when they differ, `sua` says which rule
    # was applied and why. Without `goc` there is no "before" to compare
    # against, and the user has to take the machine's word for it.
    goc: str = ""
    sua: list = field(default_factory=list)         # [rewrite.Sua]
    yeu: list = field(default_factory=list)         # [rewrite.Yeu] — machine points, Vin fixes
    # A MARK is WHERE IN THE SENTENCE, not which sentence. Underline the whole
    # line and the reader still has to hunt; underline the exact phrase and the
    # eye goes straight to what needs changing.
    vet: list = field(default_factory=list)         # [rewrite.Vet]


def dang_ke(line: Line) -> bool:
    """Does this sentence have anything TO ACCOUNT FOR.

    ONE place decides. The red pen on the page and the detail block below it
    must ask THE SAME question: ask in two places and they drift apart, and a
    clickable mark on the page points at an anchor that does not exist —
    clicking goes nowhere, silently. It happened to sentences 6 and 7.
    """
    return bool(line.sua or line.yeu or line.review or line.hits)


@dataclass
class Section:
    kind: str
    title: str
    meta: str
    lines: list[Line] = field(default_factory=list)


@dataclass
class TailoredCV:
    header: list[str]
    summary: str
    sections: list[Section]
    dropped: list[tuple[str, str]]      # (sentence, why it was dropped)
    wanted: list[str]                   # skills the JD cares about (wide — for ordering)
    covered: list[str]                  # of those, what this CV can speak to
    missing: list[str]                  # the JD asks, the profile has not got it
    # TWO FIELDS FOR THE NUMBER ON SCREEN. Separate from wanted/covered
    # because they measure something else: wanted is wide so sentences can be
    # ordered, asked is narrow so the denominator is honest.
    asked: list[str] = field(default_factory=list)    # what the posting REALLY asks
    on_paper: list[str] = field(default_factory=list) # what THE PAGE can say


def skills_in(text: str) -> set[str]:
    """Skills present in a stretch of text. The matching rule lives in
    vocab.alias_hits — ONE place, because score._signals used to keep a copy
    and both sides had to remember to change together."""
    return set(alias_hits(norm(text)))


def wanted_skills(explain: dict | None, jd_text: str = "") -> set[str]:
    """Skills this posting cares about.

    Scans THE WHOLE posting, not just the bullet lines: Jane Street mentions
    "time series analysis, feature engineering" in the opening paragraph, not
    under "About You".
    """
    out: set[str] = set(skills_in(jd_text))
    for req in (explain or {}).get("requirements", []):
        out |= skills_in(req["text"])
    return out


# Separators between ITEMS on a skills line. Never cut inside brackets:
# "Python (pandas, NumPy, PyTorch)" is ONE item, and cutting it gives
# "Python (pandas" and "PyTorch)" — broken text on the page sent to employers.
_NGAN = ",;·"


def _ky_cua_muc(block) -> set:
    """Which skills this skills section mentions — including in its TITLE."""
    ra = skills_in(block.title)
    for l in block.lines:
        ra |= skills_in(l)
    return ra


def _tach_mon(chu: str) -> list:
    """Split a skills line into ITEMS. Counts brackets, never cuts inside."""
    ra, dem, cuoi = [], 0, 0
    for i, c in enumerate(chu):
        if c in "([":
            dem += 1
        elif c in ")]":
            dem = max(0, dem - 1)
        elif c in _NGAN and dem == 0:
            ra.append(chu[cuoi:i])
            cuoi = i + 1
    ra.append(chu[cuoi:])
    return [m.strip() for m in ra if m.strip()]


# An item in a LIST is short: "SQL", "Python (pandas, NumPy)". Longer than
# that and it is a CLAUSE, and the line is PROSE rather than a list.
_MON_DAI_NHAT = 5          # words


def _la_danh_sach(mon: list) -> bool:
    """Is this line a LIST or PROSE — i.e. may it be reordered.

    THIS IS A GATE, and it was needed: the first version reordered every
    skills line, and the real profile's "Compute" section is a piece of prose
    — "a GPU is fast at many simple operations at once, which suits deep
    learning; most classical ML models run slower…". Reordering it TURNS AN
    ARGUMENT INSIDE OUT into nonsense, on the page sent to employers. 80 of
    120 CVs were hit.

    Told apart by SHAPE, not vocabulary: list items are short and carry no
    sentence-ending punctuation inside them.
    """
    if len(mon) < 3:
        return False
    return all(len(m.split()) <= _MON_DAI_NHAT and "." not in m for m in mon)


def _xep_mon(chu: str, wanted: set) -> str:
    """Move the items this posting asks for to the FRONT. Same words, new order.

    ONLY touches lines that are LISTS — see `_la_danh_sach`. The full stop at
    the end stays put: it is the LINE's punctuation, not the last item's.
    """
    het = chu.rstrip()
    cham = het.endswith(".")
    mon = _tach_mon(het[:-1] if cham else het)
    if not _la_danh_sach(mon):
        return chu
    # STABLE: items that hit nothing keep their old order, only hits move up.
    xep = sorted(range(len(mon)), key=lambda i: (-len(skills_in(mon[i]) & wanted), i))
    ra = ", ".join(mon[i] for i in xep)
    return ra + ("." if cham else "")


def asked_skills(explain: dict | None) -> set[str]:
    """Skills the posting REALLY ASKS FOR — from REQUIREMENT LINES only.

    It differs from `wanted_skills` in exactly one way, and that way decides
    the number on screen:

        wanted  scans the whole posting -> used to ORDER sentences. Wide is
                good: a false catch at worst misplaces a line, nobody sees it.
        asked   requirement lines only -> used as the DENOMINATOR of the
                fraction on screen. Wide here is A LIE.

    Measured on the real store: NXP "asks for" cloud — the word `cloud`
    appears only in the company's own blurb. Bank of America: 3 of the 4 words
    in the denominator came from the blurb. The result: the screen reported
    29% coverage while the actual page carried 63%, and it advised Vin not to
    apply to postings the page was answering well.
    """
    out: set[str] = set()
    for req in (explain or {}).get("requirements", []):
        out |= skills_in(req.get("text", ""))
    return out


def build(profile: dict, explain: dict | None, jd_text: str = "",
          num: dict | None = None, pick: dict | None = None) -> TailoredCV:
    from ..scoring.score import build_index, _matches

    blocks = parse(profile.get("cv_text") or "")
    wanted = wanted_skills(explain, jd_text)
    index = build_index(profile)
    header, summary = _identity(profile, blocks, wanted)

    # Which sentences ANSWER what this posting asks — sharing the index with
    # the scoring layer, so the two can no longer read the same sentence
    # differently.
    answers: dict[str, list[str]] = {}
    for signal in wanted:
        for ev in _matches(signal, index):
            if ev.kind:
                answers.setdefault(ev.text, []).append(signal)

    # TRIED AND DROPPED (10/09): filtering out every sentence that answers
    # nothing. Measured, it fails twice over. (1) The number of answering
    # sentences does NOT measure fit — it measures whether the JD happens to
    # name a lot of skills; `unlikely` postings average 10.1 sentences while
    # `likely` ones only 6.9, and Millennium at 84 points yielded EXACTLY ONE.
    # (2) Filtering on "does it prove a skill" cuts precisely the best
    # sentences: "self-funded, across 17 instruments and five years of data",
    # "I never budgeted the time a proof would take". Scale, scars and
    # judgement are not in vocab.SKILLS, and those are what persuade.
    #
    # So ANSWERING decides the ORDER and decides which blocks get cut, not
    # whether an individual sentence lives.
    # A BLOCK THAT DOES NOT FIT THIS POSTING DOES NOT GO ON. `cap` is a
    # CEILING, not a quota to fill — that is how `Compress EA` (0 skills,
    # fitting 0 of 117 postings) still appeared on 115 CVs, purely because
    # there were four projects and three slots.
    #
    # Filtered at BLOCK level, not SENTENCE level: sentence filtering by
    # keyword was tried and dropped, because it cut "self-funded, across 17
    # instruments" and "I never budgeted the time a proof would take" — scale
    # and scars are not in the vocabulary.
    sections: list[Section] = []
    # Sentences the RULES forbid, with the real reason. Collected here rather
    # than inferred later: inferred, every absent sentence gets the same
    # reason "weaker than what this posting asks for", and that is the WRONG
    # reason for a forbidden one — it is not weak, it does not belong on a CV.
    bi_cam: list[tuple[str, str]] = []
    for kind, cap in (("experience", rules.BUDGET["experience"]),
                      ("project", rules.BUDGET["project"])):
        chosen = [b for b in blocks if b.kind == kind and set(b.tags) & wanted]
        chosen.sort(key=lambda b: -len(set(b.tags) & wanted))
        # AN EXPERIENCE BLOCK IS NEVER DROPPED WHOLE — only projects may be.
        #
        # Filtering blocks on "does it hit what this posting asks" is right
        # for projects (a project is optional, dropping one leaves no trace).
        # For EXPERIENCE it punches a hole in the timeline: measured on the
        # real store, 6 of the top 12 CVs lost the block "Research Consultant
        # — WorldQuant, Jan–Sep 2025" entirely, i.e. the page being sent
        # declared a 9-month gap about itself.
        #
        # A gap costs far more than one loosely-related line: the HBS/
        # Accenture 2021 survey (8,000 workers, 2,250 hiring leaders, UK
        # included) found nearly half of employers screen out CVs with gaps
        # over 6 months. A loosely-related block costs three lines of paper.
        #
        # Still ORDERED by relevance: blocks that hit more come first. The
        # only difference is that a block hitting nothing goes last rather
        # than disappearing.
        # ALWAYS KEEP EVERY EXPERIENCE BLOCK. This was once a switch; dropped
        # because turning it off is always wrong: measured, 6 of 12 CVs lost
        # the WorldQuant Jan–Sep 2025 block entirely, i.e. the page being sent
        # declared a 9-month hole in its own timeline.
        if kind == "experience":
            con_lai = [b for b in blocks if b.kind == kind and b not in chosen]
            con_lai.sort(key=lambda b: -len(b.tags))
            chosen = chosen + con_lai
        if not chosen:
            # No block fits — 9 of 117 postings land here. An empty CV cannot
            # be sent, so take the strongest block and let that truth show.
            chosen = sorted((b for b in blocks if b.kind == kind),
                            key=lambda b: -len(b.tags))[:1]
        for block in chosen[:cap]:
            lines = _pick(block, wanted, answers,
                          rules.BUDGET["exp_bullets"],
                          bo=bi_cam, num=num, chon=pick)
            if lines:
                sections.append(Section(kind, block.title, block.meta, lines))

    for block in blocks:
        if block.kind == "education":
            keep = [Line(l) for l in block.lines if _worth(l)]
            sections.append(Section("education", block.title, block.meta, keep))
    certs = [l for b in blocks if b.kind == "cert" for l in b.lines if _worth(l)]
    if certs:
        sections.append(Section("cert", "", "", [Line(l) for l in certs]))
    # THE SKILLS SECTIONS — and this is where the app once tied its own hands
    # tightest.
    #
    # Measured on the real store: 98 DIFFERENT requirement sets across 120
    # postings, producing only 19 distinct CVs. 12 sentences appeared on
    # 120/120 CVs, 6 of them from skills sections — because skills sections
    # were poured out VERBATIM in profile order and never touched. And that
    # is the densest part of the page for keywords.
    #
    # REORDERING is the most HONEST tailoring left: no word added, no word
    # removed, only what this posting asks moved to the front. A CV screener
    # reads the first line of each section; `SQL` sitting at the end of the
    # fourth line may as well not be there. Measured: 19 -> 46 distinct CVs
    # when sections are ordered, -> 72 when items inside sections are too.
    # True to the founding rule: the machine SELECTS and ORDERS, it does not
    # write.
    muc_ky = []
    for block in blocks:
        # A skills section of nothing but adjectives, naming no technology.
        # This was once a switch; measured, keeping them adds +0 postings, so
        # it runs unconditionally.
        bo = rules.bo_muc_ky_nang(block.title, " ".join(block.lines))
        if block.kind == "skill" and not bo:
            muc_ky.append(block)
    rieng = (num or {}).get("rieng") or "rieng"
    if rieng in ("vua", "rieng"):
        muc_ky.sort(key=lambda b: -len(_ky_cua_muc(b) & wanted))
    for block in muc_ky:
        chu = " ".join(block.lines)
        if rieng == "rieng":
            chu = _xep_mon(chu, wanted)
        sections.append(Section("skill", block.title, "", [Line(chu)]))

    have: set[str] = set()
    for block in blocks:
        have |= set(block.tags)
    have |= skills_in(profile.get("skills_strong", "") + " "
                      + profile.get("skills_weak", ""))

    # WHY IT WAS DROPPED — two very different reasons, and the user needs to
    # be able to tell them apart:
    #   FORBIDDEN  the rules keep it off a CV (telling a failure, an opinion)
    #              -> rewriting the sentence will not help
    #   WEAKER     perfectly valid, but this posting asks about something else
    #              -> another posting will use it
    shown = {l.text for s in sections for l in s.lines}
    goc_hien = {l.goc or l.text for s in sections for l in s.lines}
    cam_text = {t for t, _ in bi_cam}
    dropped = list(dict.fromkeys(bi_cam))
    dropped += [(rules.clean(t), "weaker than what this posting asks for")
                for b in blocks if b.kind in ("experience", "project")
                for t in sentences(b)
                if rules.clean(t) not in shown
                and rules.clean(t) not in goc_hien
                and rules.clean(t) not in cam_text and _worth(t)]

    # WHAT THE PAGE CAN SAY — read off what is about to be printed, skills
    # sections INCLUDED. The old version only counted skills proved by the
    # chosen sentences, so the TECHNICAL SKILLS section printed on that very
    # page did not count.
    tren_giay: set[str] = set()
    for sec in sections:
        # SECTION TITLES ARE PRINTED TOO. `render.paper` prints them as
        # "<b>Git and GitHub</b> — every project version-controlled…", so
        # leaving titles out of the count under-reports: measured, `git` was
        # counted as missing on 14 of 287 postings while the word sat right
        # there on the page.
        tren_giay |= skills_in(sec.title)
        for line in sec.lines:
            tren_giay |= skills_in(line.text)
    doi = asked_skills(explain)
    return TailoredCV(header, summary, sections, dropped, sorted(wanted),
                      sorted({s for v in answers.values() for s in v} & wanted),
                      sorted(_real_missing(explain, wanted, have)),
                      asked=sorted(doi),
                      on_paper=sorted(doi & tren_giay))


def _real_missing(explain: dict | None, wanted: set[str], have: set[str]) -> set[str]:
    """Skills REALLY missing — "any of" lists do not count.

    The JD says "Programming in any of the following: C++, Java, MATLAB, R,
    Python" and you have C++ and Python, so Java/MATLAB/R are NOT missing.
    Reporting them here is a false alarm, and after a false alarm nobody reads
    the next one.
    """
    missing = wanted - have
    if not explain:
        return missing
    for req in explain.get("requirements", []):
        in_line = skills_in(req["text"])
        if in_line & have:                 # this line already has an answer
            missing -= in_line
    return missing


def _pick(block: Block, wanted: set[str], answers: dict, cap: int,
          bo: list | None = None, num: dict | None = None,
          chon: dict | None = None) -> list[Line]:
    """Sentences within a block: answering ones first, FORBIDDEN ones dropped.

    IT ASKS `rules.sentence_ok` — it used to NOT ask, and that was a real
    hole. The rules forbid sentences telling a failure and sentences of
    opinion, `cvhealth` reported them correctly, but this builder never
    consulted them so they went out anyway. Measured on the real profile on
    12/09: the Man Group CV carried 3 forbidden sentences, including "drawdown
    ran roughly 30% deeper than the model predicted".

    Three pieces — the rules, the per-line checker, the builder — sitting
    apart means the rules are only talk. This is the join.
    """
    num = num or {}
    kept: list[Line] = []
    for raw in sentences(block):
        goc = rules.clean(raw)
        if not _worth(goc):
            continue                      # "·", "Sep 2025" — PDF scrapings
        tags = sorted(skills_in(goc))
        phan, ly_do = rules.sentence_ok(goc, tags)
        if phan == "drop":
            if bo is not None:
                bo.append((goc, ly_do))
            continue
        # FIXED USING VIN'S OWN WORDS — see cv/rewrite.py. Fixed AFTER
        # judging, so the rules still read the sentence Vin wrote rather than
        # the machine's adjusted version.
        text, da_sua = rewrite.sua(goc)
        hits = sorted(set(answers.get(raw, [])) | set(answers.get(goc, [])))
        kept.append(Line(
            text, rules.sentence_weight(text, wanted, tags), hits,
            review=ly_do if phan == "review" else "",
            goc=goc, sua=da_sua,
            yeu=rewrite.diem_yeu(text, tags, wanted),
            vet=rewrite.vet(text, tags, wanted, da_sua)))
    # THE PERSON BEATS THE MACHINE. Vin pins a sentence and it goes on, low
    # weight or not; Vin drops one and it goes off, high weight or not. The
    # machine orders by a general rule, and Vin knows what a general rule
    # cannot — which way this posting leans, who he just spoke to.
    #
    # Pinning does NOT break the `cap` ceiling: one page is still one page.
    # Pin more than there are slots and the pins take every slot, which is
    # exactly what Vin meant.
    ghim = set((chon or {}).get("pin") or ())
    gat = set((chon or {}).get("drop") or ())
    kept = [l for l in kept if (l.goc or l.text) not in gat]
    kept.sort(key=lambda l: ((l.goc or l.text) not in ghim,
                             -len(l.hits), -l.weight))
    return kept[:cap]


def _worth(text: str) -> bool:
    """PDF scrapings: a lone bullet, a truncated date fragment. These used to
    reach the CV because `BUDGET` had empty slots to fill — "·" and "Sep 2025"
    went out on all 117 CVs."""
    body = text.strip().strip("·-–—• ")
    return len(body) >= 12 and any(c.isalpha() for c in body)


def _identity(profile: dict, blocks: list[Block],
              wanted: set[str]) -> tuple[list[str], str]:
    header = [profile.get("full_name") or "",
              " · ".join(x for x in [profile.get("location"), profile.get("phone"),
                                     profile.get("email")] if x)]
    links = (profile.get("links") or "").splitlines()
    if links:
        header.append(" · ".join(l.strip() for l in links if l.strip()))
    visa = next((" ".join(b.lines) for b in blocks
                 if b.kind == "header" and "visa" in " ".join(b.lines).lower()), "")
    if visa:
        header.append(visa)

    facts = []
    education = (profile.get("education") or "").splitlines()
    if education:
        facts.append(education[0].split("—")[0].strip())
    certs = (profile.get("certifications") or "").splitlines()
    if certs:
        facts.append(certs[0].split("—")[0].strip() if "—" in certs[0] else certs[0])
    strong = [s.strip() for s in (profile.get("skills_strong") or "").split(",") if s.strip()]
    want_norm = {norm(w) for w in wanted}
    hit = [s for s in strong if norm(s) in want_norm]
    rest = [s for s in strong if norm(s) not in want_norm]
    lead = (hit + rest)[:6]
    if lead:
        facts.append(" · ".join(lead))
    return header, " · ".join(f for f in facts if f)


# --- THE PERSON RE-PICKS: pin / drop, and the bench -------------------

def picks(conn, posting_id: int) -> dict:
    """Vin's picks for ONE posting: {'pin': [...], 'drop': [...]}."""
    ra: dict = {"pin": [], "drop": []}
    for row in conn.execute(
            "SELECT text, mode FROM cv_pick WHERE posting_id = ?", (posting_id,)):
        ra.setdefault(row["mode"], []).append(row["text"])
    return ra


def set_pick(conn, posting_id: int, text: str, mode: str) -> None:
    """Pin / drop a sentence. `mode=''` clears the pick, back to the machine's
    own ordering."""
    if not mode:
        conn.execute("DELETE FROM cv_pick WHERE posting_id = ? AND text = ?",
                     (posting_id, text))
    else:
        from ..core.postings import now
        conn.execute(
            "INSERT INTO cv_pick (posting_id, text, mode, made_at)"
            " VALUES (?, ?, ?, ?) ON CONFLICT(posting_id, text)"
            " DO UPDATE SET mode = excluded.mode, made_at = excluded.made_at",
            (posting_id, text, mode, now()))
    conn.commit()


def bench(profile: dict, cv: TailoredCV, block_title: str = "") -> list[dict]:
    """THE BENCH — rule-abiding sentences in the profile this CV did not pick.

    This is what makes "re-pick" a REAL choice rather than a promise: the
    machine writes no new sentence, it puts forward sentences Vin HAS ALREADY
    WRITTEN that were not called this time, ordered by how well they hit what
    THIS POSTING asks.

    Measured on the real profile: 10 bench sentences for one posting — enough
    for a swap to mean something.
    """
    in_ra = {l.goc or l.text for s in cv.sections for l in s.lines}
    # Uses the WIDE set: this is a "swap to this and you gain what" hint, not
    # a scoring number. Too narrow and every bench sentence reads "gains
    # nothing", leaving the user no grounds to choose.
    doi = set(cv.wanted)
    ra = []
    for block in parse(str(profile.get("cv_text") or "")):
        if block.kind not in ("experience", "project"):
            continue
        if block_title and block.title != block_title:
            continue
        for raw in sentences(block):
            text = rules.clean(raw)
            if text in in_ra or not _worth(text):
                continue
            phan, _ = rules.sentence_ok(text, sorted(skills_in(text)))
            if phan == "drop":
                continue
            trung = sorted(skills_in(text) & doi)
            ra.append({"text": text, "khoi": block.title, "trung": trung,
                       "diem": rules.sentence_weight(text, doi,
                                                     sorted(skills_in(text)))})
    # Sentences that hit what this posting asks come first — that is the
    # reason to swap to them.
    ra.sort(key=lambda x: (-len(x["trung"]), -x["diem"]))
    return ra
