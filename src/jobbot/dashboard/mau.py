"""The app's accent colour — declared in ONE place, changeable in Settings.

The green used to be hardcoded in app.css. That was not a design decision,
only that nobody had needed to change it; and the accent colour is what the
user looks at all day.

ONE BASE COLOUR PRODUCES ALL SIX. The other five values are functions of the
base, because typing thirty numbers by hand invites a mistake: one set off
key and the whole app goes off key with nobody able to point at the error.

    --acc-rgb   the three RGB components, for every other opacity
    --acc       the accent
    --acc-2     darker — used for gradients and pressed states
    --acc-ink   text placed ON an accent background
    --acc-bg    a faint wash (11%) — the selected item
    --acc-bg-2  a stronger wash (20%)

`--acc-rgb` IS THE MOST IMPORTANT ONE, and it was added last. Without it,
every place needing the accent at a different opacity had to hardcode
`rgba(85,201,141,.35)` — measured, 12 borders and backgrounds did exactly
that, so choosing Purple gave PURPLE TEXT WITH GREEN BORDERS.

GREEN KEEPS ITS OLD VALUES, unrecomputed. It is the default, and one round of
"tidying" that shifts the whole app's green is changing something nobody
asked to change.

EVERY COLOUR MUST MEET CONTRAST. The accent often sits on small text (the
active tab label, the numbers on the deck), so under 4.5:1 it is unreadable
at 10px — and a beautiful colour you cannot read is not a choice, it is a
trap. There is a test that measures each colour against `--panel`.
"""

from __future__ import annotations

# The darkest background the accent has to sit on. The same value as
# `--panel` in app.css — the hardest place to read, so measuring here
# measures the worst case.
NEN_PANEL = "#212121"
TOI_THIEU = 4.5          # the WCAG contrast ratio for body text


def _rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(v))):02X}" for v in rgb)


def _nhan(h: str, k: float) -> str:
    return _hex(v * k for v in _rgb(h))


def _sang(h: str) -> float:
    """Relative luminance (WCAG). Not the RGB mean — the human eye is seven
    times more sensitive to green than to blue, so a mean measures the wrong
    thing entirely."""
    def kenh(v):
        v /= 255
        return v / 12.92 if v <= .03928 else ((v + .055) / 1.055) ** 2.4
    r, g, b = (kenh(v) for v in _rgb(h))
    return .2126 * r + .7152 * g + .0722 * b


def tuong_phan(a: str, b: str) -> float:
    x, y = sorted((_sang(a), _sang(b)))
    return round((y + .05) / (x + .05), 2)


def _bo(goc: str) -> dict:
    """Base colour -> the whole set of five. The two coefficients come from
    the green set already running: `--acc-2` is 0.89× the base, `--acc-ink`
    is 0.19×."""
    r, g, b = _rgb(goc)
    return {"--acc-rgb": f"{r},{g},{b}",
            "--acc": goc,
            "--acc-2": _nhan(goc, .89),
            "--acc-ink": _nhan(goc, .19),
            "--acc-bg": f"rgba({r},{g},{b},.11)",
            "--acc-bg-2": f"rgba({r},{g},{b},.20)"}


# Six colours, each with a clear character — not six shades of one thing.
# Anyone who wants no colour at all picks Steel: it is still an "accent", it
# just accents with brightness instead of hue.
BANG = {
    # GREEN keeps VERBATIM the values already running in app.css.
    "la": ("Green", {"--acc-rgb": "85,201,141",
                       "--acc": "#55C98D", "--acc-2": "#48B37C",
                       "--acc-ink": "#10261B",
                       "--acc-bg": "rgba(85,201,141,.11)",
                       "--acc-bg-2": "rgba(85,201,141,.20)"}),
    "lam": ("Blue", _bo("#63B3F0")),
    "tim": ("Purple", _bo("#A78BFA")),
    "cam": ("Orange", _bo("#E8A15C")),
    "hong": ("Pink", _bo("#F08BA8")),
    "thep": ("Steel", _bo("#AFB6BF")),
}

MAC_DINH = "la"


def css(ten: str) -> str:
    """The CSS snippet that overrides :root. The default colour -> EMPTY.

    Returning empty for the default is deliberate: app.css remains the source
    of truth for the green set, so picking the default overrides nothing and
    cannot drift off key.
    """
    if ten == MAC_DINH or ten not in BANG:
        return ""
    bo = BANG[ten][1]
    khai = "".join(f"{k}:{v};" for k, v in bo.items())
    return f"/* accent: {BANG[ten][0]} */\n:root{{{khai}}}\n"


def hop_le(ten: str) -> str:
    return ten if ten in BANG else MAC_DINH
