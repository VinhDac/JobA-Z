"""CV — mọi bản hệ thống SẼ GỬI, xem trước khi gửi.

Tab này KHÔNG phải chỗ soạn CV. Bản gốc vẫn là `cv_text` trong Hồ sơ — chữ của
Vin, và luật gốc không đổi: máy CHỌN và SẮP XẾP, không viết mới (xem cv/build).

Đây là chỗ NHÌN TRƯỚC. Trước khi bước 5 gửi bất cứ thứ gì đi, Vin phải đọc
được mọi bản sẽ đi ra ngoài, trên một trang.

Vì sao gộp bản trùng: 101 tin đáng nộp, nhưng chỉ 29 bản khác nhau. Cấu trúc
CV cố định — 2 việc · 3 project · 2 học vấn · 1 chứng chỉ · 4 kỹ năng = 16 câu
— nên phần đổi chỉ là CÂU NÀO trong mỗi khối được chọn. Liệt kê đủ 101 dòng là
bắt đọc lại cùng một bản ba bốn lần.

CHỈ VẼ.
"""

from __future__ import annotations

from html import escape as esc
from urllib.parse import quote

from . import runtime

KIND_LABEL = {"experience": "việc", "project": "project", "education": "học vấn",
              "cert": "chứng chỉ", "skill": "kỹ năng", "summary": "tóm tắt"}


def _khop(job: dict, q: str) -> bool:
    """Tin này có khớp chữ đang tìm không — theo CÔNG TY hoặc CHỨC DANH."""
    return q in (job.get("company") or "").lower() \
        or q in (job.get("title") or "").lower()


def _row(index: int, ver: dict, q: str = "") -> str:
    """MỘT dòng = một NHÓM TIN dùng chung một bản CV.

    NGƯỜI DÙNG KHÔNG NỘP CHO "BẢN", HỌ NỘP CHO MỘT TIN. Nên dòng phải dẫn
    bằng tin, không dẫn bằng tài liệu.

    Bản cũ in ra 4 câu tiếng Anh RIÊNG của bản này. Đó là chữ chính Vin viết —
    đọc lại không nắm thêm được gì, mà nhân 28 dòng thì không ai đọc nổi. Nó
    cũng không trả lời được câu hỏi thật của người đứng trước 364 tin: *giờ
    tôi nên nộp cái nào, và bản này có đủ tốt để gửi không.*

    Bốn thứ, theo đúng thứ tự cần đọc:

        tin nào      công ty — chức danh — điểm, chính là thứ bấm vào để nộp
        đủ chưa      trả lời được mấy phần thứ TIN ĐÓ hỏi  <- chốt chặn
        rộng bao xa  còn mấy tin nữa dùng chung bản này
        thiếu gì     kỹ năng tin đó đòi mà CV câm  <- việc phải làm

    Chi tiết (từng câu, sửa gì, vì sao bỏ) nằm ở trang bấm vào — chỗ có cả
    bản chấm điểm. Danh sách để QUÉT, trang chi tiết để ĐỌC.
    """
    jobs = ver["jobs"]
    if q:
        jobs = sorted(jobs, key=lambda j: not _khop(j, q))
    # Đang tìm thì dòng phải mở đúng tin vừa gõ tên, không mở tin điểm cao
    # nhất của nhóm — người ta gõ "Man Group" là muốn xem bản gửi Man Group.
    hop = [j for j in jobs if _khop(j, q)] if q else jobs
    best = max(hop or jobs, key=lambda j: j["score"] or 0)

    # PHỦ — con số chốt của cả dòng. Tính trên MỘT tin (xem live.cv_versions):
    # tính trên hợp cả nhóm thì nó đo kích thước nhóm, không đo chất lượng CV.
    hoi = int(ver.get("hoi") or 0)
    tra = int(ver.get("tra_loi") or 0)
    pct = round(100 * tra / hoi) if hoi else 0
    # Ba mức, vì ba mức dẫn tới ba HÀNH ĐỘNG khác nhau: gửi được / gửi được
    # nhưng yếu / viết thêm đã rồi hẵng gửi.
    muc = "ok" if pct >= 60 else ("mid" if pct >= 35 else "low")
    thanh = (f"<span class='vbarc {muc}'><i style='width:{pct}%'></i></span>"
             if hoi else "")
    do = (f"<b>{tra}/{hoi}</b> thứ tin này hỏi" if hoi
          else "<b>—</b> tin này không gọi tên kỹ năng nào")

    khac = (f" · dùng chung cho {len(jobs):,} tin" if len(jobs) > 1 else "")

    # HAI CON SỐ, HAI CÂU HỎI KHÁC NHAU — phải nói rõ, không thì người đọc
    # trừ 7−1=6 rồi thấy bên dưới chỉ liệt kê 2 và tưởng máy đếm sai:
    #   tra/hoi   BẢN NÀY trả lời được mấy thứ TIN ĐÓ hỏi
    #   cam       CẢ HỒ SƠ không có câu nào về mấy thứ này
    # Ở giữa là thứ hồ sơ CÓ mà bản này không kịp dùng — đó là chuyện bố cục,
    # xem ở trang chi tiết.
    cam = ver.get("cam") or ver.get("missing") or []
    gap = ""
    if cam:
        chip = "".join(f"<span class=cvmiss>{esc(m)}</span>" for m in cam[:5])
        if len(cam) > 5:
            chip += f"<span class=cvmiss>+{len(cam) - 5}</span>"
        gap = f"<div class=cvgap>hồ sơ chưa có câu nào về: {chip}</div>"

    return (
        f"<a class=cvrow href='/jobs/{best['id']}/cv'>"
        f"<div class=cvn>#{index}</div>"
        f"<div class=cvmain>"
        f"<div class=cvwho><b>{esc(best['company'])}</b>"
        f"<span class=vjob>{esc(best['title'])}</span></div>"
        f"<div class=vline>{thanh}<span class=vfrac>{do}</span>"
        f"<span class=muted>{esc(khac)}</span></div>"
        f"{gap}</div>"
        f"<div class=cvact><span class=cvscore>{best['score']}</span>"
        f"<button class='mbtn tiny' data-post='/cv/pdf'"
        f" data-arg='{best['id']}' onclick='event.preventDefault()'>PDF</button>"
        f"<span class=muted>xem →</span></div></a>")


