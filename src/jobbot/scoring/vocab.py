"""The vocabulary for recognising what a requirement line is asking for.

No LLM here. Deliberately:
  - Runs over 4,000 postings for nothing
  - The same input always gives the same output -> testable -> catches bugs
  - An LLM is reserved for where string matching genuinely gives up (step 2b)

The vocabulary leans quant / finance / data — the user's actual band. A
missing word gets added here, not fixed somewhere else.
"""

from __future__ import annotations

import re

# ----------------------------------------------------------------- skills
# key = the canonical name, value = other spellings (already normalised)
SKILLS: dict[str, set[str]] = {
    # languages
    "python": {"python", "python3"},
    "c++": {"c++", "cpp"},
    "java": {"java"},
    "scala": {"scala"},
    "go": {"go", "golang"},
    "rust": {"rust"},
    "r": {" r ", "r language"},
    "matlab": {"matlab"},
    "sql": {"sql", "postgres", "postgresql", "mysql", "t-sql"},
    "kdb": {"kdb", "kdb+", "q language"},
    "javascript": {"javascript", "typescript", "js"},
    "excel": {"excel", "vba"},
    # dữ liệu / ML
    "pandas": {"pandas"},
    "numpy": {"numpy"},
    "scipy": {"scipy"},
    "scikit-learn": {"scikit-learn", "sklearn", "scikit learn"},
    "pytorch": {"pytorch", "torch"},
    "tensorflow": {"tensorflow", "keras"},
    "spark": {"spark", "pyspark"},
    "machine learning": {"machine learning", "ml ", "supervised learning"},
    "deep learning": {"deep learning", "neural network", "neural networks"},
    "nlp": {"nlp", "natural language processing", "llm", "large language model"},
    "time series": {"time series", "time-series", "timeseries"},
    "statistics": {"statistics", "statistical", "econometric", "econometrics"},
    "probability": {"probability", "stochastic"},
    "optimisation": {"optimisation", "optimization", "convex"},
    "bayesian": {"bayesian"},
    "data pipeline": {"etl", "data pipeline", "airflow", "dbt", "kafka"},
    "visualisation": {"visualisation", "visualization", "tableau", "power bi", "matplotlib"},
    # finance
    "portfolio": {"portfolio", "asset allocation", "efficient frontier",
                  "portfolio construction", "rebalanc", "position sizing"},
    "derivatives": {"derivative", "derivatives", "options", "futures", "swaps"},
    "equities": {"equity", "equities", "stocks"},
    "fixed income": {"fixed income", "bonds", "credit"},
    "risk": {"risk management", "market risk", "credit risk", "var ", "value at risk",
             "drawdown", "sharpe", "risk limit", "risk budget"},
    "alpha research": {"alpha", "signal research", "systematic trading", "quant research"},
    "backtesting": {"backtest", "backtesting", "walk-forward", "walk forward",
                    "paper trading", "simulation"},
    # This group was missing entirely, and it is exactly the expertise that
    # separates someone who knows the work from someone who has just learned
    # it: knowing whether a number can be trusted.
    "validation": {"out-of-sample", "out of sample", "cross-validation",
                   "cross validation", "look-ahead", "look ahead bias",
                   "data leakage", "data snooping", "overfit", "overfitting",
                   "train/test", "train test split", "holdout", "regime"},
    "market data": {"market data", "bloomberg", "refinitiv", "reuters"},
    "asset pricing": {"asset pricing", "pricing model", "valuation"},
    "factor models": {"factor model", "factor models", "fama"},
    "cfa": {"cfa"},
    "frm": {"frm"},
    # hạ tầng
    "linux": {"linux", "unix", "bash", "shell scripting"},
    "docker": {"docker", "container"},
    "kubernetes": {"kubernetes", "k8s"},
    "cloud": {"aws", "gcp", "azure", "cloud"},
    "git": {"git", "version control"},
    "ci/cd": {"ci/cd", "continuous integration", "jenkins"},
}

