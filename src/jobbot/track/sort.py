"""What this mail says — and which application it belongs to.

A SEPARATE mailbox for job hunting makes the problem far lighter: nearly
every message is recruiting mail, so this is CLASSIFYING, not FILTERING. A
main mailbox would have to guess among invoices, friends and adverts.

Mail PROPOSES a status change, it does NOT make one. An "unfortunately" mail
could be a rejection, or it could be the opening line of an interview
reschedule. Guess wrong and write it, and the table is wrong with no way for
Vin to know.
"""

from __future__ import annotations

import re

from ..ingest.base import norm
from .board import INTERVIEW, OFFER, REJECTED, SENT

# The ORDER MATTERS: strongest outcome first. An interview invitation still
# usually opens with "thank you for applying" — catching "confirm" first
# files the most important mail as an acknowledgement.
RULES = [
    (OFFER, re.compile(
        r"\b(offer of employment|pleased to offer|we would like to offer|"
        r"offer letter|congratulations[^.]{0,40}offer)\b", re.I)),
    (INTERVIEW, re.compile(
        r"\b(invit\w* (?:you )?(?:to|for) (?:an? )?"
        r"(?:interview|call|chat|conversation)|"
        r"invitation to (?:an? )?interview|interview invitation|"
        r"would like to invite|would like to (?:meet|speak|chat|talk)|"
        r"schedule (?:a |an )?(?:call|interview|chat)|book a time|"
        r"next (?:round|stage)|first[- ]round|online assessment|"
        r"coding (?:test|challenge)|hackerrank|codility|karat)\b", re.I)),
    # Measured on real subject lines: the old version missed "decided not to
    # move forward" (it only had "moving") and "won't be taking your
    # application further" (only "take"). Missing here is the worst kind of
    # miss: a rejection falling into "other" gets `needs_you = 0`, never
    # appears, and the table says "waiting" forever for a dead application.
    (REJECTED, re.compile(
        r"\b(not (?:be )?(?:mov\w+|progress\w+|proceed\w+) forward|"
        r"will not be (?:progressing|proceeding|moving)|"
        r"decided not to (?:proceed|continue|mov\w+ forward)|"
        r"(?:not|won'?t)[^.]{0,24}your application (?:any )?further|"
        r"not (?:been )?successful|unsuccessful|"
        r"not (?:the )?right (?:fit|match)|"
        r"other candidates|unable to offer you|regret to inform)\b", re.I)),
    (SENT, re.compile(
        r"\b(thank you for (?:applying|your application)|"
        r"we(?:'ve| have) received your application|application received|"
        r"your application (?:to|for|has been received))\b", re.I)),
]

# THE POSTMAN, NOT THE EMPLOYER. Three groups, one consequence: their name
# is NEVER the company's, and the real company name is in the text.
#
# Measured on the real mailbox, 60 days, 56 mails with an outcome: the worst
# error on the whole table was the INTERVIEW INVITATION — the most important
# row — recorded under "GoHire", a recruiting software vendor. The real
# company was Kappa Lab, sitting in both the subject ("Kappa Lab Interview")
# and the body ("Thank you for applying to Kappa Lab"). Likewise: Workable
# hid Flowdesk, Longshot Systems and G-20 Group.
ATS_HOST = re.compile(
    r"(greenhouse|lever|ashbyhq|ashby|workday|myworkday|smartrecruiters|icims|"
    r"successfactors|teamtailor|pinpointhq|jobvite|bamboohr|ripplematch|"
    r"workable|gohire|broadbean|recruiterflow|recruitee|breezy|jazzhr|"
    r"applytojob|personio|taleo|brassring|avature|eightfold|phenom|"
    # the job table: the postman, not the employer
    r"linkedin|indeed|glassdoor|ziprecruiter|totaljobs|reed\.co|cv-library|"
    r"efinancialcareers|otta|welcometothejungle|jobtoday)",
    re.I)

# STRONG OUTCOMES — these three cannot be matched by accident from an
# administrative email. No tax office writes "we would like to invite you to
# interview".
#
# `applied` is WEAK: "Your application for a National Insurance number"
# matches it on the single word "application".
MANH = (INTERVIEW, OFFER, REJECTED)

