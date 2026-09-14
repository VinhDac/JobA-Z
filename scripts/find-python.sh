# Find a Python >= 3.11.  Use:  . scripts/find-python.sh   ->  $PY
#
# ONE COPY, used in two places: start.command (double-click) and the jobbot.app
# wrapper. Copy it in two and sooner or later the two drift, and drift here
# means a double-click opens the app while the icon does not — with nobody able
# to guess why.
#
# Why not simply type `python3`: on this machine `/usr/bin/python3` is 3.9.6
# (measured), while the app needs 3.11 or later (tomllib). And Finder's PATH is
# not Terminal's PATH — what works when typed in a terminal may be invisible on
# a double-click. So ASK EACH CANDIDATE what version it is, never trust the name.

PY=""
for _candidate in \
    "$JOBBOT_PYTHON" \
    "$(command -v python3)" \
    "$(command -v python3.13)" "$(command -v python3.12)" "$(command -v python3.11)" \
    /opt/homebrew/bin/python3 /usr/local/bin/python3 \
    /opt/anaconda3/bin/python3 "$HOME/anaconda3/bin/python3" \
    /Library/Frameworks/Python.framework/Versions/Current/bin/python3
do
  [ -n "$_candidate" ] && [ -x "$_candidate" ] || continue
  if "$_candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY="$_candidate"
    break
  fi
done
unset _candidate

# What to tell the user when nothing is found. The same sentence in both places.
PYTHON_MISSING="No Python 3.11 or later was found.

Install one with:  brew install python@3.12
Or download it from python.org

If you already have one, point at it:
  export JOBBOT_PYTHON=/path/to/python3"