def _tim(q: str) -> str:
    """Ô TÌM trong mấy bản đã dựng.

    Câu hỏi thật của người dùng ở ô này không phải "cho tôi xem 28 bản", mà là
    "gửi Man Group thì dùng bản nào". 28 dòng không trả lời được câu đó; gõ
    tên công ty thì trả lời được ngay.

    FORM GET, không JavaScript — giống ô tìm ở tab Search: trạng thái nằm hết
    trên URL, nên gõ xong bấm Enter là ra một địa chỉ lưu lại được và Back được.
    """
    xoa = ("<a class=jfindx href='/cv' title='Bỏ tìm, xem lại tất cả'>×</a>"
           if q else "")
    return (f"<form class=jfind method=get action='/cv'>"
            f"<input class=search type=search name=q value='{esc(q)}'"
            f" autocomplete=off spellcheck=false"
            f" placeholder='gửi cho ai — gõ tên công ty hoặc chức danh'>"
            f"{xoa}</form>")


def _list(data: dict, q: str = "") -> str:
    versions = data["versions"]
    if not versions:
        return ("<div class=empty-box>chưa có tin nào đáng nộp — chạy Search "
                "trước, hoặc nới lưới lọc</div>")

    lines = versions[0]["lines"]
    core = data["core"]
    gaps = "".join(f"<span class=cvmiss>{esc(g)}</span>" for g in data["gaps"][:14])

    # Nói thẳng mức may đo thật. "29 bản khác nhau" nghe như nhiều, nhưng
    # 14/16 câu giống hệt nhau ở mọi bản — chỉ 2 câu đổi theo JD.
    head = (f"<div class=gapnote><b>{len(versions)}</b> bản cho "
            f"<b>{data['jobs']}</b> tin đáng nộp. Nhưng <b>{core}/{lines}</b> câu "
            f"giống hệt nhau ở mọi bản — chỉ <b>{lines - core}</b> câu đổi theo JD. "
            f"Dưới đây mỗi dòng chỉ in phần RIÊNG của bản đó.</div>")
    if gaps:
        head += (f"<div class=cvgaps>Hồ sơ KHÔNG nói được câu nào về: {gaps}"
                 f"<span class=muted>— đây là chỗ project mới nên nhắm</span></div>")

    head += _tim(q)

    # LỌC SAU KHI ĐÁNH SỐ. Số hiệu bản phải giữ nguyên khi tìm — "#7" lúc tìm
    # mà là "#3" lúc không tìm thì không nói chuyện được về nó.
    danh = list(enumerate(versions, 1))
    if q:
        low = q.lower()
        danh = [(i, v) for i, v in danh if any(_khop(j, low) for j in v["jobs"])]
        if not danh:
            return (head + "<div class=empty-box>không bản nào gửi cho "
                    f"«{esc(q)}» — thử tên công ty hoặc chức danh khác</div>")
        head += (f"<div class=gapnote><b>{len(danh)}</b>/{len(versions)} bản "
                 f"có tin khớp «{esc(q)}»</div>")

    return head + "<div class=vlist>" + "".join(
        _row(i, v, q.lower()) for i, v in danh) + "</div>"


