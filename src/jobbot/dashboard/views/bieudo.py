"""Charts — SVG built on the server, NO library, NO JavaScript.

Why no charting library: these screens contain not one line of JS beyond
live.js, and every external library is a CDN reaching out to the network —
the app working offline is a property, not luck. The charts here are bars and
columns, and for bars and columns `<rect>` is enough.

THREE RULES FOR EVERY SHAPE IN THIS FILE:

  1. NEVER DRAW WHAT WAS NOT MEASURED. A day before the app existed has no
     column, not a column of 0 — "that day produced 0" and "the app did not
     exist that day" are two different truths, and drawing them the same is
     lying with a picture.
  2. ALWAYS SHOW THE DENOMINATOR. A 3% bar that does not say 3% of what
     leaves the reader filling in the number themselves, usually wrongly.
  3. READABLE WITHOUT COLOUR. Every shape carries its number in text; colour
     only groups things quickly, it never carries information.

DRAWING ONLY.
"""

from __future__ import annotations

from datetime import date
from html import escape as esc


def _so(n) -> str:
    """12345 -> 12,345. A long number without separators has to be counted."""
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(n)


def cot_ngay(cot: list, dinh: int, cao: int = 34, mau: str = "",
             truoc: int = 0) -> str:
    """Columns by day. ONE column per day, scaled to THIS series' own peak.

    Normalised to its own peak rather than a shared axis: one day's scan
    returns 4,651 postings while 4 applications go out. On a shared axis the
    "applied" strip flattens to a line, and that strip is exactly the one the
    user most needs to see.

    The cost: TWO STRIPS CANNOT BE COMPARED BY EYE — so each strip has to
    print its own peak in text, and the caller is responsible for that.
    """
    if not cot:
        return ""
    # `truoc` = days INSIDE the window when the app WAS NOT RUNNING. They
    # still take their place on the strip, drawn as a faint line at the
    # bottom — clearly different from a 0 column (darker, solid).
    #
    # Drop them and two days of data expand to fill the strip, reading as
    # "steady all along"; fill them with 0 and it reads as "productivity
    # collapsed". Both are wrong, and the second sends the user off fixing
    # the wrong thing.
    n = len(cot) + truoc
    w = round(100 / n, 4)
    o = []
    for i in range(truoc):
        o.append(f"<rect x='{round(i * w, 4)}%' y='99.4%'"
                 f" width='{round(w * .74, 4)}%' height='0.6%'"
                 f" class=ngoai><title>the app was not running</title></rect>")
    for j, (d, v) in enumerate(cot):
        i = j + truoc
        h = round(v * 100 / dinh, 2) if dinh else 0
        h = max(h, 1.6) if v else 0          # a non-zero value must be visible
        nhan = f"{esc(str(d))}: {_so(v)}"
        if h:
            o.append(f"<rect x='{round(i * w, 4)}%' y='{round(100 - h, 2)}%'"
                     f" width='{round(w * .74, 4)}%' height='{h}%' rx='0.6'>"
                     f"<title>{nhan}</title></rect>")
        else:
            # A day that IS in the window with a value of 0: draw a dot at
            # the bottom. Leaving it blank makes it look like a day outside
            # the window (the app was not running).
            o.append(f"<rect x='{round(i * w, 4)}%' y='99%'"
                     f" width='{round(w * .74, 4)}%' height='1%' rx='0.5'"
                     f" class=khong><title>{nhan}</title></rect>")
    lop = f" {mau}" if mau else ""
    # The height is CSS's job (.spark), not a style on each shape: expanding
    # the panel has to make the strip taller, and a number baked into the
    # HTML cannot do that.
    return (f"<svg class='spark{lop}' viewBox='0 0 100 100'"
            f" preserveAspectRatio=none aria-hidden=true>{''.join(o)}</svg>")


def dai_viec(v: dict) -> str:
    """One metric = one strip: name · total · average · daily columns · range."""
    cot = v.get("cot") or []
    if not cot:
        return (f"<div class=dai><div class=daitop><b>{esc(v['ten'])}</b>"
                f"<span class=muted>no days yet</span></div></div>")
    truoc = v.get("truoc") or 0
    # The left-hand label has to be THE LEFT EDGE OF THE STRIP, not the
    # first day with a value: the strip now draws the not-running stretch
    # too, so using the first day with data misnames what is on screen.
    dau = (v.get("mep_trai") or cot[0][0])[5:].replace("-", "/")
    cuoi = cot[-1][0][5:].replace("-", "/")
    # SAY OUTRIGHT how many days the app was not running; do not make the
    # reader infer it from a gap — any gap reads as "produced 0".
    chan = (f"{v['ngay_co']} days with data" if not truoc else
            f"{truoc} days before the app ran · {v['ngay_co']} days with data")
    # FOR A RARE EVENT, "avg 0/day" IS A MEANINGLESS SENTENCE. One interview
    # invitation in 60 days is a fact very much worth knowing, and printing
    # it as "avg 0/day · peak 1" reads like broken data. For a sparse series
    # the right answer is WHEN IT LAST HAPPENED.
    cuoi_co = next((d for d, x in reversed(cot) if x), "")
    if round(v["tb"]) < 1 and v["tong"]:
        phu = (f"last on {esc(cuoi_co[5:].replace('-', '/'))}"
               if cuoi_co else f"peak {_so(v['dinh'])}")
    else:
        phu = f"avg {_so(round(v['tb']))}/day · peak {_so(v['dinh'])}"
    return (f"<div class=dai>"
            f"<div class=daitop><a href='{esc(v['di'])}'>{esc(v['ten'])}</a>"
            f"<span class=daiso><b>{_so(v['tong'])}</b><i>{phu}</i>"
            f"</span></div>"
            + cot_ngay(cot, v["dinh"], mau=v.get("mau", ""), truoc=truoc)
            + f"<div class=daichan><span>{esc(dau)}</span>"
            f"<span>{esc(chan)}</span>"
            f"<span>{esc(cuoi)}</span></div></div>")


