"""The shared frame for every tab WITH RUNNING TIME.

Search, Score and Project are three different jobs, but the question the user
asks of all three is one:

    what is it doing · what did it just do · what came out · where do I
    adjust it · where do I look when it breaks

So they SHARE one frame. Each tab supplies its own content, while the panel
positions, the per-stream journal filtering and where the progress bar sits
are identical — learn one tab and you know all three, and a fourth tab does
not need rethinking from scratch.

CHỈ VẼ.
"""

from __future__ import annotations

from html import escape as esc

from ..layout import grid, journal_box, page, progress_box, stat, widget


def tiles(rows: list[tuple[str, str, str]]) -> str:
    """rows = [(number, label, note)]."""
    return "<div class=stats>" + "".join(stat(v, k, note) for v, k, note in rows) + "</div>"


def rows(items: list[tuple[str, str]], empty_note: str = "—") -> str:
    """A two-column label/value table — for the stats and settings panels."""
    if not items:
        return f"<div class=empty-box>{esc(empty_note)}</div>"
    out = ""
    for k, v in items:
        # A "— CHROME —" row is a group HEADING, not a setting. Recognised by
        # the empty value, so the settings of the three search routes do not
        # run together.
        if not v:
            out += f"<div class=kgroup>{esc(k.strip(' —'))}</div>"
        else:
            out += f"<div class=krow><span>{esc(k)}</span><b>{v}</b></div>"
    return f"<div class=krows>{out}</div>"


def actions(items: list[tuple[str, str, str]]) -> str:
    """Debug buttons. items = [(label, POST path, description)].

    A button not yet wired to a backend gets an empty path — it renders
    dimmed and unclickable, rather than doing nothing when pressed and
    leaving the user thinking the app is broken.
    """
    out = ""
    for label, path, note in items:
        dead = "" if path else " disabled"
        act = f" data-act='{esc(path)}'" if path else ""
        out += (f"<div class=drow><button class=mbtn{dead}{act}>{esc(label)}</button>"
                f"<span class=muted>{esc(note)}</span></div>")
    return f"<div class=debug>{out}</div>"


def _rows_needed(panels: list[tuple], width: int, run_span: int = 0) -> int:
    """How many rows the left side fills — so the journal on the right is
    exactly as tall.

    CSS 'grid-row: 1 / -1' cannot be used: negative numbers only count
    EXPLICITLY DECLARED rows, and this grid uses grid-auto-rows so the rows
    are implicit — '1 / -1' collapses to exactly one row. Counting by hand
    goes wrong the moment a panel is added or removed.
    """
    # The "Running" panel is on row 1; if it does not fill the row, the first
    # content panel sits beside it rather than starting a new row.
    # run_span=0 -> no "Running" panel on row 1, content starts at the top.
    row, col, tall = 1, (run_span if run_span else 0), 1
    for _title, _body, span, rows, *_rest in panels:
        if col + span > width:        # out of room -> new row
            row += tall
            col, tall = 0, 1
        col += span
        tall = max(tall, rows)
    return row + tall - 1


def panel(title: str, body: str, span: int = 1, rows: int = 1,
          at: tuple[int, int] | None = None, cls: str = "") -> tuple:
    """One content panel belonging to a tab. The frame handles the shared
    parts, the tab handles the content.

    at=(column, row) places the panel. Left as None the browser lays it out —
    enough for a tab whose panels are peers. A tab that needs its own layout
    (Search: the journal under the grid, the list running full height) says
    so explicitly.
    """
    return (title, body, span, rows, at, cls)


