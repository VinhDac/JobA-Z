"""Read an application form and sort each field into EXACTLY ONE of three
buckets.

    FILL   the machine can prove the answer   -> it fills it
    ASK    a question Vin has to decide       -> left empty, with a reason
    SKIP   demographics                       -> NOT TOUCHED, even if required

One field, one bucket, never two. A field no rule claims defaults to ASK —
when you do not know, ask; that is the only safe direction.

Matched by THE QUESTION rather than the field name: Greenhouse calls it
`first_name`, Ashby `_systemfield_name`, Lever `name`. All three ask "what is
your name". Keying on field names is three rule sets; keying on the question
is one.
"""

from __future__ import annotations

import json
import re

FILL, ASK, SKIP = "fill", "ask", "skip"

# --- SKIP -----------------------------------------------------------------
# Legally protected characteristics. The machine does not answer these on a
# person's behalf, even when the form marks them required. Vin chooses,
# including choosing "prefer not to say".
NEVER = re.compile(
    r"gender|\bsex\b|\brace\b|ethnic|hispanic|latin[ox]|veteran|militar|"
    r"armed forces|disabilit|"
    r"disabled|sexual orientation|lgbt|transgender|pronoun|self identif|"
    r"equal opportunit|eeoc|protected (class|characteristic)")

# --- ASK ------------------------------------------------------------------
# Each entry carries a REASON, because the reason is what Vin reads to know
# what to do.
ASK_RULES: list[tuple[re.Pattern, str]] = [
    # Greenhouse/Lever's most common phrasing is REVERSED: "authorized to
    # work in this country". The old version only caught "work authoriz…" in
    # that exact order, so the reversed phrasing fell through to the FILL rule
    # for `country` and the machine answered a Yes/No question about the right
    # to work with the words "United Kingdom".
    (re.compile(r"sponsor|visa|right to work|immigration|"
                r"work (authoris|authoriz)|(authoris|authoriz)\w*\s+to work|"
                r"legally (authoris|authoriz)|eligib\w*\s+to work|"
                r"work permit|permitted to work"),
     "one wrong word ruins the application — Graduate visa: NO sponsorship "
     "needed now, YES in future"),
    # Nationality / country of birth is NOT where you live. The old version
    # let every field containing "country" fall into the FILL rule and
    # answered with the country of residence.
    (re.compile(r"citizen|nationalit|country of birth|born in|place of birth|"
                r"passport|domicile|country of origin"),
     "legal status — Vin is a Vietnamese national living in the UK on a "
     "Graduate visa"),
    (re.compile(r"\bgpa\b|grade point|classification|predicted grade"),
     "the MSc has no final grade yet; the BA is 3.59/4.0"),
    (re.compile(r"graduat\w*|expected completion|when .* finish"),
     "Vin graduates in 2026 — a wrong guess is an outright rejection"),
    (re.compile(r"salary|compensation|expected pay|day rate|remuneration"),
     "this number is Vin's own call"),
    (re.compile(r"cover letter|why (do|are) you|motivat|tell us|describe|"
                r"what interests|in your own words"),
     "this one is written by hand, not assembled"),
    (re.compile(r"notice period|start date|earliest|available from|when can you"),
     "depends on Vin's own schedule"),
    (re.compile(r"relocat"), "Vin's own call"),
    (re.compile(r"criminal|conviction|background check|dbs"), "a legal declaration"),
    (re.compile(r"agree|consent|acknowledg|privacy|terms|gdpr|data protection"),
     "agreeing to terms is a signature — only Vin can click it"),
    # \b: the string "referr" sits INSIDE the word "preferred", so every
    # "Preferred name" field landed in the ASK bucket and Vin typed his own
    # name by hand every time.
    (re.compile(r"how did you hear|\breferr|\bsource\b|who referred"),
     "Vin picks this himself"),
    (re.compile(r"cover_letter|coverletter"), "no cover-letter file yet"),
]

# --- FILL -----------------------------------------------------------------
# Verifiable facts, taken from answer.book(). The order matters: narrow rules
# come before broad ones ("first name" before "name").
FILL_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"first name|given name|forename|\bfname\b"), "first_name"),
    (re.compile(r"last name|family name|surname|\blname\b"), "last_name"),
    (re.compile(r"preferred name|nickname|preferred first"), "first_name"),
    (re.compile(r"linkedin"), "linkedin"),
    (re.compile(r"github"), "github"),
    (re.compile(r"website|portfolio|personal site|blog|web page"), "website"),
    (re.compile(r"e ?mail"), "email"),
    (re.compile(r"phone|mobile|telephone|contact number"), "phone"),
    (re.compile(r"country"), "country"),
    (re.compile(r"\bcity\b|town"), "city"),
    (re.compile(r"location|where are you based|current residence|address"), "location"),
    (re.compile(r"school|universit|college|institution|alma mater"), "school"),
    (re.compile(r"discipline|major|field of study|course|subject"), "discipline"),
    (re.compile(r"degree|qualification|level of study|education level"), "degree"),
    (re.compile(r"(start|from)[^a-z]*month"), "edu_start_month"),
    (re.compile(r"(start|from)[^a-z]*year"), "edu_start_year"),
    (re.compile(r"(end|to|finish)[^a-z]*month"), "edu_end_month"),
    (re.compile(r"(end|to|finish)[^a-z]*year"), "edu_end_year"),
    (re.compile(r"full name|your name|\bname\b"), "full_name"),
]