def render(*, versions: list[dict], jobs: int, gaps: list[str],
           core: int = 0, blocks: list[dict] | None = None,
           stage: dict | None = None, q: str = "",
           gap: dict | None = None) -> str:
    """Tab CV. KHỐI là nguyên liệu của Vin; BẢN SẼ GỬI là thứ máy dựng ra.

    Hai ô đó khác hẳn nhau về quyền sở hữu, nên chỉ ô bên phải chờ nút Chạy:
    khối thì Vin gõ vào và thấy ngay, bản thì phải bấm mới dựng.
    """
    from ..layout import deck
    info = stage or {}
    data = {"versions": versions, "jobs": jobs, "gaps": gaps, "core": core}
    blocks = blocks or []
    words = sum(len(b["lines"]) for b in blocks)
    # LỜI DẪN phải nói đúng tình trạng. Chưa dựng mà vẫn ghi "26 câu -> 0 bản
    # cho 364 tin" thì người dùng tưởng máy dựng hỏng, chứ không hiểu là mình
    # chưa bấm.
    note = (f"{words} câu nguyên liệu → {len(versions)} bản cho {jobs} tin. "
            f"Kho câu là TRẦN của cả hệ thống: muốn CV trúng hơn thì viết "
            f"thêm khối, không phải chọn khéo hơn." if versions else
            f"{words} câu nguyên liệu trong kho. Chưa dựng bản nào — bấm "
            f"Chạy trên thanh trên để máy đọc từng tin rồi dựng bản riêng "
            f"cho nó.")
    return runtime.render(
        title="CV", active="/cv", stream="cv", journal="corner",
        bar=deck("cv", "CV", info.get("state", "chưa dựng bản nào"),
                 [(f"{words}", "câu kho", "stock"),
                  (f"{len(versions)}", "bản", "act"),
                  (f"{info.get('worth', 0):,}", "tin đáng nộp", "view")],
                 adjust="/adjust/cv",
                 run=info.get("label", "Chạy"),
                 run_note=info.get("note", "")),
        note=note,
        cols=2, columns="minmax(360px, 1fr) 1.6fr",
        rows_tpl="minmax(260px, auto) 1fr 140px", journal_at=(1, 3),
        panels=[
            # HỤT đứng TRÊN kho khối: nó nói việc phải làm, kho khối nói
            # thứ đang có. Việc phải làm đọc trước.
            runtime.panel("Viết gì để hết hụt", hut(gap or {}), at=(1, 1)),
            runtime.panel("Khối nguyên liệu", _blocks(blocks, gaps), at=(1, 2)),
            runtime.panel("Bản sẽ gửi", _list(data, q) if versions
                          else _chua_dung(info), rows=3, at=(2, 1)),
        ],
    )


def _chua_dung(info: dict) -> str:
    """Ô trống khi chưa bấm Chạy. Nói ra SẼ CÓ GÌ, không chỉ nói là trống.

    "Chưa có dữ liệu" là câu vô dụng: nó không cho người dùng biết bấm vào thì
    được gì, nên họ không bấm.
    """
    ly_do = esc(info.get("note", ""))
    return (
        "<div class=empty-box>"
        "<b>Chưa dựng bản CV nào.</b><br>"
        "Bấm <b>Chạy</b> trên thanh trên. Máy sẽ đọc từng tin đáng nộp, hỏi "
        "kho câu của bạn xem câu nào trả lời được yêu cầu của tin đó, rồi "
        "dựng một bản riêng — kèm bản so sánh trước/sau và lý do từng câu "
        "được chọn hay bị bỏ."
        f"<br><span class=muted>{ly_do}</span></div>")


