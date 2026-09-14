"""The per-posting tailored CV page — WITH THE MARKING ON THE PAGE ITSELF.

The order is deliberate, and it is the order a reader needs:

    score + Prev/Next      is this version good enough, at a glance
    THE CV SHEET, marked   the red pen is on the work, not in an appendix
    detail by sentence     clicking a mark on the sheet jumps to the right place

ONE sheet, not two. The previous version drew the CV and then listed every
sentence again below — the same sentence appearing twice, leaving the reader
to match "sentence 3 below" with one above. Now a sentence has one place, and
the section below only says what the sheet cannot.
"""

from __future__ import annotations

from html import escape as esc
from urllib.parse import quote

from ...cv.build import TailoredCV
from ...cv.build import bench
from ...cv.render import dem_lai, paper
from ...cv.report import chi_tiet, head
from ..layout import duong_ve, h1, page


def render(job: dict, cv: TailoredCV, profile: dict | None = None,
           tu: str = "") -> str:
    dem_lai()          # sentence numbering restarts at 1 for each sheet
    du_bi = bench(profile or {}, cv) if profile else []
    ve, ten = duong_ve(tu, "/cv")
    # VIEWING THE POSTING is a DIFFERENT JOURNEY, so it is its own button —
    # and it carries the way back, so Back on the posting page returns to
    # this exact CV version rather than dropping to the list.
    xem = (f"/jobs/{esc(job['id'])}?tu="
           + quote(f"/jobs/{job['id']}/cv?tu={tu or '/cv'}", safe=""))
    return page(
        f"CV — {job['title']}",
        f"<a class=back href='{esc(ve)}'>← {esc(ten)}</a>"
        + h1("The CV for this posting",
             f"Dựng cho {job['company']} — {job['title']}.")
        + head(cv, xem)
        + paper(cv, cham=True, du_bi=du_bi, job=str(job['id']))
        + chi_tiet(cv),
        active="/jobs",
    )