# ------------------------------------------------------- degrees / years
DEGREE_WORDS = {
    "phd": {"phd", "ph.d", "doctorate", "doctoral"},
    "masters": {"master", "masters", "msc", "ms", "m.sc", "mba", "postgraduate", "meng"},
    "bachelors": {"bachelor", "bachelors", "bsc", "b.sc", "ba", "bs", "beng",
                  "undergraduate", "degree"},
}
QUANT_FIELD = {"mathematics", "maths", "math", "physics", "statistics", "computer science",
               "engineering", "quantitative", "computational", "economics", "finance",
               "econometrics", "operations research", "stem"}

YEARS = re.compile(r"(\d+)\s*(?:\+|\s*-\s*\d+)?\s*(?:or more\s*)?year", re.I)

# -------------------------------------------------------- classification
# Headings that open a REQUIREMENTS section
REQ_HEADS = re.compile(
    r"^\s*(requirements?|qualifications?|what we(?:'re| are)? looking for|"
    r"who you are|about you|you(?:'ll| will)? have|you have|your profile|"
    r"skills? (?:and|&) experience|experience required|what you(?:'ll| will)? bring|"
    r"ideal candidate|must[- ]haves?|essential|the ideal)", re.I)

# Headings that open a RESPONSIBILITIES section.
#
# This half of the JD used to be thrown away. Measured 10 Sep over 176
# postings: 48% had a REQUIREMENTS section (being read), 47% had a
# RESPONSIBILITIES section (skipped) — and it is that second half that
# describes the work, which is to say it describes what a project looks like.
DO_HEADS = re.compile(
    r"^\s*(responsibilit\w+|the role|your role|role (?:overview|summary)|"
    r"what you(?:'ll| will)? (?:do|be doing)|key (?:duties|responsibilities|tasks)|"
    r"duties|day[- ]to[- ]day|the job|what the (?:role|job) involves|"
    r"in this role|you will be|your impact|the opportunity|"
    r"about the (?:role|position)|job description)", re.I)

# Headings that open a NICE-TO-HAVE section
NICE_HEADS = re.compile(
    r"^\s*(nice[- ]to[- ]haves?|bonus|preferred|desirable|advantageous|"
    r"plus(?:es)?|it would be great|good to have)", re.I)

# Headings that are NOT requirements — they must be excluded, or the score
# is based on the company's benefits ("we offer 25 days holiday")
STOP_HEADS = re.compile(
    r"^\s*(what we offer|benefits?|perks?|our offer|compensation|salary|"
    r"about (?:us|the (?:company|team|firm))|why join|diversity|equal opportunit|"
    r"how to apply|application process|next steps|our values?|life at)", re.I)

# Required / optional signals inside the sentence itself
MUST_WORDS = re.compile(r"\b(must|required|essential|strong|proven|solid|demonstrated)\b", re.I)
NICE_WORDS = re.compile(
    r"\b(nice to have|bonus|preferred|desirable|advantage|a plus|would be great|"
    r"ideally|familiarity)\b", re.I)


def alias_map() -> dict[str, str]:
    """Every spelling -> the canonical name."""
    out: dict[str, str] = {}
    for canonical, forms in SKILLS.items():
        out[canonical] = canonical
        for form in forms:
            out[form.strip()] = canonical
    return out


ALIASES = alias_map()


# --------------------------------------------------------------- khớp alias
# SUBSTRING matching is wrong, and badly wrong: 'excel' is inside
# 'excellent', so 70 kept postings were tagged with the skill Excel purely
# because the JD said "excellent communication" — and the largest project
# cluster on the /projects screen grew out of that. Same pattern:
# 'scala' trong 'scalable' (46 tin), 'rust' trong 'trust' (35), 'valuation'
# trong 'evaluation' (10).
#
# But banning substrings outright loses most of what is RIGHT, because
# English inflects: backtesting, derivatives, pipelines, containerisation,
# portfolios. So the rule is: a proper WORD BOUNDARY at the start, and only
# one INFLECTIONAL SUFFIX allowed at the end.
_TAIL = r"(?:s|es|ed|ing|ings|ation|ations|isation|isations|ization|izations)?"