# ------------------------------------------------------------ soạn khối

KIND_TAG = {"experience": "việc", "project": "project"}


def _blocks(blocks: list[dict], gaps: list[str]) -> str:
    """Kho nguyên liệu, xếp theo VỚI TỚI BAO NHIÊU TIN.

    Cột đó là cả câu chuyện: khối 0 tin lên CV vì có ô trống phải lấp, không
    vì nó chứng minh được gì.
    """
    rows = ""
    for b in blocks:
        skills = "".join(f"<span class=sk>{esc(s)}</span>" for s in b["skills"][:5])
        dead = " dead" if b["reach"] == 0 else ""
        rows += (
            f"<a class='blk{dead}' href='#' data-settings="
            # quote(), KHÔNG phải esc(): esc() là để CHỮ hiện an toàn trong
            # HTML, còn đây là THAM SỐ URL. Tiêu đề "Research & Development"
            # thoát HTML thành "Research &amp; Development" — dấu & vẫn cắt
            # tham số, và trang mở ra một khối khác hoặc khối rỗng.
            f"'/cv/block?title={quote(b['title'], safe='')}'>"
            f"<div class=blkmain>"
            f"<div class=blkhead><b>{esc(b['title'][:44])}</b>"
            f"<span class=blkkind>{esc(KIND_TAG.get(b['kind'], b['kind']))}</span></div>"
            f"<div class=blktags>{skills or '<span class=muted>không kỹ năng nào</span>'}</div>"
            f"</div>"
            f"<div class=blkreach><b>{b['reach']}</b><span>tin</span>"
            f"<i>{len(b['lines'])} câu</i></div></a>")

    aim = "".join(f"<span class=cvmiss>{esc(g)}</span>" for g in gaps[:8])
    return (
        f"<div class=gapnote>Xếp theo <b>số tin khối đó với tới</b>. "
        f"Khối <b>0 tin</b> đang chiếm chỗ chứ không chứng minh gì.</div>"
        f"<div class=blklist>{rows}</div>"
        f"<div class=blkfoot>"
        f"<button class='mbtn apply' data-settings='/cv/block?title='>+ Khối mới</button>"
        f"</div>")


def edit(block: dict | None, gaps: list[str]) -> str:
    """Mảnh HTML cho tấm phủ: soạn một khối.

    Ghi thẳng vào `cv_text` — MỘT nguồn sự thật. Không dựng bảng khối riêng:
    hai kho thì phải ngồi giữ chúng khớp nhau, đúng cái bệnh vừa chữa xong ở
    tầng chấm điểm và tầng dựng CV.
    """
    b = block or {"kind": "project", "title": "", "meta": "", "lines": [],
                  "skills": [], "reach": 0}
    boxes = "".join(
        f"<textarea class=cvdraft name=line rows=2>{esc(l)}</textarea>"
        for l in b["lines"] + ["", ""])
    kinds = "".join(
        f"<option value='{k}'{' selected' if k == b['kind'] else ''}>{esc(v)}</option>"
        for k, v in KIND_TAG.items())
    aim = "".join(f"<span class=cvmiss>{esc(g)}</span>" for g in gaps[:10])

    return (
        "<form class=setform method=post action='/cv/block'>"
        f"<h3>{'Sửa khối' if block else 'Khối mới'}</h3>"
        "<div class=safe>Mỗi câu ở đây là một câu có thể lên CV. Câu nào không "
        "chứng minh được gì thì không tin nào với tới — nhưng câu nói về QUY MÔ "
        "hay VẾT XƯỚC vẫn đáng viết, chúng thuyết phục theo cách khác.<br>"
        f"Đang câm ở: {aim}</div>"
        f"<input type=hidden name=was value='{esc(b['title'])}'>"
        f"<label class=slab>Loại</label><select name=kind>{kinds}</select>"
        "<label class=slab>Tên khối</label>"
        f"<input class=dfthead type=text name=title value='{esc(b['title'])}'>"
        "<label class=slab>Ngày tháng / tổ chức<span>để trống nếu là project</span></label>"
        f"<input class=dfthead type=text name=meta value='{esc(b['meta'])}'>"
        f"<label class=slab>Câu<span>mỗi ô một câu · ô trống thì bỏ qua</span></label>"
        f"{boxes}"
        "<div class=setfoot>"
        "<button class='mbtn apply' type=submit>Lưu vào CV gốc</button>"
        + (f"<button class='mbtn kill' type=submit name=kill value=1>Xoá khối"
           f"</button>" if block else "")
        + "<span class=applynote>ghi thẳng vào hồ sơ · mọi bản CV dựng lại từ đó"
        "</span></div>"
        + (f"<div class=forced>Khối này hợp với <b>{b['reach']}</b> tin. "
           f"Không hợp tin nào thì xoá đi cho sạch — giữ lại chỉ làm CV gốc "
           f"bẩn thêm.</div>" if block and b["reach"] == 0 else "")
        + "</form>")