def cot_thu(so: list, ten: list, mau: str = "") -> str:
    """Seven columns, one per weekday. Only for a LONG ENOUGH series — the
    caller guards that."""
    dinh = max(so) if so else 0
    o = ""
    for i, v in enumerate(so):
        h = round(v * 100 / dinh) if dinh else 0
        o += (f"<div class=tcot><span class=tbar style='height:{max(h, 2)}%'"
              f" title='{esc(ten[i])}: {_so(v)}'></span>"
              f"<b>{_so(v)}</b><i>{esc(ten[i])}</i></div>")
    return f"<div class='thubar {esc(mau)}'>{o}</div>"


def chua_du(co: int, can: int, don: str = "days") -> str:
    """Not enough data yet -> SAY SO, do not draw an empty grid.

    This is the most important shape in this file: an empty chart looks
    exactly like a "productivity is zero" chart, and the user will believe
    the second one.
    """
    return (f"<div class=chuadu><b>Not enough to say</b>"
            f"<span>only <b>{co}</b> {esc(don)} of data so far; <b>{can}</b> "
            f"{esc(don)} are needed before an average means anything. Keep "
            f"the app running and this appears on its own.</span></div>")


# ------------------------------------------------------------------ FUNNEL

def pheu(buoc: list, chu: str = "") -> str:
    """Drop-off through each stage. Widths are relative to the FIRST stage,
    so the eye sees the loss at once.

    It also prints the % KEPT at each stage relative to the one before — that
    is the number that says which stage is cutting hardest; against the first
    stage every later one just looks small.
    """
    if not buoc:
        return ""
    dau = buoc[0][1] or 1
    o = ""
    truoc = None
    for ten, so, di in buoc:
        r = max(round(so * 100 / dau, 2), 0.8) if dau else 0
        rot = ("" if truoc in (None, 0) else
               f"<i class=protr>{round(so * 100 / truoc)}% of the previous step</i>")
        o += (f"<a class=fbuoc href='{esc(di)}'>"
              f"<span class=pten>{esc(ten)}</span>"
              f"<span class=pbar><span style='width:{r}%'></span></span>"
              f"<span class=pso><b>{_so(so)}</b>{rot}</span></a>")
        truoc = so
    return f"<div class=pheu>{o}</div>" + (
        f"<div class=note>{chu}</div>" if chu else "")


def thanh_chia(phan: list, tong: int) -> str:
    """A segmented bar: [(label, count, class)]. The denominator prints
    beside it.

    A segment of 0 is NOT drawn — no hairline with a caption, because a
    caption for a segment that does not exist sends the reader hunting for it
    on the bar.
    """
    if not tong:
        return "<div class=empty-box>nothing applied to yet</div>"
    o = "".join(
        f"<span class='segq {lop}' style='width:{round(so * 100 / tong, 2)}%'"
        f" title='{esc(ten)}: {_so(so)}/{_so(tong)}'></span>"
        for ten, so, lop in phan if so)
    chu = "".join(
        f"<span class=qkey><i class='qdot {lop}'></i>{esc(ten)}"
        f"<b>{_so(so)}</b></span>" for ten, so, lop in phan if so)
    return f"<div class=qbar>{o}</div><div class=qkeys>{chu}</div>"


def ti_le(pc, tren: str, ten: str, lop: str = "") -> str:
    """ONE ratio + its denominator. Never print a % while hiding what of."""
    v = "—" if pc is None else f"{pc:g}%"
    return (f"<div class='tile {lop}'><b>{esc(v)}</b>"
            f"<span>{esc(ten)}</span><i>{esc(tren)}</i></div>")


def thang_gan(thang: dict, n: int = 6, mau: str = "") -> str:
    """The last few months. Month names spelled out, not a bare 2026-08."""
    if not thang:
        return ""
    muc = sorted(thang.items())[-n:]
    dinh = max(v for _, v in muc) or 1
    o = ""
    for t, v in muc:
        h = round(v * 100 / dinh)
        try:
            nhan = ("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec"
                    .split()[int(t[5:7]) - 1])
        except (TypeError, ValueError):
            nhan = t
        o += (f"<div class=tcot><span class=tbar style='height:{max(h, 2)}%'"
              f" title='{esc(t)}: {_so(v)}'></span>"
              f"<b>{_so(v)}</b><i>{esc(nhan)}</i></div>")
    return f"<div class='thubar {esc(mau)}'>{o}</div>"


def hom_nay_la() -> str:
    t = date.today()
    return "Mon Tue Wed Thu Fri Sat Sun".split()[t.weekday()]