RESUME = re.compile(r"resume|\bcv\b|curriculum")

# Signals that this is a QUESTION rather than the label of a data field.
#
# FILL rules match substrings, so "Do you have a valid driving licence for
# work in your city?" hits the `city` rule and the machine types "London" into
# it. A real data-field label is short and asks nothing: "City", "Country",
# "Phone". A question has a subject and a question mark. Seeing question
# signals -> leave it for Vin.
ASKING = re.compile(
    r"\b(do|did|does|are|is|have|has|will|would|can|could|should|were|was)\s+you"
    r"|\byou\b.{0,24}\?|^\s*(why|how|what|which|when|where|who)\b"
    r"|\bplease (tell|describe|explain|list|confirm)\b")

# Read every visible field and give each an index so filling cannot get lost.
#
# THREE THINGS LEARNED FROM A REAL FORM (Point72, Greenhouse Remix 2025):
#
# 1. There is no <select> left. Everything that looks like a dropdown is an
#    input[role=combobox] — react-select. Setting .value on it only types
#    into the FILTER box and selects nothing; and `el.value` afterwards
#    equals exactly what was typed, so that kind of check REPORTS FALSE
#    SUCCESS. Measured: 4 such fields.
# 2. Beside each combobox is a SHADOW input: no name, no id, there only so
#    react can show "required". Having no label it borrows its neighbour's ->
#    every question appears twice. A field with neither name nor id is not
#    read by the form; drop it.
# 3. A multiple-choice question is N checkboxes sharing ONE name. Read
#    separately, "London", "Paris" and "Hong Kong" become three separate
#    required questions — meaningless. Grouped by name, one question per row.
READ_JS = r"""
(() => {
  const seen = [], out = [];
  const clean = t => (t || '').replace(/\s+/g, ' ').trim();
  const own = el => {
    let t = '';
    if (el.id) { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
                 if (l) t = l.innerText; }
    if (!t && el.closest('label')) t = el.closest('label').innerText;
    if (!t) t = el.getAttribute('aria-label') || '';
    if (!t) { const by = el.getAttribute('aria-labelledby');
              if (by) { const n = document.getElementById(by); if (n) t = n.innerText; } }
    return clean(t).slice(0, 200);
  };
  // The SHARED question of a checkbox group: walk up looking for a label
  // that is not this field's own.
  const groupLabel = (el, mine) => {
    const fs = el.closest('fieldset');
    if (fs) { const lg = fs.querySelector('legend'); if (lg) return clean(lg.innerText).slice(0, 200); }
    let p = el.parentElement, hop = 0;
    while (p && hop++ < 5) {
      for (const c of p.querySelectorAll('label,legend,[class*="label"]')) {
        const t = clean(c.innerText);
        if (t && t !== mine && t.length > 2) return t.slice(0, 200);
      }
      p = p.parentElement;
    }
    return '';
  };
  document.querySelectorAll('input,select,textarea').forEach(el => {
    const type = (el.type || '').toLowerCase();
    if (['hidden','submit','button','image','reset'].includes(type)) return;
    if (el.disabled) return;
    // A LOCKED (readOnly) field still BELONGS in the list. Date pickers
    // often lock the text box to force use of the calendar, and that field
    // is usually REQUIRED. Leave it out and missing() cannot see it, and the
    // machine presses Send on an application with no graduation date. Keep
    // it, mark it locked, and let Vin pick.
    const locked = !!el.readOnly;
    // A shadow field (neither name nor id) is not read by the form — DROP
    // it, EXCEPT file inputs: many ATSes hide <input type=file> with no name
    // and no id, driven entirely by JS. Dropping it sends an application
    // with NO CV and nobody says so.
    if (!el.name && !el.id && type !== 'file') return;
    if (type !== 'file' && !el.offsetParent) return;
    const n = seen.length; seen.push(el); el.setAttribute('data-jb', n);

    const combo = el.getAttribute('role') === 'combobox'
               || /select__input/.test(el.className || '');
    const kind = el.tagName === 'SELECT' ? 'select'
               : el.tagName === 'TEXTAREA' ? 'textarea'
               : combo ? 'combo'
               : type;
    const mine = own(el);
    const grouped = (type === 'checkbox' || type === 'radio');
    // The label USED FOR MATCHING. For a grouped field, each option's label
    // is "London" or "Yes" — with no * anywhere, so a `required` flag
    // computed from it is always false and missing() cannot see an empty
    // required sponsorship question.
    const lab = grouped ? (groupLabel(el, mine) || mine) : (mine || el.placeholder || '');
    // The CURRENT value. For a dropdown the real value is not in el.value
    // (that is just the filter box) but in the "chip" drawn inside the
    // wrapper.
    let now = '';
    if (grouped) now = el.checked ? (mine || 'x') : '';
    else if (combo) {
      const ctl = el.closest('[class*="control"]');
      const chip = ctl && ctl.querySelector('[class*="ingleValue"], [class*="ingle-value"],'
                                          + '[class*="ultiValue"], [class*="ulti-value"]');
      now = chip ? clean(chip.innerText) : '';
    } else if (type === 'file') now = (el.files && el.files.length) ? el.files[0].name : '';
    else now = el.value || '';
    out.push({
      k: n, name: el.name || '', dom_id: el.id || '', kind: kind,
      label: lab,
      option: grouped ? mine : '',
      group: grouped ? (el.name || el.id) : '',
      required: !!(el.required || el.getAttribute('aria-required') === 'true'
                   || /[*✱]/.test(lab)),
      locked: locked,
      value: now,
      options: el.tagName === 'SELECT'
             ? Array.from(el.options).map(o => clean(o.text)).filter(Boolean).slice(0, 60) : [],
    });
  });
  return JSON.stringify(out);
})()
"""