# ------------------------------------------------------ tấm Điều chỉnh ⚟

# BA NÚM, và mỗi núm phải trả lời được "xoay nó thì bản CV đổi thế nào" bằng
# một câu. Núm nào không trả lời được thì nó là núm trang trí — và một núm
# trang trí làm người dùng mất tin vào cả bảng.
#
# Cả ba xoay SỐ ĐÃ CÓ trong cv/rules.py, không đẻ khái niệm mới:
#   giọng văn  -> bật/tắt phép lược chủ ngữ trong cv/rewrite.py
#   từ khoá    -> trọng số "trúng thứ tin đòi" trong rules.sentence_weight
#   bố cục     -> số dòng mỗi khối (rules.BUDGET)
NUM = (
    ("giong", "Giọng văn",
     "Câu trên CV mở đầu thế nào. Máy chỉ CẮT chữ bạn viết — không viết thêm.",
     (("cv", "Lược chủ ngữ", "Built… · Designed… — quy ước của CV"),
      ("nguyen", "Giữ nguyên", "I built… · I designed… — đúng giọng bạn viết"))),
    ("khoa", "Độ dày từ khoá",
     "Máy ưu tiên câu TRÚNG thứ tin đòi đến mức nào. Đây KHÔNG phải nút nhồi "
     "từ khoá: máy không thêm từ nào, nó chỉ đổi thứ tự ưu tiên giữa mấy câu "
     "bạn đã viết.",
     (("nhe", "Nhẹ", "ưu tiên câu mạnh về nội dung, dù không trúng từ nào"),
      ("thuong", "Thường", "cân giữa trúng từ khoá và nội dung"),
      ("day", "Dày", "ưu tiên câu trúng từ khoá — qua máy sàng ATS dễ hơn"))),
    ("bo_cuc", "Bố cục",
     "Mấy dòng mỗi khối. Trần một mặt giấy: gọn thì đọc nhanh nhưng nói được "
     "ít, đầy thì ngược lại.",
     (("gon", "Gọn", "2 dòng mỗi khối"),
      ("thuong", "Thường", "3 dòng mỗi khối"),
      ("day", "Đầy", "4 dòng mỗi khối"))),
)


def adjust(num: dict) -> str:
    """Mảnh cho tấm phủ ⚟ — BA NÚM của tầng CV.

    Bấm là có tác dụng ngay, KHÔNG đi qua nút Áp dụng — giống công tắc nguồn ở
    tab Search. Nhưng nó không tự dựng lại: dựng mất 5 giây, và người vừa xoay
    thử một núm chưa chắc muốn trả cái giá đó. Nên nút Chạy đổi thành "Cập
    nhật" và để người quyết lúc nào.
    """
    dang = (num or {}).get("ten") or {}
    khoi = []
    for ma, ten, y_nghia, chon in NUM:
        nut = "".join(
            f"<button class='mbtn tiny{'' if dang.get(ma) == gia else ' off'}'"
            f" data-post='/api/cv/num' data-arg='{esc(ma)}:{esc(gia)}'"
            f" title='{esc(ghi)}'>{esc(nhan)}</button>"
            for gia, nhan, ghi in chon)
        giai = "".join(
            f"<div class=krow><span>{esc(nhan)}</span><b>{esc(ghi)}</b></div>"
            for gia, nhan, ghi in chon)
        khoi.append(
            f"<label class=slab>{esc(ten)}<span>{esc(y_nghia)}</span></label>"
            f"<div class=srcrow>{nut}</div><div class=krows>{giai}</div>")
    return ("<div class=sheethead>Điều chỉnh · CV</div>"
            + "".join(khoi)
            + "<div class=note>Xoay núm xong thì nút trên thanh đổi thành "
              "<b>Cập nhật</b> — bấm lúc nào cũng được. Máy không tự dựng lại: "
              "dựng mất ~5 giây và đó là quyết định của bạn.</div>")