# DOMAINS THAT SEND ADMINISTRATIVE MAIL. A BROAD list, deliberately, and it
# is only safe because of the STRONG rule above.
#
# It can override WEAK evidence — measured on the real mailbox, "Your
# application for a National Insurance number" once produced a job row called
# "Apply for a
# National Insurance num".
#
# But it CANNOT override a STRONG outcome. In the UK the Civil Service and
# the NHS are the two largest employers in the country; the previous version
# forced their interview invitations to "other", needs_you = 0, and the mail
# vanished from every screen.
#
# The trade: an "application received" mail from the Civil Service does not
# create a row on its own. Acceptable — losing an acknowledgement row is far
# lighter than losing an invitation.
KHONG_PHAI_VIEC = re.compile(
    r"(service\.gov\.uk|gov\.uk|hmrc|dvla|nhs\.uk|\.edu$|companieshouse)", re.I)

# The company name is in the TEXT. Ordered most-certain first — the first
# match wins. The patterns come from 56 real mails, not from guesswork.
TRONG_CHU = (
    re.compile(r"thanks?(?: you)? for (?:applying|submitting your application)"
               r" (?:to|for) (.{2,160})", re.I),
    re.compile(r"thanks?(?: you)? for your (?:application|interest)"
               r" (?:to|in) (.{2,160})", re.I),
    re.compile(r"(?:we(?:'ve| have) )?received your application (?:to|for) (.{2,160})", re.I),
    re.compile(r"your application (?:to|for) (.{2,160})", re.I),
    re.compile(r"thanks?(?: you)? from (.{2,60})", re.I),
    re.compile(r"^(.{2,40}?) (?:interview|hiring team|careers team)\b", re.I),
)

# THE COMPANY NAME COMES AFTER THE LAST `at`. This is the rule that rescues
# the most rows, and it comes straight from the real mailbox:
#     "Your application to Quantitative Researcher at Durlston Partners"
#     "interest in the Machine Learning Engineer position at IMC"
#     "interest in career opportunities at Schonfeld"
# With no `at`, the captured span is the company name itself.
_SAU_AT = re.compile(r"\bat\s+(.+)$", re.I | re.S)

# Tails after a company name: punctuation, greetings, linking verbs.
_DUOI_TEN = re.compile(
    r"\s*(?:[,|!.:;]|\band (?:for|your|taking)\b|\brole\b|\bposition\b|"
    r"\bis\b|\bhas\b|\bwas\b|\bwill\b|\bteam will\b).*$",
    re.I | re.S)

# THIS TEXT IS A ROLE, NOT A COMPANY. The most important remaining guard:
# "we've received your application for Quantitative Trading Analyst" — bắt
# captures a job title, and the table grows a "company" called "Quantitative
# Trading Analyst". Only trusted when the sentence has an `at` separating
# role from company; without one it is better not to guess.
LA_VAI_TRO = re.compile(
    r"\b(engineer|developer|analyst|researcher|scientist|trader|manager|"
    r"associate|consultant|intern(ship)?|specialist|architect|quant\w*|"
    r"programme|program|graduate|officer|lead|director|assistant|advisor|"
    r"strategist|technologist|administrator)\b", re.I)

# Articles / HTML junk stuck to the front of the captured span.
_DAU_THUA = re.compile(r"^(?:the|a|an|our|your|from)\s+", re.I)
_RAC_HTML = re.compile(r"&[a-z]+;|&#\d+;|[\u200b\u200c\u00a0]")

# What is left after stripping head and tail, if it lands in here, is NOT a
# company name. "Talent Acquisition" strips "Talent" and leaves "Acquisition";
# "GD Notification" leaves "GD". Both reached the table as company names.
KHONG_PHAI_TEN = re.compile(
    r"^(acquisition|notifications?|team|hiring|careers?|recruit\w*|talent|"
    r"people|hr|jobs?|apply|application|admin|info|support|mail|no ?reply|"
    r"do ?not ?reply|gd|ta|confirmation)$", re.I)

# Filler in a subject line; strip it and the company / role remains.
NOISE = re.compile(
    r"\b(re|fwd|your application|application (?:for|to|update|status)|"
    r"thank you for applying|update on your application)\b[:\s-]*", re.I)


