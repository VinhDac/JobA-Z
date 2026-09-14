"""Test telling 'a match' apart from 'a real chance'.  python3 tests/test_realism.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobbot.scoring.realism import assess, find_deadline

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}")

GRAD = {"years_real": "0-1"}
MID = {"years_real": "3-5"}
LONG = "x" * 400

print("\n[is there a real chance]")
cases = [
    ("Graduate Analyst", "Our graduate programme welcomes final-year students. " + LONG,
     GRAD, "likely"),
    ("Quantitative Researcher", "A PhD is required in a quantitative field. " + LONG,
     GRAD, "unlikely"),
    ("Quantitative Analyst", "You will need 7+ years of experience. " + LONG,
     GRAD, "unlikely"),
    ("Senior Data Scientist", "Join our team building models. " + LONG, GRAD, "unlikely"),
    ("Data Analyst", "You will build dashboards and reports. " + LONG, GRAD, "possible"),
]
for title, text, profile, want in cases:
    got = assess(title, text, None, profile)["band"]
    check(f"{want:9} ← {title[:34]}", got == want)

check("same posting: five years' experience beats a fresh graduate",
      assess("Quant Analyst", "Requires 4+ years of experience. " + LONG, None, MID)["score"]
      > assess("Quant Analyst", "Requires 4+ years of experience. " + LONG, None, GRAD)["score"])

print("\n[it never guesses]")
blank = assess("Analyst", "", None, GRAD)
check("no description -> 'unknown'", blank["band"] == "unknown")
check("and it says why", "no description" in blank["why"])
check("too short a description is also 'unknown'",
      assess("Analyst", "Join us!", None, GRAD)["band"] == "unknown")

print("\n[always explicable]")
phd = assess("Quant Researcher", "A PhD is required here. " + LONG, None, GRAD)
check("names the PhD as the reason", "PhD" in phd["why"])
yrs = assess("Quant Analyst", "We need 6+ years experience. " + LONG, None, GRAD)
check("names the exact number of years", "6+" in yrs["why"] and "0.5" in yrs["why"])
grad = assess("Graduate Analyst", "Our graduate programme. " + LONG, None, GRAD)
check("names why there is a chance", "graduate" in grad["why"].lower())

print("\n[the deadline]")
for text, want in [
    ("Applications close 15 November 2026.", "15 November 2026"),
    ("Deadline: 2026-11-30 for all candidates.", "2026-11-30"),
    ("Apply by 01/12/2026 please.", "01/12/2026"),
]:
    got, ts = find_deadline(text)
    check(f"reads '{want}'", got == want and ts > 0)
check("no deadline -> empty", find_deadline("We hire all year round.") == ("", 0))
check("it does not grab some other date",
      find_deadline("Founded in 2015, we now have 400 staff.")[0] == "")

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