# ------------------------------------------------------------ khối HỤT

VIEC = {"viet": ("VIẾT", "viet", "bạn có làm rồi, chỉ chưa viết ra — một buổi tối"),
        "hoc": ("HỌC", "hoc", "gọi đích danh tên sản phẩm, không viết thay được")}


def hut(d: dict) -> str:
    """Viết thêm câu về cái gì thì bao nhiêu TIN HẾT HỤT.

    Khối trả lời câu hỏi duy nhất của tab này: *tối nay tôi viết gì?*

    ĐƠN VỊ LÀ TIN HẾT HỤT — tin mà MỌI dòng must đều đáp được. Đếm theo lượt
    thì `cloud` đứng đầu (50 dòng) trong khi nó chỉ mở khoá thêm 19 tin, còn
    `visualisation` mở 28. Đếm sai đơn vị là xếp sai thứ tự việc.

    Mỗi dòng là GIÁ TRỊ BIÊN khi đã làm xong mấy dòng trên nó — ba kỹ năng
    cùng mở một tin thì cộng riêng lẻ là đếm tin đó ba lần.
    """
    buoc = d.get("buoc") or []
    tong, nen = d.get("tin") or 0, d.get("nen") or 0
    if not buoc or not tong:
        return ("<div class=empty-box>Chưa đo được chỗ hụt — cần tin đã chấm "
                "điểm. Chạy Search trước.</div>")

    hang = []
    for b in buoc:
        nhan, lop, y = VIEC.get(b["viec"], VIEC["viet"])
        viet_duoc = b["dong"] - b["rieng"]
        # Vạch dài theo SỐ TIN MỞ KHOÁ, không theo số dòng — đó là thứ quyết định
        rong = round(100 * b["them"] / max(1, buoc[0]["them"]))
        hang.append(
            f"<div class=hrow title='{esc(y)}'>"
            f"<span class='hlab {lop}'>{nhan}</span>"
            f"<span class=hname>{esc(b['ky_nang'])}</span>"
            f"<span class=hbar><i style='width:{rong}%' class={lop}></i></span>"
            f"<span class=hplus>+{b['them']}<span>tin</span></span>"
            f"<span class=hcum>{b['cong_don']}<span>/{tong}</span></span>"
            f"<span class=hsplit>{b['dong']} dòng đòi · "
            f"<b>{viet_duoc}</b> viết được"
            + (f" · <b>{b['rieng']}</b> phải học" if b["rieng"] else "")
            + "</span></div>")

    het = buoc[-1]["cong_don"]
    cv_ = d.get("chi_viet") or nen
    nv = d.get("so_viet") or 0
    # HAI ĐÍCH, KHÔNG MỘT. "Làm hết bảng" gộp cả mấy dòng phải đi HỌC — học
    # tính bằng tháng, viết tính bằng buổi tối. Gộp lại là chỉ cho người dùng
    # một cái đích tối nay không với tới được.
    return (
        f"<div class=gapnote>Hồ sơ đang đáp trọn <b>{nen}</b>/{tong} tin "
        f"(<b>{nen * 100 // tong}%</b>).</div>"
        f"<div class=htarget>"
        f"<span class=ht1><b>{cv_}</b> tin ({cv_ * 100 // tong}%)"
        f"<span>chỉ cần VIẾT {nv} câu — làm được tối nay</span></span>"
        f"<span class=ht2><b>{het}</b> tin ({het * 100 // tong}%)"
        f"<span>nếu đi học nốt mấy thứ còn lại</span></span></div>"
        f"<div class=gapnote>Mỗi dòng là số tin mở khoá THÊM khi đã làm xong "
        f"mấy dòng trên nó — không phải cộng lại.</div>"
        + "".join(hang)
        + "<div class=note><b>VIẾT</b> = dòng yêu cầu nói chung chung mà bạn "
          "đã làm rồi, chỉ chưa viết ra hồ sơ. <b>HỌC</b> = nó gọi đích danh "
          "tên sản phẩm, không câu nào viết thay được. Máy chỉ chọn được chữ "
          "bạn đã viết, nên mấy chỗ này là việc của bạn.</div>")