def kind(msg: dict) -> str:
    """-> 'offer' | 'interview' | 'rejected' | 'applied' | 'other'."""
    blob = f"{msg.get('subject', '')} {msg.get('snippet', '')}"
    for name, pattern in RULES:
        if pattern.search(blob):
            return name
    return "other"


# Tails in a sender name: "Jump Trading Recruiting" -> "Jump Trading".
ROLE_TAIL = re.compile(
    r"\s*\b(recruit(ing|ment)?|talent( acquisition)?|careers?|hr|people|"
    r"hiring|no[- ]?reply|team|notifications?)\b\s*$", re.I)

ROLE_HEAD = re.compile(
    r"^(careers?|recruit(ing|ment)?|talent|no[- ]?reply|hr|hiring|jobs?)"
    r"\s*(at|@|-|\|)?\s*", re.I)


def _clean_name(text: str) -> str:
    out = ROLE_HEAD.sub("", text or "").strip(" .,|-")
    for _ in range(3):                       # "X Talent Acquisition Team"
        cut = ROLE_TAIL.sub("", out).strip(" .,|-")
        if cut == out:
            break
        out = cut
    # A FUNCTION WORD LEFT AFTER STRIPPING is not a company name. Measured on
    # the real mailbox: "Talent Acquisition" left "Acquisition", "GD
    # Notification" left "GD" — both reached the table as company names.
    return "" if KHONG_PHAI_TEN.match(out.strip()) else out


# The label before the real domain: "st.griddynamics.net" -> "griddynamics",
# not "st". Taking the first label takes a hostname, not a company.
_PHU = {"mail", "email", "mailer", "smtp", "no-reply", "noreply", "notify",
        "notification", "notifications", "st", "us", "eu", "uk", "hire",
        "candidates", "jobs", "careers", "apply", "info", "my", "www"}


def _ten_mien(host: str) -> str:
    phan = [x for x in (host or "").lower().split(".") if x]
    if len(phan) < 2:
        return phan[0] if phan else ""
    # Drop the TLD (and two-part TLDs like .co.uk), then the leading labels.
    loi = phan[:-2] if phan[-2] in ("co", "com", "org", "net", "ac", "gov") \
        and len(phan) > 2 else phan[:-1]
    loi = [x for x in loi if x not in _PHU] or loi
    return loi[-1] if loi else ""


def _got(doan: str) -> str:
    """From a captured span -> A COMPANY NAME, or "" when unsure.

    Three steps, in order:
        1  take what follows the LAST `at` — what precedes it is the role
        2  cut tails and articles, clean HTML junk
        3  still carrying a job title with NO `at` separator -> do not guess

    Step 3 is the guard: "received your application for Quantitative Trading
    Analyst" captures a job title, and the table grows a "company" by that
    name. Better to fall through to the domain — mavensecurities.com is still
    right.
    """
    doan = _RAC_HTML.sub(" ", doan or "")
    doan = " ".join(doan.split())             # subject lines contain newlines
    m = _SAU_AT.search(doan)
    co_at = bool(m)
    if m:
        doan = m.group(1)
    doan = _DUOI_TEN.sub("", doan)
    doan = _DAU_THUA.sub("", doan).strip(" -–—|:")
    # A CAPITALISED PROPER NOUN. A general rule, not a list: the word after
    # `at` in "unable to give further feedback at this stage" is "this",
    # lowercase — and it reached the table as a company called "this stage".
    # Every phrase like "at the moment", "at least" and "at scale" dies by
    # the same rule, with no extra line.
    if doan and not (doan[0].isupper() or doan[0].isdigit()):
        return ""
    if not co_at and LA_VAI_TRO.search(doan):
        return ""
    # A WHOLE SENTENCE is not a name. "from mcgregorboyall Thank you for your
    # application" once reached the table verbatim as a company name.
    if len(doan.split()) > 8 or re.search(r"\bthank|\bapplication\b", doan, re.I):
        return ""
    return _clean_name(doan)