# Programmer-style field names: firstName, opportunityLocationId.
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
# The site's internal identifier fields, not questions for a person.
INTERNAL = re.compile(r"\bid\b$|\buuid\b|\btoken\b|\bcsrf\b")


def _ask(text: str) -> str:
    """The question reduced to a matchable form: camelCase split, lowercased,
    letters and digits only."""
    return re.sub(r"[^a-z0-9]+", " ", _CAMEL.sub(" ", text or "").lower()).strip()


def classify(field: dict) -> tuple[str, str]:
    """This field -> (bucket, key-or-reason). The first matching rule wins."""
    asked = _ask(f"{field.get('label','')} {field.get('name','')} {field.get('dom_id','')}")
    if not asked:
        return ASK, "unlabelled field"
    # No human-readable label, and the name is an internal identifier
    # (Lever: `opportunityLocationId`) — that is not a question. Guessing
    # means filling in nonsense. Uses the SPLIT form, because this rule needs
    # word boundaries.
    if not field.get("label") and INTERNAL.search(asked):
        return ASK, "an internal field of the site"

    # Matched against BOTH forms. Splitting camelCase helps
    # `opportunityLocationId`, but it also breaks "LinkedIn" into "linked in"
    # and "GitHub" into "git hub" — the `linkedin` rule misses and the
    # LinkedIn field silently becomes "needs you" with no reason.
    hay = f"{asked} {asked.replace(' ', '')}"
    if NEVER.search(hay):
        return SKIP, ""
    if field.get("kind") == "file":
        return (FILL, "resume") if RESUME.search(hay) else (ASK, "another attachment")
    for rule, reason in ASK_RULES:
        if rule.search(hay):
            return ASK, reason
    asking = bool(ASKING.search(asked)) or asked.count(" ") >= 8
    for rule, key in FILL_RULES:
        if rule.search(hay):
            # A long question with the subject "you" or a question mark is
            # not a data field — even if it happens to mention "city" or
            # "country".
            if asking:
                return ASK, "a question, not a data field — the machine does not guess"
            return FILL, key
    return ASK, ""


def read(tab) -> list[dict]:
    """Every field of the open form, already grouped and bucketed."""
    raw = tab.eval(READ_JS) or "[]"
    out: list[dict] = []
    groups: dict[str, dict] = {}
    for f in json.loads(raw):
        if f["group"]:
            head = groups.get(f["group"])
            if head is None:
                f["options"] = [f["option"]] if f["option"] else []
                groups[f["group"]] = f
                out.append(f)
            else:
                if f["option"]:
                    head["options"].append(f["option"])
                head["required"] = head["required"] or f["required"]
                head["value"] = head.get("value") or f.get("value", "")
            continue
        out.append(f)
    for f in out:
        f["bucket"], f["key"] = classify(f)
        # A locked field cannot be typed into — only picked with the widget.
        # Keep it in the list so missing() can see it, but do not let fill()
        # go typing.
        if f.get("locked") and f["bucket"] == FILL:
            f["bucket"], f["key"] = ASK, "locked field — pick it with the page's calendar/widget"
    return out
