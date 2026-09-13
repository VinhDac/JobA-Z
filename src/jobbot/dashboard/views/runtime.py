"""Khuôn chung cho mọi tab CÓ THỜI GIAN CHẠY.

Search, Score, Project là ba việc khác nhau, nhưng câu hỏi người dùng đặt ra
cho cả ba là một:

    đang làm gì · vừa làm gì · ra được cái gì · chỉnh ở đâu · hỏng thì soi đâu

Nên chúng dùng CHUNG một khuôn. Mỗi tab tự nộp phần ruột, còn vị trí các ô,
cách lọc nhật ký theo luồng, chỗ đặt thanh tiến độ thì giống hệt nhau — học
một tab là biết cả ba, và thêm tab thứ tư không phải nghĩ lại từ đầu.

CHỈ VẼ.
"""

from __future__ import annotations

from html import escape as esc

from ..layout import grid, journal_box, page, progress_box, stat, widget


def tiles(rows: list[tuple[str, str, str]]) -> str:
    """rows = [(số, nhãn, ghi chú)]."""
    return "<div class=stats>" + "".join(stat(v, k, note) for v, k, note in rows) + "</div>"


def rows(items: list[tuple[str, str]], empty_note: str = "—") -> str:
    """Bảng hai cột nhãn/giá trị — dùng cho ô thống kê và ô cài đặt."""
    if not items:
        return f"<div class=empty-box>{esc(empty_note)}</div>"
    out = ""
    for k, v in items:
        # Dòng "— CHROME —" là TIÊU ĐỀ nhóm, không phải một cài đặt. Nhận ra
        # bằng chỗ giá trị rỗng, để cài đặt của ba cách tìm không lẫn vào nhau.
        if not v:
            out += f"<div class=kgroup>{esc(k.strip(' —'))}</div>"
        else:
            out += f"<div class=krow><span>{esc(k)}</span><b>{v}</b></div>"
    return f"<div class=krows>{out}</div>"


def actions(items: list[tuple[str, str, str]]) -> str:
    """Nút debug. items = [(nhãn, đường dẫn POST, mô tả)].

    Nút nào CHƯA nối backend thì để path rỗng — nó hiện mờ và không bấm được,
    thay vì bấm vào rồi không có gì xảy ra và người dùng tưởng app hỏng.
    """
    out = ""
    for label, path, note in items:
        dead = "" if path else " disabled"
        act = f" data-act='{esc(path)}'" if path else ""
        out += (f"<div class=drow><button class=mbtn{dead}{act}>{esc(label)}</button>"
                f"<span class=muted>{esc(note)}</span></div>")
    return f"<div class=debug>{out}</div>"


def _rows_needed(panels: list[tuple], width: int, run_span: int = 0) -> int:
    """Bên trái xếp hết mấy hàng — để nhật ký bên phải cao đúng bằng.

    Không dùng CSS 'grid-row: 1 / -1' được: số âm chỉ đếm các hàng KHAI BÁO
    tường minh, mà lưới ở đây dùng grid-auto-rows nên hàng là hàng ngầm —
    '1 / -1' rút về đúng một hàng. Còn đếm tay thì thêm bớt một ô là lệch.
    """
    # Ô "Đang chạy" nằm ở hàng 1; nếu nó không chiếm trọn hàng thì ô nội dung
    # đầu tiên xếp ngay cạnh nó, không xuống hàng mới.
    # run_span=0 -> không có ô "Đang chạy" ở hàng 1, nội dung xếp từ đầu.
    row, col, tall = 1, (run_span if run_span else 0), 1
    for _title, _body, span, rows, *_rest in panels:
        if col + span > width:        # hết chỗ -> xuống hàng mới
            row += tall
            col, tall = 0, 1
        col += span
        tall = max(tall, rows)
    return row + tall - 1


def panel(title: str, body: str, span: int = 1, rows: int = 1,
          at: tuple[int, int] | None = None, cls: str = "") -> tuple:
    """Một ô nội dung riêng của tab. Khuôn lo phần chung, tab lo phần ruột.

    at=(cột, hàng) đặt ô vào đúng chỗ. Để None thì trình duyệt tự xếp — đủ
    cho tab mà mấy ô ngang vai nhau. Tab nào cần bố cục riêng (Search: nhật
    ký nằm dưới ô lưới, danh sách kéo suốt chiều cao) thì nói rõ ra.
    """
    return (title, body, span, rows, at, cls)