def _tu_chu(nguon: str) -> str:
    """The company name inside ONE piece of text — a subject, or the first
    lines of a body."""
    nguon = " ".join((nguon or "").split())
    for mau in TRONG_CHU:
        m = mau.search(nguon)
        if not m:
            continue
        ten = _got(m.group(1))
        # Do not accept the software vendor's own name ("applying to Workable").
        if ten and len(ten) <= 46 and not ATS_HOST.search(ten):
            return ten[:60]
    return ""


def company_of(msg: dict) -> str:
    """Guess the company — THE TEXT FIRST, the sender second.

    THIS ORDER IS THE WHOLE PROBLEM. The old version trusted the sender name
    first, while most recruiting mail today is sent on the employer's behalf
    by software: Greenhouse, Workable, Ashby, GoHire, Workday. Their name is
    what appears in "From", while the real company sits in the sentence
    "Thank you for applying to …".

    Measured on the real mailbox's 56 mails with an outcome: trusting the
    sender first labelled the INTERVIEW INVITATION "GoHire" instead of Kappa
    Lab, and merged three applications sent through Workable into one
    "Workable" row.
    """
    host = (msg.get("from_addr") or "").split("@")[-1]
    la_trung_gian = bool(ATS_HOST.search(host))

    # 1. THE SUBJECT — the most reliable text, and the ONLY route when a
    #    third party sends on the employer's behalf. Kappa Lab's interview
    #    invitation came through GoHire: the real name is only here.
    ten = _tu_chu(msg.get("subject") or "")
    if ten:
        return ten

    # 2. THE SENDER NAME — as long as it is not the postman's own name.
    #
    #    BEFORE THE BODY, not after. The body is the noisiest place:
    #    Flowdesk's mail opens "We have received your application for the
    #    Technology | Quantitative Developer (Low Latency) | London", and
    #    capturing there gives "Technology" while From already says
    #    "Flowdesk".
    #
    # Do NOT block by HOST here. Ashby and SmartRecruiters send on behalf but
    # still put THE COMPANY's name in From ("Midnite Talent Team", "Ayming",
    # "Monad Foundation Hiring"); blocking the whole host throws those correct
    # names away. Block only when THE NAME ITSELF is the vendor's — GoHire,
    # Workable, LinkedIn.
    name = _clean_name(msg.get("from_name") or "")
    if name and not ATS_HOST.search(name):
        return name[:60]

    # 3. THE BODY — noisier than the subject, but it rescues mail whose
    #    subject only says
    #    chức danh: "we've received your application for Quantitative Trading
    #    Analyst" / body: "Thanks for applying to Maven."
    ten = _tu_chu(msg.get("snippet") or "")
    if ten:
        return ten

    # 4. THE DOMAIN — the label before the TLD, not the first label.
    if host and not la_trung_gian:
        goc = _ten_mien(host)
        if goc:
            return goc.replace("-", " ").title()[:60]

    # 5. LAST: the subject tail after a dash — "… - Qube Research". It still
    #    goes through `_got` rather than being written directly: this branch
    #    once put the whole sentence "from mcgregorboyall Thank you for your
    #    application" on the table as a company name, because it bypassed
    #    every guard above.
    head = NOISE.sub("", msg.get("subject") or "").strip(" -–—|:")
    if re.search(r"\s[-–—|]\s", head):
        return _got(re.split(r"\s[-–—|]\s", head)[-1])[:60]
    return "" if la_trung_gian else _got(head)[:60]


# THE ROLE comes BEFORE `at`, the company after. One sentence, two halves:
#     "your application to Quantitative Researcher at Durlston Partners"
#     "interest in the Machine Learning Engineer position at IMC"
# Throwing away the first half loses the table's `role` column, and loses the
# only thing separating "Schonfeld · Quant Research Intern" from the other 70
# Schonfeld postings.
_TRUOC_AT = re.compile(r"^(.+?)\s+\bat\s+\S", re.I | re.S)

# Wrapping around a job title; strip it and the title remains.
_VO_VAI_TRO = re.compile(
    r"\b(the|a|an|our|your|for|to|position|role|opening|opportunity|vacancy|"
    r"job)\b", re.I)


