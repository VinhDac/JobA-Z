"""Read config/config.toml — from ONE place.

Every module used to open the file itself with tomllib. Two readers are two
understandings of the same file, and they drift apart with nobody noticing —
exactly the disease just cured in the scoring layer and the CV builder.

No file means {} rather than an exception: the app has to run before Vin has
configured anything. The features that need configuration simply switch off.
"""

from __future__ import annotations

import re
import os
import tomllib

from pathlib import Path

from .paths import project_root


def _tep(ten: str) -> Path:
    """The path to a config file, computed AT CALL TIME.

    A module-level constant cannot be redirected by a test, and it did write
    straight into the REAL config.toml — leaving a fake address "a@b.c" and
    an empty app password in Vin's file on 12 Sep.
    """
    return project_root() / "config" / ten


class _Duong:
    """Lets `config.PATH` still be used like a Path, but resolved on use."""

    def __init__(self, ten: str) -> None:
        self._ten = ten

    def __fspath__(self) -> str:
        return str(_tep(self._ten))

    def __getattr__(self, ten: str):
        return getattr(_tep(self._ten), ten)

    def __truediv__(self, khac):
        return _tep(self._ten) / khac

    def __str__(self) -> str:
        return str(_tep(self._ten))


PATH = _Duong("config.toml")


def load() -> dict:
    """Read config.toml. Broken means empty — BUT IT MUST SAY SO.

    Returning empty in silence is the worst place for a silent failure: one
    stray quote in the file switches OFF both Gmail AND Telegram, and
    Telegram is the only channel that could have reported it. With the
    machine sitting at home the user knows nothing — they just see no new
    postings, forever.

    A MISSING file stays silent: that is the legitimate state of a new user.
    """
    if not PATH.exists():
        return {}
    try:
        return tomllib.loads(PATH.read_text())
    except tomllib.TOMLDecodeError as e:
        _keu(f"config.toml IS NOT VALID TOML — {str(e)[:90]}. Gmail and "
             f"Telegram are both off until it is fixed.")
        return {}
    except OSError as e:
        _keu(f"could not read config.toml — {type(e).__name__}: {str(e)[:70]}")
        return {}


_da_keu: set = set()


def _keu(cau: str) -> None:
    """Log ONCE per distinct message. `load()` is called dozens of times per
    page render; shouting every time turns the journal into noise and pushes
    the line worth reading off the top."""
    if cau in _da_keu:
        return
    _da_keu.add(cau)
    try:
        from .journal import SYSTEM, log as jlog
        jlog.error(SYSTEM, cau)
    except Exception:                       # noqa: BLE001
        pass


def section(name: str) -> dict:
    got = load().get(name)
    return got if isinstance(got, dict) else {}


EXAMPLE = _Duong("config.example.toml")
SECRET = 0o600          # owner-only — this file holds an app password


def _quote(value: str) -> str:
    """A basic TOML string. Escapes \\ and " — a Google app password contains
    neither, but this rule must not depend on luck."""
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_value(name: str, key: str, value: str) -> None:
    """Set one value in config.toml, touching ONLY that line.

    It does not rebuild the file: config.toml carries long comments about why
    to use a separate mailbox and why an app password is a full-access key.
    Overwriting the whole file deletes that reasoning, and the next reader
    will not know.

    No TOML writer library, because the stdlib only ships a READER
    (tomllib). Line-wise editing is enough for a flat config file and leaves
    everything else exactly as it was.
    """
    if not PATH.exists():
        PATH.parent.mkdir(parents=True, exist_ok=True)
        PATH.write_text(EXAMPLE.read_text() if EXAMPLE.exists()
                        else f"[{name}]\n")
    lines = PATH.read_text().splitlines()
    head = re.compile(r"^\s*\[([^\]]+)\]\s*$")
    line = re.compile(rf"^\s*{re.escape(key)}\s*=")

    here, target, last = "", -1, -1
    for i, text in enumerate(lines):
        found = head.match(text)
        if found:
            here = found.group(1).strip()
            continue
        if here == name:
            last = i
            if line.match(text):
                target = i
                break

    new = f"{key} = {_quote(value)}"
    if target >= 0:
        lines[target] = new
    elif last >= 0:
        lines.insert(last + 1, new)                  # end of that section
    else:
        lines += ["", f"[{name}]", new]

    # ATOMIC WRITE: write a temp file IN THE SAME DIRECTORY, then rename over.
    #
    # `write_text` truncates the file before writing. An interruption between
    # those two steps — power cut, full disk, the app killed — leaves an
    # empty or truncated config.toml, which means the Gmail app password and
    # the Telegram token are gone for good. There is no copy anywhere: they
    # exist only in this file.
    #
    # `os.replace` within one filesystem is atomic: either the old file
    # intact, or the new file intact, never anything in between.
    #
    # chmod ON THE TEMP FILE, before the rename — doing it after leaves a
    # window where the secret sits there with default permissions.
    goc = Path(str(PATH))
    tam = goc.with_name(goc.name + ".moi")
    tam.write_text("\n".join(lines).rstrip() + "\n")
    try:
        tam.chmod(SECRET)
    except OSError:
        pass
    os.replace(tam, goc)