def render(*, title: str, active: str, stream: str, panels: list[tuple],
           note: str = "", cols: int = 3, run_span: int | None = None,
           run_extra: str = "", journal: str = "column",
           columns: str = "", journal_h: str = "118px",
           rows_tpl: str = "", journal_at: tuple[int, int] = (1, 2),
           bar: str = "", setup: str = "", reload: str = "") -> str:
    """The shared frame for every tab WITH RUNNING TIME.

    journal="column"  nhật ký chiếm trọn cột cuối, cạnh nội dung
    journal="bottom"  the journal is a FLAT STRIP along the bottom, merged
                      with the progress bar

    Pick "bottom" when the main content needs the full width — like the job
    list: the journal is something you glance at, not something you read, so
    three lines is enough. To see more, press the expand button.
    """
    # `note` is the old prose line. A tab that already has a DECK (bar) no
    # longer needs it: the numbers are on the deck, as numbers rather than a
    # sentence.
    head = f"<div class=tnote>{esc(note)}</div>" if note and not bar else ""

    if journal == "corner":
        # The journal sits in the BOTTOM-LEFT CORNER, under the controls —
        # it does not run the full width. It is something you glance at, and
        # taking the whole width steals room from the list, which is the
        # actual result.
        # The tab sets the columns/rows and each panel's position: this
        # layout is not uniform, so letting the browser lay it out goes
        # wrong.
        boxes = [widget(t, body, span=sp, rows=rw, at=at, cls=cl)
                 for t, body, sp, rw, at, cl in panels]
        boxes.append(widget(
            f"Nhật ký · {title.lower()}",
            f"<div class=jflat><div class=jprog>{progress_box(stream)}</div>"
            f"<div class=jfeed>{journal_box(stream)}</div></div>",
            span=1, cls="flat corner", at=journal_at))
        return page(title, head + grid(*boxes, cols=cols, columns=columns,
                                       rows=rows_tpl),
                    active=active, flow=False, bar=bar, setup=setup,
                    reload=reload)

    if journal == "bottom":
        rows = _rows_needed(panels, cols, 0)
        # `at` HAS TO PASS THROUGH. This branch used to drop it, so a tab
        # with a 2×2 panel beside a 1×1 had auto-flow filling gaps, and the
        # layout followed declaration order rather than intent. A tab that
        # passes no `at` behaves exactly as before.
        if any(at for _t, _b, _sp, _rw, at, _c in panels):
            rows = max((at[1] + rw - 1)
                       for _t, _b, _sp, rw, at, _c in panels if at)
        boxes = [widget(t, body, span=sp, rows=rw, at=at, cls=cl)
                 for t, body, sp, rw, at, cl in panels]
        # Content rows stretch, the journal row is a fixed height. Unpinned,
        # the grid divides evenly and the journal strip takes a whole row —
        # twice as tall as it needs, stealing room from the list.
        # A tab that declares its own row heights gets them — Home has six
        # rows and they are NOT peers.
        row_tpl = rows_tpl or (" ".join(["1fr"] * rows) + f" {journal_h}")
        # The journal strip: progress on the left, events on the right. Both
        # answer "what is it doing"; splitting them into two panels splits
        # one question in half.
        boxes.append(widget(
            f"Nhật ký · {title.lower()}",
            f"<div class=jflat><div class=jprog>{progress_box(stream)}</div>"
            f"<div class=jfeed>{journal_box(stream)}</div></div>",
            span=cols, cls="flat", at=(1, rows + 1)))
        return page(title, head + grid(*boxes, cols=cols, columns=columns,
                                       rows=row_tpl),
                    active=active, flow=False, bar=bar, setup=setup,
                    reload=reload)

    boxes = [widget("Đang chạy", progress_box(stream) + run_extra,
                    span=run_span if run_span else cols - 1),
             widget(f"Nhật ký · {title.lower()}", journal_box(stream), span=1,
                    rows=_rows_needed(panels, cols - 1, run_span or 0),
                    cls="tall", at=(cols, 1))]
    boxes += [widget(t, body, span=sp, rows=rw)
              for t, body, sp, rw, *_r in panels]
    return page(title, head + grid(*boxes, cols=cols), active=active, flow=False, bar=bar, setup=setup,
                    reload=reload)
