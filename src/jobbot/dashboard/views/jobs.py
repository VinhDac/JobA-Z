"""Chi tiết MỘT tin — điểm, từng yêu cầu, bằng chứng, lý do.

Trang DANH SÁCH đã bỏ cùng tab Jobs. Danh sách sẽ nằm trong tab Search, vì
"tìm" và "xem kết quả tìm" là một việc chứ không phải hai.

Trang này VẪN SỐNG, vào được bằng /jobs/<id> — nó là chỗ danh sách mới sẽ
trỏ tới, và là chỗ đọc được vì sao một tin được chấm ngần ấy điểm.

CHỈ VẼ.
"""

from __future__ import annotations

from html import escape as esc

from ..layout import card, empty, h1, page, score_bar

CHANCE_BADGE = {"likely": ("worth applying", "ok"),
                "possible": ("maybe", ""),
                "unlikely": ("long shot", "warn")}



CONF_NOTE = {"high": "", "medium": "few requirements found",
             "low": "requirements guessed from prose", "none": ""}


def _score(job: dict) -> str:
    """Không chấm được thì NÓI THẲNG. Điểm bịa còn tệ hơn không có điểm."""
    if job.get("score") is None:
        return "<span class=noscore>can&#39;t read requirements — judge it yourself</span>"
    note = CONF_NOTE.get(job.get("confidence", ""), "")
    tail = f"<span class=conf>{esc(note)}</span>" if note else ""
    return score_bar(job["score"]) + tail


def _breakdown(job: dict) -> str:
    """Điểm đến từ đâu. Không giải thích được thì không dùng để quyết định nộp."""
    data = job.get("explain")
    if not data or data.get("score") is None:
        return ""
    b = data["breakdown"]
    rows = "".join(
        f"<div class=bdrow><span class=bdl>{esc(label)}</span>"
        f"<span class=bdtrack><span class=bdfill style='width:{pts / cap * 100:.0f}%'></span></span>"
        f"<b>{pts:g}<i>/{cap}</i></b><span class=muted>{esc(why)}</span></div>"
        for label, pts, cap, why in [
            ("Must-have requirements", b["must"]["points"], 55,
             f"{b['must']['met']}/{b['must']['total']} met"),
            ("Nice-to-haves", b["nice"]["points"], 15,
             f"{b['nice']['met']}/{b['nice']['total']} met"),
            ("Level fit", b["level"]["points"], 20, b["level"]["why"]),
            ("Title match", b["title"]["points"], 10, b["title"]["why"]),
        ])
    notes = []
    if data.get("capped"):
        notes.append("Score capped at 55 — this posting asks for experience or a "
                     "qualification you do not have, so it is unlikely to pass screening "
                     "however well the rest matches.")
    if data.get("unknown"):
        notes.append(f"{data['unknown']} lines could not be judged automatically "
                     "(soft skills, culture fit) — left out of the maths entirely "
                     "rather than guessed at.")
    if data.get("weak_evidence"):
        notes.append(f"{data['weak_evidence']} matches rest on keywords you set rather than "
                     "evidence in your CV. Filling in your skills and CV would firm these up.")
    tail = "".join(f"<div class=note>{esc(n)}</div>" for n in notes)
    return card(f"<div class=bd>{rows}</div>{tail}", "bdcard")


# Huy hiệu nguồn — DÙNG CHUNG cả ký hiệu lẫn lớp CSS với danh sách bên tab
# Search, để cùng một tin nhìn ở hai chỗ ra cùng một thứ.
#
# Suy ra từ FOUND_BY chứ không gõ lại: hai bảng ký hiệu ở hai file thì trùng
# nhau được đúng tới hôm có người sửa một bên.
from .search import FOUND_BY

NGUON_DAU = {k: v[0] for k, v in FOUND_BY.items()}


