"""Trang CV tuỳ biến cho một tin — và CHẤM ĐIỂM NGAY TRÊN BÀI.

Thứ tự có ý, đúng thứ tự người đọc cần:

    điểm + nút Trước/Sau   nắm ngay bản này đủ tốt chưa
    TỜ CV, đã đánh dấu     bút đỏ nằm trên bài, không nằm ở phụ lục
    chi tiết theo số câu   bấm dấu trên bài là nhảy xuống đúng chỗ

MỘT tờ giấy, không hai. Bản trước vẽ tờ CV rồi liệt kê lại từng câu ở dưới —
cùng một câu hiện hai lần, người đọc phải tự ghép "câu 3 ở dưới" với câu nào
ở trên. Giờ câu chỉ có một chỗ; phần dưới chỉ nói thứ tờ giấy không nói được.
"""

from __future__ import annotations

from html import escape as esc

from ...cv.build import TailoredCV
from ...cv.render import dem_lai, paper
from ...cv.report import chi_tiet, head
from ..layout import h1, page


def render(job: dict, cv: TailoredCV) -> str:
    dem_lai()          # số câu đếm lại từ 1 cho mỗi tờ
    return page(
        f"CV — {job['title']}",
        f"<a class=back href='/jobs/{esc(job['id'])}'>← {esc(job['title'])}</a>"
        + h1("Bản CV cho tin này",
             f"Dựng cho {job['company']} — {job['title']}.")
        + head(cv)
        + paper(cv, cham=True)
        + chi_tiet(cv),
        active="/jobs",
    )