def render(*, title: str, active: str, stream: str, panels: list[tuple],
           note: str = "", cols: int = 3, run_span: int | None = None,
           run_extra: str = "", journal: str = "column",
           columns: str = "", journal_h: str = "118px",
           rows_tpl: str = "", journal_at: tuple[int, int] = (1, 2),
           bar: str = "", setup: str = "") -> str:
    """Khuôn chung cho mọi tab CÓ THỜI GIAN CHẠY.

    journal="column"  nhật ký chiếm trọn cột cuối, cạnh nội dung
    journal="bottom"  nhật ký là DẢI NGANG DẸT dưới đáy, gộp cả thanh tiến độ

    Chọn "bottom" khi nội dung chính cần cả bề ngang — như danh sách việc:
    nhật ký là thứ liếc mắt, không phải thứ đọc lâu, nên ba dòng là đủ. Muốn
    xem nhiều thì bấm nút mở to.
    """
    # `note` là dòng văn cũ. Tab nào đã có THANH KHÚC (bar) thì không cần nó
    # nữa: số liệu đã lên thanh, ở dạng số chứ không phải câu.
    head = f"<div class=tnote>{esc(note)}</div>" if note and not bar else ""

    if journal == "corner":
        # Nhật ký nằm GÓC DƯỚI TRÁI, dưới ô điều khiển — không kéo hết bề
        # ngang. Nó là thứ liếc mắt, chiếm cả chiều ngang là ăn mất chỗ của
        # danh sách, mà danh sách mới là kết quả.
        # Tab tự đặt cột/hàng và vị trí từng ô: bố cục này không đều nhau nên
        # để trình duyệt tự xếp là ra lệch.
        boxes = [widget(t, body, span=sp, rows=rw, at=at, cls=cl)
                 for t, body, sp, rw, at, cl in panels]
        boxes.append(widget(
            f"Nhật ký · {title.lower()}",
            f"<div class=jflat><div class=jprog>{progress_box(stream)}</div>"
            f"<div class=jfeed>{journal_box(stream)}</div></div>",
            span=1, cls="flat corner", at=journal_at))
        return page(title, head + grid(*boxes, cols=cols, columns=columns,
                                       rows=rows_tpl),
                    active=active, flow=False, bar=bar, setup=setup)

    if journal == "bottom":
        rows = _rows_needed(panels, cols, 0)
        # `at` ĐI QUA ĐƯỢC. Nhánh này bỏ nó, nên tab nào có ô 2×2 nằm cạnh ô
        # 1×1 thì auto-flow tự chèn, và bố cục đổi theo thứ tự khai báo chứ
        # không theo ý người viết. Tab nào không truyền `at` vẫn như cũ.
        if any(at for _t, _b, _sp, _rw, at, _c in panels):
            rows = max((at[1] + rw - 1)
                       for _t, _b, _sp, rw, at, _c in panels if at)
        boxes = [widget(t, body, span=sp, rows=rw, at=at, cls=cl)
                 for t, body, sp, rw, at, cl in panels]
        # Hàng nội dung co giãn, hàng nhật ký cao cố định. Không ghim thì lưới
        # chia đều và dải nhật ký chiếm nguyên một hàng — cao gấp đôi thứ nó
        # cần, và ăn mất chỗ của danh sách.
        # Tab nào tự khai chiều cao hàng thì dùng khai báo của nó — Home có
        # sáu hàng và chúng KHÔNG ngang vai nhau.
        row_tpl = rows_tpl or (" ".join(["1fr"] * rows) + f" {journal_h}")
        # Dải nhật ký: tiến độ bên trái, dòng sự kiện bên phải. Hai thứ cùng
        # trả lời "nó đang làm gì", tách ra hai ô là chia đôi một câu hỏi.
        boxes.append(widget(
            f"Nhật ký · {title.lower()}",
            f"<div class=jflat><div class=jprog>{progress_box(stream)}</div>"
            f"<div class=jfeed>{journal_box(stream)}</div></div>",
            span=cols, cls="flat", at=(1, rows + 1)))
        return page(title, head + grid(*boxes, cols=cols, columns=columns,
                                       rows=row_tpl),
                    active=active, flow=False, bar=bar, setup=setup)

    boxes = [widget("Đang chạy", progress_box(stream) + run_extra,
                    span=run_span if run_span else cols - 1),
             widget(f"Nhật ký · {title.lower()}", journal_box(stream), span=1,
                    rows=_rows_needed(panels, cols - 1, run_span or 0),
                    cls="tall", at=(cols, 1))]
    boxes += [widget(t, body, span=sp, rows=rw)
              for t, body, sp, rw, *_r in panels]
    return page(title, head + grid(*boxes, cols=cols), active=active, flow=False, bar=bar, setup=setup)
