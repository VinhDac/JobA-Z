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
from urllib.parse import quote

from ...cv.build import TailoredCV
from ...cv.build import bench
from ...cv.render import dem_lai, paper
from ...cv.report import chi_tiet, head
from ..layout import duong_ve, h1, page


def render(job: dict, cv: TailoredCV, profile: dict | None = None,
           tu: str = "") -> str:
    dem_lai()          # số câu đếm lại từ 1 cho mỗi tờ
    du_bi = bench(profile or {}, cv) if profile else []
    ve, ten = duong_ve(tu, "/cv")
    # XEM TIN là một CHUYẾN ĐI KHÁC, nên nó là một nút riêng — và nó mang theo
    # đường về đây, để Back ở trang tin quay lại đúng bản CV này chứ không
    # rơi về danh sách.
    xem = (f"/jobs/{esc(job['id'])}?tu="
           + quote(f"/jobs/{job['id']}/cv?tu={tu or '/cv'}", safe=""))
    return page(
        f"CV — {job['title']}",
        f"<a class=back href='{esc(ve)}'>← {esc(ten)}</a>"
        + h1("Bản CV cho tin này",
             f"Dựng cho {job['company']} — {job['title']}.")
        + head(cv, xem)
        + paper(cv, cham=True, du_bi=du_bi, job=str(job['id']))
        + chi_tiet(cv),
        active="/jobs",
    )
