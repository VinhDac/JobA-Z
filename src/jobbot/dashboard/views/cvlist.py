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
                 run_note=info.get("note", ""),
                 sua=("/cv/soan", "Sửa khối",
                      "Mở màn soạn khối — rộng cả cửa sổ, chấm từng câu")),
        note=note,
        cols=2, columns="minmax(360px, 1fr) 1.6fr",
        rows_tpl="minmax(260px, auto) 1fr 140px", journal_at=(1, 3),
        panels=[
            # HỤT đứng TRÊN kho khối: nó nói việc phải làm, kho khối nói
            # thứ đang có. Việc phải làm đọc trước.
            runtime.panel("Viết gì để hết hụt", hut(gap or {}), at=(1, 1)),
            runtime.panel("Khối nguyên liệu", _blocks(blocks), at=(1, 2)),
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


# --------------------------------------------------------- kho khối

KIND_TAG = {"experience": "việc", "project": "project"}


def _blocks(blocks: list[dict]) -> str:
    """Kho nguyên liệu, xếp theo VỚI TỚI BAO NHIÊU TIN.

    Cột đó là cả câu chuyện: khối 0 tin lên CV vì có ô trống phải lấp, không
    vì nó chứng minh được gì.

    Bấm một khối là sang màn SOẠN (/cv/soan) — ô này chỉ để nhìn.
    """
    rows = ""
    for b in blocks:
        skills = "".join(f"<span class=sk>{esc(s)}</span>" for s in b["skills"][:5])
        dead = " dead" if b["reach"] == 0 else ""
        rows += (
            # quote(), KHÔNG phải esc(): esc() là để CHỮ hiện an toàn trong
            # HTML, còn đây là THAM SỐ URL. Tiêu đề "Research & Development"
            # thoát HTML thành "Research &amp; Development" — dấu & vẫn cắt
            # tham số, và trang mở ra một khối khác hoặc khối rỗng.
            f"<a class='blk{dead}'"
            f" href='/cv/soan?khoi={quote(b['title'], safe='')}'>"
            f"<div class=blkmain>"
            f"<div class=blkhead><b>{esc(b['title'][:44])}</b>"
            f"<span class=blkkind>{esc(KIND_TAG.get(b['kind'], b['kind']))}</span></div>"
            f"<div class=blktags>{skills or '<span class=muted>không kỹ năng nào</span>'}</div>"
            f"</div>"
            f"<div class=blkreach><b>{b['reach']}</b><span>tin</span>"
            f"<i>{len(b['lines'])} câu</i></div></a>")

    return (
        f"<div class=gapnote>Xếp theo <b>số tin khối đó với tới</b>. "
        f"Khối <b>0 tin</b> đang chiếm chỗ chứ không chứng minh gì.</div>"
        f"<div class=blklist>{rows}</div>"
        f"<div class=blkfoot>"
        f"<a class='mbtn apply' href='/cv/soan?moi=1'>+ Khối mới</a>"
        f"</div>")


# ------------------------------------------------------ tấm Điều chỉnh ⚟

# BA NÚM, và mỗi núm phải trả lời được "xoay nó thì bản CV đổi thế nào" bằng
# một câu. Núm nào không trả lời được thì nó là núm trang trí — và một núm
# trang trí làm người dùng mất tin vào cả bảng.
#
# Cả ba xoay SỐ ĐÃ CÓ trong cv/rules.py, không đẻ khái niệm mới:
#   giọng văn  -> bật/tắt phép lược chủ ngữ trong cv/rewrite.py
#   từ khoá    -> trọng số "trúng thứ tin đòi" trong rules.sentence_weight
#   bố cục     -> số dòng mỗi khối (rules.BUDGET)
# HAI NÚM NHIỀU MỨC. Cả hai đo được là ĐỔI THẬT: giọng văn đổi 60/60 bản,
# bố cục đổi 60/60. Núm "độ dày từ khoá" đã BỎ — đo trên 60 tin, xoay sang
# "dày" đổi ĐÚNG 0 bản, và nó dựa trên "keyword density", thứ không nhà cung
# cấp ATS nào công bố công thức.
NUM = (
    ("giong", "Giọng văn",
     "Câu trên CV mở đầu thế nào. Máy chỉ CẮT chữ bạn viết — không viết thêm.",
     (("cv", "Lược chủ ngữ", "Built… · Designed… — quy ước của CV"),
      ("nguyen", "Giữ nguyên", "I built… · I designed… — đúng giọng bạn viết"))),
    ("bo_cuc", "Bố cục",
     "Mấy dòng mỗi khối. Trần một mặt giấy: gọn thì đọc nhanh nhưng nói được "
     "ít, đầy thì ngược lại.",
     (("gon", "Gọn", "2 dòng mỗi khối"),
      ("thuong", "Thường", "3 dòng mỗi khối"),
      ("day", "Đầy", "4 dòng mỗi khối"))),
)

# CÔNG TẮC = mấy quyết định máy đang TỰ LÀM THAY. Mỗi cái kèm con số nó đang
# tốn, đo trên chính hồ sơ này — không có số thì đó chỉ là một nút bấm thử.
# CÔNG TẮC = mấy quyết định máy đang TỰ LÀM THAY.
#
# Chữ ở đây mô tả LUẬT, không trích câu của ai. Bản trước gõ cứng câu của một
# người vào phần giải thích ("«drawdown ran 30% deeper than predicted»"); hồ
# sơ khác mở lên thì đó là câu của người lạ, và cái panel thành tờ quảng cáo
# chứ không phải bản mô tả hồ sơ của họ.
#
# Ví dụ THẬT lấy từ chính hồ sơ đang mở — xem live.cv_gia.
CONG_TAC = (
    ("that_bai", "Giữ câu kể thất bại",
     "Câu kể một kết cục xấu của chính bạn. Chỗ của nó là buổi phỏng vấn, nơi "
     "người đọc có kinh nghiệm coi sự trung thực là điểm mạnh — không phải "
     "trước mặt người sàng 200 CV một buổi chiều."),
    ("y_kien", "Giữ câu không kể việc bạn làm",
     "Câu không nói bạn LÀM gì, không có số đo, không nhắc kỹ năng nào. Nó có "
     "thể là kiến thức đáng giá, cũng có thể chỉ là một câu hay — máy không "
     "phân biệt được nên nó đánh dấu chứ không xoá."),
    ("rui_ro", "Giữ câu mời người đọc nghi ngờ",
     "Câu nhắc tới tài khoản demo, vốn tự bỏ, hay công cụ AI. Chúng làm người "
     "đọc đặt câu hỏi về quy mô thật của việc bạn làm. Câu nào có số đo cứng "
     "thì luật chỉ đánh dấu 'xem lại' chứ không bỏ."),
    ("giu_muc", "Giữ mục kỹ năng mềm",
     "Mục kỹ năng mà cả dòng không có lấy một cái tên công nghệ nào — nó đang "
     "chiếm chỗ bằng tính từ."),
    ("moi_khoi_viec", "Giữ MỌI khối kinh nghiệm",
     "Tắt đi thì chỉ in khối hợp với tin. Nhưng khối vắng mặt để lại một lỗ "
     "trên dòng thời gian, và khoảng trống đắt hơn nhiều so với một khối kém "
     "liên quan."),
)


def adjust(num: dict, gia: dict | None = None) -> str:
    """Tấm phủ ⚟ — mấy quyết định của tầng CV.

    Bấm là có tác dụng ngay, KHÔNG đi qua nút Áp dụng — giống công tắc nguồn ở
    tab Search. Nhưng nó không tự dựng lại: dựng mất 5 giây, và người vừa lật
    thử một công tắc chưa chắc muốn trả cái giá đó ngay.

    MỖI CÔNG TẮC KÈM CON SỐ CỦA HÔM NAY. Đó là khác biệt giữa tấm này và một
    bảng nút: "Giữ câu kể thất bại" thì chưa ai quyết được gì, nhưng "Giữ câu
    kể thất bại — đang bỏ 5 câu" thì đọc xong là biết mình đang đánh đổi cái gì.
    """
    dang = (num or {}).get("ten") or {}
    g = gia or {}
    def _noi(ma: str) -> str:
        """Công tắc này đang làm gì với hồ sơ NÀY. Không đổi gì thì NÓI RA —
        im lặng để người dùng tự bấm thử rồi không thấy khác là cách chắc
        chắn nhất làm họ thôi tin cả bảng."""
        d = g.get(ma) or {}
        phan = []
        if d.get("bo"):
            phan.append(f"đang bỏ {d['bo']} câu")
        if d.get("xem"):
            phan.append(f"đánh dấu {d['xem']} câu 'xem lại' (vẫn in ra)")
        return " · ".join(phan) or "hồ sơ này không có câu nào dính luật"

    so = {ma: _noi(ma) for ma in ("that_bai", "y_kien", "rui_ro")}
    so["giu_muc"] = (("đang bỏ mục " + " · ".join(g.get("muc") or []))
                     if g.get("muc") else "hồ sơ không có mục nào bị bỏ")
    so["moi_khoi_viec"] = f"{g.get('khoi_viec', 0)} khối kinh nghiệm trong hồ sơ"

    khoi = []
    for ma, ten, y_nghia, chon in NUM:
        nut = "".join(
            f"<button class='mbtn tiny{'' if dang.get(ma) == gia_tri else ' off'}'"
            f" data-post='/api/cv/num' data-arg='{esc(ma)}:{esc(gia_tri)}'"
            f" title='{esc(ghi)}'>{esc(nhan)}</button>"
            for gia_tri, nhan, ghi in chon)
        khoi.append(
            f"<label class=slab>{esc(ten)}<span>{esc(y_nghia)}</span></label>"
            f"<div class=srcrow>{nut}</div>")

    hang = []
    for ma, ten, y_nghia in CONG_TAC:
        on = bool(dang.get(ma))
        # VÍ DỤ LẤY TỪ CHÍNH HỒ SƠ ĐANG MỞ. Đây là thứ biến một dòng mô tả
        # chung chung thành một câu nói về hồ sơ của người đang đọc: họ nhận
        # ra ngay câu đó là câu mình viết, và quyết được luôn.
        vd = (g.get(ma) or {}).get("vi_du") or []
        cau_minh = "".join(f"<span class=swvd>{esc(x)}</span>" for x in vd[:2])
        hang.append(
            f"<div class=swrow>"
            f"<button class='mbtn tiny swbtn{'' if on else ' off'}'"
            f" data-post='/api/cv/num' data-arg='{esc(ma)}:{'0' if on else '1'}'>"
            f"{'BẬT' if on else 'TẮT'}</button>"
            f"<div class=swmain><b>{esc(ten)}</b>"
            f"<span class=swnow>{esc(so.get(ma, ''))}</span>"
            f"{cau_minh}"
            f"<span class=swwhy>{esc(y_nghia)}</span></div></div>")

    return ("<div class=sheethead>Điều chỉnh · CV</div>"
            + "".join(khoi)
            + "<label class=slab>Máy đang tự quyết thay bạn"
              "<span>mỗi công tắc kèm con số nó đang tốn, đo trên chính hồ sơ "
              "của bạn</span></label>"
            + "".join(hang)
            + "<div class=note>Lật công tắc xong thì nút trên thanh đổi thành "
              "<b>Cập nhật</b> — bấm lúc nào cũng được. Máy không tự dựng lại: "
              "dựng mất ~5 giây và đó là quyết định của bạn.</div>")


# ------------------------------------------------------------ khối HỤT

# CHÚ THÍCH PHẢI NÓI ĐÚNG THỨ MÁY ĐO. Bản trước ghi "bạn có làm rồi, chỉ chưa
# viết ra" — máy không biết điều đó và chưa bao giờ đo nó; nó chỉ đo được là
# mấy dòng yêu cầu này không gọi tên sản phẩm nào. Khẳng định thay người dùng
# là đúng cái bệnh cả app này tránh.
VIEC = {"viet": ("VIẾT", "viet",
                 "mấy dòng đòi nó không gọi tên sản phẩm nào — diễn đạt lại "
                 "bằng chữ của bạn được, nếu bạn đã làm. Một buổi tối."),
        "hoc": ("HỌC", "hoc",
                "gọi đích danh tên sản phẩm — không câu nào viết thay được")}


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
            # NÚT VIẾT chỉ trên dòng CÓ THỂ VIẾT. Dòng toàn tên sản phẩm
            # thì mời viết là mời làm một việc không làm được.
            + (f"<a class='mbtn tiny hgo'"
               f" href='/cv/soan?ky={quote(b['ky_nang'], safe='')}'>Viết</a>"
               if b["dong"] - b["rieng"] > 0 else "")
            + f"<span class=hsplit>{b['dong']} dòng đòi · "
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