# An alias shorter than this gets NO suffix — see _alias_pattern.
DU_DAI_CHO_DUOI = 3


def _alias_pattern(alias: str) -> re.Pattern:
    """Boundaries via (?<!\\w) / (?!\\w), NOT via \\b.

    `\\b` is the boundary BETWEEN a word character and a non-word one, so it
    can never be true after an alias ending in a non-word character: the
    pattern `\\bc\\+\\+\\b` cannot match "c++ and python", because both sides
    there are non-word.

    Measured on the real store: 208 postings ask for C++ and Vin's CV HAS
    C++ — the machine had never seen one of them. Same bug for c#, kdb+,
    ci/cd.

    (?<!\\w) and (?!\\w) say exactly what is meant: "no word character glued
    to it". For an ordinary alias ("python") they behave identically to \\b.
    """
    # ĐUÔI CHIA CHỈ GẮN CHO ALIAS ĐỦ DÀI.
    #
    # "r" + "ed" = "red", "r" + "ing" = "ring", "go" + "ing" = "going". Đo
    # real: "the red car is going fast" yields the skills {Go, R}, and "a
    # ring of trust during the day" yields {R}. Any posting containing
    # "red"/"ring"/"going" scored for two languages the JD never mentions —
    # a wrong score with nobody able to point at the error.
    #
    # Short aliases (r, go, c, js, ai, ml) almost never need a suffix:
    # people write "R", "Go", "C", not "Rs" or "Going". Longer aliases do:
    # "api" -> "apis", "model" -> "modelling".
    duoi = _TAIL if len(alias) >= DU_DAI_CHO_DUOI else ""
    return re.compile(r"(?<!\w)" + re.escape(alias) + duoi + r"(?!\w)")


_ALIAS_RE: dict[str, tuple[re.Pattern, str]] = {
    alias: (_alias_pattern(alias), canonical)
    for alias, canonical in ALIASES.items() if alias.strip()
}


def alias_hits(normed: str) -> list[str]:
    """The canonical names of every skill present in ALREADY-NORMALISED
    TEXT, in order.

    The input must have gone through ingest.base.norm first — the word
    boundary rule depends on punctuation having become spaces.
    """
    found: list[str] = []
    for pattern, canonical in _ALIAS_RE.values():
        if canonical not in found and pattern.search(normed):
            found.append(canonical)
    return found


# ------------------------------------------------------------ industries
# SEVEN LABELS, no more. This is the vocabulary behind the profile's
# "industry" field: typing a separate list for the screen would let the user
# pick an industry the machine cannot recognise.
#
# It used to live in projects/inventory.py. It never belonged to that
# feature — this is VOCABULARY, and vocabulary lives here: "a missing word
# gets added here, not fixed somewhere else".
INDUSTRY: dict[str, set[str]] = {
    "hedge fund": {"hedge fund", "systematic fund", "multi-strategy",
                   "multi strategy", "prop trading", "proprietary trading",
                   "market making", "market maker", "quant fund"},
    # Bare "structuring" was dropped: measured, it matched "cleansing and
    # structuring for downstream" — structuring DATA, not structuring a
    # financial product.
    "investment bank": {"investment bank", "sell-side", "sell side",
                        "trading desk", "front office", "deal structuring",
                        "product structuring"},
    "asset management": {"asset management", "asset manager", "buy-side",
                         "buy side", "wealth management", "pension fund",
                         "fund management", "institutional investor"},
    "fintech": {"fintech", "payment", "neobank", "challenger bank",
                "lending platform", "e-money"},
    "insurance": {"insurance", "insurer", "actuarial", "reinsurance",
                  "underwriting"},
    "crypto": {"crypto", "cryptocurrency", "cryptocurrencies", "cryptoasset",
               "digital asset", "blockchain", "defi"},
    "energy": {"energy trading", "commodity trading", "commodities trading",
               "power trading", "carbon market"},
}