def _mo_tin_goc(job: dict) -> str:
    """Đường sang TIN THẬT. Thiếu nó thì cả trang này là lời kể lại.

    Trang chi tiết cho tới giờ hiện điểm, hiện từng yêu cầu, hiện cả bản mô tả
    — mà không có lấy một đường nào sang xem tin gốc. Người đọc muốn kiểm
    chứng phải tự đi tìm bằng tay, mà kiểm chứng là việc PHẢI làm trước khi
    nộp: mô tả trong kho là bản chụp lúc quét, tin thật có thể đã sửa hoặc đã
    đóng.

    Một việc đăng ở hai nơi thì hiện CẢ HAI. Chúng không thay thế nhau: board
    công ty là chỗ nộp thẳng, còn LinkedIn có phần "ai đã ứng tuyển", số người
    nộp, và tên người đăng tin.
    """
    links = job.get("links") or []
    if not links:
        return empty("Tin này không có đường dẫn nào — nguồn cũ không lưu lại "
                     "URL. Quét lại là có.")
    nut = "".join(
        # target=_blank: trong trình duyệt thì mở tab mới; trong cửa sổ app thì
        # Delegate bắt lại và đẩy sang trình duyệt mặc định. Không có nó, bấm
        # một đường ngoài là CẢ CỬA SỔ APP đi mất, không có nút Back nào.
        # rel=noopener: trang đích không được cầm tay vào cửa sổ này.
        f"<a class='jlink {esc(l['kind'])}' href='{esc(l['url'])}'"
        f" target='_blank' rel='noopener noreferrer'>"
        f"<i class='src {esc(l['kind'])}'>{NGUON_DAU.get(l['kind'], '◆')}"
        f"<b>{esc(l['name'])}</b></i>"
        f"<span class=jlinkhost>{esc(l['host'])}</span>"
        f"<span class=jlinkgo>↗</span></a>"
        for l in links)
    return card(f"<div class=jlinks>{nut}</div>", "jlinkcard")


def render_detail(job: dict) -> str:
    reqs = "".join(
        f"<li class='{'met' if r['met'] else ('unk' if r['met'] is None else 'miss')}'>"
        f"<b>{esc(r['text'])}</b>"
        f"<span>{esc(r['evidence'])}</span></li>"
        for r in job["requirements"]
    )
    proj = job.get("project")
    return page(
        job["title"],
        f"<a class=back href='/search'>← Jobs</a>"
        + h1(job["title"], f"{job['company']} · {job['location']} · {job['salary']}")
        + f"<div class=jmeta>{_score(job)}"
          f"<span class=spacer></span><span class=muted>{esc(job['posted'])}</span></div>"
        + "<h2>Mở tin gốc</h2>"
        + _mo_tin_goc(job)
        + "<h2>Why this score</h2>"
        + _breakdown(job)
        + (card(f"<ul class=reqs>{reqs}</ul>") if reqs
           else empty("Could not read any requirements from this posting. "
                      "Read it yourself — the system will not guess."))
        + "<h2>Tailored CV</h2>"
        + card(f"<a class=ghost href='/jobs/{esc(job['id'])}/cv'>"
               "Build a CV for this posting →</a>"
               "<div class=muted style='margin-top:6px'>Selects and orders lines from your "
               "own profile against what this posting asks for. Writes nothing new.</div>")
        + "<h2>Project write-up</h2>"
        + card(f"<a class=ghost href='/jobs/{esc(job['id'])}/project'>"
               "Build a one-page write-up for this posting →</a>"
               "<div class=muted style='margin-top:6px'>Five parts, 90 seconds to read. "
               "Uses the lines the CV builder cut out — that is where they belong.</div>")
        + "<h2>The posting</h2>"
        + card(f"<pre class=jd>{esc(job['jd'])}</pre>")
        # NÚT THẬT, nối vào đúng đường mà nút Nộp bên danh sách đang dùng.
        #
        # Chỗ này trước đây là hai nút VẼ: "Queue for approval" và "Reject…" —
        # không mang data-* nào, mà mọi trình nghe trong live.js đều bắt theo
        # data-*, nên bấm vào không có gì xảy ra. Chúng là tàn dư của bản thiết
        # kế cũ, hồi trang chi tiết định làm cổng duyệt. Cổng duyệt thật bây
        # giờ là tab Quản lí.
        #
        # Xoá hẳn thì trang này đọc xong không làm gì được, phải quay ra danh
        # sách mới bấm Nộp được — nên thay bằng nút thật, không phải bỏ trống.
        + f"<div class=actbar><button class='mbtn go' data-post='/api/apply'"
          f" data-arg='{esc(job['id'])}'>Nộp tin này</button>"
          "<span class=muted>Mở form nộp trong Chrome và thêm một dòng vào "
          "Quản lí. Chưa gửi gì cả — nút Gửi nằm bên Quản lí.</span></div>",
        active="/jobs",
    )