def role_of(msg: dict) -> str:
    """The role applied for, read from the mail itself. "" if it does not say.

    Only accepted when the sentence has an `at` separator — without one there
    is no way to tell whether the captured span is a job title or a company,
    and guessing turns the `role` column into a bin.
    """
    for nguon in (msg.get("subject") or "", msg.get("snippet") or ""):
        nguon = " ".join((nguon or "").split())
        for mau in TRONG_CHU:
            m = mau.search(nguon)
            if not m:
                continue
            truoc = _TRUOC_AT.match(_RAC_HTML.sub(" ", m.group(1)))
            if not truoc:
                continue
            ten = " ".join(_VO_VAI_TRO.sub(" ", truoc.group(1)).split())
            ten = ten.strip(" -–—|:,.")
            if ten and LA_VAI_TRO.search(ten) and len(ten) <= 70:
                return ten
    return ""


def match_posting(conn, company: str, role: str = "") -> int | None:
    """Which posting in the store this application corresponds to. None if it
    was applied to outside the app.

    MATCH THE COMPANY FIRST, THEN THE ROLE. One company can have 70 postings
    in the store (greenhouse:schonfeld), so matching only the company name
    identifies the company but not WHICH posting was applied to — and the
    detail page would open a completely different JD.

    When it cannot be resolved it returns None. The table saying "applied
    outside the app" is the truth; pointing at a roughly similar posting is a
    lie in a place the user cannot check.
    """
    key = norm(company or "").replace(" ", "")
    if len(key) < 3:
        return None
    hang = conn.execute(
        "SELECT id, title, company FROM posting"
        " WHERE REPLACE(LOWER(REPLACE(company, ' ', '')), '.', '') LIKE ?"
        " ORDER BY kept DESC, score DESC", (f"%{key[:16]}%",)).fetchall()
    if not hang or not role:
        # NO ROLE MEANS NO LINK. One posting for the company is not enough
        # either: Acadian has exactly one — "VP, Portfolio Manager" — while
        # the user is a recent graduate. A posting from the same company is
        # NOT the posting applied to.
        return None
    rn = norm(role)
    for r in hang:
        tn = norm(r["title"])
        if not tn:
            continue
        # An exact match, or one containing the other with only a few extra
        # words. "Quant Researcher" and "Senior Quant Researcher" are TWO
        # different postings; "Quant Developer" and "Quant Developer
        # (Systematic)" are one.
        if tn == rn or ((rn in tn or tn in rn)
                        and abs(len(tn) - len(rn)) <= 14):
            return int(r["id"])
    return None


def match(conn, msg: dict) -> int | None:
    """Which application this mail belongs to. Matched on the NORMALISED
    COMPANY NAME.

    It also compares the space-stripped form: a domain has no separators, so
    the guess comes out "Mangroup" while the table says "Man Group". Guessing
    has error in it; the matching has to tolerate that rather than demanding
    perfect guesses.

    No match returns None, and the mail stays on the "needs Vin" strip — it
    points, rather than guessing and writing into the wrong row.
    """
    guess = norm(company_of(msg))
    if not guess:
        return None
    tight = guess.replace(" ", "")
    hits = []
    for row in conn.execute("SELECT id, company_key, role FROM application"):
        key = (row["company_key"] or "").strip()
        if not key:
            continue
        flat = key.replace(" ", "")
        # A SHORT name inside a longer one: "imc" is inside
        # "imctradinggroup", "man" is inside "freshman". A short name must be
        # long enough before a contains-match is allowed; shorter than that
        # requires an exact match.
        short = min(len(flat), len(tight))
        loose = short >= 5
        same = flat == tight
        inside = loose and (key in guess or guess in key
                            or flat in tight or tight in flat)
        if same or inside:
            hits.append(row)
    if not hits:
        return None
    if len(hits) == 1:
        return int(hits[0]["id"])

    # ONE company, MANY applications. Taking the first row changes another
    # application's status: a rejection for role A closes role B, which was
    # awaiting an interview. The role is considered too; when it cannot be
    # resolved it returns None for Vin to point, because "do not know" beats
    # "know wrongly".
    blob = norm(f"{msg.get('subject', '')} {msg.get('snippet', '')}")
    named = [r for r in hits if (r["role"] or "").strip()
             and norm(r["role"]) in blob]
    return int(named[0]["id"]) if len(named) == 1 else None
