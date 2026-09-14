#!/bin/bash
# Double-click to open jobbot.  (macOS)
# Already running -> just open the dashboard, do NOT start a second run
# Not running     -> start it in the background (the ◆ icon in the menu bar),
#                    then open the dashboard
#
# It no longer asks for port 8765. The operating system hands out the port (see
# server.serve), so it changes from run to run; with the app alive on 8766, a
# script asking for 8765 concludes "not running" and boots a second run on top
# of the same SQLite file.
# The real address lives in data/dang-chay.txt — see src/jobbot/core/dia_chi.py.

cd "$(dirname "$0")" || exit 1

alert() {        # a failure MUST speak. A double-click that goes silent is the worst kind.
  osascript -e "display alert \"jobbot\" message \"$1\"" >/dev/null 2>&1
  echo "$1" >&2
  exit 1
}

# Is it really jobbot answering at this address? "Something answered 200" is not
# enough: the old port may belong to another app by now.
is_alive() {
  [ -n "$1" ] || return 1
  curl -sf --max-time 2 "${1}api/alive" 2>/dev/null | grep -q '^jobbot '
}

URL=""
[ -f data/dang-chay.txt ] && URL="$(head -n 1 data/dang-chay.txt)"

if is_alive "$URL"; then
  open "$URL"; exit 0
fi

# An earlier run left the file behind without still being alive (kill -9, a power
# cut). Ignore it and start fresh.
. scripts/find-python.sh
[ -n "$PY" ] || alert "$PYTHON_MISSING"

mkdir -p data
nohup "$PY" run.py > data/app.log 2>&1 &

for _ in $(seq 1 40); do
  [ -f data/dang-chay.txt ] && URL="$(head -n 1 data/dang-chay.txt)"
  is_alive "$URL" && break
  sleep 0.4
done

if is_alive "$URL"; then
  open "$URL"
else
  alert "Startup did not succeed.

See: $(pwd)/data/app.log"
fi
